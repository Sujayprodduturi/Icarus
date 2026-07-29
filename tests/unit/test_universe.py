"""Task 1.1c — point-in-time universe, derived calendar, and corporate-action back-adjustment.

The acceptance criteria this file exists to prove:
  * the backtest selects the as-of-date universe (never today's list), and
  * a known split date generates no signal.
"""

from __future__ import annotations

import csv
import io
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path

import httpx
import pytest

from icarus.agents.data import backfill
from icarus.agents.data.cache import CachedDailySource, DailyBarCache
from icarus.agents.data.corpactions import Split, back_adjust, fetch_splits
from icarus.agents.data.nse import NseBhavcopySource, bhavcopy_url, legacy_bhavcopy_url
from icarus.agents.data.quality import DataQualityGate, Verdict
from icarus.agents.data.universe import PointInTimeUniverse, trailing_sessions
from icarus.agents.data.yahoo import YahooDailySource
from icarus.common.calendar import (
    CalendarDataMissing,
    clear_derived_sessions,
    is_nse_trading_day,
    register_derived_sessions,
)
from icarus.common.config import DataQuality, Universe
from icarus.common.schemas import SchemaError
from icarus.common.types import OHLCV, AssetClass, Candle

_CRORE = Decimal("10000000")


@pytest.fixture(autouse=True)
def _clean_calendar() -> object:
    """Derived calendars are process-global; keep tests from leaking into each other."""
    clear_derived_sessions()
    yield
    clear_derived_sessions()


def _universe_cfg(**overrides: float | int | str) -> Universe:
    base: dict[str, float | int | str] = {
        "min_avg_turnover_inr": 500_000_000.0,  # Rs 50cr
        "turnover_window_sessions": 3,
        "min_close_inr": 30.0,
        "dividend_convention": "price_return",
        "history_years": 5,
    }
    base.update(overrides)
    return Universe(**base)


# --------------------------------------------------------------------------------------
# Bhavcopy fixtures — both archive layouts
# --------------------------------------------------------------------------------------
_UDIFF_COLS = [
    "TradDt", "TckrSymb", "SctySrs", "FinInstrmTp",
    "OpnPric", "HghPric", "LwPric", "ClsPric", "TtlTradgVol", "TtlTrfVal",
]  # fmt: skip
_LEGACY_COLS = [
    "SYMBOL", "SERIES", "OPEN", "HIGH", "LOW", "CLOSE",
    "TOTTRDQTY", "TOTTRDVAL", "TIMESTAMP", "ISIN",
]  # fmt: skip


def _udiff_zip(names: dict[str, tuple[str, str]]) -> bytes:
    """``{ticker: (close, turnover)}`` -> a UDiFF bhavcopy zip."""
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_UDIFF_COLS)
    writer.writeheader()
    for ticker, (close, turnover) in names.items():
        writer.writerow(
            {
                "TradDt": "2026-07-24",
                "TckrSymb": ticker,
                "SctySrs": "EQ",
                "FinInstrmTp": "STK",
                "OpnPric": close,
                "HghPric": close,
                "LwPric": close,
                "ClsPric": close,
                "TtlTradgVol": "1000",
                "TtlTrfVal": turnover,
            }
        )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("bhav.csv", buf.getvalue())
    return out.getvalue()


def _legacy_zip(names: dict[str, tuple[str, str]]) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_LEGACY_COLS)
    writer.writeheader()
    for ticker, (close, turnover) in names.items():
        writer.writerow(
            {
                "SYMBOL": ticker,
                "SERIES": "EQ",
                "OPEN": close,
                "HIGH": close,
                "LOW": close,
                "CLOSE": close,
                "TOTTRDQTY": "1000",
                "TOTTRDVAL": turnover,
                "TIMESTAMP": "23-JUL-2021",
                "ISIN": "INE002A01018",
            }
        )
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("cm23JUL2021bhav.csv", buf.getvalue())
    return out.getvalue()


def _client(handler: object) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))  # type: ignore[arg-type]


# --------------------------------------------------------------------------------------
# Legacy archive support
# --------------------------------------------------------------------------------------
def test_legacy_url_spells_the_month_explicitly() -> None:
    """Verified live 2026-07-29. %b is locale-dependent and would 404 forever on some machines."""
    assert legacy_bhavcopy_url(date(2021, 7, 23)).endswith(
        "/EQUITIES/2021/JUL/cm23JUL2021bhav.csv.zip"
    )


