"""Safety tests for the synthetic-only uncertainty research experiment."""

from collections.abc import Sequence
from pathlib import Path

import pytest
from scripts.research import signal_method_probe as probe
from scripts.research.signal_uncertainty import Estimate, Refusal


def test_reserved_seed_and_wrong_root_refuse_before_io(tmp_path: Path) -> None:
    for seed in (2026092602, 2026092603, 42):
        with pytest.raises(ValueError):
            probe.guard(seed, tmp_path / "uncreated")
    assert not (tmp_path / "uncreated").exists()
    with pytest.raises(ValueError):
        probe.guard(probe.SEED, Path("docs/reviews/step6a2/forbidden"))


def test_duplicate_bad_axis_and_missing_pair() -> None:
    trade = probe.Trade("a", 0, 1, 0.01, 0.002)
    with pytest.raises(ValueError):
        probe.observations((trade, trade), 63, 126)
    with pytest.raises(ValueError):
        probe.observations((probe.Trade("a", 126, 1, 0.01, 0.002),), 63, 126)
    cohort = probe.observations((probe.Trade("a", 0, 1, -0.01, None),), 63, 126)
    assert cohort["win"] == (0.0,)
    assert cohort["synthetic_excess"] is None
    assert cohort["raw"] == (-0.01,)


def test_targets_only_change_evaluation() -> None:
    first = probe.Counts()
    second = probe.Counts()
    first.add((-1.0, 1.0), 0.0, 0.0, "EMITTED", "win")
    second.add((-1.0, 1.0), 0.0, 2.0, "EMITTED", "win")
    assert first.coverage == 1
    assert second.upper_miss == 1
    assert first.widths == second.widths
    first.add(None, None, 0.0, "ZERO_VARIANCE", "win")
    assert first.generated == first.emitted + sum(first.refusals.values())
    assert first.emitted == first.coverage + first.lower_miss + first.upper_miss


def test_noninformative_is_candidate_level() -> None:
    full = probe.Counts()
    full.add((-0.5, 1.5), 0.5, 0.5, "EMITTED", "win")
    assert full.full_range == 1
    assert probe.noninformative((full,))
    mixed = probe.Counts()
    mixed.add((0.4, 0.6), 0.5, 0.5, "EMITTED", "win")
    assert not probe.noninformative((full, mixed))
    with pytest.raises(ValueError):
        mixed.add((float("-inf"), float("inf")), 0.5, 0.5, "EMITTED", "win")


def test_exclusive_attempt_is_not_overwritten(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    run = tmp_path / "attempt"
    probe.reserve(run, {"seed": probe.SEED})
    with pytest.raises(FileExistsError):
        probe.reserve(run, {"seed": probe.SEED})
    assert (run / "preregister.json").exists()


def test_timeout_records_failure(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(probe, "ROOT", tmp_path)
    monkeypatch.setattr(probe, "DEADLINE", 0.05)
    with pytest.raises(RuntimeError):
        probe.supervise(tmp_path / "timeout", ["python", "-c", "import time; time.sleep(2)"])
    assert '"TIMEOUT"' in (tmp_path / "timeout" / "ledger.jsonl").read_text()
    assert not (tmp_path / "timeout" / "result.json").exists()


def test_nonzero_exit_and_spawn_error_are_retained(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    monkeypatch.setattr(probe, "ROOT", tmp_path)
    with pytest.raises(RuntimeError):
        probe.supervise(tmp_path / "error", [sys.executable, "-c", "raise SystemExit(7)"])
    assert '"ERROR"' in (tmp_path / "error" / "ledger.jsonl").read_text()
    with pytest.raises(OSError):
        probe.supervise(tmp_path / "spawn", [str(tmp_path / "missing-executable")])
    assert '"ERROR"' in (tmp_path / "spawn" / "ledger.jsonl").read_text()


def test_success_without_complete_evidence_refuses(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import sys

    monkeypatch.setattr(probe, "ROOT", tmp_path)
    with pytest.raises(FileNotFoundError):
        probe.supervise(tmp_path / "empty", [sys.executable, "-c", "pass"])
    assert '"ERROR"' in (tmp_path / "empty" / "ledger.jsonl").read_text()


def test_candidate_cannot_receive_targets(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[object] = []
    original = probe.estimate

    def spy(
        values: Sequence[float], block_ids: Sequence[int], *, first_block: int, last_block: int
    ) -> Estimate | Refusal:
        captured.append((values, block_ids, first_block, last_block))
        return original(values, block_ids, first_block=first_block, last_block=last_block)

    monkeypatch.setattr(probe, "estimate", spy)
    trades = tuple(probe.Trade(str(i), i * 63, 1, float(i % 3) / 100, 0.002) for i in range(24))
    for target in (0.0, 100.0):
        counts = {
            m: {k: probe.Counts() for k in probe.METRICS} for m in ("original_cr2", "candidate")
        }
        probe._evaluate(trades, 63, 24 * 63, dict.fromkeys(probe.METRICS, target), counts)
    assert captured[:3] == captured[3:]


def test_failed_checkpoint_replace_preserves_previous(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    checkpoint = tmp_path / "result.json"
    probe._json(checkpoint, {"completed": 256})

    def denied(source: Path, target: Path) -> None:
        raise PermissionError("injected replacement failure")

    import os

    monkeypatch.setattr(os, "replace", denied)
    with pytest.raises(PermissionError):
        probe._json(checkpoint, {"completed": 512})
    assert "256" in checkpoint.read_text()


def test_spawn_sees_preregister_and_ledger_then_reaps(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import subprocess

    monkeypatch.setattr(probe, "ROOT", tmp_path)
    run = tmp_path / "reap"
    events: list[str] = []

    class FakeProcess:
        dead = False

        def wait(self, timeout: float | None = None) -> int:
            if timeout is not None:
                assert (run / "preregister.json").exists()
                assert '"STARTED"' in (run / "ledger.jsonl").read_text()
                raise subprocess.TimeoutExpired("test", timeout)
            events.append("joined")
            return 0

        def poll(self) -> int | None:
            return 0 if self.dead else None

        def kill(self) -> None:
            self.dead = True
            events.append("killed")

    def spawn(*args: object, **kwargs: object) -> FakeProcess:
        return FakeProcess()

    protocol = probe._protocol()
    monkeypatch.setattr(probe, "_protocol", lambda: protocol)
    monkeypatch.setattr(subprocess, "Popen", spawn)
    with pytest.raises(RuntimeError):
        probe.supervise(run, ["unused"])
    assert events == ["killed", "joined"]


def test_worker_launch_owns_real_interpreter_and_venv() -> None:
    import json
    import os
    import subprocess
    import sys

    import numpy as np
    import scipy

    executable, environment = probe._python_launch()
    command = (
        "import json,os,sys,numpy,scipy;"
        "print(json.dumps([os.getpid(),os.getppid(),sys.prefix,"
        "numpy.__version__,scipy.__version__]))"
    )
    child = subprocess.Popen(
        [executable, "-c", command], env=environment, stdout=subprocess.PIPE, text=True
    )
    try:
        output, _ = child.communicate(timeout=10)
    finally:
        if child.poll() is None:
            child.kill()
            child.wait()
    assert child.returncode == 0
    identity = json.loads(output)
    assert identity[:2] == [child.pid, os.getpid()]
    assert identity[2:] == [sys.prefix, np.__version__, scipy.__version__]
