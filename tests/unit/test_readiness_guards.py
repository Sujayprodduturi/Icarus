"""Focused invented-input witnesses for defects fixed by real-data readiness work."""

from __future__ import annotations

import hashlib
import io
import json
import stat
from datetime import UTC, datetime
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pytest
from scripts.run_timed_backtest import (
    EVIDENCE_KEYS,
    QualificationCertificate,
    TimedCliError,
    _validate_output_path,
    _validate_qualification_evidence,
)
from scripts.synthetic_strategy_demo import invented_panel
from tests.unit import test_shared_timing_integration as shared_timing
from tests.unit.test_data_readiness import _write_bundle
from tests.unit.test_timed_evaluation import _fixture

from icarus.common.config import load_goal
from icarus.engine import data_readiness, timed_simulation
from icarus.engine.costmodel import CostModel
from icarus.engine.data_readiness import BundlePreflight, CapturedArtifact, ReadinessError
from icarus.engine.fills import FillModel
from icarus.engine.signaltest import SignalSimulator
from icarus.engine.timed_evaluation import CataloguePayload, _stable_card_bytes
from icarus.engine.timed_runner import AssembledTimedInputs, NiftyObservation
from icarus.engine.timed_simulation import SourceDeclaration


class _RecordingBytes(io.BytesIO):
    def __init__(self, value: bytes) -> None:
        super().__init__(value)
        self.read_sizes: list[int] = []

    def read(self, size: int | None = -1) -> bytes:
        self.read_sizes.append(-1 if size is None else size)
        return super().read(size)

    def fileno(self) -> int:
        return 41


class _FakePath:
    def __init__(self, mode: int, stream: _RecordingBytes) -> None:
        self._stat = SimpleNamespace(st_mode=mode, st_dev=1, st_ino=2, st_size=4, st_mtime_ns=5)
        self._stream = stream
        self.parent = self

    def is_symlink(self) -> bool:
        return False

    def is_junction(self) -> bool:
        return False

    def stat(self) -> Any:
        return self._stat

    def open(self, mode: str) -> _RecordingBytes:
        assert mode == "rb"
        return self._stream


