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
from icarus.engine.runner import DEFAULT_TRIAL_LEDGER, BacktestResult, read_trials, run_walk_forward
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


def _print_sheet(results: list[BacktestResult], goal: object) -> None:
    """The operator-facing summary. Losses and refusals are as prominent as the returns (§8)."""
    bound = goal.stop_gate.require_sharpe_lower_bound_above  # type: ignore[attr-defined]
    promote = goal.stop_gate.trade_count_promote  # type: ignore[attr-defined]

    print("\n" + "=" * 100)
    print("WALK-FORWARD OUT-OF-SAMPLE — stitched across folds, net of costs")
    print("=" * 100)
    header = (
        f"{'strategy':<26}{'trades':>8}{'Sharpe':>9}{'95% CI':>18}{'CAGR':>9}"
        f"{'maxDD':>9}{'expR':>8}{'win%':>7}{'decay':>8}"
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
            f"{m.win_rate:>7.1%}{r.sharpe_decay:>8.2f}"
        )

    print("\n" + "-" * 100)
    print("AGAINST THE PRE-REGISTERED STOP GATE (goal.yaml, fixed 2026-08-01)")
    print("-" * 100)
    for r in results:
        m = r.oos
        if m is None:
            continue
        checks = [
            (f"Sharpe lower bound > {bound}", m.sharpe.is_estimable and m.sharpe.lower > bound),
            (f"trades >= {promote}", m.trades >= promote),
            ("expectancy > 0R", m.expectancy_r > 0),
        ]
        verdict = "PASS" if all(ok for _, ok in checks) else "FAIL"
        detail = "  ".join(f"{'OK' if ok else 'NO':>2} {label}" for label, ok in checks)
        print(f"{r.strategy:<26} {verdict:<5} {detail}")

    print("\n" + "-" * 100)
    print("TAX ON THE OUT-OF-SAMPLE LEDGER (settled annually, not per trade)")
    print("-" * 100)
    for r in results:
        gross = sum((t.net_pnl for t in r.oos_trades), Decimal(0))
        print(
            f"{r.strategy:<26} after-cost P&L {float(gross):>14,.0f}   "
            f"tax {float(r.tax_total):>12,.0f}   after-tax {float(gross - r.tax_total):>14,.0f}"
        )

    print("\n" + "-" * 100)
    print("PER-FOLD OUT-OF-SAMPLE SHARPE (a strategy alive in one fold only is not a strategy)")
    print("-" * 100)
    for r in results:
        cells = "  ".join(
            f"{f.test_from[:4]}:{f.out_of_sample.sharpe.point:>6.2f}" for f in r.folds
        )
        print(f"{r.strategy:<26} {cells}")


if __name__ == "__main__":
    sys.exit(main())
