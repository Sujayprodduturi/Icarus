"""Alerting / kill process (task 0.14, PRD §36.4, invariant #17).

Runs as its OWN supervised process, separate from the orchestrator, so the kill path survives a
wedged orchestrator. In Phase 0 it does two things:

* :meth:`kill` — set the persistent HALT flag directly. Because the flag lives in the shared
  datastore, every plane sees it on its next cycle even if the orchestrator is stalled.
* :meth:`run` — an independent heartbeat loop (its own liveness), the scaffold the Phase-2
  Telegram command handler + orchestrator-heartbeat watchdog + broker cancel-on-disconnect
  (§36.4, task 2.7 / 2.2c) plug into.

Deployed as a standalone systemd unit (see deploy/systemd). Not supervised BY the orchestrator —
that's the whole point.
"""

from __future__ import annotations

import asyncio
import os

from icarus.common.halt import HaltFlag
from icarus.common.logging import get_logger

log = get_logger("alerting")


class AlertingProcess:
    """The out-of-band kill + alert process. Phase 0 = kill flag + own heartbeat."""

    def __init__(self, halt: HaltFlag, *, heartbeat_interval_s: float = 5.0) -> None:
        self._halt = halt
        self._interval = heartbeat_interval_s

    async def kill(self, reason: str) -> None:
        """Raise the HALT flag out-of-band. This is the manual kill's enforcement point."""
        await self._halt.set(reason, source="alerting-kill")
        log.warning("kill issued", reason=reason)

    async def run(self, stop: asyncio.Event) -> None:
        """Independent loop: beat our own heartbeat until asked to stop.

        Phase 2 adds: poll Telegram for `kill`/`rollback`, watch the orchestrator heartbeat and
        fire cancel-on-disconnect if it goes stale with open positions.
        """
        log.info("alerting process started")
        while not stop.is_set():
            try:
                await asyncio.wait_for(stop.wait(), timeout=self._interval)
            except TimeoutError:
                pass  # next tick; Phase 2 does real work here
        log.info("alerting process stopped")


async def _main() -> None:
    url = os.environ.get("ICARUS_VALKEY_URL", "redis://localhost:6379/0")
    proc = AlertingProcess(HaltFlag.from_url(url))
    await proc.run(asyncio.Event())  # runs until cancelled (systemd stop)


if __name__ == "__main__":
    asyncio.run(_main())
