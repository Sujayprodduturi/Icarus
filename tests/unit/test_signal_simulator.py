from __future__ import annotations

import ast
from collections.abc import Mapping, Sequence
from dataclasses import fields
from decimal import Decimal
from pathlib import Path
from typing import cast

import numpy as np
import numpy.typing as npt
import pytest
from tests.unit.simharness import REALISM
from tests.unit.test_portfolio_characterization import (
    _COSTS,
    _RISK,
    _STRATEGY,
    _bars,
    _panel,
)

from icarus.engine.costmodel import Charges, CostModel
from icarus.engine.fills import FillModel
from icarus.engine.signaltest import (
    SignalMissingReason,
    SignalRunResult,
    SignalSimulator,
    SignalSkipReason,
)
from icarus.engine.simcore import ExitReason
from icarus.strategy.dsl import Bars, Panel, StrategyCandidate, parse_strategy
from icarus.strategy.library import default_registry


def _case(
    *, fills: FillModel | None = None, stale_after: int = 20
) -> tuple[
    StrategyCandidate,
    Panel,
    dict[str, npt.NDArray[np.float64]],
    dict[str, npt.NDArray[np.float64]],
    SignalSimulator,
]:
    panel = _panel()
    strategy = parse_strategy(
        _STRATEGY, registry=default_registry(), max_risk_r=_RISK.per_trade_risk_r
    )
    signals = {symbol: np.zeros(len(panel), dtype=np.float64) for symbol in panel.symbols}
    stops = {symbol: np.full(len(panel), 10.0) for symbol in panel.symbols}
    simulator = SignalSimulator(
        notional_inr=Decimal("100000"),
        costs=CostModel(_COSTS),
        fills=fills or FillModel(REALISM),
        stale_after_sessions=stale_after,
    )
    return strategy, panel, signals, stops, simulator


def _strategy_with(*exit_rules: str) -> StrategyCandidate:
    exits = "\n".join(f"  - {rule}" for rule in exit_rules)
    text = f"""
name: signal_exit_case
version: 1
timeframe: 1d
universe: synthetic
entry: {{structure_bullish: {{k: 2}}}}
exit:
{exits}
sizing:
  risk_r: 0.005
"""
    return parse_strategy(text, registry=default_registry(), max_risk_r=_RISK.per_trade_risk_r)


