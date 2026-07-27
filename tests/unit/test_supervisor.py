"""Supervisor tests (task 0.5): restart-on-crash, kill-line stops all, restart-storm -> HALT."""

from __future__ import annotations

import asyncio

import fakeredis.aioredis as fa
import pytest

from icarus.agents.base import Agent, RunContext
from icarus.common.halt import HaltFlag
from icarus.orchestrator.supervisor import Supervisor


class CrashOnceAgent(Agent):
    """Crashes on the first run, then blocks until the kill-line (proves it was restarted)."""

    def __init__(self) -> None:
        super().__init__("crash-once")
        self.runs = 0

    async def run(self, ctx: RunContext) -> None:
        self.runs += 1
        if self.runs == 1:
            raise RuntimeError("boom")
        # Poll the external kill-line (a datastore flag, not an in-process Event) — the real
        # agent pattern; asyncio.Event doesn't apply.
        while not await ctx.should_halt():  # noqa: ASYNC110
            await asyncio.sleep(0.01)


class LoopUntilHaltAgent(Agent):
    def __init__(self, name: str) -> None:
        super().__init__(name)
        self.stopped = False

    async def run(self, ctx: RunContext) -> None:
        while not await ctx.should_halt():  # noqa: ASYNC110
            await asyncio.sleep(0.01)
        self.stopped = True


class AlwaysCrashAgent(Agent):
    def __init__(self) -> None:
        super().__init__("always-crash")

    async def run(self, ctx: RunContext) -> None:
        raise RuntimeError("always")


@pytest.fixture
def halt() -> HaltFlag:
    return HaltFlag(fa.FakeRedis(decode_responses=True))


@pytest.mark.asyncio
async def test_crashed_agent_is_restarted(halt: HaltFlag) -> None:
    agent = CrashOnceAgent()
    sup = Supervisor(halt, backoff_s=0.01)
    task = asyncio.create_task(sup.run([agent]))
    await asyncio.sleep(0.2)  # let it crash + restart into the blocking loop
    assert agent.runs >= 2  # restarted after the crash
    assert sup.restart_counts["crash-once"] == 1
    await halt.set("test done", source="test")  # release the loop
    await asyncio.wait_for(task, timeout=2)


@pytest.mark.asyncio
async def test_kill_line_stops_all_agents(halt: HaltFlag) -> None:
    agents = [LoopUntilHaltAgent("a"), LoopUntilHaltAgent("b")]
    sup = Supervisor(halt)
    task = asyncio.create_task(sup.run(list(agents)))
    await asyncio.sleep(0.1)
    await halt.set("manual kill", source="test")  # raise the kill-line
    await asyncio.wait_for(task, timeout=2)  # supervisor returns => all agents stopped


@pytest.mark.asyncio
async def test_restart_storm_escalates_to_halt(halt: HaltFlag) -> None:
    sup = Supervisor(halt, max_restarts=3, restart_window_s=100, backoff_s=0.001)
    await asyncio.wait_for(sup.run([AlwaysCrashAgent()]), timeout=3)
    state = await halt.state()
    assert state is not None
    assert state.source == "supervisor"
    assert "restart storm" in state.reason
