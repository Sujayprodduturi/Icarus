"""Walk-forward, purge/embargo and the lockbox guard — task 1.7, PRD §13, §29-31.

The failures these guard against share one property: **they leave no trace in any metric.** A
window that overlaps its own training data, a purge gap too narrow for the strategy's lookback, a
lockbox looked at twice — none of them produce an error, a warning, or an odd-looking number. They
produce a *better* number, which is exactly why they have to be structurally impossible rather
than merely discouraged.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING

import numpy as np
import pytest

from icarus.common.config import Amendment, DataSplit
from icarus.common.config import Backtest as BacktestConfig
from icarus.engine.backtest import (
    LockboxExhausted,
    LockboxGuard,
    Window,
    assert_no_lockbox_overlap,
    lockbox_window,
    longest_lookback,
    slice_panel,
    walk_forward_windows,
)
from icarus.strategy.dsl import Bars, DslError, Panel, parse_strategy
from icarus.strategy.library import default_registry

if TYPE_CHECKING:
    from pathlib import Path

SPLIT = DataSplit(
    walk_forward_start=date(2011, 1, 1),
    walk_forward_end=date(2022, 12, 31),
    lockbox_start=date(2023, 1, 1),
    lockbox_end=None,
    lockbox_uses_allowed=1,
)
CONFIG = BacktestConfig(
    registered=date(2026, 8, 5),
    min_train_years=3.0,
    test_window_years=1.0,
    step_years=1.0,
    embargo_sessions=5,
    starting_equity_inr=100_000,
    stale_position_sessions=20,
    stale_position_sessions_amendments=(
        Amendment(
            value=20,
            set_on=date(2026, 8, 14),
            results_existed=True,
            acknowledged_post_hoc=True,
            reason="fixture",
        ),
    ),
)


def _strategy(lookback: int = 20) -> object:
    text = f"""
name: wf_test
version: 1
timeframe: 1d
universe: nse_liquid_100
entry:
  cross_above:
    a: {{sma: {{n: 5}}}}
    b: {{sma: {{n: {lookback}}}}}
exit:
  - stop_loss_atr: {{atr_mult: 2.0}}
sizing:
  risk_r: 0.005
