"""NSE bhavcopy daily-bar source (task 1.1, groundwork for 1.1c).

The exchange's own end-of-day file — authoritative, free, and the correct long-term basis for the
point-in-time universe work in task 1.1c (invariant #14). Equities only; crypto comes from Yahoo.

Shape verified against the live archive on **2026-07-28** with
``GET https://nsearchives.nseindia.com/content/cm/BhavCopy_NSE_CM_0_0_0_20260724_F_0000.csv.zip``:
a ZIP holding one CSV of 3,432 rows covering **every** instrument for that session, with columns::

    TradDt TckrSymb SctySrs FinInstrmTp OpnPric HghPric LwPric ClsPric TtlTradgVol ISIN ...

Prices arrive as fixed-point strings (``'1265.00'``), so they become ``Decimal`` losslessly — no
float ever touches a price on this path.

**One file per session, all symbols.** So the unit worth caching is the *day*, not the symbol: one
download serves every symbol for that date. Without this, a two-year fetch across ten symbols
would be ~5,000 downloads instead of ~500. The day-cache is also exactly what the point-in-time
universe snapshot in 1.1c needs.

**A missing file for a day the calendar calls a trading day raises** rather than being skipped.
Skipping would leave a hole indistinguishable from a holiday, which is the precise failure PRD
§29.4 exists to prevent — a silent gap corrupts every backtest that spans it.

**Two archive formats (task 1.1c).** The UDiFF layout above only reaches back to mid-2024 — 2023
returns 404 (verified 2026-07-29). Older sessions use the legacy layout at
``/content/historical/EQUITIES/{YYYY}/{MON}/cm{DDMONYYYY}bhav.csv.zip``, verified against
2021-07-23, whose columns carry everything we need::

    SYMBOL SERIES OPEN HIGH LOW CLOSE TOTTRDQTY TOTTRDVAL TIMESTAMP ISIN

``_download`` tries UDiFF first and falls back to legacy, so the cutover date never has to be
hard-coded; only a day missing from *both* archives is a real gap. The parser dispatches on the
header it actually sees, so a cached file from either era decodes identically.

**Turnover is carried through** (``TtlTrfVal`` / ``TOTTRDVAL``) because it is the point-in-time
liquidity measure the universe builder filters on — the only honest one available, since NSE's
published F&O and equity master lists are *today's* snapshots (§29.1).
"""

from __future__ import annotations

import asyncio
import csv
import io
import zipfile
from collections import OrderedDict
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

import httpx

from icarus.agents.data.cache import read_versioned_json, write_atomic_json
from icarus.agents.data.fetch import COURTESY_PER_S, RateLimiter, get_or_raise
from icarus.agents.data.source import SourceUnavailableError
from icarus.common.calendar import is_nse_trading_day, session_open_utc
from icarus.common.logging import get_logger
from icarus.common.schemas import SchemaError
from icarus.common.types import OHLCV, AssetClass, Candle

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger("data.nse")

BASE_URL = "https://nsearchives.nseindia.com/content/cm"
ARCHIVE_URL = "https://nsearchives.nseindia.com/content/historical/EQUITIES"

# NSE spells months this way in legacy archive paths. Not %b — that is locale-dependent.
_MONTH_ABBR = (
    "JAN", "FEB", "MAR", "APR", "MAY", "JUN",
    "JUL", "AUG", "SEP", "OCT", "NOV", "DEC",
)  # fmt: skip


def parse_month_name(name: str) -> int:
    """Month number (1-12) for an NSE month spelling, matched on its three-letter prefix.

    NSE is not consistent about this across feeds and years — the participant-wise F&O files alone
    carry both ``Jul`` and ``July`` — so matching the prefix covers every spelling seen. Not
    ``%b``, for the locale reason in :func:`legacy_bhavcopy_url`.

    Raises :class:`ValueError` if ``name`` is not a month, which callers convert to a
    ``SchemaError``: an unreadable date must halt the feed, never be guessed at.
    """
    try:
        return _MONTH_ABBR.index(name[:3].upper()) + 1
    except ValueError as exc:
        raise ValueError(f"not an NSE month name: {name!r}") from exc


# Columns we depend on per format. Any one missing means the layout changed -> halt, never guess.
_UDIFF_COLUMNS = (
    "TradDt",
    "TckrSymb",
    "SctySrs",
    "FinInstrmTp",
    "OpnPric",
    "HghPric",
    "LwPric",
    "ClsPric",
    "TtlTradgVol",
    "TtlTrfVal",
)
_LEGACY_COLUMNS = (
    "SYMBOL",
    "SERIES",
    "OPEN",
    "HIGH",
    "LOW",
    "CLOSE",
    "TOTTRDQTY",
    "TOTTRDVAL",
)
# Cash-segment equity rows only: series EQ, instrument type STK. Excludes ETFs, debt, derivatives.
# Series EQ also excludes BE/BZ, which is how NSE marks trade-to-trade and surveillance names —
# so the §29.2 "non-surveillance" requirement is satisfied by construction, point-in-time.
_EQUITY_SERIES = "EQ"
_EQUITY_INSTRUMENT = "STK"

