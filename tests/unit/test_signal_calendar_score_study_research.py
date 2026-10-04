"""Deterministic contracts for the calendar-score v2 artificial-study runner."""

from __future__ import annotations

import hashlib
import importlib.metadata
import json
import os
import subprocess
import threading
from fractions import Fraction as F
from pathlib import Path
from typing import Any

import psutil  # type: ignore[import-untyped]
import pytest
from scripts.research import signal_calendar_score_study as study


def _test_manifest(root: Path) -> study.Manifest:
    root.mkdir(parents=True, exist_ok=True)
    marker = root / "test-source.txt"
    marker.write_bytes(b"calendar-score deterministic fixture\n")
    return study.manifest_for_paths(
        {"test-source.txt": marker},
        protocol_hash=study.PROTOCOL_SHA256,
        scope="deterministic_test_fixture",
    )


def test_frozen_manifest_geometry_and_statement_accounting() -> None:
    assert (
        study.PROTOCOL_SHA256 == "130569a78811e9ad4f9dcdb915410b3c350e137a78bc70974eb81ac4daf13b71"
    )
    assert [(item.profile_id, item.n, item.classes) for item in study.SPECS] == [
        ("P1", 2048, 2),
        ("P2", 2048, 2),
        ("P3", 16384, 9),
        ("P4", 8192, 5),
        ("P5", 32768, 2),
        ("P6", 32768, 2),
        ("P7", 131072, 40),
        ("E+", 2048, 2),
        ("E-", 2048, 2),
        ("L1", 2048, 2),
    ]
    assert study.phase_totals("development") == (81920, 229376)
    assert study.phase_totals("validation") == (327680, 917504)
    assert study.statement_count() == 88


def test_exact_supports_truths_and_predata_eligibility() -> None:
    p1 = study.spec("P1")
    targets = study.targets(p1)
    assert [(t.metric.value, t.lower, t.upper) for t in targets] == [
        ("raw", F(-1, 50), F(1, 50)),
        ("win", F(0), F(1)),
        ("synthetic_excess", F(-19, 1000), F(13, 1000)),
    ]
    assert study.truths(p1) == {
        "raw": F(0),
        "win": F(1, 4),
        "synthetic_excess": F(-1, 200),
    }
    for item in study.SPECS:
        adequacy = study.adequacy(item)
        if item.profile_id == "L1":
            assert not adequacy.decision_eligible
            assert adequacy.reason == "sparse_selection_unsupported"
        else:
            assert adequacy.decision_eligible, item.profile_id


@pytest.mark.parametrize(
    "n,p,lower,want",
    [
        (32768, F(19, 20), True, 31258),
        (32768, F(1, 100), False, 270),
        (32768, F(9, 10), True, 29668),
    ],
)
def test_exact_validation_cutoffs_match_independent_review(
    n: int, p: F, lower: bool, want: int
) -> None:
    assert study.exact_cutoff(n, p, lower=lower) == want
    assert study.accepts_exact_binomial(want, n, p, lower=lower)
    adjacent = want - 1 if lower else want + 1
    assert not study.accepts_exact_binomial(adjacent, n, p, lower=lower)


def test_exact_small_binomial_equality_and_impossible_boundaries() -> None:
    # P(X>=2) for Bin(2,1/2) is exactly 1/4; equality is accepted.
    assert study.accepts_exact_binomial(2, 2, F(1, 2), lower=True, eta=F(1, 4))
    assert not study.accepts_exact_binomial(1, 2, F(1, 2), lower=True, eta=F(1, 4))
    assert study.exact_cutoff(1, F(1, 2), lower=True, eta=F(1, 8)) == 2
    assert study.exact_cutoff(1, F(1, 2), lower=False, eta=F(1, 8)) == -1


def test_stream_prefix_and_known_words_are_framed_exactly() -> None:
    root = bytes(32)
    stream = study.CounterStream(
        namespace=study.PREFLIGHT_NAMESPACE,
        phase="test_preflight",
        profile_id="P1",
        n=2048,
        replicate=0,
        root=root,
    )
    assert stream.prefix == (
        b'["icarus/calendar-score-research/test-preflight/v2",'
        b'"finite-calendar-law/v1","sha256-counter-u64x4-big-endian/v2",'
        b'"test_preflight","P1:2048",0,' + b'"' + b"0" * 64 + b'"]\n'
    )
    assert [stream.next_word() for _ in range(5)] == [
        17178914821994726101,
        16061446197116128555,
        2642099818172358451,
        8061481959689794875,
        14284209687861624289,
    ]
    assert stream.words_consumed == 5


def test_experimental_stream_requires_a_live_claim_capability() -> None:
    with pytest.raises(study.StudyError, match="unclaimed_experimental_stream"):
        study.CounterStream(
            namespace=study.EXPERIMENT_NAMESPACE,
            phase="development",
            profile_id="P1",
            n=2048,
            replicate=0,
            root=bytes(32),
        )


class _Words:
    def __init__(self, values: list[int]) -> None:
        self.values = iter(values)
        self.words_consumed = 0

    def next_word(self) -> int:
        self.words_consumed += 1
        return next(self.values)


def test_uniform_rejection_counts_every_word_and_stops_after_1024() -> None:
    limit = (1 << 64) // 3 * 3
    source = _Words([(1 << 64) - 1, 5])
    assert study.uniform(source, 3) == 2
    assert source.words_consumed == 2
    stuck = _Words([(1 << 64) - 1] * 1024)
    with pytest.raises(study.StudyError, match="rejection_limit"):
        study.uniform(stuck, 3)
    assert stuck.words_consumed == 1024
    assert limit == (1 << 64) - 1


