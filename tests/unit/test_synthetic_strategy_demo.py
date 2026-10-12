"""Synthetic catalogue integration: real DSL, accounting, timing and trial barriers."""

import json
import shutil
from dataclasses import asdict
from decimal import Decimal
from pathlib import Path
from typing import Any

import numpy as np
import pytest
from scripts import synthetic_strategy_demo as demo

from icarus.common.config import load_goal
from icarus.engine.backtest import slice_panel
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel
from icarus.engine.portfolio import PortfolioSimulator, RunResult
from icarus.engine.runner import evaluate_once
from icarus.engine.signaltest import SignalRunResult, SignalSimulator
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
        "donchian_55_20",
        "defensive_low_vol_252_q63",
    }
    assert set(rows) == expected
    for name in expected - {
        "short_term_reversal_uptrend",
        "defensive_low_vol_252_q63",
        "donchian_55_20",
    }:
        assert set(rows[name]["portfolio_rows"]) == {"seed", "edge"}
        assert all(book["closed_trade_count"] > 0 for book in rows[name]["portfolio_rows"].values())
    # The fixed catalogue fixture has symmetric highs/lows, so IBS is about 0.5 and the strict
    # pullback card correctly emits nothing.  Its positive path has a dedicated boundary fixture.
    assert rows["donchian_55_20"]["signals"] == 0
    assert all(
        book["closed_trade_count"] == 0
        for book in rows["donchian_55_20"]["portfolio_rows"].values()
    )
    assert rows["short_term_reversal_uptrend"]["signals"] == 0
    assert all(
        book["closed_trade_count"] == 0
        for book in rows["short_term_reversal_uptrend"]["portfolio_rows"].values()
    )
    assert rows["defensive_low_vol_252_q63"]["signals"] == 0
    assert all(
        book["closed_trade_count"] == 0
        for book in rows["defensive_low_vol_252_q63"]["portfolio_rows"].values()
    )
    assert all(
        book["rebalance_refusals"] > 0
        for book in rows["defensive_low_vol_252_q63"]["portfolio_rows"].values()
    )
    details = {
        payload["summary"]["strategy"]: payload
        for path in root.glob("*-results.json")
        if (payload := json.loads(path.read_bytes()))
    }
    assert set(details) == expected
    for row in summary["strategies"]:
        assert row["signals"] == row["signal_trades"] + row["signal_skips"]
        assert row["benchmark_excess"]["reason"] == "MISSING_EXECUTION_TIME_AND_CERTIFIED_BENCHMARK"
        assert row["confidence"]["reason"] == "INFERENCE_DISABLED_METHOD_NOT_ADOPTED"
        assert row["after_tax_promotion_metrics"]["reason"] == "TAX_AND_WALK_FORWARD_NOT_EVALUATED"
        detail = details[row["strategy"]]
        for record in (summary, row, detail):
            assert all(
                record[key]["value"] is None
                for key in ("benchmark_excess", "confidence", "after_tax_promotion_metrics")
            )
        assert detail["actual_ledger_used"] is False and detail["real_data_readiness"] is False
        for trade in detail["signal_run"]["trades"]:
            assert trade["entry_index"] > trade["signal_id"]["decision_index"]
            assert Decimal(trade["intended_notional"]) == Decimal("100000")
        if row["signals"] == 0:
            assert row["mechanics_status"] == "NOT_EXERCISED"
    assert rows["defensive_low_vol_252_q63"]["not_exercised_reason"] == "THIN_COHORT_24_BELOW_31"
    assert len(list(root.glob("*-trial.json"))) == 7
    assert len(list(root.glob("*-trial-complete.json"))) == 7
    assert summary["completed_evaluations"] == summary["declared_evaluations"] == 21
    assert summary["actual_ledger_used"] is False and summary["real_data_readiness"] is False
    with pytest.raises(FileExistsError):
        demo.run_demo("test")