"""
    return parse_strategy(text, registry=default_registry(), max_risk_r=0.005)


def _panel(sessions: int = 6000, start: str = "2011-01-03") -> Panel:
    """One symbol over `sessions` consecutive dated bars.

    Calendar days rather than real sessions: the window arithmetic is purely index-based, so a
    denser axis only makes the fixture shorter to write. 6,000 days spans 2011 into 2027, which is
    what the lockbox tests need.
    """
    close = np.linspace(100.0, 300.0, sessions)
    bars = Bars(
        ts=np.arange(np.datetime64(start), np.datetime64(start) + sessions).astype(
            "datetime64[ns]"
        ),
        open=close.copy(),
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=np.full(sessions, 1_000_000.0),
    )
    return Panel.build({"AAA": bars}, {"AAA": np.ones(sessions, dtype=np.bool_)})


# --------------------------------------------------------------------------------------
# Purge is derived from the strategy, not configured
# --------------------------------------------------------------------------------------


def test_the_purge_gap_is_the_strategys_own_longest_lookback() -> None:
    """A 252-day word leaks 252 days across the seam; a 20-day word leaks 20. A single constant
    would be too small for the first and wasteful for the second, and too-small leaks silently."""
    assert longest_lookback(_strategy(lookback=20)) == 20  # type: ignore[arg-type]
    assert longest_lookback(_strategy(lookback=252)) == 252  # type: ignore[arg-type]


def test_a_wider_lookback_widens_the_purge_gap_in_the_windows() -> None:
    panel = _panel()
    narrow = walk_forward_windows(panel, _strategy(20), CONFIG, SPLIT)  # type: ignore[arg-type]
    wide = walk_forward_windows(panel, _strategy(252), CONFIG, SPLIT)  # type: ignore[arg-type]
    assert narrow[0].purge_sessions == 20
    assert wide[0].purge_sessions == 252
    assert wide[0].test_start - wide[0].train_end == 252


# --------------------------------------------------------------------------------------
# Window shape
# --------------------------------------------------------------------------------------


def test_training_and_test_windows_never_overlap() -> None:
    """The construction that makes the leak impossible rather than merely unlikely."""
    for window in walk_forward_windows(_panel(), _strategy(), CONFIG, SPLIT):  # type: ignore[arg-type]
        assert window.train_end <= window.test_start
        assert window.train_end < window.test_end


def test_a_window_that_overlaps_its_own_training_data_cannot_be_constructed() -> None:
    with pytest.raises(ValueError, match="they overlap"):
        Window(
            train_start=0,
            train_end=100,
            test_start=50,
            test_end=150,
            purge_sessions=0,
            embargo_sessions=5,
        )


def test_training_is_anchored_and_expands_rather_than_rolling() -> None:
    """Every fold trains from the same start. A rolling window would drop 2011-2013 as the sample
    advances — the taper tantrum and demonetisation, exactly the regimes a strategy most needs to
    have survived."""
    windows = walk_forward_windows(_panel(), _strategy(), CONFIG, SPLIT)  # type: ignore[arg-type]
    assert len({w.train_start for w in windows}) == 1
    assert [w.train_end for w in windows] == sorted(w.train_end for w in windows)


def test_there_is_more_than_one_fold() -> None:
    """A single train/test split is one lucky draw. The whole point is several chances to fail."""
    assert len(walk_forward_windows(_panel(), _strategy(), CONFIG, SPLIT)) >= 5  # type: ignore[arg-type]


def test_a_panel_too_short_for_one_fold_refuses_rather_than_shrinking_the_window() -> None:
    """Quietly using a shorter training window would report a walk-forward result that was not
    one — a number under a name it has not earned."""
    with pytest.raises(DslError, match="no walk-forward window fits"):
        walk_forward_windows(_panel(sessions=400), _strategy(), CONFIG, SPLIT)  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------
# The lockbox is unreachable from the ordinary path
# --------------------------------------------------------------------------------------


def test_no_walk_forward_window_ever_reaches_the_lockbox() -> None:
    """Checked from two directions on purpose: the generator stops short of lockbox_start, and this
    asserts the same thing from the dates. An overlap turns the lockbox into training data and
    leaves no trace in any metric, so it is worth checking twice."""
    panel = _panel()
    windows = walk_forward_windows(panel, _strategy(), CONFIG, SPLIT)  # type: ignore[arg-type]
    assert_no_lockbox_overlap(windows, panel, SPLIT)


def test_a_window_reaching_into_the_lockbox_is_caught() -> None:
    panel = _panel()
    dates = [d.astype("datetime64[D]").astype(date) for d in panel.ts]
    inside = next(i for i, d in enumerate(dates) if d >= SPLIT.lockbox_start)
    bad = Window(
        train_start=0,
        train_end=inside,
        test_start=inside,
        test_end=inside + 10,
        purge_sessions=0,
        embargo_sessions=0,
    )
    with pytest.raises(DslError, match="contaminates the lockbox"):
        assert_no_lockbox_overlap([bad], panel, SPLIT)


def test_the_lockbox_window_starts_where_the_development_span_ends() -> None:
    panel = _panel()
    window = lockbox_window(panel, SPLIT)
    dates = [d.astype("datetime64[D]").astype(date) for d in panel.ts]
    assert dates[window.test_start] >= SPLIT.lockbox_start
    assert dates[window.train_end - 1] <= SPLIT.walk_forward_end


# --------------------------------------------------------------------------------------
# Slicing removes the future rather than hiding it
# --------------------------------------------------------------------------------------


def test_a_windowed_panel_physically_lacks_the_bars_outside_it() -> None:
    """Slicing rather than masking, so a leakage bug cannot hide behind an off-by-one in a mask —
    the same property replay mode (1.10) depends on."""
    panel = _panel(sessions=500)
    window = slice_panel(panel, 100, 200)
    assert len(window) == 100
    np.testing.assert_array_equal(window.bars[0].close, panel.bars[0].close[100:200])
    np.testing.assert_array_equal(window.tradable[0], panel.tradable[0][100:200])


def test_slicing_outside_the_panel_is_refused() -> None:
    with pytest.raises(DslError, match="outside the panel"):
        slice_panel(_panel(sessions=100), 50, 500)


# --------------------------------------------------------------------------------------
# The lockbox use log
# --------------------------------------------------------------------------------------


def _guard(tmp_path: Path) -> LockboxGuard:
    return LockboxGuard(tmp_path / "lockbox_uses.json", allowed=1)


def test_the_lockbox_can_be_consumed_once(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    assert guard.uses_since_reset() == 0
    guard.consume("wf_test", "final go/no-go")
    assert guard.uses_since_reset() == 1


def test_a_second_evaluation_is_refused(tmp_path: Path) -> None:
    """A second look makes it training data — you are tuning against it like everything else, just
    more slowly, and every number from it afterwards is meaningless."""
    guard = _guard(tmp_path)
    guard.consume("wf_test", "final go/no-go")
    with pytest.raises(LockboxExhausted, match="invariant #26"):
        guard.consume("wf_test", "just checking")


def test_the_budget_survives_a_new_guard_instance(tmp_path: Path) -> None:
    """The counter is on disk, not in memory — a restart must not hand back a spent budget."""
    _guard(tmp_path).consume("wf_test", "final go/no-go")
    with pytest.raises(LockboxExhausted):
        _guard(tmp_path).consume("wf_test", "after a restart")


def test_a_reset_restores_the_budget_and_stays_in_the_record_forever(tmp_path: Path) -> None:
    """The operator decision (2026-08-05): recoverable, never invisible.

    A bug or a mistyped date could otherwise destroy the only clean evaluation window this project
    has, turning a coding error into a project-ending event. So the accident is recoverable — and
    the record of it is not, so a later reader can always weigh the reset against what came after.
    """
    guard = _guard(tmp_path)
    guard.consume("wf_test", "burned by a mistyped date")
    guard.reset("data_split typo pointed a routine run at the lockbox; no result was read")
    guard.consume("wf_test", "the real final evaluation")

    history = guard.history()
    assert len(history) == 3
    assert [use.is_reset for use in history] == [False, True, False]
    assert guard.uses_since_reset() == 1
    assert "mistyped" in history[0].reason


def test_an_unexplained_reset_is_refused(tmp_path: Path) -> None:
    """An unexplained reset is a deletion wearing a different name."""
    with pytest.raises(DslError, match="needs a reason"):
        _guard(tmp_path).reset("   ")


def test_a_log_written_by_a_future_schema_is_refused_not_guessed_at(tmp_path: Path) -> None:
    path = tmp_path / "lockbox_uses.json"
    path.write_text('{"schema": 99, "uses": []}', encoding="utf-8")
    with pytest.raises(DslError, match="refusing to interpret"):
        LockboxGuard(path).history()


def test_the_recorded_use_carries_when_and_why(tmp_path: Path) -> None:
    guard = _guard(tmp_path)
    stamp = datetime(2026, 11, 3, 9, 30, tzinfo=UTC)
    guard.consume("donlevey_sweep", "Phase-1 final go/no-go", now=stamp)
    use = guard.history()[0]
    assert use.at == stamp
    assert use.strategy == "donlevey_sweep"
    assert use.reason == "Phase-1 final go/no-go"
