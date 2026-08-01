"""Tests for the NSE delivery-data source (task 1.1d).

Three things here matter more than the rest:

* **Both archive formats decode identically.** The modern CSV and the legacy MTO layout carry the
  same facts in different shapes, and the legacy one must be parsed *by position* — its header
  names six columns while its data rows carry seven. A header-driven parse misaligns every field
  after the symbol and produces plausible, wrong numbers.
* **The published percentage is cross-checked against the quantities.** This is the schema-drift
  detector: if NSE reorders columns, it must fail loudly rather than feed a wrong number to a
  signal (invariant #10).
* **"Not applicable" is not zero.** Non-deliverable series publish ``-``. Defaulting those to zero
  would assert "nobody took delivery", which is a different and false claim.

Fixtures below are trimmed verbatim from the live archive (2026-07-31), including the leading
space after each comma in the modern file — that whitespace is real and the parser must strip it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import httpx
import pytest

from icarus.agents.data.delivery import (
    DeliveryRecord,
    NseDeliverySource,
    delivery_url,
    legacy_delivery_url,
)
from icarus.agents.data.source import SourceUnavailableError
from icarus.common.calendar import clear_derived_sessions, register_derived_sessions
from icarus.common.schemas import SchemaError

# Verbatim from sec_bhavdata_full_28072026.csv (a Tuesday, NSE trading day).
MODERN_CSV = (
    "SYMBOL, SERIES, DATE1, PREV_CLOSE, OPEN_PRICE, HIGH_PRICE, LOW_PRICE, LAST_PRICE, "
    "CLOSE_PRICE, AVG_PRICE, TTL_TRD_QNTY, TURNOVER_LACS, NO_OF_TRADES, DELIV_QTY, DELIV_PER\n"
    "20MICRONS, EQ, 28-Jul-2026, 204.00, 204.05, 206.99, 198.14, 201.10, 201.63, 202.18, "
    "156781, 316.97, 3747, 66172, 42.21\n"
    "360ONE, EQ, 28-Jul-2026, 1132.70, 1139.50, 1139.50, 1122.40, 1126.00, 1128.30, 1129.62, "
    "617932, 6980.29, 24145, 312637, 50.59\n"
    # A non-deliverable government security: delivery columns carry '-'.
    "1018GS2026, GS, 28-Jul-2026, 104.29, 104.00, 104.20, 104.00, 104.15, 104.15, 104.10, "
    "500, 0.52, 3, -, -\n"
)

# Verbatim from MTO_13072016.DAT — four preamble lines, then record-type-20 rows.
LEGACY_DAT = (
    "Security Wise Delivery Position - Compulsory Rolling Settlement\n"
    "10,MTO,13072016,506692955,0001622\n"
    "Trade Date <13-JUL-2016>,Settlement Type <N>,Settlement No <2016131>,"
    "Settlement Date <15-JUL-2016>\n"
    "Record Type,Sr No,Name of Security,Quantity Traded,Deliverable Quantity"
    "(gross across client level),% of Deliverable Quantity to Traded Quantity\n"
    "20,1,20MICRONS,EQ,22105,14740,66.68\n"
    "20,2,3IINFOTECH,EQ,1819001,1074427,59.07\n"
    "20,3,3MINDIA,EQ,266,190,71.43\n"
)

MODERN_DAY = date(2026, 7, 28)
LEGACY_DAY = date(2016, 7, 13)


@pytest.fixture
def legacy_calendar() -> object:
    """Teach the calendar that 2016-07-13 was a session.

    The calendar ships a *verified* holiday list only for the current year and otherwise refuses to
    guess (`CalendarDataMissing`) — deliberately, since "I don't know whether the market was open"
    must never silently become "it was". Historical years are supplied from the archive by
    :mod:`icarus.agents.data.backfill`; this registers one day the same way, so the test exercises
    the real mechanism rather than bypassing it.
    """
    register_derived_sessions(2016, frozenset({LEGACY_DAY}), complete_year=False)
    yield
    clear_derived_sessions()


def _source(handler: object) -> NseDeliverySource:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return NseDeliverySource(httpx.AsyncClient(transport=transport))


def _serves(body: str, *, only_legacy: bool = False) -> object:
    """A handler returning ``body``; ``only_legacy`` makes the modern URL 404 to force fallback."""

    def handler(request: httpx.Request) -> httpx.Response:
        if only_legacy and "sec_bhavdata_full" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, text=body)

    return handler


# --------------------------------------------------------------------------------------
# URL shapes — verified against the live archive
# --------------------------------------------------------------------------------------
def test_url_shapes_are_day_month_year() -> None:
    """DDMMYYYY, not YYYYMMDD. Getting this backwards 404s forever and looks like a data gap."""
    assert delivery_url(date(2026, 7, 28)).endswith("sec_bhavdata_full_28072026.csv")
    assert legacy_delivery_url(date(2016, 7, 13)).endswith("MTO_13072016.DAT")


# --------------------------------------------------------------------------------------
# The modern layout
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_modern_layout_parses_symbols_and_strips_whitespace() -> None:
    records = await _source(_serves(MODERN_CSV)).day_records(MODERN_DAY)
    micron = records["20MICRONS"]
    assert micron == DeliveryRecord(
        symbol="20MICRONS",
        series="EQ",
        traded_qty=156781,
        delivered_qty=66172,
        delivery_pct=Decimal("42.21"),
    )
    assert records["360ONE"].delivery_pct == Decimal("50.59")


@pytest.mark.asyncio
async def test_non_deliverable_series_is_skipped_not_zeroed() -> None:
    """'-' means delivery does not apply. A zero would assert nobody took delivery — false."""
    records = await _source(_serves(MODERN_CSV)).day_records(MODERN_DAY)
    assert "1018GS2026" not in records
    assert set(records) == {"20MICRONS", "360ONE"}


# --------------------------------------------------------------------------------------
# The legacy layout — parsed by POSITION, not by header
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_legacy_layout_parses_by_position(legacy_calendar: object) -> None:
    """The MTO header names 6 columns; data rows carry 7, because 'Name of Security' is symbol
    AND series. A header-driven parse would shift every field after the symbol."""
    records = await _source(_serves(LEGACY_DAT, only_legacy=True)).day_records(LEGACY_DAY)
    assert records["20MICRONS"] == DeliveryRecord(
        symbol="20MICRONS",
        series="EQ",
        traded_qty=22105,
        delivered_qty=14740,
        delivery_pct=Decimal("66.68"),
    )
    assert set(records) == {"20MICRONS", "3IINFOTECH", "3MINDIA"}


@pytest.mark.asyncio
async def test_legacy_preamble_lines_are_not_mistaken_for_data(legacy_calendar: object) -> None:
    records = await _source(_serves(LEGACY_DAT, only_legacy=True)).day_records(LEGACY_DAY)
    assert all(r.series == "EQ" for r in records.values())
    assert "MTO" not in records


@pytest.mark.asyncio
async def test_falls_back_to_legacy_without_a_hard_coded_cutover_date(
    legacy_calendar: object,
) -> None:
    """The modern archive starts mid-2019. Falling back on absence means the boundary never has to
    be encoded — and a date that moves later does not silently become a gap."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        if "sec_bhavdata_full" in str(request.url):
            return httpx.Response(404)
        return httpx.Response(200, text=LEGACY_DAT)

    records = await _source(handler).day_records(LEGACY_DAY)
    assert len(seen) == 2  # modern tried first, then legacy
    assert "sec_bhavdata_full" in seen[0]
    assert "MTO_" in seen[1]
    assert records["3MINDIA"].delivered_qty == 190


