"""NSE F&O securities-in-ban list (task 1.1d).

**What this is.** When a security's derivatives open interest crosses 95% of the exchange-set
market-wide position limit, NSE puts it "in ban" for the next session. In ban, participants may
**only reduce** existing F&O positions in that security — no new longs, no new shorts, no
increases. Violating it draws a penalty from the exchange, so this is a compliance boundary and
not a trading opinion. The list is published daily, free, back to at least 2015 (verified live
2026-08-02).

**Two scope facts that are easy to get wrong, and both directions are expensive:**

* The ban binds the **derivatives** segment only. Cash-segment delivery trading in the same
  security is entirely unaffected — so blocking Phase-1 equity delivery on a ban day would refuse
  perfectly legal trades for no reason.
* It blocks **entry**, not exit. A position already open may always be reduced or closed. A veto
  that also blocked exits would trap us in a position we wanted out of, which is strictly worse
  than the risk the ban exists to control.

:meth:`NseFnoBanSource.fno_entry_blocked` is named for exactly that scope.

**This is a veto, not a signal**, which is why the only things this module exposes are a set and a
boolean. There is deliberately no "days in ban" counter or ban-frequency series: those would be
numeric features a strategy could rank on, and the moment a compliance boundary becomes a strategy
input, the learning loop has a reason to seek it out rather than respect it (CLAUDE.md §0 #4).

**Absent file ≠ nothing banned.** ``NIL`` is NSE stating there are no banned securities — that is
data. A missing or unreadable file means we cannot confirm what is banned, which raises rather than
returning an empty set (invariant #10). An empty set on failure would read as "everything is
tradeable", the single most dangerous wrong answer this module could give.

**Four header spellings, all real** (observed 2015→2026): ``: NIL``, ``:NIL``, a bare trailing
space, and ``:,``. The parser normalises the remainder rather than matching any one of them.
"""

from __future__ import annotations

import asyncio
import csv
import re
from collections import OrderedDict
from datetime import date

import httpx

from icarus.agents.data.fetch import COURTESY_PER_S, RateLimiter, get_or_raise
from icarus.agents.data.nse import parse_month_name
from icarus.common.calendar import is_nse_trading_day
from icarus.common.logging import get_logger
from icarus.common.schemas import SchemaError

log = get_logger("data.fnoban")

BAN_URL = "https://nsearchives.nseindia.com/archives/fo/sec_ban"

_MEMO_MAX_DAYS = 40

# Day, month-name and year are captured separately and the month resolved by name rather than by
# ``%b``. Every file sampled 2015->2026 spells it "13-JUL-2015", but the participant-wise feed in
# the same archive carries four different month spellings, so nothing here relies on NSE being
# consistent — and the halt path stays reserved for genuine drift, not a spelling change.
_HEADER = re.compile(
    r"Securities in Ban For Trade Date\s+(\d{1,2})-([A-Za-z]{3,9})-(\d{4})\s*:(.*)", re.IGNORECASE
)

# What NSE writes when the list is empty. Anything else after the colon is treated as a stray.
_NIL = "NIL"

# Each listed security is exactly "<serial>,<symbol>".
_BAN_ROW_FIELDS = 2


def ban_url(d: date) -> str:
    """Verified live against 2015-07-13, 2016-01-05, 2019-07-15 and 2026-07-28 on 2026-08-02."""
    return f"{BAN_URL}/fo_secban_{d:%d%m%Y}.csv"


