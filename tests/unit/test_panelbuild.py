"""Panel assembly from the bhavcopy archive — task 1.7c.

The properties here cannot be checked by looking at the output, because a wrong panel looks
exactly like a right one: membership decided on raw prices, back-adjustment applied to the past
rather than the future, and a discontinuity we could not explain being removed rather than traded
through. Each test states which of those it pins and what the failure would have looked like.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
import pytest

from icarus.agents.data.corpactions import Split
from icarus.agents.data.nse import DAY_CACHE_SCHEMA
from icarus.agents.data.nseactions import ActionHistory, Unpriceable
from icarus.common.config import Universe as UniverseConfig
from icarus.engine.panelbuild import build_panel, load_panel, save_panel, session_axis
from icarus.strategy.dsl import Bars, DslError

if TYPE_CHECKING:
    from pathlib import Path

SESSIONS = [date(2024, 1, d) for d in range(1, 26)]


def _universe(**over: object) -> UniverseConfig:
    base: dict[str, object] = {
        "min_avg_turnover_inr": 1_000_000,
        "turnover_window_sessions": 5,
        "min_close_inr": 30,
        "dividend_convention": "price_return",
        "history_years": 5,
    }
    return UniverseConfig(**(base | over))  # type: ignore[arg-type]


def _write_days(
    root: Path, prices: dict[str, list[float | None]], turnover: float = 10_000_000.0
) -> None:
    """One JSON day-file per session, in the day-cache's own format. ``None`` = did not trade."""
    root.mkdir(parents=True, exist_ok=True)
    for t, day in enumerate(SESSIONS):
        rows = {}
        for symbol, series in prices.items():
            price = series[t]
            if price is None:
                continue
            rows[symbol] = [
                f"{price:.2f}",
                f"{price * 1.01:.2f}",
                f"{price * 0.99:.2f}",
                f"{price:.2f}",
                "100000",
                f"{turnover:.2f}",
            ]
        (root / f"{day:%Y%m%d}.json").write_text(
            json.dumps({"schema": DAY_CACHE_SCHEMA, "rows": rows}), encoding="utf-8"
        )


def _actions(
    splits: dict[str, tuple[Split, ...]] | None = None,
    *,
    unpriceable: tuple[Unpriceable, ...] = (),
    unrecognised: tuple[Unpriceable, ...] = (),
) -> ActionHistory:
    return ActionHistory(
        frm=SESSIONS[0],
        to=SESSIONS[-1],
        splits=splits or {},
        unpriceable=unpriceable,
        unrecognised=unrecognised,
    )


def _prices(values: list[float]) -> dict[str, list[float | None]]:
    return {"AAA": list(values)}


# --------------------------------------------------------------------------------------
# Back-adjustment
# --------------------------------------------------------------------------------------


def test_a_split_rescales_the_past_and_leaves_the_present_alone(tmp_path: Path) -> None:
    """A 1:1 bonus on session 12: prices before are halved, prices from the ex-date are untouched.

    Adjusting *forward* instead would leave history alone and double every recent price — a
    perfectly smooth series in which the most recent quote is not the price a live order fills at.
    """
    _write_days(tmp_path, _prices([100.0] * 12 + [50.0] * 13))
    panel, report = build_panel(
        sessions=SESSIONS,
        cache_dir=tmp_path,
        actions=_actions({"AAA": (Split(ex_date=SESSIONS[12], ratio=Decimal(2)),)}),
        universe=_universe(),
    )
    close = panel.bars[panel.index_of("AAA")].close
    assert close[0] == pytest.approx(50.0), "pre-split price halved"
    assert close[-1] == pytest.approx(50.0), "post-split price untouched"
    assert report.splits_applied == 1
    assert report.quarantines == [], "the adjustment explained the gap, so nothing is quarantined"


def test_volume_moves_the_opposite_way_so_traded_value_is_preserved(tmp_path: Path) -> None:
    """Halving the price without doubling the share count would halve the historical turnover a
    liquidity filter reads, and the name would look like it had thinned out."""
    _write_days(tmp_path, _prices([100.0] * 12 + [50.0] * 13))
    panel, _ = build_panel(
        sessions=SESSIONS,
        cache_dir=tmp_path,
        actions=_actions({"AAA": (Split(ex_date=SESSIONS[12], ratio=Decimal(2)),)}),
        universe=_universe(),
    )
    volume = panel.bars[panel.index_of("AAA")].volume
    assert volume[0] == pytest.approx(200_000.0)
    assert volume[-1] == pytest.approx(100_000.0)


