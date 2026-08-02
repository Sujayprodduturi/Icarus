"""Tests for the NSE F&O ban-list source (task 1.1d).

The ban list is a **compliance boundary**, not a signal, and that changes what the tests are for.
Three properties matter most:

* **A missing file must never read as "nothing is banned."** That is the single most dangerous
  wrong answer this module can give — it turns an unreadable file into blanket permission to trade
  (invariant #10). ``NIL`` is NSE *stating* the list is empty; absence is not.
* **``NIL`` and a populated list must not be confusable in either direction.** Four header
  spellings are real in the archive, and every one of them has to land on the right side.
* **A truncated file must not look like a shorter valid list.** It parses cleanly and reads as
  correct, so the serial-number run is what catches it.

Fixtures are verbatim from the live archive (2026-08-02).
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from icarus.agents.data.fetch import RateLimiter
from icarus.agents.data.fnoban import NseFnoBanSource, ban_url
from icarus.agents.data.source import SourceUnavailableError
from icarus.common.calendar import clear_derived_sessions, register_derived_sessions
from icarus.common.schemas import SchemaError

# Verbatim from fo_secban_15072019.csv — note the bare trailing space after the colon.
BAN_2019 = (
    "Securities in Ban For Trade Date 15-JUL-2019: \n1,DHFL\n2,IDBI\n3,RELCAPITAL\n4,RELINFRA\n"
)

# Verbatim from fo_secban_28072026.csv.
BAN_NIL = "Securities in Ban For Trade Date 28-JUL-2026: NIL\n"

DAY_2019 = date(2019, 7, 15)
DAY_2026 = date(2026, 7, 28)


@pytest.fixture
def calendar_2019() -> object:
    """Teach the calendar that 2019-07-15 was a session (see `test_delivery.py` for why)."""
    register_derived_sessions(2019, frozenset({DAY_2019}), complete_year=False)
    yield
    clear_derived_sessions()


def _source(handler: object) -> NseFnoBanSource:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return NseFnoBanSource(httpx.AsyncClient(transport=transport), RateLimiter(1000.0))


def _serves(body: str) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    return handler


# --------------------------------------------------------------------------------------------
# Reading the list
# --------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_populated_list_parses(calendar_2019: object) -> None:
    banned = await _source(_serves(BAN_2019)).banned_on(DAY_2019)
    assert banned == {"DHFL", "IDBI", "RELCAPITAL", "RELINFRA"}


@pytest.mark.asyncio
async def test_nil_means_an_empty_list_not_an_error() -> None:
    """NSE stating "no securities are banned today" is data, and the common case."""
    assert (await _source(_serves(BAN_NIL)).banned_on(DAY_2026)) == frozenset()


@pytest.mark.parametrize(
    "header",
    [
        "Securities in Ban For Trade Date 28-JUL-2026: NIL",  # 2019-2026
        "Securities in Ban For Trade Date 28-JUL-2026:NIL",  # 2016, no space
        "Securities in Ban For Trade Date 28-JUL-2026:NIL,",  # trailing comma
        "Securities in Ban For Trade Date 28-July-2026: NIL",  # full month name
    ],
)
@pytest.mark.asyncio
async def test_every_nil_spelling_is_understood(header: str) -> None:
    assert (await _source(_serves(header + "\n")).banned_on(DAY_2026)) == frozenset()


@pytest.mark.asyncio
async def test_a_bare_colon_header_with_rows_parses(calendar_2019: object) -> None:
    """The 2015 spelling: "...:," followed by the securities."""
    body = "Securities in Ban For Trade Date 15-JUL-2019:,\n1,DHFL\n"
    assert (await _source(_serves(body)).banned_on(DAY_2019)) == {"DHFL"}


@pytest.mark.asyncio
async def test_symbols_are_upper_cased(calendar_2019: object) -> None:
    body = "Securities in Ban For Trade Date 15-JUL-2019: \n1,dhfl\n"
    assert (await _source(_serves(body)).banned_on(DAY_2019)) == {"DHFL"}


# --------------------------------------------------------------------------------------------
# The veto
# --------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_entry_is_blocked_for_a_banned_security(calendar_2019: object) -> None:
    source = _source(_serves(BAN_2019))
    assert await source.fno_entry_blocked("DHFL", DAY_2019) is True


@pytest.mark.asyncio
async def test_entry_is_allowed_for_an_unbanned_security(calendar_2019: object) -> None:
    source = _source(_serves(BAN_2019))
    assert await source.fno_entry_blocked("RELIANCE", DAY_2019) is False


@pytest.mark.asyncio
async def test_the_veto_is_case_insensitive(calendar_2019: object) -> None:
    """Symbol casing varies across our own feeds; a case slip must not silently unblock."""
    source = _source(_serves(BAN_2019))
    assert await source.fno_entry_blocked("dhfl", DAY_2019) is True


# --------------------------------------------------------------------------------------------
# Refusals — the half that matters most for a compliance feed
# --------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_missing_file_raises_rather_than_reporting_nothing_banned() -> None:
    """The dangerous failure: an unreadable file must not become permission to trade."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with pytest.raises(SourceUnavailableError):
        await _source(handler).banned_on(DAY_2026)


