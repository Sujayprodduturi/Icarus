"""Synthetic contract checks for the first-batch breadth candidates.

These fixtures prove mechanics only.  They do not load a market panel, estimate performance, or
write to the counted trial ledger.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from uuid import uuid4

import numpy as np
import numpy.typing as npt
import pytest

from icarus.common.config import GoalConfig, load_goal
from icarus.common.types import OrderSide
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel, Intent, NoFillReason, OrderKind, SimBar
from icarus.engine.portfolio import ExitReason, PortfolioSimulator, Skipped
from icarus.engine.runner import evaluate_once
from icarus.state.trial_ledger import (
    EvaluationReservation,
    TrialBatchReservation,
    TrialKind,
    TrialOrigin,
)
from icarus.strategy.dsl import (
    Bars,
    DslError,
    Panel,
    StrategyCandidate,
    evaluate_universe,
    parse_strategy,
)
from icarus.strategy.library import cross_sectional, default_registry

START = np.datetime64("2020-01-01")
MOMENTUM_FILE = "xs_momentum_252_skip21.yaml"
PULLBACK_FILE = "uptrend_pullback_3.yaml"


@pytest.fixture
def goal(repo_root: Path) -> GoalConfig:
    return load_goal(repo_root / "goal.yaml")


def _load(repo_root: Path, filename: str) -> StrategyCandidate:
    return parse_strategy(
        (repo_root / "strategies" / filename).read_text(),
        registry=default_registry(),
        max_risk_r=0.005,
    )


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


def _panel(
    bars: dict[str, Bars], tradable: dict[str, npt.NDArray[np.bool_]] | None = None
) -> Panel:
    size = len(next(iter(bars.values())))
    membership = (
        {symbol: np.ones(size, dtype=np.bool_) for symbol in bars} if tradable is None else tradable
    )
    return Panel.build(bars, membership)


def _momentum_panel(scores: list[float], *, size: int = 325) -> Panel:
    bars: dict[str, Bars] = {}
    for index, score in enumerate(scores):
        close = np.full(size, 100.0)
        close[231:] = 100.0 * (1.0 + score / 100.0)
        bars[f"S{index:02d}"] = _bars(close)
    return _panel(bars)


def _sim(goal: GoalConfig) -> PortfolioSimulator:
    return PortfolioSimulator(
        risk=goal.risk,
        costs=CostModel(goal.costs),
        fills=FillModel(goal.execution_realism),
        stale_after_sessions=goal.backtest.stale_position_sessions,
    )


def _pullback_panel(*, streak: int = 3, ibs: float = 0.1, trend_delta: float = 0.2) -> Panel:
    size = 220
    close = np.full(size, 197.0)
    event = 204
    close[event - streak : event + 1] = np.arange(197.0 + streak, 196.0, -1.0, dtype=np.float64)
    # Cancel the streak's excess over 197 so the final 200-bar mean equals the event close.
    # Lowering one old observation by trend_delta makes the comparison strictly true without
    # changing the recent streak.
    close[event - 199] = 197.0 - sum(range(1, streak + 1)) - trend_delta
    high = close + 5.0
    low = close - 5.0
    if ibs == 0.2:
        low[event], high[event] = 190.0, 225.0
    elif ibs == 0.1:
        low[event], high[event] = 196.0, 206.0
    elif np.isnan(ibs):
        low[event] = high[event] = close[event]
    else:
        raise AssertionError("fixture supports only the reviewed IBS boundaries")
    return _panel({"PULL": _bars(close, high=high, low=low)})


def test_exact_reviewed_cards_parse_and_unknown_fields_are_refused(repo_root: Path) -> None:
    momentum = _load(repo_root, MOMENTUM_FILE)
    pullback = _load(repo_root, PULLBACK_FILE)

    assert (momentum.name, momentum.version, momentum.timeframe, momentum.universe) == (
        "xs_momentum_252_21",
        1,
        "1d",
        "nse_liquid",
    )
    assert momentum.primitives_used() == frozenset({"xs_top_n", "roc_skip"})
    assert [(rule.rule, rule.literals) for rule in momentum.exits] == [
        ("stop_loss_atr", {"atr_mult": 3.0, "atr_period": 14}),
        ("time_stop", {"bars": 63}),
    ]
    assert (momentum.sizing.risk_r, momentum.sizing.weighting) == (0.005, "equal_weight")

    assert (pullback.name, pullback.version, pullback.timeframe, pullback.universe) == (
        "short_term_reversal_uptrend",
        1,
        "1d",
        "nse_liquid",
    )
    assert pullback.primitives_used() == frozenset(
        {"above", "below", "close", "constant", "down_streak", "internal_bar_strength", "sma"}
    )
    assert [(rule.rule, rule.literals) for rule in pullback.exits] == [
        ("stop_loss_atr", {"atr_mult": 2.0, "atr_period": 14}),
        ("time_stop", {"bars": 5}),
    ]
    assert pullback.rank_by is not None and pullback.rank_by.primitive == "down_streak"

    invalid = (repo_root / "strategies" / PULLBACK_FILE).read_text() + "\ncooldown: 3\n"
    with pytest.raises(DslError, match="unknown top-level keys"):
        parse_strategy(invalid, registry=default_registry(), max_risk_r=0.005)


def test_existing_cards_keep_their_reviewed_byte_identities(repo_root: Path) -> None:
    expected = {
        "baseline_buy_and_hold.yaml": (
            "b1bded2f21c1817adced9d4e789ae79f5e9058e433827276d0d1e434c1fd721e"
        ),
        "donlevey_sweep_reclaim.yaml": (
            "a39f9d507b16550b1bcf4a4997abd1ba73643fcf8b52b2aec4ea036a3bdfb295"
        ),
        "xs_momentum_20.yaml": "8905d1162d1fea9d2194e0a39312e2512b726b24db4b06f5d20fc5533614d725",
    }
    for filename, digest in expected.items():
        assert (
            hashlib.sha256((repo_root / "strategies" / filename).read_bytes()).hexdigest() == digest
        )


def test_new_card_hashes_and_versions_form_a_native_reservation(repo_root: Path) -> None:
    for filename in (MOMENTUM_FILE, PULLBACK_FILE):
        strategy = _load(repo_root, filename)
        digest = hashlib.sha256((repo_root / "strategies" / filename).read_bytes()).hexdigest()
        reservation = TrialBatchReservation(
            run_group_id=uuid4(),
            origin=TrialOrigin.OPERATOR,
            strategy_name=strategy.name,
            strategy_version=strategy.version,
            strategy_sha256=digest,
            panel_sha256="1" * 64,
            config_sha256="2" * 64,
            primitives=tuple(sorted(strategy.primitives_used())),
            evaluations=(
                EvaluationReservation(
                    ordinal=0,
                    kind=TrialKind.PORTFOLIO,
                    fold_index=None,
                    start_index=0,
                    end_index_exclusive=2,
                    start_ts=datetime(2020, 1, 1, tzinfo=UTC),
                    end_ts=datetime(2020, 1, 2, tzinfo=UTC),
                    reset_identity="walk_forward_portfolio_v1",
                ),
            ),
        )
        assert (
            reservation.strategy_name,
            reservation.strategy_version,
            reservation.strategy_sha256,
        ) == (
            strategy.name,
            strategy.version,
            digest,
        )


def test_roc_skip_is_causal_scale_free_and_matches_the_card_formula(repo_root: Path) -> None:
    strategy = _load(repo_root, MOMENTUM_FILE)
    assert strategy.rank_by is not None
    close = np.linspace(10.0, 40.0, 254)
    bars = _bars(close)
    scaled = _bars(close * 10.0)
    registry = default_registry()
    observed = registry.get("roc_skip").compute(bars, n=252, skip=21)
    observed_scaled = registry.get("roc_skip").compute(scaled, n=252, skip=21)
    expected = (close[231] - close[0]) / close[0] * 100.0

    assert np.isnan(observed[251])
    assert observed[252] == pytest.approx(expected)
    assert observed_scaled[252] == pytest.approx(expected)
    changed_future = close.copy()
    changed_future[253] = 1_000_000.0
    future_observed = registry.get("roc_skip").compute(_bars(changed_future), n=252, skip=21)
    assert future_observed[252] == observed[252]


@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_cross_sectional_eligibility_excludes_every_nonfinite_value(bad: float) -> None:
    panel = _momentum_panel([float(index) for index in range(20)], size=1)
    values = np.arange(20, dtype=np.float64).reshape(20, 1)
    values[0, 0] = bad
    assert not cross_sectional._eligible(panel, values, 20).any()


@pytest.mark.parametrize("endpoint", [1e307, -1e307])
def test_roc_skip_overflow_cannot_enter_or_satisfy_the_floor(
    repo_root: Path, endpoint: float
) -> None:
    strategy = _load(repo_root, MOMENTUM_FILE)
    bars = {}
    for index in range(20):
        close = np.ones(253, dtype=np.float64)
        close[231:] = 1.0 + index / 100.0
        if index == 0:
            close[231:] = endpoint
        bars[f"S{index:02d}"] = _bars(close, high=close.copy(), low=close.copy())
    with np.errstate(over="ignore"):
        signals = evaluate_universe(strategy.entry, _panel(bars), default_registry())
    assert all(np.isnan(column[252]) for column in signals.values())


def test_momentum_masks_membership_missing_scores_and_a_thin_universe(repo_root: Path) -> None:
    strategy = _load(repo_root, MOMENTUM_FILE)
    registry = default_registry()
    thin = evaluate_universe(strategy.entry, _momentum_panel(list(range(19))), registry)
    assert all(np.isnan(column[252]) for column in thin.values())

    panel = _momentum_panel(list(range(22)))
    tradable = {symbol: np.ones(len(panel), dtype=np.bool_) for symbol in panel.symbols}
    tradable["S20"][252] = False
    close = panel.bars[19].close.copy()
    close[0] = np.nan
    bars = {symbol: series for symbol, series in zip(panel.symbols, panel.bars, strict=True)}
    bars["S19"] = _bars(close)
    signals = evaluate_universe(strategy.entry, _panel(bars, tradable), registry)
    assert np.isnan(signals["S19"][252]) and np.isnan(signals["S20"][252])
    assert sum(column[252] == 1.0 for column in signals.values()) == 10


@pytest.mark.parametrize(
    ("scores", "expected"),
    [
        ([100.0 - i for i in range(8)] + [90.0] * 3 + [80.0 - i for i in range(9)], 11),
        ([100.0 - i for i in range(9)] + [90.0] * 2 + [80.0 - i for i in range(9)], 9),
    ],
)
def test_momentum_cutoff_ties_pin_average_rank_cohort_sizes(
    repo_root: Path, scores: list[float], expected: int
) -> None:
    strategy = _load(repo_root, MOMENTUM_FILE)
    signals = evaluate_universe(strategy.entry, _momentum_panel(scores), default_registry())
    assert sum(column[252] == 1.0 for column in signals.values()) == expected


@pytest.mark.parametrize(
    ("panel", "expected"),
    [
        (_pullback_panel(trend_delta=0.0), False),
        (_pullback_panel(streak=2), False),
        (_pullback_panel(streak=3), True),
        (_pullback_panel(streak=4), True),
        (_pullback_panel(ibs=0.2), False),
        (_pullback_panel(ibs=0.1), True),
        (_pullback_panel(ibs=np.nan), None),
    ],
)
def test_pullback_boundaries_are_strict(
    repo_root: Path, panel: Panel, expected: bool | None
) -> None:
    strategy = _load(repo_root, PULLBACK_FILE)
    value = evaluate_universe(strategy.entry, panel, default_registry())["PULL"][204]
    if expected is None:
        assert np.isnan(value)
    else:
        assert bool(value) is expected


def test_momentum_time_exit_reenters_without_pyramiding_and_counts_entry_bar(
    repo_root: Path, goal: GoalConfig
) -> None:
    strategy = _load(repo_root, MOMENTUM_FILE)
    panel = _momentum_panel([float(index) for index in range(20)], size=325)
    columns = evaluate_once(strategy, panel, default_registry())
    result = _sim(goal).run(
        strategy,
        panel,
        columns.signals,
        columns.stops,
        ranks=columns.ranks,
        starting_equity=Decimal("1000000"),
    )

    timed = [trade for trade in result.trades if trade.reason is ExitReason.TIME_STOP]
    assert timed
    first = timed[0]
    assert (first.exit_ts - first.entry_ts).days == 62
    assert result.skipped[Skipped.ALREADY_HELD] > 0
    same_symbol = sorted(
        (trade for trade in result.trades if trade.symbol == first.symbol),
        key=lambda trade: trade.entry_ts,
    )
    assert len(same_symbol) >= 2
    assert same_symbol[1].entry_ts > first.exit_ts
    assert same_symbol[0].costs > 0 and same_symbol[1].costs > 0


def test_positive_pullback_fixture_uses_next_bar_one_position_and_five_bar_exit(
    repo_root: Path, goal: GoalConfig
) -> None:
    strategy = _load(repo_root, PULLBACK_FILE)
    panel = _pullback_panel()
    columns = evaluate_once(strategy, panel, default_registry())
    result = _sim(goal).run(
        strategy,
        panel,
        columns.signals,
        columns.stops,
        ranks=columns.ranks,
        starting_equity=Decimal("1000000"),
    )
    trade = result.trades[0]
    assert trade.entry_ts == datetime(2020, 7, 24, tzinfo=UTC)
    assert trade.reason is ExitReason.TIME_STOP
    assert (trade.exit_ts - trade.entry_ts).days == 4


def test_stop_distance_and_fill_model_keep_protective_and_resting_orders_distinct(
    repo_root: Path, goal: GoalConfig
) -> None:
    strategy = _load(repo_root, PULLBACK_FILE)
    panel = _pullback_panel()
    registry = default_registry()
    columns = evaluate_once(strategy, panel, registry)
    atr = registry.get("atr").compute(panel.bars[0], n=14)
    assert columns.stops["PULL"][204] == pytest.approx(2.0 * atr[204])

    fills = FillModel(goal.execution_realism)
    decided = datetime(2020, 1, 1, tzinfo=UTC)
    at = datetime(2020, 1, 2, tzinfo=UTC)
    touch = SimBar(
        ts=at,
        open=Decimal("100"),
        high=Decimal("101"),
        low=Decimal("95"),
        close=Decimal("100"),
        volume=Decimal("1000000"),
    )
    stop = fills.execute(Intent(OrderSide.SELL, OrderKind.STOP, 1, decided, Decimal("95")), touch)
    resting = fills.execute(
        Intent(OrderSide.BUY, OrderKind.RESTING_LIMIT, 1, decided, Decimal("95")), touch
    )
    assert stop.filled
    assert not resting.filled and resting.reason is NoFillReason.NOT_TRADED_THROUGH


def test_protective_stop_can_close_on_the_entry_session(repo_root: Path, goal: GoalConfig) -> None:
    strategy = _load(repo_root, PULLBACK_FILE)
    close = np.array([100.0, 95.0, 95.0])
    panel = _panel(
        {
            "PULL": _bars(
                close,
                open_=np.array([100.0, 100.0, 95.0]),
                high=np.array([101.0, 101.0, 96.0]),
                low=np.array([99.0, 89.0, 94.0]),
            )
        }
    )
    result = _sim(goal).run(
        strategy,
        panel,
        signals={"PULL": np.array([1.0, 0.0, 0.0])},
        stops={"PULL": np.full(3, 10.0)},
        starting_equity=Decimal("1000000"),
    )
    trade = result.trades[0]
    assert trade.reason is ExitReason.STOP_LOSS
    assert trade.exit_ts == trade.entry_ts


def test_gap_through_protective_stop_fills_at_the_worse_open(
    repo_root: Path, goal: GoalConfig
) -> None:
    strategy = _load(repo_root, PULLBACK_FILE)
    close = np.array([100.0, 100.0, 80.0, 80.0])
    panel = _panel(
        {
            "PULL": _bars(
                close,
                open_=np.array([100.0, 100.0, 80.0, 80.0]),
                high=np.array([101.0, 101.0, 81.0, 81.0]),
                low=np.array([99.0, 95.0, 79.0, 79.0]),
            )
        }
    )
    result = _sim(goal).run(
        strategy,
        panel,
        signals={"PULL": np.array([1.0, 0.0, 0.0, 0.0])},
        stops={"PULL": np.full(4, 10.0)},
        starting_equity=Decimal("1000000"),
    )
    trade = result.trades[0]
    expected = FillModel(goal.execution_realism).marketable_price(
        Decimal("80"), side=OrderSide.SELL
    )
    assert trade.reason is ExitReason.STOP_LOSS
    assert trade.exit_price == expected
    assert trade.exit_price < trade.entry_price - Decimal("10")