async def test_falls_back_to_the_legacy_archive(tmp_path: Path) -> None:
    """UDiFF only reaches back to mid-2024; older sessions must still load."""
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        requested.append(url)
        if url == bhavcopy_url(date(2026, 7, 24)):
            return httpx.Response(404)
        return httpx.Response(200, content=_legacy_zip({"RELIANCE": ("2105.70", "9717885501")}))

    async with _client(handler) as http:
        rows = await NseBhavcopySource(http, tmp_path).day_rows(date(2026, 7, 24))

    assert len(requested) == 2  # UDiFF tried first, then legacy
    assert rows["RELIANCE"][3] == "2105.70"
    assert rows["RELIANCE"][5] == "9717885501"  # turnover carried through


async def test_missing_from_both_archives_still_raises(tmp_path: Path) -> None:
    from icarus.agents.data.source import SourceUnavailableError

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with _client(handler) as http:
        with pytest.raises(SourceUnavailableError, match="both archives"):
            await NseBhavcopySource(http, tmp_path).day_rows(date(2026, 7, 24))


async def test_unknown_layout_halts_rather_than_guessing(tmp_path: Path) -> None:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["TICKER", "PRICE"])
    writer.writeheader()
    writer.writerow({"TICKER": "X", "PRICE": "1"})
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("weird.csv", buf.getvalue())

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=out.getvalue())

    async with _client(handler) as http:
        with pytest.raises(SchemaError, match="neither archive layout"):
            await NseBhavcopySource(http, tmp_path).day_rows(date(2026, 7, 24))


# --------------------------------------------------------------------------------------
# Derived calendar
# --------------------------------------------------------------------------------------
def test_unknown_year_raises_rather_than_assuming() -> None:
    with pytest.raises(CalendarDataMissing):
        is_nse_trading_day(date(2021, 7, 23))


def test_derived_sessions_answer_for_a_year_with_no_holiday_list() -> None:
    register_derived_sessions(
        2021, frozenset({date(2021, 7, 22), date(2021, 7, 23)}), complete_year=False
    )
    assert is_nse_trading_day(date(2021, 7, 23))
    assert not is_nse_trading_day(date(2021, 7, 26))  # scanned range said no file that day


def test_verified_holidays_win_over_derived_sessions() -> None:
    """2026 has a cross-checked list; a bad derived artifact must not override it."""
    register_derived_sessions(2026, frozenset({date(2026, 1, 26)}), complete_year=False)
    assert not is_nse_trading_day(date(2026, 1, 26))  # Republic Day, from the verified list


def test_a_complete_year_with_too_few_sessions_is_refused() -> None:
    """An incomplete archive must not become a calendar claiming the market was shut for months."""
    with pytest.raises(CalendarDataMissing, match="archive is incomplete"):
        register_derived_sessions(2021, frozenset({date(2021, 7, 23)}), complete_year=True)


def test_a_partial_year_is_accepted_without_the_count_check() -> None:
    register_derived_sessions(2021, frozenset({date(2021, 7, 23)}), complete_year=False)
    assert is_nse_trading_day(date(2021, 7, 23))


async def test_backfill_scan_records_published_days_as_sessions(tmp_path: Path) -> None:
    """The exchange not publishing an end-of-day file is the evidence the market was shut."""
    published = {date(2026, 7, 22), date(2026, 7, 24)}

    def handler(request: httpx.Request) -> httpx.Response:
        stamp = str(request.url).split("_")[-3] if "BhavCopy" in str(request.url) else ""
        day = datetime.strptime(stamp, "%Y%m%d").date() if stamp else None
        if day in published:
            return httpx.Response(200, content=_udiff_zip({"X": ("100", "1")}))
        return httpx.Response(404)

    async with _client(handler) as http:
        result = await backfill.scan(
            NseBhavcopySource(http, tmp_path), date(2026, 7, 22), date(2026, 7, 24)
        )

    assert set(result.sessions) == published
    assert set(result.closures) == {date(2026, 7, 23)}