def test_atom_mapping_draw_order_and_lossless_payload() -> None:
    item = study.spec("P5")
    # S,Q,G,e1,e2,J. The jump word lands in the first listed half-open atom.
    words = _Words([0, 0, 0, 0, 1, 0] * study.source_length(item))
    payload = study.generate_payload(item, words)
    assert payload == bytes([1 | 2 | 4 | 8 | (0 << 4) | (0 << 5)]) * study.source_length(item)
    assert words.words_consumed == 6 * study.source_length(item)
    assert study.evaluate_payload(item, payload).count >= item.n


def test_strict_win_tie_is_not_a_win_and_results_reconcile() -> None:
    item = study.spec("P1")
    # s=-1 makes factor=-1; epsilon1=+1 gives raw zero, which strict win excludes.
    atom = 4 | 8 | 16
    result = study.evaluate_payload(item, bytes([atom]) * study.source_length(item))
    rows = {row.metric: row for row in result.rows}
    assert rows["raw"].total == 0
    assert rows["win"].total == 0
    assert rows["synthetic_excess"].total == F(13 * item.n, 1000)
    assert all(row.arithmetic and row.precision for row in result.rows)


def test_source_manifest_detects_protocol_and_transitive_source_drift(tmp_path: Path) -> None:
    source = tmp_path / "source.py"
    source.write_text("old", encoding="ascii")
    manifest = study.manifest_for_paths({"source.py": source}, protocol_hash="b" * 64)
    study.verify_manifest(manifest, {"source.py": source}, protocol_hash="b" * 64)
    source.write_text("new", encoding="ascii")
    with pytest.raises(study.StudyError, match="source_drift"):
        study.verify_manifest(manifest, {"source.py": source}, protocol_hash="b" * 64)
    with pytest.raises(study.StudyError, match="protocol_drift"):
        study.verify_manifest(manifest, {"source.py": source}, protocol_hash="c" * 64)


def test_source_manifest_rejects_changed_protocol_bytes(monkeypatch: Any) -> None:
    original = Path.read_bytes

    def changed_protocol(path: Path) -> bytes:
        blob = original(path)
        if path == study.PROJECT / study.PROTOCOL_PATH:
            return blob + b"\nchanged after review\n"
        return blob

    monkeypatch.setattr(Path, "read_bytes", changed_protocol)
    with pytest.raises(study.StudyError, match="protocol_drift"):
        study.source_manifest()


class _ShortWriter:
    def __init__(self, limits: list[int], *, flush_error: bool = False, close_error: bool = False):
        self.limits = iter(limits)
        self.data = bytearray()
        self.flush_error = flush_error
        self.close_error = close_error
        self.closed = False

    def write(self, blob: bytes | memoryview) -> int:
        limit = next(self.limits, len(blob))
        count = min(limit, len(blob))
        self.data.extend(blob[:count])
        return count

    def flush(self) -> None:
        if self.flush_error:
            raise OSError("flush failed")

    def fileno(self) -> int:
        return 1

    def close(self) -> None:
        self.closed = True
        if self.close_error:
            raise OSError("close failed")


def test_write_all_completes_partial_writes_and_refuses_zero_progress() -> None:
    partial = _ShortWriter([2, 1, 3])
    study._write_all(partial, b"abcdef")
    assert partial.data == b"abcdef"
    with pytest.raises(study.StudyError, match="short_write"):
        study._write_all(_ShortWriter([0]), b"x")


@pytest.mark.parametrize("failure", ["flush", "fsync", "close"])
def test_exclusive_record_propagates_durability_failures(
    tmp_path: Path, monkeypatch: Any, failure: str
) -> None:
    stream = _ShortWriter(
        [1] * 100,
        flush_error=failure == "flush",
        close_error=failure == "close",
    )
    monkeypatch.setattr(study, "_open_exclusive", lambda path: stream)
    if failure == "fsync":
        monkeypatch.setattr(
            os, "fsync", lambda descriptor: (_ for _ in ()).throw(OSError("fsync failed"))
        )
    expected = "close_failure" if failure == "close" else f"{failure} failed"
    with pytest.raises((OSError, study.StudyError), match=expected):
        study._exclusive_record(tmp_path / "record.json", {"ok": True}, root=tmp_path)
    assert stream.closed


def test_bounded_canonical_writer_reader_rejects_overflow_corruption_and_trailing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "records.jsonl"
    with study.CanonicalRecordWriter(path, total_cap=80, record_cap=64, sync_every=1) as writer:
        writer.write({"a": 1})
        with pytest.raises(study.StudyError, match="record_cap"):
            writer.write({"too_big": "x" * 80})
    assert list(study.read_canonical_records(path, total_cap=80, record_cap=64)) == [{"a": 1}]
    path.write_bytes(path.read_bytes() + b"{}")
    with pytest.raises(study.StudyError, match="trailing_or_noncanonical"):
        list(study.read_canonical_records(path, total_cap=80, record_cap=64))


def test_writer_rejects_reparse_ancestor_before_creating_parent(
    tmp_path: Path, monkeypatch: Any
) -> None:
    parent = tmp_path / "missing"
    original = study._is_reparse
    monkeypatch.setattr(study, "_is_reparse", lambda path: path == tmp_path or original(path))
    with pytest.raises(study.StudyError, match="reparse_path"):
        study.CanonicalRecordWriter(parent / "records.jsonl", total_cap=80)
    assert not parent.exists()


@pytest.mark.parametrize("reparse_part", ["root", "ancestor", "leaf"])
def test_path_guard_checks_lexical_reparse_chain_before_resolving(
    tmp_path: Path, monkeypatch: Any, reparse_part: str
) -> None:
    root = tmp_path / "root"
    ancestor = root / "ancestor"
    ancestor.mkdir(parents=True)
    leaf = ancestor / "leaf.bin"
    leaf.write_bytes(b"x")
    selected = {"root": root, "ancestor": ancestor, "leaf": leaf}[reparse_part]
    original = study._is_reparse
    monkeypatch.setattr(study, "_is_reparse", lambda path: path == selected or original(path))
    with pytest.raises(study.StudyError, match="reparse_path"):
        study._guard_path(leaf, root, existing=True)