# --------------------------------------------------------------------------------------
# Failure and halt paths — the ones that matter most
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_missing_from_both_archives_raises_rather_than_returning_empty() -> None:
    """A silent skip leaves a hole indistinguishable from a holiday (§29.4)."""
    with pytest.raises(SourceUnavailableError, match="both archives"):
        await _source(lambda _r: httpx.Response(404)).day_records(MODERN_DAY)


@pytest.mark.asyncio
async def test_non_trading_day_is_a_caller_bug_not_an_empty_result() -> None:
    saturday = date(2026, 7, 25)
    with pytest.raises(ValueError, match="not an NSE trading day"):
        await _source(_serves(MODERN_CSV)).day_records(saturday)


@pytest.mark.asyncio
async def test_reordered_columns_are_caught_by_the_percentage_cross_check() -> None:
    """THE schema-drift test, and the subtle case.

    Here DELIV_QTY has slipped one column left and is reading NO_OF_TRADES (3747). Delivered stays
    *below* traded, so the volume guard is satisfied and the row parses cleanly — it is simply
    wrong by a factor of eighteen. Only cross-checking the published percentage against the
    quantities catches it: 3747/156781 = 2.39%, against a published 42.21.
    """
    drifted = (
        "SYMBOL, SERIES, TTL_TRD_QNTY, DELIV_QTY, DELIV_PER\n20MICRONS, EQ, 156781, 3747, 42.21\n"
    )
    with pytest.raises(SchemaError, match="column layout may have changed"):
        await _source(_serves(drifted)).day_records(MODERN_DAY)


