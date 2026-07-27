"""Agent supervision + the kill-line (task 0.5, PRD §9.3, §28, invariant #10/#17).

The Supervisor runs each agent as an asyncio task and:
* **restarts** an agent that crashes (raises), with backoff;
* escalates a **restart storm** (too many restarts in a window) to a plane HALT — a wedged agent
  must not thrash forever (§28);
* enforces the **kill-line**: when the HALT flag is raised, every agent is cancelled promptly,
  even one ignoring its own ``should_halt`` check.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque

from icarus.agents.base import Agent, RunContext
from icarus.common.halt import HaltFlag
from icarus.common.logging import get_logger

log = get_logger("supervisor")


class Supervisor:
    def __init__(
        self,
        halt: HaltFlag,
        *,
        max_restarts: int = 3,
        restart_window_s: float = 10.0,
        backoff_s: float = 0.05,
        kill_poll_s: float = 0.05,
    ) -> None:
        self._halt = halt
        self._max_restarts = max_restarts
        self._window_s = restart_window_s
        self._backoff_s = backoff_s
        self._kill_poll_s = kill_poll_s
        self.restart_counts: dict[str, int] = {}

    async def run(self, agents: list[Agent]) -> None:
        """Run all agents until they finish, a restart storm halts, or the kill-line fires."""
        ctx = RunContext(should_halt=self._halt.should_halt)
        workers = [asyncio.create_task(self._supervise(a, ctx), name=a.name) for a in agents]
        monitor = asyncio.create_task(self._kill_monitor(workers), name="kill-line")
        try:
            await asyncio.gather(*workers, return_exceptions=True)
        finally:
            monitor.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await monitor

    async def _kill_monitor(self, workers: list[asyncio.Task[None]]) -> None:
        """Poll the HALT flag; on halt, cancel every agent (the kill-line)."""
        while True:
            if await self._halt.should_halt():
                log.warning("kill-line raised: cancelling all agents")
                for w in workers:
                    w.cancel()
                return
            await asyncio.sleep(self._kill_poll_s)

    async def _supervise(self, agent: Agent, ctx: RunContext) -> None:
        """Run one agent, restarting on crash until it completes or a storm escalates to HALT."""
        restarts: deque[float] = deque()
        while True:
            try:
                await agent.run(ctx)
                return  # normal completion
            except asyncio.CancelledError:
                return  # kill-line cancelled us — stop cleanly
            except Exception as exc:
                self.restart_counts[agent.name] = self.restart_counts.get(agent.name, 0) + 1
                now = asyncio.get_event_loop().time()
                restarts.append(now)
                while restarts and now - restarts[0] > self._window_s:
                    restarts.popleft()
                log.warning("agent crashed; restarting", agent=agent.name, error=str(exc))
                if len(restarts) > self._max_restarts:
                    await self._halt.set(f"restart storm: agent {agent.name}", source="supervisor")
                    log.error("restart storm -> plane HALT", agent=agent.name)
                    return
                await asyncio.sleep(self._backoff_s)