# A day-row: [open, high, low, close, volume, turnover]. Turnover is index 5 (task 1.1c).
TURNOVER_INDEX = 5
CLOSE_INDEX = 3

# Schema 2 added turnover; schema-1 caches are discarded and refetched, which is what the
# version is for.
_DAY_CACHE_SCHEMA = 2

# Parsed day-files kept in memory. One entry is ~2,000 tickers; the bound keeps a long backfill
# from growing without limit while still covering a typical multi-symbol lookback window, where
# every symbol walks the same recent sessions.
_MEMO_MAX_DAYS = 64


def bhavcopy_url(d: date) -> str:
    """Archive URL for one session's full bhavcopy (UDiFF layout, verified 2026-07-28)."""
    return f"{BASE_URL}/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"


def legacy_bhavcopy_url(d: date) -> str:
    """Pre-mid-2024 archive URL (verified against 2021-07-23 on 2026-07-29).

    Months are spelled out rather than taken from ``%b``: that directive is locale-dependent, and
    a non-English locale would silently build URLs that 404 forever.
    """
    mon = _MONTH_ABBR[d.month - 1]
    return f"{ARCHIVE_URL}/{d.year}/{mon}/cm{d.day:02d}{mon}{d.year}bhav.csv.zip"


class NseBhavcopySource:
    """Daily equity OHLCV from NSE's official end-of-day archive.

    ``day_cache_dir`` holds one small JSON per session (all symbols), so repeat fetches and other
    symbols cost nothing. A bounded in-memory memo sits in front of it, because the disk cache
    alone still re-reads and re-parses the same session file once per symbol. The HTTP client is
    injected so tests never touch the network.
    """

    def __init__(
        self,
        client: httpx.AsyncClient,
        day_cache_dir: Path,
        limiter: RateLimiter | None = None,
    ) -> None:
        self._client = client
        self._dir = day_cache_dir
        self._limiter = limiter or RateLimiter(COURTESY_PER_S)
        self._memo: OrderedDict[date, dict[str, list[str]]] = OrderedDict()

    @property
    def name(self) -> str:
        return "nse_bhavcopy"

    def supports(self, asset_class: AssetClass) -> bool:
        return asset_class is AssetClass.EQUITY

    @property
    def prices_are_split_adjusted(self) -> bool:
        """False — the bhavcopy reports what actually traded that session, unadjusted.

        This is the series that *must* go through
        :func:`icarus.agents.data.corpactions.back_adjust`, and it is why the bhavcopy is our
        equity price of record: an unadjusted source can be adjusted correctly, whereas an
        already-adjusted one cannot be un-adjusted.
        """
        return False

    async def daily_bars(self, symbol: str, frm: date, to: date) -> list[Candle]:
        """Bars for ``symbol`` over ``[frm, to]``, assembled from one day-file per session.

        Accepts either ``RELIANCE`` or Yahoo-style ``RELIANCE.NS`` so both sources take the same
        canonical symbol.
        """
        ticker = symbol.removesuffix(".NS").upper()
        candles: list[Candle] = []
        for day in _trading_days(frm, to):
            rows = await self.day_rows(day)
            row = rows.get(ticker)
            if row is None:
                continue  # not listed / not traded that session — absence of a row is real data
            candles.append(_to_candle(day, row, ticker))
        return candles

    async def day_rows(self, day: date) -> dict[str, list[str]]:
        """One session's equity rows as ``ticker -> [o,h,l,c,volume,turnover]``, memoized+cached.

        Public because the point-in-time universe builder (1.1c) needs whole sessions, not single
        symbols: one file already holds every name that traded that day.

        Disk and CPU work is pushed to a worker thread: a bhavcopy holds ~3,400 rows, and unzip +
        CSV parse on the event loop would stall every other agent — including the kill-line poll.
        """
        memoized = self._memo.get(day)
        if memoized is not None:
            self._memo.move_to_end(day)
            return memoized

        cached = await asyncio.to_thread(
            read_versioned_json, self._dir / f"{day:%Y%m%d}.json", _DAY_CACHE_SCHEMA
        )
        if cached is not None and isinstance(cached.get("rows"), dict):
            rows: dict[str, list[str]] = cached["rows"]
        else:
            raw = await self._download(day)
            rows = await asyncio.to_thread(_parse_bhavcopy, raw, day)
            await asyncio.to_thread(
                write_atomic_json,
                self._dir / f"{day:%Y%m%d}.json",
                {"schema": _DAY_CACHE_SCHEMA, "rows": rows},
            )

        self._memo[day] = rows
        while len(self._memo) > _MEMO_MAX_DAYS:
            self._memo.popitem(last=False)
        return rows

    async def _download(self, day: date) -> bytes:
        """Fetch one session's archive, trying the current layout then the legacy one.

        Falling back on absence means the mid-2024 cutover never has to be hard-coded. Only a day
        missing from *both* archives is a real gap, and that still raises — a silent skip would
        leave a hole indistinguishable from a holiday (§29.4).
        """
        try:
            response = await get_or_raise(
                self._client,
                bhavcopy_url(day),
                what=f"nse bhavcopy {day}",
                limiter=self._limiter,
            )
        except SourceUnavailableError:
            response = await get_or_raise(
                self._client,
                legacy_bhavcopy_url(day),
                # Names the day so the error points at the exact missing session (§29.4).
                what=f"nse bhavcopy missing from both archives for trading day {day}",
                limiter=self._limiter,
            )
        return response.content


