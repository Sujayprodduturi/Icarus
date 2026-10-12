"""TDD specification for the two D47 strategy consumers.

This file stays in the verification plan directory until F48 source ownership is released.  It
uses artificial bars only.  Each test names a consumer-visible failure rather than inspecting the
implementation.  After release it moves unchanged to ``tests/unit/test_strategy_consumers.py``
for the RED witness, then drives the implementation.
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path

import numpy as np
import numpy.typing as npt
import pytest

from icarus.common.config import GoalConfig, load_goal
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel
from icarus.engine.portfolio import ExitReason, PortfolioSimulator
from icarus.engine.runner import _run_span, evaluate_once
from icarus.engine.signaltest import SignalSimulator
from icarus.strategy.dsl import Bars, Call, DslError, Panel, StrategyCandidate, parse_strategy
from icarus.strategy.library import default_registry

START = np.datetime64("2020-01-01")

DONCHIAN = """
name: donchian_55_20
version: 1
timeframe: 1d
universe: nse_liquid
entry: {donchian_breakout_up: {n: 55, basis: close}}
exit:
  - stop_loss_atr: {atr_mult: 3.0, atr_period: 14}
  - opposite_signal:
      event: {donchian_breakout_down: {n: 20, basis: close}}
sizing: {risk_r: 0.005, weighting: equal_weight}
"""

LOW_VOL = """
name: defensive_low_vol_252_q63
version: 1
timeframe: 1d
universe: nse_liquid
entry:
  xs_bottom_n:
    expr: {realized_vol: {n: 252}}
    n: 30
    min_symbols: 31
rank_by: {negate: {series: {realized_vol: {n: 252}}}}
rebalance: {every_sessions: 63}
exit:
  - stop_loss_atr: {atr_mult: 3.0, atr_period: 14}
