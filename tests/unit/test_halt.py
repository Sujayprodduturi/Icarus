"""HALT flag + alerting-kill tests (task 0.14, PRD §36.4, invariant #17)."""

from __future__ import annotations

import fakeredis.aioredis as fa
import pytest

from icarus.agents.oversight.alerting import AlertingProcess
from icarus.common.halt import HaltFlag


@pytest.fixture
def redis() -> fa.FakeRedis:
    return fa.FakeRedis(decode_responses=True)


@pytest.mark.asyncio
async def test_set_and_read_flag(redis: fa.FakeRedis) -> None:
    flag = HaltFlag(redis)
    assert await flag.state() is None
    await flag.set("reconciliation drift", source="portfolio")
    state = await flag.state()
    assert state is not None
    assert state.reason == "reconciliation drift"
    assert state.source == "portfolio"


@pytest.mark.asyncio
async def test_clear_flag(redis: fa.FakeRedis) -> None:
    flag = HaltFlag(redis)
    await flag.set("x", source="test")
    await flag.clear()
    assert await flag.state() is None


@pytest.mark.asyncio
async def test_flag_outlives_orchestrator_cross_instance(redis: fa.FakeRedis) -> None:
    # The kill process and a plane are DIFFERENT objects sharing only the datastore — modeling
    # separate OS processes. A flag set by one must be seen by the other (invariant #17).
    kill_side = HaltFlag(redis)
    plane_side = HaltFlag(redis)  # a different plane/process
    await kill_side.set("manual kill", source="alerting-kill")
    assert await plane_side.should_halt() is True


@pytest.mark.asyncio
async def test_set_is_idempotent_keeps_first_reason(redis: fa.FakeRedis) -> None:
    flag = HaltFlag(redis)
    await flag.set("first", source="a")
    await flag.set("second", source="b")
    state = await flag.state()
    assert state is not None
    assert state.reason == "first"  # first cause wins; not overwritten


@pytest.mark.asyncio
async def test_should_halt_false_when_clear(redis: fa.FakeRedis) -> None:
    assert await HaltFlag(redis).should_halt() is False


@pytest.mark.asyncio
async def test_datastore_down_fails_safe_to_halt() -> None:
    # A HaltFlag whose datastore raises on read must report should_halt() = True (§36.1).
    class _BrokenRedis:
        async def get(self, _key: str) -> str:
            raise OSError("valkey down")

    flag = HaltFlag(_BrokenRedis())  # type: ignore[arg-type]
    assert await flag.should_halt() is True


@pytest.mark.asyncio
async def test_alerting_kill_sets_flag(redis: fa.FakeRedis) -> None:
    flag = HaltFlag(redis)
    proc = AlertingProcess(flag)
    await proc.kill("operator pressed kill")
    state = await flag.state()
    assert state is not None
    assert state.source == "alerting-kill"