def test_path_guard_checks_ancestors_above_selected_root(tmp_path: Path, monkeypatch: Any) -> None:
    root = tmp_path / "root"
    root.mkdir()
    leaf = root / "leaf.bin"
    leaf.write_bytes(b"x")
    original = study._is_reparse
    monkeypatch.setattr(study, "_is_reparse", lambda path: path == tmp_path or original(path))
    with pytest.raises(study.StudyError, match="reparse_path"):
        study._guard_path(leaf, root, existing=True)


@pytest.mark.parametrize(
    "elapsed,rss,heartbeat_age,free,reason",
    [
        (11.0, 1, 0.0, 100, "timeout"),
        (0.0, 101, 0.0, 100, "memory"),
        (0.0, 1, 31.0, 100, "heartbeat"),
        (0.0, 1, 0.0, 9, "disk_reserve"),
    ],
)
def test_supervisor_limits_fail_closed(
    elapsed: float, rss: int, heartbeat_age: float, free: int, reason: str
) -> None:
    limits = study.SupervisionLimits(10.0, 100, 30.0, 10)
    with pytest.raises(study.StudyError, match=reason):
        study.check_supervision(limits, elapsed, rss, heartbeat_age, free)


def test_resource_limits_are_explicitly_monitored_not_claimed_hard() -> None:
    disclosure = study.resource_disclosure()
    assert disclosure == {
        "operational_resources": study.load_operational_resources().binding(),
        "rss_enforcement": "MONITORED_CANCELLATION_LIMIT",
        "sample_interval_seconds": "<=0.25",
        "transient_peaks_between_samples": "UNPROVED",
        "windows_power_loss_equivalence": "NOT_CLAIMED",
    }


def test_cli_defaults_to_refusal_and_only_preflight_is_public() -> None:
    parser = study.parser()
    args = parser.parse_args([])
    assert not args.preflight and args.internal_worker is None
    with pytest.raises(study.StudyError, match="preflight_only"):
        study.dispatch(args)


def test_preflight_plan_is_full_workload_and_separate_from_experimental_namespace() -> None:
    plan = study.preflight_plan()
    assert plan.namespace == study.PREFLIGHT_NAMESPACE
    assert plan.namespace != study.EXPERIMENT_NAMESPACE
    assert plan.root == bytes(32)
    assert plan.phase == "test_preflight"
    assert [(p.profile_id, p.n, p.replicates) for p in plan.phases] == [
        (item.profile_id, item.n, 1) for item in study.SPECS
    ]
    assert plan.disk_probe_bytes == 32 * 1024 * 1024
    assert plan.safety_factor == 2


def test_deterministic_preflight_uses_production_workload_and_cleans_probe(tmp_path: Path) -> None:
    manifest = _test_manifest(tmp_path / "manifest")
    plan = study.test_preflight_plan(tmp_path / "evidence", (study.spec("P1"),))
    assert plan.evidence_root is not None
    receipt = study.execute_preflight(plan, manifest)
    assert receipt.generated_paths == 1
    assert receipt.replayed_paths == 1
    assert receipt.disk_probe_bytes == 32 * 1024
    assert receipt.source_manifest_digest == manifest.digest
    assert receipt.eligible
    assert not (plan.evidence_root / "preflight-disk-probe.bin").exists()
    assert (plan.evidence_root / "preflight-payload.bin").exists()
    assert (plan.evidence_root / "preflight-index.jsonl").exists()
    assert (plan.evidence_root / "preflight-probe-cleanup.json").exists()


def test_execute_preflight_rejects_reparse_ancestor_before_root_creation(
    tmp_path: Path, monkeypatch: Any
) -> None:
    parent = tmp_path / "unsafe-parent"
    parent.mkdir()
    root = parent / "evidence"
    manifest = _test_manifest(tmp_path / "manifest")
    plan = study.test_preflight_plan(root, (study.spec("P1"),))
    original = study._is_reparse
    monkeypatch.setattr(study, "_is_reparse", lambda path: path == parent or original(path))
    with pytest.raises(study.StudyError, match="reparse_path"):
        study.execute_preflight(plan, manifest)
    assert not root.exists()


def test_preflight_runs_under_real_subprocess_supervision(tmp_path: Path) -> None:
    manifest = _test_manifest(tmp_path / "manifest")
    plan = study.test_preflight_plan(tmp_path / "supervised", (study.spec("P1"),))
    assert plan.evidence_root is not None
    receipt = study.run_supervised_preflight(plan.evidence_root, plan=plan, manifest=manifest)
    assert receipt.generated_paths == receipt.replayed_paths == 1
    assert (plan.evidence_root / "preflight-terminal.json").exists()
    assert not (plan.evidence_root / "preflight-failure.json").exists()


def test_launcher_rejects_reparse_ancestor_before_mkdir_or_launch(
    tmp_path: Path, monkeypatch: Any
) -> None:
    parent = tmp_path / "junction-parent"
    parent.mkdir()
    root = parent / "run"
    manifest = _test_manifest(tmp_path / "manifest")
    plan = study.test_preflight_plan(root, (study.spec("P1"),))
    original = study._is_reparse
    monkeypatch.setattr(study, "_is_reparse", lambda path: path == parent or original(path))
    monkeypatch.setattr(
        subprocess,
        "Popen",
        lambda *args, **kwargs: pytest.fail("unsafe launcher reached subprocess"),
    )
    with pytest.raises(study.StudyError, match="reparse_path"):
        study.run_supervised_preflight(root, plan=plan, manifest=manifest)
    assert not root.exists()