@pytest.mark.asyncio
async def test_a_file_for_the_wrong_session_is_rejected() -> None:
    """A stale ban list is well-formed; acting on it is both a breach and a needless block."""
    body = "Securities in Ban For Trade Date 27-JUL-2026: NIL\n"
    with pytest.raises(SchemaError, match="file is for 2026-07-27"):
        await _source(_serves(body)).banned_on(DAY_2026)


@pytest.mark.asyncio
async def test_nil_contradicted_by_listed_securities_is_rejected() -> None:
    body = "Securities in Ban For Trade Date 28-JUL-2026: NIL\n1,DHFL\n"
    with pytest.raises(SchemaError, match="declares NIL"):
        await _source(_serves(body)).banned_on(DAY_2026)


@pytest.mark.asyncio
async def test_neither_nil_nor_securities_is_rejected() -> None:
    """Ambiguous: it could be an empty list or a truncated one, and those differ enormously."""
    body = "Securities in Ban For Trade Date 28-JUL-2026: \n"
    with pytest.raises(SchemaError, match="no NIL declared"):
        await _source(_serves(body)).banned_on(DAY_2026)


@pytest.mark.asyncio
async def test_a_gap_in_the_serial_numbers_is_rejected() -> None:
    """A truncated list parses cleanly and reads as a valid, shorter one. The run catches it."""
    body = "Securities in Ban For Trade Date 28-JUL-2026: \n1,DHFL\n3,IDBI\n"
    with pytest.raises(SchemaError, match="not sequential"):
        await _source(_serves(body)).banned_on(DAY_2026)


@pytest.mark.asyncio
async def test_a_duplicated_security_is_rejected() -> None:
    body = "Securities in Ban For Trade Date 28-JUL-2026: \n1,DHFL\n2,DHFL\n"
    with pytest.raises(SchemaError, match="listed twice"):
        await _source(_serves(body)).banned_on(DAY_2026)


@pytest.mark.asyncio
async def test_an_unrecognised_header_is_rejected() -> None:
    with pytest.raises(SchemaError, match="unrecognised header"):
        await _source(_serves("Banned Securities 28-JUL-2026\n1,DHFL\n")).banned_on(DAY_2026)


@pytest.mark.asyncio
async def test_an_impossible_header_date_is_rejected() -> None:
    body = "Securities in Ban For Trade Date 28-XXX-2026: NIL\n"
    with pytest.raises(SchemaError, match="not an NSE month name"):
        await _source(_serves(body)).banned_on(DAY_2026)


@pytest.mark.asyncio
async def test_a_malformed_row_is_rejected() -> None:
    body = "Securities in Ban For Trade Date 28-JUL-2026: \n1,DHFL,EQ,extra\n"
    with pytest.raises(SchemaError, match="expected '<serial>,<symbol>'"):
        await _source(_serves(body)).banned_on(DAY_2026)


@pytest.mark.asyncio
async def test_an_empty_file_is_rejected() -> None:
    with pytest.raises(SchemaError, match="empty file"):
        await _source(_serves("")).banned_on(DAY_2026)


@pytest.mark.asyncio
async def test_a_non_trading_day_is_a_caller_bug() -> None:
    with pytest.raises(ValueError, match="not an NSE trading day"):
        await _source(_serves(BAN_NIL)).banned_on(date(2026, 7, 26))


@pytest.mark.asyncio
async def test_a_session_is_fetched_once(calendar_2019: object) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text=BAN_2019)

    source = _source(handler)
    await source.banned_on(DAY_2019)
    await source.fno_entry_blocked("DHFL", DAY_2019)
    assert calls == 1


def test_the_url_carries_the_day() -> None:
    assert ban_url(DAY_2026).endswith("fo_secban_28072026.csv")
