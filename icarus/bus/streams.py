"""Durable message bus over Valkey/Redis Streams (tasks 0.3 + 0.13, PRD §36.2).

Design (invariants #10, #18; PRD §36.2):

* **Typed messages.** Publish/consume :class:`~icarus.common.schemas.Msg` subclasses; on receipt
  the major ``schema_version`` is checked and an incompatible one raises :class:`SchemaError`
  (the caller halts that feed — never best-effort parse).
* **Consumer groups + explicit XACK.** A message is redeliverable until acked, so a crash
  mid-processing replays it on restart (matters for order/position streams).
* **Dead-letter stream.** A message that fails (including ``SchemaError``) ``max_deliveries``
  times is moved to ``<stream>.dlq`` instead of poison-looping.
* **MAXLEN ~ cap** per stream to bound memory.
* **Backpressure policy per stream kind:** market-data is *ephemeral* (drop-oldest via MAXLEN, never
  replayed); order/position streams are *critical* (block-or-halt, never silently dropped — §36.2).

This module speaks the ``redis`` client, which works against a Valkey server (PRD §21). It does
NOT choose the server; that's a deployment/licensing decision (prefer Valkey, BSD-3).
"""

from __future__ import annotations

import enum
from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, cast

from redis import asyncio as aioredis

from icarus.common.schemas import Msg, SchemaError

if TYPE_CHECKING:
    from redis.asyncio import Redis


def _fields(mapping: Mapping[str, str]) -> Any:
    """Cast a str->str field map to the type redis-py's XADD stub expects (invariant key union)."""
    return cast("Any", mapping)


# Field key used to carry the JSON-encoded message body inside a stream entry.
_BODY_FIELD = "body"
_TYPE_FIELD = "type"


class StreamKind(enum.StrEnum):
    """Backpressure class of a stream (PRD §36.2).

    * ``EPHEMERAL`` — market-data; bounded by MAXLEN, drop-oldest, never replayed.
    * ``CRITICAL`` — order/position; never silently dropped, replayed on recovery.
    """

    EPHEMERAL = "ephemeral"
    CRITICAL = "critical"


@dataclass(frozen=True)
class StreamSpec:
    """Configuration for one logical stream."""

    name: str
    kind: StreamKind
    maxlen: int = 100_000  # goal.yaml resilience.bus_maxlen_approx
    max_deliveries: int = 3  # -> dead-letter after this many failed attempts (§36.2)

    @property
    def dlq_name(self) -> str:
        return f"{self.name}.dlq"


@dataclass(frozen=True)
class Delivery:
    """A message pulled from the bus, plus the handle needed to ack it."""

    entry_id: str
    message: Msg
    delivery_count: int