class _ExitedProcess:
    pid = -1
    returncode = 0

    def poll(self) -> int:
        return 0


def test_supervisor_runs_completion_time_checks(tmp_path: Path, monkeypatch: Any) -> None:
    root = tmp_path / "supervised"
    root.mkdir()
    (root / "heartbeat.json").write_text("{}\n", encoding="ascii")
    (root / "preflight-worker.log").write_bytes(b"")
    samples: list[tuple[float, int, float, int]] = []

    def record_sample(
        limits: study.SupervisionLimits,
        elapsed: float,
        rss: int,
        heartbeat_age: float,
        free_bytes: int,
    ) -> None:
        samples.append((elapsed, rss, heartbeat_age, free_bytes))

    monkeypatch.setattr(study, "check_supervision", record_sample)
    study._supervise_preflight(_ExitedProcess(), root)  # type: ignore[arg-type]
    assert len(samples) == 1


def test_worker_propagates_fast_heartbeat_io_failure_before_complete(
    tmp_path: Path, monkeypatch: Any
) -> None:
    root = tmp_path / "worker"
    root.mkdir()
    nonce = "a" * 64
    manifest = _test_manifest(tmp_path / "manifest")
    plan = study.test_preflight_plan(root, (study.spec("P1"),))
    (root / "preflight-claim.json").write_bytes(
        study.canonical_json(
            {
                "operational_resources": study.load_operational_resources().binding(),
                "manifest": {"digest": manifest.digest, "payload": manifest.payload},
                "nonce": nonce,
                "plan": study._plan_record(plan),
            }
        )
    )

    class _Receipt:
        digest = "d" * 64

    monkeypatch.setattr(study, "execute_preflight", lambda selected, source: _Receipt())

    def fail_heartbeat(path: Path, stop: Any, errors: list[BaseException]) -> None:
        errors.append(OSError("heartbeat write failed"))
        stop.set()

    monkeypatch.setattr(study, "_heartbeat", fail_heartbeat)
    with pytest.raises(study.StudyError, match="heartbeat_io"):
        study._internal_preflight_worker(root, nonce)
    assert not (root / "preflight-terminal.json").exists()


def test_heartbeat_body_captures_write_failure(tmp_path: Path, monkeypatch: Any) -> None:
    stop = threading.Event()
    errors: list[BaseException] = []
    monkeypatch.setattr(
        study,
        "_write_all",
        lambda stream, blob: (_ for _ in ()).throw(OSError("heartbeat write failed")),
    )
    study._heartbeat(tmp_path / "heartbeat.json", stop, errors)
    assert stop.is_set()
    assert len(errors) == 1
    assert isinstance(errors[0], OSError)


@pytest.mark.parametrize(
    "mode,reason,stage",
    [
        ("startup", "disk_reserve", "startup"),
        ("supervision", "worker_log_cap", "supervision"),
        ("close", "close_failure", "supervision"),
    ],
)
def test_supervised_failure_retains_stable_reason_and_stage(
    tmp_path: Path, monkeypatch: Any, mode: str, reason: str, stage: str
) -> None:
    root = tmp_path / mode
    manifest = _test_manifest(tmp_path / f"manifest-{mode}")
    plan = study.test_preflight_plan(root, (study.spec("P1"),))

    class _Process:
        pid = -1
        returncode = 0

        def poll(self) -> int:
            return 0

    if mode == "startup":
        usage = psutil.disk_usage(str(tmp_path))
        monkeypatch.setattr(
            psutil,
            "disk_usage",
            lambda path: usage._replace(free=0),
        )
    else:
        monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: _Process())
        if mode == "supervision":
            monkeypatch.setattr(
                study,
                "_supervise_preflight",
                lambda process, selected: (_ for _ in ()).throw(study.StudyError("worker_log_cap")),
            )
        else:
            original_open = study._open_exclusive

            def close_failing_open(path: Path) -> Any:
                if path.name != "preflight-worker.log":
                    return original_open(path)
                return _ShortWriter([100000], close_error=True)

            monkeypatch.setattr(study, "_open_exclusive", close_failing_open)
            monkeypatch.setattr(study, "_supervise_preflight", lambda process, selected: None)
    with pytest.raises(study.StudyError, match=reason):
        study.run_supervised_preflight(root, plan=plan, manifest=manifest)
    failure = json.loads((root / "preflight-failure.json").read_bytes())
    assert failure["reason"] == reason
    assert failure["stage"] == stage
    assert not (root / "preflight-terminal.json").exists()


def test_preflight_cleanup_failure_is_receipted_and_cannot_report_success(
    tmp_path: Path, monkeypatch: Any
) -> None:
    manifest = _test_manifest(tmp_path / "manifest")
    plan = study.test_preflight_plan(tmp_path / "evidence", (study.spec("P1"),))
    assert plan.evidence_root is not None
    original = Path.unlink

    def fail_index(path: Path, *args: Any, **kwargs: Any) -> None:
        if path.name == "preflight-disk-probe.bin":
            raise OSError("blocked")
        original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", fail_index)
    with pytest.raises(study.StudyError, match="preflight_cleanup_failure"):
        study.execute_preflight(plan, manifest)
    failure = json.loads((plan.evidence_root / "preflight-cleanup-failure.json").read_bytes())
    assert failure["state"] == "PARTIAL_FAILURE"
    assert not (plan.evidence_root / "preflight-receipt.json").exists()


