"""Durable-bus tests against fakeredis (tasks 0.3 + 0.13).

Covers: publish/consume round-trip + XACK, schema-drift -> DLQ (never crash the loop),
CRITICAL replay of unacked entries, EPHEMERAL never replayed. Real-Valkey equivalents run
as `integration` tests in CI (see tests/integration/).
"""

from __future__ import annotations

import fakeredis.aioredis as fa
import pytest

from icarus.bus.streams import Bus, StreamKind, StreamSpec
from icarus.common.schemas import Msg


class Ping(Msg):
    SCHEMA_VERSION = "1.0"
    note: str


REGISTRY: dict[str, type[Msg]] = {"Ping": Ping}

ORDERS = StreamSpec(name="orders", kind=StreamKind.CRITICAL, maxlen=1000)
TICKS = StreamSpec(name="ticks", kind=StreamKind.EPHEMERAL, maxlen=1000)


@pytest.fixture
def bus() -> Bus:
    return Bus(fa.FakeRedis(decode_responses=True))


async def _drain(bus: Bus, spec: StreamSpec, group: str, consumer: str) -> list[Ping]:
    out: list[Ping] = []
    async for d in bus.consume(spec, group, consumer, REGISTRY, block_ms=10):
        assert isinstance(d.message, Ping)
        out.append(d.message)
        await bus.ack(spec, group, d.entry_id)
    return out


@pytest.mark.asyncio
async def test_publish_consume_roundtrip(bus: Bus) -> None:
    await bus.publish(ORDERS, Ping(note="hello"))
    got = await _drain(bus, ORDERS, "g1", "c1")
    assert [m.note for m in got] == ["hello"]


@pytest.mark.asyncio
async def test_ack_prevents_redelivery(bus: Bus) -> None:
    await bus.publish(ORDERS, Ping(note="once"))
    first = await _drain(bus, ORDERS, "g1", "c1")
    second = await _drain(bus, ORDERS, "g1", "c1")  # already acked -> nothing new
    assert len(first) == 1
    assert second == []


@pytest.mark.asyncio
async def test_schema_drift_goes_to_dlq_not_crash(bus: Bus) -> None:
    # Simulate a producer on an incompatible MAJOR schema version.
    await bus.publish(ORDERS, Ping(note="bad", schema_version="2.0"))
    got = await _drain(bus, ORDERS, "g1", "c1")
    assert got == []  # not delivered to the handler
    assert await bus.dlq_len(ORDERS) == 1  # routed to dead-letter instead


@pytest.mark.asyncio
async def test_unknown_type_goes_to_dlq(bus: Bus) -> None:
    await bus.ensure_group(ORDERS, "g1")
    # Hand-craft a stream entry with an unregistered type name.
    await bus._r.xadd(ORDERS.name, {"type": "Nope", "body": "{}"})
    got = await _drain(bus, ORDERS, "g1", "c1")
    assert got == []
    assert await bus.dlq_len(ORDERS) == 1


@pytest.mark.asyncio
async def test_critical_replay_returns_unacked(bus: Bus) -> None:
    await bus.publish(ORDERS, Ping(note="unacked"))
    # Read but DO NOT ack -> stays pending.
    async for _ in bus.consume(ORDERS, "g1", "c1", REGISTRY, block_ms=10):
        pass
    replayed = await bus.replay_pending(ORDERS, "g1", "c1", REGISTRY)
    assert [m.message.note for m in replayed] == ["unacked"]  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_ephemeral_never_replayed(bus: Bus) -> None:
    await bus.publish(TICKS, Ping(note="tick"))
    async for _ in bus.consume(TICKS, "g1", "c1", REGISTRY, block_ms=10):
        pass
    replayed = await bus.replay_pending(TICKS, "g1", "c1", REGISTRY)
    assert replayed == []  # market-data is not replayed (§36.2)
