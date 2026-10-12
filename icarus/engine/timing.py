"""Immutable invented timing and fixture bindings; no authenticated market evidence."""

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import StrEnum
from hashlib import sha256

from icarus.common.calendar import IST
from icarus.engine.fills import SimBar

STEP = timedelta(minutes=15)


def _utc(value: datetime) -> None:
    if not isinstance(value, datetime) or value.tzinfo is not UTC:
        raise ValueError("fixture times must use datetime.UTC")


def _integer(value: int, *, zero: bool = False) -> None:
    if type(value) is not int or value < (0 if zero else 1):
        raise ValueError("expected a whole quantity/index, excluding bool")


def _money(value: Decimal, *, zero: bool = False) -> None:
    if type(value) is not Decimal or not value.is_finite() or (value < 0 if zero else value <= 0):
        raise ValueError("expected finite Decimal money/volume")


def _window(start: datetime, end: datetime) -> None:
    _utc(start)
    _utc(end)
    if end <= start or start.astimezone(IST).date() != end.astimezone(IST).date():
        raise ValueError("window must be ordered within one IST date")


@dataclass(frozen=True, slots=True)
class SourceDeclaration:
    """Expected fixture identity/hash declaration, not authenticated source evidence."""

    artifact_id: str
    version: str
    sha256: str
    schema_version: int = 1

    def __post_init__(self) -> None:
        if any(type(s) is not str or not s.strip() for s in (self.artifact_id, self.version)):
            raise ValueError("source identity/version must be nonempty strings")
        if (
            type(self.sha256) is not str
            or len(self.sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.sha256)
        ):
            raise ValueError("source SHA256 must be lowercase hex")
        if type(self.schema_version) is not int or self.schema_version != 1:
            raise ValueError("only integer schema1 is supported")


@dataclass(frozen=True, slots=True)
class Session:
    index: int
    open_ts: datetime
    close_ts: datetime
    source: SourceDeclaration

    def __post_init__(self) -> None:
        _integer(self.index, zero=True)
        _window(self.open_ts, self.close_ts)
        if (self.close_ts - self.open_ts) % STEP:
            raise ValueError("declared session must partition into exact M15 bars")
        if not isinstance(self.source, SourceDeclaration):
            raise TypeError("session requires a source declaration")


@dataclass(frozen=True, slots=True)
class OpeningLiquidity:
    quantity: Decimal
    available_ts: datetime
    source: SourceDeclaration

    def __post_init__(self) -> None:
        _money(self.quantity, zero=True)
        _utc(self.available_ts)
        if not isinstance(self.source, SourceDeclaration):
            raise TypeError("opening proxy requires a source declaration")


@dataclass(frozen=True, slots=True)
class ReplayBar:
    session_index: int
    bar: SimBar
    end_ts: datetime
    opening: OpeningLiquidity | None
    source: SourceDeclaration

    def __post_init__(self) -> None:
        _integer(self.session_index, zero=True)
        if not isinstance(self.bar, SimBar):
            raise TypeError("replay bar requires SimBar")
        _window(self.bar.ts, self.end_ts)
        if self.end_ts - self.bar.ts != STEP:
            raise ValueError("only exact M15 intervals are supported")
        for price in (self.bar.open, self.bar.high, self.bar.low, self.bar.close):
            _money(price)
        _money(self.bar.volume, zero=True)
        if (
            not self.bar.low
            <= min(self.bar.open, self.bar.close)
            <= max(self.bar.open, self.bar.close)
            <= self.bar.high
        ):
            raise ValueError("OHLC range is inconsistent")
        if self.opening is not None and not isinstance(self.opening, OpeningLiquidity):
            raise TypeError("opening proxy must be a typed declaration or None")
        if not isinstance(self.source, SourceDeclaration):
            raise TypeError("bar requires a source declaration")


def fixture_digest(sessions: tuple[Session, ...], bars: tuple[ReplayBar, ...]) -> str:
    """Bind actual fixture values, excluding circular identity/hash declarations."""
    payload = [
        [(s.index, s.open_ts.isoformat(), s.close_ts.isoformat()) for s in sessions],
        [
            (
                b.session_index,
                b.bar.ts.isoformat(),
                b.end_ts.isoformat(),
                *(str(v) for v in (b.bar.open, b.bar.high, b.bar.low, b.bar.close, b.bar.volume)),
                None
                if b.opening is None
                else (str(b.opening.quantity), b.opening.available_ts.isoformat()),
            )
            for b in bars
        ],
    ]
    return sha256(json.dumps(payload, separators=(",", ":")).encode("utf-8")).hexdigest()


class Precision(StrEnum):
    SESSION_ONLY = "session_only"
    BAR_RESOLVED = "bar_resolved"
    EVENT_RESOLVED = "event_resolved"


@dataclass(frozen=True, slots=True)
class Timing:
    precision: Precision
    event_ts: datetime | None = None
    interval_start: datetime | None = None
    interval_end: datetime | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.precision, Precision):
            raise TypeError("precision must be Precision")
        for name in ("event_ts", "interval_start", "interval_end"):
            value = getattr(self, name)
            if value is not None:
                _utc(value)
        if (self.interval_start is None) != (self.interval_end is None):
            raise ValueError("interval bounds must both be present or both absent")
        if self.interval_start is not None and self.interval_end is not None:
            if self.interval_end < self.interval_start:
                raise ValueError("interval end precedes start")
            if (
                self.event_ts is not None
                and not self.interval_start <= self.event_ts <= self.interval_end
            ):
                raise ValueError("declared event lies outside its interval")
