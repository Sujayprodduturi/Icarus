"""Atomic lifetime trial accounting for portfolio and signal evaluations.

The database rows are reservations, not just successful results: once a real-data evaluation is
authorized, its trial is counted even if the process fails.  Synthetic callers do not use this
module.  PostgreSQL is authoritative only after the legacy JSON ledger has been explicitly
validated, imported and activated.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
from pathlib import Path
from typing import Literal, TypeAlias, cast
from uuid import UUID, uuid5

from sqlalchemy import Engine, func, insert, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from icarus.state.models import (
    TrialBatch,
    TrialEvaluation,
    TrialLedgerActivation,
    TrialResult,
)
from icarus.state.models import (
    TrialBatchTerminal as TrialBatchTerminalRow,
)

JsonValue: TypeAlias = (  # noqa: UP040 -- mypy lacks stable PEP 695 support
    bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"] | None
)

_HASH_RE = re.compile(r"[0-9a-f]{64}")
_FAILURE_RE = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
_MAX_DECIMAL_DIGITS = 128
_MAX_DECIMAL_EXPONENT = 128
_LEGACY_REQUIRED = {
    "at",
    "strategy",
    "version",
    "origin",
    "primitives",
    "oos_sharpe",
    "oos_trades",
    "folds",
}
_LEGACY_OPTIONAL = {"oos_sharpe_after_tax"}


class TrialOrigin(StrEnum):
    OPERATOR = "operator"
    INVENTOR = "inventor"


class TrialKind(StrEnum):
    PORTFOLIO = "portfolio"
    SIGNAL_FULL = "signal_full"
    SIGNAL_FOLD = "signal_fold"


class TrialTerminalState(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class TrialReservationAuthorization(StrEnum):
    NEW_EVALUATION = "new_evaluation"
    RECOVERY_ONLY = "recovery_only"


class TrialLedgerError(RuntimeError):
    """Base class for fail-closed trial-ledger errors."""


class TrialLedgerUnavailable(TrialLedgerError):
    pass


class TrialLedgerCorruption(TrialLedgerError):
    pass


class TrialLedgerNotActivated(TrialLedgerError):
    pass


class TrialIdentityConflict(TrialLedgerError):
    pass


def _whole(value: object, name: str, *, minimum: int = 0) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < minimum:
        raise ValueError(f"{name} must be a whole integer >= {minimum}")
    return value


def _utc(value: datetime, name: str) -> None:
    if value.tzinfo is None or value.utcoffset() != UTC.utcoffset(value):
        raise ValueError(f"{name} must be UTC timezone-aware")


def _hash(value: str | None, name: str, *, required: bool) -> None:
    if value is None:
        if required:
            raise ValueError(f"{name} is required for native trial evidence")
        return
    if _HASH_RE.fullmatch(value) is None:
        raise ValueError(f"{name} must be 64 lowercase hexadecimal characters")


def _decimal(value: Decimal | None, name: str) -> None:
    if value is None:
        return
    if not value.is_finite():
        raise ValueError(f"{name} must be finite")
    sign, digits, exponent = value.as_tuple()
    del sign
    if not isinstance(exponent, int):
        raise ValueError(f"{name} must be finite")
    if len(digits) > _MAX_DECIMAL_DIGITS or abs(exponent) > _MAX_DECIMAL_EXPONENT:
        raise ValueError(f"{name} exceeds the exact storage precision boundary")


def _validate_json(value: JsonValue, path: str = "payload") -> None:
    if value is None or isinstance(value, (bool, str)):
        return
    if isinstance(value, int):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError(f"{path} contains a non-finite number")
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json(item, f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError(f"{path} keys must be strings")
            _validate_json(item, f"{path}.{key}")
        return
    raise ValueError(f"{path} contains unsupported JSON data")


@dataclass(frozen=True, slots=True)
class EvaluationReservation:
    ordinal: int
    kind: TrialKind
    fold_index: int | None
    start_index: int | None
    end_index_exclusive: int | None
    start_ts: datetime | None
    end_ts: datetime | None
    reset_identity: str

    def __post_init__(self) -> None:
        _whole(self.ordinal, "ordinal")
        if self.fold_index is not None:
            _whole(self.fold_index, "fold_index")
        fields = (self.start_index, self.end_index_exclusive, self.start_ts, self.end_ts)
        if any(value is None for value in fields) and not all(value is None for value in fields):
            raise ValueError("evaluation span indices and timestamps must be present together")
        if self.start_index is not None:
            start = _whole(self.start_index, "start_index")
            end = _whole(self.end_index_exclusive, "end_index_exclusive", minimum=1)
            if end <= start:
                raise ValueError("evaluation span must be non-empty")
            assert self.start_ts is not None and self.end_ts is not None
            _utc(self.start_ts, "start_ts")
            _utc(self.end_ts, "end_ts")
            if self.end_ts < self.start_ts:
                raise ValueError("evaluation timestamps must be ordered")
        if not self.reset_identity or len(self.reset_identity) > 64:
            raise ValueError("reset_identity must be non-empty and at most 64 characters")


@dataclass(frozen=True, slots=True)
class TrialBatchReservation:
    run_group_id: UUID
    origin: TrialOrigin
    strategy_name: str
    strategy_version: int
    strategy_sha256: str | None
    panel_sha256: str | None
    config_sha256: str | None
    primitives: tuple[str, ...]
    evaluations: tuple[EvaluationReservation, ...]
    source: Literal["native", "legacy_json_v1"] = "native"

    def __post_init__(self) -> None:
        if not self.strategy_name or len(self.strategy_name) > 128:
            raise ValueError("strategy_name must be non-empty and at most 128 characters")
        _whole(self.strategy_version, "strategy_version", minimum=1)
        required = self.source == "native"
        _hash(self.strategy_sha256, "strategy_sha256", required=required)
        _hash(self.panel_sha256, "panel_sha256", required=required)
        _hash(self.config_sha256, "config_sha256", required=required)
        if tuple(sorted(set(self.primitives))) != self.primitives:
            raise ValueError("primitives must be sorted and unique")
        if not self.evaluations:
            raise ValueError("a trial batch must reserve at least one evaluation")
        if tuple(item.ordinal for item in self.evaluations) != tuple(range(len(self.evaluations))):
            raise ValueError("evaluation ordinals must be contiguous from zero")
        if required and any(item.start_index is None for item in self.evaluations):
            raise ValueError("native trial evaluations require exact span geometry")
        self._validate_geometry()

    def _validate_geometry(self) -> None:
        kinds = {item.kind for item in self.evaluations}
        if kinds == {TrialKind.PORTFOLIO}:
            if len(self.evaluations) != 1:
                raise ValueError("a portfolio batch contains exactly one evaluation")
            item = self.evaluations[0]
            if item.fold_index is not None or item.reset_identity != "walk_forward_portfolio_v1":
                raise ValueError("portfolio evaluation has invalid fold/reset identity")
            return
        if TrialKind.PORTFOLIO in kinds or self.evaluations[0].kind is not TrialKind.SIGNAL_FULL:
            raise ValueError("signal batch must start with exactly one full-span evaluation")
        full = self.evaluations[0]
        if full.fold_index is not None or full.reset_identity != "continuous_full_development_v1":
            raise ValueError("signal full-span evaluation has invalid fold/reset identity")
        folds = self.evaluations[1:]
        if not folds:
            raise ValueError("signal batch must include at least one fold")
        previous_end: int | None = None
        previous_end_ts: datetime | None = None
        assert full.start_index is not None and full.end_index_exclusive is not None
        assert full.start_ts is not None and full.end_ts is not None
        for item in folds:
            expected_fold = item.ordinal - 1
            if item.kind is not TrialKind.SIGNAL_FOLD or item.fold_index != expected_fold:
                raise ValueError("signal fold_index must equal ordinal minus one")
            if item.reset_identity != "fresh_signal_simulator_per_fold_v1":
                raise ValueError("signal fold has invalid reset identity")
            assert item.start_index is not None and item.end_index_exclusive is not None
            assert item.start_ts is not None and item.end_ts is not None
            if not (
                full.start_index
                <= item.start_index
                < item.end_index_exclusive
                <= full.end_index_exclusive
                and full.start_ts <= item.start_ts <= item.end_ts <= full.end_ts
            ):
                raise ValueError("signal fold is outside the full-span geometry")
            if previous_end is not None and item.start_index < previous_end:
                raise ValueError("signal folds must be ordered and non-overlapping")
            if previous_end_ts is not None and item.start_ts <= previous_end_ts:
                raise ValueError("signal folds must be temporally ordered and non-overlapping")
            previous_end = item.end_index_exclusive
            previous_end_ts = item.end_ts


@dataclass(frozen=True, slots=True)
class TrialEvaluationResult:
    ordinal: int
    kind: TrialKind
    oos_sharpe: Decimal | None
    oos_sharpe_after_tax: Decimal | None
    observation_count: int
    payload: dict[str, JsonValue]

    def __post_init__(self) -> None:
        _whole(self.ordinal, "ordinal")
        _whole(self.observation_count, "observation_count")
        _decimal(self.oos_sharpe, "oos_sharpe")
        _decimal(self.oos_sharpe_after_tax, "oos_sharpe_after_tax")
        _validate_json(self.payload)
        if self.kind is not TrialKind.PORTFOLIO and (
            self.oos_sharpe is not None or self.oos_sharpe_after_tax is not None
        ):
            raise ValueError("signal trial results cannot contain Sharpe values")


@dataclass(frozen=True, slots=True)
class TrialBatchReceipt:
    run_group_id: UUID
    reservation_sha256: str
    evaluation_ids: tuple[UUID, ...]
    lifetime_trial_count: int
    newly_created: bool
    authorization: TrialReservationAuthorization


@dataclass(frozen=True, slots=True)
class TrialBatchTerminal:
    run_group_id: UUID
    state: TrialTerminalState
    results_sha256: str | None
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class LegacyPortfolioTrial:
    ordinal: int
    at: datetime
    strategy_name: str
    strategy_version: int
    origin: TrialOrigin
    primitives: tuple[str, ...]
    oos_sharpe: Decimal | None
    oos_sharpe_after_tax: Decimal | None
    after_tax_field_present: bool
    oos_trades: int
    folds: int
    original_payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class LegacyPortfolioLedger:
    schema: Literal[1]
    sha256: str
    trials: tuple[LegacyPortfolioTrial, ...]


@dataclass(frozen=True, slots=True)
class ActivationReceipt:
    legacy_entry_count: int
    legacy_sha256: str
    lifetime_trial_count: int


@dataclass(frozen=True, slots=True)
class _LockedBatch:
    expected_evaluations: int


def _canonical_value(value: object) -> JsonValue:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, tuple):
        return [_canonical_value(item) for item in value]
    if isinstance(value, list):
        return [_canonical_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _canonical_value(item) for key, item in value.items()}
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    raise TypeError(f"unsupported canonical value {type(value).__name__}")


def _canonical_bytes(value: object) -> bytes:
    converted = _canonical_value(value)
    _validate_json(converted)
    return json.dumps(converted, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()


def canonical_reservation_sha256(batch: TrialBatchReservation) -> str:
    """Hash the validated reservation without relying on caller mapping order."""
    batch._validate_geometry()
    return hashlib.sha256(_canonical_bytes(asdict(batch))).hexdigest()


def _legacy_decimal(value: object, name: str) -> Decimal | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"legacy {name} must be a number or null")
    result = Decimal(str(value))
    _decimal(result, f"legacy {name}")
    return result


def read_legacy_portfolio_ledger(path: Path) -> LegacyPortfolioLedger:
    """Validate schema-1 portfolio history without changing or normalizing its source file."""
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ValueError("legacy trial ledger is missing or unreadable") from exc
    try:
        payload: object = json.loads(
            raw.decode("utf-8"),
            parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)),
        )
    except (UnicodeError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError("legacy trial ledger is malformed") from exc
    if (
        not isinstance(payload, dict)
        or type(payload.get("schema")) is not int
        or payload.get("schema") != 1
    ):
        raise ValueError("legacy trial ledger schema must be 1")
    rows = payload.get("trials")
    if not isinstance(rows, list):
        raise ValueError("legacy trial ledger trials must be a list")
    trials: list[LegacyPortfolioTrial] = []
    for ordinal, value in enumerate(rows):
        if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
            raise ValueError(f"legacy trial {ordinal} must be an object")
        keys = set(value)
        if not _LEGACY_REQUIRED.issubset(keys) or not keys.issubset(
            _LEGACY_REQUIRED | _LEGACY_OPTIONAL
        ):
            raise ValueError(f"legacy trial {ordinal} has missing or unexpected keys")
        at_raw = value["at"]
        if not isinstance(at_raw, str):
            raise ValueError(f"legacy trial {ordinal} at must be a string")
        try:
            at = datetime.fromisoformat(at_raw)
        except ValueError as exc:
            raise ValueError(f"legacy trial {ordinal} at is invalid") from exc
        _utc(at, f"legacy trial {ordinal} at")
        strategy = value["strategy"]
        primitives = value["primitives"]
        if not isinstance(strategy, str) or not strategy:
            raise ValueError(f"legacy trial {ordinal} strategy is invalid")
        if not isinstance(primitives, list) or not all(
            isinstance(item, str) for item in primitives
        ):
            raise ValueError(f"legacy trial {ordinal} primitives are invalid")
        typed_payload = cast(dict[str, JsonValue], dict(value))
        _validate_json(typed_payload)
        trials.append(
            LegacyPortfolioTrial(
                ordinal=ordinal,
                at=at.astimezone(UTC),
                strategy_name=strategy,
                strategy_version=_whole(value["version"], "legacy version", minimum=1),
                origin=TrialOrigin(value["origin"]),
                primitives=tuple(primitives),
                oos_sharpe=_legacy_decimal(value["oos_sharpe"], "oos_sharpe"),
                oos_sharpe_after_tax=_legacy_decimal(
                    value.get("oos_sharpe_after_tax"), "oos_sharpe_after_tax"
                ),
                after_tax_field_present="oos_sharpe_after_tax" in value,
                oos_trades=_whole(value["oos_trades"], "legacy oos_trades"),
                folds=_whole(value["folds"], "legacy folds"),
                original_payload=typed_payload,
            )
        )
    return LegacyPortfolioLedger(
        schema=1,
        sha256=hashlib.sha256(raw).hexdigest(),
        trials=tuple(trials),
    )


def evaluation_id(batch: TrialBatchReservation, item: EvaluationReservation) -> UUID:
    return uuid5(batch.run_group_id, _canonical_bytes(asdict(item)).decode("ascii"))


def validate_failure_code(value: str) -> None:
    if _FAILURE_RE.fullmatch(value) is None:
        raise ValueError("failure_code must be an uppercase machine code")


def _result_sha256(result: TrialEvaluationResult) -> str:
    return hashlib.sha256(_canonical_bytes(asdict(result))).hexdigest()


def _results_sha256(results: tuple[TrialEvaluationResult, ...]) -> str:
    return hashlib.sha256(_canonical_bytes([asdict(item) for item in results])).hexdigest()


class PostgresTrialLedger:
    """Synchronous transaction boundary for the Phase-1 offline runners."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def reserve(self, batch: TrialBatchReservation) -> TrialBatchReceipt:
        if batch.source != "native":
            raise ValueError("public trial reservation accepts native evidence only")
        digest = canonical_reservation_sha256(batch)
        ids = tuple(evaluation_id(batch, item) for item in batch.evaluations)
        try:
            with self._engine.begin() as conn:
                if (
                    conn.execute(
                        select(TrialLedgerActivation.id).where(TrialLedgerActivation.id == 1)
                    ).scalar_one_or_none()
                    is None
                ):
                    raise TrialLedgerNotActivated("trial ledger is not activated")
                inserted = conn.execute(
                    pg_insert(TrialBatch)
                    .values(
                        run_group_id=batch.run_group_id,
                        reservation_sha256=digest,
                        origin=batch.origin.value,
                        source=batch.source,
                        strategy_name=batch.strategy_name,
                        strategy_version=batch.strategy_version,
                        strategy_sha256=batch.strategy_sha256,
                        panel_sha256=batch.panel_sha256,
                        config_sha256=batch.config_sha256,
                        primitives=list(batch.primitives),
                        expected_evaluations=len(batch.evaluations),
                    )
                    .on_conflict_do_nothing(index_elements=[TrialBatch.run_group_id])
                    .returning(TrialBatch.run_group_id)
                ).scalar_one_or_none()
                newly_created = inserted is not None
                row = conn.execute(
                    select(
                        TrialBatch.reservation_sha256,
                        TrialBatch.expected_evaluations,
                    )
                    .where(TrialBatch.run_group_id == batch.run_group_id)
                    .with_for_update()
                ).one_or_none()
                if row is None:
                    raise TrialLedgerCorruption("reserved trial batch disappeared")
                if row.reservation_sha256 != digest or row.expected_evaluations != len(ids):
                    raise TrialIdentityConflict("run_group_id already binds different evidence")
                if newly_created:
                    conn.execute(
                        insert(TrialEvaluation),
                        [
                            {
                                "evaluation_id": identifier,
                                "run_group_id": batch.run_group_id,
                                "ordinal": item.ordinal,
                                "kind": item.kind.value,
                                "fold_index": item.fold_index,
                                "start_index": item.start_index,
                                "end_index_exclusive": item.end_index_exclusive,
                                "start_ts": item.start_ts,
                                "end_ts": item.end_ts,
                                "reset_identity": item.reset_identity,
                            }
                            for identifier, item in zip(ids, batch.evaluations, strict=True)
                        ],
                    )
                persisted = tuple(
                    conn.execute(
                        select(TrialEvaluation.evaluation_id)
                        .where(TrialEvaluation.run_group_id == batch.run_group_id)
                        .order_by(TrialEvaluation.ordinal)
                    ).scalars()
                )
                if persisted != ids:
                    raise TrialLedgerCorruption("persisted trial evaluation identities differ")
                count = conn.execute(select(func.count()).select_from(TrialEvaluation)).scalar_one()
            return TrialBatchReceipt(
                run_group_id=batch.run_group_id,
                reservation_sha256=digest,
                evaluation_ids=ids,
                lifetime_trial_count=count,
                newly_created=newly_created,
                authorization=(
                    TrialReservationAuthorization.NEW_EVALUATION
                    if newly_created
                    else TrialReservationAuthorization.RECOVERY_ONLY
                ),
            )
        except TrialLedgerError:
            raise
        except SQLAlchemyError:
            raise TrialLedgerUnavailable("trial ledger reservation failed") from None

    def complete(
        self,
        receipt: TrialBatchReceipt,
        results: tuple[TrialEvaluationResult, ...],
    ) -> TrialBatchTerminal:
        digest = _results_sha256(results)
        try:
            with self._engine.begin() as conn:
                row = self._locked_batch(conn, receipt)
                terminal = conn.execute(
                    select(
                        TrialBatchTerminalRow.state,
                        TrialBatchTerminalRow.results_sha256,
                        TrialBatchTerminalRow.failure_code,
                    ).where(TrialBatchTerminalRow.run_group_id == receipt.run_group_id)
                ).one_or_none()
                if terminal is not None:
                    if terminal.state != "completed" or terminal.results_sha256 != digest:
                        raise TrialIdentityConflict("trial batch already has a different terminal")
                    self._verify_results(conn, receipt, results)
                    return TrialBatchTerminal(
                        receipt.run_group_id,
                        TrialTerminalState.COMPLETED,
                        terminal.results_sha256,
                        None,
                    )
                if len(results) != row.expected_evaluations:
                    raise TrialIdentityConflict("result batch does not match reserved cardinality")
                if tuple(result.ordinal for result in results) != tuple(range(len(results))):
                    raise TrialIdentityConflict("result ordinals do not match the reservation")
                kinds = tuple(
                    conn.execute(
                        select(TrialEvaluation.kind)
                        .where(TrialEvaluation.run_group_id == receipt.run_group_id)
                        .order_by(TrialEvaluation.ordinal)
                    ).scalars()
                )
                if kinds != tuple(result.kind.value for result in results):
                    raise TrialIdentityConflict("result kinds do not match the reservation")
                conn.execute(
                    insert(TrialResult),
                    [
                        {
                            "evaluation_id": identifier,
                            "result_sha256": _result_sha256(result),
                            "oos_sharpe": result.oos_sharpe,
                            "oos_sharpe_after_tax": result.oos_sharpe_after_tax,
                            "observation_count": result.observation_count,
                            "payload": result.payload,
                        }
                        for identifier, result in zip(receipt.evaluation_ids, results, strict=True)
                    ],
                )
                conn.execute(
                    insert(TrialBatchTerminalRow).values(
                        run_group_id=receipt.run_group_id,
                        state="completed",
                        results_sha256=digest,
                        failure_code=None,
                    )
                )
                self._verify_results(conn, receipt, results)
            return TrialBatchTerminal(
                receipt.run_group_id,
                TrialTerminalState.COMPLETED,
                digest,
                None,
            )
        except TrialLedgerError:
            raise
        except SQLAlchemyError:
            raise TrialLedgerUnavailable("trial ledger completion failed") from None

    def fail(
        self,
        receipt: TrialBatchReceipt,
        *,
        failure_code: str,
    ) -> TrialBatchTerminal:
        validate_failure_code(failure_code)
        try:
            with self._engine.begin() as conn:
                self._locked_batch(conn, receipt)
                terminal = conn.execute(
                    select(
                        TrialBatchTerminalRow.state,
                        TrialBatchTerminalRow.results_sha256,
                        TrialBatchTerminalRow.failure_code,
                    ).where(TrialBatchTerminalRow.run_group_id == receipt.run_group_id)
                ).one_or_none()
                if terminal is not None:
                    if terminal.state != "failed" or terminal.failure_code != failure_code:
                        raise TrialIdentityConflict("trial batch already has a different terminal")
                    return TrialBatchTerminal(
                        receipt.run_group_id,
                        TrialTerminalState.FAILED,
                        None,
                        failure_code,
                    )
                conn.execute(
                    insert(TrialBatchTerminalRow).values(
                        run_group_id=receipt.run_group_id,
                        state="failed",
                        results_sha256=None,
                        failure_code=failure_code,
                    )
                )
            return TrialBatchTerminal(
                receipt.run_group_id,
                TrialTerminalState.FAILED,
                None,
                failure_code,
            )
        except TrialLedgerError:
            raise
        except SQLAlchemyError:
            raise TrialLedgerUnavailable("trial ledger failure persistence failed") from None

    def lifetime_count(self) -> int:
        try:
            with self._engine.connect() as conn:
                if (
                    conn.execute(
                        select(TrialLedgerActivation.id).where(TrialLedgerActivation.id == 1)
                    ).scalar_one_or_none()
                    is None
                ):
                    raise TrialLedgerNotActivated("trial ledger is not activated")
                return conn.execute(select(func.count()).select_from(TrialEvaluation)).scalar_one()
        except TrialLedgerError:
            raise
        except SQLAlchemyError:
            raise TrialLedgerUnavailable("trial ledger count failed") from None

    def import_legacy_and_activate(self, legacy: LegacyPortfolioLedger) -> ActivationReceipt:
        try:
            with self._engine.begin() as conn:
                existing = conn.execute(
                    select(
                        TrialLedgerActivation.legacy_entry_count,
                        TrialLedgerActivation.legacy_sha256,
                    ).where(TrialLedgerActivation.id == 1)
                ).one_or_none()
                if existing is not None:
                    if (
                        existing.legacy_entry_count != len(legacy.trials)
                        or existing.legacy_sha256 != legacy.sha256
                    ):
                        raise TrialIdentityConflict(
                            "activated legacy ledger differs from supplied evidence"
                        )
                    count = conn.execute(
                        select(func.count()).select_from(TrialEvaluation)
                    ).scalar_one()
                    return ActivationReceipt(len(legacy.trials), legacy.sha256, count)
                conn.execute(
                    insert(TrialLedgerActivation).values(
                        id=1,
                        legacy_schema=legacy.schema,
                        legacy_entry_count=len(legacy.trials),
                        legacy_sha256=legacy.sha256,
                    )
                )
                for trial in legacy.trials:
                    group_id = uuid5(
                        UUID("09c85f1a-1db9-4a26-a1aa-6f966879b9f4"),
                        f"icarus:legacy-trial-ledger:v1:{trial.ordinal}",
                    )
                    batch = TrialBatchReservation(
                        run_group_id=group_id,
                        origin=trial.origin,
                        strategy_name=trial.strategy_name,
                        strategy_version=trial.strategy_version,
                        strategy_sha256=None,
                        panel_sha256=None,
                        config_sha256=None,
                        primitives=trial.primitives,
                        evaluations=(
                            EvaluationReservation(
                                ordinal=0,
                                kind=TrialKind.PORTFOLIO,
                                fold_index=None,
                                start_index=None,
                                end_index_exclusive=None,
                                start_ts=None,
                                end_ts=None,
                                reset_identity="walk_forward_portfolio_v1",
                            ),
                        ),
                        source="legacy_json_v1",
                    )
                    reservation_digest = canonical_reservation_sha256(batch)
                    identifier = evaluation_id(batch, batch.evaluations[0])
                    conn.execute(
                        insert(TrialBatch).values(
                            run_group_id=group_id,
                            reservation_sha256=reservation_digest,
                            origin=trial.origin.value,
                            source="legacy_json_v1",
                            strategy_name=trial.strategy_name,
                            strategy_version=trial.strategy_version,
                            strategy_sha256=None,
                            panel_sha256=None,
                            config_sha256=None,
                            primitives=list(trial.primitives),
                            expected_evaluations=1,
                            reserved_at=trial.at,
                        )
                    )
                    conn.execute(
                        insert(TrialEvaluation).values(
                            evaluation_id=identifier,
                            run_group_id=group_id,
                            ordinal=0,
                            kind="portfolio",
                            fold_index=None,
                            start_index=None,
                            end_index_exclusive=None,
                            start_ts=None,
                            end_ts=None,
                            reset_identity="walk_forward_portfolio_v1",
                        )
                    )
                    result = TrialEvaluationResult(
                        ordinal=0,
                        kind=TrialKind.PORTFOLIO,
                        oos_sharpe=trial.oos_sharpe,
                        oos_sharpe_after_tax=trial.oos_sharpe_after_tax,
                        observation_count=trial.oos_trades,
                        payload=trial.original_payload,
                    )
                    result_digest = _result_sha256(result)
                    conn.execute(
                        insert(TrialResult).values(
                            evaluation_id=identifier,
                            result_sha256=result_digest,
                            oos_sharpe=trial.oos_sharpe,
                            oos_sharpe_after_tax=trial.oos_sharpe_after_tax,
                            observation_count=trial.oos_trades,
                            payload=trial.original_payload,
                            recorded_at=trial.at,
                        )
                    )
                    conn.execute(
                        insert(TrialBatchTerminalRow).values(
                            run_group_id=group_id,
                            state="completed",
                            results_sha256=_results_sha256((result,)),
                            failure_code=None,
                            recorded_at=trial.at,
                        )
                    )
                count = conn.execute(select(func.count()).select_from(TrialEvaluation)).scalar_one()
            return ActivationReceipt(len(legacy.trials), legacy.sha256, count)
        except TrialLedgerError:
            raise
        except SQLAlchemyError:
            raise TrialLedgerUnavailable("legacy trial-ledger activation failed") from None

    @staticmethod
    def _locked_batch(conn: Connection, receipt: TrialBatchReceipt) -> _LockedBatch:
        row = conn.execute(
            select(TrialBatch.reservation_sha256, TrialBatch.expected_evaluations)
            .where(TrialBatch.run_group_id == receipt.run_group_id)
            .with_for_update()
        ).one_or_none()
        if row is None:
            raise TrialLedgerCorruption("trial batch receipt has no persisted reservation")
        if row.reservation_sha256 != receipt.reservation_sha256:
            raise TrialIdentityConflict("trial batch receipt digest differs")
        persisted_ids = tuple(
            conn.execute(
                select(TrialEvaluation.evaluation_id)
                .where(TrialEvaluation.run_group_id == receipt.run_group_id)
                .order_by(TrialEvaluation.ordinal)
            ).scalars()
        )
        if persisted_ids != receipt.evaluation_ids:
            raise TrialLedgerCorruption("trial batch receipt evaluation identities differ")
        return _LockedBatch(expected_evaluations=row.expected_evaluations)

    @staticmethod
    def _verify_results(
        conn: Connection,
        receipt: TrialBatchReceipt,
        results: tuple[TrialEvaluationResult, ...],
    ) -> None:
        stored = tuple(
            conn.execute(
                select(
                    TrialEvaluation.ordinal,
                    TrialEvaluation.kind,
                    TrialResult.result_sha256,
                    TrialResult.oos_sharpe,
                    TrialResult.oos_sharpe_after_tax,
                    TrialResult.observation_count,
                    TrialResult.payload,
                )
                .join(TrialResult, TrialResult.evaluation_id == TrialEvaluation.evaluation_id)
                .where(TrialEvaluation.run_group_id == receipt.run_group_id)
                .order_by(TrialEvaluation.ordinal)
            ).mappings()
        )
        expected = tuple(
            {
                "ordinal": result.ordinal,
                "kind": result.kind.value,
                "result_sha256": _result_sha256(result),
                "oos_sharpe": result.oos_sharpe,
                "oos_sharpe_after_tax": result.oos_sharpe_after_tax,
                "observation_count": result.observation_count,
                "payload": result.payload,
            }
            for result in results
        )
        if len(stored) != len(expected) or any(
            dict(row) != wanted for row, wanted in zip(stored, expected, strict=True)
        ):
            raise TrialLedgerCorruption("persisted trial result rows differ from the retry body")
