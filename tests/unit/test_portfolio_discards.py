"""Synthetic accounting witnesses for portfolio entry signals."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, cast

import numpy as np
import numpy.typing as npt
import pytest
from tests.unit.simharness import REALISM, simulator

from icarus.common.config import load_goal
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel
from icarus.engine.portfolio import (
    PortfolioDiscard,
    PortfolioOmission,
    PortfolioSimulator,
    RunResult,
    Skipped,
)
from icarus.engine.simcore import SignalId
from icarus.strategy.dsl import Bars, Panel, StrategyCandidate, parse_strategy
from icarus.strategy.library import default_registry

if TYPE_CHECKING:
    from icarus.common.config import GoalConfig


_START = np.datetime64("2024-01-01")
Column = npt.NDArray[np.float64]
BoolColumn = npt.NDArray[np.bool_]
_STRATEGY = """
name: discard_probe
version: 1
timeframe: 1d
universe: synthetic
entry: {structure_bullish: {k: 2}}
exit:
  - stop_loss_pct: {pct: 0.1}
sizing:
  risk_r: 0.005
"""


@pytest.fixture
def goal(repo_root: Path) -> GoalConfig:
    return load_goal(repo_root / "goal.yaml")


def _strategy() -> StrategyCandidate:
    return parse_strategy(_STRATEGY, registry=default_registry(), max_risk_r=0.005)


def _panel(
    symbols: tuple[str, ...],
    *,
    size: int = 6,
    price: float = 100.0,
    volumes: dict[str, list[float]] | None = None,
    tradable: dict[str, list[bool]] | None = None,
    missing: dict[str, set[int]] | None = None,
) -> Panel:
    bars: dict[str, Bars] = {}
    membership: dict[str, BoolColumn] = {}
    for symbol in symbols:
        close = np.full(size, price, dtype=np.float64)
        if missing and symbol in missing:
            close[list(missing[symbol])] = np.nan
        bars[symbol] = Bars(
            ts=np.arange(_START, _START + size).astype("datetime64[ns]"),
            open=close.copy(),
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=np.array(
                volumes.get(symbol, [1_000_000.0] * size) if volumes else [1_000_000.0] * size,
                dtype=np.float64,
            ),
        )
        membership[symbol] = np.array(
            tradable.get(symbol, [True] * size) if tradable else [True] * size,
            dtype=np.bool_,
        )
    return Panel.build(bars, membership)


def _columns(
    symbols: tuple[str, ...], size: int, fires: dict[str, tuple[int, ...]], stop: float = 10.0
) -> tuple[dict[str, Column], dict[str, Column]]:
    signals = {symbol: np.zeros(size, dtype=np.float64) for symbol in symbols}
    for symbol, indices in fires.items():
        signals[symbol][list(indices)] = 1.0
    stops = {symbol: np.full(size, stop, dtype=np.float64) for symbol in symbols}
    return signals, stops


def _run(
    sim: PortfolioSimulator,
    panel: Panel,
    fires: dict[str, tuple[int, ...]],
    *,
    stop: float = 10.0,
    ranks: dict[str, Column] | None = None,
    source_indices: tuple[int, ...] | None = None,
) -> RunResult:
    signals, stops = _columns(tuple(panel.symbols), len(panel), fires, stop)
    return sim.run(
        _strategy(),
        panel,
        signals,
        stops,
        starting_equity=Decimal(100_000),
        ranks=ranks,
        source_indices=source_indices,
    )


def _signal_id(index: int, symbol: str = "AAA") -> SignalId:
    return SignalId(
        strategy_id="discard_probe",
        strategy_version=1,
        symbol=symbol,
        decision_ts=datetime(2024, 1, index + 1, tzinfo=UTC),
        decision_index=index,
    )


@pytest.mark.parametrize(
    ("signal_id", "reason"),
    [
        (object(), Skipped.NO_SLOT),
        (_signal_id(0), object()),
    ],
)
def test_portfolio_discard_rejects_untyped_identity_or_reason(
    signal_id: object, reason: object
) -> None:
    """A malformed record must halt before it can poison the per-signal partition."""
    with pytest.raises(TypeError, match="PortfolioDiscard"):
        PortfolioDiscard(signal_id, reason)  # type: ignore[arg-type]


def test_reconciliation_requires_every_emitted_signal_to_have_one_outcome() -> None:
    """Dropping one discard append must fail rather than undercount emitted signals."""
    accepted = _signal_id(0)
    omitted = _signal_id(1, "BBB")
    result = RunResult(accepted_signal_ids=[accepted])
    result.record_discard(PortfolioDiscard(omitted, PortfolioOmission.NO_NEXT_BAR))

    result.reconcile_signals({accepted, omitted})

    assert result.emitted_signals == 2
    assert result.accepted_signal_ids == [accepted]
    assert result.portfolio_discards == [PortfolioDiscard(omitted, PortfolioOmission.NO_NEXT_BAR)]
    assert result.skipped == {}


def test_no_execution_bar_preserves_the_historical_skip_projection() -> None:
    """Splitting missing execution data must not change the old no-stop-distance count."""
    missing = _signal_id(0)
    result = RunResult()
    result.record_discard(PortfolioDiscard(missing, PortfolioOmission.NO_EXECUTION_BAR))
    result.reconcile_signals({missing})

    assert result.skipped == {Skipped.NO_STOP_DISTANCE: 1}


@pytest.mark.parametrize("bad_outcomes", ["duplicate", "overlap", "invented", "missing"])
def test_reconciliation_rejects_non_bijective_signal_accounting(bad_outcomes: str) -> None:
    """Counts alone can hide one invented ID and one omitted ID; exact sets cannot."""
    first = _signal_id(0)
    second = _signal_id(1, "BBB")
    result = RunResult()
    expected = {first, second}

    if bad_outcomes == "duplicate":
        result.portfolio_discards.extend(
            [
                PortfolioDiscard(first, Skipped.NO_SLOT),
                PortfolioDiscard(first, Skipped.NO_SLOT),
            ]
        )
        result.skipped[Skipped.NO_SLOT] = 2
    elif bad_outcomes == "overlap":
        result.accepted_signal_ids.append(first)
        result.portfolio_discards.append(PortfolioDiscard(first, Skipped.NO_SLOT))
        result.skipped[Skipped.NO_SLOT] = 1
    elif bad_outcomes == "invented":
        result.accepted_signal_ids.extend([first, _signal_id(2, "CCC")])
    else:
        result.accepted_signal_ids.append(first)

    with pytest.raises(ValueError, match="signal accounting"):
        result.reconcile_signals(expected)


# --------------------------------------------------------------------------------------
# The simulator observes every emitted entry signal without moving a trading decision.
# --------------------------------------------------------------------------------------


def _observations(result: RunResult) -> list[tuple[str, int, str]]:
    return [
        (discard.signal_id.symbol, discard.signal_id.decision_index, discard.reason.value)
        for discard in result.portfolio_discards
    ]


def test_untradable_and_final_bar_signals_are_observed_with_fixed_precedence(
    goal: GoalConfig,
) -> None:
    """Filtering membership or checking it before the final bar would silently lose these."""
    panel = _panel(
        ("AAA", "BBB"),
        size=4,
        tradable={"AAA": [False, True, True, True], "BBB": [True, True, True, False]},
    )
    result = _run(simulator(goal), panel, {"AAA": (0,), "BBB": (3,)})

    assert _observations(result) == [
        ("AAA", 0, "not_tradable"),
        ("BBB", 3, "no_next_bar"),
    ]
    assert result.emitted_signals == 2
    assert result.skipped == {}


def test_an_already_held_repeat_signal_has_its_own_id(goal: GoalConfig) -> None:
    """Removing the held-symbol pass would double-enter or omit the repeat decision."""
    result = _run(simulator(goal), _panel(("AAA",)), {"AAA": (0, 1)})

    assert _observations(result) == [("AAA", 1, "already_held")]
    assert [signal.decision_index for signal in result.accepted_signal_ids] == [0]


def test_both_no_slot_sites_record_the_actual_signal(goal: GoalConfig) -> None:
    """A full book and rank-loop exhaustion are distinct branches with the same legacy reason."""
    already_full = _run(
        simulator(goal, slots=1),
        _panel(("AAA", "BBB")),
        {"AAA": (0,), "BBB": (1,)},
    )
    ranks = {
        "AAA": np.full(6, 2.0, dtype=np.float64),
        "BBB": np.full(6, 1.0, dtype=np.float64),
    }
    exhausted = _run(
        simulator(goal, slots=1),
        _panel(("AAA", "BBB")),
        {"AAA": (0,), "BBB": (0,)},
        ranks=ranks,
    )

    assert _observations(already_full) == [("BBB", 1, "no_slot")]
    assert _observations(exhausted) == [("BBB", 0, "no_slot")]


def test_no_slot_precedes_an_unreachable_missing_execution_bar(goal: GoalConfig) -> None:
    """Inspecting a refused loser would rewrite actual selection as missing market data."""
    panel = _panel(("AAA", "BBB"), missing={"BBB": {1}})
    ranks = {
        "AAA": np.full(6, 2.0, dtype=np.float64),
        "BBB": np.full(6, 1.0, dtype=np.float64),
    }
    result = _run(simulator(goal, slots=1), panel, {"AAA": (0,), "BBB": (0,)}, ranks=ranks)

    assert _observations(result) == [("BBB", 0, "no_slot")]


def test_missing_execution_bar_is_split_from_invalid_stop_without_changing_legacy_count(
    goal: GoalConfig,
) -> None:
    """Combining these observations would prevent later diagnosis of market-data timing."""
    missing = _run(
        simulator(goal),
        _panel(("AAA",), missing={"AAA": {1}}),
        {"AAA": (0,)},
    )
    panel = _panel(("AAA",))
    signals, stops = _columns(("AAA",), len(panel), {"AAA": (0,)})
    stops["AAA"][0] = np.nan
    invalid = simulator(goal).run(
        _strategy(),
        panel,
        signals,
        stops,
        starting_equity=Decimal(100_000),
    )

    assert _observations(missing) == [("AAA", 0, "no_execution_bar")]
    assert _observations(invalid) == [("AAA", 0, "no_stop_distance")]
    assert missing.skipped == invalid.skipped == {Skipped.NO_STOP_DISTANCE: 1}


def test_remaining_legacy_reasons_are_recorded_at_their_existing_decision_sites(
    goal: GoalConfig,
) -> None:
    """Moving any guard can change which refusal wins; each literal pins the current order."""
    rounds = _run(simulator(goal), _panel(("AAA",)), {"AAA": (0,)}, stop=600.0)
    concentration = _run(
        simulator(goal), _panel(("AAA",), price=30_000.0), {"AAA": (0,)}, stop=100.0
    )
    heat_risk = goal.risk.model_copy(update={"max_portfolio_heat": 0.004})
    heat = _run(
        PortfolioSimulator(
            risk=heat_risk,
            costs=CostModel(goal.costs),
            fills=FillModel(REALISM),
            stale_after_sessions=20,
        ),
        _panel(("AAA",)),
        {"AAA": (0,)},
    )
    no_fill = _run(
        simulator(goal),
        _panel(
            ("AAA",),
            volumes={"AAA": [1_000_000.0, 0.0, 1_000_000.0, 1_000_000.0, 1_000_000.0, 1_000_000.0]},
        ),
        {"AAA": (0,)},
    )
    no_cash = _run(
        simulator(goal, position_pct=1.0),
        _panel(("AAA",)),
        {"AAA": (0,)},
        stop=0.5005,
    )

    assert _observations(rounds) == [("AAA", 0, "rounds_to_zero")]
    assert _observations(concentration) == [("AAA", 0, "concentration_cap")]
    assert _observations(heat) == [("AAA", 0, "heat_cap")]
    assert _observations(no_fill) == [("AAA", 0, "entry_not_filled")]
    assert _observations(no_cash) == [("AAA", 0, "insufficient_cash")]
    assert no_cash.accepted_signal_ids == [], "acceptance must occur after the cash gate"


def test_partial_entry_and_fragmented_exit_still_count_one_accepted_signal(
    goal: GoalConfig,
) -> None:
    """Counting ClosedTrade rows would turn one position into several accepted decisions."""
    panel = _panel(
        ("AAA",),
        size=6,
        volumes={"AAA": [1_000_000.0, 400.0, 100.0, 100.0, 100.0, 1_000_000.0]},
    )
    # Entry volume caps the 50-share request to 20. Falling bars then drain it in partial exits.
    bars = panel.bars[0]
    falling = Bars(
        ts=bars.ts,
        open=np.array([100.0, 100.0, 80.0, 80.0, 80.0, 80.0]),
        high=np.array([101.0, 101.0, 81.0, 81.0, 81.0, 81.0]),
        low=np.array([99.0, 99.0, 79.0, 79.0, 79.0, 79.0]),
        close=np.array([100.0, 100.0, 80.0, 80.0, 80.0, 80.0]),
        volume=bars.volume,
    )
    panel = Panel.build({"AAA": falling}, {"AAA": np.ones(6, dtype=np.bool_)})
    result = _run(simulator(goal), panel, {"AAA": (0,)})

    assert len(result.trades) > 1
    assert len(result.accepted_signal_ids) == 1
    assert result.emitted_signals == 1


def test_a_signal_after_the_first_position_closes_is_a_new_acceptance(goal: GoalConfig) -> None:
    """Treating a symbol as permanently held would discard a legitimate later decision."""
    bars = Bars(
        ts=np.arange(_START, _START + 6).astype("datetime64[ns]"),
        open=np.array([100.0, 100.0, 80.0, 100.0, 100.0, 100.0]),
        high=np.array([101.0, 101.0, 81.0, 101.0, 101.0, 101.0]),
        low=np.array([99.0, 99.0, 79.0, 99.0, 99.0, 99.0]),
        close=np.array([100.0, 100.0, 80.0, 100.0, 100.0, 100.0]),
        volume=np.full(6, 1_000_000.0),
    )
    panel = Panel.build({"AAA": bars}, {"AAA": np.ones(6, dtype=np.bool_)})
    result = _run(simulator(goal), panel, {"AAA": (0, 2)})

    assert [signal.decision_index for signal in result.accepted_signal_ids] == [0, 2]
    assert result.portfolio_discards == []


@pytest.mark.parametrize(
    "source_indices",
    [
        (10, 12, 13, 14, 15, 16),
        (10, 11, 12, 13, 14),
        (-1, 0, 1, 2, 3, 4),
        (True, 1, 2, 3, 4, 5),
    ],
)
def test_source_indices_must_be_contiguous_nonnegative_integers(
    goal: GoalConfig, source_indices: tuple[object, ...]
) -> None:
    """A malformed source coordinate must fail before it can mint an ambiguous signal ID."""
    with pytest.raises(ValueError, match="source_indices"):
        _run(
            simulator(goal),
            _panel(("AAA",)),
            {"AAA": (0,)},
            source_indices=cast(tuple[int, ...], source_indices),
        )


def test_run_end_reconciliation_detects_a_suppressed_discard_append(
    goal: GoalConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A missing observation must fail even if all legacy money-path state is unchanged."""
    original = RunResult.record_discard

    def suppress_not_tradable(self: RunResult, discard: PortfolioDiscard) -> None:
        if discard.reason is not PortfolioOmission.NOT_TRADABLE:
            original(self, discard)

    monkeypatch.setattr(RunResult, "record_discard", suppress_not_tradable)
    panel = _panel(("AAA",), tradable={"AAA": [False, True, True, True, True, True]})

    with pytest.raises(ValueError, match="signal accounting"):
        _run(simulator(goal), panel, {"AAA": (0,)})