sizing: {risk_r: 0.005, weighting: equal_weight}
"""


@pytest.fixture
def goal(repo_root: Path) -> GoalConfig:
    return load_goal(repo_root / "goal.yaml")


def _parse(text: str) -> StrategyCandidate:
    return parse_strategy(text, registry=default_registry(), max_risk_r=0.005)


def _bars(
    close: npt.NDArray[np.float64],
    *,
    open_: npt.NDArray[np.float64] | None = None,
    high: npt.NDArray[np.float64] | None = None,
    low: npt.NDArray[np.float64] | None = None,
    volume: npt.NDArray[np.float64] | None = None,
) -> Bars:
    size = close.size
    return Bars(
        ts=np.arange(START, START + size).astype("datetime64[ns]"),
        open=close.copy() if open_ is None else open_,
        high=close + 1.0 if high is None else high,
        low=close - 1.0 if low is None else low,
        close=close,
        volume=np.full(size, 1_000_000.0) if volume is None else volume,
    )


def _panel(bars: dict[str, Bars]) -> Panel:
    size = len(next(iter(bars.values())))
    return Panel.build(
        bars,
        {symbol: np.ones(size, dtype=np.bool_) for symbol in bars},
    )


def _flat_panel(symbols: tuple[str, ...], size: int) -> Panel:
    return _panel({symbol: _bars(np.full(size, 100.0)) for symbol in symbols})


def _portfolio(goal: GoalConfig) -> PortfolioSimulator:
    return PortfolioSimulator(
        risk=goal.risk,
        costs=CostModel(goal.costs),
        fills=FillModel(goal.execution_realism),
        stale_after_sessions=goal.backtest.stale_position_sessions,
    )


def _signals(symbols: tuple[str, ...], size: int) -> dict[str, npt.NDArray[np.float64]]:
    return {symbol: np.zeros(size, dtype=np.float64) for symbol in symbols}


def _stops(
    symbols: tuple[str, ...], size: int, distance: float = 10.0
) -> dict[str, npt.NDArray[np.float64]]:
    return {symbol: np.full(size, distance, dtype=np.float64) for symbol in symbols}


def _rank_columns(symbols: tuple[str, ...], size: int) -> dict[str, npt.NDArray[np.float64]]:
    return {
        symbol: np.full(size, float(len(symbols) - index), dtype=np.float64)
        for index, symbol in enumerate(symbols)
    }


def _low_vol_panel(size: int = 400, symbols: int = 31) -> Panel:
    """Thirty-one deterministic return paths ordered from lowest to highest volatility."""
    bars: dict[str, Bars] = {}
    signs = np.where(np.arange(size) % 2 == 0, 1.0, -1.0)
    for index in range(symbols):
        returns = signs * (index + 1) * 0.00005
        close = 100.0 * np.cumprod(1.0 + returns)
        bars[f"S{index:02d}"] = _bars(close.astype(np.float64))
    return _panel(bars)


def _expand_rebalance_fixture(
    panel: Panel,
    signals: dict[str, npt.NDArray[np.float64]],
    ranks: dict[str, npt.NDArray[np.float64]],
    pulses: npt.NDArray[np.bool_],
) -> tuple[
    Panel,
    dict[str, npt.NDArray[np.float64]],
    dict[str, npt.NDArray[np.float64]],
    npt.NDArray[np.bool_],
    tuple[int, ...],
    dict[int, int],
]:
    """Put hand-worked logical events on the unchanged card's source252/315 grid.

    Inserted sessions are flat, finite, and zero-volume; they cannot add fills or new signals.
    The map preserves every original logical event and its immediate execution bar.
    """
    pulse_number = {int(index): k for k, index in enumerate(np.flatnonzero(pulses))}
    offset = 0
    mapping = {}
    for old in range(len(panel)):
        if old in pulse_number:
            offset = 63 * pulse_number[old] - old
        mapping[old] = old + offset
    size = mapping[len(panel) - 1] + 1
    bars = {}
    membership = {}
    expanded_signals = {}
    expanded_ranks = {}
    for symbol, original in zip(panel.symbols, panel.bars, strict=True):
        expanded = _bars(np.full(size, float(original.close[0])), volume=np.zeros(size))
        eligible = np.ones(size, dtype=np.bool_)
        entry = np.zeros(size, dtype=np.float64)
        rank = np.full(size, float(ranks[symbol][0]))
        for old, new in mapping.items():
            for name in ("open", "high", "low", "close", "volume"):
                getattr(expanded, name)[new] = getattr(original, name)[old]
            eligible[new] = panel.tradable[panel.index_of(symbol), old]
            entry[new] = signals[symbol][old]
            rank[new] = ranks[symbol][old]
        bars[symbol] = expanded
        membership[symbol] = eligible
        expanded_signals[symbol] = entry
        expanded_ranks[symbol] = rank
    source = tuple(range(252, 252 + size))
    return (
        Panel.build(bars, membership),
        expanded_signals,
        expanded_ranks,
        np.array([index % 63 == 0 for index in source]),
        source,
        mapping,
    )


def test_exact_cards_parse_and_audit_nested_exit_primitives() -> None:
    donchian = _parse(DONCHIAN)
    low_vol = _parse(LOW_VOL)

    assert donchian.primitives_used() == frozenset(
        {"donchian_breakout_up", "donchian_breakout_down"}
    )
    assert donchian.exits[1].rule == "opposite_signal"
    assert isinstance(donchian.exits[1].event, Call)
    assert donchian.exits[1].event.primitive == "donchian_breakout_down"
    assert low_vol.rebalance is not None
    assert low_vol.rebalance.every_sessions == 63
    assert low_vol.rank_by is not None and low_vol.rank_by.primitive == "negate"
    assert low_vol.sizing.weighting == "equal_weight"


@pytest.mark.parametrize(
    "bad",
    [
        DONCHIAN.replace("event:", "events:"),
        LOW_VOL.replace("every_sessions: 63", "every_sessions: 63, anchor: fold"),
        LOW_VOL.replace("rebalance: {every_sessions: 63}", "rebalance: {every_sessions: 0}"),
    ],
)
def test_unknown_or_invalid_consumer_fields_refuse(bad: str) -> None:
    with pytest.raises(DslError):
        _parse(bad)


def test_negate_accepts_scale_free_volatility_and_refuses_price_level() -> None:
    accepted = _parse(LOW_VOL)
    assert accepted.rank_by is not None

    unsafe = LOW_VOL.replace(
        "{negate: {series: {realized_vol: {n: 252}}}}",
        "{negate: {series: close}}",
    )
    with pytest.raises(DslError, match="scale-free"):
        _parse(unsafe)


def test_donchian_exit_is_fresh_strict_and_computed_before_fold_slicing() -> None:
    close = np.full(80, 100.0)
    close[55:75] = 110.0
    close[75:] = np.array([90.0, 89.0, 89.0, 89.0, 89.0])
    panel = _panel({"AAA": _bars(close)})

    columns = evaluate_once(_parse(DONCHIAN), panel, default_registry())
    assert columns.exit_signals is not None
    exits = columns.exit_signals["AAA"]

    assert columns.signals["AAA"][55] == 1.0
    assert exits[74] == 0.0
    assert exits[75] == 1.0
    assert exits[76] == 0.0
    sliced_exits = columns.slice(60, 80)[3]
    assert sliced_exits is not None
    assert np.array_equal(
        exits[60:],
        sliced_exits["AAA"],
        equal_nan=True,
    )


def test_opposite_exit_decision_is_latched_and_first_fills_next_bar(goal: GoalConfig) -> None:
    panel = _flat_panel(("AAA",), 6)
    signals = {"AAA": np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0])}
    exits = {"AAA": np.array([0.0, 0.0, 1.0, 0.0, 0.0, 0.0])}
    panel.bars[0].volume[3] = 0.0

    result = _portfolio(goal).run(
        _parse(DONCHIAN),
        panel,
        signals,
        _stops(panel.symbols, len(panel)),
        exit_signals=exits,
        starting_equity=Decimal("100000"),
        source_indices=range(40, 46),
    )

    trade = result.trades[0]
    assert trade.reason is ExitReason.OPPOSITE_SIGNAL
    assert trade.exit_ts == panel.ts[4].astype("datetime64[us]").astype(object).replace(
        tzinfo=trade.exit_ts.tzinfo
    )
    assert result.unfilled_exits == 1
    event = result.management_exit_events[0]
    assert (event.decision_index, event.first_execution_index) == (42, 43)


def test_protective_exit_spends_the_only_exit_attempt_and_pending_retries_later(
    goal: GoalConfig,
) -> None:
    close = np.full(7, 100.0)
    low = np.array([99.0, 99.0, 99.0, 80.0, 99.0, 99.0, 99.0])
    volume = np.array([1_000_000.0, 1_000_000.0, 1_000_000.0, 400.0, 400.0, 400.0, 400.0])
    panel = _panel({"AAA": _bars(close, low=low, volume=volume)})
    signals = {"AAA": np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0])}
    exits = {"AAA": np.array([0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0])}

    result = _portfolio(goal).run(
        _parse(DONCHIAN),
        panel,
        signals,
        _stops(panel.symbols, len(panel)),
        exit_signals=exits,
        starting_equity=Decimal("100000"),
    )

    assert [(trade.reason, trade.quantity) for trade in result.trades[:2]] == [
        (ExitReason.STOP_LOSS, 20),
        (ExitReason.OPPOSITE_SIGNAL, 20),
    ]
    assert result.trades[0].exit_ts == panel.ts[3].astype("datetime64[us]").astype(object).replace(
        tzinfo=result.trades[0].exit_ts.tzinfo
    )
    assert result.trades[1].exit_ts == panel.ts[4].astype("datetime64[us]").astype(object).replace(
        tzinfo=result.trades[1].exit_ts.tzinfo
    )


def test_low_vol_membership_and_rank_are_exact_at_first_whole_source_pulse() -> None:
    panel = _low_vol_panel()
    columns = evaluate_once(
        _parse(LOW_VOL),
        panel,
        default_registry(),
        source_indices=range(len(panel)),
    )

    selected = tuple(symbol for symbol in panel.symbols if columns.signals[symbol][252] == 1.0)
    ranked = sorted(selected, key=lambda symbol: -columns.ranks[symbol][252])  # type: ignore[index]
    assert selected == tuple(f"S{index:02d}" for index in range(30))
    assert ranked == list(selected)
    assert columns.rebalance_pulses is not None
    assert np.flatnonzero(columns.rebalance_pulses).tolist() == [252, 315, 378]


def test_schedule_uses_offset_full_source_axis_and_survives_different_fold_starts(
    goal: GoalConfig,
) -> None:
    panel = _low_vol_panel(size=320)
    source = tuple(range(100, 420))
    strategy = _parse(LOW_VOL)
    columns = evaluate_once(strategy, panel, default_registry(), source_indices=source)

    assert columns.rebalance_pulses is not None
    assert [source[i] for i in np.flatnonzero(columns.rebalance_pulses)] == [252, 315, 378]
    first = _run_span(strategy, panel, 120, 230, columns, goal, source)
    second = _run_span(strategy, panel, 200, 320, columns, goal, source)
    assert [event.decision_index for event in first.rebalance_events] == [252, 315]
    assert [event.decision_index for event in second.rebalance_events] == [315, 378]


@pytest.mark.parametrize(
    ("active", "nonfinite", "want_status"),
    [
        (30, (), "cohort_unavailable"),
        (31, (0,), "cohort_unavailable"),
        (29, (), "cardinality_mismatch"),
        (31, (), "cardinality_mismatch"),
    ],
)
def test_invalid_or_tied_cohort_refuses_without_liquidating_incumbents(
    goal: GoalConfig,
    active: int,
    nonfinite: tuple[int, ...],
    want_status: str,
) -> None:
    symbols = tuple(f"S{index:02d}" for index in range(31))
    panel = _flat_panel(symbols, 6)
    signals = _signals(symbols, len(panel))
    ranks = _rank_columns(symbols, len(panel))
    pulses = np.array([True, False, True, False, False, False])
    for symbol in symbols[:30]:
        signals[symbol][0] = 1.0
    for symbol in symbols[:active]:
        signals[symbol][2] = 1.0
    for index in nonfinite:
        signals[symbols[index]][2] = np.nan
    if active == 30 and not nonfinite:
        panel.tradable[-1, 2] = False

    panel, signals, ranks, pulses, source, _mapping = _expand_rebalance_fixture(
        panel, signals, ranks, pulses
    )
    result = _portfolio(goal).run(
        _parse(LOW_VOL),
        panel,
        signals,
        _stops(symbols, len(panel)),
        ranks=ranks,
        rebalance_pulses=pulses,
        source_indices=source,
        starting_equity=Decimal("100000"),
    )

    refused = result.rebalance_events[1]
    assert refused.status.value == want_status
    assert refused.candidates == ()
    assert not [trade for trade in result.trades if trade.reason is ExitReason.REBALANCE]


def test_rebalance_retains_incumbents_caps_book_at_four_and_uses_actual_freed_slot(
    goal: GoalConfig,
) -> None:
    symbols = tuple(f"S{index:02d}" for index in range(31))
    panel = _flat_panel(symbols, 7)
    signals = _signals(symbols, len(panel))
    ranks = _rank_columns(symbols, len(panel))
    pulses = np.array([True, False, True, False, False, False, False])
    for symbol in symbols[:30]:
        signals[symbol][0] = 1.0
        signals[symbol][2] = 1.0
    signals["S00"][2] = 0.0
    signals["S30"][2] = 1.0

    panel, signals, ranks, pulses, source, _mapping = _expand_rebalance_fixture(
        panel, signals, ranks, pulses
    )
    result = _portfolio(goal).run(
        _parse(LOW_VOL),
        panel,
        signals,
        _stops(symbols, len(panel)),
        ranks=ranks,
        rebalance_pulses=pulses,
        source_indices=source,
        starting_equity=Decimal("100000"),
    )

    first, second = result.rebalance_events
    assert len(first.candidates) == len(second.candidates) == 30
    assert first.holdings_after == ("S00", "S01", "S02", "S03")
    assert second.retained == ("S01", "S02", "S03")
    assert second.holdings_after == ("S01", "S02", "S03", "S04")
    assert len(second.holdings_after) == 4
    assert [(trade.symbol, trade.reason) for trade in result.trades if trade.symbol == "S00"] == [
        ("S00", ExitReason.REBALANCE)
    ]


def test_partial_rebalance_exit_keeps_slot_and_defers_admission(goal: GoalConfig) -> None:
    symbols = tuple(f"S{index:02d}" for index in range(31))
    panel = _flat_panel(symbols, 8)
    panel.bars[panel.index_of("S00")].volume[3] = 1.0
    signals = _signals(symbols, len(panel))
    ranks = _rank_columns(symbols, len(panel))
    pulses = np.array([True, False, True, False, False, False, False, False])
    for symbol in symbols[:30]:
        signals[symbol][0] = 1.0
        signals[symbol][2] = 1.0
    signals["S00"][2] = 0.0
    signals["S30"][2] = 1.0

    panel, signals, ranks, pulses, source, _mapping = _expand_rebalance_fixture(
        panel, signals, ranks, pulses
    )
    result = _portfolio(goal).run(
        _parse(LOW_VOL),
        panel,
        signals,
        _stops(symbols, len(panel)),
        ranks=ranks,
        rebalance_pulses=pulses,
        source_indices=source,
        starting_equity=Decimal("100000"),
    )

    second = result.rebalance_events[1]
    assert "S00" in second.holdings_after
    assert "S04" not in second.holdings_after
    assert "S04" in second.pending_admissions
    assert "S30" in second.pending_admissions


def test_queued_admission_keeps_entry_session_protective_stop(goal: GoalConfig) -> None:
    symbols = tuple(f"S{index:02d}" for index in range(31))
    panel = _flat_panel(symbols, 7)
    new_bars = panel.bars[panel.index_of("S04")]
    new_bars.low[3] = 80.0
    signals = _signals(symbols, len(panel))
    ranks = _rank_columns(symbols, len(panel))
    pulses = np.array([True, False, True, False, False, False, False])
    for symbol in symbols[:30]:
        signals[symbol][0] = 1.0
        signals[symbol][2] = 1.0
    signals["S00"][2] = 0.0
    signals["S30"][2] = 1.0

    panel, signals, ranks, pulses, source, _mapping = _expand_rebalance_fixture(
        panel, signals, ranks, pulses
    )
    result = _portfolio(goal).run(
        _parse(LOW_VOL),
        panel,
        signals,
        _stops(symbols, len(panel)),
        ranks=ranks,
        rebalance_pulses=pulses,
        source_indices=source,
        starting_equity=Decimal("100000"),
    )

    stopped = next(trade for trade in result.trades if trade.symbol == "S04")
    assert stopped.reason is ExitReason.STOP_LOSS
    assert stopped.exit_ts == stopped.entry_ts


@pytest.mark.parametrize("risk_r", [0.004, 0.005])
def test_stop_out_cannot_reenter_between_pulses_but_can_at_next_pulse(
    goal: GoalConfig, risk_r: float
) -> None:
    symbols = tuple(f"S{index:02d}" for index in range(31))
    panel = _flat_panel(symbols, 8)
    panel.bars[panel.index_of("S00")].low[2] = 80.0
    signals = _signals(symbols, len(panel))
    ranks = _rank_columns(symbols, len(panel))
    pulses = np.array([True, False, False, False, True, False, False, False])
    for symbol in symbols[:30]:
        signals[symbol][0] = 1.0
        signals[symbol][1] = 1.0
        signals[symbol][4] = 1.0

    panel, signals, ranks, pulses, source, _mapping = _expand_rebalance_fixture(
        panel, signals, ranks, pulses
    )
    result = _portfolio(goal).run(
        _parse(LOW_VOL.replace("risk_r: 0.005", f"risk_r: {risk_r}")),
        panel,
        signals,
        _stops(symbols, len(panel)),
        ranks=ranks,
        rebalance_pulses=pulses,
        source_indices=source,
        starting_equity=Decimal("100000"),
    )

    s00 = [trade for trade in result.trades if trade.symbol == "S00"]
    assert s00[0].reason is ExitReason.STOP_LOSS
    if risk_r == 0.005:
        from icarus.engine.portfolio import Skipped

        assert len(s00) == 1
        assert result.skipped[Skipped.HEAT_CAP] > 0
        return
    assert s00[1].entry_ts == panel.ts[_mapping[5]].astype("datetime64[us]").astype(object).replace(
        tzinfo=s00[1].entry_ts.tzinfo
    )


def test_signal_mode_reports_same_schedule_and_conditional_exit_identity(goal: GoalConfig) -> None:
    panel = _flat_panel(("AAA",), 6)
    signals = {"AAA": np.array([1.0, 0.0, 0.0, 0.0, 0.0, 0.0])}
    exits = {"AAA": np.array([0.0, 0.0, 1.0, 0.0, 0.0, 0.0])}
    result = SignalSimulator(
        notional_inr=Decimal("100000"),
        costs=CostModel(goal.costs),
        fills=FillModel(goal.execution_realism),
        stale_after_sessions=goal.backtest.stale_position_sessions,
    ).run(
        _parse(DONCHIAN),
        panel,
        signals,
        _stops(panel.symbols, len(panel)),
        exit_signals=exits,
        source_indices=range(100, 106),
    )

    assert result.trades[0].exit_fragments[0].reason is ExitReason.OPPOSITE_SIGNAL
    assert result.management_exit_events[0].decision_index == 102


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_entry_and_exit_on_same_decision_bar_does_not_exit_future_holding(
    goal: GoalConfig, mode: str
) -> None:
    panel = _flat_panel(("AAA",), 5)
    signals = {"AAA": np.array([1.0, 0.0, 0.0, 0.0, 0.0])}
    exits = {"AAA": np.array([1.0, 0.0, 0.0, 0.0, 0.0])}
    stops = _stops(panel.symbols, len(panel))
    strategy = _parse(DONCHIAN)
    if mode == "portfolio":
        portfolio_result = _portfolio(goal).run(
            strategy, panel, signals, stops, exit_signals=exits, starting_equity=Decimal("100000")
        )
        assert portfolio_result.trades[0].reason is ExitReason.END_OF_DATA
    else:
        signal_result = SignalSimulator(
            notional_inr=Decimal("100000"),
            costs=CostModel(goal.costs),
            fills=FillModel(goal.execution_realism),
            stale_after_sessions=goal.backtest.stale_position_sessions,
        ).run(strategy, panel, signals, stops, exit_signals=exits, source_indices=range(len(panel)))
        assert signal_result.trades[0].exit_fragments[0].reason is ExitReason.END_OF_DATA
    if mode == "portfolio":
        assert not portfolio_result.management_exit_events
    else:
        assert not signal_result.management_exit_events


def test_signal_rebalance_is_uncapped_retains_and_exits_removed_next_bar(goal: GoalConfig) -> None:
    symbols = tuple(f"S{index:02d}" for index in range(31))
    panel = _flat_panel(symbols, 7)
    signals = _signals(symbols, len(panel))
    for symbol in symbols[:30]:
        signals[symbol][0] = signals[symbol][2] = 1.0
    signals["S00"][2] = 0.0
    signals["S30"][2] = 1.0
    ranks = _rank_columns(symbols, len(panel))
    pulses = np.array([True, False, True, False, False, False, False])
    panel, signals, ranks, pulses, source, _ = _expand_rebalance_fixture(
        panel, signals, ranks, pulses
    )
    result = SignalSimulator(
        notional_inr=Decimal("10000"),
        costs=CostModel(goal.costs),
        fills=FillModel(goal.execution_realism),
        stale_after_sessions=goal.backtest.stale_position_sessions,
    ).run(
        _parse(LOW_VOL),
        panel,
        signals,
        _stops(symbols, len(panel)),
        ranks=ranks,
        source_indices=source,
        rebalance_pulses=pulses,
    )
    assert len(result.rebalance_events[0].holdings_after) == 30
    assert len(result.trades) == 31
    removed = next(trade for trade in result.trades if trade.signal_id.symbol == "S00")
    assert removed.exit_fragments[0].reason is ExitReason.REBALANCE
    assert removed.exit_fragments[0].recognition_index == 316
    assert result.management_exit_events[0].decision_index == 315
    retained = next(trade for trade in result.trades if trade.signal_id.symbol == "S01")
    assert retained.entry_index == 253 and len(retained.exit_fragments) == 1


def test_global_rank_admits_newcomer_only_when_it_is_best_unheld(goal: GoalConfig) -> None:
    symbols = tuple(f"S{index:02d}" for index in range(31))
    panel = _flat_panel(symbols, 7)
    signals = _signals(symbols, len(panel))
    ranks = _rank_columns(symbols, len(panel))
    for symbol in symbols[:30]:
        signals[symbol][0] = signals[symbol][2] = 1.0
    signals["S00"][2] = 0.0
    signals["S30"][2] = 1.0
    ranks["S30"][2] = 100.0
    pulses = np.array([True, False, True, False, False, False, False])
    panel, signals, ranks, pulses, source, _ = _expand_rebalance_fixture(
        panel, signals, ranks, pulses
    )
    result = _portfolio(goal).run(
        _parse(LOW_VOL),
        panel,
        signals,
        _stops(symbols, len(panel)),
        ranks=ranks,
        rebalance_pulses=pulses,
        source_indices=source,
        starting_equity=Decimal("100000"),
    )
    assert result.rebalance_events[1].holdings_after == ("S01", "S02", "S03", "S30")


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_retained_at_grid_and_stopped_next_bar_has_no_readmission_intent(
    goal: GoalConfig, mode: str
) -> None:
    symbols = tuple(f"S{index:02d}" for index in range(31))
    panel = _flat_panel(symbols, 7)
    panel.bars[0].low[3] = 80.0
    signals = _signals(symbols, len(panel))
    for symbol in symbols[:30]:
        signals[symbol][0] = signals[symbol][2] = 1.0
    strategy = _parse(LOW_VOL.replace("risk_r: 0.005", "risk_r: 0.004"))
    ranks = _rank_columns(symbols, len(panel))
    pulses = np.array([True, False, True, False, False, False, False])
    panel, signals, ranks, pulses, source, _ = _expand_rebalance_fixture(
        panel, signals, ranks, pulses
    )
    if mode == "portfolio":
        portfolio_result = _portfolio(goal).run(
            strategy,
            panel,
            signals,
            _stops(symbols, len(panel)),
            ranks=ranks,
            rebalance_pulses=pulses,
            source_indices=source,
            starting_equity=Decimal("100000"),
        )
        assert len([trade for trade in portfolio_result.trades if trade.symbol == "S00"]) == 1
    else:
        signal_result = SignalSimulator(
            notional_inr=Decimal("10000"),
            costs=CostModel(goal.costs),
            fills=FillModel(goal.execution_realism),
            stale_after_sessions=goal.backtest.stale_position_sessions,
        ).run(
            strategy,
            panel,
            signals,
            _stops(symbols, len(panel)),
            ranks=ranks,
            rebalance_pulses=pulses,
            source_indices=source,
        )
        assert (
            len([trade for trade in signal_result.trades if trade.signal_id.symbol == "S00"]) == 1
        )


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_off_grid_rebalance_pulses_refuse_before_simulation(goal: GoalConfig, mode: str) -> None:
    symbols = tuple(f"S{index:02d}" for index in range(31))
    panel = _flat_panel(symbols, 6)
    signals = _signals(symbols, len(panel))
    ranks = _rank_columns(symbols, len(panel))
    pulses = np.array([True, False, True, False, False, False])
    source = tuple(range(252, 258))
    with pytest.raises(ValueError, match="grid"):
        if mode == "portfolio":
            _portfolio(goal).run(
                _parse(LOW_VOL),
                panel,
                signals,
                _stops(symbols, len(panel)),
                ranks=ranks,
                rebalance_pulses=pulses,
                source_indices=source,
                starting_equity=Decimal("100000"),
            )
        else:
            SignalSimulator(
                notional_inr=Decimal("10000"),
                costs=CostModel(goal.costs),
                fills=FillModel(goal.execution_realism),
                stale_after_sessions=goal.backtest.stale_position_sessions,
            ).run(
                _parse(LOW_VOL),
                panel,
                signals,
                _stops(symbols, len(panel)),
                ranks=ranks,
                rebalance_pulses=pulses,
                source_indices=source,
            )


def test_pending_removal_stays_latched_when_later_target_includes_symbol(goal: GoalConfig) -> None:
    symbols = tuple(f"S{index:02d}" for index in range(31))
    panel = _flat_panel(symbols, 7)
    panel.bars[0].volume[3:5] = 0.0
    signals = _signals(symbols, len(panel))
    ranks = _rank_columns(symbols, len(panel))
    for symbol in symbols[:30]:
        signals[symbol][0] = signals[symbol][2] = signals[symbol][4] = 1.0
    signals["S00"][2] = 0.0
    signals["S30"][2] = 1.0
    pulses = np.array([True, False, True, False, True, False, False])
    panel, signals, ranks, pulses, source, _ = _expand_rebalance_fixture(
        panel, signals, ranks, pulses
    )
    result = SignalSimulator(
        notional_inr=Decimal("10000"),
        costs=CostModel(goal.costs),
        fills=FillModel(goal.execution_realism),
        stale_after_sessions=goal.backtest.stale_position_sessions,
    ).run(
        _parse(LOW_VOL),
        panel,
        signals,
        _stops(symbols, len(panel)),
        ranks=ranks,
        source_indices=source,
        rebalance_pulses=pulses,
    )
    removed = [trade for trade in result.trades if trade.signal_id.symbol == "S00"]
    assert len(removed) == 1
    assert removed[0].exit_fragments[0].reason is ExitReason.REBALANCE
    assert removed[0].exit_fragments[0].recognition_index == 379
    assert "S00" not in result.rebalance_events[2].retained


@pytest.mark.parametrize(("symbols", "tail_tie", "selected_count"), [(32, 3, 29), (31, 2, 31)])
def test_average_rank_cutoff_ties_refuse_real_evaluated_cohort(
    goal: GoalConfig, symbols: int, tail_tie: int, selected_count: int
) -> None:
    panel = _low_vol_panel(size=270, symbols=symbols)
    common = panel.bars[symbols - tail_tie].close.copy()
    tied = {
        symbol: (_bars(common.copy()) if i >= symbols - tail_tie else bars)
        for i, (symbol, bars) in enumerate(zip(panel.symbols, panel.bars, strict=True))
    }
    panel = _panel(tied)
    strategy = _parse(LOW_VOL)
    columns = evaluate_once(strategy, panel, default_registry())
    assert sum(columns.signals[s][252] == 1 for s in panel.symbols) == selected_count
    run = _run_span(strategy, panel, 252, 270, columns, goal)
    assert run.rebalance_events[0].status.value == "cardinality_mismatch"
    assert not run.accepted_signal_ids and not run.trades


def test_real_31_name_low_vol_card_runs_through_both_public_simulators(goal: GoalConfig) -> None:
    from icarus.engine.backtest import slice_panel

    full = _low_vol_panel(size=330)
    strategy = _parse(LOW_VOL)
    columns = evaluate_once(strategy, full, default_registry())
    panel = slice_panel(full, 252, 330)
    signals, stops, ranks, exits, pulses = columns.slice(252, 330)
    signal = SignalSimulator(
        notional_inr=Decimal("10000"),
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
        source_indices=range(252, 330),
    )
    portfolio = _run_span(strategy, full, 252, 330, columns, goal)
    assert [event.decision_index for event in signal.rebalance_events] == [252, 315]
    assert [event.decision_index for event in portfolio.rebalance_events] == [252, 315]
    assert len(signal.rebalance_events[0].holdings_after) == 30
    assert len(portfolio.rebalance_events[0].holdings_after) <= 4
    assert signal.trades and portfolio.trades


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
def test_real_donchian_entry_and_opposite_exit_execute_following_source_bar(
    goal: GoalConfig, mode: str
) -> None:
    from icarus.engine.backtest import slice_panel

    close = np.full(80, 100.0)
    close[55:75] = 110.0
    close[75:] = 107.0
    full = _panel({"AAA": _bars(close)})
    strategy = _parse(DONCHIAN)
    columns = evaluate_once(strategy, full, default_registry())
    if mode == "portfolio":
        portfolio = _run_span(strategy, full, 55, 80, columns, goal)
        assert portfolio.trades[0].reason is ExitReason.OPPOSITE_SIGNAL
        assert portfolio.trades[0].exit_ts == _portfolio_ts(full, 76)
        assert portfolio.management_exit_events[0].decision_index == 75
    else:
        panel = slice_panel(full, 55, 80)
        signals, stops, _ranks, exits, _pulses = columns.slice(55, 80)
        signal = SignalSimulator(
            notional_inr=Decimal("10000"),
            costs=CostModel(goal.costs),
            fills=FillModel(goal.execution_realism),
            stale_after_sessions=goal.backtest.stale_position_sessions,
        ).run(strategy, panel, signals, stops, source_indices=range(55, 80), exit_signals=exits)
        assert signal.trades[0].entry_index == 56
        assert signal.trades[0].exit_fragments[0].recognition_index == 76
        assert signal.trades[0].exit_fragments[0].reason is ExitReason.OPPOSITE_SIGNAL


def _portfolio_ts(panel: Panel, index: int) -> datetime:
    from icarus.engine.simcore import _ts_at

    return _ts_at(panel, index)


def test_fold_inherits_evaluated_full_source_axis_and_refuses_rebinding(goal: GoalConfig) -> None:
    panel = _low_vol_panel(size=320)
    source = tuple(range(100, 420))
    strategy = _parse(LOW_VOL)
    columns = evaluate_once(strategy, panel, default_registry(), source_indices=source)
    run = _run_span(strategy, panel, 200, 320, columns, goal)
    assert [event.decision_index for event in run.rebalance_events] == [315, 378]
    with pytest.raises(ValueError, match="source"):
        _run_span(strategy, panel, 200, 320, columns, goal, range(163, 483))


def test_nested_opposite_exit_participates_in_longest_lookback() -> None:
    from icarus.engine.backtest import longest_lookback

    strategy = _parse(DONCHIAN.replace("n: 20, basis", "n: 80, basis"))
    assert longest_lookback(strategy) == 80


@pytest.mark.parametrize("mode", ["signal", "portfolio"])
@pytest.mark.parametrize(
    "bad", ["missing", "symbols", "shape", "nonbinary", "infinite", "no_event"]
)
def test_declared_opposite_exit_refuses_malformed_columns(
    goal: GoalConfig, mode: str, bad: str
) -> None:
    from icarus.strategy.dsl import ExitRule

    panel = _flat_panel(("AAA",), 5)
    strategy = _parse(DONCHIAN)
    exits = {"AAA": np.zeros(5)}
    if bad == "symbols":
        exits = {"BBB": np.zeros(5)}
    elif bad == "shape":
        exits = {"AAA": np.zeros(4)}
    elif bad == "nonbinary":
        exits["AAA"][2] = 2.0
    elif bad == "infinite":
        exits["AAA"][2] = np.inf
    elif bad == "no_event":
        strategy = strategy.model_copy(
            update={"exits": (strategy.exits[0], ExitRule(rule="opposite_signal"))}
        )
    signals = {"AAA": np.array([1.0, 0.0, 0.0, 0.0, 0.0])}
    with pytest.raises(ValueError):
        if mode == "portfolio":
            _portfolio(goal).run(
                strategy,
                panel,
                signals,
                _stops(panel.symbols, len(panel)),
                starting_equity=Decimal("100000"),
                exit_signals=None if bad == "missing" else exits,
            )
        else:
            SignalSimulator(
                notional_inr=Decimal("10000"),
                costs=CostModel(goal.costs),
                fills=FillModel(goal.execution_realism),
                stale_after_sessions=goal.backtest.stale_position_sessions,
            ).run(
                strategy,
                panel,
                signals,
                _stops(panel.symbols, len(panel)),
                source_indices=range(len(panel)),
                exit_signals=None if bad == "missing" else exits,
            )


def test_queued_open_entry_cannot_borrow_a_slot_from_later_intrabar_stop(goal: GoalConfig) -> None:
    def accepted_after_current_low(low: float) -> tuple[str, ...]:
        symbols = tuple(f"S{index:02d}" for index in range(31))
        panel = _flat_panel(symbols, 7)
        panel.bars[0].low[3] = low
        signals = _signals(symbols, len(panel))
        ranks = _rank_columns(symbols, len(panel))
        for symbol in symbols[:30]:
            signals[symbol][0] = signals[symbol][2] = 1.0
        pulses = np.array([True, False, True, False, False, False, False])
        panel, signals, ranks, pulses, source, _ = _expand_rebalance_fixture(
            panel, signals, ranks, pulses
        )
        # Lower requested fixture risk isolates ordering from the unchanged heat veto.
        result = _portfolio(goal).run(
            _parse(LOW_VOL.replace("risk_r: 0.005", "risk_r: 0.004")),
            panel,
            signals,
            _stops(symbols, len(panel)),
            ranks=ranks,
            source_indices=source,
            rebalance_pulses=pulses,
            starting_equity=Decimal("100000"),
        )
        return tuple(
            signal.symbol for signal in result.accepted_signal_ids if signal.decision_index == 315
        )

    assert accepted_after_current_low(80.0) == accepted_after_current_low(99.0) == ()


@pytest.mark.parametrize("execution_close", [100.0, 140.0])
def test_carried_trailing_updates_refuse_queued_open_admissions(
    goal: GoalConfig, execution_close: float
) -> None:
    symbols = tuple(f"S{index:02d}" for index in range(31))
    panel = _flat_panel(symbols, 7)
    panel.bars[0].close[3] = execution_close
    panel.bars[0].high[3] = max(101.0, execution_close + 1.0)
    signals = _signals(symbols, len(panel))
    ranks = _rank_columns(symbols, len(panel))
    for symbol in symbols[:30]:
        signals[symbol][0] = signals[symbol][2] = 1.0
    signals["S00"][2] = 0.0
    signals["S30"][2] = 1.0
    pulses = np.array([True, False, True, False, False, False, False])
    panel, signals, ranks, pulses, source, _ = _expand_rebalance_fixture(
        panel, signals, ranks, pulses
    )
    strategy = _parse(LOW_VOL.replace("stop_loss_atr:", "trailing_stop_atr:"))
    result = _portfolio(goal).run(
        strategy,
        panel,
        signals,
        _stops(symbols, len(panel)),
        ranks=ranks,
        rebalance_pulses=pulses,
        source_indices=source,
        starting_equity=Decimal("100000"),
    )
    assert not [item for item in result.accepted_signal_ids if item.decision_index == 315]
    refusal = result.rebalance_events[1].admission_refusal
    assert refusal is not None and refusal.value == "execution_order_unavailable"


def test_final_stale_residual_cannot_fund_queued_open_admission(goal: GoalConfig) -> None:
    symbols = tuple(f"S{index:02d}" for index in range(31))
    panel = _flat_panel(symbols, 4)
    panel.bars[0].volume[3] = 1.0
    signals = _signals(symbols, len(panel))
    ranks = _rank_columns(symbols, len(panel))
    for symbol in symbols[:30]:
        signals[symbol][0] = signals[symbol][2] = 1.0
    signals["S00"][2] = 0.0
    signals["S30"][2] = 1.0
    pulses = np.array([True, False, True, False])
    panel, signals, ranks, pulses, source, _ = _expand_rebalance_fixture(
        panel, signals, ranks, pulses
    )
    result = _portfolio(goal).run(
        _parse(LOW_VOL),
        panel,
        signals,
        _stops(symbols, len(panel)),
        ranks=ranks,
        rebalance_pulses=pulses,
        source_indices=source,
        starting_equity=Decimal("100000"),
    )
    assert result.stale_marks == 1
    assert not [item for item in result.accepted_signal_ids if item.decision_index == 315]
    refusal = result.rebalance_events[1].admission_refusal
    assert refusal is not None and refusal.value == "execution_order_unavailable"


def test_gap_protective_fill_can_free_a_known_open_slot_for_new_admission(goal: GoalConfig) -> None:
    symbols = tuple(f"S{index:02d}" for index in range(31))
    panel = _flat_panel(symbols, 7)
    panel.bars[0].open[3] = 80.0
    panel.bars[0].low[3] = 79.0
    signals = _signals(symbols, len(panel))
    ranks = _rank_columns(symbols, len(panel))
    for symbol in symbols[:30]:
        signals[symbol][0] = signals[symbol][2] = 1.0
    pulses = np.array([True, False, True, False, False, False, False])
    panel, signals, ranks, pulses, source, _ = _expand_rebalance_fixture(
        panel, signals, ranks, pulses
    )
    result = _portfolio(goal).run(
        _parse(LOW_VOL.replace("risk_r: 0.005", "risk_r: 0.004")),
        panel,
        signals,
        _stops(symbols, len(panel)),
        ranks=ranks,
        rebalance_pulses=pulses,
        source_indices=source,
        starting_equity=Decimal("100000"),
    )
    assert tuple(
        item.symbol for item in result.accepted_signal_ids if item.decision_index == 315
    ) == ("S04",)
    assert result.rebalance_events[1].admission_refusal is None


@pytest.mark.parametrize("ordering", ["intrabar", "trailing", "missing", "target", "stale"])
def test_signal_mode_reports_ambiguous_queued_admission_refusal(
    goal: GoalConfig, ordering: str
) -> None:
    symbols = tuple(f"S{index:02d}" for index in range(31))
    size = 4 if ordering == "stale" else 7
    panel = _flat_panel(symbols, size)
    text = LOW_VOL
    if ordering == "intrabar":
        panel.bars[0].low[3] = 80.0
    elif ordering == "trailing":
        text = text.replace("stop_loss_atr:", "trailing_stop_atr:")
    elif ordering == "missing":
        panel.bars[0].open[3] = np.nan
    elif ordering == "target":
        panel.bars[0].high[3] = 102.0
        text = text.replace("sizing:", "  - take_profit_r: {r_multiple: 0.1}\nsizing:")
    else:
        panel.bars[0].volume[3] = 1.0
    signals = _signals(symbols, size)
    ranks = _rank_columns(symbols, size)
    for symbol in symbols[:30]:
        signals[symbol][0] = signals[symbol][2] = 1.0
    signals["S00"][2] = 0.0
    signals["S30"][2] = 1.0
    pulses = np.zeros(size, dtype=np.bool_)
    pulses[[0, 2]] = True
    panel, signals, ranks, pulses, source, _ = _expand_rebalance_fixture(
        panel, signals, ranks, pulses
    )
    result = SignalSimulator(
        notional_inr=Decimal("10000"),
        costs=CostModel(goal.costs),
        fills=FillModel(goal.execution_realism),
        stale_after_sessions=goal.backtest.stale_position_sessions,
    ).run(
        _parse(text),
        panel,
        signals,
        _stops(symbols, len(panel)),
        ranks=ranks,
        source_indices=source,
        rebalance_pulses=pulses,
    )
    refusal = result.rebalance_events[1].admission_refusal
    assert refusal is not None and refusal.value == "execution_order_unavailable"
    skipped = [skip for skip in result.skips if skip.signal_id.symbol == "S30"]
    assert len(skipped) == 1 and skipped[0].reason.value == "execution_order_unavailable"
    assert not [trade for trade in result.trades if trade.signal_id.symbol == "S30"]
