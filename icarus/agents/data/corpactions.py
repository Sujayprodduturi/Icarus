"""Corporate-action back-adjustment (task 1.1c, PRD §29.3, invariant #14).

A 1:2 split halves the quoted price overnight while nothing real changes. Left unadjusted, every
strategy sees a 50% crash and every volatility measure is poisoned for as long as the window spans
that date. So historical prices are **back-adjusted**: prices before an ex-date are divided by the
split ratio, and volumes multiplied by it, making the series continuous.

**Convention: price-return** (operator decision, 2026-07-29; §29.3 requires picking exactly one
and applying it identically in signal, cost and tax). Splits, bonuses and rights are adjusted for.
**Dividends are not.** A dividend is real cash leaving the company, and the ex-date price drop is
a real drop that a price-based strategy actually experiences; crediting it back would hand the
strategy income it never traded for, and the cash has its own tax treatment.

The practical consequence: **Yahoo's ``adjclose`` must not be used.** It is dividend-adjusted, so
it silently encodes the total-return convention. We take the raw OHLC and apply split ratios
ourselves, from Yahoo's ``events=split`` feed.

Source of actions for **crypto and for cross-checking**: Yahoo's chart endpoint with
``events=div,split`` returns full history with exact ratios (RELIANCE: 3 splits and 22 dividends
over 21 years).

    ⚠️ **Corrected 2026-08-07.** This module used to record that NSE's own corporate-actions API
    "returns only a rolling ~2-day window — useless for history" (noted 2026-07-29). That is true
    only of the bare call; passing ``from_date``/``to_date`` serves history back to at least
    January 2011. **NSE is now the primary source for equities** — see
    :mod:`icarus.agents.data.nseactions` — because Yahoo has no split record at all for delisted
    names such as RCOM, and those are exactly the names a point-in-time universe must price
    honestly (invariant #14). The functions here remain the adjustment arithmetic both paths use.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from icarus.agents.data.fetch import get_or_raise
from icarus.agents.data.yahoo import BASE_URL, epoch_seconds
from icarus.common.logging import get_logger
from icarus.common.schemas import SchemaError
from icarus.common.types import OHLCV, Candle

if TYPE_CHECKING:
    from datetime import date

    import httpx

    from icarus.agents.data.fetch import RateLimiter

log = get_logger("data.corpactions")


@dataclass(frozen=True)
class Split:
    """A capital change that rescales the quoted price. Bonuses and rights arrive as splits too.

    ``ratio`` is new shares per old share: a 1:2 split (price halves) is ``2``, a 1:1 bonus is
    also ``2``, a 3:1 reverse split is ``Decimal("1")/3``.
    """

    ex_date: date
    ratio: Decimal

    def __post_init__(self) -> None:
        if self.ratio <= 0:
            raise ValueError(f"split ratio must be positive, got {self.ratio}")


def back_adjust(bars: list[Candle], splits: list[Split]) -> list[Candle]:
    """Return ``bars`` with pre-split prices rescaled so the series is continuous.

    **Only ever pass an unadjusted series.** Check
    :attr:`~icarus.agents.data.source.DailyBarSource.prices_are_split_adjusted` first: NSE
    bhavcopy is unadjusted and belongs here, Yahoo is already split-adjusted and does not.
    Double-adjusting halves every historical price a second time and yields a smooth, entirely
    plausible, entirely wrong series — the worst kind of bug, because nothing downstream looks
    broken.

    For each bar, the cumulative factor is the product of the ratios of every split whose ex-date
    is strictly **after** that bar. Prices are divided by it and volume multiplied, so traded value
    is preserved. Bars on or after the last split are untouched, which keeps the most recent prices
    equal to the actual quoted prices — the ones a live order will really be filled at.
    """
    if not splits:
        return list(bars)
    ordered = sorted(splits, key=lambda s: s.ex_date)
    adjusted: list[Candle] = []
    for bar in bars:
        session = bar.ts.date()
        factor = Decimal(1)
        for split in ordered:
            if split.ex_date > session:
                factor *= split.ratio
        adjusted.append(bar if factor == 1 else _rescale(bar, factor))
    return adjusted


def _rescale(bar: Candle, factor: Decimal) -> Candle:
    ohlcv = bar.ohlcv
    return Candle(
        ts=bar.ts,
        ohlcv=OHLCV(
            open=ohlcv.open / factor,
            high=ohlcv.high / factor,
            low=ohlcv.low / factor,
            close=ohlcv.close / factor,
            volume=ohlcv.volume * factor,
        ),
    )


async def fetch_splits(
    client: httpx.AsyncClient,
    symbol: str,
    frm: date,
    to: date,
    *,
    limiter: RateLimiter | None = None,
) -> list[Split]:
    """Split/bonus/rights events for ``symbol`` over ``[frm, to]``, ascending by ex-date.

    Dividends are requested too (the endpoint returns both) but deliberately discarded — see the
    module docstring on the price-return convention.
    """
    params = {
        "period1": str(epoch_seconds(frm)),
        "period2": str(epoch_seconds(to)),
        "interval": "1d",
        "events": "div,split",
    }
    response = await get_or_raise(
        client,
        f"{BASE_URL}/{symbol}",
        what=f"yahoo splits {symbol}",
        params=params,
        limiter=limiter,
    )
    try:
        body: Any = response.json()
    except ValueError as exc:
        raise SchemaError(f"yahoo splits {symbol}: response is not JSON") from exc
    return _parse_splits(body, symbol)


def _parse_splits(body: Any, symbol: str) -> list[Split]:
    """Pull ``chart.result[0].events.splits`` out of a verified-shape response.

    An absent ``events`` block means the symbol simply had no actions in the window — that is
    data, not drift. A *malformed* split entry is drift and raises, because silently skipping one
    would leave an unadjusted jump that looks exactly like a crash.
    """
    if not isinstance(body, dict):
        raise SchemaError(f"yahoo splits {symbol}: expected a JSON object")
    results = (body.get("chart") or {}).get("result")
    if not isinstance(results, list) or not results or not isinstance(results[0], dict):
        raise SchemaError(f"yahoo splits {symbol}: missing 'chart.result[0]'")
    events = results[0].get("events")
    if not isinstance(events, dict):
        return []  # no dividends and no splits in the window
    raw_splits = events.get("splits")
    if raw_splits is None:
        return []
    if not isinstance(raw_splits, dict):
        raise SchemaError(f"yahoo splits {symbol}: 'events.splits' is not an object")

    splits: list[Split] = []
    for entry in raw_splits.values():
        if not isinstance(entry, dict):
            raise SchemaError(f"yahoo splits {symbol}: split entry is not an object")
        try:
            numerator = Decimal(str(entry["numerator"]))
            denominator = Decimal(str(entry["denominator"]))
            epoch = float(entry["date"])
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            raise SchemaError(f"yahoo splits {symbol}: malformed split entry {entry}") from exc
        if denominator <= 0 or numerator <= 0:
            raise SchemaError(f"yahoo splits {symbol}: non-positive split ratio {entry}")
        splits.append(
            Split(
                ex_date=datetime.fromtimestamp(epoch, tz=UTC).date(),
                ratio=numerator / denominator,
            )
        )
    splits.sort(key=lambda s: s.ex_date)
    if splits:
        log.info("splits found", symbol=symbol, count=len(splits))
    return splits
