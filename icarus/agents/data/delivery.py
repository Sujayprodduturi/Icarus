"""NSE security-wise delivery data (task 1.1d).

**What this is and why it matters.** Every equity trade on NSE either settles as *delivery* — the
buyer actually takes the shares — or is squared off intraday and never leaves the exchange. NSE
publishes the split per symbol per session, free, back to 2011. A stock where 70% of volume went
to delivery is being accumulated; the same volume at 15% delivery is day-traders passing paper
around. That distinction is invisible in OHLCV.

It matters strategically because **it has no Western equivalent** and is therefore one of the very
few inputs in `docs/strategy-research/primitive-catalogue.md` that the global quant industry has
not mined. Every indicator in every trading book has been tested by thousands of people with
better data than us; this has not.

**Two archive formats, verified live 2026-07-31** — the same dual-format shape ``nse.py`` already
handles for the bhavcopy, for the same reason (NSE changed layout mid-history and left the old
files in place):

* **Modern**, ~mid-2019 onward: ``/products/content/sec_bhavdata_full_DDMMYYYY.csv``. A plain CSV
  whose header is ``SYMBOL, SERIES, DATE1, ..., TTL_TRD_QNTY, ..., DELIV_QTY, DELIV_PER``. Note
  the values carry a leading space after each comma (``' EQ'``), so every field is stripped.
* **Legacy**, back to at least 2011: ``/archives/equities/mto/MTO_DDMMYYYY.DAT``. Four preamble
  lines, then rows of ``20,<srno>,<symbol>,<series>,<traded>,<delivered>,<pct>``. The ``20`` is a
  record-type marker; the column *header* line names six columns while the data rows carry seven,
  because "Name of Security" is really symbol **and** series. Parsing this by header name rather
  than position would silently misread every row.

``_download`` tries modern first and falls back to legacy, so the cutover date never has to be
hard-coded — only a day missing from *both* archives is a real gap, and that raises (§29.4: a
silent skip leaves a hole indistinguishable from a holiday, corrupting every backtest spanning it).

**Non-deliverable series.** Government securities and similar carry ``-`` where a delivery figure
would be. That is legitimately "not applicable", not missing data, so those rows are skipped
rather than defaulted to zero — a zero would read as "nobody took delivery", which is a different
and false claim.

**The published percentage is cross-checked against the quantities** (:data:`_PCT_TOLERANCE_PP`).
The file gives us both, so agreeing is free; if NSE ever reorders columns, the mismatch surfaces
immediately as :class:`SchemaError` instead of quietly poisoning a signal.
"""

from __future__ import annotations

import asyncio
import csv
from collections import OrderedDict
from datetime import date
from decimal import Decimal, InvalidOperation

import httpx
from pydantic import BaseModel, ConfigDict

from icarus.agents.data.fetch import COURTESY_PER_S, RateLimiter, get_or_raise
from icarus.agents.data.source import SourceUnavailableError
from icarus.common.calendar import is_nse_trading_day
from icarus.common.logging import get_logger
from icarus.common.schemas import SchemaError

log = get_logger("data.delivery")

MODERN_URL = "https://nsearchives.nseindia.com/products/content"
LEGACY_URL = "https://nsearchives.nseindia.com/archives/equities/mto"

# One file serves every symbol for a session, so the day is the unit worth holding — same reasoning
# as nse.py. Bounded so a long backfill cannot grow memory without limit.
_MEMO_MAX_DAYS = 40

# Published DELIV_PER vs computed delivered/traded, in percentage points. Generous enough for the
# file's own 2-dp rounding on small quantities, tight enough that a column reorder cannot hide.
_PCT_TOLERANCE_PP = Decimal("0.1")

# Legacy MTO rows are marked with record type 20; 10 is the file header.
_MTO_DATA_RECORD = "20"
_MTO_FIELDS = 7

# "Not applicable" markers seen in the delivery columns for non-deliverable series.
_NOT_APPLICABLE = {"-", "", "NA"}


