"""Run the guarded seven-card timed evaluator from externally approved local inputs."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import stat
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any
from uuid import NAMESPACE_URL, uuid5

import yaml

from icarus.engine.benchmark_match import MatchingPolicy, SelectionPolicy
from icarus.engine.data_readiness import BundlePreflight, preflight_bundle

if TYPE_CHECKING:
    from icarus.engine.timed_runner import ExecutionBinding, RunAuthorization


class TimedCliError(RuntimeError):
    pass


EVIDENCE_KEYS = frozenset(
    {
        "archive",
        "benchmark_identity",
        "calendar",
        "corporate_adjustments",
        "licence",
        "pit_delisted",
        "prior_only_liquidity",
        "raw_event_availability",
    }
)
EXTERNAL_EVIDENCE_KEYS = frozenset({"archive", "licence", "raw_event_availability"})
PRODUCTION_CARD_FILES = frozenset(
    {
        "baseline_buy_and_hold.yaml",
        "defensive_low_vol_252_q63.yaml",
        "donchian_55_20.yaml",
        "donlevey_sweep_reclaim.yaml",
        "uptrend_pullback_3.yaml",
        "xs_momentum_20.yaml",
        "xs_momentum_252_skip21.yaml",
    }
)


@dataclass(frozen=True, slots=True)
class QualificationCertificate:
    qualification_id: str
    reviewer: str
    approved_at: datetime
    policy_registered_at: datetime
    manifest_sha256: str
    approval_sha256: str
    policy_sha256: str
    matching_policy_sha256: str
    evidence_sha256: dict[str, str]
    invented: bool


def _strict_object(raw: bytes, code: str) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise ValueError("duplicate key")
            value[key] = item
        return value

    try:
        value = json.loads(
            raw,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError("nonfinite")),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise TimedCliError(code) from exc
    if type(value) is not dict:
        raise TimedCliError(code)
    return value


def _sha(value: object, code: str) -> str:
    if (
        type(value) is not str
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise TimedCliError(code)
    return value


def _text(value: object, code: str) -> str:
    if type(value) is not str or not value.strip():
        raise TimedCliError(code)
    return value


def _utc(value: object, code: str) -> datetime:
    if (
        type(value) is not str
        or re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z", value) is None
    ):
        raise TimedCliError(code)
    try:
        result = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise TimedCliError(code) from exc
    if result.tzinfo is not UTC:
        raise TimedCliError(code)
    return result


def parse_qualification_certificate(raw: bytes) -> QualificationCertificate:
    value = _strict_object(raw, "QUALIFICATION_JSON")
    fields = {
        "schema_version",
        "qualification_id",
        "reviewer",
        "approved_at",
        "policy_registered_at",
        "manifest_sha256",
        "approval_sha256",
        "policy_sha256",
        "matching_policy_sha256",
        "evidence_sha256",
        "invented",
    }
    if (
        set(value) != fields
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
        or type(value["invented"]) is not bool
        or type(value["evidence_sha256"]) is not dict
        or set(value["evidence_sha256"]) != EVIDENCE_KEYS
    ):
        raise TimedCliError("QUALIFICATION_SCHEMA")
    evidence = {
        key: _sha(item, "QUALIFICATION_EVIDENCE") for key, item in value["evidence_sha256"].items()
    }
    result = QualificationCertificate(
        _text(value["qualification_id"], "QUALIFICATION_ID"),
        _text(value["reviewer"], "QUALIFICATION_REVIEWER"),
        _utc(value["approved_at"], "QUALIFICATION_TIME"),
        _utc(value["policy_registered_at"], "QUALIFICATION_TIME"),
        _sha(value["manifest_sha256"], "QUALIFICATION_BINDING"),
        _sha(value["approval_sha256"], "QUALIFICATION_BINDING"),
        _sha(value["policy_sha256"], "QUALIFICATION_BINDING"),
        _sha(value["matching_policy_sha256"], "QUALIFICATION_BINDING"),
        evidence,
        value["invented"],
    )
    if result.invented:
        raise TimedCliError("INVENTED_QUALIFICATION")
    if result.policy_registered_at > result.approved_at:
        raise TimedCliError("QUALIFICATION_CHRONOLOGY")
    return result


def parse_matching_policy(raw: bytes) -> MatchingPolicy:
    value = _strict_object(raw, "MATCHING_POLICY_JSON")
    if set(value) != {
        "schema_version",
        "policy_id",
        "selection",
        "max_age_seconds",
        "registered_at",
        "source_binding",
    }:
        raise TimedCliError("MATCHING_POLICY_SCHEMA")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise TimedCliError("MATCHING_POLICY_SCHEMA")
    age = value["max_age_seconds"]
    if type(age) is not int or age < 0:
        raise TimedCliError("MATCHING_POLICY_AGE")
    _utc(value["registered_at"], "MATCHING_POLICY_TIME")
    _text(value["source_binding"], "MATCHING_POLICY_SOURCE")
    try:
        selection = SelectionPolicy(value["selection"])
        return MatchingPolicy(
            _text(value["policy_id"], "MATCHING_POLICY_ID"), selection, timedelta(seconds=age)
        )
    except (TypeError, ValueError) as exc:
        raise TimedCliError("MATCHING_POLICY_SCHEMA") from exc


def _validate_policy_registration(
    source_policy_raw: bytes,
    matching_policy_raw: bytes,
    certificate: QualificationCertificate,
    matching_policy: MatchingPolicy,
) -> None:
    source = _strict_object(source_policy_raw, "SOURCE_POLICY_JSON")
    registered = _strict_object(matching_policy_raw, "MATCHING_POLICY_JSON")
    if (
        source.get("matching_policy") != matching_policy.policy_id
        or source.get("matching_policy_sha256") != hashlib.sha256(matching_policy_raw).hexdigest()
        or registered.get("source_binding") != source.get("source_binding")
        or _utc(source.get("registered_at"), "SOURCE_POLICY_TIME")
        != certificate.policy_registered_at
        or _utc(registered.get("registered_at"), "MATCHING_POLICY_TIME")
        != certificate.policy_registered_at
    ):
        raise TimedCliError("MATCHING_POLICY_BINDING")


def _validate_qualification_evidence(
    preflight: BundlePreflight,
    certificate: QualificationCertificate,
    external: dict[str, Path],
    bundle_root: Path,
) -> None:
    artifact_hashes = {item.role: item.sha256 for item in preflight.artifacts}
    expected_bundle = {
        "benchmark_identity": artifact_hashes["nifty_observation"],
        "calendar": artifact_hashes["session_calendar"],
        "corporate_adjustments": artifact_hashes["corporate_action"],
        "pit_delisted": artifact_hashes["pit_universe"],
        "prior_only_liquidity": artifact_hashes["opening_liquidity"],
    }
    if any(certificate.evidence_sha256[key] != value for key, value in expected_bundle.items()):
        raise TimedCliError("QUALIFICATION_ARTIFACT_EVIDENCE")
    if set(external) != EXTERNAL_EVIDENCE_KEYS:
        raise TimedCliError("QUALIFICATION_EXTERNAL_EVIDENCE")
    for key, path in external.items():
        _assert_external_path(path, bundle_root)
        digest = hashlib.sha256(_stable(path, 5_000_000, "QUALIFICATION_EVIDENCE_FILE")).hexdigest()
        if certificate.evidence_sha256[key] != digest:
            raise TimedCliError("QUALIFICATION_EXTERNAL_EVIDENCE")


def _evidence_arguments(values: list[str]) -> dict[str, Path]:
    result: dict[str, Path] = {}
    for value in values:
        key, separator, raw_path = value.partition("=")
        if not separator or key in result or key not in EXTERNAL_EVIDENCE_KEYS or not raw_path:
            raise TimedCliError("QUALIFICATION_EXTERNAL_EVIDENCE")
        result[key] = Path(raw_path)
    if set(result) != EXTERNAL_EVIDENCE_KEYS:
        raise TimedCliError("QUALIFICATION_EXTERNAL_EVIDENCE")
    return result


def _stable(path: Path, limit: int, code: str) -> bytes:
    try:
        before = path.stat()
        if (
            path.is_symlink()
            or path.is_junction()
            or not stat.S_ISREG(before.st_mode)
            or before.st_size > limit
        ):
            raise TimedCliError(code)
        with path.open("rb") as handle:
            opened = os.fstat(handle.fileno())
            if not stat.S_ISREG(opened.st_mode):
                raise TimedCliError(code)
            value = handle.read(limit + 1)
            after_open = os.fstat(handle.fileno())
        after = path.stat()
    except TimedCliError:
        raise
    except OSError as exc:
        raise TimedCliError(code) from exc

    def identity(item: os.stat_result) -> tuple[int, int, int, int]:
        return item.st_dev, item.st_ino, item.st_size, item.st_mtime_ns

    if len(value) > limit:
        raise TimedCliError(code)
    if not (identity(before) == identity(opened) == identity(after_open) == identity(after)):
        raise TimedCliError("EXTERNAL_BYTES_CHANGED")
    return value


def _assert_external_path(path: Path, bundle_root: Path) -> None:
    try:
        resolved = path.resolve(strict=True)
        root = bundle_root.resolve(strict=True)
        if resolved == root or root in resolved.parents:
            raise TimedCliError("EXTERNAL_EVIDENCE_PATH")
        current = path
        while True:
            if current.is_symlink() or current.is_junction():
                raise TimedCliError("EXTERNAL_EVIDENCE_PATH")
            if current.parent == current:
                break
            current = current.parent
    except TimedCliError:
        raise
    except OSError as exc:
        raise TimedCliError("EXTERNAL_EVIDENCE_PATH") from exc


def _validate_output_path(path: Path, protected: tuple[Path, ...]) -> None:
    try:
        resolved = path.resolve(strict=False)
        if path.exists() or path.is_symlink() or path.is_junction():
            raise TimedCliError("OUTPUT_EXISTS")
        if any(resolved == item.resolve(strict=True) for item in protected):
            raise TimedCliError("OUTPUT_PROTECTED_PATH")
        parent = path.parent.resolve(strict=True)
        if parent.is_symlink() or parent.is_junction():
            raise TimedCliError("OUTPUT_PATH")
    except TimedCliError:
        raise
    except OSError as exc:
        raise TimedCliError("OUTPUT_PATH") from exc


def _cards_hash(cards: tuple[object, ...]) -> str:
    rows = [(item.candidate.name, item.sha256) for item in cards]  # type: ignore[attr-defined]
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode()).hexdigest()


def _runner_hash() -> str:
    root = Path(__file__).resolve().parents[1]
    paths = (
        *sorted((root / "icarus").rglob("*.py")),
        root / "scripts/run_timed_backtest.py",
        root / "pyproject.toml",
        root / "uv.lock",
    )
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(root).as_posix().encode()
        value = _stable(path, 20_000_000, "RUNNER_DEPENDENCY_FILE")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(value).to_bytes(8, "big"))
        digest.update(value)
    return digest.hexdigest()


def _validate_external_bindings(
    preflight: BundlePreflight,
    certificate: QualificationCertificate,
    certificate_sha256: str,
    matching_policy_sha256: str,
    authorization: RunAuthorization,
    goal_sha256: str,
    cards_sha256: str,
    runner_sha256: str,
) -> ExecutionBinding:
    from icarus.engine.timed_runner import ExecutionBinding

    expected_certificate = (
        preflight.manifest_sha256,
        preflight.approval_sha256,
        preflight.policy_sha256,
        matching_policy_sha256,
    )
    actual_certificate = (
        certificate.manifest_sha256,
        certificate.approval_sha256,
        certificate.policy_sha256,
        certificate.matching_policy_sha256,
    )
    if actual_certificate != expected_certificate:
        raise TimedCliError("QUALIFICATION_BINDING")
    if not (
        certificate.approved_at <= authorization.issued_at <= datetime.now(UTC)
        and authorization.issued_at < authorization.expires_at
    ):
        raise TimedCliError("AUTHORIZATION_CHRONOLOGY")
    binding = ExecutionBinding(
        preflight.manifest_sha256,
        preflight.approval_sha256,
        preflight.policy_sha256,
        certificate_sha256,
        goal_sha256,
        cards_sha256,
        runner_sha256,
    )
    if binding != ExecutionBinding(
        authorization.bundle_sha256,
        authorization.approval_sha256,
        authorization.policy_sha256,
        authorization.qualification_sha256,
        authorization.goal_sha256,
        authorization.cards_sha256,
        authorization.runner_sha256,
    ):
        raise TimedCliError("AUTHORIZATION_BINDING_MISMATCH")
    return binding


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    preflight_command = commands.add_parser(
        "preflight", help="hash and capture bundle metadata only"
    )
    check = commands.add_parser("check", help="hash and capture bundle metadata only")
    run = commands.add_parser("run", help="run after external qualification and authorization")
    for command in (preflight_command, check, run):
        command.add_argument("--manifest", type=Path, required=True)
        command.add_argument("--approval", type=Path, required=True)
        command.add_argument("--source-policy", type=Path, required=True)
    run.add_argument("--matching-policy", type=Path, required=True)
    run.add_argument("--qualification", type=Path, required=True)
    run.add_argument(
        "--qualification-evidence",
        action="append",
        default=[],
        metavar="ROLE=PATH",
    )
    run.add_argument("--authorization", type=Path, required=True)
    run.add_argument("--goal", type=Path, default=Path("goal.yaml"))
    run.add_argument("--strategy-dir", type=Path, default=Path("strategies"))
    run.add_argument("--activated-ledger-dsn", required=True)
    run.add_argument("--out", type=Path, required=True)
    arguments = list(sys.argv[1:] if argv is None else argv)
    if not arguments or arguments[0] not in {"preflight", "check", "run"}:
        arguments.insert(0, "preflight")
    args = parser.parse_args(arguments)

    preflight = preflight_bundle(args.manifest, args.approval, args.source_policy)
    if args.command in {"preflight", "check"}:
        print(
            json.dumps(
                {
                    "metadata_verified": preflight.software_verified,
                    "data_qualified": False,
                    "run_authorized": False,
                    "manifest_sha256": preflight.manifest_sha256,
                    "approval_sha256": preflight.approval_sha256,
                    "policy_sha256": preflight.policy_sha256,
                    "status_reasons": preflight.status_reasons,
                },
                indent=2,
            )
        )
        return 0

    from sqlalchemy import create_engine

    from icarus.common.config import GoalConfig
    from icarus.engine.timed_evaluation import (
        CataloguePayload,
        EvaluationClock,
        TimedCatalogueEvaluator,
        build_evaluation_plans,
        load_strategy_catalogue,
    )
    from icarus.engine.timed_runner import (
        GuardedTimedRunner,
        assemble_timed_inputs,
        parse_calendar_jsonl,
        parse_run_authorization_json,
    )
    from icarus.state.trial_ledger import PostgresTrialLedger

    for external in (args.matching_policy, args.qualification, args.authorization):
        _assert_external_path(external, args.manifest.parent)
    qualification_raw = _stable(args.qualification, 1_000_000, "QUALIFICATION_FILE")
    authorization_raw = _stable(args.authorization, 1_000_000, "AUTHORIZATION_FILE")
    policy_raw = _stable(args.matching_policy, 1_000_000, "MATCHING_POLICY_FILE")
    source_policy_raw = _stable(args.source_policy, 1_000_000, "SOURCE_POLICY_FILE")
    if hashlib.sha256(source_policy_raw).hexdigest() != preflight.policy_sha256:
        raise TimedCliError("SOURCE_POLICY_BYTES_CHANGED")
    certificate = parse_qualification_certificate(qualification_raw)
    external_evidence = _evidence_arguments(args.qualification_evidence)
    _validate_qualification_evidence(
        preflight, certificate, external_evidence, args.manifest.parent
    )
    authorization = parse_run_authorization_json(authorization_raw)
    matching_policy = parse_matching_policy(policy_raw)
    _validate_policy_registration(source_policy_raw, policy_raw, certificate, matching_policy)
    goal_raw = _stable(args.goal, 2_000_000, "GOAL_FILE")
    try:
        goal_value = yaml.safe_load(goal_raw.decode("utf-8"))
        if type(goal_value) is not dict:
            raise ValueError("goal root")
        goal = GoalConfig.model_validate(goal_value)
    except Exception as exc:
        raise TimedCliError("GOAL_SCHEMA") from exc
    card_paths = tuple(sorted(args.strategy_dir.glob("*.yaml")))
    if len(card_paths) != 7 or {path.name for path in card_paths} != PRODUCTION_CARD_FILES:
        raise TimedCliError("PRODUCTION_CATALOGUE_IDENTITY")
    cards = load_strategy_catalogue(card_paths, goal)
    calendar_artifact = next(
        item for item in preflight.artifacts if item.role == "session_calendar"
    )
    calendar = tuple(
        item for item in parse_calendar_jsonl(calendar_artifact.payload) if item.open_ts
    )
    clock = EvaluationClock(
        tuple(item.source_index for item in calendar if item.source_index is not None),
        tuple(item.open_ts for item in calendar if item.open_ts is not None),
    )
    plans = build_evaluation_plans(cards, clock, goal)
    goal_sha256 = hashlib.sha256(goal_raw).hexdigest()
    cards_sha256, runner_sha256 = _cards_hash(cards), _runner_hash()
    binding = _validate_external_bindings(
        preflight,
        certificate,
        hashlib.sha256(qualification_raw).hexdigest(),
        hashlib.sha256(policy_raw).hexdigest(),
        authorization,
        goal_sha256,
        cards_sha256,
        runner_sha256,
    )
    _validate_output_path(
        args.out,
        (
            args.manifest,
            args.approval,
            args.source_policy,
            args.matching_policy,
            args.qualification,
            args.authorization,
            args.goal,
            *card_paths,
        ),
    )
    engine = create_engine(args.activated_ledger_dsn)
    try:
        runner = GuardedTimedRunner(PostgresTrialLedger(engine))
        evaluator = TimedCatalogueEvaluator(cards, goal, matching_policy)
        results = runner.run(
            authorization,
            binding,
            plans,
            lambda: CataloguePayload.from_assembled(assemble_timed_inputs(preflight), cards),
            evaluator.evaluate,
        )
        report = {
            "metadata_verified": True,
            "software_test_evidence_required_separately": True,
            "data_qualified": True,
            "run_authorized": True,
            "scope": "PRE_TAX_DESCRIPTIVE_NOT_PROMOTION_OR_ALPHA",
            "qualification_id": certificate.qualification_id,
            "matching_policy_id": matching_policy.policy_id,
            "qualification_evidence": "HASH_BOUND_EXTERNAL_ATTESTATIONS_NOT_VENDOR_AUTHENTICATION",
            "results": [
                {
                    "run_group_id": str(
                        uuid5(
                            NAMESPACE_URL,
                            f"{authorization.authorization_id}/{plan.card}/{plan.mode}/{plan.capital}",
                        )
                    ),
                    "plan": {
                        "card": plan.card,
                        "card_version": plan.card_version,
                        "card_sha256": plan.card_sha256,
                        "mode": plan.mode,
                        "capital": plan.capital,
                        "evaluations": [
                            {
                                "ordinal": item.ordinal,
                                "kind": item.kind.value,
                                "fold_index": item.fold_index,
                                "start_index": item.start_index,
                                "end_index_exclusive": item.end_index_exclusive,
                                "start_ts": (
                                    None if item.start_ts is None else item.start_ts.isoformat()
                                ),
                                "end_ts": None if item.end_ts is None else item.end_ts.isoformat(),
                                "reset_identity": item.reset_identity,
                            }
                            for item in plan.evaluations
                        ],
                    },
                    "outcomes": [item.payload for item in rows],
                }
                for plan, rows in zip(plans, results, strict=True)
            ],
        }
        try:
            with args.out.open("x", encoding="utf-8") as handle:
                json.dump(report, handle, indent=2)
        except OSError as exc:
            raise TimedCliError("OUTPUT_WRITE_FAILED") from exc
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(json.dumps({"status": "REFUSED", "reason": str(exc)}))
        raise SystemExit(2) from None
