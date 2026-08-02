"""Tests for the NSE participant-wise F&O source (task 1.1d).

Four things here carry more weight than the rest:

* **Both eras decode to the same numbers.** The 2015 and 2026 files differ in quoting and column
  padding but state the same facts, and a parser that only handles the recent one silently costs us
  a decade of the only feed with no Western equivalent.
* **The title date is checked, and NSE spells it four ways.** The guard catches being served the
  wrong session — a stale file is well-formed and looks entirely correct. But a strict format
  string would reject half of recorded history, so the tolerance is tested as carefully as the
  rejection.
* **The ``TOTAL`` reconciliation tolerates NSE's own off-by-one and nothing larger.** The 2026
  fixture is a real file that does not reconcile exactly; both halves of that boundary are pinned.
* **The two metrics cache separately.** OI and volume share a layout, a class and a memo — handing
  back volume for an open-interest request would be invisible in every number downstream.

Fixtures are verbatim from the live archive (2026-08-02), including the doubled quotes in the 2026
title and the trailing padding in its header — both are real and the parser must cope.
"""

from __future__ import annotations

from datetime import date

import httpx
import pytest

from icarus.agents.data.fetch import RateLimiter
from icarus.agents.data.participants import (
    NseParticipantSource,
    ParticipantCategory,
    ParticipantMetric,
    ParticipantRow,
    participant_url,
)
from icarus.agents.data.source import SourceUnavailableError
from icarus.common.calendar import clear_derived_sessions, register_derived_sessions
from icarus.common.schemas import SchemaError

# Verbatim from fao_participant_oi_28072026.csv. Note the *doubled* quotes around the title and the
# trailing padding on two header names. This file also carries NSE's own 1-contract discrepancy:
# Option Index Put Long sums to 2,697,953 against a published 2,697,954.
TITLE_2026 = (
    '""Participant wise Open Interest (no. of contracts) in Equity Derivatives '
    'as on Jul 28, 2026"",,,,,,,,,,,,,,'
)
BODY_2026 = (
    "Client Type,Future Index Long,Future Index Short,Future Stock Long,"
    "Future Stock Short       ,Option Index Call Long,Option Index Put Long,"
    "Option Index Call Short,Option Index Put Short,Option Stock Call Long,"
    "Option Stock Put Long,Option Stock Call Short,Option Stock Put Short,"
    "Total Long Contracts      ,Total Short Contracts\n"
    "Client,205837,52584,3072856,194452,1757449,1373039,1568403,1996366,"
    "1061765,457117,649152,709131,7928063,5170088\n"
    "DII,70112,15641,258616,4199595,3360,38202,80,125,964,32133,76768,4478,403387,4296687\n"
    "FII,21862,227463,3515193,2950984,304843,733568,552390,211668,"
    "61979,112413,109843,49406,4749858,4101754\n"
    "Pro,20281,22404,817070,318704,532086,553144,476865,489794,"
    "433001,601419,721946,440067,2957002,2469780\n"
    "TOTAL,318092,318092,7663735,7663735,2597738,2697954,2597738,2697954,"
    "1557709,1203082,1557709,1203082,16038310,16038310\n"
)
OI_2026 = f"{TITLE_2026}\n{BODY_2026}"

# Verbatim from fao_participant_oi_13072015.csv — single quotes, no padding, reconciles exactly.
TITLE_2015 = (
    '"Participant wise Open Interest (no. of contracts) in Equity Derivatives '
    'as on Jul 13, 2015",,,,,,,,,,,,,,'
)
BODY_2015 = (
    "Client Type,Future Index Long,Future Index Short,Future Stock Long,Future Stock Short,"
    "Option Index Call Long,Option Index Put Long,Option Index Call Short,Option Index Put Short,"
    "Option Stock Call Long,Option Stock Put Long,Option Stock Call Short,Option Stock Put Short,"
    "Total Long Contracts,Total Short Contracts\n"
    "Client,259335,549554,1384966,346076,769177,853955,1328889,1525227,"
    "279140,123048,210048,117225,3669621,4077019\n"
    "DII,41247,55777,24077,685190,248662,0,0,0,0,0,64,0,313986,741031\n"
    "FII,536248,246898,642473,1087932,968778,1395249,462138,450841,"
    "28050,21568,24666,18436,3592366,2290911\n"
    "Pro,92406,77007,240049,172367,393271,415879,588861,689015,"
    "66416,58522,138828,67477,1266543,1733555\n"
    "TOTAL,929236,929236,2291565,2291565,2379888,2665083,2379888,2665083,"
    "373606,203138,373606,203138,8842516,8842516\n"
)
OI_2015 = f"{TITLE_2015}\n{BODY_2015}"

DAY_2026 = date(2026, 7, 28)
DAY_2015 = date(2015, 7, 13)


