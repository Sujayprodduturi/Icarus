"""NSE participant-wise F&O open interest and trading volume (task 1.1d).

**What this is and why it matters.** Every trading day NSE publishes how the *entire* equity-
derivatives book is split across four participant categories — retail/`Client`, `DII`, `FII` and
`Pro` (proprietary desks) — long and short, futures and options, index and stock. Fourteen columns,
four categories, back to at least 2014 (verified live 2026-08-02), free.

This is the reason the task exists. Everywhere else in the world "smart money versus dumb money" is
an inference drawn from a chart; here it is a **published number**. When FII index-futures
positioning is net short while retail is net long, that is not a pattern someone read into a
candle — it is the exchange stating who holds what. No Western venue publishes this, so unlike
every other primitive in `docs/strategy-research/primitive-catalogue.md` it has not been mined flat
by people with better data than us.

**Two files, one shape.** ``fao_participant_oi_DDMMYYYY.csv`` (open interest — positions *held*)
and ``fao_participant_vol_DDMMYYYY.csv`` (volume — contracts *traded*) are byte-for-byte identical
in layout and differ only in the title line, so :class:`ParticipantMetric` selects between them
rather than there being two near-duplicate classes.

**Three independent guards, each catching something the others cannot:**

* **Parse by header name, and require the exact expected column set.** Unlike the legacy MTO file
  in ``delivery.py``, this header is trustworthy: names match the data and have been stable since
  2014. So a reorder is harmless and a rename raises :class:`SchemaError`. *This* is the
  schema-drift detector.
* **The title must name the right metric and the right date.** Cheap, and it catches the failure a
  column check structurally cannot: being served the wrong file (a stale cache, a URL slip, NSE
  reusing yesterday's content). Reading Monday's positioning as Tuesday's is a wrong number that
  looks entirely reasonable. NSE spells that date **four different ways** across the archive
  (``Jul 28, 2026`` · ``Mar 03,2021`` · ``July 02, 2018`` · ``Mar 20 2020``), so the parser resolves
  month, day and year separately — a strict format string rejects half of recorded history, which
  is how a useful guard turns into a feed that refuses to load.
* **``TOTAL`` must reconcile against the four categories** (:data:`_RECONCILE_TOLERANCE`). Note what
  this does *not* do: a uniform column reorder shifts the ``TOTAL`` row identically, so the sums
  would still agree — the header check above is what covers that. What it does catch is a **changed
  participant taxonomy** (NSE adding or splitting a category, which would silently drop a slice of
  the market from every one of our sums) and garbled or truncated rows.

**The tolerance is measured, not guessed.** NSE's own files do not always reconcile exactly: across
48 files sampled from 2015→2026, 11 carried a discrepancy and the worst was **1 contract** (e.g.
2026-07-28 OI, ``Option Index Put Long``: categories sum to 2,697,953 against a published
2,697,954). It reads as one contract left unattributed to a category, so the bound is one per
category — four. Any genuine corruption is orders of magnitude larger than that, since these
columns run to millions.
"""

from __future__ import annotations

import asyncio
import csv
import re
from collections import OrderedDict
from datetime import date
from enum import StrEnum

import httpx
from pydantic import BaseModel, ConfigDict

from icarus.agents.data.fetch import COURTESY_PER_S, RateLimiter, get_or_raise
from icarus.agents.data.nse import parse_month_name
from icarus.common.calendar import is_nse_trading_day
from icarus.common.logging import get_logger
from icarus.common.schemas import SchemaError

log = get_logger("data.participants")

PARTICIPANT_URL = "https://nsearchives.nseindia.com/content/nsccl"

# Two files per session (OI + volume); 40 sessions is the same bound delivery.py uses.
_MEMO_MAX_DAYS = 80

# See the module docstring: measured maximum discrepancy is 1 contract, read as one unattributed
# contract per category. Four categories, so four. Real corruption is millions off, not four.
_RECONCILE_TOLERANCE = 4

# NSE spells the title date four different ways across the archive (all observed live 2026-08-02):
# "Jul 28, 2026", "Mar 03,2021" (no space), "July 02, 2018" (full month) and "Mar 20 2020" (no
# comma at all). Month, day and year are captured separately and the month is resolved by name, so
# every spelling parses and none of them is guessed at.
_TITLE_DATE = re.compile(r"as on\s+([A-Za-z]{3,9})\s+(\d{1,2})\s*,?\s*(\d{4})")