def test_manifest_json_is_canonical_and_digest_bound(tmp_path: Path) -> None:
    manifest = _test_manifest(tmp_path)
    payload = study.canonical_json(manifest.payload)
    assert (
        payload
        == json.dumps(
            manifest.payload, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
        + b"\n"
    )
    assert manifest.digest == hashlib.sha256(payload).hexdigest()


class _IndependentStream:
    """Original scalar SHA framing, without production buffering."""

    def __init__(self, prefix: bytes, *, counter: int = 0, lanes: tuple[int, ...] = ()) -> None:
        self.prefix = prefix
        self.counter = counter
        self.lanes = list(lanes)
        self.words_consumed = 0

    def next_word(self) -> int:
        if not self.lanes:
            if self.counter >= 1 << 64:
                raise study.StudyError("counter_overflow")
            block = hashlib.sha256(self.prefix + self.counter.to_bytes(8, "big")).digest()
            self.lanes = [int.from_bytes(block[i : i + 8], "big") for i in range(0, 32, 8)]
            self.counter += 1
        self.words_consumed += 1
        return self.lanes.pop(0)


def _stream(
    item: study.StudySpec, root: bytes = bytes(32), replicate: int = 0, *, preflight: bool = False
) -> study.CounterStream:
    return study.CounterStream(
        namespace=study.PREFLIGHT_NAMESPACE if preflight else study.TEST_NAMESPACE,
        phase="test_preflight" if preflight else "test_fixture",
        profile_id=item.profile_id,
        n=item.n,
        root=root,
        replicate=replicate,
    )


def test_buffer_peek_ownership_partial_lanes_and_bounded_refusal() -> None:
    stream = _stream(study.spec("P1"))
    oracle = _IndependentStream(stream.prefix)
    expected = [oracle.next_word() for _ in range(17)]
    first = stream.peek_words(7)
    assert type(first) is bytes
    assert stream.words_consumed == 0
    assert first == b"".join(word.to_bytes(8, "big") for word in expected[:7])
    stream.consume_words(3)
    assert stream.next_word() == expected[3]
    assert stream.peek_words(13) == b"".join(word.to_bytes(8, "big") for word in expected[4:17])
    assert first == b"".join(word.to_bytes(8, "big") for word in expected[:7])
    assert stream.words_consumed == 4
    for invalid in (0, -1, 49153, True):
        with pytest.raises(study.StudyError, match="word_buffer_count"):
            stream.peek_words(invalid)
    with pytest.raises(study.StudyError, match="word_buffer_count"):
        stream.consume_words(18)
    assert stream.next_word() == expected[4]


def test_buffer_overflow_refuses_atomically_then_consumes_valid_suffix() -> None:
    stream = _stream(study.spec("P1"))
    stream._counter = (1 << 64) - 1
    first = stream.next_word()
    counter = stream._counter
    with pytest.raises(study.StudyError, match="counter_overflow"):
        stream.peek_words(4)
    assert stream._counter == counter and stream.words_consumed == 1
    oracle = _IndependentStream(stream.prefix, counter=(1 << 64) - 1)
    assert first == oracle.next_word()
    assert [stream.next_word() for _ in range(3)] == [oracle.next_word() for _ in range(3)]
    with pytest.raises(study.StudyError, match="counter_overflow"):
        stream.next_word()
    assert stream.words_consumed == 4


@pytest.mark.parametrize("item", study.SPECS, ids=lambda item: item.profile_id)
def test_optimized_full_frozen_payload_matches_old_scalar_and_committed_hash(
    item: study.StudySpec,
) -> None:
    stream = _stream(item, preflight=True)
    oracle = _IndependentStream(stream.prefix)
    actual = study.generate_payload(item, stream)
    expected = study.generate_payload(item, oracle)
    baseline = json.loads(
        (study.PROJECT / "docs/reviews/2026-10-04-calendar-score-study-preflight.json").read_bytes()
    )
    row = next(row for row in baseline["path_results"] if row["profile_id"] == item.profile_id)
    assert hashlib.sha256(actual).hexdigest() == row["payload_sha256"]
    assert actual == expected
    assert stream.words_consumed == oracle.words_consumed == 6 * len(actual)
    assert stream.next_word() == oracle.next_word()


@pytest.mark.parametrize("root,replicate", [(bytes(range(32)), 7), (b"x" * 32, 19)])
@pytest.mark.parametrize("profile_id", ["P4", "P7", "L1"])
def test_test_domain_batch_boundaries_match_independent_scalar(
    root: bytes, replicate: int, profile_id: str
) -> None:
    item = study.spec(profile_id)
    stream = _stream(item, root, replicate)
    oracle = _IndependentStream(stream.prefix)
    assert study.generate_payload(item, stream) == study.generate_payload(item, oracle)
    assert stream.words_consumed == oracle.words_consumed
    assert stream.next_word() == oracle.next_word()


@pytest.mark.parametrize("fail_at", [None, 0, 65536])
def test_callback_consumption_and_exception_boundary_match_scalar(fail_at: int | None) -> None:
    item = study.spec("P7")
    stream = _stream(item)
    oracle = _IndependentStream(stream.prefix)
    observations: list[list[tuple[int, int]]] = [[], []]

    def run(source: Any, log: list[tuple[int, int]]) -> bytes | None:
        def progress(index: int) -> None:
            log.append((index, source.words_consumed))
            if index == fail_at:
                raise ValueError("callback stopped")

        if fail_at is not None:
            with pytest.raises(ValueError, match="callback stopped"):
                study.generate_payload(item, source, progress=progress)
            return None
        return study.generate_payload(item, source, progress=progress)

    assert run(stream, observations[0]) == run(oracle, observations[1])
    assert observations[0] == observations[1]
    assert observations[0][0] == (0, 6)
    assert stream.words_consumed == oracle.words_consumed
    assert stream.next_word() == oracle.next_word()


@pytest.mark.parametrize("rejection_index", [2, 49148, 49154])
def test_actual_batch_rejection_shifts_rows_without_redrawing(
    monkeypatch: Any, rejection_index: int
) -> None:
    # Use enlarged L1 geometry to cross the 8192-date boundary.
    item = study.StudySpec("L1", 16384, 2, False)
    values = [0] * (6 * study.source_length(item) + 32)
    limit = (1 << 64) // 50 * 50
    values[rejection_index] = limit

    def digest(prefix: bytes, counter: int) -> bytes:
        return b"".join(v.to_bytes(8, "big") for v in values[4 * counter : 4 * counter + 4])

    monkeypatch.setattr(study, "_counter_digest", digest)
    stream = _stream(item)
    oracle = _Words(values)
    assert study.generate_payload(item, stream) == study.generate_payload(item, oracle)
    assert stream.words_consumed == oracle.words_consumed
    assert stream.next_word() == oracle.next_word()


def test_actual_batch_rejection_limit_preserves_failed_row_state(monkeypatch: Any) -> None:
    item = study.spec("L1")
    values = [0, 0] + [(1 << 64) - 1] * 1024 + [23] * (6 * study.source_length(item))

    def digest(prefix: bytes, counter: int) -> bytes:
        return b"".join(v.to_bytes(8, "big") for v in values[4 * counter : 4 * counter + 4])

    monkeypatch.setattr(study, "_counter_digest", digest)
    stream = _stream(item)
    oracle = _Words(values)
    for source in (stream, oracle):
        with pytest.raises(study.StudyError, match="rejection_limit"):
            study.generate_payload(item, source)
        assert source.words_consumed == 1026
    assert stream.next_word() == oracle.next_word() == 23


def test_generator_overflow_consumes_partial_failed_row_identically() -> None:
    item = study.spec("P1")
    stream = _stream(item)
    stream._counter = (1 << 64) - 2
    assert stream.next_word() >= 0
    oracle = _IndependentStream(stream.prefix, counter=(1 << 64) - 2)
    oracle.next_word()
    for source in (stream, oracle):
        with pytest.raises(study.StudyError, match="counter_overflow"):
            study.generate_payload(item, source)
        assert source.words_consumed == 8


def test_numpy_version_is_bound_to_manifest(tmp_path: Path) -> None:
    import importlib.metadata

    assert _test_manifest(tmp_path).payload["libraries"]["numpy"] == importlib.metadata.version(
        "numpy"
    )


@pytest.mark.parametrize(
    "word,extra", [((1 << 64) - 17, 0), ((1 << 64) - 16, 1), ((1 << 64) - 1, 1)]
)
def test_uint64_acceptance_boundary_in_actual_batch(
    monkeypatch: Any, word: int, extra: int
) -> None:
    item = study.spec("L1")
    values = [i * 137 + 11 for i in range(6 * study.source_length(item) + 32)]
    values[2] = word

    def digest(prefix: bytes, counter: int) -> bytes:
        return b"".join(v.to_bytes(8, "big") for v in values[4 * counter : 4 * counter + 4])

    monkeypatch.setattr(study, "_counter_digest", digest)
    stream = _stream(item)
    oracle = _Words(values)
    assert study.generate_payload(item, stream) == study.generate_payload(item, oracle)
    assert stream.words_consumed == oracle.words_consumed == 6 * study.source_length(item) + extra
    assert stream.next_word() == oracle.next_word()


def test_custom_counter_subclass_never_enters_trusted_batch() -> None:
    class Custom(study.CounterStream):
        def __init__(self) -> None:
            self.words_consumed = 0

        def next_word(self) -> int:
            self.words_consumed += 1
            return 0

        def peek_words(self, count: int) -> bytes:
            pytest.fail("custom source trusted by batch")

    item = study.spec("P1")
    custom = Custom()
    assert study.generate_payload(item, custom) == bytes([31]) * study.source_length(item)
    assert custom.words_consumed == 6 * study.source_length(item)


def test_generator_refuses_output_budget_before_allocation_or_words() -> None:
    item = study.StudySpec("P1", study.MAX_BUFFER + 1, 2, True)
    words = _Words([])
    with pytest.raises(study.StudyError, match="payload_buffer_cap"):
        study.generate_payload(item, words)
    assert words.words_consumed == 0


def test_manifest_versions_are_fresh_single_lookups(tmp_path: Path, monkeypatch: Any) -> None:
    source = tmp_path / "source.py"
    source.write_bytes(b"bound source")
    calls: list[str] = []
    versions = {"psutil": "first-psutil", "numpy": "first-numpy"}

    def version(name: str) -> str:
        calls.append(name)
        return versions[name]

    monkeypatch.setattr(importlib.metadata, "version", version)
    first = study.manifest_for_paths({"source": source}, protocol_hash="b" * 64)
    assert calls == ["psutil", "numpy"]
    assert first.payload["libraries"] == versions
    versions = {"psutil": "next-psutil", "numpy": "next-numpy"}
    calls.clear()
    second = study.manifest_for_paths({"source": source}, protocol_hash="b" * 64)
    assert calls == ["psutil", "numpy"]
    assert second.payload["libraries"] == versions
    assert first.digest != second.digest


def test_manifest_missing_distribution_only_is_omitted(tmp_path: Path, monkeypatch: Any) -> None:
    source = tmp_path / "source.py"
    source.write_bytes(b"bound source")
    calls: list[str] = []

    def version(name: str) -> str:
        calls.append(name)
        if name == "psutil":
            raise importlib.metadata.PackageNotFoundError(name)
        return "present-numpy"

    monkeypatch.setattr(importlib.metadata, "version", version)
    result = study.manifest_for_paths({"source": source}, protocol_hash="b" * 64)
    assert result.payload["libraries"] == {"numpy": "present-numpy"}
    assert calls == ["psutil", "numpy"]


def test_manifest_unexpected_metadata_failure_propagates(tmp_path: Path, monkeypatch: Any) -> None:
    source = tmp_path / "source.py"
    source.write_bytes(b"bound source")

    def version(name: str) -> str:
        raise RuntimeError("metadata corruption")

    monkeypatch.setattr(importlib.metadata, "version", version)
    with pytest.raises(RuntimeError, match="metadata corruption"):
        study.manifest_for_paths({"source": source}, protocol_hash="b" * 64)


def test_operational_contract_is_explicit_and_gates_keep_legacy_comparison() -> None:
    resources = study.load_operational_resources()
    binding = resources.binding()
    assert binding["legacy_verifier_seconds"] == 43200
    assert binding["effective_verifier_seconds"] == 50400
    comparison = resources.compare(2 * 8192 * 0.70, 2 * 32768 * 0.70)
    assert comparison["legacy_validation_eligible"] is False
    assert comparison["effective_validation_eligible"] is True
    for seconds, old, new in (
        (43200.0, True, True),
        (43200.0001, False, True),
        (50400.0, False, True),
        (50400.0001, False, False),
    ):
        actual = resources.compare(seconds, seconds)
        assert actual["legacy_validation_eligible"] is old
        assert actual["effective_validation_eligible"] is new


@pytest.mark.parametrize(
    "damage",
    [
        "missing",
        "oversize",
        "noncanonical",
        "duplicate",
        "unknown",
        "schema_bool",
        "sequence_bool",
        "seconds_bool",
        "baseline",
        "predecessor",
        "effective",
        "third",
        "ack",
        "timestamp",
        "evidence",
        "pin",
    ],
)
def test_operational_contract_refuses_corruption(tmp_path: Path, damage: str) -> None:
    source = study.PROJECT / "docs/plans/calendar-score-operational-resources.json"
    path = tmp_path / "contract.json"
    blob = source.read_bytes()
    value = json.loads(blob)
    if damage == "missing":
        pass
    elif damage == "oversize":
        path.write_bytes(b"x" * 16385)
    elif damage == "noncanonical":
        path.write_bytes(json.dumps(value).encode() + b"\n")
    elif damage == "duplicate":
        path.write_bytes(blob.replace(b'{"effective_id":', b'{"schema":1,"effective_id":', 1))
    else:
        if damage == "unknown":
            value["extra"] = 1
        elif damage == "schema_bool":
            value["schema"] = True
        elif damage == "sequence_bool":
            value["history"][1]["sequence"] = True
        elif damage == "seconds_bool":
            value["history"][1]["verifier_seconds"] = True
        elif damage == "baseline":
            value["history"][0]["verifier_seconds"] = 50400
        elif damage == "predecessor":
            value["history"][1]["predecessor_sha256"] = "0" * 64
        elif damage == "effective":
            value["effective_id"] = "unapproved"
        elif damage == "third":
            value["history"].append(dict(value["history"][1]))
        elif damage == "ack":
            value["history"][1]["acknowledged_post_hoc"] = False
        elif damage == "timestamp":
            value["history"][1]["amended_at_utc"] = "2026-10-04"
        elif damage == "evidence":
            value["history"][1]["evidence"][0]["path"] = "../outside"
        elif damage == "pin":
            value["history"][1]["amended_at_utc"] = "2026-10-04T17:14:01Z"
        # Rehash malicious history: internal consistency must not authorize edits.
        for entry in value["history"]:
            entry["entry_sha256"] = hashlib.sha256(
                study.canonical_json({k: v for k, v in entry.items() if k != "entry_sha256"})
            ).hexdigest()
        path.write_bytes(study.canonical_json(value))
    expected = hashlib.sha256(path.read_bytes()).hexdigest() if path.exists() else "0" * 64
    if damage == "pin":
        expected = hashlib.sha256(blob).hexdigest()
    with pytest.raises(study.StudyError, match="resource_contract"):
        study._load_operational_resources(path, expected_sha256=expected)


def test_operational_contract_is_fresh_and_missing_has_no_fallback(
    tmp_path: Path, monkeypatch: Any
) -> None:
    path = tmp_path / "contract.json"
    path.write_bytes(
        (study.PROJECT / "docs/plans/calendar-score-operational-resources.json").read_bytes()
    )
    monkeypatch.setattr(study, "RESOURCE_PATH", path)
    assert study.load_operational_resources().effective_verifier_seconds == 50400
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(study.StudyError, match="resource_contract"):
        study.load_operational_resources()


def test_preflight_missing_policy_after_root_creation_is_durable_error(
    tmp_path: Path, monkeypatch: Any
) -> None:
    root = tmp_path / "new-root"
    manifest = _test_manifest(tmp_path / "manifest")
    plan = study.test_preflight_plan(root, (study.spec("P1"),))
    monkeypatch.setattr(study, "RESOURCE_PATH", tmp_path / "missing.json")
    with pytest.raises(study.StudyError, match="resource_contract"):
        study.run_supervised_preflight(root, plan=plan, manifest=manifest)
    failure = json.loads((root / "preflight-failure.json").read_bytes())
    assert failure["operational_resources"] is None
    assert failure["resource_contract_error"] is True
    assert not (root / "preflight-receipt.json").exists()


@pytest.mark.parametrize("value", [True, -1.0, float("nan"), float("inf"), 1 << 4096])
def test_operational_projection_invalid_values_refuse(value: Any) -> None:
    with pytest.raises(study.StudyError, match="invalid_resource_projection"):
        study.load_operational_resources().compare(value, 0.0)


def test_operational_evidence_source_drift_is_rechecked(monkeypatch: Any) -> None:
    original = Path.open

    def drift(path: Path, *args: Any, **kwargs: Any) -> Any:
        if path.name == "2026-10-04-calendar-score-verifier-optimization-2-benchmarks.json":
            raise OSError("changed evidence source")
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "open", drift)
    with pytest.raises(study.StudyError, match="resource_contract"):
        study.load_operational_resources()