@pytest.fixture
def calendar_2015() -> object:
    """Teach the calendar that 2015-07-13 was a session (see `test_delivery.py` for why)."""
    register_derived_sessions(2015, frozenset({DAY_2015}), complete_year=False)
    yield
    clear_derived_sessions()


def _source(handler: object) -> NseParticipantSource:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    # A fast limiter: these tests assert parsing, not politeness, and the real rate is exercised
    # by the RateLimiter's own tests.
    return NseParticipantSource(httpx.AsyncClient(transport=transport), RateLimiter(1000.0))


def _serves(body: str) -> object:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=body)

    return handler


def _with_title(title: str) -> str:
    """The 2026 file with its title line replaced — the title guards are tested through this."""
    return f"{title}\n{BODY_2026}"


async def _rows_2026(body: str) -> dict[ParticipantCategory, ParticipantRow]:
    source = _source(_serves(body))
    return await source.day_rows(DAY_2026, ParticipantMetric.OPEN_INTEREST)


# --------------------------------------------------------------------------------------------
# Happy path: both eras
# --------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_modern_file_parses_every_category() -> None:
    rows = await _rows_2026(OI_2026)
    assert set(rows) == set(ParticipantCategory)


@pytest.mark.asyncio
async def test_modern_values_match_the_published_file() -> None:
    rows = await _rows_2026(OI_2026)
    fii = rows[ParticipantCategory.FII]
    assert fii.future_index_long == 21862
    assert fii.future_index_short == 227463
    assert fii.total_long == 4749858


@pytest.mark.asyncio
async def test_trailing_padding_in_header_names_is_stripped() -> None:
    """ "Future Stock Short       " is real in the file; a naive parse loses the column."""
    rows = await _rows_2026(OI_2026)
    assert rows[ParticipantCategory.DII].future_stock_short == 4199595


@pytest.mark.asyncio
async def test_legacy_2015_file_parses_identically(calendar_2015: object) -> None:
    source = _source(_serves(OI_2015))
    rows = await source.day_rows(DAY_2015, ParticipantMetric.OPEN_INTEREST)
    assert rows[ParticipantCategory.FII].future_index_long == 536248


@pytest.mark.asyncio
async def test_net_positioning_opposes_retail_and_foreign_flow(calendar_2015: object) -> None:
    """The whole point of the feed: FII and Client sit on opposite sides of the same book."""
    source = _source(_serves(OI_2015))
    rows = await source.day_rows(DAY_2015, ParticipantMetric.OPEN_INTEREST)
    assert rows[ParticipantCategory.FII].net_future_index == 289350
    assert rows[ParticipantCategory.CLIENT].net_future_index == -290219


@pytest.mark.asyncio
async def test_net_future_stock_is_long_minus_short() -> None:
    rows = await _rows_2026(OI_2026)
    fii = rows[ParticipantCategory.FII]
    assert fii.net_future_stock == 3515193 - 2950984


# --------------------------------------------------------------------------------------------
# The title guard: date spellings it must accept, and the wrong-file cases it must reject
# --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "spelling",
    [
        "Jul 28, 2026",  # modern
        "Jul 28,2026",  # no space after the comma (2021-2024 files)
        "July 28, 2026",  # full month name (2018-2019 files)
        "Jul 28 2026",  # no comma at all (2020 files)
    ],
)
@pytest.mark.asyncio
async def test_every_title_date_spelling_nse_uses_is_accepted(spelling: str) -> None:
    """All four are real. A strict format string rejects half of recorded history."""
    rows = await _rows_2026(_with_title(f"Participant wise Open Interest as on {spelling},,,"))
    assert rows[ParticipantCategory.FII].future_index_long == 21862


@pytest.mark.asyncio
async def test_a_file_for_the_wrong_session_is_rejected() -> None:
    """Yesterday's positioning is well-formed and plausible — only the date betrays it."""
    with pytest.raises(SchemaError, match="file is for 2026-07-27"):
        await _rows_2026(_with_title("Participant wise Open Interest as on Jul 27, 2026,,,"))


@pytest.mark.asyncio
async def test_the_wrong_metric_is_rejected() -> None:
    """Volume served for an open-interest request: same shape, entirely different meaning."""
    with pytest.raises(SchemaError, match="Open Interest"):
        await _rows_2026(_with_title("Participant wise Trading Volume as on Jul 28, 2026,,,"))


@pytest.mark.asyncio
async def test_a_title_without_a_date_is_rejected() -> None:
    with pytest.raises(SchemaError, match="no 'as on <date>'"):
        await _rows_2026(_with_title("Participant wise Open Interest,,,"))


@pytest.mark.asyncio
async def test_an_impossible_title_date_is_rejected() -> None:
    with pytest.raises(SchemaError, match="unparseable title date"):
        await _rows_2026(_with_title("Participant wise Open Interest as on Jul 99, 2026,,,"))


