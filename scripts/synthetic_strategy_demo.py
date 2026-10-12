"""Run unchanged catalogue DSL on invented prices; no performance inference or real data."""

from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from dataclasses import asdict
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np

from icarus.common.config import load_goal
from icarus.engine.backtest import longest_lookback
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel
from icarus.engine.portfolio import PortfolioSimulator, RunResult
from icarus.engine.runner import evaluate_once
from icarus.engine.signalmetrics import SourceSessionAxis, summarize_signal_run
from icarus.engine.signaltest import SignalMissingReason, SignalSimulator
from icarus.strategy.dsl import Bars, Panel, parse_strategy
from icarus.strategy.library import default_registry

PROJECT = Path(__file__).resolve().parents[1]
SCOPE = "SYNTHETIC_MECHANICS_ONLY_NO_STRATEGY_PERFORMANCE_INFERENCE"
CATALOGUE = frozenset(
    {
        "baseline_buy_and_hold",
        "donlevey_sweep_reclaim",
        "uptrend_pullback_3",
        "xs_momentum_20",
        "xs_momentum_252_skip21",
        "donchian_55_20",
        "defensive_low_vol_252_q63",
    }
)


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


CAPITALS = (("seed", Decimal("100000")), ("edge", Decimal("1000000")))
UNAVAILABLE = {
    "benchmark_excess": {"value": None, "reason": "MISSING_EXECUTION_TIME_AND_CERTIFIED_BENCHMARK"},
    "confidence": {"value": None, "reason": "INFERENCE_DISABLED_METHOD_NOT_ADOPTED"},
    "after_tax_promotion_metrics": {"value": None, "reason": "TAX_AND_WALK_FORWARD_NOT_EVALUATED"},
}


def fixture_sha256(panel: Panel) -> str:
    """Bind the actual ordered OHLCV/date columns and point-in-time membership."""
    digest = hashlib.sha256(encoded({"symbols": panel.symbols, "sessions": len(panel)}))
    for symbol, bars in zip(panel.symbols, panel.bars, strict=True):
        for name in ("ts", "open", "high", "low", "close", "volume"):
            values = np.ascontiguousarray(getattr(bars, name))
            digest.update(
                encoded(
                    {
                        "symbol": symbol,
                        "field": name,
                        "dtype": values.dtype.str,
                        "shape": values.shape,
                    }
                )
            )
            digest.update(values.tobytes())
    digest.update(encoded({"membership_shape": panel.tradable.shape}))
    digest.update(np.ascontiguousarray(panel.tradable).tobytes())
    return digest.hexdigest()


def _portfolio_row(run: RunResult, label: str, capital: Decimal) -> dict[str, Any]:
    return {
        "capital_label": label,
        "starting_equity": str(capital),
        "final_equity": str(run.final_equity),
        "closed_trade_gross_pnl": str(sum((trade.gross_pnl for trade in run.trades), Decimal(0))),
        "closed_trade_charges": str(sum((trade.costs for trade in run.trades), Decimal(0))),
        "closed_trade_net_pnl_after_charges_before_tax": str(
            sum((trade.net_pnl for trade in run.trades), Decimal(0))
        ),
        "closed_trade_count": len(run.trades),
        "accepted_entry_count": len(run.accepted_signal_ids),
        "emitted_signals": run.emitted_signals,
        "typed_discard_counts": dict(
            Counter(discard.reason.value for discard in run.portfolio_discards)
        ),
        "stale_marks": run.stale_marks,
        "stale_mark_value": str(run.stale_mark_value),
        "unfilled_exits": run.unfilled_exits,
        "ambiguous_selection_days": run.ambiguous_selection_days,
        "concentration_capped": run.concentration_capped,
        "rebalance_refusals": sum(event.status.value != "valid" for event in run.rebalance_events),
        "admission_refusals": sum(
            event.admission_refusal is not None for event in run.rebalance_events
        ),
        "mechanics_status": "EXERCISED" if run.accepted_signal_ids else "NOT_EXERCISED",
    }


