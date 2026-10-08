"""Synthetic catalogue integration: real DSL, accounting, timing and trial barriers."""

import json
import shutil
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scripts import synthetic_strategy_demo as demo

from icarus.strategy.dsl import Bars, Panel, evaluate_universe, parse_strategy
from icarus.strategy.library import default_registry


def test_catalogue_signals_do_not_change_when_future_bars_are_removed() -> None:
    panel = demo.invented_panel()
    registry = default_registry()
    prefix = 420
    truncated = Panel.build(
        {
            s: Bars(
                **{
                    k: getattr(b, k)[:prefix].copy()
                    for k in ("ts", "open", "high", "low", "close", "volume")
                }
            )
            for s, b in zip(panel.symbols, panel.bars, strict=True)
        },
        {s: np.ones(prefix, dtype=np.bool_) for s in panel.symbols},
    )
    for path in sorted((demo.PROJECT / "strategies").glob("*.yaml")):
        strategy = parse_strategy(path.read_text(), registry=registry, max_risk_r=0.005)
        full = evaluate_universe(strategy.entry, panel, registry)
        short = evaluate_universe(strategy.entry, truncated, registry)
        for symbol in panel.symbols:
            np.testing.assert_array_equal(full[symbol][:prefix], short[symbol])


def test_catalogue_demo_records_real_dsl_trades_and_refuses_reuse(
    tmp_path: Path, monkeypatch: Any
) -> None:
    shutil.copy(demo.PROJECT / "goal.yaml", tmp_path / "goal.yaml")
    shutil.copytree(demo.PROJECT / "strategies", tmp_path / "strategies")
    monkeypatch.setattr(demo, "PROJECT", tmp_path)
    root = demo.run_demo("test")
    summary = json.loads((root / "summary.json").read_bytes())
    assert summary["inference_enabled"] is False and summary["real_market_data"] is False
    rows = {row["strategy"]: row for row in summary["strategies"]}
    expected = {
        "baseline_buy_and_hold",
        "donlevey_sweep_reclaim",
        "short_term_reversal_uptrend",
        "xs_momentum_20",
        "xs_momentum_252_21",
    }
    assert set(rows) == expected
    for name in expected - {"short_term_reversal_uptrend"}:
        assert rows[name]["portfolio_trades"] > 0
    # The fixed catalogue fixture has symmetric highs/lows, so IBS is about 0.5 and the strict
    # pullback card correctly emits nothing.  Its positive path has a dedicated boundary fixture.
    assert rows["short_term_reversal_uptrend"]["signals"] == 0
    assert rows["short_term_reversal_uptrend"]["portfolio_trades"] == 0
    details = {
        payload["summary"]["strategy"]: payload
        for path in root.glob("*-results.json")
        if (payload := json.loads(path.read_bytes()))
    }
    assert set(details) == expected
    for row in summary["strategies"]:
        assert row["signals"] == row["signal_trades"] + row["signal_skips"]
        assert row["benchmark_alpha"] is None and row["after_tax_promotion_metrics"] is None
        detail = details[row["strategy"]]
        for trade in detail["signal_run"]["trades"]:
            assert trade["entry_index"] > trade["signal_id"]["decision_index"]
    assert len(list(root.glob("*-trial.json"))) == 5
    assert len(list(root.glob("*-trial-complete.json"))) == 5
    with pytest.raises(FileExistsError):
        demo.run_demo("test")