# --------------------------------------------------------------------------------------
# The gap audit
# --------------------------------------------------------------------------------------


def test_an_unexplained_halving_quarantines_the_history_before_it(tmp_path: Path) -> None:
    """The same price series with no split on file — the real situation for the 186 symbols
    NSE's corporate-action list does not cover.

    Pre-gap history is on a different scale from post-gap history, so it is removed. The symbol
    survives from the gap onward, and the quarantine is counted rather than absorbed.
    """
    _write_days(tmp_path, _prices([100.0] * 12 + [50.0] * 13))
    panel, report = build_panel(
        sessions=SESSIONS, cache_dir=tmp_path, actions=_actions(), universe=_universe()
    )
    tradable = panel.tradable[panel.index_of("AAA")]
    assert not tradable[:13].any(), "everything up to and including the gap is gone"
    assert tradable[13:].any(), "and everything after it survives"
    assert len(report.quarantines) == 1
    assert report.quarantines[0].ratio == pytest.approx(0.5, abs=0.02)
    assert report.quarantines[0].had_action_on_file is False


def test_an_ordinary_move_is_not_a_discontinuity(tmp_path: Path) -> None:
    """A 10% overnight move is a bad day, not a corporate action.

    Quarantining it would delete a real loss, which is the one direction this must never be
    wrong in — every deleted loss makes the backtest look better than the strategy was.
    """
    _write_days(tmp_path, _prices([100.0] * 12 + [90.0] * 13))
    _, report = build_panel(
        sessions=SESSIONS, cache_dir=tmp_path, actions=_actions(), universe=_universe()
    )
    assert report.quarantines == []


def test_a_gap_next_to_an_event_on_file_is_reported_as_such(tmp_path: Path) -> None:
    """Distinguishes "our ratio was wrong" from "NSE never listed it". Different fixes: one is a
    parser bug, the other is a coverage gap needing a second source."""
    _write_days(tmp_path, _prices([100.0] * 12 + [50.0] * 13))
    _, report = build_panel(
        sessions=SESSIONS,
        cache_dir=tmp_path,
        actions=_actions(
            unpriceable=(Unpriceable(symbol="AAA", ex_date=SESSIONS[12], subject="Demerger"),)
        ),
        universe=_universe(),
    )
    assert report.quarantines[0].had_action_on_file is True


def test_an_absence_is_not_a_gap(tmp_path: Path) -> None:
    """A symbol suspended for a week and returning lower has not gapped, it has been away.

    Comparing across the hole would quarantine every name that ever took a trading halt.
    """
    series: list[float | None] = [100.0] * 10 + [None] * 5 + [70.0] * 10
    _write_days(tmp_path, {"AAA": series})
    _, report = build_panel(
        sessions=SESSIONS, cache_dir=tmp_path, actions=_actions(), universe=_universe()
    )
    assert report.quarantines == []


# --------------------------------------------------------------------------------------
# Membership is decided on the raw prices
# --------------------------------------------------------------------------------------


def test_the_penny_floor_is_applied_before_back_adjustment(tmp_path: Path) -> None:
    """A stock trading at ₹45, which later does a 1:10 bonus, back-adjusts to ₹4.50.

    Judged on the adjusted series it would be excluded as a penny stock — by a rule applied using
    knowledge of something that happened afterwards. It really traded at ₹45 and really was
    tradable, so membership is decided on what a trader could see on the day, and only then are
    prices made continuous.
    """
    _write_days(tmp_path, _prices([45.0] * 20 + [4.5] * 5))
    panel, _ = build_panel(
        sessions=SESSIONS,
        cache_dir=tmp_path,
        actions=_actions({"AAA": (Split(ex_date=SESSIONS[20], ratio=Decimal(10)),)}),
        universe=_universe(min_close_inr=30),
    )
    index = panel.index_of("AAA")
    assert panel.tradable[index][10], "tradable in the era it really traded above the floor"
    assert panel.bars[index].close[10] == pytest.approx(4.5), "and still back-adjusted"


def test_a_name_below_the_turnover_floor_is_never_tradable(tmp_path: Path) -> None:
    """And a panel in which nothing is ever tradable is refused rather than returned empty."""
    _write_days(tmp_path, _prices([100.0] * 25), turnover=1.0)
    with pytest.raises(DslError, match="no symbol cleared"):
        build_panel(sessions=SESSIONS, cache_dir=tmp_path, actions=_actions(), universe=_universe())