@pytest.mark.asyncio
async def test_transposed_quantities_are_caught_by_the_volume_guard() -> None:
    """The blunter drift: TTL_TRD_QNTY and DELIV_QTY swapped outright. Caught earlier, by the
    physical impossibility of delivering more shares than changed hands."""
    transposed = (
        "SYMBOL, SERIES, TTL_TRD_QNTY, DELIV_QTY, DELIV_PER\n20MICRONS, EQ, 66172, 156781, 42.21\n"
    )
    with pytest.raises(SchemaError, match="cannot exceed volume"):
        await _source(_serves(transposed)).day_records(MODERN_DAY)


@pytest.mark.asyncio
async def test_delivery_exceeding_volume_is_rejected() -> None:
    impossible = (
        "SYMBOL, SERIES, TTL_TRD_QNTY, DELIV_QTY, DELIV_PER\n"
        "FAKE, EQ, 100, 150, 150.00\n"  # internally consistent, physically impossible
    )
    with pytest.raises(SchemaError, match="cannot exceed volume"):
        await _source(_serves(impossible)).day_records(MODERN_DAY)


@pytest.mark.asyncio
async def test_missing_columns_raise_schema_error() -> None:
    with pytest.raises(SchemaError, match="missing columns"):
        await _source(_serves("SYMBOL, SERIES, DELIV_PER\nX, EQ, 10.0\n")).day_records(MODERN_DAY)


@pytest.mark.asyncio
async def test_unrecognised_layout_raises_rather_than_guessing() -> None:
    with pytest.raises(SchemaError, match="unrecognised layout"):
        await _source(_serves("some,other,file\n1,2,3\n")).day_records(MODERN_DAY)


@pytest.mark.asyncio
async def test_empty_file_raises() -> None:
    with pytest.raises(SchemaError, match="empty file"):
        await _source(_serves("   \n")).day_records(MODERN_DAY)


@pytest.mark.asyncio
async def test_unparseable_quantity_raises_rather_than_defaulting() -> None:
    with pytest.raises(SchemaError, match="unparseable row"):
        await _source(
            _serves("SYMBOL, SERIES, TTL_TRD_QNTY, DELIV_QTY, DELIV_PER\nX, EQ, lots, 5, 50.00\n")
        ).day_records(MODERN_DAY)


# --------------------------------------------------------------------------------------
# Caching + convenience
# --------------------------------------------------------------------------------------
@pytest.mark.asyncio
async def test_one_download_serves_every_symbol_for_the_day() -> None:
    """One file per session, all symbols — so the day is the cache unit, not the symbol. Without
    this a multi-symbol backfill would issue one request per symbol per day."""
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, text=MODERN_CSV)

    src = _source(handler)
    assert (await src.for_symbol("20MICRONS", MODERN_DAY)) is not None
    assert (await src.for_symbol("360ONE", MODERN_DAY)) is not None
    await src.day_records(MODERN_DAY)
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_symbol_absent_from_the_session_is_none_not_an_error() -> None:
    """Not trading that day is ordinary, unlike a missing file."""
    src = _source(_serves(MODERN_CSV))
    assert await src.for_symbol("DID_NOT_TRADE", MODERN_DAY) is None


@pytest.mark.asyncio
async def test_symbol_lookup_is_case_insensitive() -> None:
    src = _source(_serves(MODERN_CSV))
    assert (await src.for_symbol("20microns", MODERN_DAY)) == (
        await src.for_symbol("20MICRONS", MODERN_DAY)
    )