class DeliveryRecord(BaseModel):
    """One symbol's delivery split for one session.

    ``delivery_pct`` is carried as published rather than recomputed: it is what NSE stated, and a
    derived value would quietly disagree with the exchange's own file at the rounding boundary.
    """

    model_config = ConfigDict(frozen=True)

    symbol: str
    series: str
    traded_qty: int
    delivered_qty: int
    delivery_pct: Decimal


def delivery_url(d: date) -> str:
    """Modern layout (verified against 2026-07-28 and 2020-05-13 on 2026-07-31)."""
    return f"{MODERN_URL}/sec_bhavdata_full_{d:%d%m%Y}.csv"


def legacy_delivery_url(d: date) -> str:
    """Legacy MTO layout (verified against 2011-07-13, 2013-07-10 and 2016-07-13 on 2026-07-31)."""
    return f"{LEGACY_URL}/MTO_{d:%d%m%Y}.DAT"


class NseDeliverySource:
    """Per-session delivery quantities and percentages. The HTTP client is injected for testing."""

    def __init__(self, client: httpx.AsyncClient, limiter: RateLimiter | None = None) -> None:
        self._client = client
        self._limiter = limiter or RateLimiter(COURTESY_PER_S)
        self._memo: OrderedDict[date, dict[str, DeliveryRecord]] = OrderedDict()
        self._lock = asyncio.Lock()

    @property
    def name(self) -> str:
        return "nse-delivery"

    async def day_records(self, day: date) -> dict[str, DeliveryRecord]:
        """Every symbol's delivery split for ``day``, keyed by symbol.

        Raises :class:`SourceUnavailableError` if the session is missing from both archives, and
        :class:`ValueError` if ``day`` is not an NSE trading day — asking for delivery on a holiday
        is a caller bug, and answering with an empty dict would look like "nobody delivered".
        """
        if not is_nse_trading_day(day):
            raise ValueError(f"{day} is not an NSE trading day — no delivery file exists")
        async with self._lock:
            cached = self._memo.get(day)
            if cached is not None:
                self._memo.move_to_end(day)
                return cached
        raw = await self._download(day)
        records = _parse(raw, day)
        async with self._lock:
            self._memo[day] = records
            while len(self._memo) > _MEMO_MAX_DAYS:
                self._memo.popitem(last=False)
        return records

    async def for_symbol(self, symbol: str, day: date) -> DeliveryRecord | None:
        """One symbol's record, or ``None`` if it did not trade that session."""
        return (await self.day_records(day)).get(symbol.upper())

    async def _download(self, day: date) -> str:
        """Modern layout first, then legacy. Only absence from both is a real gap (§29.4)."""
        try:
            response = await get_or_raise(
                self._client,
                delivery_url(day),
                what=f"nse delivery {day}",
                limiter=self._limiter,
            )
        except SourceUnavailableError:
            response = await get_or_raise(
                self._client,
                legacy_delivery_url(day),
                what=f"nse delivery missing from both archives for trading day {day}",
                limiter=self._limiter,
            )
        return response.text


def _parse(raw: str, day: date) -> dict[str, DeliveryRecord]:
    """Dispatch on the content actually seen, so a file cached from either era decodes the same."""
    if not raw.strip():
        raise SchemaError(f"nse delivery {day}: empty file")
    head = raw.lstrip()[:400].upper()
    if "DELIV_PER" in head:
        return _parse_modern(raw, day)
    if "SECURITY WISE DELIVERY" in head:
        return _parse_legacy(raw, day)
    raise SchemaError(
        f"nse delivery {day}: unrecognised layout — expected a DELIV_PER header (modern) or an "
        f"MTO preamble (legacy), got {raw[:120]!r}"
    )