_CATEGORY_COLUMN = "Client Type"
_TOTAL_ROW = "TOTAL"

# Header name -> field name. Parsing by name (not position) is the drift guard: a rename raises
# rather than silently reading the neighbouring column.
_COLUMNS = {
    "Future Index Long": "future_index_long",
    "Future Index Short": "future_index_short",
    "Future Stock Long": "future_stock_long",
    "Future Stock Short": "future_stock_short",
    "Option Index Call Long": "option_index_call_long",
    "Option Index Put Long": "option_index_put_long",
    "Option Index Call Short": "option_index_call_short",
    "Option Index Put Short": "option_index_put_short",
    "Option Stock Call Long": "option_stock_call_long",
    "Option Stock Put Long": "option_stock_put_long",
    "Option Stock Call Short": "option_stock_call_short",
    "Option Stock Put Short": "option_stock_put_short",
    "Total Long Contracts": "total_long",
    "Total Short Contracts": "total_short",
}


class ParticipantMetric(StrEnum):
    """Which of the two files to read. The value is the slug NSE uses in the filename."""

    OPEN_INTEREST = "oi"
    VOLUME = "vol"

    @property
    def title_phrase(self) -> str:
        """The phrase the file's own title line must contain — guards against the wrong file."""
        return "Open Interest" if self is ParticipantMetric.OPEN_INTEREST else "Trading Volume"


class ParticipantCategory(StrEnum):
    """The four categories NSE splits the book into. Values match the file verbatim."""

    CLIENT = "Client"
    DII = "DII"
    FII = "FII"
    PRO = "Pro"


class ParticipantRow(BaseModel):
    """One category's positioning for one session, in contracts."""

    model_config = ConfigDict(frozen=True)

    category: ParticipantCategory
    future_index_long: int
    future_index_short: int
    future_stock_long: int
    future_stock_short: int
    option_index_call_long: int
    option_index_put_long: int
    option_index_call_short: int
    option_index_put_short: int
    option_stock_call_long: int
    option_stock_put_long: int
    option_stock_call_short: int
    option_stock_put_short: int
    total_long: int
    total_short: int

    @property
    def net_future_index(self) -> int:
        """Long minus short in index futures — the headline directional-positioning number."""
        return self.future_index_long - self.future_index_short

    @property
    def net_future_stock(self) -> int:
        """Long minus short in single-stock futures."""
        return self.future_stock_long - self.future_stock_short


def participant_url(d: date, metric: ParticipantMetric) -> str:
    """Verified live against 2014-01-14, 2015-06-01, 2019-07-15 and 2026-07-28 on 2026-08-02."""
    return f"{PARTICIPANT_URL}/fao_participant_{metric.value}_{d:%d%m%Y}.csv"


class NseParticipantSource:
    """Per-session participant-wise F&O positioning. The HTTP client is injected for testing."""

    def __init__(self, client: httpx.AsyncClient, limiter: RateLimiter | None = None) -> None:
        self._client = client
        self._limiter = limiter or RateLimiter(COURTESY_PER_S)
        self._memo: OrderedDict[
            tuple[date, ParticipantMetric], dict[ParticipantCategory, ParticipantRow]
        ] = OrderedDict()
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "nse-participants"

    async def day_rows(
        self, day: date, metric: ParticipantMetric
    ) -> dict[ParticipantCategory, ParticipantRow]:
        """Every category's positioning for ``day``, keyed by category.

        Raises :class:`ValueError` if ``day`` is not an NSE trading day (asking for positioning on
        a holiday is a caller bug), ``SourceUnavailableError`` if the file is absent, and
        :class:`SchemaError` if any guard in the module docstring fails. It never returns a partial
        book — an incomplete split is worse than none, because the missing slice is invisible.
        """
        if not is_nse_trading_day(day):
            raise ValueError(f"{day} is not an NSE trading day — no participant file exists")
        key = (day, metric)
        async with self._lock:
            cached = self._memo.get(key)
            if cached is not None:
                self._memo.move_to_end(key)
                return cached
        response = await get_or_raise(
            self._client,
            participant_url(day, metric),
            what=f"nse participant {metric.value} {day}",
            limiter=self._limiter,
        )
        rows = _parse(response.text, day, metric)
        async with self._lock:
            self._memo[key] = rows
            while len(self._memo) > _MEMO_MAX_DAYS:
                self._memo.popitem(last=False)
        return rows