def _prepare(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    shutil.copy(demo.PROJECT / "goal.yaml", tmp_path / "goal.yaml")
    shutil.copytree(demo.PROJECT / "strategies", tmp_path / "strategies")
    monkeypatch.setattr(demo, "PROJECT", tmp_path)


def test_all_twenty_one_public_evaluations_have_prior_distinct_declarations(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, monkeypatch)
    root = tmp_path / "var" / "synthetic-strategy-demo" / "declared"
    calls: list[tuple[str, str, Decimal | None]] = []
    original_signal = SignalSimulator.run
    original_portfolio = PortfolioSimulator.run

    def check(strategy: Any) -> None:
        records = [json.loads(path.read_bytes()) for path in root.glob("*-trial.json")]
        assert len(records) == 7
        identities = [
            item["evaluation_id"] for record in records for item in record["evaluation_identities"]
        ]
        assert len(identities) == len(set(identities)) == 21
        record = next(item for item in records if item["strategy"] == strategy.name)
        assert record["evaluations"] == 3
        assert record["actual_ledger_used"] is False
        assert record["receipt_kind"] == "ISOLATED_SYNTHETIC_ATTEMPT_NOT_ACTUAL_POSTGRES_LEDGER"
        assert record["source_indices"] == list(range(260, 600))

    def signal(self: SignalSimulator, *args: Any, **kwargs: Any) -> SignalRunResult:
        check(args[0])
        calls.append((args[0].name, "signal", None))
        return original_signal(self, *args, **kwargs)

    def portfolio(self: PortfolioSimulator, *args: Any, **kwargs: Any) -> RunResult:
        check(args[0])
        calls.append((args[0].name, "portfolio", kwargs["starting_equity"]))
        return original_portfolio(self, *args, **kwargs)

    monkeypatch.setattr(SignalSimulator, "run", signal)
    monkeypatch.setattr(PortfolioSimulator, "run", portfolio)
    demo.run_demo("declared")
    assert len(calls) == 21
    for name in {item[0] for item in calls}:
        assert [(mode, capital) for strategy, mode, capital in calls if strategy == name] == [
            ("signal", None),
            ("portfolio", Decimal("100000")),
            ("portfolio", Decimal("1000000")),
        ]


def test_paired_books_match_independent_public_replays_and_real_whole_shares(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, monkeypatch)
    root = demo.run_demo("independent")
    detail = json.loads((root / "baseline_buy_and_hold-results.json").read_bytes())
    goal = load_goal(tmp_path / "goal.yaml")
    registry = default_registry()
    strategy = parse_strategy(
        (tmp_path / "strategies/baseline_buy_and_hold.yaml").read_text(),
        registry=registry,
        max_risk_r=goal.risk.per_trade_risk_r,
    )
    full = demo.invented_panel()
    panel = slice_panel(full, 260, 600)
    signals, stops, ranks, exits, pulses = evaluate_once(strategy, full, registry).slice(260, 600)
    for label, capital in (("seed", Decimal("100000")), ("edge", Decimal("1000000"))):
        direct = PortfolioSimulator(
            risk=goal.risk,
            costs=CostModel(goal.costs),
            fills=FillModel(goal.execution_realism),
            stale_after_sessions=goal.backtest.stale_position_sessions,
        ).run(
            strategy,
            panel,
            signals,
            stops,
            ranks=ranks,
            exit_signals=exits,
            rebalance_pulses=pulses,
            source_indices=range(260, 600),
            starting_equity=capital,
        )
        expected = {"capital_label": label, "starting_equity": str(capital), **asdict(direct)}
        assert detail["portfolio_runs"][label] == json.loads(demo.encoded(expected))
        row = detail["summary"]["portfolio_rows"][label]
        assert row["starting_equity"] == str(capital)
        assert Decimal(row["final_equity"]) == direct.final_equity
        assert Decimal(row["closed_trade_net_pnl_after_charges_before_tax"]) == sum(
            (trade.net_pnl for trade in direct.trades), Decimal(0)
        )
        assert Decimal(row["closed_trade_gross_pnl"]) - Decimal(
            row["closed_trade_net_pnl_after_charges_before_tax"]
        ) == Decimal(row["closed_trade_charges"])
    seed = detail["portfolio_runs"]["seed"]["trades"]
    edge = detail["portfolio_runs"]["edge"]["trades"]
    assert len(seed) == len(edge) > 0
    assert all(high["quantity"] > low["quantity"] for low, high in zip(seed, edge, strict=True))
    assert any(
        high["quantity"] != 10 * low["quantity"] for low, high in zip(seed, edge, strict=True)
    )
    assert detail["fixture_sha256"] == demo.fixture_sha256(full)
    assert detail["evaluated_fixture_sha256"] == demo.fixture_sha256(panel)


def test_fixture_hash_covers_prices_and_point_in_time_membership() -> None:
    panel = demo.invented_panel()
    baseline = demo.fixture_sha256(panel)
    panel.bars[0].close[0] += 0.01
    assert demo.fixture_sha256(panel) != baseline
    panel = demo.invented_panel()
    panel.tradable[0, 0] = False
    assert demo.fixture_sha256(panel) != baseline


@pytest.mark.parametrize("invalid", ["inference", "catalogue", "goal_drift", "card_drift"])
def test_invalid_inputs_refuse_before_any_evaluation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, invalid: str
) -> None:
    _prepare(tmp_path, monkeypatch)
    calls = []

    def forbidden(*args: Any, **kwargs: Any) -> Any:
        calls.append("evaluated")
        raise AssertionError("invalid input reached a simulator")

    monkeypatch.setattr(SignalSimulator, "run", forbidden)
    monkeypatch.setattr(PortfolioSimulator, "run", forbidden)
    if invalid == "catalogue":
        (tmp_path / "strategies/donchian_55_20.yaml").unlink()
    elif invalid == "inference":
        original_load = load_goal

        def enabled(path: Path) -> Any:
            goal = original_load(path)
            return goal.model_copy(
                update={
                    "signal_test": goal.signal_test.model_copy(update={"inference_enabled": True})
                }
            )

        monkeypatch.setattr(demo, "load_goal", enabled)
    elif invalid == "goal_drift":
        original_load = load_goal

        def drift(path: Path) -> Any:
            goal = original_load(path)
            path.write_bytes(path.read_bytes() + b"\n# changed during load\n")
            return goal

        monkeypatch.setattr(demo, "load_goal", drift)
    else:
        original_parse = parse_strategy

        def drift_card(*args: Any, **kwargs: Any) -> Any:
            strategy = original_parse(*args, **kwargs)
            path = tmp_path / "strategies/baseline_buy_and_hold.yaml"
            path.write_bytes(path.read_bytes() + b"\n# changed during parse\n")
            return strategy

        monkeypatch.setattr(demo, "parse_strategy", drift_card)
    with pytest.raises(ValueError):
        demo.run_demo("invalid")
    assert calls == []
    assert not (tmp_path / "var/synthetic-strategy-demo/invalid/summary.json").exists()


def test_failed_evaluation_never_publishes_completion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _prepare(tmp_path, monkeypatch)

    def fail(*args: Any, **kwargs: Any) -> RunResult:
        raise RuntimeError("invented evaluation failure")

    monkeypatch.setattr(PortfolioSimulator, "run", fail)
    with pytest.raises(RuntimeError, match="invented evaluation failure"):
        demo.run_demo("failed")
    root = tmp_path / "var/synthetic-strategy-demo/failed"
    assert len(list(root.glob("*-trial.json"))) == 7
    assert not list(root.glob("*-trial-complete.json")) and not (root / "summary.json").exists()