def _trading_days(frm: date, to: date) -> list[date]:
    """NSE trading days in ``[frm, to]``. Raises if a year's holiday list isn't loaded (§28)."""
    days: list[date] = []
    day = frm
    while day <= to:
        if is_nse_trading_day(day):
            days.append(day)
        day += timedelta(days=1)
    return days


def _parse_bhavcopy(raw: bytes, day: date) -> dict[str, list[str]]:
    """Extract cash-equity rows from a bhavcopy ZIP, in either archive layout.

    Dispatches on the header actually present rather than on the date, so a file cached from
    either era decodes the same way. A header matching neither layout is ``SchemaError``: an
    unrecognised format must halt the feed, never be parsed hopefully (invariant #10).
    """
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        names = archive.namelist()
        if len(names) != 1:
            raise SchemaError(f"nse bhavcopy {day}: expected 1 file in the zip, got {len(names)}")
        text = archive.read(names[0]).decode("utf-8")
    except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise SchemaError(f"nse bhavcopy {day}: unreadable archive ({exc})") from exc

    reader = csv.DictReader(io.StringIO(text))
    columns = set(reader.fieldnames or [])
    if set(_UDIFF_COLUMNS) <= columns:
        return _rows_from_udiff(reader)
    if set(_LEGACY_COLUMNS) <= columns:
        return _rows_from_legacy(reader)
    raise SchemaError(
        f"nse bhavcopy {day}: header matches neither archive layout",
        expected=f"{_UDIFF_COLUMNS} or {_LEGACY_COLUMNS}",
        got=str(sorted(columns)),
    )


def _rows_from_udiff(reader: csv.DictReader[str]) -> dict[str, list[str]]:
    rows: dict[str, list[str]] = {}
    for row in reader:
        if row.get("SctySrs") != _EQUITY_SERIES or row.get("FinInstrmTp") != _EQUITY_INSTRUMENT:
            continue
        ticker = (row.get("TckrSymb") or "").strip().upper()
        if ticker:
            rows[ticker] = [
                row["OpnPric"],
                row["HghPric"],
                row["LwPric"],
                row["ClsPric"],
                row["TtlTradgVol"],
                row["TtlTrfVal"],
            ]
    return rows


def _rows_from_legacy(reader: csv.DictReader[str]) -> dict[str, list[str]]:
    """Pre-mid-2024 layout. It has no instrument-type column; SERIES alone carries the filter."""
    rows: dict[str, list[str]] = {}
    for row in reader:
        if (row.get("SERIES") or "").strip() != _EQUITY_SERIES:
            continue
        ticker = (row.get("SYMBOL") or "").strip().upper()
        if ticker:
            rows[ticker] = [
                row["OPEN"],
                row["HIGH"],
                row["LOW"],
                row["CLOSE"],
                row["TOTTRDQTY"],
                row["TOTTRDVAL"],
            ]
    return rows


def _to_candle(day: date, row: list[str], ticker: str) -> Candle:
    try:
        open_, high, low, close, volume = (Decimal(v) for v in row[:5])
    except (InvalidOperation, ValueError) as exc:
        raise SchemaError(f"nse bhavcopy {day}: non-numeric price for {ticker}: {row}") from exc
    return Candle(
        ts=session_open_utc(day),
        ohlcv=OHLCV(open=open_, high=high, low=low, close=close, volume=volume),
    )