def _parse(
    raw: str, day: date, metric: ParticipantMetric
) -> dict[ParticipantCategory, ParticipantRow]:
    lines = [line for line in raw.splitlines() if line.strip()]
    if len(lines) < 2:
        raise SchemaError(f"nse participant {metric.value} {day}: file has no data rows")

    _assert_title_matches(lines[0], day=day, metric=metric)
    values = _read_columns(lines[1:], day=day, metric=metric)
    _assert_total_reconciles(values, day=day, metric=metric)

    return {
        category: ParticipantRow(category=category, **values[category.value])
        for category in ParticipantCategory
    }


def _assert_title_matches(title: str, *, day: date, metric: ParticipantMetric) -> None:
    """The title states both the metric and the date, so both are checked against what we asked for.

    Catches being served the wrong file — a stale cache, a URL slip, NSE republishing yesterday.
    A column check cannot see this: yesterday's file is perfectly well-formed.
    """
    if metric.title_phrase not in title:
        raise SchemaError(
            f"nse participant {metric.value} {day}: title does not mention "
            f"{metric.title_phrase!r} — wrong file served? got {title[:120]!r}"
        )
    found = _TITLE_DATE.search(title)
    if found is None:
        raise SchemaError(
            f"nse participant {metric.value} {day}: no 'as on <date>' in title {title[:120]!r}"
        )
    month_name, day_of_month, year = found.groups()
    try:
        stated = date(int(year), parse_month_name(month_name), int(day_of_month))
    except ValueError as exc:
        raise SchemaError(
            f"nse participant {metric.value} {day}: unparseable title date "
            f"{found.group(0)!r} ({exc})"
        ) from exc
    if stated != day:
        raise SchemaError(
            f"nse participant {metric.value} {day}: file is for {stated}, not {day} — "
            f"wrong session served"
        )


def _read_columns(
    body: list[str], *, day: date, metric: ParticipantMetric
) -> dict[str, dict[str, int]]:
    """Read the header + category rows into ``{category: {field: contracts}}``."""
    reader = csv.DictReader(body)
    if reader.fieldnames is None:
        raise SchemaError(f"nse participant {metric.value} {day}: no header row")
    # Some columns carry trailing padding in the modern files ("Future Stock Short       ").
    reader.fieldnames = [f.strip() for f in reader.fieldnames]
    missing = ({_CATEGORY_COLUMN, *_COLUMNS}) - set(reader.fieldnames)
    if missing:
        raise SchemaError(
            f"nse participant {metric.value} {day}: missing columns {sorted(missing)} — "
            f"layout may have changed"
        )

    out: dict[str, dict[str, int]] = {}
    for row in reader:
        category = (row.get(_CATEGORY_COLUMN) or "").strip()
        if not category:
            continue
        out[category] = {
            field: _contracts(row.get(header), category=category, header=header, day=day)
            for header, field in _COLUMNS.items()
        }

    expected = {c.value for c in ParticipantCategory} | {_TOTAL_ROW}
    if set(out) != expected:
        raise SchemaError(
            f"nse participant {metric.value} {day}: expected categories {sorted(expected)}, "
            f"got {sorted(out)} — participant taxonomy may have changed"
        )
    return out


def _contracts(raw: str | None, *, category: str, header: str, day: date) -> int:
    value = (raw or "").strip()
    try:
        contracts = int(value)
    except ValueError as exc:
        raise SchemaError(
            f"nse participant {day}: {category}/{header} is not an integer ({value!r})"
        ) from exc
    if contracts < 0:
        raise SchemaError(
            f"nse participant {day}: {category}/{header} is negative ({contracts}) — "
            f"contract counts cannot be negative"
        )
    return contracts


def _assert_total_reconciles(
    values: dict[str, dict[str, int]], *, day: date, metric: ParticipantMetric
) -> None:
    """Every column's four categories must sum to the published ``TOTAL``, within tolerance.

    Its job is catching a **changed participant taxonomy** — if NSE added a fifth category we would
    silently drop a slice of the market from every sum, and nothing else here would notice.
    """
    total = values[_TOTAL_ROW]
    for field in _COLUMNS.values():
        summed = sum(values[c.value][field] for c in ParticipantCategory)
        if abs(summed - total[field]) > _RECONCILE_TOLERANCE:
            raise SchemaError(
                f"nse participant {metric.value} {day}: {field} categories sum to {summed} but "
                f"TOTAL says {total[field]} — participant categories may have changed"
            )
