"""Run unchanged catalogue DSL on invented prices; no performance inference or real data."""

from __future__ import annotations

import argparse
import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from icarus.common.config import load_goal
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel
from icarus.engine.portfolio import PortfolioSimulator
from icarus.engine.signalmetrics import SourceSessionAxis, summarize_signal_run
from icarus.engine.signaltest import SignalSimulator
from icarus.strategy.dsl import Bars, Panel, evaluate_universe, parse_strategy
from icarus.strategy.library import default_registry

PROJECT = Path(__file__).resolve().parents[1]
SCOPE = "SYNTHETIC_MECHANICS_ONLY_NO_STRATEGY_PERFORMANCE_INFERENCE"


def invented_panel() -> Panel:
    """Fixed 24-symbol/600-session fixture; no downloaded data or random draws."""
    t = np.arange(600, dtype=np.float64)
    ts = np.arange(np.datetime64("2020-01-01"), np.datetime64("2020-01-01") + 600)
    data: dict[str, Bars] = {}
    for j in range(24):
        close = 100 + j * 3 + (0.08 + j * 0.003) * t + 3 * np.sin(t / 9 + j)
        low = close - 1.5
        low[(t.astype(int) + j) % 17 == 0] -= 7
        data[f"SYN{j:02d}"] = Bars(
            ts=ts,
            open=close - 0.2,
            high=close + 1.5,
            low=low,
            close=close,
            volume=np.full(600, 1_000_000.0),
        )
    return Panel.build(data, {s: np.ones(600, dtype=np.bool_) for s in data})


def encoded(value: Any) -> bytes:
    return json.dumps(value, default=str, sort_keys=True, indent=2, allow_nan=False).encode()


def write_once(path: Path, value: Any) -> None:
    with path.open("xb") as stream:
        stream.write(encoded(value))


def run_demo(case: str) -> Path:
    if not case or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in case):
        raise ValueError("case must be a lowercase identifier")
    goal = load_goal(PROJECT / "goal.yaml")
    if goal.signal_test.inference_enabled:
        raise ValueError("synthetic demo requires inference disabled")
    root = PROJECT / "var" / "synthetic-strategy-demo" / case
    root.mkdir(parents=True, exist_ok=False)
    panel = invented_panel()
    registry = default_registry()
    origin = 260
    bars = {
        s: Bars(
            **{
                name: getattr(b, name)[origin:].copy()
                for name in ("ts", "open", "high", "low", "close", "volume")
            }
        )
        for s, b in zip(panel.symbols, panel.bars, strict=True)
    }
    cropped = Panel.build(bars, {s: np.ones(len(b), dtype=np.bool_) for s, b in bars.items()})
    indices = tuple(range(origin, len(panel)))
    axis = SourceSessionAxis(
        tuple((i, datetime.fromisoformat(str(panel.ts[i])).replace(tzinfo=UTC)) for i in indices),
        origin,
    )
    costs = CostModel(goal.costs)
    fills = FillModel(goal.execution_realism)
    rows = []
    for path in sorted((PROJECT / "strategies").glob("*.yaml")):
        write_once(
            root / f"{path.stem}-trial.json",
            {
                "scope": SCOPE,
                "origin": "operator",
                "strategy_sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                "goal_sha256": hashlib.sha256((PROJECT / "goal.yaml").read_bytes()).hexdigest(),
                "fixture": "invented-24-symbols-600-sessions-v1",
                "evaluations": 2,
                "evaluators": ["SignalSimulator", "PortfolioSimulator"],
                "confidence": None,
                "promotion": False,
            },
        )
        strategy = parse_strategy(
            path.read_text(), registry=registry, max_risk_r=goal.risk.per_trade_risk_r
        )
        signals = evaluate_universe(strategy.entry, panel, registry)
        ranks = evaluate_universe(strategy.rank_by, panel, registry) if strategy.rank_by else None
        rule = next(x for x in strategy.exits if x.rule in ("stop_loss_atr", "stop_loss_pct"))
        stops = {}
        for s, b in zip(panel.symbols, panel.bars, strict=True):
            if rule.rule == "stop_loss_pct":
                stops[s] = b.close * float(rule.literals["pct"])
            else:
                stops[s] = registry.get("atr").compute(b, n=rule.literals["atr_period"]) * float(
                    rule.literals["atr_mult"]
                )
        signals = {s: v[origin:].copy() for s, v in signals.items()}
        stops = {s: v[origin:].copy() for s, v in stops.items()}
        ranks = {s: v[origin:].copy() for s, v in ranks.items()} if ranks else None
        signal_run = SignalSimulator(
            notional_inr=Decimal(str(goal.signal_test.notional_inr)),
            costs=costs,
            fills=fills,
            stale_after_sessions=goal.backtest.stale_position_sessions,
        ).run(strategy, cropped, signals, stops, source_indices=indices)
        diagnostics = summarize_signal_run(
            signal_run,
            source_axis=axis,
            settings=goal.signal_test,
        )
        portfolio_run = PortfolioSimulator(
            risk=goal.risk,
            costs=costs,
            fills=fills,
            stale_after_sessions=goal.backtest.stale_position_sessions,
        ).run(
            strategy,
            cropped,
            signals,
            stops,
            ranks=ranks,
            starting_equity=Decimal(str(goal.backtest.starting_equity_inr)),
            source_indices=indices,
        )
        assert signal_run.emitted_signals == len(signal_run.trades) + len(signal_run.skips)
        assert all(t.entry_index > t.signal_id.decision_index for t in signal_run.trades)
        for trade in portfolio_run.trades:
            assert trade.net_pnl == trade.gross_pnl - trade.costs
        row = {
            "strategy": strategy.name,
            "scope": SCOPE,
            "signals": signal_run.emitted_signals,
            "signal_trades": len(signal_run.trades),
            "signal_skips": len(signal_run.skips),
            "portfolio_trades": len(portfolio_run.trades),
            "portfolio_net_pnl_after_charges_before_tax": str(
                sum((t.net_pnl for t in portfolio_run.trades), Decimal(0))
            ),
            "benchmark_alpha": None,
            "after_tax_promotion_metrics": None,
        }
        write_once(
            root / f"{path.stem}-results.json",
            {
                "summary": row,
                "signal_run": asdict(signal_run),
                "diagnostics": asdict(diagnostics),
                "portfolio_run": asdict(portfolio_run),
            },
        )
        write_once(root / f"{path.stem}-trial-complete.json", row)
        rows.append(row)
    write_once(
        root / "summary.json",
        {
            "scope": SCOPE,
            "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "real_market_data": False,
            "inference_enabled": False,
            "strategies": rows,
            "qualification": "mechanics demonstration only; no confidence or edge ranking",
        },
    )
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    print(run_demo(parser.parse_args().case))
