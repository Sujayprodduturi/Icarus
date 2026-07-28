"""Yahoo chart daily-bar source (task 1.1).

Free, no key, and it covers **both** asset classes — ``RELIANCE.NS`` for NSE equities and
``BTC-USD`` for crypto — which is what lets one source satisfy the 1.1 acceptance criterion.

Response shape verified against the live endpoint on **2026-07-28** with
``GET /v8/finance/chart/RELIANCE.NS?period1=..&period2=..&interval=1d``::

    chart.result[0].timestamp                -> list[int]   epoch seconds, one per bar
    chart.result[0].indicators.quote[0].{open,high,low,close,volume} -> parallel lists
    chart.result[0].indicators.adjclose[0].adjclose                  -> present (used in 1.1c)
    chart.error                              -> null, or an error object

Two verified quirks worth knowing:

* A daily bar's timestamp is the **session open** (1735703100 = 09:15 IST), not midnight. The
  whole NSE session sits inside one UTC date, so the UTC date equals the IST trading date.
* The quote arrays contain ``null`` for sessions with no trade. Those are holes in the data,
  not schema drift — they are skipped and counted, never forward-filled (fabricating a bar is
  exactly the dishonesty PRD §29.4 bans).

This is an **unofficial** endpoint Yahoo can change without notice. That is precisely why every
field is checked and any deviation raises ``SchemaError`` to halt the feed rather than parse on.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING, Any

import httpx

from icarus.agents.data.fetch import COURTESY_PER_S, RateLimiter, get_or_raise
from icarus.agents.data.source import SourceUnavailableError
from icarus.common.logging import get_logger
from icarus.common.schemas import SchemaError
from icarus.common.types import OHLCV, AssetClass, Candle

if TYPE_CHECKING:
    from datetime import date

log = get_logger("data.yahoo")

BASE_URL = "https://query1.finance.yahoo.com/v8/finance/chart"
_QUOTE_FIELDS = ("open", "high", "low", "close", "volume")


class YahooDailySource:
    """Daily OHLCV from the Yahoo chart endpoint. The HTTP client is injected for testability."""

    def __init__(self, client: httpx.AsyncClient, limiter: RateLimiter | None = None) -> None:
        self._client = client
        self._limiter = limiter or RateLimiter(COURTESY_PER_S)

    @property
    def name(self) -> str:
        return "yahoo"

    def supports(self, asset_class: AssetClass) -> bool:
        # Equities via the .NS suffix, crypto via pairs like BTC-USD.
        return asset_class in (AssetClass.EQUITY, AssetClass.CRYPTO)

    async def daily_bars(self, symbol: str, frm: date, to: date) -> list[Candle]:
        payload = await self._get(symbol, frm, to)
        result = _unwrap(payload, symbol)
        if result is None:
            return []
        bars = _to_candles(result, symbol)
        return [c for c in bars if frm <= c.ts.date() <= to]

    async def _get(self, symbol: str, frm: date, to: date) -> dict[str, Any]:
        """One rate-limited HTTP GET; transport/status failures become the right error type."""
        params = {
            "period1": str(_epoch(frm)),
            # period2 is exclusive of the following midnight, so push past the last session.
            "period2": str(_epoch(to + timedelta(days=1))),
            "interval": "1d",
        }
        resp = await get_or_raise(
            self._client,
            f"{BASE_URL}/{symbol}",
            what=f"yahoo {symbol}",
            params=params,
            limiter=self._limiter,
        )
        try:
            body: Any = resp.json()
        except ValueError as exc:
            raise SchemaError(f"yahoo {symbol}: response is not JSON") from exc
        if not isinstance(body, dict):
            raise SchemaError(f"yahoo {symbol}: expected a JSON object, got {type(body).__name__}")
        return body


def _epoch(d: date) -> int:
    return int(datetime.combine(d, time.min, tzinfo=UTC).timestamp())


def _unwrap(payload: dict[str, Any], symbol: str) -> dict[str, Any] | None:
    """Validate the envelope and return ``chart.result[0]``, or ``None`` when there is no data.

    Every deviation from the verified shape raises ``SchemaError`` — the feed halts rather than
    guessing what a renamed or restructured field meant.
    """
    chart = payload.get("chart")
    if not isinstance(chart, dict):
        raise SchemaError(f"yahoo {symbol}: missing 'chart' object", expected="chart")
    if chart.get("error"):
        # A well-formed error (unknown symbol, delisted) — real, but not drift and not retryable.
        raise SourceUnavailableError(f"yahoo {symbol}: {chart['error']}")
    results = chart.get("result")
    if results is None:
        return None
    if not isinstance(results, list):
        raise SchemaError(f"yahoo {symbol}: 'chart.result' is not a list", expected="list")
    if not results:
        return None
    first = results[0]
    if not isinstance(first, dict):
        raise SchemaError(f"yahoo {symbol}: 'chart.result[0]' is not an object")
    return first


def _to_candles(result: dict[str, Any], symbol: str) -> list[Candle]:
    """Convert the verified column-oriented payload into Candles, skipping null sessions."""
    timestamps = result.get("timestamp")
    if timestamps is None:
        return []  # a valid empty window (e.g. the symbol had not listed yet)
    if not isinstance(timestamps, list):
        raise SchemaError(f"yahoo {symbol}: 'timestamp' is not a list", expected="list")

    indicators = result.get("indicators")
    if not isinstance(indicators, dict):
        raise SchemaError(f"yahoo {symbol}: missing 'indicators' object", expected="indicators")
    quotes = indicators.get("quote")
    if not isinstance(quotes, list) or not quotes or not isinstance(quotes[0], dict):
        raise SchemaError(f"yahoo {symbol}: missing 'indicators.quote[0]'", expected="quote[0]")
    quote: dict[str, Any] = quotes[0]

    missing = [f for f in _QUOTE_FIELDS if f not in quote]
    if missing:
        raise SchemaError(
            f"yahoo {symbol}: quote is missing {missing}",
            expected=str(_QUOTE_FIELDS),
            got=str(sorted(quote)),
        )
    for field in _QUOTE_FIELDS:
        series = quote[field]
        if not isinstance(series, list):
            raise SchemaError(f"yahoo {symbol}: '{field}' is not a list", expected="list")
        if len(series) != len(timestamps):
            raise SchemaError(
                f"yahoo {symbol}: '{field}' has {len(series)} values for "
                f"{len(timestamps)} timestamps"
            )

    candles: list[Candle] = []
    skipped = 0
    for i, epoch in enumerate(timestamps):
        row = [quote[f][i] for f in _QUOTE_FIELDS]
        if any(v is None for v in row) or not isinstance(epoch, int | float):
            skipped += 1  # no-trade session: a hole in the data, never forward-filled (§29.4)
            continue
        try:
            values = [Decimal(str(v)) for v in row]
        except (InvalidOperation, ValueError) as exc:
            raise SchemaError(f"yahoo {symbol}: non-numeric quote value at index {i}") from exc
        open_, high, low, close, volume = values
        candles.append(
            Candle(
                ts=datetime.fromtimestamp(float(epoch), tz=UTC),
                ohlcv=OHLCV(open=open_, high=high, low=low, close=close, volume=volume),
            )
        )
    if skipped:
        log.info("skipped null sessions", source="yahoo", symbol=symbol, skipped=skipped)
    return candles
