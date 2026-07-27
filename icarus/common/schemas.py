"""Message contracts for the Icarus bus.

Every message on the bus carries ``schema_version``, ``ts`` (UTC tz-aware), and a
``correlation_id`` for audit/replay (CLAUDE.md §3, PRD §10).

Schema-evolution policy (PRD §39.2, invariant #22):

* **Minor bump** (same major, new *optional* fields) is additive and back-compatible
  — a consumer on an older minor MUST NOT halt; it ignores unknown optional fields.
* **Major mismatch** is incompatible — the consumer raises :class:`SchemaError` and the
  caller halts that feed. Never best-effort parse across a major boundary (CLAUDE.md §3).

Timestamps are stored tz-aware in UTC; convert to IST only at session/calendar/tax
boundaries (PRD §29.5, invariant #22).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, ClassVar

from pydantic import BaseModel, ConfigDict, Field, field_validator


class SchemaError(Exception):
    """Raised on an incompatible (major) ``schema_version`` mismatch.

    The Data-Ingestion agent raises this on schema drift and signals the Orchestrator
    to halt that feed — fail safe, never best-effort parse (PRD §10, CLAUDE.md §3).
    """

    def __init__(
        self, message: str, *, expected: str | None = None, got: str | None = None
    ) -> None:
        super().__init__(message)
        self.expected = expected
        self.got = got


def utc_now() -> datetime:
    """Timezone-aware current UTC time. The one blessed clock source for message ts."""
    return datetime.now(UTC)


def new_correlation_id() -> str:
    """Fresh correlation id for a new causal chain (e.g. a bar tick fanning out)."""
    return str(uuid.uuid4())


def _parse_version(version: str) -> tuple[int, int]:
    """Parse a ``"major.minor"`` string into an ``(major, minor)`` tuple."""
    try:
        major_s, minor_s = version.split(".", 1)
        return int(major_s), int(minor_s)
    except (ValueError, AttributeError) as exc:  # malformed version string
        raise SchemaError(f"malformed schema_version {version!r}", got=version) from exc


def check_compatible(*, local: str, incoming: str) -> None:
    """Enforce the §39.2 policy between a consumer's ``local`` schema and an ``incoming`` one.

    * Same major, incoming minor <= or > local minor → compatible (additive), return.
    * Different major → :class:`SchemaError` (caller halts the feed).
    """
    local_major, _ = _parse_version(local)
    inc_major, _ = _parse_version(incoming)
    if local_major != inc_major:
        raise SchemaError(
            f"incompatible schema major version: consumer speaks {local}, message is {incoming}",
            expected=local,
            got=incoming,
        )
    # Same major: additive minor differences are back-compatible → no halt.


class Msg(BaseModel):
    """Base class for every typed bus message.

    Subclasses set a class-level ``SCHEMA_VERSION`` (``"major.minor"``). The wire field
    ``schema_version`` defaults to it. Use :meth:`ensure_compatible` on receipt.
    """

    # Immutable + reject unknown fields at a MAJOR level is enforced via ensure_compatible;
    # we allow extra so an additive minor from a newer producer doesn't hard-fail parsing.
    model_config = ConfigDict(frozen=True, extra="allow")

    SCHEMA_VERSION: ClassVar[str] = "1.0"

    schema_version: str = Field(default="")
    ts: datetime = Field(default_factory=utc_now)
    correlation_id: str = Field(default_factory=new_correlation_id)

    def model_post_init(self, __context: Any) -> None:
        # Stamp the class schema version when the caller didn't supply one.
        if not self.schema_version:
            object.__setattr__(self, "schema_version", self.SCHEMA_VERSION)

    @field_validator("ts")
    @classmethod
    def _ts_must_be_utc_aware(cls, v: datetime) -> datetime:
        if v.tzinfo is None:
            raise ValueError("ts must be timezone-aware (store UTC; PRD §29.5)")
        return v.astimezone(UTC)

    def ensure_compatible(self) -> None:
        """Raise :class:`SchemaError` if this message's major version differs from the consumer's.

        Call this the moment a message is deserialized off the bus.
        """
        check_compatible(local=self.SCHEMA_VERSION, incoming=self.schema_version)
