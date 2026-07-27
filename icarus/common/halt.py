"""Persistent HALT flag (task 0.14, PRD §36.4, invariant #17).

The kill must outlive the orchestrator. The HALT flag therefore lives in the shared datastore
(Valkey, AOF-persisted), NOT in orchestrator memory — so a separate process (the alerting/kill
bot, §36.4) can set it and every plane sees it, even if the orchestrator is wedged. Every plane
reads it each cycle and at startup; a set flag means stop.

Datastore-down doctrine (§36.1, invariant #18): if the flag can't be read, the caller must treat
that as halt — "I can't tell if I'm halted" fails safe to halted. :meth:`should_halt` encodes that.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import TYPE_CHECKING

from redis import asyncio as aioredis

from icarus.common.schemas import utc_now

if TYPE_CHECKING:
    from redis.asyncio import Redis

HALT_KEY = "icarus:halt"


@dataclass(frozen=True)
class HaltState:
    reason: str
    source: str  # who set it (e.g. "telegram-kill", "reconciliation-drift", "watchdog")
    set_at: str  # ISO-8601 UTC


class HaltFlag:
    """Read/write the shared HALT flag. Cheap to construct; one per process is fine."""

    def __init__(self, redis: Redis) -> None:
        self._r = redis

    @classmethod
    def from_url(cls, url: str) -> HaltFlag:
        return cls(aioredis.from_url(url, decode_responses=True))  # type: ignore[no-untyped-call]

    async def set(self, reason: str, *, source: str) -> None:
        """Raise the HALT flag. Idempotent; the first reason/source is kept if already set."""
        if await self._r.exists(HALT_KEY):
            return
        state = HaltState(reason=reason, source=source, set_at=utc_now().isoformat())
        await self._r.set(HALT_KEY, json.dumps(asdict(state)))

    async def clear(self) -> None:
        """Lower the HALT flag (operator action after resolving the cause)."""
        await self._r.delete(HALT_KEY)

    async def state(self) -> HaltState | None:
        """Return the current HALT state, or None if not halted. Raises on datastore error."""
        raw = await self._r.get(HALT_KEY)
        if raw is None:
            return None
        return HaltState(**json.loads(raw))

    async def should_halt(self) -> bool:
        """Fail-safe check for a plane's cycle: True if halted OR the datastore is unreachable."""
        try:
            return await self.state() is not None
        except (aioredis.RedisError, OSError):
            # Datastore-down with work in flight = halt (§36.1). Can't confirm safe -> stop.
            return True

    async def aclose(self) -> None:
        await self._r.aclose()
