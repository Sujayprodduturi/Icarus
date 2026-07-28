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
from icarus.common.calendar import is_nse_trading_day, session_open_utc
from icarus.common.logging import get_logger
from icarus.common.schemas import SchemaError
from icarus.common.types import OHLCV, AssetClass, Candle

if TYPE_CHECKING:
    from pathlib import Path

log = get_logger("data.nse")

BASE_URL = "https://nsearchives.nseindia.com/content/cm"

# The columns we depend on. Any one missing means the layout changed -> halt, never guess.
_REQUIRED_COLUMNS = (
    "TradDt",
    "TckrSymb",
    "SctySrs",
    "FinInstrmTp",
    "OpnPric",
    "HghPric",
    "LwPric",
    "ClsPric",
    "TtlTradgVol",
)
# Cash-segment equity rows only: series EQ, instrument type STK. Excludes ETFs, debt, derivatives.
_EQUITY_SERIES = "EQ"
_EQUITY_INSTRUMENT = "STK"

_DAY_CACHE_SCHEMA = 1

# Parsed day-files kept in memory. One entry is ~2,000 tickers; the bound keeps a long backfill
# from growing without limit while still covering a typical multi-symbol lookback window, where
# every symbol walks the same recent sessions.
_MEMO_MAX_DAYS = 64


def bhavcopy_url(d: date) -> str:
    """Archive URL for one session's full bhavcopy (UDiFF layout, verified 2026-07-28)."""
    return f"{BASE_URL}/BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip"


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

    async def daily_bars(self, symbol: str, frm: date, to: date) -> list[Candle]:
        """Bars for ``symbol`` over ``[frm, to]``, assembled from one day-file per session.

        Accepts either ``RELIANCE`` or Yahoo-style ``RELIANCE.NS`` so both sources take the same
        canonical symbol.
        """
        ticker = symbol.removesuffix(".NS").upper()
        candles: list[Candle] = []
        for day in _trading_days(frm, to):
            rows = await self._day(day)
            row = rows.get(ticker)
            if row is None:
                continue  # not listed / not traded that session — absence of a row is real data
            candles.append(_to_candle(day, row, ticker))
        return candles

    async def _day(self, day: date) -> dict[str, list[str]]:
        """One session's equity rows as ``ticker -> [o, h, l, c, v]``, memoized then disk-cached.

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
        """Fetch one session's archive. A missing file for a trading day is a gap, not a holiday."""
        response = await get_or_raise(
            self._client,
            bhavcopy_url(day),
            # Names the day so a SourceUnavailableError points at the exact missing session (§29.4).
            what=f"nse bhavcopy missing for trading day {day}",
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
    """Extract the cash-equity rows from a bhavcopy ZIP. Any layout surprise is ``SchemaError``."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        names = archive.namelist()
        if len(names) != 1:
            raise SchemaError(f"nse bhavcopy {day}: expected 1 file in the zip, got {len(names)}")
        text = archive.read(names[0]).decode("utf-8")
    except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise SchemaError(f"nse bhavcopy {day}: unreadable archive ({exc})") from exc

    reader = csv.DictReader(io.StringIO(text))
    columns = reader.fieldnames or []
    missing = [c for c in _REQUIRED_COLUMNS if c not in columns]
    if missing:
        raise SchemaError(
            f"nse bhavcopy {day}: missing columns {missing}",
            expected=str(_REQUIRED_COLUMNS),
            got=str(columns),
        )

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
            ]
    return rows


def _to_candle(day: date, row: list[str], ticker: str) -> Candle:
    try:
        open_, high, low, close, volume = (Decimal(v) for v in row)
    except (InvalidOperation, ValueError) as exc:
        raise SchemaError(f"nse bhavcopy {day}: non-numeric price for {ticker}: {row}") from exc
    return Candle(
        ts=session_open_utc(day),
        ohlcv=OHLCV(open=open_, high=high, low=low, close=close, volume=volume),
    )