def _parse_modern(raw: str, day: date) -> dict[str, DeliveryRecord]:
    reader = csv.DictReader(raw.splitlines())
    if reader.fieldnames is None:
        raise SchemaError(f"nse delivery {day}: no header row")
    # Values AND field names carry a leading space after each comma in this file.
    reader.fieldnames = [f.strip() for f in reader.fieldnames]
    required = {"SYMBOL", "SERIES", "TTL_TRD_QNTY", "DELIV_QTY", "DELIV_PER"}
    missing = required - set(reader.fieldnames)
    if missing:
        raise SchemaError(f"nse delivery {day}: modern layout missing columns {sorted(missing)}")

    out: dict[str, DeliveryRecord] = {}
    for row in reader:
        record = _record(
            symbol=(row.get("SYMBOL") or "").strip(),
            series=(row.get("SERIES") or "").strip(),
            traded=(row.get("TTL_TRD_QNTY") or "").strip(),
            delivered=(row.get("DELIV_QTY") or "").strip(),
            pct=(row.get("DELIV_PER") or "").strip(),
            day=day,
        )
        if record is not None:
            out[record.symbol] = record
    if not out:
        raise SchemaError(f"nse delivery {day}: modern layout parsed to zero usable rows")
    return out


def _parse_legacy(raw: str, day: date) -> dict[str, DeliveryRecord]:
    """Parse MTO rows **by position**, not by header name.

    The header line names six columns while data rows carry seven — "Name of Security" is really
    symbol *and* series. Trusting the header here would misalign every field after the symbol.
    """
    out: dict[str, DeliveryRecord] = {}
    for fields in csv.reader(raw.splitlines()):
        if len(fields) != _MTO_FIELDS or fields[0].strip() != _MTO_DATA_RECORD:
            continue  # preamble, header, or the record-type-10 file marker
        record = _record(
            symbol=fields[2].strip(),
            series=fields[3].strip(),
            traded=fields[4].strip(),
            delivered=fields[5].strip(),
            pct=fields[6].strip(),
            day=day,
        )
        if record is not None:
            out[record.symbol] = record
    if not out:
        raise SchemaError(f"nse delivery {day}: legacy MTO layout parsed to zero usable rows")
    return out


def _record(
    *, symbol: str, series: str, traded: str, delivered: str, pct: str, day: date
) -> DeliveryRecord | None:
    """Build one record, or ``None`` for rows where delivery does not apply.

    A non-deliverable series (government securities and similar) publishes ``-``. Skipping is the
    honest reading: defaulting to zero would assert "nobody took delivery", which is false.
    """
    if not symbol:
        return None
    if delivered in _NOT_APPLICABLE or pct in _NOT_APPLICABLE or traded in _NOT_APPLICABLE:
        return None
    try:
        traded_qty = int(traded)
        delivered_qty = int(delivered)
        delivery_pct = Decimal(pct)
    except (ValueError, InvalidOperation) as exc:
        raise SchemaError(
            f"nse delivery {day}: unparseable row for {symbol!r} "
            f"(traded={traded!r} delivered={delivered!r} pct={pct!r})"
        ) from exc

    if delivered_qty > traded_qty:
        raise SchemaError(
            f"nse delivery {day}: {symbol} delivered {delivered_qty} of {traded_qty} traded — "
            f"delivery cannot exceed volume"
        )
    _assert_pct_agrees(
        symbol=symbol, traded=traded_qty, delivered=delivered_qty, published=delivery_pct, day=day
    )
    return DeliveryRecord(
        symbol=symbol,
        series=series,
        traded_qty=traded_qty,
        delivered_qty=delivered_qty,
        delivery_pct=delivery_pct,
    )


def _assert_pct_agrees(
    *, symbol: str, traded: int, delivered: int, published: Decimal, day: date
) -> None:
    """Cross-check the published percentage against the quantities in the same row.

    The file hands us both, so agreement is free. Its real job is schema-drift detection: if NSE
    ever reorders columns, this fires immediately rather than letting a wrong number reach a
    signal (invariant #10 — fail safe, not silent).
    """
    if traded <= 0:
        return
    computed = Decimal(delivered) * 100 / Decimal(traded)
    if abs(computed - published) > _PCT_TOLERANCE_PP:
        raise SchemaError(
            f"nse delivery {day}: {symbol} publishes DELIV_PER={published} but "
            f"{delivered}/{traded} computes to {computed:.2f} — column layout may have changed"
        )