@pytest.mark.parametrize(
    "damage", ["verification", "generation", "count_bool", "eligible_int", "rss", "disk"]
)
def test_rehashed_preflight_composite_eligibility_is_not_trusted(
    tmp_path: Path, damage: str
) -> None:
    root = tmp_path / "evidence"
    manifest = _test_manifest(tmp_path / "manifest")
    plan = study.test_preflight_plan(root, (study.spec("P1"),))
    receipt = study.execute_preflight(plan, manifest)
    assert receipt.eligible
    row = json.loads((root / "preflight-receipt.json").read_bytes())
    if damage == "verification":
        row["replay_seconds"] = 60000.0 / (2 * 32768)
        row["projected_development_verify_seconds"] = 15000.0
        row["projected_validation_verify_seconds"] = 60000.0
        row["verification_budget_comparison"] = study.load_operational_resources().compare(
            15000.0, 60000.0
        )
    elif damage == "generation":
        row["generation_seconds"] = 30000.0 / (2 * 8192)
        row["projected_development_seconds"] = 30000.0
        row["projected_validation_seconds"] = 120000.0
    elif damage == "count_bool":
        row["generated_paths"] = True
    elif damage == "eligible_int":
        row["eligible"] = 1
    elif damage == "rss":
        row["peak_rss_bytes"] = study.WORKER_RSS_CAP + 1
    elif damage == "disk":
        row["free_disk_bytes"] = 0
    row["digest"] = hashlib.sha256(
        study.canonical_json(
            {k: v for k, v in row.items() if k not in ("digest", "resource_disclosure")}
        )
    ).hexdigest()
    (root / "preflight-receipt.json").write_bytes(study.canonical_json(row))
    with pytest.raises(study.StudyError):
        study._read_preflight_receipt(root, manifest, plan=plan)