def test_backfill_artifact_round_trips(tmp_path: Path) -> None:
    result = backfill.BackfillResult(
        frm=date(2026, 7, 22),
        to=date(2026, 7, 24),
        sessions=(date(2026, 7, 22), date(2026, 7, 24)),
        closures=(date(2026, 7, 23),),
    )
    path = tmp_path / "calendar.json"
    backfill.save(result, path)
    assert backfill.load(path) == result


def test_complete_years_only_counts_fully_scanned_ones() -> None:
    result = backfill.BackfillResult(
        frm=date(2026, 7, 1),
        to=date(2026, 7, 31),
        sessions=(date(2026, 7, 22),),
        closures=(),
    )
    assert result.complete_years() == frozenset()


# --------------------------------------------------------------------------------------
# Point-in-time universe
# --------------------------------------------------------------------------------------
_WINDOW = [date(2026, 7, 22), date(2026, 7, 23), date(2026, 7, 24)]


def _universe_client(
    by_day: dict[date, dict[str, tuple[str, str]]], seen: list[date] | None = None
) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        stamp = str(request.url).split("_")[-3]
        day = datetime.strptime(stamp, "%Y%m%d").date()
        if seen is not None:
            seen.append(day)
        rows = by_day.get(day)
        if rows is None:
            return httpx.Response(404)
        return httpx.Response(200, content=_udiff_zip(rows))

    return _client(handler)


async def test_universe_keeps_liquid_names_and_drops_illiquid_ones(tmp_path: Path) -> None:
    liquid = ("500", str(100 * _CRORE))
    thin = ("500", str(1 * _CRORE))
    by_day = {d: {"BIG": liquid, "THIN": thin} for d in _WINDOW}

    async with _universe_client(by_day) as http:
        universe = PointInTimeUniverse(NseBhavcopySource(http, tmp_path), _universe_cfg())
        snapshot = await universe.as_of(date(2026, 7, 24))

    assert snapshot.symbols == {"BIG"}
    assert snapshot.considered == 2


async def test_universe_bans_the_penny_names(tmp_path: Path) -> None:
    """The floor is on price, and it applies even to a name with enormous turnover."""
    by_day = {
        d: {"BIG": ("500", str(100 * _CRORE)), "PENNY": ("9", str(500 * _CRORE))} for d in _WINDOW
    }

    async with _universe_client(by_day) as http:
        universe = PointInTimeUniverse(NseBhavcopySource(http, tmp_path), _universe_cfg())
        snapshot = await universe.as_of(date(2026, 7, 24))

    assert snapshot.symbols == {"BIG"}


async def test_universe_never_reads_a_session_after_the_as_of_date(tmp_path: Path) -> None:
    """The mechanical proof of point-in-time: no future file is even requested (§29.1)."""
    seen: list[date] = []
    by_day = {d: {"BIG": ("500", str(100 * _CRORE))} for d in [*_WINDOW, date(2026, 7, 27)]}

    async with _universe_client(by_day, seen) as http:
        universe = PointInTimeUniverse(NseBhavcopySource(http, tmp_path), _universe_cfg())
        await universe.as_of(date(2026, 7, 24))

    assert seen, "expected the builder to read some sessions"
    assert max(seen) <= date(2026, 7, 24)


async def test_a_delisted_name_simply_leaves_the_universe(tmp_path: Path) -> None:
    """No delisting feed needed: absence from the session file IS the delisting (§29.2)."""
    liquid = ("500", str(100 * _CRORE))
    by_day = {
        date(2026, 7, 22): {"BIG": liquid, "GONE": liquid},
        date(2026, 7, 23): {"BIG": liquid, "GONE": liquid},
        date(2026, 7, 24): {"BIG": liquid},  # GONE stopped trading
    }

    async with _universe_client(by_day) as http:
        universe = PointInTimeUniverse(NseBhavcopySource(http, tmp_path), _universe_cfg())
        snapshot = await universe.as_of(date(2026, 7, 24))

    assert snapshot.symbols == {"BIG"}


async def test_a_freshly_listed_name_has_no_trailing_liquidity_yet(tmp_path: Path) -> None:
    """An IPO has no trailing record; inventing one would be fabricating history."""
    liquid = ("500", str(100 * _CRORE))
    by_day = {
        date(2026, 7, 22): {"BIG": liquid},
        date(2026, 7, 23): {"BIG": liquid},
        date(2026, 7, 24): {"BIG": liquid, "NEWIPO": liquid},
    }

    async with _universe_client(by_day) as http:
        universe = PointInTimeUniverse(NseBhavcopySource(http, tmp_path), _universe_cfg())
        snapshot = await universe.as_of(date(2026, 7, 24))

    assert snapshot.symbols == {"BIG"}


