"""The walk-forward runner — task 1.7d.

These pin the joins, not the parts: the parts have their own suites. What can only go wrong once
things are wired together is (a) the warm-up prefix leaking into the tradable region, (b) folds
being stitched by addition instead of compounding, (c) the exposure numerator being counted on a
different axis from its denominator, and (d) a run not reaching the trial ledger.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
import pytest

from icarus.common.config import load_goal
from icarus.engine.costmodel import Charges
from icarus.engine.metrics import Metrics, SharpeEstimate
from icarus.engine.portfolio import ClosedTrade, ExitReason
from icarus.engine.runner import (
    BacktestResult,
    FoldResult,
    _gate_signals,
    _session_days,
    _sessions_held,
    _stitch,
    read_trials,
    record_trial,
)
from icarus.strategy.dsl import parse_strategy
from icarus.strategy.library import default_registry

if TYPE_CHECKING:
    from pathlib import Path

    from icarus.common.config import GoalConfig

START = datetime(2024, 1, 1, tzinfo=UTC)

NO_CHARGES = Charges(
    brokerage=Decimal(0),
    stt=Decimal(0),
    exchange_txn=Decimal(0),
    sebi_fee=Decimal(0),
    gst=Decimal(0),
    stamp_duty=Decimal(0),
    dp_charge=Decimal(0),
    turnover=Decimal(0),
)

STRATEGY = """
name: runner_test
version: 1
timeframe: 1d
universe: nse_liquid
entry:
  cross_above:
    a: {sma: {n: 5}}
    b: {sma: {n: 20}}
exit:
  - stop_loss_atr: {atr_mult: 2.0}
sizing:
  risk_r: 0.005
"""


@pytest.fixture
def goal(repo_root: Path) -> GoalConfig:
    return load_goal(repo_root / "goal.yaml")


# --------------------------------------------------------------------------------------
# The warm-up prefix must feed the indicators and never open a position
# --------------------------------------------------------------------------------------


def test_the_warm_up_prefix_cannot_fire_a_signal() -> None:
    """Everything before the gate is blanked; everything at or after it survives untouched."""
    signals = {"AAA": np.ones(10, dtype=np.float64)}
    _gate_signals(signals, gate=4)
    assert signals["AAA"][:4].tolist() == [0.0, 0.0, 0.0, 0.0]
    assert signals["AAA"][4:].tolist() == [1.0] * 6


def test_a_nan_warm_up_signal_is_zeroed_not_left_as_nan() -> None:
    """``nan`` is truthy. Left in place it would open a position on every warm-up bar of every
    symbol — which reads as an unusually active strategy rather than as a bug."""
    signals = {"AAA": np.full(6, np.nan)}
    _gate_signals(signals, gate=3)
    assert not np.isnan(signals["AAA"][:3]).any()
    assert (signals["AAA"][:3] == 0.0).all()


def test_no_warm_up_means_nothing_is_blanked() -> None:
    signals = {"AAA": np.ones(5, dtype=np.float64)}
    _gate_signals(signals, gate=0)
    assert (signals["AAA"] == 1.0).all()


# --------------------------------------------------------------------------------------
# Stitching compounds; it does not add
# --------------------------------------------------------------------------------------


def _metrics_stub() -> Metrics:
    nan = float("nan")
    return Metrics(
        sharpe=SharpeEstimate(nan, nan, nan, nan, 0, 0.95),
        sortino=nan,
        calmar=nan,
        cagr=0.0,
        total_return=0.0,
        volatility_annual=0.0,
        max_drawdown=0.0,
        max_drawdown_days=0,
        trades=0,
        win_rate=0.0,
        profit_factor=nan,
        expectancy_r=0.0,
        avg_win_r=0.0,
        avg_loss_r=0.0,
        avg_holding_days=0.0,
        sessions=0,
        exposure=0.0,
    )


def _fold(index: int, values: list[float], day0: int) -> FoldResult:
    curve = tuple((START + timedelta(days=day0 + i), Decimal(str(v))) for i, v in enumerate(values))
    return FoldResult(
        index=index,
        window=None,  # type: ignore[arg-type]
        train_from="",
        train_to="",
        test_from="",
        test_to="",
        in_sample=_metrics_stub(),
        out_of_sample=_metrics_stub(),
        trades=(),
        skipped={},
        stale_marks=0,
        stale_mark_value=Decimal(0),
        unfilled_exits=0,
        equity_curve=curve,
    )


def test_two_folds_that_each_gained_ten_percent_compound_to_twenty_one() -> None:
    """Both folds start from 100,000 and end at 110,000. Run back to back that is 1.1 x 1.1.

    Concatenating rupee values instead would show equity falling from 110,000 back to 100,000 at
    the seam — a 9% drawdown that never happened, in every walk-forward result.
    """
    folds = [_fold(0, [100_000, 110_000], 0), _fold(1, [100_000, 110_000], 10)]
    stitched = _stitch(folds)
    assert float(stitched[-1][1]) == pytest.approx(1.21)


def test_a_losing_fold_after_a_winning_one_compounds_downward() -> None:
    """+100% then -50% is exactly flat, which addition would report as +50%."""
    folds = [_fold(0, [100.0, 200.0], 0), _fold(1, [100.0, 50.0], 10)]
    assert float(_stitch(folds)[-1][1]) == pytest.approx(1.0)


def test_the_stitched_curve_has_one_point_per_session_after_the_first_of_each_fold() -> None:
    """Each fold's first point establishes a base and produces no return of its own."""
    folds = [_fold(0, [100.0, 101.0, 102.0], 0), _fold(1, [100.0, 101.0], 10)]
    assert len(_stitch(folds)) == 3