def test_the_first_sessions_have_no_complete_liquidity_window(tmp_path: Path) -> None:
    """A five-session trailing window cannot be complete before the fifth session.

    Qualifying earlier would let a name trade on liquidity it had not yet demonstrated, which is
    the off-by-one that turns a point-in-time filter into a look-ahead.
    """
    _write_days(tmp_path, _prices([100.0] * 25))
    panel, _ = build_panel(
        sessions=SESSIONS,
        cache_dir=tmp_path,
        actions=_actions(),
        universe=_universe(turnover_window_sessions=5),
    )
    tradable = panel.tradable[panel.index_of("AAA")]
    assert not tradable[:4].any()
    assert tradable[4]


# --------------------------------------------------------------------------------------
# Missing data is a halt, not a skip
# --------------------------------------------------------------------------------------


def test_a_session_with_no_cached_file_raises(tmp_path: Path) -> None:
    """A hole in the middle of a backtest corrupts every window spanning it, and a silently
    skipped session is indistinguishable from a holiday (§29.4)."""
    _write_days(tmp_path, _prices([100.0] * 25))
    (tmp_path / f"{SESSIONS[7]:%Y%m%d}.json").unlink()
    with pytest.raises(DslError, match="no cached bhavcopy"):
        build_panel(sessions=SESSIONS, cache_dir=tmp_path, actions=_actions(), universe=_universe())


def test_a_stale_day_cache_schema_raises_rather_than_being_read(tmp_path: Path) -> None:
    """The schema constant is imported from the writer, so this can only fire on a real drift."""
    _write_days(tmp_path, _prices([100.0] * 25))
    path = tmp_path / f"{SESSIONS[0]:%Y%m%d}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**payload, "schema": 99}), encoding="utf-8")
    with pytest.raises(DslError, match="day-cache schema"):
        build_panel(sessions=SESSIONS, cache_dir=tmp_path, actions=_actions(), universe=_universe())


# --------------------------------------------------------------------------------------
# The cache round-trip
# --------------------------------------------------------------------------------------


def test_the_benchmark_survives_the_cache_round_trip(tmp_path: Path) -> None:
    """It did not, in the first version — ``save_panel`` dropped it silently, so every reload came
    back with ``benchmark=None``, every index-relative word would have refused to evaluate, and
    the alpha gate would have had nothing to measure against. The build log said it loaded fine."""
    _write_days(tmp_path / "days", _prices([100.0] * 25))
    index = Bars(
        ts=session_axis(SESSIONS),
        open=np.full(25, 20000.0),
        high=np.full(25, 20100.0),
        low=np.full(25, 19900.0),
        close=np.full(25, 20000.0),
        volume=np.full(25, 1.0),
    )
    panel, report = build_panel(
        sessions=SESSIONS,
        cache_dir=tmp_path / "days",
        actions=_actions(),
        universe=_universe(),
        benchmark=index,
    )
    save_panel(panel, report, tmp_path / "panel.npz")
    reloaded = load_panel(tmp_path / "panel.npz")
    assert reloaded.benchmark is not None
    assert reloaded.benchmark.close[0] == pytest.approx(20000.0)


def test_a_panel_survives_the_round_trip_unchanged(tmp_path: Path) -> None:
    _write_days(tmp_path / "days", _prices([100.0] * 25))
    panel, report = build_panel(
        sessions=SESSIONS, cache_dir=tmp_path / "days", actions=_actions(), universe=_universe()
    )
    save_panel(panel, report, tmp_path / "panel.npz")
    reloaded = load_panel(tmp_path / "panel.npz")
    assert reloaded.symbols == panel.symbols
    assert np.array_equal(reloaded.tradable, panel.tradable)
    assert np.array_equal(reloaded.bars[0].close, panel.bars[0].close, equal_nan=True)


def test_a_stale_panel_cache_schema_is_refused(tmp_path: Path) -> None:
    """Rebuilt rather than coerced: a panel read under the wrong layout is silently wrong."""
    _write_days(tmp_path / "days", _prices([100.0] * 25))
    panel, report = build_panel(
        sessions=SESSIONS, cache_dir=tmp_path / "days", actions=_actions(), universe=_universe()
    )
    save_panel(panel, report, tmp_path / "panel.npz")
    with np.load(tmp_path / "panel.npz") as data:
        payload = {name: data[name] for name in data.files}
    payload["schema"] = np.array([99])
    np.savez_compressed(tmp_path / "panel.npz", **payload)
    with pytest.raises(DslError, match="schema"):
        load_panel(tmp_path / "panel.npz")
