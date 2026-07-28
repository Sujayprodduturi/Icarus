"""Data-Ingestion agent (task 1.1, PRD §10 agent #1, invariants #10 and #22).

Turns whatever a source returns into the one canonical
:class:`~icarus.common.types.MarketData` message the rest of Icarus consumes, and stops rather
than guesses when the data stops making sense.

Three behaviours carry the safety weight:

* **Kill-line first.** ``ctx.should_halt()`` is checked at the top of every cycle *and* between
  feeds, so a raised HALT stops publishing promptly instead of after a full sweep.
* **Schema drift halts that feed, and only that feed.** A ``SchemaError`` from one symbol's source
  disables that feed and pages the operator; the other feeds keep running. That is deliberate:
  equity data breaking must not silently stop the crypto plane (PRD §38). When every feed is
  halted the agent returns — there is nothing left for it to do, and the supervisor must not
  restart-loop an agent with no working inputs.
* **Bars are published once, and only once they are final.** Each feed remembers the last
  timestamp it emitted and only publishes strictly newer ones, so a bar is never double-counted.
  A bar for the session *currently in progress* is withheld entirely: its close is only the last
  trade so far, and emitting it would hand a strategy a close that has not happened yet
  (invariants #12/#13). See :func:`icarus.common.calendar.session_closed`.

The agent takes ``publish`` and ``alert`` as injected callables rather than reaching for the bus
itself. That keeps it pure enough to unit-test without Valkey, and keeps bus wiring a deployment
concern (same pattern as :mod:`icarus.agents.daily_auth`).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING

from icarus.agents.base import Agent
from icarus.common.calendar import session_closed
from icarus.common.logging import get_logger
from icarus.common.schemas import SchemaError, utc_now
from icarus.common.types import AssetClass, MarketData

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

    from icarus.agents.base import RunContext
    from icarus.agents.data.source import DailyBarSource
    from icarus.common.types import Candle

log = get_logger("data.ingest")


@dataclass(frozen=True)
class FeedSpec:
    """One symbol to ingest, and the asset class it belongs to."""

    symbol: str
    asset_class: AssetClass

    @property
    def key(self) -> str:
        return f"{self.asset_class}:{self.symbol}"


class DataIngestionAgent(Agent):
    """Polls a daily-bar source for each feed and publishes normalized ``MarketData``."""

    def __init__(
        self,
        feeds: list[FeedSpec],
        source: DailyBarSource,
        *,
        publish: Callable[[MarketData], Awaitable[None]],
        alert: Callable[[str], Awaitable[None]],
        lookback_days: int = 30,
        poll_interval_s: float = 60.0,
        now_fn: Callable[[], datetime] = utc_now,
        name: str = "data-ingest",
    ) -> None:
        super().__init__(name)
        if not feeds:
            raise ValueError("DataIngestionAgent needs at least one feed")
        # Fail at construction, not silently at 09:15: a source that cannot serve a feed's asset
        # class (NSE bhavcopy is equity-only) would otherwise return nothing forever and look fine.
        unsupported = sorted({f.key for f in feeds if not source.supports(f.asset_class)})
        if unsupported:
            raise ValueError(f"source {source.name!r} cannot serve feeds: {unsupported}")
        self._feeds = feeds
        self._source = source
        self._publish = publish
        self._alert = alert
        self._lookback = timedelta(days=lookback_days)
        self._poll_interval_s = poll_interval_s
        self._now = now_fn
        self._halted: set[str] = set()
        self._last_ts: dict[str, datetime] = {}

    @property
    def halted_feeds(self) -> frozenset[str]:
        """Feeds stopped by schema drift. Non-empty means degraded ingestion (surfaced daily)."""
        return frozenset(self._halted)

    async def run(self, ctx: RunContext) -> None:
        """Poll every live feed until the kill-line fires or every feed has halted."""
        while True:
            if await ctx.should_halt():
                log.warning("kill-line raised; stopping ingestion", agent=self.name)
                return
            for feed in self._feeds:
                if feed.key in self._halted:
                    continue
                if await ctx.should_halt():
                    return
                await self._poll(feed)
            if len(self._halted) == len(self._feeds):
                log.error("every feed halted; ingestion has no working inputs", agent=self.name)
                return
            await asyncio.sleep(self._poll_interval_s)

    async def _poll(self, feed: FeedSpec) -> None:
        """Fetch one feed's recent bars and publish the ones not seen before."""
        to = self._now().date()
        frm = to - self._lookback
        try:
            bars = await self._source.daily_bars(feed.symbol, frm, to)
        except SchemaError as exc:
            await self._halt_feed(feed, f"schema drift: {exc}")
            return
        for candle in self._fresh(feed, bars):
            await self._publish(_to_market_data(feed, candle))
            self._last_ts[feed.key] = candle.ts

    def _fresh(self, feed: FeedSpec, bars: list[Candle]) -> list[Candle]:
        """Closed-session bars strictly newer than the last one published, oldest first.

        Sorted defensively: ``_last_ts`` advances as bars are published, so out-of-order input
        would silently drop bars. Cheap insurance over a lookback window on a money path.
        """
        seen = self._last_ts.get(feed.key)
        now = self._now()
        candles = sorted(bars, key=lambda c: c.ts)
        return [
            c
            for c in candles
            if (seen is None or c.ts > seen) and session_closed(feed.asset_class, c.ts.date(), now)
        ]

    async def _halt_feed(self, feed: FeedSpec, reason: str) -> None:
        """Stop one feed and page the operator. Never falls back to best-effort parsing (§3)."""
        self._halted.add(feed.key)
        log.error("feed halted", agent=self.name, feed=feed.key, reason=reason)
        await self._alert(f"[data] feed {feed.key} halted: {reason}")


def _to_market_data(feed: FeedSpec, candle: Candle) -> MarketData:
    """Normalize one bar into the canonical bus message, stamped at the bar's own timestamp."""
    return MarketData(
        ts=candle.ts,
        symbol=feed.symbol,
        asset_class=feed.asset_class,
        ohlcv=candle.ohlcv,
    )
