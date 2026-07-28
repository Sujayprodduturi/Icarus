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

* **Nothing is published before it passes QA** (task 1.1b). Every bar goes through
  :class:`~icarus.agents.data.quality.DataQualityGate` first: a rejected bar is dropped, and a
  quarantine verdict — a price series that looks like an unadjusted corporate action — stops the
  whole feed. Staleness is judged after each sweep, vetoing a quiet symbol or halting the plane
  when the venue itself looks dead.

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
from icarus.agents.data.quality import Verdict
from icarus.common.calendar import session_closed
from icarus.common.logging import get_logger
from icarus.common.schemas import SchemaError, utc_now
from icarus.common.types import AssetClass, MarketData

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable
    from datetime import datetime

    from icarus.agents.base import RunContext
    from icarus.agents.data.quality import DataQualityGate
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
        quality: DataQualityGate | None = None,
        halt_plane: Callable[[str], Awaitable[None]] | None = None,
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
        # The QA layer can demand a plane halt (a dead venue). Accepting the gate without
        # somewhere to send that would silently downgrade a halt to a log line.
        if quality is not None and halt_plane is None:
            raise ValueError("a quality gate requires halt_plane — it can demand a plane halt")
        self._feeds = feeds
        self._source = source
        self._publish = publish
        self._alert = alert
        self._quality = quality
        self._halt_plane = halt_plane
        self._lookback = timedelta(days=lookback_days)
        self._poll_interval_s = poll_interval_s
        self._now = now_fn
        self._halted: set[str] = set()
        self._vetoed: frozenset[str] = frozenset()
        self._last_ts: dict[str, datetime] = {}

    @property
    def halted_feeds(self) -> frozenset[str]:
        """Feeds stopped by schema drift or QA quarantine. Non-empty means degraded ingestion."""
        return frozenset(self._halted)

    @property
    def vetoed_feeds(self) -> frozenset[str]:
        """Feeds gone stale: no new entries on these symbols (§37).

        Surfaced as state rather than enforced here — there is no order path in Phase 1. The Risk
        agent reads it in Phase 2. Ingestion keeps publishing whatever these feeds *do* produce;
        a stale symbol is a reason not to open a position, not a reason to discard real data.
        """
        return self._vetoed

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
            if await self._review_staleness():
                return
            if len(self._halted) == len(self._feeds):
                log.error("every feed halted; ingestion has no working inputs", agent=self.name)
                return
            await asyncio.sleep(self._poll_interval_s)

    async def _poll(self, feed: FeedSpec) -> None:
        """Fetch one feed's recent bars, run them through QA, and publish what survives."""
        to = self._now().date()
        frm = to - self._lookback
        try:
            bars = await self._source.daily_bars(feed.symbol, frm, to)
        except SchemaError as exc:
            await self._halt_feed(feed, f"schema drift: {exc}")
            return
        for candle in self._fresh(feed, bars):
            if not await self._passes_quality(feed, candle):
                continue
            await self._publish(_to_market_data(feed, candle))
            self._last_ts[feed.key] = candle.ts

    async def _passes_quality(self, feed: FeedSpec, candle: Candle) -> bool:
        """Run one bar past the QA layer. A rejected bar is dropped; a quarantine stops the feed.

        ``_last_ts`` is deliberately NOT advanced for a rejected bar: the bar was never published,
        so the next poll must reconsider it rather than skip past it as already delivered.
        """
        if self._quality is None:
            return True
        assessment = self._quality.assess(feed.key, feed.asset_class, candle)
        if assessment.accepted:
            return True
        if assessment.verdict is Verdict.QUARANTINE:
            await self._halt_feed(feed, f"QA quarantine ({assessment.reason}): {assessment.detail}")
        return False

    async def _review_staleness(self) -> bool:
        """Apply the staleness rules after a full sweep. Returns True if the plane was halted.

        Split by blast radius (operator decision, 2026-07-28): one quiet symbol vetoes that
        symbol; enough of the plane quiet at once means the venue is dead, which halts the plane.
        """
        if self._quality is None or self._halt_plane is None:
            return False
        live = {f.key: f.asset_class for f in self._feeds if f.key not in self._halted}
        if not live:
            return False
        stale = self._quality.stale_feeds(live, self._now().date())
        if stale != self._vetoed:
            self._vetoed = stale
            if stale:
                log.warning("feeds stale; no new entries on these symbols", feeds=sorted(stale))
        if self._quality.plane_is_dead(live, stale):
            reason = f"{len(stale)}/{len(live)} feeds stale — venue presumed dead"
            log.error("plane halt from data staleness", agent=self.name, reason=reason)
            await self._halt_plane(reason)
            await self._alert(f"[data] plane halted: {reason}")
            return True
        return False

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
