"""Real research IO must retain failure and refuse phase/source substitution."""

import hashlib
import os
import subprocess
from pathlib import Path

import pytest
from scripts.research import signal_calendar_laws as laws
from scripts.research import signal_calendar_runner as m
from scripts.research import signal_calendar_uncertainty as calendar


def test_claim_is_exclusive_and_preserves_original_manifest(tmp_path: Path) -> None:
    destination = tmp_path / "attempt"
    m.claim(destination, {"phase": "development", "root": "fixture"}, root=tmp_path)
    original = (destination / "claim.json").read_bytes()
    with pytest.raises(FileExistsError):
        m.claim(destination, {"phase": "confirmation"}, root=tmp_path)
    assert (destination / "claim.json").read_bytes() == original


def test_claim_refuses_escape_before_writes(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        m.claim(tmp_path.parent / "outside", {}, root=tmp_path)
    assert not (tmp_path.parent / "outside").exists()


def test_source_mismatch_refuses_before_atom_construction() -> None:
    manifest = m.source_manifest()
    manifest["protocol"] = "wrong"
    with pytest.raises(ValueError):
        m.check_sources(manifest)


def test_counter_atom_mapping_checks_seed_and_exact_support() -> None:
    with pytest.raises(ValueError):
        m.Atoms(b"short", "development", "P1:64", 0)
    with pytest.raises(ValueError):
        m.Atoms(bytes(32), "real", "P1:64", 0)
    # Deterministic byte-mapping characterization, not a stochastic experiment.
    atoms = m.Atoms(bytes(32), "development", "P1:64", 0)
    assert all(0 <= atoms.uniform(50) < 50 for _ in range(100))
    assert atoms.words >= 100


def test_bounded_writer_rejects_before_crossing_cap(tmp_path: Path) -> None:
    with m.EvidenceWriter(tmp_path / "rows.jsonl", cap=20) as writer:
        writer.write({"a": 1})
        before = writer.bytes_written
        with pytest.raises(ValueError):
            writer.write({"long": "x" * 50})
        assert writer.bytes_written == before
    assert (tmp_path / "rows.jsonl").stat().st_size == before


def test_failed_development_cannot_issue_confirmation_authority() -> None:
    with pytest.raises(ValueError):
        m.confirmation_permission({"complete": True, "passed": False}, {})
    with pytest.raises(ValueError):
        m.confirmation_permission({"complete": False, "passed": True}, {})


def test_oversized_geometry_refuses_preflight_not_silently_changed() -> None:
    assert not m.geometry_ready("P7", 192)
    assert m.geometry_ready("P7", 128)


def test_fixed_byte_evidence_cannot_become_real_market_eligible() -> None:
    assert m.source_manifest()["scope"] == "synthetic_only"


def test_evaluate_integrates_actual_law_and_calculator_original_sum() -> None:
    from fractions import Fraction

    from scripts.research import signal_calendar_laws as laws

    family = laws.PathFamily(
        "P2",
        64,
        (calendar.Metric.RAW, calendar.Metric.WIN, calendar.Metric.SYNTHETIC_EXCESS),
        True,
    )
    path = m._path(family, None)
    fixture = laws.build(family.profile_id, family.n, path)
    results = m.evaluate(family, path)
    raw = results[0]
    expected = sum((Fraction(record.raw) for record in fixture.source.records), Fraction(0))
    assert raw["count"] == 128
    assert Fraction(raw["sum"]) == expected
    assert Fraction(raw["mean"]) == expected / 128
    assert tuple(item["metric"] for item in results) == ("raw", "win", "synthetic_excess")
    assert tuple(item["truth"] for item in results) == ("0", "7/12", "-1/200")


def test_full_support_encode_decode_replays_every_registered_family() -> None:
    for family in laws.path_families():
        original = m._path(family, None)
        encoded = m.encode_path(family, original)
        reconstructed = m.decode_path(family, encoded)
        assert reconstructed == original
        assert m.evaluate(family, reconstructed) == m.evaluate(family, original)


@pytest.mark.parametrize("encoded", ["00", "gg", "ff" * 66, "00" * 5000])
def test_malformed_span_atom_or_unbounded_path_encoding_refuses(encoded: str) -> None:
    family = laws.path_families()[0]
    with pytest.raises(ValueError):
        m.decode_path(family, encoded)


def test_replay_rejects_changed_result_and_duplicate_replicate_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json

    family = laws.path_families()[0]
    monkeypatch.setattr(laws, "path_families", lambda: (family,))
    monkeypatch.setitem(m.REPLICATES, "development", 2)
    seed = bytes(32)
    atoms = m.Atoms(seed, "development", f"{family.profile_id}:{family.n}", 0)
    path = m._path(family, atoms)
    (tmp_path / "claim.json").write_bytes(
        m.canonical(
            {
                "phase": "development",
                "source": m.source_manifest(),
                "seed": seed.hex(),
                "seed_commitment": hashlib.sha256(seed).hexdigest(),
            }
        )
    )
    row = {
        "family": family.profile_id,
        "n": family.n,
        "replicate": 0,
        "path": m.encode_path(family, path),
        "words": atoms.words,
        "results": m.pack_results(m.evaluate(family, path)),
    }
    evidence = tmp_path / "paths.jsonl"
    evidence.write_bytes(m.canonical(row) + m.canonical(row))
    with pytest.raises(ValueError, match="duplicate/omitted/reordered"):
        m.verify(tmp_path, "development", m.source_manifest())
    changed = json.loads(m.canonical(row))
    changed["results"][0]["count"] += 1
    evidence.write_bytes(m.canonical(changed))
    with pytest.raises(ValueError, match="source result replay mismatch"):
        m.verify(tmp_path, "development", m.source_manifest())


def test_missing_or_truncated_evidence_never_becomes_complete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    family = laws.path_families()[0]
    monkeypatch.setattr(laws, "path_families", lambda: (family,))
    monkeypatch.setitem(m.REPLICATES, "development", 1)
    (tmp_path / "claim.json").write_bytes(
        m.canonical(
            {
                "phase": "development",
                "source": m.source_manifest(),
                "seed": bytes(32).hex(),
                "seed_commitment": hashlib.sha256(bytes(32)).hexdigest(),
            }
        )
    )
    with pytest.raises(FileNotFoundError):
        m.verify(tmp_path, "development", m.source_manifest())
    (tmp_path / "paths.jsonl").write_bytes(b"")
    with pytest.raises(ValueError, match="incomplete/unbounded"):
        m.verify(tmp_path, "development", m.source_manifest())


def test_writer_propagates_fsync_failure_and_closes_evidence(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:

    def failed_fsync(descriptor: int) -> None:
        raise OSError("invented persistence failure")

    monkeypatch.setattr(os, "fsync", failed_fsync)
    writer = m.EvidenceWriter(tmp_path / "rows.jsonl")
    with pytest.raises(OSError, match="persistence failure"):
        with writer:
            writer.write({"record": "retained-before-failed-sync"})
    assert writer.stream is not None and writer.stream.closed
    assert (tmp_path / "rows.jsonl").read_bytes() == m.canonical(
        {"record": "retained-before-failed-sync"}
    )


def test_source_change_and_infeasibility_stop_before_attempt_claim(tmp_path: Path) -> None:
    from dataclasses import replace

    manifest = m.source_manifest()
    feasibility = m.Feasibility(manifest, 1.0, 1024, 100.0, 1024, 1, False)
    with pytest.raises(ValueError, match="infeasible"):
        m.run_phase(tmp_path / "no-claim", "development", bytes(32), feasibility)
    assert not (tmp_path / "no-claim").exists()
    invalid = replace(feasibility, manifest={**manifest, "protocol": "different"}, eligible=True)
    with pytest.raises(ValueError, match="source/environment mismatch"):
        m.run_phase(tmp_path / "no-claim", "development", bytes(32), invalid)
    assert not (tmp_path / "no-claim").exists()


def test_supervisor_timeout_retains_error_and_prevents_resume(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import json
    from typing import Any

    original_claim = m.claim

    def claim_in_test(destination: Path, manifest: dict[str, Any]) -> None:
        original_claim(destination, manifest, root=tmp_path)

    class Process:
        alive = True
        pid = 12345
        returncode = None

        def poll(self) -> int | None:
            return None if self.alive else 1

        def kill(self) -> None:
            self.alive = False

        def wait(self, timeout: int) -> int:
            if self.alive:
                raise TimeoutError("test process still active")
            return 1

    def launch(*args: object, **kwargs: object) -> Process:
        return Process()

    monkeypatch.setattr(m, "claim", claim_in_test)
    monkeypatch.setattr(m, "ROOT", tmp_path)
    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setitem(m.DEADLINES, "development", 0.0)
    manifest = m.source_manifest()
    feasibility = m.Feasibility(manifest, 1.0, 1024, 100.0, 1024, 1, True, m._MEASURED)
    destination = tmp_path / "timed-out-attempt"
    with pytest.raises(TimeoutError, match="parent research deadline"):
        m.run_phase(destination, "development", bytes(32), feasibility)
    assert (destination / "claim.json").exists()
    assert json.loads((destination / "error.json").read_bytes())["state"] == "ERROR"
    assert not (destination / "terminal.json").exists()
    with pytest.raises(FileExistsError):
        m.run_phase(destination, "development", bytes(32), feasibility)
    with pytest.raises(FileExistsError):
        m.run_phase(tmp_path / "different-destination", "development", bytes(32), feasibility)
    assert (tmp_path / "different-destination" / "error.json").exists()
    monkeypatch.setitem(m.DEADLINES, "confirmation", 0.0)
    first_seed, second_seed = bytes([1]) * 32, bytes([2]) * 32
    for index, seed in enumerate((first_seed, second_seed)):
        authority = m._Confirmation(
            manifest, m._AUTHORITY, "a" * 64, hashlib.sha256(seed).hexdigest()
        )
        destination = tmp_path / f"confirmation-{index}"
        expected = TimeoutError if index == 0 else FileExistsError
        with pytest.raises(expected):
            m.run_phase(destination, "confirmation", seed, feasibility, authority=authority)
        assert (destination / "error.json").exists()


def test_confirmation_requires_live_verified_authority_before_claim(tmp_path: Path) -> None:
    feasibility = m.Feasibility(m.source_manifest(), 1.0, 1024, 100.0, 1024, 1, True, m._MEASURED)
    with pytest.raises(ValueError, match="no live verified development authority"):
        m.run_phase(tmp_path / "confirmation", "confirmation", bytes(32), feasibility)
    assert not (tmp_path / "confirmation").exists()


def test_plain_pass_dictionary_cannot_issue_confirmation_authority() -> None:
    with pytest.raises(ValueError):
        m.confirmation_permission({"complete": True, "passed": True}, m.source_manifest())


def test_replay_alone_cannot_authorize_confirmation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(laws, "path_families", lambda: ())
    manifest = m.source_manifest()
    (tmp_path / "claim.json").write_bytes(
        m.canonical(
            {
                "phase": "development",
                "source": manifest,
                "seed": bytes(32).hex(),
                "seed_commitment": hashlib.sha256(bytes(32)).hexdigest(),
            }
        )
    )
    (tmp_path / "paths.jsonl").write_bytes(b"")
    replay = m.verify(tmp_path, "development", manifest)
    with pytest.raises(ValueError, match="failed/incomplete"):
        m.confirmation_permission(replay, manifest, confirmation_commitment="1" * 64)


def test_verifier_requires_claimed_seed_before_replaying_evidence(tmp_path: Path) -> None:
    family = laws.path_families()[0]
    path = m._path(family, None)
    row = {
        "family": family.profile_id,
        "n": family.n,
        "replicate": 0,
        "path": m.encode_path(family, path),
        "words": 0,
        "results": m.pack_results(m.evaluate(family, path)),
    }
    (tmp_path / "paths.jsonl").write_bytes(m.canonical(row))
    with pytest.raises((ValueError, FileNotFoundError), match=r"claim|seed"):
        m.verify(tmp_path, "development", m.source_manifest())


def test_lossless_decimal_encoding_retains_all_digits_and_signed_zero() -> None:
    from decimal import Decimal

    values = ["-0.000", "1E+20", "-0.123456789012345678901234567890", "3.000"]
    for value in values:
        restored = m.unpack_decimal(m.pack_decimal(value))
        assert Decimal(restored).as_tuple() == Decimal(value).as_tuple()
        assert restored == value


def test_result_compaction_preserves_required_fields_and_refusal() -> None:
    family = laws.path_families()[0]
    result = m.evaluate(family, m._path(family, None))
    assert m.unpack_results(m.pack_results(result)) == result


def test_counter_stream_uses_all_four_words_and_replays_exact_lane_order() -> None:
    atoms = m.Atoms(bytes(32), "development", "P1:64", 0)
    block = hashlib.sha256(atoms.prefix + bytes(8)).digest()
    expected = [int.from_bytes(block[i : i + 8], "big") % 512 for i in (0, 8, 16, 24)]
    assert [atoms.uniform(512) for _ in range(4)] == expected
    assert atoms.words == 4


def test_preflight_inventions_cover_every_metric_and_match_reference() -> None:
    for family in laws.path_families():
        witnessed: set[str] = set()
        for pattern in range(4):
            path = m._path(family, None, pattern=pattern)
            result = m.evaluate(family, path)
            assert result == m.evaluate_reference(family, path)
            witnessed.update(r["metric"] for r in result if r["lower"] is not None)
        assert witnessed == {metric.value for metric in family.metrics}
