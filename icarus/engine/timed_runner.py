"""Canonical local data records for the guarded time-resolved simulator."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from itertools import pairwise
from typing import Any, Protocol
from uuid import NAMESPACE_URL, uuid5

import numpy as np

from icarus.common.calendar import IST
from icarus.common.config import LOCKBOX_START
from icarus.engine.benchmark_match import (
    AvailabilityBasis,
    BenchmarkCandle,
    BenchmarkMode,
    FixtureIdentity,
)
from icarus.engine.data_readiness import ARTIFACT_ROLES, BundlePreflight
from icarus.engine.fills import SimBar
from icarus.engine.source_pair import (
    PairQualification,
    _bind_source_pair,
    validate_source_pair_identities,
)
from icarus.engine.timed_simulation import (
    DecisionAvailability,
    OpeningLiquidity,
    Refinement,
    ReplayBar,
    Session,
    SourceDeclaration,
    TimedFixture,
    timed_fixture_digest,
)
from icarus.state.trial_ledger import (
    EvaluationReservation,
    JsonValue,
    TrialBatchReceipt,
    TrialBatchReservation,
    TrialEvaluationResult,
    TrialKind,
    TrialLedgerUnavailable,
    TrialOrigin,
    TrialReservationAuthorization,
)
from icarus.strategy.dsl import Bars, Panel


class InputUnavailable(ValueError):
    pass


class RunnerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class CalendarRecord:
    record_id: str
    revision: str
    source_index: int | None
    session_date: date
    state: str
    open_ts: datetime | None
    close_ts: datetime | None


@dataclass(frozen=True, slots=True)
class NiftyObservation:
    record_id: str
    revision: str
    event_ts: datetime
    available_ts: datetime
    observed: bool
    price: Fraction


@dataclass(frozen=True, slots=True)
class AssembledTimedInputs:
    panel: Panel
    fixture: TimedFixture
    source_indices: tuple[int, ...]
    nifty: tuple[NiftyObservation, ...]
    data_qualified: bool
    nifty_source: SourceDeclaration | None = None
    benchmark_mode: BenchmarkMode = BenchmarkMode.EXACT_OBSERVED_SESSION_CLOSE
    benchmark_candles: tuple[BenchmarkCandle, ...] = ()
    benchmark_identity: FixtureIdentity | None = None


@dataclass(frozen=True, slots=True)
class RunAuthorization:
    authorization_id: str
    issued_at: datetime
    expires_at: datetime
    bundle_sha256: str
    approval_sha256: str
    policy_sha256: str
    qualification_sha256: str
    goal_sha256: str
    cards_sha256: str
    runner_sha256: str
    actual_ledger_activated: bool
    invented: bool


@dataclass(frozen=True, slots=True)
class ExecutionBinding:
    bundle_sha256: str
    approval_sha256: str
    policy_sha256: str
    qualification_sha256: str
    goal_sha256: str
    cards_sha256: str
    runner_sha256: str


def parse_run_authorization_json(raw: bytes) -> RunAuthorization:
    """Parse the separate external execution authorization without truthy coercions."""
    value = _records(raw)
    if len(value) != 1:
        raise RunnerError("AUTHORIZATION_JSON")
    row = value[0]
    fields = {
        "schema_version",
        "authorization_id",
        "issued_at",
        "expires_at",
        "bundle_sha256",
        "approval_sha256",
        "policy_sha256",
        "qualification_sha256",
        "goal_sha256",
        "cards_sha256",
        "runner_sha256",
        "actual_ledger_activated",
        "invented",
    }
    if (
        set(row) != fields
        or type(row["schema_version"]) is not int
        or row["schema_version"] != 1
        or type(row["actual_ledger_activated"]) is not bool
        or type(row["invented"]) is not bool
    ):
        raise RunnerError("AUTHORIZATION_SCHEMA")
    try:
        authorization = RunAuthorization(
            _text(row["authorization_id"]),
            _utc(row["issued_at"]),
            _utc(row["expires_at"]),
            _text(row["bundle_sha256"]),
            _text(row["approval_sha256"]),
            _text(row["policy_sha256"]),
            _text(row["qualification_sha256"]),
            _text(row["goal_sha256"]),
            _text(row["cards_sha256"]),
            _text(row["runner_sha256"]),
            row["actual_ledger_activated"],
            row["invented"],
        )
    except (InputUnavailable, TypeError, ValueError) as exc:
        raise RunnerError("AUTHORIZATION_SCHEMA") from exc
    GuardedTimedRunner._validate_authorization(authorization)
    return authorization


@dataclass(frozen=True, slots=True)
class EvaluationPlan:
    card: str
    card_version: int
    card_sha256: str
    mode: str
    capital: int | None
    evaluations: tuple[EvaluationReservation, ...]
    primitives: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if (
            not self.card
            or type(self.card_version) is not int
            or self.card_version <= 0
            or len(self.card_sha256) != 64
            or any(c not in "0123456789abcdef" for c in self.card_sha256)
            or self.mode not in ("signal", "portfolio")
        ):
            raise ValueError("evaluation plan needs a card and supported mode")
        if (self.mode == "signal") != (self.capital is None):
            raise ValueError("only portfolio evaluations carry capital")
        if self.capital is not None and (type(self.capital) is not int or self.capital <= 0):
            raise ValueError("capital must be a positive whole amount")
        if not self.evaluations or any(
            not isinstance(item, EvaluationReservation) for item in self.evaluations
        ):
            raise ValueError("evaluation plan requires exact persisted geometry")
        if (
            type(self.primitives) is not tuple
            or self.primitives != tuple(sorted(set(self.primitives)))
            or any(type(item) is not str or not item for item in self.primitives)
        ):
            raise ValueError("evaluation primitives must be a sorted unique immutable tuple")
        kinds = {item.kind for item in self.evaluations}
        if self.mode == "portfolio" and kinds != {TrialKind.PORTFOLIO}:
            raise ValueError("portfolio plan requires portfolio geometry")
        if self.mode == "signal" and not (
            (kinds == {TrialKind.DESCRIPTIVE_PILOT} and len(self.evaluations) == 1)
            or kinds == {TrialKind.SIGNAL_FULL, TrialKind.SIGNAL_FOLD}
        ):
            raise ValueError(
                "signal plan requires descriptive singleton or full-span and fold geometry"
            )


@dataclass(frozen=True, slots=True)
class EvaluationOutcome:
    payload: object
    observation_count: int

    def __post_init__(self) -> None:
        if type(self.observation_count) is not int or self.observation_count < 0:
            raise ValueError("observation_count must be a nonnegative whole number")


class _Ledger(Protocol):
    def reserve(self, batch: TrialBatchReservation) -> TrialBatchReceipt: ...

    def complete(
        self, receipt: TrialBatchReceipt, results: tuple[TrialEvaluationResult, ...]
    ) -> object: ...

    def fail(self, receipt: TrialBatchReceipt, *, failure_code: str) -> object: ...


def _hash_text(*parts: object) -> str:
    return hashlib.sha256(
        json.dumps(parts, separators=(",", ":"), sort_keys=True).encode()
    ).hexdigest()


def _json_value(value: object) -> JsonValue:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if isinstance(value, dict) and all(isinstance(key, str) for key in value):
        return {key: _json_value(item) for key, item in value.items()}
    raise RunnerError("RESULT_JSON")


class GuardedTimedRunner:
    """Reserve every evaluation before the one shared price decode and release after terminals."""

    def __init__(self, ledger: _Ledger) -> None:
        self._ledger = ledger

    def _fail_all(self, receipts: tuple[tuple[TrialBatchReceipt, str], ...]) -> None:
        first_error: Exception | None = None
        for receipt, code in receipts:
            try:
                self._ledger.fail(receipt, failure_code=code)
            except Exception as exc:
                if first_error is None:
                    first_error = exc
        if first_error is not None:
            raise RunnerError("TERMINAL_WRITE_FAILED") from first_error

    @staticmethod
    def _validate_authorization(value: RunAuthorization) -> None:
        if not isinstance(value, RunAuthorization):
            raise TypeError("authorization must be typed")
        if value.invented:
            raise RunnerError("INVENTED_AUTHORIZATION")
        if not value.actual_ledger_activated:
            raise RunnerError("LEDGER_NOT_ACTIVATED")
        now = datetime.now(UTC)
        if (
            value.issued_at.tzinfo is not UTC
            or value.expires_at.tzinfo is not UTC
            or value.issued_at > now
            or value.expires_at <= now
            or value.expires_at <= value.issued_at
        ):
            raise RunnerError("AUTHORIZATION_EXPIRED")
        for item in (
            value.bundle_sha256,
            value.approval_sha256,
            value.policy_sha256,
            value.qualification_sha256,
            value.goal_sha256,
            value.cards_sha256,
            value.runner_sha256,
        ):
            if len(item) != 64 or any(c not in "0123456789abcdef" for c in item):
                raise RunnerError("AUTHORIZATION_BINDING")

    @staticmethod
    def _batch(authorization: RunAuthorization, plan: EvaluationPlan) -> TrialBatchReservation:
        binding = _hash_text(
            authorization.authorization_id,
            authorization.issued_at.isoformat(),
            authorization.bundle_sha256,
            authorization.approval_sha256,
            authorization.policy_sha256,
            authorization.qualification_sha256,
            authorization.goal_sha256,
            authorization.cards_sha256,
            authorization.runner_sha256,
            plan.mode,
            plan.capital,
        )
        return TrialBatchReservation(
            uuid5(
                NAMESPACE_URL,
                f"{authorization.authorization_id}/{plan.card}/{plan.mode}/{plan.capital}",
            ),
            TrialOrigin.OPERATOR,
            plan.card,
            plan.card_version,
            plan.card_sha256,
            authorization.bundle_sha256,
            binding,
            plan.primitives,
            plan.evaluations,
        )

    def run(
        self,
        authorization: RunAuthorization,
        binding: ExecutionBinding,
        plans: tuple[EvaluationPlan, ...],
        decode_prices: Callable[[], object],
        evaluate: Callable[[EvaluationPlan, object], tuple[EvaluationOutcome, ...]],
    ) -> tuple[tuple[EvaluationOutcome, ...], ...]:
        self._validate_authorization(authorization)
        fields = (
            "bundle_sha256",
            "approval_sha256",
            "policy_sha256",
            "qualification_sha256",
            "goal_sha256",
            "cards_sha256",
            "runner_sha256",
        )
        if not isinstance(binding, ExecutionBinding) or tuple(
            getattr(authorization, field) for field in fields
        ) != tuple(getattr(binding, field) for field in fields):
            raise RunnerError("AUTHORIZATION_BINDING_MISMATCH")
        if not plans or any(not isinstance(plan, EvaluationPlan) for plan in plans):
            raise RunnerError("EVALUATION_PLANS")
        batches = tuple(self._batch(authorization, plan) for plan in plans)
        reserved: list[tuple[TrialBatchReceipt, TrialBatchReservation]] = []
        for batch in batches:
            try:
                receipt = self._ledger.reserve(batch)
            except Exception:
                self._fail_all(
                    tuple((prior, "RESERVATION_SET_INCOMPLETE") for prior, _ in reserved)
                )
                raise RunnerError("RESERVATION_SET_INCOMPLETE") from None
            if receipt.authorization is not TrialReservationAuthorization.NEW_EVALUATION:
                self._fail_all(
                    tuple((prior, "RESERVATION_SET_INCOMPLETE") for prior, _ in reserved)
                )
                raise RunnerError("RECOVERY_ONLY")
            reserved.append((receipt, batch))
        try:
            payload = decode_prices()
        except Exception:
            self._fail_all(tuple((receipt, "PRICE_DECODE_FAILED") for receipt, _ in reserved))
            raise RunnerError("PRICE_DECODE_FAILED") from None
        released: list[tuple[EvaluationOutcome, ...]] = []
        for position, (plan, (receipt, batch)) in enumerate(zip(plans, reserved, strict=True)):
            try:
                result = evaluate(plan, payload)
                if len(result) != len(batch.evaluations) or any(
                    not isinstance(outcome, EvaluationOutcome) for outcome in result
                ):
                    raise RunnerError("EVALUATION_RESULT_GEOMETRY")
                rows = tuple(
                    TrialEvaluationResult(
                        item.ordinal,
                        item.kind,
                        None,
                        None,
                        outcome.observation_count,
                        {"pre_tax_diagnostic": True, "result": _json_value(outcome.payload)},
                    )
                    for item, outcome in zip(batch.evaluations, result, strict=True)
                )
            except Exception:
                self._fail_all(
                    (
                        (receipt, "EVALUATION_FAILED"),
                        *(
                            (later, "EVALUATION_NOT_STARTED")
                            for later, _later_batch in reserved[position + 1 :]
                        ),
                    )
                )
                raise RunnerError("EVALUATION_FAILED") from None
            try:
                self._ledger.complete(receipt, rows)
            except TrialLedgerUnavailable:
                try:
                    self._ledger.complete(receipt, rows)
                except Exception:
                    self._fail_all(
                        tuple(
                            (later, "EVALUATION_NOT_STARTED")
                            for later, _later_batch in reserved[position + 1 :]
                        )
                    )
                    raise RunnerError("TERMINAL_WRITE_FAILED") from None
            except Exception:
                self._fail_all(
                    tuple(
                        (later, "EVALUATION_NOT_STARTED")
                        for later, _later_batch in reserved[position + 1 :]
                    )
                )
                raise RunnerError("TERMINAL_WRITE_FAILED") from None
            released.append(result)
        return tuple(released)


def _records(raw: bytes) -> tuple[dict[str, Any], ...]:
    if type(raw) is not bytes:
        raise TypeError("JSONL payload must be bytes")
    values: list[dict[str, Any]] = []

    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate JSON key")
            value[key] = item
        return value

    try:
        text = raw.decode("utf-8")
        for line in text.splitlines():
            value = json.loads(
                line,
                object_pairs_hook=pairs,
                parse_constant=lambda _: (_ for _ in ()).throw(ValueError("non-finite JSON")),
            )
            if type(value) is not dict:
                raise InputUnavailable("JSONL_OBJECT")
            values.append(value)
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise InputUnavailable("JSONL_SYNTAX") from exc
    if not values:
        raise InputUnavailable("JSONL_EMPTY")
    return tuple(values)


def _utc(value: object) -> datetime:
    if (
        type(value) is not str
        or not value.endswith("Z")
        or re.search(r"\.\d{7,}Z$", value) is not None
    ):
        raise InputUnavailable("UTC_TIMESTAMP")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise InputUnavailable("UTC_TIMESTAMP") from exc
    if parsed.tzinfo is not UTC:
        raise InputUnavailable("UTC_TIMESTAMP")
    return parsed


def _text(value: object) -> str:
    if type(value) is not str or not value:
        raise InputUnavailable("TEXT_FIELD")
    return value


def _decimal(value: object, *, zero: bool = False) -> Decimal:
    if type(value) is not str:
        raise InputUnavailable("DECIMAL_TEXT")
    try:
        parsed = Decimal(value)
    except Exception as exc:
        raise InputUnavailable("DECIMAL_TEXT") from exc
    if not parsed.is_finite() or (parsed < 0 if zero else parsed <= 0):
        raise InputUnavailable("DECIMAL_VALUE")
    return parsed


def _typed_rows(raw: bytes, fields: set[str], code: str) -> tuple[dict[str, Any], ...]:
    rows = _records(raw)
    if any(
        set(row) != fields
        or type(row.get("schema_version")) is not int
        or row["schema_version"] != 1
        for row in rows
    ):
        raise InputUnavailable(code)
    return rows


def assemble_timed_inputs(
    preflight: BundlePreflight,
    source_pair: PairQualification | None = None,
    *,
    benchmark_mode: BenchmarkMode = BenchmarkMode.EXACT_OBSERVED_SESSION_CLOSE,
    availability_model: str | None = None,
) -> AssembledTimedInputs:
    """Decode all seven captured artifacts and build one causally aligned engine input."""
    if (
        not isinstance(preflight, BundlePreflight)
        or not preflight.software_verified
        or not isinstance(benchmark_mode, BenchmarkMode)
    ):
        raise InputUnavailable("PREFLIGHT_REQUIRED")
    if benchmark_mode is BenchmarkMode.DESCRIPTIVE_CANDLE_PROXY:
        if availability_model != "MODELED_NEXT_SESSION_OPEN_V1":
            raise InputUnavailable("AVAILABILITY_MODEL")
    elif availability_model is not None:
        raise InputUnavailable("AVAILABILITY_MODEL")
    payloads = {item.role: item.payload for item in preflight.artifacts}
    if tuple(payloads) != ARTIFACT_ROLES:
        raise InputUnavailable("ARTIFACT_ROLES")
    artifacts = {item.role: item for item in preflight.artifacts}
    if source_pair is not None:
        expected = {
            "daily_stock": source_pair.daily_sha256,
            "m15_stock": source_pair.m15_sha256,
            "corporate_action": source_pair.action_sha256,
            "session_calendar": source_pair.calendar_sha256,
        }
        if any(artifacts[role].sha256 != digest for role, digest in expected.items()):
            raise InputUnavailable("PAIR_ARTIFACT_BINDING")
        try:
            validate_source_pair_identities(
                source_pair, {role: artifact.metadata for role, artifact in artifacts.items()}
            )
        except ValueError as exc:
            raise InputUnavailable("PAIR_SOURCE_IDENTITY") from exc
    role_identity = {
        "daily_stock": ("NSE", "CASH_EQUITY", "BACK_ADJUSTED"),
        "pit_universe": ("NSE", "CASH_EQUITY", "POINT_IN_TIME_MEMBERSHIP"),
        "corporate_action": ("NSE", "CASH_EQUITY", "BACK_ADJUSTED"),
        "m15_stock": ("NSE", "CASH_EQUITY", "BACK_ADJUSTED"),
        "nifty_observation": ("NSE", "NIFTY 50", "PRICE_INDEX"),
        "session_calendar": ("NSE", "CASH_EQUITY", "EXCHANGE_SESSION"),
        "opening_liquidity": ("NSE", "CASH_EQUITY", "PRIOR_OBSERVED_QUANTITY"),
    }
    coverage: dict[str, tuple[datetime, datetime]] = {}
    for role, artifact in artifacts.items():
        metadata = artifact.metadata
        if (
            metadata.get("format") != "jsonl"
            or type(metadata.get("schema_version")) is not int
            or metadata["schema_version"]
            != (
                2
                if role == "nifty_observation"
                and benchmark_mode is BenchmarkMode.DESCRIPTIVE_CANDLE_PROXY
                else 1
            )
            or metadata.get("parser_version")
            != (
                "icarus-benchmark-candle-v2"
                if role == "nifty_observation"
                and benchmark_mode is BenchmarkMode.DESCRIPTIVE_CANDLE_PROXY
                else "icarus-real-data-v1"
            )
            or type(metadata.get("source_revision")) is not str
            or not metadata["source_revision"]
            or (
                metadata.get("venue"),
                metadata.get("instrument"),
                metadata.get("price_basis"),
            )
            != role_identity[role]
            or metadata.get("projection_policy")
            != (benchmark_mode.value if role == "nifty_observation" else "NONE")
        ):
            raise InputUnavailable(f"{role.upper()}_METADATA")
        start = _utc(metadata.get("coverage_start"))
        end = _utc(metadata.get("coverage_end"))
        _utc(metadata.get("retrieved_at"))
        if end < start or end.date() >= LOCKBOX_START:
            raise InputUnavailable("LOCKBOX_OR_COVERAGE")
        coverage[role] = (start, end)
    calendar = parse_calendar_jsonl(payloads["session_calendar"])
    calendar_start, calendar_end = coverage["session_calendar"]
    if (
        calendar[0].session_date != calendar_start.astimezone(IST).date()
        or calendar[-1].session_date != calendar_end.astimezone(IST).date()
    ):
        raise InputUnavailable("CALENDAR_COVERAGE_BOUNDARY")
    sessions_raw = tuple(row for row in calendar if row.state != "closed")
    if not sessions_raw:
        raise InputUnavailable("CALENDAR_NO_SESSIONS")
    if any(row.source_index is None for row in sessions_raw):
        raise InputUnavailable("CALENDAR_SOURCE_INDEX")
    source_indices = tuple(row.source_index for row in sessions_raw if row.source_index is not None)
    if any(b != a + 1 for a, b in pairwise(source_indices)):
        raise InputUnavailable("OPEN_SESSION_SOURCE_INDICES")
    daily_fields = {
        "schema_version",
        "record_id",
        "revision",
        "source_index",
        "symbol",
        "event_ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "tradable",
        "state",
        "reason",
        "adjustment_basis",
    }
    pit_fields = {
        "schema_version",
        "record_id",
        "revision",
        "source_index",
        "symbol",
        "event_ts",
        "available_ts",
        "eligible",
    }
    action_fields = {
        "schema_version",
        "record_id",
        "revision",
        "symbol",
        "effective_ts",
        "adjustment_basis",
    }
    m15_fields = {
        "schema_version",
        "record_id",
        "revision",
        "source_index",
        "symbol",
        "event_ts",
        "end_ts",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "adjustment_basis",
    }
    liquidity_fields = {
        "schema_version",
        "record_id",
        "revision",
        "source_index",
        "symbol",
        "event_ts",
        "available_ts",
        "quantity",
        "method",
    }
    daily = _typed_rows(payloads["daily_stock"], daily_fields, "DAILY_SCHEMA")
    pit = _typed_rows(payloads["pit_universe"], pit_fields, "PIT_SCHEMA")
    actions = _typed_rows(payloads["corporate_action"], action_fields, "ACTION_SCHEMA")
    m15 = _typed_rows(payloads["m15_stock"], m15_fields, "M15_SCHEMA")
    liquidity = _typed_rows(payloads["opening_liquidity"], liquidity_fields, "LIQUIDITY_SCHEMA")
    nifty = (
        parse_nifty_jsonl(payloads["nifty_observation"])
        if benchmark_mode is BenchmarkMode.EXACT_OBSERVED_SESSION_CLOSE
        else ()
    )
    nifty_artifact = artifacts["nifty_observation"]
    benchmark_identity = FixtureIdentity(
        "NIFTY 50",
        _text(nifty_artifact.metadata["source_revision"]),
        "PRICE_INDEX",
        _text(nifty_artifact.metadata["vendor"]),
        nifty_artifact.sha256,
    )
    benchmark_candles = (
        parse_benchmark_candle_jsonl(payloads["nifty_observation"], benchmark_identity)
        if benchmark_mode is BenchmarkMode.DESCRIPTIVE_CANDLE_PROXY
        else ()
    )
    row_sets = {
        "daily_stock": daily,
        "pit_universe": pit,
        "corporate_action": actions,
        "m15_stock": m15,
        "opening_liquidity": liquidity,
    }
    for role, role_rows in row_sets.items():
        revision = artifacts[role].metadata["source_revision"]
        identities: set[tuple[str, str]] = set()
        for row in role_rows:
            identity = (_text(row["record_id"]), _text(row["revision"]))
            if identity in identities or identity[1] != revision:
                raise InputUnavailable(f"{role.upper()}_REVISION")
            identities.add(identity)
        timestamp_field = {
            "daily_stock": "event_ts",
            "pit_universe": "event_ts",
            "corporate_action": "effective_ts",
            "m15_stock": "event_ts",
            "opening_liquidity": "event_ts",
        }[role]
        if any(
            not (coverage[role][0] <= _utc(row[timestamp_field]) <= coverage[role][1])
            for row in role_rows
        ):
            raise InputUnavailable(f"{role.upper()}_COVERAGE")
    if any(
        row.revision != artifacts["session_calendar"].metadata["source_revision"]
        for row in calendar
    ):
        raise InputUnavailable("SESSION_CALENDAR_REVISION")
    if benchmark_mode is BenchmarkMode.EXACT_OBSERVED_SESSION_CLOSE and any(
        row.revision != artifacts["nifty_observation"].metadata["source_revision"] for row in nifty
    ):
        raise InputUnavailable("NIFTY_OBSERVATION_REVISION")
    if benchmark_mode is BenchmarkMode.EXACT_OBSERVED_SESSION_CLOSE and any(
        not (coverage["nifty_observation"][0] <= row.event_ts <= coverage["nifty_observation"][1])
        for row in nifty
    ):
        raise InputUnavailable("NIFTY_OBSERVATION_COVERAGE")
    if benchmark_mode is BenchmarkMode.DESCRIPTIVE_CANDLE_PROXY and any(
        not (
            coverage["nifty_observation"][0]
            <= row.interval_start_ts
            < row.interval_end_ts
            <= coverage["nifty_observation"][1]
        )
        for row in benchmark_candles
    ):
        raise InputUnavailable("NIFTY_CANDLE_COVERAGE")
    if any(
        row.open_ts is not None
        and not (coverage["session_calendar"][0] <= row.open_ts <= coverage["session_calendar"][1])
        for row in calendar
    ):
        raise InputUnavailable("SESSION_CALENDAR_COVERAGE")
    basis_by_symbol: dict[str, str] = {}
    last_action_by_symbol: dict[str, datetime] = {}
    for row in actions:
        symbol, basis = _text(row["symbol"]), _text(row["adjustment_basis"])
        if symbol in basis_by_symbol and basis_by_symbol[symbol] != basis:
            raise InputUnavailable("ACTION_BASIS_CONFLICT")
        effective = _utc(row["effective_ts"])
        if effective <= last_action_by_symbol.get(symbol, datetime.min.replace(tzinfo=UTC)):
            raise InputUnavailable("ACTION_ORDER")
        last_action_by_symbol[symbol] = effective
        basis_by_symbol[symbol] = basis
    session_by_index = {
        row.source_index: row for row in sessions_raw if row.source_index is not None
    }
    for candle in benchmark_candles:
        candle_session = session_by_index.get(candle.session_index)
        if (
            candle_session is None
            or candle_session.open_ts is None
            or candle_session.close_ts is None
            or candle.interval_start_ts < candle_session.open_ts
            or candle.interval_end_ts > candle_session.close_ts
        ):
            raise InputUnavailable("NIFTY_CANDLE_SESSION")
    revision_by_symbol = {row["symbol"]: row["revision"] for row in actions}
    daily_map: dict[tuple[int, str], dict[str, Any]] = {}
    for row in daily:
        key = (row["source_index"], _text(row["symbol"]))
        if (
            type(key[0]) is not int
            or key in daily_map
            or key[0] not in source_indices
            or type(row["tradable"]) is not bool
        ):
            raise InputUnavailable("DAILY_IDENTITY")
        state, reason = row["state"], row["reason"]
        values = tuple(row[name] for name in ("open", "high", "low", "close", "volume"))
        if state == "OBSERVED":
            if reason != "" or any(type(value) is not str for value in values):
                raise InputUnavailable("DAILY_AVAILABILITY")
        elif state in ("INACTIVE_ABSENT", "DATA_GAP"):
            if type(reason) is not str or not reason or any(value is not None for value in values):
                raise InputUnavailable("DAILY_AVAILABILITY")
            if state == "INACTIVE_ABSENT" and row["tradable"]:
                raise InputUnavailable("DAILY_INACTIVE_TRADABLE")
        else:
            raise InputUnavailable("DAILY_AVAILABILITY")
        if _utc(row["event_ts"]) != session_by_index[key[0]].open_ts:
            raise InputUnavailable("DAILY_TIME")
        if row["adjustment_basis"] != basis_by_symbol.get(key[1]) or row[
            "revision"
        ] != revision_by_symbol.get(key[1]):
            raise InputUnavailable("DAILY_BASIS")
        daily_map[key] = row
    symbols = tuple(sorted({key[1] for key in daily_map}))
    if not symbols or set(basis_by_symbol) != set(symbols):
        raise InputUnavailable("DAILY_UNIVERSE")
    expected_grid = {(index, symbol) for index in source_indices for symbol in symbols}
    if set(daily_map) != expected_grid:
        raise InputUnavailable("DAILY_COVERAGE")
    if source_pair is not None:
        try:
            for index, symbol in expected_grid:
                session = session_by_index[index]
                assert session.open_ts is not None
                assert session.close_ts is not None
                mapping = source_pair.mapping_for(symbol, session.open_ts, session.close_ts)
                if mapping.daily_symbol != symbol or mapping.m15_symbol != symbol:
                    raise ValueError("canonical symbol mismatch")
        except (AssertionError, ValueError) as exc:
            raise InputUnavailable("PAIR_LINEAGE_MAPPING") from exc
    pit_map: dict[tuple[int, str], bool] = {}
    for row in pit:
        key = (row["source_index"], _text(row["symbol"]))
        event, available = _utc(row["event_ts"]), _utc(row["available_ts"])
        if (
            key in pit_map
            or key not in daily_map
            or available > event
            or type(row["eligible"]) is not bool
        ):
            raise InputUnavailable("PIT_IDENTITY")
        if event != session_by_index[key[0]].open_ts:
            raise InputUnavailable("PIT_TIME")
        if row["eligible"] != daily_map[key]["tradable"]:
            raise InputUnavailable("PIT_TRADABLE_CONFLICT")
        if daily_map[key]["state"] == "INACTIVE_ABSENT" and row["eligible"]:
            raise InputUnavailable("PIT_INACTIVE_CONFLICT")
        pit_map[key] = row["eligible"]
    if set(pit_map) != set(daily_map):
        raise InputUnavailable("PIT_COVERAGE")
    source = SourceDeclaration("real-data-bundle", "v1", "0" * 64)
    sessions = tuple(
        Session(row.source_index, row.open_ts, row.close_ts, source)
        for row in sessions_raw
        if row.source_index is not None and row.open_ts is not None and row.close_ts is not None
    )
    liquid_map: dict[tuple[int, str, datetime], OpeningLiquidity] = {}
    for row in liquidity:
        liquidity_key = (row["source_index"], _text(row["symbol"]), _utc(row["event_ts"]))
        available = _utc(row["available_ts"])
        if (
            liquidity_key in liquid_map
            or available > liquidity_key[2]
            or row["revision"] != artifacts["opening_liquidity"].metadata["source_revision"]
        ):
            raise InputUnavailable("LIQUIDITY_CAUSALITY")
        if row["method"] != "PRIOR_OBSERVED_QUANTITY_V1" or available >= liquidity_key[2]:
            raise InputUnavailable("LIQUIDITY_METHOD")
        liquid_map[liquidity_key] = OpeningLiquidity(
            _decimal(row["quantity"], zero=True), available, source
        )
    rows_by_symbol: dict[str, list[ReplayBar]] = {symbol: [] for symbol in symbols}
    for row in m15:
        index, symbol = row["source_index"], _text(row["symbol"])
        event, end = _utc(row["event_ts"]), _utc(row["end_ts"])
        bar_key = (index, symbol, event)
        if type(index) is not int or symbol not in rows_by_symbol or bar_key not in liquid_map:
            raise InputUnavailable("M15_IDENTITY")
        if daily_map[(index, symbol)]["state"] == "INACTIVE_ABSENT":
            raise InputUnavailable("M15_INACTIVE_CONFLICT")
        m15_session = session_by_index.get(index)
        if (
            m15_session is None
            or m15_session.open_ts is None
            or m15_session.close_ts is None
            or event < m15_session.open_ts
            or end <= event
            or end > m15_session.close_ts
        ):
            raise InputUnavailable("M15_SESSION_TIME")
        if (
            row["adjustment_basis"] != basis_by_symbol[symbol]
            or row["revision"] != revision_by_symbol[symbol]
        ):
            raise InputUnavailable("M15_BASIS")
        price_values = tuple(
            _decimal(row[name], zero=name == "volume")
            for name in ("open", "high", "low", "close", "volume")
        )
        rows_by_symbol[symbol].append(
            ReplayBar(index, SimBar(event, *price_values), end, liquid_map[bar_key], source)
        )
    if len(liquid_map) != sum(len(rows) for rows in rows_by_symbol.values()):
        raise InputUnavailable("LIQUIDITY_COVERAGE")
    inactive = frozenset(
        (symbol, index)
        for (index, symbol), row in daily_map.items()
        if row["state"] == "INACTIVE_ABSENT"
    )
    refinements = tuple(Refinement(symbol, tuple(rows_by_symbol[symbol])) for symbol in symbols)
    decision_availability = (
        tuple(
            DecisionAvailability(
                session.index,
                None,
                None if offset + 1 == len(sessions) else sessions[offset + 1].open_ts,
                AvailabilityBasis.MODELED_NEXT_SESSION_OPEN,
            )
            for offset, session in enumerate(sessions)
        )
        if benchmark_mode is BenchmarkMode.DESCRIPTIVE_CANDLE_PROXY
        else ()
    )
    digest = timed_fixture_digest(
        sessions,
        refinements,
        inactive,
        None if source_pair is None else source_pair.document_sha256,
        decision_availability=decision_availability,
        availability_model=availability_model,
    )
    bound = replace(source, sha256=digest)
    sessions = tuple(replace(row, source=bound) for row in sessions)
    refinements = tuple(
        Refinement(
            item.symbol,
            tuple(
                replace(
                    row,
                    source=bound,
                    opening=replace(row.opening, source=bound) if row.opening is not None else None,
                )
                for row in item.bars
            ),
        )
        for item in refinements
    )
    axis = np.array([np.datetime64(row.open_ts.replace(tzinfo=None), "ns") for row in sessions])
    bar_columns: dict[str, Bars] = {}
    tradable: dict[str, np.ndarray[Any, np.dtype[np.bool_]]] = {}
    for symbol in symbols:
        daily_rows = [daily_map[(index, symbol)] for index in source_indices]
        columns = {
            name: np.array(
                [
                    np.nan
                    if row["state"] != "OBSERVED"
                    else float(_decimal(row[name], zero=name == "volume"))
                    for row in daily_rows
                ]
            )
            for name in ("open", "high", "low", "close", "volume")
        }
        bar_columns[symbol] = Bars(axis, **columns)
        tradable[symbol] = np.array(
            [pit_map[(index, symbol)] for index in source_indices], dtype=np.bool_
        )
    benchmark = None
    if benchmark_mode is BenchmarkMode.EXACT_OBSERVED_SESSION_CLOSE:
        benchmark_rows: list[tuple[float, float]] = []
        nifty_by_event: dict[datetime, list[NiftyObservation]] = {}
        for observation in nifty:
            nifty_by_event.setdefault(observation.event_ts, []).append(observation)
        for fixture_session in sessions:
            if not (
                coverage["nifty_observation"][0]
                <= fixture_session.close_ts
                <= coverage["nifty_observation"][1]
            ):
                benchmark_rows.append((np.nan, np.nan))
                continue
            opens = tuple(
                row
                for row in nifty_by_event.get(fixture_session.open_ts, ())
                if row.observed and row.available_ts <= fixture_session.open_ts
            )
            closes = tuple(
                row
                for row in nifty_by_event.get(fixture_session.close_ts, ())
                if row.observed and row.available_ts <= fixture_session.close_ts
            )
            if len(opens) > 1 or len(closes) != 1:
                raise InputUnavailable("NIFTY_DAILY_PROJECTION_UNAVAILABLE")
            benchmark_rows.append(
                (float(opens[0].price) if opens else np.nan, float(closes[0].price))
            )
        benchmark_values = np.array(benchmark_rows)
        benchmark = Bars(
            axis,
            benchmark_values[:, 0],
            np.full(len(axis), np.nan),
            np.full(len(axis), np.nan),
            benchmark_values[:, 1],
            np.full(len(axis), np.nan),
        )
    panel = Panel.build(bar_columns, tradable, benchmark=benchmark)
    bound_pair = (
        None
        if source_pair is None
        else _bind_source_pair(
            source_pair,
            {role: artifact.sha256 for role, artifact in artifacts.items()},
            {role: artifact.metadata for role, artifact in artifacts.items()},
            panel,
            source_indices,
        )
    )
    return AssembledTimedInputs(
        panel,
        TimedFixture(
            sessions,
            refinements,
            bound,
            inactive,
            bound_pair,
            decision_availability,
            availability_model,
        ),
        source_indices,
        nifty,
        False,
        SourceDeclaration(
            _text(artifacts["nifty_observation"].metadata["vendor"]),
            _text(artifacts["nifty_observation"].metadata["source_revision"]),
            artifacts["nifty_observation"].sha256,
        ),
        benchmark_mode,
        benchmark_candles,
        benchmark_identity,
    )


def parse_calendar_jsonl(raw: bytes) -> tuple[CalendarRecord, ...]:
    wanted = {
        "schema_version",
        "record_id",
        "revision",
        "source_index",
        "session_date",
        "state",
        "open_ts",
        "close_ts",
    }
    answer: list[CalendarRecord] = []
    previous = -1
    previous_date: date | None = None
    ids: set[str] = set()
    for row in _records(raw):
        if (
            set(row) != wanted
            or type(row["schema_version"]) is not int
            or row["schema_version"] != 1
        ):
            raise InputUnavailable("CALENDAR_SCHEMA")
        record_id = _text(row["record_id"])
        if record_id in ids:
            raise InputUnavailable("CALENDAR_DUPLICATE")
        ids.add(record_id)
        index = row["source_index"]
        try:
            session_date = date.fromisoformat(_text(row["session_date"]))
        except ValueError as exc:
            raise InputUnavailable("CALENDAR_DATE") from exc
        if previous_date is not None and session_date <= previous_date:
            raise InputUnavailable("CALENDAR_DATE_ORDER")
        if previous_date is not None and session_date != previous_date + timedelta(days=1):
            raise InputUnavailable("CALENDAR_DATE_GAP")
        previous_date = session_date
        state = row["state"]
        if state not in ("regular", "special", "closed"):
            raise InputUnavailable("CALENDAR_STATE")
        if state == "closed":
            if index is not None:
                raise InputUnavailable("CALENDAR_SOURCE_INDEX")
        elif type(index) is not int or (index != previous + 1 and previous >= 0):
            raise InputUnavailable("CALENDAR_SOURCE_INDEX")
        else:
            previous = index
        opened = None if row["open_ts"] is None else _utc(row["open_ts"])
        closed = None if row["close_ts"] is None else _utc(row["close_ts"])
        if (state == "closed" and (opened is not None or closed is not None)) or (
            state != "closed" and (opened is None or closed is None)
        ):
            raise InputUnavailable("CALENDAR_HOURS")
        if opened is not None and (closed is None or closed <= opened):
            raise InputUnavailable("CALENDAR_HOURS")
        if opened is not None and (
            opened.astimezone(IST).date() != session_date
            or opened.date() != session_date
            or closed is None
            or closed.astimezone(IST).date() != session_date
        ):
            raise InputUnavailable("CALENDAR_DATE_TIME")
        answer.append(
            CalendarRecord(
                record_id, _text(row["revision"]), index, session_date, state, opened, closed
            )
        )
    return tuple(answer)


def parse_nifty_jsonl(raw: bytes) -> tuple[NiftyObservation, ...]:
    wanted = {
        "schema_version",
        "record_id",
        "revision",
        "instrument",
        "venue",
        "price_basis",
        "event_ts",
        "available_ts",
        "observed",
        "price_numerator",
        "price_denominator",
    }
    answer: list[NiftyObservation] = []
    identities: set[tuple[str, str]] = set()
    for row in _records(raw):
        if (
            set(row) != wanted
            or type(row["schema_version"]) is not int
            or row["schema_version"] != 1
        ):
            raise InputUnavailable("NIFTY_SCHEMA")
        if (row["instrument"], row["venue"], row["price_basis"]) != (
            "NIFTY 50",
            "NSE",
            "PRICE_INDEX",
        ):
            raise InputUnavailable("NIFTY_IDENTITY")
        event, available = _utc(row["event_ts"]), _utc(row["available_ts"])
        if available < event or type(row["observed"]) is not bool:
            raise InputUnavailable("NIFTY_CAUSALITY")
        numerator, denominator = row["price_numerator"], row["price_denominator"]
        if (
            type(numerator) is not int
            or type(denominator) is not int
            or denominator <= 0
            or numerator <= 0
        ):
            raise InputUnavailable("NIFTY_PRICE")
        key = (_text(row["record_id"]), _text(row["revision"]))
        if key in identities:
            raise InputUnavailable("NIFTY_DUPLICATE")
        identities.add(key)
        answer.append(
            NiftyObservation(
                key[0], key[1], event, available, row["observed"], Fraction(numerator, denominator)
            )
        )
    return tuple(answer)


def parse_benchmark_candle_jsonl(
    raw: bytes, expected: FixtureIdentity
) -> tuple[BenchmarkCandle, ...]:
    wanted = {
        "schema_version",
        "record_id",
        "revision",
        "source_index",
        "instrument",
        "venue",
        "price_basis",
        "interval_start_ts",
        "interval_end_ts",
        "open_numerator",
        "open_denominator",
        "high_numerator",
        "high_denominator",
        "low_numerator",
        "low_denominator",
        "close_numerator",
        "close_denominator",
        "raw_available_ts",
        "modeled_available_ts",
        "availability_basis",
        "quarantined",
    }
    answer: list[BenchmarkCandle] = []
    for row in _records(raw):
        if (
            set(row) != wanted
            or type(row["schema_version"]) is not int
            or row["schema_version"] != 2
        ):
            raise InputUnavailable("NIFTY_CANDLE_SCHEMA")
        if (row["instrument"], row["venue"], row["price_basis"]) != (
            "NIFTY 50",
            "NSE",
            "PRICE_INDEX",
        ):
            raise InputUnavailable("NIFTY_CANDLE_IDENTITY")
        prices: list[Fraction] = []
        for name in ("open", "high", "low", "close"):
            numerator, denominator = row[f"{name}_numerator"], row[f"{name}_denominator"]
            if (
                type(numerator) is not int
                or type(denominator) is not int
                or numerator <= 0
                or denominator <= 0
            ):
                raise InputUnavailable("NIFTY_CANDLE_PRICE")
            prices.append(Fraction(numerator, denominator))
        try:
            opened, high, low, closed = prices
            answer.append(
                BenchmarkCandle(
                    expected,
                    _text(row["record_id"]),
                    _text(row["revision"]),
                    row["source_index"],
                    _utc(row["interval_start_ts"]),
                    _utc(row["interval_end_ts"]),
                    opened,
                    high,
                    low,
                    closed,
                    None if row["raw_available_ts"] is None else _utc(row["raw_available_ts"]),
                    _utc(row["modeled_available_ts"]),
                    AvailabilityBasis(row["availability_basis"]),
                    row["quarantined"],
                )
            )
        except (TypeError, ValueError) as exc:
            raise InputUnavailable("NIFTY_CANDLE_VALUE") from exc
    if len({row.record_id for row in answer}) != len(answer):
        raise InputUnavailable("NIFTY_CANDLE_DUPLICATE")
    return tuple(answer)