class NseFnoBanSource:
    """The daily F&O ban list. The HTTP client is injected for testing."""

    def __init__(self, client: httpx.AsyncClient, limiter: RateLimiter | None = None) -> None:
        self._client = client
        self._limiter = limiter or RateLimiter(COURTESY_PER_S)
        self._memo: OrderedDict[date, frozenset[str]] = OrderedDict()
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "nse-fno-ban"

    async def banned_on(self, day: date) -> frozenset[str]:
        """Every security in F&O ban for ``day``.

        Raises rather than returning an empty list if the file is missing or malformed: "we could
        not confirm what is banned" and "nothing is banned" must never be the same answer.
        """
        if not is_nse_trading_day(day):
            raise ValueError(f"{day} is not an NSE trading day — no ban list exists")
        async with self._lock:
            cached = self._memo.get(day)
            if cached is not None:
                self._memo.move_to_end(day)
                return cached
        response = await get_or_raise(
            self._client, ban_url(day), what=f"nse fo ban list {day}", limiter=self._limiter
        )
        ban_list = _parse(response.text, day)
        async with self._lock:
            self._memo[day] = ban_list
            while len(self._memo) > _MEMO_MAX_DAYS:
                self._memo.popitem(last=False)
        return ban_list

    async def fno_entry_blocked(self, symbol: str, day: date) -> bool:
        """Whether opening or increasing an F&O position in ``symbol`` is barred on ``day``.

        Deliberately says nothing about the cash segment (unaffected) or about exits (always
        permitted) — see the module docstring.
        """
        return symbol.upper() in await self.banned_on(day)


def _parse(raw: str, day: date) -> frozenset[str]:
    lines = [line for line in raw.splitlines() if line.strip()]
    if not lines:
        raise SchemaError(f"nse fo ban list {day}: empty file")

    header = _HEADER.search(lines[0])
    if header is None:
        raise SchemaError(
            f"nse fo ban list {day}: unrecognised header {lines[0][:120]!r} — layout may "
            f"have changed"
        )
    _assert_header_date(header.group(1), header.group(2), header.group(3), day)

    # Trailing ",", " " and "NIL" are all layout noise; only the NIL carries meaning.
    remainder = header.group(4).strip().strip(",").strip()
    declared_nil = remainder.upper() == _NIL
    if remainder and not declared_nil:
        raise SchemaError(
            f"nse fo ban list {day}: unexpected text after the header colon ({remainder!r})"
        )

    symbols = _read_symbols(lines[1:], day)
    if declared_nil and symbols:
        raise SchemaError(
            f"nse fo ban list {day}: header declares NIL but {len(symbols)} securities are listed"
        )
    if not declared_nil and not symbols:
        raise SchemaError(
            f"nse fo ban list {day}: no securities listed and no NIL declared — file may be "
            f"truncated"
        )
    return frozenset(symbols)


def _assert_header_date(day_of_month: str, month_name: str, year: str, day: date) -> None:
    """The file names its own trade date; a mismatch means we were served the wrong session.

    That is the failure worth catching here — a stale ban list is well-formed and looks correct,
    and acting on yesterday's is both a compliance breach and an unnecessary block.
    """
    try:
        parsed = date(int(year), parse_month_name(month_name), int(day_of_month))
    except ValueError as exc:
        raise SchemaError(
            f"nse fo ban list {day}: unparseable header date "
            f"{day_of_month}-{month_name}-{year} ({exc})"
        ) from exc
    if parsed != day:
        raise SchemaError(
            f"nse fo ban list {day}: file is for {parsed}, not {day} — wrong session served"
        )


def _read_symbols(body: list[str], day: date) -> list[str]:
    """Parse ``<serial>,<symbol>`` rows, asserting the serials run 1..n without a gap.

    The serial check is what catches a truncated or reordered file: a ban list that lost its tail
    still parses cleanly and still looks like a valid, shorter list.
    """
    symbols: list[str] = []
    for fields in csv.reader(body):
        cells = [f.strip() for f in fields if f.strip()]
        if not cells:
            continue
        if len(cells) != _BAN_ROW_FIELDS:
            raise SchemaError(f"nse fo ban list {day}: expected '<serial>,<symbol>', got {cells!r}")
        serial, symbol = cells
        expected = len(symbols) + 1
        if serial != str(expected):
            raise SchemaError(
                f"nse fo ban list {day}: serial numbers are not sequential — expected "
                f"{expected}, got {serial!r} (file may be truncated)"
            )
        if symbol.upper() in symbols:
            raise SchemaError(f"nse fo ban list {day}: {symbol} listed twice")
        symbols.append(symbol.upper())
    return symbols
