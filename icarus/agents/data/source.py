"""The daily-bar source contract (task 1.1, PRD §10, invariant #10).

Everything that can produce daily OHLCV bars implements :class:`DailyBarSource`: the free
sources used for the Phase-1 stop gate (Yahoo, NSE bhavcopy) now, a broker adapter later.
The ingestion agent above this line never knows which one it is talking to, so swapping the
provider is a wiring change, not a rewrite (CLAUDE.md §2).

**The error taxonomy is the safety-critical part of this module.** A fetch can fail two ways
and they must never be confused:

* :class:`TransientSourceError` — the request was fine, the world was briefly not (timeout,
  dropped connection, 5xx, throttle). Retrying is correct.
* :class:`~icarus.common.schemas.SchemaError` — the *shape* of the response is not what we
  understand (a renamed field, a changed layout). Retrying is pointless and parsing anyway is
  dangerous: a mis-parsed price is worse than no price. It propagates and halts the feed
  (CLAUDE.md §3, invariant #10).

:func:`~icarus.agents.data.fetch.with_retry` encodes exactly that distinction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from datetime import date

    from icarus.common.types import AssetClass, Candle


class TransientSourceError(RuntimeError):
    """A retryable fetch failure: timeout, connection reset, 5xx, rate-limit response.

    Sources must raise this (and only this) for failures where the same request, sent again
    later, could reasonably succeed.
    """


class SourceUnavailableError(RuntimeError):
    """A non-retryable failure: the source cannot serve this symbol/range at all.

    Distinct from :class:`TransientSourceError` (retrying will not help) and from
    ``SchemaError`` (the response we *did* get was well-formed — there just isn't one).
    """


@runtime_checkable
class DailyBarSource(Protocol):
    """Anything that can return daily OHLCV bars for a symbol over an inclusive date range."""

    @property
    def name(self) -> str:
        """Short stable identifier, e.g. ``"yahoo"``. Used in cache paths and logs."""
        ...

    def supports(self, asset_class: AssetClass) -> bool:
        """Whether this source can serve that asset class (NSE bhavcopy is equity-only)."""
        ...

    @property
    def prices_are_split_adjusted(self) -> bool:
        """Whether this source already back-adjusts its OHLC for splits/bonuses.

        Every source must declare this, because getting it wrong is silent and catastrophic:
        back-adjusting an already-adjusted series halves every historical price a second time,
        producing a smooth, plausible-looking series that is simply wrong. Verified 2026-07-29 —
        Yahoo adjusts (RELIANCE crosses its 2024-10-28 1:2 split with no gap), NSE bhavcopy does
        not (it reports the price that actually traded that day).
        """
        ...

    async def daily_bars(self, symbol: str, frm: date, to: date) -> list[Candle]:
        """Daily bars for ``symbol`` over ``[frm, to]`` inclusive, ascending by timestamp.

        Raises :class:`TransientSourceError` on a retryable failure and ``SchemaError`` on any
        unexpected response shape. Returns ``[]`` when the range legitimately holds no bars
        (all holidays, or the instrument had not listed yet) — that is data, not an error.
        """
        ...