# --------------------------------------------------------------------------------------
# Exposure is counted on the session axis
# --------------------------------------------------------------------------------------


def _held(entry: datetime, exit_: datetime) -> ClosedTrade:
    return ClosedTrade(
        symbol="AAA",
        quantity=1,
        entry_ts=entry,
        entry_price=Decimal(100),
        exit_ts=exit_,
        exit_price=Decimal(100),
        reason=ExitReason.TIME_STOP,
        entry_charges=NO_CHARGES,
        exit_charges=NO_CHARGES,
        risk_per_share=Decimal(10),
    )


def test_a_weekend_inside_a_holding_period_is_not_an_exposed_session() -> None:
    """Friday to Monday is four calendar days and two sessions.

    Counting calendar days gave an exposure of 1.48 against a session denominator. The fix is to
    intersect with the run's own session axis, so a day the market was shut cannot be a day the
    strategy was exposed.
    """
    friday, monday = datetime(2024, 1, 5, tzinfo=UTC), datetime(2024, 1, 8, tzinfo=UTC)
    sessions = _session_days([(friday, Decimal(1)), (monday, Decimal(1))])
    assert _sessions_held([_held(friday, monday)], sessions) == 2


def test_two_positions_open_on_one_day_count_as_one_exposed_session() -> None:
    """Exposure asks whether the strategy was in the market, not in how many ways."""
    day = datetime(2024, 1, 5, tzinfo=UTC)
    sessions = _session_days([(day, Decimal(1))])
    assert _sessions_held([_held(day, day), _held(day, day)], sessions) == 1


# --------------------------------------------------------------------------------------
# The trial ledger (invariant #24)
# --------------------------------------------------------------------------------------


def _result() -> BacktestResult:
    return BacktestResult(strategy="runner_test", folds=[], oos=None, oos_trades=[])


def test_a_run_appends_to_the_ledger_rather_than_replacing_it(tmp_path: Path) -> None:
    """The count is the whole point. Two runs of the same strategy are two trials, not one:
    re-running after a tweak is exactly the search DSR has to correct for."""
    strategy = parse_strategy(STRATEGY, registry=default_registry(), max_risk_r=0.005)
    path = tmp_path / "trials.json"
    assert record_trial(path, strategy, _result(), origin="operator") == 1  # type: ignore[arg-type]
    assert record_trial(path, strategy, _result(), origin="operator") == 2  # type: ignore[arg-type]
    assert len(read_trials(path)) == 2


def test_a_human_run_is_recorded_with_the_same_weight_as_an_inventor_run(tmp_path: Path) -> None:
    """Phase 1's only searcher is the operator. A ledger counting only machine candidates would
    be blind during exactly the phase it exists to protect."""
    strategy = parse_strategy(STRATEGY, registry=default_registry(), max_risk_r=0.005)
    path = tmp_path / "trials.json"
    record_trial(path, strategy, _result(), origin="operator")  # type: ignore[arg-type]
    record_trial(path, strategy, _result(), origin="inventor")  # type: ignore[arg-type]
    origins = [t["origin"] for t in read_trials(path)]
    assert origins == ["operator", "inventor"]
    assert len(read_trials(path)) == 2


def test_an_unreadable_ledger_raises_rather_than_starting_a_fresh_one(tmp_path: Path) -> None:
    """Silently starting over would reset the lifetime trial count to zero and make every DSR
    figure computed afterwards too generous."""
    path = tmp_path / "trials.json"
    path.write_text(json.dumps({"schema": 99, "trials": []}), encoding="utf-8")
    with pytest.raises(Exception, match="schema"):
        read_trials(path)


def test_a_missing_ledger_is_an_empty_history_not_an_error(tmp_path: Path) -> None:
    assert read_trials(tmp_path / "nope.json") == []


def test_the_recorded_trial_names_the_primitives_that_were_searched(tmp_path: Path) -> None:
    """The effective trial count depends on how *similar* the things tried were; two runs of the
    same primitives are closer to one trial than two, and 1.9b needs the vocabulary to judge it."""
    strategy = parse_strategy(STRATEGY, registry=default_registry(), max_risk_r=0.005)
    path = tmp_path / "trials.json"
    record_trial(path, strategy, _result(), origin="operator")  # type: ignore[arg-type]
    assert "sma" in read_trials(path)[0]["primitives"]  # type: ignore[operator]


def test_the_ledger_survives_a_date_change(tmp_path: Path) -> None:
    """Entries carry their own timestamp, so the ledger is a record and not a snapshot."""
    strategy = parse_strategy(STRATEGY, registry=default_registry(), max_risk_r=0.005)
    path = tmp_path / "trials.json"
    record_trial(path, strategy, _result(), origin="operator")  # type: ignore[arg-type]
    stamped = str(read_trials(path)[0]["at"])
    assert date.fromisoformat(stamped[:10]) <= datetime.now(UTC).date()