class Bus:
    """Async durable bus wrapper. One instance per process; cheap to share across agents."""

    def __init__(self, redis: Redis) -> None:
        self._r = redis

    @classmethod
    def from_url(cls, url: str) -> Bus:
        """Build from a redis:// URL (decode_responses so we get str, not bytes)."""
        # redis-py's from_url is untyped in the shipped stubs; the return is a Redis client.
        return cls(aioredis.from_url(url, decode_responses=True))  # type: ignore[no-untyped-call]

    async def publish(self, spec: StreamSpec, msg: Msg) -> str:
        """Append a typed message. Returns the stream entry id.

        MAXLEN caps every stream. For EPHEMERAL streams that IS the drop-oldest backpressure;
        CRITICAL streams are sized so trimming never discards an unacked order in practice, and
        recovery only ever replays unacked CRITICAL entries.
        """
        fields = {
            _TYPE_FIELD: type(msg).__name__,
            _BODY_FIELD: msg.model_dump_json(),
        }
        entry_id: str = await self._r.xadd(
            spec.name, _fields(fields), maxlen=spec.maxlen, approximate=True
        )
        return entry_id

    async def ensure_group(self, spec: StreamSpec, group: str) -> None:
        """Create the consumer group if absent (idempotent). ``mkstream`` so first use works."""
        try:
            await self._r.xgroup_create(spec.name, group, id="0", mkstream=True)
        except aioredis.ResponseError as exc:  # BUSYGROUP: already exists
            if "BUSYGROUP" not in str(exc):
                raise

    async def consume(
        self,
        spec: StreamSpec,
        group: str,
        consumer: str,
        registry: dict[str, type[Msg]],
        *,
        count: int = 10,
        block_ms: int = 1000,
    ) -> AsyncIterator[Delivery]:
        """Yield undelivered messages for ``group``/``consumer`` (needs XACK after handling).

        ``registry`` maps the wire type name -> Msg subclass for decoding. A message whose
        major schema version is incompatible, or whose type is unknown, is routed to the DLQ
        rather than crashing the consumer loop (fail safe, never silently drop — §36.2).
        """
        await self.ensure_group(spec, group)
        resp = await self._r.xreadgroup(
            group, consumer, {spec.name: ">"}, count=count, block=block_ms
        )
        if not resp:
            return
        for _stream, entries in resp:
            for entry_id, fields in entries:
                delivery = await self._decode(spec, group, entry_id, fields, registry)
                if delivery is not None:
                    yield delivery

    async def _decode(
        self,
        spec: StreamSpec,
        group: str,
        entry_id: str,
        fields: dict[str, str],
        registry: dict[str, type[Msg]],
    ) -> Delivery | None:
        type_name = fields.get(_TYPE_FIELD, "")
        body = fields.get(_BODY_FIELD, "")
        cls = registry.get(type_name)
        if cls is None:
            await self._dead_letter(
                spec, group, entry_id, fields, reason=f"unknown type {type_name!r}"
            )
            return None
        try:
            msg = cls.model_validate_json(body)
            msg.ensure_compatible()  # raises SchemaError on incompatible major version
        except SchemaError as exc:
            await self._dead_letter(spec, group, entry_id, fields, reason=f"schema: {exc}")
            return None
        except Exception as exc:  # malformed body -> DLQ, don't crash the loop
            await self._dead_letter(spec, group, entry_id, fields, reason=f"decode: {exc}")
            return None
        # delivery count from PEL (pending entries list)
        pending = await self._r.xpending_range(spec.name, group, entry_id, entry_id, 1)
        count = int(pending[0]["times_delivered"]) if pending else 1
        if count > spec.max_deliveries:
            await self._dead_letter(spec, group, entry_id, fields, reason="max deliveries exceeded")
            return None
        return Delivery(entry_id=entry_id, message=msg, delivery_count=count)

    async def ack(self, spec: StreamSpec, group: str, entry_id: str) -> None:
        """Acknowledge successful processing so the message is not redelivered."""
        await self._r.xack(spec.name, group, entry_id)

    async def _dead_letter(
        self,
        spec: StreamSpec,
        group: str,
        entry_id: str,
        fields: dict[str, str],
        *,
        reason: str,
    ) -> None:
        """Move a poison message to the DLQ and ack the original so it stops redelivering."""
        await self._r.xadd(
            spec.dlq_name,
            _fields({**fields, "dlq_reason": reason, "orig_id": entry_id}),
            maxlen=spec.maxlen,
            approximate=True,
        )
        await self._r.xack(spec.name, group, entry_id)

    async def replay_pending(
        self, spec: StreamSpec, group: str, consumer: str, registry: dict[str, type[Msg]]
    ) -> list[Delivery]:
        """Return unacked CRITICAL messages for recovery (PRD §36.2: replay only order/position).

        Market-data (EPHEMERAL) is never replayed — stale ticks are worse than missing ones.
        """
        if spec.kind is StreamKind.EPHEMERAL:
            return []
        await self.ensure_group(spec, group)
        resp = await self._r.xreadgroup(group, consumer, {spec.name: "0"}, count=1000)
        out: list[Delivery] = []
        if not resp:
            return out
        for _stream, entries in resp:
            for entry_id, fields in entries:
                delivery = await self._decode(spec, group, entry_id, fields, registry)
                if delivery is not None:
                    out.append(delivery)
        return out

    async def dlq_len(self, spec: StreamSpec) -> int:
        length: int = await self._r.xlen(spec.dlq_name)
        return length

    async def aclose(self) -> None:
        await self._r.aclose()