@pytest.mark.parametrize("damage", ["missing", "corrupt", "drift"])
def test_direct_preflight_contract_error_is_durable_after_root_guard(
    tmp_path: Path, monkeypatch: Any, damage: str
) -> None:
    root = tmp_path / "evidence"
    manifest = _test_manifest(tmp_path / "manifest")
    captured = study.load_operational_resources().binding()
    plan = study.test_preflight_plan(root, (study.spec("P1"),))
    path = tmp_path / "policy.json"
    if damage == "corrupt":
        path.write_bytes(b"broken")
    if damage in ("missing", "corrupt"):
        monkeypatch.setattr(study, "RESOURCE_PATH", path)
    else:

        def drift(*args: Any, **kwargs: Any) -> Any:
            monkeypatch.setattr(study, "RESOURCE_PATH", path)
            raise study.StudyError("resource_contract_drift")

        monkeypatch.setattr(study, "generate_payload", drift)
    with pytest.raises(study.StudyError, match="resource_contract"):
        study.execute_preflight(plan, manifest)
    row = json.loads((root / "preflight-failure.json").read_bytes())
    assert row["operational_resources"] == (captured if damage == "drift" else None)
    assert row["resource_contract_error"] is (damage != "drift")
    assert not (root / "preflight-receipt.json").exists()


