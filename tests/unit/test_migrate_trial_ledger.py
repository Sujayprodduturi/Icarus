"""The legacy migration command validates locally and never guesses a database."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from scripts import migrate_trial_ledger


def test_check_reports_only_validated_metadata(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    source = tmp_path / "legacy.json"
    source.write_text('{"schema":1,"trials":[]}', encoding="utf-8")

    assert migrate_trial_ledger.main(["--check", "--source", str(source)]) == 0

    report = json.loads(capsys.readouterr().out)
    assert report == {
        "legacy_entry_count": 0,
        "legacy_schema": 1,
        "legacy_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
    }


def test_apply_requires_an_explicit_database_dsn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "legacy.json"
    source.write_text('{"schema":1,"trials":[]}', encoding="utf-8")
    monkeypatch.delenv("ICARUS_PG_DSN", raising=False)

    with pytest.raises(SystemExit, match="ICARUS_PG_DSN"):
        migrate_trial_ledger.main(["--apply", "--source", str(source)])