# --------------------------------------------------------------------------------------------
# Structural guards
# --------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_renamed_column_is_rejected() -> None:
    """Parsing by name is the drift detector: a rename must halt, not read the neighbour."""
    with pytest.raises(SchemaError, match="missing columns"):
        await _rows_2026(OI_2026.replace("Future Index Long", "Fut Index Long"))


@pytest.mark.asyncio
async def test_a_new_participant_category_is_rejected() -> None:
    """The failure the TOTAL check exists for: a fifth category would silently vanish from sums."""
    with_extra = OI_2026.replace("TOTAL,", "Algo,1,1,1,1,1,1,1,1,1,1,1,1,1,1\nTOTAL,", 1)
    with pytest.raises(SchemaError, match="taxonomy may have changed"):
        await _rows_2026(with_extra)


@pytest.mark.asyncio
async def test_a_missing_category_is_rejected() -> None:
    """A partial book is worse than none: the absent slice is invisible in every number."""
    without_dii = "\n".join(line for line in OI_2026.splitlines() if not line.startswith("DII,"))
    with pytest.raises(SchemaError, match="expected categories"):
        await _rows_2026(without_dii + "\n")


@pytest.mark.asyncio
async def test_nse_own_one_contract_discrepancy_is_tolerated() -> None:
    """The 2026 fixture is a real file that does not reconcile exactly.

    Measured across 48 files, 2015->2026: 11 carry a discrepancy and the worst is 1 contract. An
    exact-equality check would halt the feed on live data.
    """
    rows = await _rows_2026(OI_2026)
    summed = sum(rows[c].option_index_put_long for c in ParticipantCategory)
    assert summed == 2697953  # while the file publishes 2,697,954
    assert set(rows) == set(ParticipantCategory)


@pytest.mark.asyncio
async def test_a_reconciliation_gap_beyond_tolerance_is_rejected() -> None:
    with pytest.raises(SchemaError, match="categories sum to"):
        await _rows_2026(OI_2026.replace(",16038310,16038310", ",99038310,16038310"))


@pytest.mark.asyncio
async def test_a_negative_contract_count_is_rejected() -> None:
    with pytest.raises(SchemaError, match="cannot be negative"):
        await _rows_2026(OI_2026.replace("Client,205837,", "Client,-205837,"))


@pytest.mark.asyncio
async def test_a_non_numeric_cell_is_rejected() -> None:
    with pytest.raises(SchemaError, match="not an integer"):
        await _rows_2026(OI_2026.replace("Client,205837,", "Client,n/a,"))


@pytest.mark.asyncio
async def test_an_empty_file_is_rejected() -> None:
    with pytest.raises(SchemaError, match="no data rows"):
        await _rows_2026("")


# --------------------------------------------------------------------------------------------
# Fetch behaviour
# --------------------------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_missing_file_raises_rather_than_returning_nothing() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    with pytest.raises(SourceUnavailableError):
        await _source(handler).day_rows(DAY_2026, ParticipantMetric.OPEN_INTEREST)


@pytest.mark.asyncio
async def test_a_non_trading_day_is_a_caller_bug() -> None:
    """Sunday. Answering with an empty book would read as "nobody held anything"."""
    with pytest.raises(ValueError, match="not an NSE trading day"):
        await _source(_serves(OI_2026)).day_rows(date(2026, 7, 26), ParticipantMetric.VOLUME)


@pytest.mark.asyncio
async def test_a_session_is_fetched_once() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(200, text=OI_2026)

    source = _source(handler)
    await source.day_rows(DAY_2026, ParticipantMetric.OPEN_INTEREST)
    await source.day_rows(DAY_2026, ParticipantMetric.OPEN_INTEREST)
    assert calls == 1


@pytest.mark.asyncio
async def test_the_two_metrics_do_not_share_a_cache_entry() -> None:
    """Returning OI for a volume request would be invisible in every number downstream."""
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        body = (
            OI_2026
            if "_oi_" in str(request.url)
            else _with_title(TITLE_2026).replace("Open Interest", "Trading Volume")
        )
        return httpx.Response(200, text=body)

    source = _source(handler)
    await source.day_rows(DAY_2026, ParticipantMetric.OPEN_INTEREST)
    await source.day_rows(DAY_2026, ParticipantMetric.VOLUME)
    assert len(seen) == 2
    assert any("_oi_" in u for u in seen)
    assert any("_vol_" in u for u in seen)


def test_the_url_carries_the_metric_and_the_day() -> None:
    assert participant_url(DAY_2026, ParticipantMetric.OPEN_INTEREST).endswith(
        "fao_participant_oi_28072026.csv"
    )
    assert participant_url(DAY_2026, ParticipantMetric.VOLUME).endswith(
        "fao_participant_vol_28072026.csv"
    )