def test_bounded_reader_requests_only_limit_plus_one_from_a_growing_source(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = _RecordingBytes(b"0123456789")
    path = _FakePath(stat.S_IFREG | 0o600, stream)
    monkeypatch.setattr("icarus.engine.data_readiness.os.fstat", lambda _fd: path._stat)
    with pytest.raises(ReadinessError, match="TEST_SIZE"):
        data_readiness._read_limited(path, 4, "TEST_SIZE")  # type: ignore[arg-type]
    assert stream.read_sizes == [5]


def test_nonregular_reader_refuses_before_open(monkeypatch: pytest.MonkeyPatch) -> None:
    stream = _RecordingBytes(b"must-not-open")
    path = _FakePath(stat.S_IFDIR | 0o700, stream)
    monkeypatch.setattr(
        path,
        "open",
        lambda _mode: pytest.fail("nonregular resource was opened"),
    )
    with pytest.raises(ReadinessError, match="NONREGULAR_FILE"):
        data_readiness._read_limited(path, 4, "TEST_SIZE")  # type: ignore[arg-type]


def test_aggregate_budget_refuses_final_artifact_before_its_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    manifest, approval, policy = _write_bundle(tmp_path / "bundle")
    manifest_value = json.loads(manifest.read_text())
    total = sum(row["size"] for row in manifest_value["artifacts"])
    policy_value = json.loads(policy.read_text())
    policy_value["max_total_bytes"] = total - 1
    policy.write_text(json.dumps(policy_value))
    approval_value = json.loads(approval.read_text())
    approval_value["policy_sha256"] = hashlib.sha256(policy.read_bytes()).hexdigest()
    approval.write_text(json.dumps(approval_value))

    original = data_readiness._read_limited
    artifact_reads: list[str] = []

    def recording(path: Path, limit: int, code: str) -> bytes:
        if path.parent == manifest.parent and path != manifest:
            artifact_reads.append(path.name)
        return original(path, limit, code)

    monkeypatch.setattr(data_readiness, "_read_limited", recording)
    with pytest.raises(ReadinessError, match="BUNDLE_SIZE"):
        data_readiness.preflight_bundle(manifest, approval, policy)
    assert artifact_reads == [row["path"] for row in manifest_value["artifacts"][:-1]]


def test_simulated_cross_drive_member_is_rejected_but_external_approval_is_allowed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    member = bundle / "row.jsonl"
    member.write_text("invented")
    monkeypatch.setattr(
        "icarus.engine.data_readiness.os.path.commonpath",
        lambda _paths: (_ for _ in ()).throw(ValueError("different drives")),
    )
    with pytest.raises(ReadinessError, match="MEMBER_PATH"):
        data_readiness._member(bundle, "row.jsonl")

    manifest = bundle / "manifest.json"
    approval = tmp_path / "approval.json"
    policy = tmp_path / "policy.json"
    for path in (manifest, approval, policy):
        path.write_text("{}")
    with pytest.raises(ReadinessError, match="POLICY_FIELDS"):
        data_readiness.preflight_bundle(manifest, approval, policy)


def test_strategy_card_reader_is_bounded_and_rejects_nonregular(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    card = tmp_path / "card.yaml"
    card.write_bytes(b"x" * 1_000_001)
    with pytest.raises(ValueError, match="bounded schema"):
        _stable_card_bytes(card)

    directory = tmp_path / "directory-card"
    directory.mkdir()
    opened = False

    def forbidden_open(*_args: object, **_kwargs: object) -> object:
        nonlocal opened
        opened = True
        raise AssertionError("directory opened")

    monkeypatch.setattr(Path, "open", forbidden_open)
    with pytest.raises(ValueError, match="regular file"):
        _stable_card_bytes(directory)
    assert opened is False


def test_output_guard_rejects_existing_and_protected_paths(tmp_path: Path) -> None:
    existing = tmp_path / "existing.json"
    existing.write_text("invented")
    with pytest.raises(TimedCliError, match="OUTPUT_EXISTS"):
        _validate_output_path(existing, ())

    with pytest.raises(TimedCliError, match="OUTPUT_EXISTS"):
        _validate_output_path(existing, (existing,))


def test_nifty_source_identity_changes_with_the_explicit_raw_artifact_pin() -> None:
    panel = invented_panel()
    fixture = _fixture(panel)
    observed = (
        NiftyObservation(
            "nifty-1",
            "revision-1",
            datetime(2020, 1, 1, 10, tzinfo=UTC),
            datetime(2020, 1, 1, 10, tzinfo=UTC),
            True,
            Fraction(12_345, 1),
        ),
    )
    identities = []
    for digest in ("a" * 64, "b" * 64):
        assembled = AssembledTimedInputs(
            panel,
            fixture,
            tuple(range(len(panel))),
            observed,
            False,
            SourceDeclaration("invented-nifty", "revision-1", digest),
        )
        identities.append(CataloguePayload.from_assembled(assembled, ()).benchmark_identity)
    assert identities[0].artifact_sha256 != identities[1].artifact_sha256


def test_qualification_evidence_must_equal_bundle_and_external_bytes(tmp_path: Path) -> None:
    (tmp_path / "bundle").mkdir()
    roles = {
        "nifty_observation": "a" * 64,
        "session_calendar": "b" * 64,
        "corporate_action": "c" * 64,
        "pit_universe": "d" * 64,
        "opening_liquidity": "e" * 64,
    }
    artifacts = tuple(
        CapturedArtifact(role, f"{role}.jsonl", digest, 1, b"x", {})
        for role, digest in roles.items()
    )
    preflight = BundlePreflight("f" * 64, "1" * 64, "2" * 64, artifacts, True, False, False, ())
    external: dict[str, Path] = {}
    evidence = {
        "benchmark_identity": roles["nifty_observation"],
        "calendar": roles["session_calendar"],
        "corporate_adjustments": roles["corporate_action"],
        "pit_delisted": roles["pit_universe"],
        "prior_only_liquidity": roles["opening_liquidity"],
    }
    for role in ("archive", "licence", "raw_event_availability"):
        path = tmp_path / f"{role}.txt"
        value = f"invented-{role}".encode()
        path.write_bytes(value)
        external[role] = path
        evidence[role] = hashlib.sha256(value).hexdigest()
    assert set(evidence) == EVIDENCE_KEYS
    certificate = QualificationCertificate(
        "invented-review",
        "invented-reviewer",
        datetime(2026, 10, 14, 1, tzinfo=UTC),
        datetime(2026, 10, 14, 0, tzinfo=UTC),
        preflight.manifest_sha256,
        preflight.approval_sha256,
        preflight.policy_sha256,
        "3" * 64,
        evidence,
        False,
    )
    _validate_qualification_evidence(preflight, certificate, external, tmp_path / "bundle")
    bad = QualificationCertificate(
        certificate.qualification_id,
        certificate.reviewer,
        certificate.approved_at,
        certificate.policy_registered_at,
        certificate.manifest_sha256,
        certificate.approval_sha256,
        certificate.policy_sha256,
        certificate.matching_policy_sha256,
        {**evidence, "calendar": "9" * 64},
        False,
    )
    with pytest.raises(TimedCliError, match="QUALIFICATION_ARTIFACT_EVIDENCE"):
        _validate_qualification_evidence(preflight, bad, external, tmp_path / "bundle")


def test_requested_span_with_missing_m15_refuses_without_clipping_names_or_dates() -> None:
    complete = shared_timing.make(timed_simulation, ("S0",), days=2)
    daily = shared_timing.panel(complete)
    later_only = timed_simulation.Refinement("S0", complete.refinements[0].bars[2:])
    broken = shared_timing.bind(timed_simulation, complete.sessions, (later_only,))
    goal = load_goal()
    simulator = SignalSimulator(
        notional_inr=Decimal("1000"),
        costs=CostModel(goal.costs),
        fills=FillModel(goal.execution_realism),
        stale_after_sessions=goal.backtest.stale_position_sessions,
    )
    run = simulator.run_time_resolved(
        shared_timing.strategy(),
        daily,
        {"S0": np.zeros(2, dtype=np.float64)},
        {"S0": np.ones(2, dtype=np.float64)},
        fixture=broken,
        source_indices=(252, 253),
    )
    assert not run.valid
    assert run.refusal is not None
    assert run.refusal.reason is timed_simulation.TimedRefusal.MISSING_REFINEMENT
    assert run.source_indices == (252, 253)
    assert run.symbols == ("S0",)
    assert run.trades == ()
    assert run.cash is run.realized_equity is run.final_equity is None