def test_preflight_receipt_reader_recomputes_valid_plan_and_counts(tmp_path: Path) -> None:
    root = tmp_path / "evidence"
    manifest = _test_manifest(tmp_path / "manifest")
    plan = study.test_preflight_plan(root, (study.spec("P1"),))
    expected = study.execute_preflight(plan, manifest)
    assert study._read_preflight_receipt(root, manifest, plan=plan) == expected
    with pytest.raises(study.StudyError, match="preflight_receipt_plan"):
        study._read_preflight_receipt(root, manifest)


@pytest.mark.parametrize("failure", ["exists", "binding", "poll", "kill"])
def test_supervised_failure_secondary_errors_preserve_original_and_attempt_evidence(
    tmp_path: Path, monkeypatch: Any, failure: str
) -> None:
    root = tmp_path / "supervised"
    manifest = _test_manifest(tmp_path / "manifest")
    plan = study.test_preflight_plan(root, (study.spec("P1"),))
    original_error = study.StudyError("original_refusal")

    class Process:
        pid = -1

        def poll(self) -> int | None:
            if failure == "poll":
                raise OSError("poll denied")
            return None if failure == "kill" else 0

    monkeypatch.setattr(subprocess, "Popen", lambda *args, **kwargs: Process())

    def kill(process: Any) -> None:
        if failure == "kill":
            raise OSError("kill denied")

    monkeypatch.setattr(study, "_kill_tree", kill)
    original_exists = Path.exists

    def supervise(*args: Any) -> Any:
        if failure == "exists":

            def denied(path: Path) -> bool:
                if path.name == "preflight-failure.json":
                    raise OSError("failure existence denied")
                return original_exists(path)

            monkeypatch.setattr(Path, "exists", denied)
        elif failure == "binding":

            def denied_binding(self: Any) -> Any:
                raise OSError("failure binding denied")

            monkeypatch.setattr(study.OperationalResources, "binding", denied_binding)
        raise original_error

    monkeypatch.setattr(study, "_supervise_preflight", supervise)
    with pytest.raises(study.StudyError) as caught:
        study.run_supervised_preflight(root, plan=plan, manifest=manifest)
    assert caught.value is original_error
    assert original_error.__notes__
    assert not (root / "preflight-receipt.json").exists()
    if failure in ("poll", "kill"):
        failure_record = json.loads((root / "preflight-failure.json").read_bytes())
        assert failure_record["reason"] == "original_refusal"
        assert failure_record["state"] == "ERROR"
