"""Run pre-registered strategies over the walk-forward span and print the metric sheet (1.7d).

    uv run python scripts/run_backtest.py [strategies/*.yaml ...]

With no arguments it runs every file in ``strategies/``. The panel comes from ``var/panel.npz``,
built by ``scripts/build_panel.py``; this script touches no network and reads no session outside
the development span, because the panel it loads does not contain one.

**Every run recorded here is a trial.** The ledger at ``var/trial_ledger.json`` counts it whether
a human or the Inventor started it (invariant #24), and it is printed at the end so the number is
never out of sight. The overfitting correction in 1.9 reads that count; a run that quietly did not
appear in it would make every DSR figure afterwards too generous.
"""

from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal
from pathlib import Path

from icarus.common.config import load_goal
from icarus.common.logging import get_logger
from icarus.engine.panelbuild import load_panel
from icarus.engine.portfolio import Skipped
from icarus.engine.runner import (
    DEFAULT_TRIAL_LEDGER,
    BacktestResult,
    gate_verdict,
    read_trials,
    run_walk_forward,
)
from icarus.strategy.dsl import parse_strategy
from icarus.strategy.library import default_registry

log = get_logger("scripts.run_backtest")

PANEL = Path("var/panel.npz")
STRATEGY_DIR = Path("strategies")
RESULTS = Path("var/backtest_results.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", type=Path)
    parser.add_argument("--panel", type=Path, default=PANEL)
    parser.add_argument("--out", type=Path, default=RESULTS)
    args = parser.parse_args()

    files = args.files or sorted(STRATEGY_DIR.glob("*.yaml"))
    if not files:
        raise SystemExit(f"no strategy files given and none found in {STRATEGY_DIR}/")

    goal = load_goal()
    registry = default_registry()
    panel = load_panel(args.panel)
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
        strategy = parse_strategy(
            path.read_text(encoding="utf-8"),
            registry=registry,
            max_risk_r=goal.risk.per_trade_risk_r,
        )
        log.info("running", strategy=strategy.name, file=str(path))
        results.append(run_walk_forward(strategy, panel, goal=goal, registry=registry))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps([r.as_json() for r in results], indent=2), encoding="utf-8")
    _print_sheet(results, goal)
    print(f"\nlifetime trials on the ledger: {len(read_trials(DEFAULT_TRIAL_LEDGER))}")
    print(f"full results: {args.out}")
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

    # The purge is derived per strategy, so a wider lookback costs folds and moves the start date.
    # Two strategies on this sheet can therefore be measured over different periods, and the table
    # above puts their numbers side by side as though they were not. Printing the spans is the
    # stop-gap until step 3c makes the comparison a common-window one (finding F31).
    print("\n" + "-" * 100)
    print("THE SPANS ARE NOT THE SAME — compare the numbers above with that in mind")
    print("-" * 100)
    for r in results:
        if not r.folds:
            continue
        purge = r.folds[0].window.purge_sessions
        print(
            f"{r.strategy:<26} {len(r.folds)} folds  "
            f"{r.folds[0].test_from}..{r.folds[-1].test_to}   purge {purge} sessions"
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
        marked = "no marked exits" if not marks else f"{marks} marked"
        print(
            f"{r.strategy:<26} {marked:<18} gross {float(value):>13,.0f}   "
            f"{unfilled} exits refused or capped mid-run"
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