async def test_universe_records_what_each_name_qualified_on(tmp_path: Path) -> None:
    by_day = {d: {"BIG": ("500", str(100 * _CRORE))} for d in _WINDOW}

    async with _universe_client(by_day) as http:
        universe = PointInTimeUniverse(NseBhavcopySource(http, tmp_path), _universe_cfg())
        snapshot = await universe.as_of(date(2026, 7, 24))

    member = snapshot.members[0]
    assert member.close == Decimal("500")
    assert member.avg_turnover == 100 * _CRORE
    assert "BIG" in snapshot
    assert "BIG.NS" in snapshot  # accepts the Yahoo-style symbol too


def test_trailing_sessions_walks_backwards_only() -> None:
    sessions = trailing_sessions(date(2026, 7, 27), 3)
    assert sessions == [date(2026, 7, 23), date(2026, 7, 24), date(2026, 7, 27)]
    assert max(sessions) == date(2026, 7, 27)


def test_trailing_sessions_refuses_a_non_trading_day() -> None:
    with pytest.raises(ValueError, match="not an NSE trading day"):
        trailing_sessions(date(2026, 7, 25), 3)  # Saturday


async def test_sources_declare_whether_they_are_already_split_adjusted(tmp_path: Path) -> None:
    """Verified live 2026-07-29. Getting this backwards double-adjusts every historical price
    into a smooth, plausible, wrong series — so each source must state it explicitly."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"chart": {"result": []}})

    async with _client(handler) as http:
        assert YahooDailySource(http).prices_are_split_adjusted is True
        assert NseBhavcopySource(http, tmp_path).prices_are_split_adjusted is False
        # The cache wrapper must not lose the flag on the way through.
        wrapped = CachedDailySource(NseBhavcopySource(http, tmp_path), DailyBarCache(tmp_path))
        assert wrapped.prices_are_split_adjusted is False


def test_config_rejects_a_disabled_penny_ban() -> None:
    with pytest.raises(ValueError, match="penny"):
        _universe_cfg(min_close_inr=1.0)


def test_config_rejects_an_unknown_dividend_convention() -> None:
    with pytest.raises(ValueError, match="dividend_convention"):
        _universe_cfg(dividend_convention="mixed")


# --------------------------------------------------------------------------------------
# Corporate actions
# --------------------------------------------------------------------------------------
def _bar(day: date, price: str, volume: str = "1000") -> Candle:
    value = Decimal(price)
    return Candle(
        ts=datetime.combine(day, datetime.min.time(), tzinfo=UTC).replace(hour=3, minute=45),
        ohlcv=OHLCV(open=value, high=value, low=value, close=value, volume=Decimal(volume)),
    )


def test_back_adjust_removes_the_artificial_split_gap() -> None:
    """The 1.1c acceptance criterion: a known split date generates no signal."""
    split_day = date(2026, 7, 23)
    raw = [
        _bar(date(2026, 7, 21), "1000"),
        _bar(date(2026, 7, 22), "1000"),
        _bar(split_day, "500"),  # 1:2 split — price halves, nothing real changed
        _bar(date(2026, 7, 24), "505"),
    ]
    raw_move = (raw[2].ohlcv.close - raw[1].ohlcv.close) / raw[1].ohlcv.close
    assert raw_move == Decimal("-0.5")  # the artifact a strategy would trade

    adjusted = back_adjust(raw, [Split(ex_date=split_day, ratio=Decimal(2))])
    move = (adjusted[2].ohlcv.close - adjusted[1].ohlcv.close) / adjusted[1].ohlcv.close

    assert move == 0  # continuous series -> no signal
    assert adjusted[0].ohlcv.close == Decimal("500")  # pre-split prices rescaled
    assert adjusted[3].ohlcv.close == Decimal("505")  # post-split prices untouched


def test_back_adjust_preserves_traded_value() -> None:
    """Prices divide, volumes multiply — the rupees that changed hands stay the same."""
    raw = [_bar(date(2026, 7, 21), "1000", volume="500")]
    adjusted = back_adjust(raw, [Split(ex_date=date(2026, 7, 23), ratio=Decimal(2))])
    before = raw[0].ohlcv.close * raw[0].ohlcv.volume
    after = adjusted[0].ohlcv.close * adjusted[0].ohlcv.volume
    assert before == after


def test_back_adjusted_series_no_longer_trips_the_qa_quarantine() -> None:
    """1.1b quarantines a >50% move as a probable unadjusted action. 1.1c is what resolves it."""
    split_day = date(2026, 7, 23)
    raw = [_bar(date(2026, 7, 22), "1000"), _bar(split_day, "500")]
    cfg = DataQuality(
        atr_window=14,
        max_bar_move_atr=8.0,
        max_single_bar_move=0.5,
        min_day_score=0.98,
        stale_sessions_symbol_veto=2,
        stale_plane_halt_ratio=0.5,
    )

    unadjusted_gate = DataQualityGate(cfg)
    verdicts = [unadjusted_gate.assess("equity:X", AssetClass.EQUITY, bar).verdict for bar in raw]
    assert verdicts[1] is Verdict.QUARANTINE

    adjusted_gate = DataQualityGate(cfg)
    adjusted = back_adjust(raw, [Split(ex_date=split_day, ratio=Decimal(2))])
    assert all(
        adjusted_gate.assess("equity:Y", AssetClass.EQUITY, bar).accepted for bar in adjusted
    )


def test_multiple_splits_compound() -> None:
    raw = [_bar(date(2026, 1, 5), "4000"), _bar(date(2026, 7, 24), "1000")]
    adjusted = back_adjust(
        raw,
        [
            Split(ex_date=date(2026, 3, 2), ratio=Decimal(2)),
            Split(ex_date=date(2026, 6, 1), ratio=Decimal(2)),
        ],
    )
    assert adjusted[0].ohlcv.close == Decimal("1000")  # divided by 2 x 2
    assert adjusted[1].ohlcv.close == Decimal("1000")  # after both -> untouched


def test_no_splits_is_a_passthrough() -> None:
    raw = [_bar(date(2026, 7, 24), "1000")]
    assert back_adjust(raw, []) == raw


def test_reverse_split_scales_the_other_way() -> None:
    raw = [_bar(date(2026, 7, 21), "10")]
    adjusted = back_adjust(raw, [Split(ex_date=date(2026, 7, 23), ratio=Decimal(1) / Decimal(3))])
    assert adjusted[0].ohlcv.close == Decimal(30)


def test_split_ratio_must_be_positive() -> None:
    with pytest.raises(ValueError, match="positive"):
        Split(ex_date=date(2026, 7, 23), ratio=Decimal(0))


async def test_fetch_splits_parses_the_verified_event_shape() -> None:
    """Shape verified live 2026-07-29: RELIANCE returned 3 splits and 22 dividends."""
    payload = {
        "chart": {
            "result": [
                {
                    "events": {
                        "splits": {
                            "1259207100": {
                                "date": 1259207100,
                                "numerator": 2.0,
                                "denominator": 1.0,
                                "splitRatio": "2:1",
                            }
                        },
                        "dividends": {"1115869500": {"amount": 0.93, "date": 1115869500}},
                    }
                }
            ]
        }
    }

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with _client(handler) as http:
        splits = await fetch_splits(http, "RELIANCE.NS", date(2005, 1, 1), date(2026, 7, 24))

    assert len(splits) == 1  # dividends deliberately discarded — price-return convention
    assert splits[0].ratio == Decimal(2)
    assert splits[0].ex_date == date(2009, 11, 26)


async def test_fetch_splits_returns_empty_when_there_were_no_actions() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"chart": {"result": [{}]}})

    async with _client(handler) as http:
        assert await fetch_splits(http, "X", date(2026, 1, 1), date(2026, 7, 24)) == []


async def test_malformed_split_entry_raises_rather_than_being_skipped() -> None:
    """Skipping one would leave an unadjusted jump that looks exactly like a crash."""
    payload = {"chart": {"result": [{"events": {"splits": {"1": {"date": 1, "numerator": 2.0}}}}]}}

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with _client(handler) as http:
        with pytest.raises(SchemaError, match="malformed split"):
            await fetch_splits(http, "X", date(2026, 1, 1), date(2026, 7, 24))