class _ExplodingFills:
    def marketable_price(self, *args: object, **kwargs: object) -> Decimal:
        raise AssertionError("preflight must finish before pricing")

    def execute(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("preflight must finish before filling")


@pytest.mark.parametrize("value", [np.inf, -np.inf, 0.5, -1.0, 2.0])
def test_signal_values_must_be_binary_or_labelled_nan(value: float) -> None:
    strategy, panel, signals, stops, simulator = _case(fills=cast(FillModel, _ExplodingFills()))
    signals["AAA"][1] = value

    with pytest.raises(ValueError, match="signal value"):
        simulator.run(strategy, panel, signals, stops, source_indices=range(6))


def test_unlabelled_nan_fails_even_on_untradable_last_bar() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["AAA"][-1] = np.nan
    panel.tradable[panel.index_of("AAA"), -1] = False

    with pytest.raises(ValueError, match="unlabelled NaN"):
        simulator.run(strategy, panel, signals, stops, source_indices=range(40, 46))


@pytest.mark.parametrize("reason", list(SignalMissingReason))
def test_labelled_nan_becomes_canonical_missing_diagnostic(
    reason: SignalMissingReason,
) -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["AAA"][1] = np.nan

    result = simulator.run(
        strategy,
        panel,
        signals,
        stops,
        source_indices=range(40, 46),
        missing_reasons={"AAA": {41: reason}},
    )

    assert len(result.missing) == 1
    assert result.missing[0].symbol == "AAA"
    assert result.missing[0].decision_index == 41
    assert result.missing[0].decision_ts.isoformat() == "2024-01-02T00:00:00+00:00"
    assert result.missing[0].reason is reason
    assert result.emitted_signals == 0


def test_reason_on_finite_signal_is_refused() -> None:
    strategy, panel, signals, stops, simulator = _case()

    with pytest.raises(ValueError, match="finite signal"):
        simulator.run(
            strategy,
            panel,
            signals,
            stops,
            source_indices=range(6),
            missing_reasons={"AAA": {1: SignalMissingReason.WARMUP}},
        )


@pytest.mark.parametrize(
    ("reasons", "match"),
    [
        ({"UNKNOWN": {1: SignalMissingReason.WARMUP}}, "unknown symbol"),
        ({"AAA": {99: SignalMissingReason.WARMUP}}, "canonical index"),
    ],
)
def test_missingness_keys_must_name_exact_panel_cells(
    reasons: Mapping[str, Mapping[int, SignalMissingReason]], match: str
) -> None:
    strategy, panel, signals, stops, simulator = _case()

    with pytest.raises(ValueError, match=match):
        simulator.run(
            strategy,
            panel,
            signals,
            stops,
            source_indices=range(6),
            missing_reasons=reasons,
        )


@pytest.mark.parametrize("target", ["signals", "stops"])
@pytest.mark.parametrize("change", ["missing", "extra"])
def test_signal_and_stop_symbols_must_exactly_match_panel(target: str, change: str) -> None:
    strategy, panel, signals, stops, simulator = _case()
    columns = signals if target == "signals" else stops
    if change == "missing":
        columns.pop("AAA")
    else:
        columns["ZZZ"] = np.zeros(len(panel), dtype=np.float64)

    with pytest.raises(ValueError, match=f"{target} symbols"):
        simulator.run(strategy, panel, signals, stops, source_indices=range(6))


@pytest.mark.parametrize("target", ["signals", "stops"])
def test_column_lengths_must_match_panel(target: str) -> None:
    strategy, panel, signals, stops, simulator = _case()
    columns = signals if target == "signals" else stops
    columns["AAA"] = columns["AAA"][:-1]

    with pytest.raises(ValueError, match="wrong length"):
        simulator.run(strategy, panel, signals, stops, source_indices=range(6))


@pytest.mark.parametrize(
    "source_indices",
    [[], range(5), [0, 1, 1, 2, 3, 4], [0, 2, 3, 4, 5, 6], [1, 0, 2, 3, 4, 5]],
)
def test_source_indices_must_be_exact_contiguous_axis(
    source_indices: Sequence[int],
) -> None:
    strategy, panel, signals, stops, simulator = _case()

    with pytest.raises(ValueError, match="source_indices"):
        simulator.run(strategy, panel, signals, stops, source_indices=source_indices)


def test_source_indices_reject_bool_as_integer() -> None:
    strategy, panel, signals, stops, simulator = _case()

    with pytest.raises(ValueError, match="whole"):
        simulator.run(strategy, panel, signals, stops, source_indices=[False, 1, 2, 3, 4, 5])


@pytest.mark.parametrize("second", ["2024-01-01", "2023-12-31"])
def test_panel_dates_must_be_strictly_increasing_unique_sessions(second: str) -> None:
    strategy, panel, signals, stops, simulator = _case()
    for bars in panel.bars:
        bars.ts[1] = np.datetime64(second)

    with pytest.raises(ValueError, match="date axis"):
        simulator.run(strategy, panel, signals, stops, source_indices=range(6))


@pytest.mark.parametrize("column", ["open", "high", "low", "close", "volume"])
def test_panel_bar_shapes_are_preflighted(column: str) -> None:
    strategy, panel, signals, stops, simulator = _case()
    bars = panel.bars[0]
    malformed = Bars(
        ts=bars.ts,
        open=bars.open[:-1] if column == "open" else bars.open,
        high=bars.high[:-1] if column == "high" else bars.high,
        low=bars.low[:-1] if column == "low" else bars.low,
        close=bars.close[:-1] if column == "close" else bars.close,
        volume=bars.volume[:-1] if column == "volume" else bars.volume,
    )
    panel = Panel(panel.symbols, (malformed, *panel.bars[1:]), panel.tradable)

    with pytest.raises(ValueError, match="panel bar shape"):
        simulator.run(strategy, panel, signals, stops, source_indices=range(6))


def test_panel_membership_shape_is_preflighted() -> None:
    strategy, panel, signals, stops, simulator = _case()
    panel = Panel(panel.symbols, panel.bars, panel.tradable[:, :-1])

    with pytest.raises(ValueError, match="tradable shape"):
        simulator.run(strategy, panel, signals, stops, source_indices=range(6))


def test_preflight_checks_later_cells_before_any_fill_call() -> None:
    strategy, panel, signals, stops, simulator = _case(fills=cast(FillModel, _ExplodingFills()))
    signals["AAA"][0] = 1.0
    signals["CCC"][-1] = np.nan

    with pytest.raises(ValueError, match="unlabelled NaN"):
        simulator.run(strategy, panel, signals, stops, source_indices=range(6))


def test_empty_result_is_frozen_slotted_and_has_no_portfolio_metrics() -> None:
    strategy, panel, signals, stops, simulator = _case()
    result = simulator.run(strategy, panel, signals, stops, source_indices=range(6))

    assert result == SignalRunResult((), (), (), 0, 0)
    assert not hasattr(result, "__dict__")
    assert {field.name for field in fields(result)} == {
        "trades",
        "skips",
        "missing",
        "emitted_signals",
        "unfilled_exits",
    }
    for forbidden in ("equity", "sharpe", "max_drawdown", "gate_verdict"):
        assert not hasattr(result, forbidden)


@pytest.mark.parametrize(
    ("setup", "reason"),
    [
        ("last", SignalSkipReason.NO_NEXT_BAR),
        ("untradable", SignalSkipReason.NOT_TRADABLE),
        ("missing_bar", SignalSkipReason.NO_EXECUTION_BAR),
        ("zero_stop", SignalSkipReason.INVALID_STOP_DISTANCE),
        ("nan_stop", SignalSkipReason.INVALID_STOP_DISTANCE),
        ("expensive", SignalSkipReason.PRICE_ABOVE_NOTIONAL),
        ("no_fill", SignalSkipReason.ENTRY_NOT_FILLED),
    ],
)
def test_each_entry_refusal_has_one_explicit_reason(setup: str, reason: SignalSkipReason) -> None:
    strategy, panel, signals, stops, simulator = _case()
    symbol = "AAA"
    at = 0
    if setup == "last":
        at = len(panel) - 1
    elif setup == "untradable":
        panel.tradable[panel.index_of(symbol), at] = False
    elif setup == "missing_bar":
        panel.bars[panel.index_of(symbol)].open[1] = np.nan
    elif setup == "zero_stop":
        stops[symbol][at] = 0.0
    elif setup == "nan_stop":
        stops[symbol][at] = np.nan
    elif setup == "expensive":
        panel.bars[panel.index_of(symbol)].open[1] = 200_000.0
        panel.bars[panel.index_of(symbol)].high[1] = 200_001.0
        panel.bars[panel.index_of(symbol)].low[1] = 199_999.0
        panel.bars[panel.index_of(symbol)].close[1] = 200_000.0
    elif setup == "no_fill":
        symbol = "CCC"
    signals[symbol][at] = 1.0

    result = simulator.run(strategy, panel, signals, stops, source_indices=range(6))

    assert result.emitted_signals == 1
    assert result.trades == ()
    assert len(result.skips) == 1
    assert result.skips[0].reason is reason


def test_skip_precedence_is_deterministic() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["AAA"][-1] = 1.0
    panel.tradable[panel.index_of("AAA"), -1] = False
    stops["AAA"][-1] = np.nan

    result = simulator.run(strategy, panel, signals, stops, source_indices=range(6))

    assert result.skips[0].reason is SignalSkipReason.NO_NEXT_BAR


def test_repeated_signal_while_position_is_open_is_explicit_skip() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["BBB"][[0, 1]] = 1.0

    result = simulator.run(strategy, panel, signals, stops, source_indices=range(6))

    assert len(result.trades) == 1
    assert [skip.reason for skip in result.skips] == [SignalSkipReason.ALREADY_OPEN]
    assert result.emitted_signals == 2


def test_entry_executes_on_next_bar_and_partial_fill_is_recorded() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["BBB"][0] = 1.0

    result = simulator.run(strategy, panel, signals, stops, source_indices=range(40, 46))
    trade = result.trades[0]

    assert trade.signal_id.decision_index == 40
    assert trade.entry_index == 41
    assert trade.signal_id.decision_ts.isoformat() == "2024-01-01T00:00:00+00:00"
    assert trade.entry_ts.isoformat() == "2024-01-02T00:00:00+00:00"
    assert trade.filled_quantity == 20
    assert trade.exit_fragments[-1].reason is ExitReason.END_OF_DATA


def test_full_fill_deployment_uses_adverse_price_and_stays_within_notional() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["BBB"][0] = 1.0
    panel.bars[panel.index_of("BBB")].volume[1] = 1_000_000.0

    trade = simulator.run(strategy, panel, signals, stops, source_indices=range(6)).trades[0]

    assert trade.entry_price == Decimal("100.05")
    assert trade.filled_quantity == 999
    assert trade.deployed_capital == Decimal("99949.95")
    assert trade.entry_charges.turnover == Decimal("99949.95")
    assert trade.deployed_capital <= Decimal("100000")


def test_signal_mode_takes_more_simultaneous_entries_than_portfolio_slot_cap() -> None:
    strategy, _old_panel, _old_signals, _old_stops, simulator = _case()
    symbols = tuple(f"SYM{number}" for number in range(_RISK.max_open_positions + 1))
    bars = {symbol: _bars([100.0] * 6) for symbol in symbols}
    panel = Panel.build(
        bars,
        {symbol: np.ones(6, dtype=np.bool_) for symbol in symbols},
    )
    signals = {symbol: np.zeros(6, dtype=np.float64) for symbol in symbols}
    stops = {symbol: np.full(6, 10.0) for symbol in symbols}
    for symbol in symbols:
        signals[symbol][0] = 1.0

    result = simulator.run(strategy, panel, signals, stops, source_indices=range(6))

    assert len(result.trades) == 5
    assert len(result.trades) > _RISK.max_open_positions
    assert result.skips == ()


def test_stop_wins_when_stop_and_target_are_both_inside_bar() -> None:
    _old, panel, signals, stops, simulator = _case()
    strategy = _strategy_with(
        "stop_loss_atr: {atr_mult: 2.0, atr_period: 14}",
        "take_profit_r: {r_multiple: 1.0}",
    )
    signals["BBB"][0] = 1.0
    bars = panel.bars[panel.index_of("BBB")]
    bars.low[2] = 80.0
    bars.high[2] = 120.0

    trade = simulator.run(strategy, panel, signals, stops, source_indices=range(6)).trades[0]

    assert trade.exit_fragments[0].reason is ExitReason.STOP_LOSS
    assert trade.exit_fragments[0].recognition_index == 2


def test_protective_stop_can_fill_on_entry_bar() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["AAA"][0] = 1.0
    bars = panel.bars[panel.index_of("AAA")]
    bars.low[1] = 70.0

    trade = simulator.run(strategy, panel, signals, stops, source_indices=range(40, 46)).trades[0]

    assert trade.entry_index == 41
    assert trade.exit_fragments[0].recognition_index == 41
    assert trade.exit_fragments[0].reason is ExitReason.STOP_LOSS


def test_resting_target_requires_strict_trade_through() -> None:
    _old, panel, signals, stops, simulator = _case()
    strategy = _strategy_with(
        "stop_loss_atr: {atr_mult: 2.0, atr_period: 14}",
        "take_profit_r: {r_multiple: 1.0}",
    )
    signals["BBB"][0] = 1.0
    bars = panel.bars[panel.index_of("BBB")]
    bars.high[2] = 110.05
    bars.high[3] = 110.10

    trade = simulator.run(strategy, panel, signals, stops, source_indices=range(6)).trades[0]

    assert trade.exit_fragments[0].reason is ExitReason.TAKE_PROFIT
    assert trade.exit_fragments[0].recognition_index == 3


def test_time_stop_counts_held_sessions_like_portfolio() -> None:
    _old, panel, signals, stops, simulator = _case()
    strategy = _strategy_with(
        "stop_loss_atr: {atr_mult: 2.0, atr_period: 14}",
        "time_stop: {bars: 2}",
    )
    signals["BBB"][0] = 1.0

    trade = simulator.run(strategy, panel, signals, stops, source_indices=range(6)).trades[0]

    assert trade.exit_fragments[0].reason is ExitReason.TIME_STOP
    assert trade.exit_fragments[0].recognition_index == 2


def test_trailing_ratchet_order_matches_portfolio() -> None:
    _old, panel, signals, stops, simulator = _case()
    strategy = _strategy_with("trailing_stop_atr: {atr_mult: 2.0, atr_period: 14}")
    signals["BBB"][0] = 1.0
    bars = panel.bars[panel.index_of("BBB")]
    bars.close[1] = 120.0
    bars.high[1] = 121.0
    bars.low[1] = 99.0

    trade = simulator.run(strategy, panel, signals, stops, source_indices=range(6)).trades[0]

    assert trade.exit_fragments[0].reason is ExitReason.TRAILING_STOP
    assert trade.exit_fragments[0].recognition_index == 1


def test_partial_real_exits_aggregate_one_trade_and_charge_entry_once() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["AAA"][0] = 1.0
    bars = panel.bars[panel.index_of("AAA")]
    bars.low[2:] = 80.0
    bars.volume[2:5] = 1_000.0

    trade = simulator.run(strategy, panel, signals, stops, source_indices=range(6)).trades[0]

    assert len(trade.exit_fragments) > 1
    assert sum(fragment.quantity for fragment in trade.exit_fragments) == trade.filled_quantity
    assert trade.entry_charges.turnover == trade.deployed_capital
    assert trade.total_charges.turnover == trade.entry_charges.turnover + sum(
        (fragment.charges.turnover for fragment in trade.exit_fragments), Decimal(0)
    )


def test_dark_sessions_mark_at_last_close_with_separate_recognition() -> None:
    strategy, panel, signals, stops, _simulator = _case()
    simulator = SignalSimulator(
        notional_inr=Decimal("100000"),
        costs=CostModel(_COSTS),
        fills=FillModel(REALISM),
        stale_after_sessions=2,
    )
    signals["BBB"][0] = 1.0
    bars = panel.bars[panel.index_of("BBB")]
    for name in ("open", "high", "low", "close", "volume"):
        getattr(bars, name)[2:] = np.nan

    trade = simulator.run(strategy, panel, signals, stops, source_indices=range(40, 46)).trades[0]
    mark = trade.exit_fragments[-1]

    assert mark.reason is ExitReason.STALE_MARK
    assert mark.price_source_index == 41
    assert mark.recognition_index == 43
    assert mark.price_source_ts < mark.recognition_ts
    assert trade.marked_quantity == trade.filled_quantity
    assert trade.entry_charges == Charges(
        brokerage=Decimal("0"),
        stt=Decimal("2.00100"),
        exchange_txn=Decimal("0.061430700"),
        sebi_fee=Decimal("0.00200100"),
        gst=Decimal("0.01141770600"),
        stamp_duty=Decimal("0.3001500"),
        dp_charge=Decimal("0"),
        turnover=Decimal("2001.00"),
    )
    assert mark.charges == Charges(
        brokerage=Decimal("0"),
        stt=Decimal("2.0000"),
        exchange_txn=Decimal("0.06140000"),
        sebi_fee=Decimal("0.0020000"),
        gst=Decimal("0.0114120000"),
        stamp_duty=Decimal("0"),
        dp_charge=Decimal("15.34"),
        turnover=Decimal("2000.0"),
    )
    assert trade.deployed_capital == Decimal("2001.00")
    assert trade.costs == Decimal("19.79081140600")
    assert trade.gross_pnl == Decimal("-1.00")
    assert trade.net_pnl == Decimal("-20.79081140600")
    assert trade.gross_return == Decimal("-0.0004997501249375312343828085957")
    assert trade.net_return == Decimal("-0.01039021059770114942528735632")


def test_unfilled_final_exit_marks_residual_and_counts_refusal() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["BBB"][0] = 1.0
    panel.bars[panel.index_of("BBB")].volume[-1] = 1.0

    result = simulator.run(strategy, panel, signals, stops, source_indices=range(6))
    trade = result.trades[0]

    assert result.unfilled_exits == 1
    assert sum(fragment.quantity for fragment in trade.exit_fragments) == trade.filled_quantity
    assert trade.marked_quantity == trade.filled_quantity
    assert trade.exit_fragments[-1].reason is ExitReason.STALE_MARK


def test_partial_final_exit_and_residual_mark_have_literal_accounting() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["BBB"][0] = 1.0
    panel.bars[panel.index_of("BBB")].volume[-1] = 200.0

    result = simulator.run(strategy, panel, signals, stops, source_indices=range(6))
    trade = result.trades[0]
    actual_exit, residual_mark = trade.exit_fragments

    assert (actual_exit.quantity, actual_exit.price, actual_exit.reason) == (
        10,
        Decimal("99.95"),
        ExitReason.END_OF_DATA,
    )
    assert actual_exit.charges == Charges(
        brokerage=Decimal("0"),
        stt=Decimal("0.99950"),
        exchange_txn=Decimal("0.030684650"),
        sebi_fee=Decimal("0.00099950"),
        gst=Decimal("0.00570314700"),
        stamp_duty=Decimal("0"),
        dp_charge=Decimal("15.34"),
        turnover=Decimal("999.50"),
    )
    assert (residual_mark.quantity, residual_mark.price, residual_mark.reason) == (
        10,
        Decimal("100.0"),
        ExitReason.STALE_MARK,
    )
    assert residual_mark.charges == Charges(
        brokerage=Decimal("0"),
        stt=Decimal("1.0000"),
        exchange_txn=Decimal("0.03070000"),
        sebi_fee=Decimal("0.0010000"),
        gst=Decimal("0.0057060000"),
        stamp_duty=Decimal("0"),
        dp_charge=Decimal("15.34"),
        turnover=Decimal("1000.0"),
    )
    assert trade.entry_charges.total == Decimal("2.37599940600")
    assert trade.deployed_capital == Decimal("2001.00")
    assert trade.costs == Decimal("35.13029270300")
    assert trade.gross_pnl == Decimal("-1.50")
    assert trade.net_pnl == Decimal("-36.63029270300")
    assert trade.gross_return == Decimal("-0.0007496251874062968515742128936")
    assert trade.net_return == Decimal("-0.01830599335482258870564717641")
    assert trade.r_multiple == Decimal("-0.183151463515")


def test_canonical_offset_and_reentry_after_close_are_preserved() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["AAA"][[0, 3]] = 1.0

    result = simulator.run(strategy, panel, signals, stops, source_indices=range(40, 46))

    assert [trade.signal_id.decision_index for trade in result.trades] == [40, 43]
    assert [trade.entry_index for trade in result.trades] == [41, 44]
    assert len({trade.signal_id.uuid for trade in result.trades}) == 2


def test_full_source_and_slice_preserve_signal_id_and_holding_sessions() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["BBB"][1] = 1.0
    full_trade = simulator.run(
        strategy, panel, signals, stops, source_indices=range(40, 46)
    ).trades[0]

    sliced_bars = {}
    sliced_tradable = {}
    for symbol, bars in zip(panel.symbols, panel.bars, strict=True):
        sliced_bars[symbol] = Bars(
            ts=bars.ts[1:].copy(),
            open=bars.open[1:].copy(),
            high=bars.high[1:].copy(),
            low=bars.low[1:].copy(),
            close=bars.close[1:].copy(),
            volume=bars.volume[1:].copy(),
        )
        sliced_tradable[symbol] = panel.tradable[panel.index_of(symbol), 1:].copy()
    sliced_panel = Panel.build(sliced_bars, sliced_tradable)
    sliced_signals = {symbol: values[1:].copy() for symbol, values in signals.items()}
    sliced_stops = {symbol: values[1:].copy() for symbol, values in stops.items()}

    sliced_trade = simulator.run(
        strategy,
        sliced_panel,
        sliced_signals,
        sliced_stops,
        source_indices=range(41, 46),
    ).trades[0]

    assert sliced_trade.signal_id == full_trade.signal_id
    assert sliced_trade.signal_id.uuid == full_trade.signal_id.uuid
    assert sliced_trade.holding_sessions == full_trade.holding_sessions == 4


def test_benchmark_and_pre_tax_alpha_remain_unavailable() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["BBB"][0] = 1.0

    trade = simulator.run(strategy, panel, signals, stops, source_indices=range(6)).trades[0]

    assert all(fragment.benchmark_return is None for fragment in trade.exit_fragments)
    assert trade.benchmark_return is None
    assert trade.pre_tax_alpha is None


def test_repeated_runs_do_not_leak_book_state() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["BBB"][0] = 1.0

    first = simulator.run(strategy, panel, signals, stops, source_indices=range(6))
    second = simulator.run(strategy, panel, signals, stops, source_indices=range(6))

    assert second == first


def test_remaining_skip_precedence_pairs_are_pinned() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["BBB"][[0, 1]] = 1.0
    panel.tradable[panel.index_of("BBB"), 1] = False
    panel.bars[panel.index_of("BBB")].open[2] = np.nan
    stops["BBB"][1] = np.nan
    result = simulator.run(strategy, panel, signals, stops, source_indices=range(6))
    assert result.skips[0].reason is SignalSkipReason.NOT_TRADABLE

    strategy, panel, signals, stops, simulator = _case()
    signals["BBB"][[0, 1]] = 1.0
    panel.bars[panel.index_of("BBB")].open[2] = np.nan
    stops["BBB"][1] = np.nan
    result = simulator.run(strategy, panel, signals, stops, source_indices=range(6))
    assert result.skips[0].reason is SignalSkipReason.ALREADY_OPEN

    strategy, panel, signals, stops, simulator = _case()
    signals["AAA"][0] = 1.0
    panel.bars[panel.index_of("AAA")].open[1] = np.nan
    stops["AAA"][0] = 0.0
    result = simulator.run(strategy, panel, signals, stops, source_indices=range(6))
    assert result.skips[0].reason is SignalSkipReason.NO_EXECUTION_BAR

    strategy, panel, signals, stops, simulator = _case()
    signals["AAA"][0] = 1.0
    stops["AAA"][0] = 0.0
    panel.bars[panel.index_of("AAA")].open[1] = 200_000.0
    panel.bars[panel.index_of("AAA")].volume[1] = 0.0
    result = simulator.run(strategy, panel, signals, stops, source_indices=range(6))
    assert result.skips[0].reason is SignalSkipReason.INVALID_STOP_DISTANCE

    stops["AAA"][0] = 10.0
    result = simulator.run(strategy, panel, signals, stops, source_indices=range(6))
    assert result.skips[0].reason is SignalSkipReason.PRICE_ABOVE_NOTIONAL


def test_final_bar_exit_priority_remains_end_of_data() -> None:
    strategy, panel, signals, stops, simulator = _case()
    signals["BBB"][0] = 1.0
    panel.bars[panel.index_of("BBB")].low[-1] = 1.0

    trade = simulator.run(strategy, panel, signals, stops, source_indices=range(6)).trades[0]

    assert trade.exit_fragments[-1].reason is ExitReason.END_OF_DATA


def test_panel_symbol_and_bar_counts_are_preflighted() -> None:
    strategy, panel, signals, stops, _simulator = _case()
    malformed = Panel(panel.symbols, panel.bars[:-1], panel.tradable)
    simulator = SignalSimulator(
        notional_inr=Decimal("100000"),
        costs=CostModel(_COSTS),
        fills=cast(FillModel, _ExplodingFills()),
        stale_after_sessions=20,
    )

    with pytest.raises(ValueError, match="panel bars"):
        simulator.run(strategy, malformed, signals, stops, source_indices=range(6))


def test_signaltest_has_no_forbidden_runtime_imports() -> None:
    path = Path(__file__).parents[2] / "icarus" / "engine" / "signaltest.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    } | {node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)}

    assert not any(
        name == "icarus.engine.portfolio"
        or "broker" in name
        or name == "icarus.engine.metrics"
        or name.endswith("taxmodel")
        for name in imported
    )