def run_demo(case: str) -> Path:
    if not case or any(c not in "abcdefghijklmnopqrstuvwxyz0123456789-" for c in case):
        raise ValueError("case must be a lowercase identifier")
    goal_path = PROJECT / "goal.yaml"
    goal_bytes = goal_path.read_bytes()
    goal = load_goal(goal_path)
    if goal_path.read_bytes() != goal_bytes:
        raise ValueError("goal bytes changed while being loaded")
    if goal.signal_test.inference_enabled:
        raise ValueError("synthetic demo requires inference disabled")
    paths = sorted((PROJECT / "strategies").glob("*.yaml"))
    if {path.stem for path in paths} != CATALOGUE:
        raise ValueError("synthetic demo requires the exact seven-card catalogue")
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
    provenance = {
        "scope": SCOPE,
        "receipt_kind": "ISOLATED_SYNTHETIC_ATTEMPT_NOT_ACTUAL_POSTGRES_LEDGER",
        "actual_ledger_used": False,
        "real_market_data": False,
        "real_data_readiness": False,
        "inference_enabled": False,
        "goal_sha256": hashlib.sha256(goal_bytes).hexdigest(),
        "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture": "invented-24-symbols-600-sessions-v1",
        "fixture_sha256": fixture_sha256(panel),
        "evaluated_fixture_sha256": fixture_sha256(cropped),
        "study_origin_index": origin,
        "source_indices": list(indices),
        **UNAVAILABLE,
    }
    rows = []
    cards = []
    for path in paths:
        card_bytes = path.read_bytes()
        strategy = parse_strategy(
            card_bytes.decode("utf-8"), registry=registry, max_risk_r=goal.risk.per_trade_risk_r
        )
        if path.read_bytes() != card_bytes:
            raise ValueError("strategy bytes changed while being loaded")
        cards.append((path, strategy, hashlib.sha256(card_bytes).hexdigest()))
    for path, strategy, card_hash in cards:
        write_once(
            root / f"{path.stem}-trial.json",
            {
                **provenance,
                "strategy": strategy.name,
                "strategy_sha256": card_hash,
                "evaluations": 3,
                "evaluation_identities": [
                    {
                        "evaluation_id": f"{case}/{path.stem}/signal",
                        "kind": "signal",
                        "notional_inr": str(goal.signal_test.notional_inr),
                    },
                    *[
                        {
                            "evaluation_id": f"{case}/{path.stem}/{label}",
                            "kind": "portfolio",
                            "capital_label": label,
                            "starting_equity": str(capital),
                        }
                        for label, capital in CAPITALS
                    ],
                ],
                "promotion": False,
            },
        )
    for path, strategy, card_hash in cards:
        columns = evaluate_once(strategy, panel, registry)
        signals, stops, ranks, exit_signals, pulses = columns.slice(origin, len(panel))
        missing = {
            s: {
                indices[i]: (
                    SignalMissingReason.WARMUP
                    if indices[i] < longest_lookback(strategy)
                    else SignalMissingReason.MISSING_INPUT
                )
                for i in np.flatnonzero(np.isnan(column)).tolist()
            }
            for s, column in signals.items()
        }
        signal_run = SignalSimulator(
            notional_inr=Decimal(str(goal.signal_test.notional_inr)),
            costs=CostModel(goal.costs),
            fills=FillModel(goal.execution_realism),
            stale_after_sessions=goal.backtest.stale_position_sessions,
        ).run(
            strategy,
            cropped,
            signals,
            stops,
            source_indices=indices,
            exit_signals=exit_signals,
            ranks=ranks,
            rebalance_pulses=pulses,
            missing_reasons=missing,
        )
        diagnostics = summarize_signal_run(
            signal_run,
            source_axis=axis,
            settings=goal.signal_test,
        )
        portfolio_runs = {}
        portfolio_rows = {}
        for label, capital in CAPITALS:
            book = PortfolioSimulator(
                risk=goal.risk,
                costs=CostModel(goal.costs),
                fills=FillModel(goal.execution_realism),
                stale_after_sessions=goal.backtest.stale_position_sessions,
            ).run(
                strategy,
                cropped,
                signals,
                stops,
                ranks=ranks,
                exit_signals=exit_signals,
                rebalance_pulses=pulses,
                starting_equity=capital,
                source_indices=indices,
            )
            for trade in book.trades:
                assert trade.net_pnl == trade.gross_pnl - trade.costs
            portfolio_runs[label] = {
                "capital_label": label,
                "starting_equity": str(capital),
                **asdict(book),
            }
            portfolio_rows[label] = _portfolio_row(book, label, capital)
        assert signal_run.emitted_signals == len(signal_run.trades) + len(signal_run.skips)
        assert all(
            trade.entry_index > trade.signal_id.decision_index for trade in signal_run.trades
        )
        empty_reason = None
        if not signal_run.trades and not any(
            book["accepted_entry_count"] for book in portfolio_rows.values()
        ):
            empty_reason = (
                "THIN_COHORT_24_BELOW_31"
                if strategy.name == "defensive_low_vol_252_q63"
                else "NO_TRADES_IN_FIXED_FIXTURE"
            )
        row = {
            "strategy": strategy.name,
            "strategy_sha256": card_hash,
            "scope": SCOPE,
            "signals": signal_run.emitted_signals,
            "signal_trades": len(signal_run.trades),
            "signal_skips": len(signal_run.skips),
            "portfolio_rows": portfolio_rows,
            "mechanics_status": "NOT_EXERCISED" if empty_reason else "EXERCISED",
            "not_exercised_reason": empty_reason,
            **UNAVAILABLE,
        }
        write_once(
            root / f"{path.stem}-results.json",
            {
                **provenance,
                "summary": row,
                "signal_run": asdict(signal_run),
                "diagnostics": asdict(diagnostics),
                "portfolio_runs": portfolio_runs,
            },
        )
        write_once(root / f"{path.stem}-trial-complete.json", row)
        rows.append(row)
    write_once(
        root / "summary.json",
        {
            **provenance,
            "declared_evaluations": 3 * len(cards),
            "completed_evaluations": 3 * len(rows),
            "strategies": rows,
            "qualification": "mechanics demonstration only; no confidence or edge ranking",
        },
    )
    return root


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True)
    print(run_demo(parser.parse_args().case))
