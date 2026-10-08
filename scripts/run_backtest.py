"""Run pre-registered strategies over the walk-forward span and print the metric sheet (1.7d).

    uv run python scripts/run_backtest.py [strategies/*.yaml ...]

With no arguments it runs every file in ``strategies/``. The panel comes from ``var/panel.npz``,
built by ``scripts/build_panel.py``; this script touches no network and reads no session outside
the development span, because the panel it loads does not contain one.

**Every run recorded here is a trial.** PostgreSQL reserves the attempt before evaluation and is
the sole lifetime-count authority after explicit legacy activation. A result is not released to
stdout or an artifact until its terminal transaction has been verified.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Protocol, TypeVar
from uuid import uuid4

import numpy as np
from sqlalchemy import create_engine

from icarus.common.config import load_goal
from icarus.common.logging import get_logger
from icarus.engine.panelbuild import load_panel
from icarus.engine.portfolio import Skipped
from icarus.engine.runner import (
    BacktestResult,
    gate_verdict,
    run_walk_forward,
)
from icarus.state.trial_ledger import (
    EvaluationReservation,
    JsonValue,
    PostgresTrialLedger,
    TrialBatchReceipt,
    TrialBatchReservation,
    TrialBatchTerminal,
    TrialEvaluationResult,
    TrialIdentityConflict,
    TrialKind,
    TrialLedgerUnavailable,
    TrialOrigin,
    TrialReservationAuthorization,
)
from icarus.strategy.dsl import Panel, StrategyCandidate, parse_strategy
from icarus.strategy.library import default_registry

log = get_logger("scripts.run_backtest")

PANEL = Path("var/panel.npz")
STRATEGY_DIR = Path("strategies")
RESULTS = Path("var/backtest_results.json")
GOAL = Path("goal.yaml")
_Loaded = TypeVar("_Loaded")


class _PortfolioLedger(Protocol):
    def reserve(self, batch: TrialBatchReservation) -> TrialBatchReceipt: ...

    def complete(
        self,
        receipt: TrialBatchReceipt,
        results: tuple[TrialEvaluationResult, ...],
    ) -> TrialBatchTerminal: ...

    def fail(self, receipt: TrialBatchReceipt, *, failure_code: str) -> TrialBatchTerminal: ...


def _read_bytes(path: Path) -> bytes:
    try:
        return path.read_bytes()
    except OSError as exc:
        raise SystemExit(f"cannot read counted-trial input: {path}") from exc


def _load_stable(  # noqa: UP047 -- mypy lacks stable PEP 695 support
    path: Path, loader: Callable[[Path], _Loaded]
) -> tuple[_Loaded, str]:
    """Bind the hash to bytes that stayed stable for the whole path-based load."""
    before = _read_bytes(path)
    loaded = loader(path)
    after = _read_bytes(path)
    if before != after:
        raise SystemExit(f"counted-trial input changed while it was being loaded: {path}")
    return loaded, hashlib.sha256(before).hexdigest()


def _utc_timestamp(value: np.datetime64) -> datetime:
    text = np.datetime_as_string(value, unit="us", timezone="UTC")
    return datetime.fromisoformat(text.replace("Z", "+00:00")).astimezone(UTC)


def _portfolio_reservation(
    strategy: StrategyCandidate,
    panel: Panel,
    *,
    strategy_sha256: str,
    panel_sha256: str,
    config_sha256: str,
) -> TrialBatchReservation:
    if len(panel) == 0:
        raise ValueError("cannot reserve an empty portfolio panel")
    return TrialBatchReservation(
        run_group_id=uuid4(),
        origin=TrialOrigin.OPERATOR,
        strategy_name=strategy.name,
        strategy_version=strategy.version,
        strategy_sha256=strategy_sha256,
        panel_sha256=panel_sha256,
        config_sha256=config_sha256,
        primitives=tuple(sorted(strategy.primitives_used())),
        evaluations=(
            EvaluationReservation(
                ordinal=0,
                kind=TrialKind.PORTFOLIO,
                fold_index=None,
                start_index=0,
                end_index_exclusive=len(panel),
                start_ts=_utc_timestamp(panel.ts[0]),
                end_ts=_utc_timestamp(panel.ts[-1]),
                reset_identity="walk_forward_portfolio_v1",
            ),
        ),
    )


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise ValueError("portfolio result payload keys must be strings")
        return {key: _json_value(item) for key, item in value.items()}
    raise ValueError(f"portfolio result contains unsupported {type(value).__name__}")


def _sharpe(result: BacktestResult, *, after_tax: bool) -> Decimal | None:
    metrics = result.oos_after_tax if after_tax else result.oos
    if metrics is None or not metrics.sharpe.is_estimable:
        return None
    point = metrics.sharpe.point
    return Decimal(str(point)) if math.isfinite(point) else None


def _portfolio_result(result: BacktestResult) -> TrialEvaluationResult:
    payload = _json_value(result.as_json())
    if not isinstance(payload, dict):
        raise ValueError("portfolio result payload must be an object")
    return TrialEvaluationResult(
        ordinal=0,
        kind=TrialKind.PORTFOLIO,
        oos_sharpe=_sharpe(result, after_tax=False),
        oos_sharpe_after_tax=_sharpe(result, after_tax=True),
        observation_count=len(result.oos_trades),
        payload=payload,
    )


def _execute_counted_portfolio(
    ledger: _PortfolioLedger,
    batch: TrialBatchReservation,
    evaluate: Callable[[], BacktestResult],
) -> BacktestResult:
    """Return an evaluation only after its complete terminal is durably verified."""
    receipt = ledger.reserve(batch)
    if receipt.authorization is not TrialReservationAuthorization.NEW_EVALUATION:
        raise TrialIdentityConflict(
            "a recovery-only reservation receipt does not authorize portfolio evaluation"
        )
    try:
        result = evaluate()
        rows = (_portfolio_result(result),)
    except Exception:
        ledger.fail(receipt, failure_code="EVALUATION_FAILED")
        raise RuntimeError("portfolio evaluation failed after counted reservation") from None
    try:
        ledger.complete(receipt, rows)
    except TrialLedgerUnavailable:
        # A lost COMMIT acknowledgement is ambiguous. Repeating the same idempotent persistence
        # call verifies the terminal without running the portfolio a second time. If the datastore
        # remains unavailable, the result stays behind this function's release barrier.
        ledger.complete(receipt, rows)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--panel", type=Path, default=PANEL)
    parser.add_argument("--out", type=Path, default=RESULTS)
    args = parser.parse_args()

    files = args.files or sorted(STRATEGY_DIR.glob("*.yaml"))
    if not files:
        raise SystemExit(f"no strategy files given and none found in {STRATEGY_DIR}/")

    goal, config_sha256 = _load_stable(GOAL, load_goal)
    registry = default_registry()
    panel, panel_sha256 = _load_stable(args.panel, load_panel)
    dsn = os.environ.get("ICARUS_PG_DSN")
    if not dsn:
        raise SystemExit("ICARUS_PG_DSN is required for counted portfolio evaluation")
    engine = create_engine(dsn)
    ledger = PostgresTrialLedger(engine)
    log.info(
        "panel loaded",
        symbols=len(panel.symbols),
        sessions=len(panel),
        frm=str(panel.ts[0])[:10],
        to=str(panel.ts[-1])[:10],
        has_benchmark=panel.benchmark is not None,
    )

    results: list[BacktestResult] = []
    for path in files:
        strategy, strategy_sha256 = _load_stable(
            path,
            lambda strategy_path: parse_strategy(
                strategy_path.read_text(encoding="utf-8"),
                registry=registry,
                max_risk_r=goal.risk.per_trade_risk_r,
            ),
        )
        log.info("running", strategy=strategy.name, file=str(path))
        batch = _portfolio_reservation(
            strategy,
            panel,
            strategy_sha256=strategy_sha256,
            panel_sha256=panel_sha256,
            config_sha256=config_sha256,
        )

        def evaluate(current: StrategyCandidate = strategy) -> BacktestResult:
            return run_walk_forward(
                current,
                panel,
                goal=goal,
                registry=registry,
                ledger=None,
            )

        results.append(_execute_counted_portfolio(ledger, batch, evaluate))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps([r.as_json() for r in results], indent=2), encoding="utf-8")
    _print_sheet(results, goal)
    print(f"\nlifetime trials on the ledger: {ledger.lifetime_count()}")
    print(f"full results: {args.out}")
    engine.dispose()
    return 0


def _mean_in_sample(result: BacktestResult) -> float:
    """Mean in-sample Sharpe across folds, or ``nan`` if none was estimable."""
    points = [f.in_sample.sharpe.point for f in result.folds if f.in_sample.sharpe.is_estimable]
    return sum(points) / len(points) if points else float("nan")


def _print_sheet(results: list[BacktestResult], goal: object) -> None:
    """The operator-facing summary. Losses and refusals are as prominent as the returns (§8)."""
    print("\n" + "=" * 100)
    print("WALK-FORWARD OUT-OF-SAMPLE — stitched across folds, net of costs (BEFORE tax)")
    print("=" * 100)
    header = (
        f"{'strategy':<26}{'trades':>8}{'Sharpe':>9}{'95% CI':>18}{'CAGR':>9}"
        f"{'maxDD':>9}{'expR':>8}{'win%':>7}{'meanIS':>8}{'decay':>8}"
    )
    print(header)
    print("-" * 100)
    for r in results:
        m = r.oos
        if m is None:
            print(f"{r.strategy:<26}{'no result':>8}")
            continue
        ci = f"[{m.sharpe.lower:.2f}, {m.sharpe.upper:.2f}]" if m.sharpe.is_estimable else "-"
        print(
            f"{r.strategy:<26}{m.trades:>8}{m.sharpe.point:>9.2f}{ci:>18}"
            f"{m.cagr:>8.1%}{m.max_drawdown:>9.1%}{m.expectancy_r:>8.2f}"
            f"{m.win_rate:>7.1%}{_mean_in_sample(r):>8.2f}{r.sharpe_decay:>8.2f}"
        )
    # The mean in-sample Sharpe sits next to the decay because decay is a RATIO and goes `nan`
    # whenever the in-sample figure is not positive. That case is not missing information — it is
    # the sharpest verdict available: a strategy that loses money on the data it could have been
    # fitted to is not overfitted, it simply has no edge. Printing only `nan` hid that entirely.
    print(
        "\n  meanIS = mean in-sample Sharpe across folds. decay = meanOOS / meanIS; it is `nan`\n"
        "  when meanIS <= 0, which means there was never an in-sample edge to decay from."
    )

    print("\n" + "-" * 100)
    print("AGAINST THE PRE-REGISTERED STOP GATE (goal.yaml, fixed 2026-08-01) — AFTER TAX")
    print("-" * 100)
    # **After tax, from 2026-08-16.** `stop_gate.net_of_cost_and_tax: true` had been asserted by
    # the loader and read by nothing: the gate tested a curve net of costs only while tax was
    # computed afterwards and printed below as an informational line (finding F38). CLAUDE.md §5
    # requires cost and tax inside every backtest; invariant #21 gates on alpha after both.
    # A strategy with no after-tax record prints its NO RESULT row rather than vanishing. The row
    # used to be computed and then dropped by `if not checks: continue`, so on the one table that
    # decides whether a strategy gets money, a strategy that produced nothing looked like a
    # strategy that was never run.
    for r in results:
        verdict, checks = gate_verdict(r, goal)  # type: ignore[arg-type]
        detail = "  ".join(f"{'OK' if ok else 'NO':>2} {label}" for label, ok in checks)
        print(f"{r.strategy:<26} {verdict:<9} {detail or 'no out-of-sample record to judge'}")

    print("\n" + "-" * 100)
    print("TAX ON THE OUT-OF-SAMPLE LEDGER (settled annually, not per trade)")
    print("-" * 100)
    for r in results:
        gross = sum((t.net_pnl for t in r.oos_trades), Decimal(0))
        print(
            f"{r.strategy:<26} after-cost P&L {float(gross):>14,.0f}   "
            f"tax {float(r.tax_total):>12,.0f}   after-tax {float(gross - r.tax_total):>14,.0f}"
        )

    # What the tax actually costs the metrics, rather than only the P&L. The gate reads the second
    # row; the first is kept beside it so the drag is visible instead of absorbed.
    print("\n" + "-" * 100)
    print("WHAT TAX DOES TO THE METRICS (the gate reads the after-tax row)")
    print("-" * 100)
    print(f"{'strategy':<26}{'':>10}{'Sharpe':>9}{'95% CI':>18}{'CAGR':>9}{'maxDD':>9}")
    for r in results:
        for label, m in (("before tax", r.oos), ("AFTER TAX", r.oos_after_tax)):
            if m is None:
                continue
            ci = f"[{m.sharpe.lower:.2f}, {m.sharpe.upper:.2f}]" if m.sharpe.is_estimable else "-"
            name = r.strategy if label == "before tax" else ""
            print(
                f"{name:<26}{label:>10}{m.sharpe.point:>9.2f}{ci:>18}"
                f"{m.cagr:>8.1%}{m.max_drawdown:>9.1%}"
            )

    print("\n" + "-" * 100)
    print("PER-FOLD OUT-OF-SAMPLE SHARPE (a strategy alive in one fold only is not a strategy)")
    print("-" * 100)
    for r in results:
        cells = "  ".join(
            f"{f.test_from[:4]}:{f.out_of_sample.sharpe.point:>6.2f}" for f in r.folds
        )
        print(f"{r.strategy:<26} {cells}")

    # The seam became one strategy-independent constant on 2026-08-17 (finding F40), so every
    # strategy should now be measured over exactly the same window and the control is finally a
    # control. That is a claim, so it is checked here and printed either way rather than assumed:
    # it used to be false — `baseline_buy_and_hold` ran 7 folds from ~2015 against
    # `xs_momentum_20`'s 8 from ~2014 — and the sheet compared them anyway (findings F16, F31).
    spans = {(r.folds[0].test_from, r.folds[-1].test_to, len(r.folds)) for r in results if r.folds}
    # ASCII, deliberately. The operator's console is cp1252, where `U+26A0 WARNING SIGN` raises
    # `UnicodeEncodeError` — and this branch only ever runs when something is wrong, so the
    # decoration would have crashed the sheet precisely when it had something to say, taking every
    # section below it with it. `test_the_metric_sheet_prints_on_the_operators_console` pins it.
    header = (
        "ALL STRATEGIES MEASURED OVER THE SAME WINDOW"
        if len(spans) <= 1
        else "!! THE SPANS DIFFER — the numbers above are NOT like-for-like"
    )
    print("\n" + "-" * 100)
    print(header)
    print("-" * 100)
    for r in results:
        if not r.folds:
            print(f"{r.strategy:<26} no folds")
            continue
        print(
            f"{r.strategy:<26} {len(r.folds)} folds  "
            f"{r.folds[0].test_from}..{r.folds[-1].test_to}   "
            f"seam {r.folds[0].window.seam_sessions} sessions"
        )

    # Every position must end as a trade, but not every ending is a sale. A symbol that stops
    # printing bars is written off at the last price it ever traded at — nobody was there to sell
    # to, so that price is an assumption. Its size belongs on the sheet (finding F4).
    print("\n" + "-" * 100)
    print("CLOSED AT A PRICE NOBODY QUOTED, AND EXITS THAT DID NOT HAPPEN")
    print("-" * 100)
    for r in results:
        marks = sum(f.stale_marks for f in r.folds)
        value = sum((f.stale_mark_value for f in r.folds), Decimal(0))
        unfilled = sum(f.unfilled_exits for f in r.folds)
        capped = sum(f.concentration_capped for f in r.folds)
        marked = "no marked exits" if not marks else f"{marks} marked"
        print(
            f"{r.strategy:<26} {marked:<18} gross {float(value):>13,.0f}   "
            f"{unfilled} exits refused or capped mid-run   "
            f"{capped} entries resized by the position cap"
        )
    # Both numbers or neither. The first version of this section said "none — every exit met a real
    # bar" whenever the mark count was zero, which was a claim it had not checked: an exit the fill
    # model refused leaves capital exposed through a different door, was already being counted, and
    # was never shown anywhere.
    print(
        "\n  marked = closed at the last price the symbol printed, because no trade was possible.\n"
        "  refused/capped = the fill model would not fill the exit; the position stayed open."
    )

    # Signals the book could not act on. These were counted from the beginning and printed nowhere,
    # which is how "94-99.99% of every strategy's signals were discarded for want of a slot" — the
    # single largest fact about the first backtest — stayed invisible until somebody read the JSON.
    # `insufficient_cash` is the one to watch for decision D9: a strategy failing on cash rather
    # than on edge is NEEDS_MORE_CAPITAL, which is a different verdict from a bad strategy.
    print("\n" + "-" * 100)
    print("SIGNALS THE BOOK COULD NOT TAKE (a strategy is only worth the trades it can act on)")
    print("-" * 100)
    for r in results:
        totals: dict[str, int] = {}
        for fold in r.folds:
            for reason, count in fold.skipped.items():
                totals[reason] = totals.get(reason, 0) + count
        # **Entries, not closed trades.** One entry drains into several `ClosedTrade` rows when a
        # partial fill splits it, so counting rows would inflate the numerator by up to the number
        # of chunks — and would do so worst in exactly the thin-liquidity runs this line exists to
        # describe. And `already_held` is dropped from the denominator: a signal on a name we
        # already own is not one the book turned away, it is the same idea firing twice.
        taken = len({(t.symbol, t.entry_ts) for t in r.oos_trades})
        refused = sum(v for k, v in totals.items() if k != Skipped.ALREADY_HELD.value)
        offered = taken + refused
        share = f"{taken / offered:.2%}" if offered else "-"
        detail = "  ".join(f"{k}={v:,}" for k, v in sorted(totals.items())) or "none"
        print(f"{r.strategy:<26} took {taken:>6,} of {offered:>9,} ({share:>7})   {detail}")


if __name__ == "__main__":
    sys.exit(main())
