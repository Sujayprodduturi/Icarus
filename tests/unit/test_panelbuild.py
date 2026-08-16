"""Panel assembly from the bhavcopy archive — task 1.7c.

The properties here cannot be checked by looking at the output, because a wrong panel looks
exactly like a right one: membership decided on raw prices, back-adjustment applied to the past
rather than the future, and a discontinuity we could not explain being removed rather than traded
through. Each test states which of those it pins and what the failure would have looked like.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
import pytest

from icarus.agents.data.corpactions import Split
from icarus.agents.data.nse import DAY_CACHE_SCHEMA
from icarus.agents.data.nseactions import ActionHistory, Unpriceable
from icarus.common.config import DataQuality as DataQualityConfig
from icarus.common.config import Universe as UniverseConfig
from icarus.engine.panelbuild import build_panel, load_panel, save_panel, session_axis
from icarus.strategy.dsl import Bars, DslError

if TYPE_CHECKING:
    from pathlib import Path

SESSIONS = [date(2024, 1, d) for d in range(1, 26)]


def _quality(**over: object) -> DataQualityConfig:
    """The QA thresholds. ``atr_window`` is 3 rather than the live 14 because these fixtures are
    25 sessions long — a 14-bar warm-up would leave the bad-tick test silent for over half of
    every fixture, and a test that cannot fire proves nothing."""
    base: dict[str, object] = {
        "atr_window": 3,
        "max_bar_move_atr": 8.0,
        "max_single_bar_move": 0.5,
        "min_day_score": 0.98,
        "stale_sessions_symbol_veto": 2,
        "stale_plane_halt_ratio": 0.5,
    }
    return DataQualityConfig(**(base | over))


def _universe(**over: object) -> UniverseConfig:
    base: dict[str, object] = {
        "min_avg_turnover_inr": 1_000_000,
        "turnover_window_sessions": 5,
        "min_close_inr": 30,
        "dividend_convention": "price_return",
        "history_years": 5,
    }
    return UniverseConfig(**(base | over))


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
        sessions=SESSIONS,
        cache_dir=tmp_path,
        actions=_actions(),
        universe=_universe(),
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
        sessions=SESSIONS,
        cache_dir=tmp_path,
        actions=_actions(),
        universe=_universe(),
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
        sessions=SESSIONS,
        cache_dir=tmp_path,
        actions=_actions(),
        universe=_universe(),
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
        build_panel(
            sessions=SESSIONS,
            cache_dir=tmp_path,
            actions=_actions(),
            universe=_universe(),
        )


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
        build_panel(
            sessions=SESSIONS,
            cache_dir=tmp_path,
            actions=_actions(),
            universe=_universe(),
        )


def test_a_stale_day_cache_schema_raises_rather_than_being_read(tmp_path: Path) -> None:
    """The schema constant is imported from the writer, so this can only fire on a real drift."""
    _write_days(tmp_path, _prices([100.0] * 25))
    path = tmp_path / f"{SESSIONS[0]:%Y%m%d}.json"
    payload = json.loads(path.read_text(encoding="utf-8"))
    path.write_text(json.dumps({**payload, "schema": 99}), encoding="utf-8")
    with pytest.raises(DslError, match="day-cache schema"):
        build_panel(
            sessions=SESSIONS,
            cache_dir=tmp_path,
            actions=_actions(),
            universe=_universe(),
        )


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
        sessions=SESSIONS,
        cache_dir=tmp_path / "days",
        actions=_actions(),
        universe=_universe(),
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
        sessions=SESSIONS,
        cache_dir=tmp_path / "days",
        actions=_actions(),
        universe=_universe(),
    )
    save_panel(panel, report, tmp_path / "panel.npz")
    with np.load(tmp_path / "panel.npz") as data:
        payload = {name: data[name] for name in data.files}
    payload["schema"] = np.array([99])
    np.savez_compressed(tmp_path / "panel.npz", **payload)
    with pytest.raises(DslError, match="schema"):
        load_panel(tmp_path / "panel.npz")


def test_a_listed_unpriceable_action_quarantines_even_with_no_visible_gap(tmp_path: Path) -> None:
    """A rights issue or partial demerger repricing a name by 15% is below MAX_UNEXPLAINED_GAP.

    Both module docstrings promised that unpriceable actions get their history quarantined, but
    the promise was never kept: `unpriceable` only ever set the `had_action_on_file` label on gaps
    the audit had already found on its own. So an event NSE told us about, which we admitted we
    could not price, sailed through and became a real 15% loss the strategy traded and stopped
    out on.
    """
    _write_days(tmp_path, _prices([100.0] * 12 + [85.0] * 13))
    panel, report = build_panel(
        sessions=SESSIONS,
        cache_dir=tmp_path,
        actions=_actions(
            unpriceable=(Unpriceable(symbol="AAA", ex_date=SESSIONS[12], subject="Demerger"),)
        ),
        universe=_universe(),
    )
    tradable = panel.tradable[panel.index_of("AAA")]
    assert not tradable[:13].any(), "history before an unpriceable event is gone"
    assert tradable[13:].any(), "and the name survives after it"
    assert len(report.quarantines) == 1
    assert report.quarantines[0].had_action_on_file is True


def test_an_unpriceable_action_outside_the_span_quarantines_nothing(tmp_path: Path) -> None:
    """Only ex-dates inside the built panel can cut it; one before or after is not this panel's
    problem and must not silently blank a symbol."""
    _write_days(tmp_path, _prices([100.0] * 25))
    _, report = build_panel(
        sessions=SESSIONS,
        cache_dir=tmp_path,
        actions=_actions(
            unpriceable=(Unpriceable(symbol="AAA", ex_date=date(2030, 1, 1), subject="Demerger"),)
        ),
        universe=_universe(),
    )
    assert report.quarantines == []


# --------------------------------------------------------------------------------------
# The structural rules exist twice. Prove they agree.
# --------------------------------------------------------------------------------------

_STRUCTURAL: tuple[tuple[str, tuple[float, float, float, float], float], ...] = (
    ("an ordinary bar", (100.0, 101.0, 99.0, 100.5), 1_000.0),
    ("a doji", (100.0, 100.0, 100.0, 100.0), 0.0),
    ("negative open", (-1.0, 101.0, 99.0, 100.0), 1_000.0),
    ("negative close", (100.0, 101.0, 99.0, -5.0), 1_000.0),
    ("zero low", (100.0, 101.0, 0.0, 100.0), 1_000.0),
    ("all zero", (0.0, 0.0, 0.0, 0.0), 1_000.0),
    ("high below low", (100.0, 99.0, 101.0, 100.0), 1_000.0),
    ("open above high", (105.0, 101.0, 99.0, 100.0), 1_000.0),
    ("close above high", (100.0, 101.0, 99.0, 105.0), 1_000.0),
    ("open below low", (95.0, 101.0, 99.0, 100.0), 1_000.0),
    ("close below low", (100.0, 101.0, 99.0, 95.0), 1_000.0),
    ("negative volume", (100.0, 101.0, 99.0, 100.0), -1.0),
)


@pytest.mark.parametrize(("label", "ohlc", "volume"), _STRUCTURAL, ids=[c[0] for c in _STRUCTURAL])
def test_the_panel_and_the_live_gate_agree_on_every_structural_rule(
    label: str, ohlc: tuple[float, float, float, float], volume: float
) -> None:
    """``_row_values`` and ``DataQualityGate`` implement the same three structural rules twice.

    **They are not shared code and should not be.** The gate is a stateful validator over a stream
    of ``Decimal`` candles; the panel builder is a batch ``float64`` matrix pass over 4.4 million
    rows. Forcing one implementation onto both would make one of them the wrong shape, and
    converting every row to ``Decimal`` to reuse the other would cost more than the check is worth.

    But two copies nobody ever compares is precisely how the day-cache schema constant drifted —
    a reader and a writer holding different numbers, each internally consistent. So the answer is
    not shared code, it is a **proof of equivalence**: same bars, same verdict, checked here.

    The candle is priced as ``CRYPTO`` so the gate's trading-day rule stays out of the comparison.
    That rule has no counterpart in the panel and cannot have one — sessions come from the
    validated calendar artifact, so a non-trading day is unreachable by construction rather than
    rejected. Comparing it would be comparing a rule against nothing.
    """
    from decimal import Decimal as D

    from icarus.agents.data.quality import DataQualityGate
    from icarus.common.types import OHLCV, AssetClass, Candle
    from icarus.engine.panelbuild import _row_values

    row = [f"{v:.4f}" for v in ohlc] + [f"{volume:.4f}", "1000000.0"]
    panel_accepts = _row_values(row) is not None

    gate = DataQualityGate(_quality())
    candle = Candle(
        ts=datetime(2024, 1, 3, tzinfo=UTC),
        ohlcv=OHLCV(
            open=D(str(ohlc[0])),
            high=D(str(ohlc[1])),
            low=D(str(ohlc[2])),
            close=D(str(ohlc[3])),
            volume=D(str(volume)),
        ),
    )
    gate_accepts = gate.assess("x", AssetClass.CRYPTO, candle).accepted

    assert panel_accepts == gate_accepts, (
        f"{label}: the panel {'accepts' if panel_accepts else 'rejects'} this bar and the live "
        f"gate {'accepts' if gate_accepts else 'rejects'} it. The two structural implementations "
        f"have drifted — a bar tradable in one plane and not the other."
    )


def test_the_one_deliberate_difference_is_the_sub_rupee_floor() -> None:
    """The panel is **stricter** than the gate below ₹1, on purpose — so the test above would
    fail on that band if it were included, and pretending otherwise would be the drift we are
    guarding against.

    A 40-paisa quote moves in 5-paisa ticks: an eighth of the price per tick. No fill model of
    ours is honest there, so the panel refuses it while the live gate — which only asks whether
    the print is *real* — accepts it. Stated as its own test rather than as an exception buried
    in a parametrised list, because an untested exception is how a rule quietly becomes optional.
    """
    from decimal import Decimal as D

    from icarus.agents.data.quality import DataQualityGate
    from icarus.common.types import OHLCV, AssetClass, Candle
    from icarus.engine.panelbuild import _MIN_SANE_PRICE, _row_values

    price = _MIN_SANE_PRICE / 2
    row = [f"{price:.4f}"] * 4 + ["1000.0", "1000.0"]
    assert _row_values(row) is None, "the panel refuses a sub-rupee quote"

    gate = DataQualityGate(_quality())
    candle = Candle(
        ts=datetime(2024, 1, 3, tzinfo=UTC),
        ohlcv=OHLCV(**dict.fromkeys(("open", "high", "low", "close"), D(str(price))), volume=D(1)),
    )
    assert gate.assess("x", AssetClass.CRYPTO, candle).accepted, "the live gate allows it"
