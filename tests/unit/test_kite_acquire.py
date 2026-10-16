from __future__ import annotations

import csv
import getpass
import hashlib
import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import tools.kite_acquire.acquire as acquire
from tools.kite_acquire.acquire import (
    AuthFailure,
    KiteClient,
    LegacyTokenRoute,
    Request,
    SchemaFailure,
    _chunks,
    _resolve,
    _validate_historical,
    _validate_legacy_tokens_not_current,
    archive_response,
    legacy_manifest_sha256,
    load_checkpoint,
    parse_callback_token,
    urllib_transport,
    validate_legacy_token_file,
    validate_provenance,
    validate_range,
    validate_symbol_file,
)
from tools.kite_acquire.proxy import proxy_decision

LEGACY_EVIDENCE_URL = "https://kite.trade/forum/discussion/comment/9169/"


def _legacy_route(token: object = 340481) -> dict[str, object]:
    return {
        "requested_label": "HDFC",
        "historical_tradingsymbol": "HDFC",
        "historical_instrument_token": token,
        "provider_evidence_date": "2017-11",
        "provider_evidence_url": LEGACY_EVIDENCE_URL,
        "provider_evidence_observation": "The forum record publishes HDFC;340481.",
        "nse_2022_12_30_series": "EQ",
        "nse_2022_12_30_isin": "INE001A01036",
        "pilot_disposition": ["CONDITIONAL_QUALIFIES"] * 5,
        "route_status": "COLLECTION_CANDIDATE_ONLY",
        "identity_status": "UNKNOWN",
        "token_continuity": "UNKNOWN",
    }


def _write_legacy_manifest(tmp_path: Path, token: object = 340481) -> Path:
    path = tmp_path / "legacy.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "status": "EXPLICIT_LEGACY_TOKEN_CANDIDATES_NOT_IDENTITY_PROOF",
                "as_of_date": "2026-10-16",
                "scope": "metadata routing for the bounded 2022 pilot and its warmup only",
                "routes": [_legacy_route(token)],
                "limits": ["candidate only"],
            }
        ),
        encoding="utf-8",
    )
    return path


def _write_download_inputs(
    tmp_path: Path,
    symbols: list[str],
    *,
    classification: str = "REQUESTED_NOT_CERTIFIED_PIT",
) -> tuple[Path, Path]:
    symbols_path = tmp_path / "symbols.txt"
    symbols_path.write_text("\n".join(symbols) + "\n", encoding="utf-8")
    provenance_path = tmp_path / "provenance.json"
    decoded_member: dict[str, object] = {"name": "symbols.npy", "sha256": "b" * 64}
    if classification == "CURRENT_SERIES_RETRIEVAL_CANDIDATES_NOT_IDENTITY_PROOF":
        evidence_path = tmp_path / "series-evidence.json"
        evidence_path.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "status": "CURRENT_SERIES_RETRIEVAL_CANDIDATES_ONLY",
                    "as_of_date": "2026-10-16",
                    "routes": [
                        {
                            "requested_label": "HFCL",
                            "retrieval_symbol": "HFCL-BE",
                            "current_instrument_token": 5620225,
                            "current_exchange_token": 21954,
                            "current_exchange": "NSE",
                            "current_series": "BE",
                            "current_instrument_type": "EQ",
                            "current_isin": "INE548A01028",
                            "nse_2022_12_30_symbol": "HFCL",
                            "nse_2022_12_30_series": "EQ",
                            "nse_2022_12_30_isin": "INE548A01028",
                            "route_status": "COLLECTION_CANDIDATE_ONLY",
                            "series_continuity": "UNKNOWN",
                            "token_continuity": "UNKNOWN",
                        }
                    ],
                    "source": {"path": "receipt.json", "sha256": "c" * 64},
                    "limits": ["candidate only"],
                }
            ),
            encoding="utf-8",
        )
        decoded_member = {
            "path": evidence_path.name,
            "sha256": hashlib.sha256(evidence_path.read_bytes()).hexdigest(),
            "status": "CURRENT_SERIES_RETRIEVAL_CANDIDATES_ONLY",
        }
    provenance_path.write_text(
        json.dumps(
            {
                "output": {"sha256": hashlib.sha256(symbols_path.read_bytes()).hexdigest()},
                "classification": classification,
                "source": {"path": "panel.npz", "sha256": "a" * 64},
                "decoded_member": decoded_member,
            }
        ),
        encoding="utf-8",
    )
    return symbols_path, provenance_path


def _main_args(
    tmp_path: Path,
    symbols_path: Path,
    provenance_path: Path,
    *,
    run_id: str,
) -> list[str]:
    return [
        "--mode",
        "download",
        "--symbols-file",
        str(symbols_path),
        "--provenance",
        str(provenance_path),
        "--export",
        str(tmp_path / "export"),
        "--run-id",
        run_id,
        "--history-start",
        "2022-11-29",
        "--history-end",
        "2022-12-30",
    ]


def _instrument_master(*, collision: bool = False, include_be: bool = False) -> bytes:
    header = (
        "instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,"
        "tick_size,lot_size,instrument_type,segment,exchange\n"
    )
    rows = [
        "408065,1594,INFY,Infosys,0,,0,0.05,1,EQ,NSE,NSE",
        "256265,1001,NIFTY 50,NIFTY 50,0,,0,0.05,1,EQ,INDICES,NSE",
    ]
    if collision:
        rows.append("340481,1329,SOMEOTHER,Some Other,0,,0,0.05,1,EQ,NSE,NSE")
    if include_be:
        rows.append("5620225,21954,HFCL-BE,HFCL,0,,0,0.05,1,EQ,NSE,NSE")
    return (header + "\n".join(rows) + "\n").encode()


def _valid_candles() -> bytes:
    return (
        b'{"status":"success","data":{"candles":[["2022-12-28T09:15:00+05:30",100,110,90,105,10]]}}'
    )


class _InteractiveInput:
    @staticmethod
    def isatty() -> bool:
        return True


class _NonInteractiveInput:
    @staticmethod
    def isatty() -> bool:
        return False


def _install_fake_auth(monkeypatch: pytest.MonkeyPatch, transport: Any) -> None:
    answers = iter(("api-key", "api-secret", "request-token"))
    monkeypatch.setattr(sys, "stdin", _InteractiveInput())
    monkeypatch.setattr(getpass, "getpass", lambda _: next(answers))
    monkeypatch.setattr(acquire, "create_session", lambda *_: "access-token")
    monkeypatch.setattr(acquire, "urllib_transport", lambda _: transport)


def test_proxy_accepts_only_kite_connect_tunnel() -> None:
    assert proxy_decision("CONNECT", "api.kite.trade:443") == ("api.kite.trade", 443)
    assert proxy_decision("GET", "https://api.kite.trade/") is None
    assert proxy_decision("CONNECT", "example.com:443") is None
    assert proxy_decision("CONNECT", "api.kite.trade:80") is None


def test_low_level_transport_refuses_non_acquisition_route() -> None:
    transport = urllib_transport("http://127.0.0.1:9")
    with pytest.raises(ValueError, match="read-only Kite routes"):
        transport(Request("POST", "/orders/regular", {}, b"danger"))


def test_lockbox_is_refused_before_transport(tmp_path: Path) -> None:
    calls: list[object] = []

    def transport(request: Any) -> bytes:
        calls.append(request)
        return b""

    client = KiteClient("key", "token", tmp_path, transport=transport)
    with pytest.raises(ValueError, match="lockbox"):
        client.historical(
            1, "day", datetime(2022, 12, 1, tzinfo=UTC), datetime(2023, 1, 1, tzinfo=UTC)
        )
    assert calls == []


def test_malformed_historical_schema_is_rejected(tmp_path: Path) -> None:
    client = KiteClient(
        "key",
        "token",
        tmp_path,
        transport=lambda _: b'{"status":"success","data":{"candles":[["bad"]]}}',
    )
    with pytest.raises(SchemaFailure):
        client.historical(
            1, "day", datetime(2022, 1, 1, tzinfo=UTC), datetime(2022, 1, 2, tzinfo=UTC)
        )


def test_archive_is_immutable_and_checkpoint_detects_tampering(tmp_path: Path) -> None:
    request = {"kind": "historical", "instrument_token": 1, "interval": "day"}
    payload = b'{"status":"success","data":{"candles":[]}}'
    archived = archive_response(
        tmp_path,
        request,
        payload,
        "empty",
        coverage={"count": 0, "first_timestamp": None, "last_timestamp": None},
    )
    assert archived.raw_path.read_bytes() == payload
    assert load_checkpoint(archived.manifest_path)["result"] == "empty"
    archived.raw_path.write_bytes(b"tampered")
    with pytest.raises(ValueError, match=r"metadata|hash"):
        load_checkpoint(archived.manifest_path)


def test_empty_response_is_preserved_as_empty_not_holiday(tmp_path: Path) -> None:
    client = KiteClient(
        "key", "token", tmp_path, transport=lambda _: b'{"status":"success","data":{"candles":[]}}'
    )
    result = client.historical(
        1, "day", datetime(2022, 1, 1, tzinfo=UTC), datetime(2022, 1, 2, tzinfo=UTC)
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["result"] == "empty"
    assert "holiday" not in json.dumps(manifest).lower()


def test_symbol_file_requires_unique_nifty50_and_preserves_missing(tmp_path: Path) -> None:
    symbols = tmp_path / "symbols.txt"
    symbols.write_text("INFY\nMISSINGCO\nNIFTY50\n", encoding="utf-8")
    assert validate_symbol_file(symbols) == ["INFY", "MISSINGCO", "NIFTY50"]
    symbols.write_text("INFY\nINFY\nNIFTY50\n", encoding="utf-8")
    with pytest.raises(ValueError, match="duplicate"):
        validate_symbol_file(symbols)


def test_request_list_provenance_detects_tampering(tmp_path: Path) -> None:
    symbols = tmp_path / "symbols.txt"
    symbols.write_bytes(b"INFY\nNIFTY50\n")
    provenance = tmp_path / "provenance.json"
    provenance.write_text(
        json.dumps(
            {
                "output": {"sha256": hashlib.sha256(symbols.read_bytes()).hexdigest()},
                "classification": "REQUESTED_NOT_CERTIFIED_PIT",
                "source": {"path": "panel.npz", "sha256": "a" * 64},
                "decoded_member": {"name": "symbols.npy", "sha256": "b" * 64},
            }
        ),
        encoding="utf-8",
    )
    assert validate_provenance(provenance, symbols)["classification"]
    symbols.write_bytes(b"TAMPERED\nNIFTY50\n")
    with pytest.raises(ValueError, match="hash mismatch"):
        validate_provenance(provenance, symbols)
    symbols.write_text("INFY\n", encoding="utf-8")
    with pytest.raises(ValueError, match="NIFTY50"):
        validate_symbol_file(symbols)


def test_legacy_manifest_requires_caller_reviewed_digest(tmp_path: Path) -> None:
    path = _write_legacy_manifest(tmp_path)
    reviewed = legacy_manifest_sha256(path)
    assert validate_legacy_token_file(path, reviewed) == [
        LegacyTokenRoute("HDFC", "HDFC", 340481, "EQ", "INE001A01036", LEGACY_EVIDENCE_URL)
    ]
    path = _write_legacy_manifest(tmp_path, 341249)
    with pytest.raises(ValueError, match="digest"):
        validate_legacy_token_file(path, reviewed)


@pytest.mark.parametrize("token", [True, 0, -1, "340481"])
def test_legacy_manifest_rejects_invalid_token(tmp_path: Path, token: object) -> None:
    path = _write_legacy_manifest(tmp_path, token)
    digest = legacy_manifest_sha256(path)
    with pytest.raises(ValueError):
        validate_legacy_token_file(path, digest)


def test_legacy_token_collision_guard_checks_every_current_master_row() -> None:
    rows = list(csv.DictReader(_instrument_master(collision=True).decode().splitlines()))
    route = LegacyTokenRoute("HDFC", "HDFC", 340481, "EQ", "INE001A01036", LEGACY_EVIDENCE_URL)
    with pytest.raises(SchemaFailure, match="legacy token present in current master"):
        _validate_legacy_tokens_not_current(rows, [route])


@pytest.mark.parametrize(
    ("start", "end"),
    [("2022-11-28", "2022-12-30"), ("2022-11-29", "2022-12-31")],
)
def test_invalid_download_range_fails_before_credentials_or_transport(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    start: str,
    end: str,
) -> None:
    symbols, provenance = _write_download_inputs(tmp_path, ["NIFTY50"])
    manifest = _write_legacy_manifest(tmp_path)
    args = _main_args(tmp_path, symbols, provenance, run_id=f"bad-range-{start[-2:]}-{end[-2:]}")
    args.extend(
        [
            "--legacy-token-file",
            str(manifest),
            "--legacy-token-sha256",
            legacy_manifest_sha256(manifest),
        ]
    )
    args[args.index("--history-start") + 1] = start
    args[args.index("--history-end") + 1] = end
    monkeypatch.setattr(
        getpass,
        "getpass",
        lambda _: (_ for _ in ()).throw(AssertionError("credential prompt reached")),
    )
    monkeypatch.setattr(
        acquire,
        "urllib_transport",
        lambda _: (_ for _ in ()).throw(AssertionError("transport created")),
    )
    with pytest.raises(ValueError, match="bounded history range"):
        acquire.main(args)


def test_ordinary_download_without_range_preserves_original_run_identity(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    symbols, provenance = _write_download_inputs(tmp_path, ["NIFTY50"])
    args = _main_args(tmp_path, symbols, provenance, run_id="ordinary-default")
    del args[args.index("--history-start") :]
    monkeypatch.setattr(sys, "stdin", _NonInteractiveInput())
    with pytest.raises(RuntimeError, match="interactive terminal"):
        acquire.main(args)
    identity = json.loads(
        (tmp_path / "export" / "download" / "ordinary-default" / "request-identity.json").read_text(
            encoding="utf-8"
        )
    )
    assert set(identity) == {
        "mode",
        "symbols",
        "symbols_sha256",
        "provenance_sha256",
        "classification",
        "source_panel",
        "decoded_member",
    }
    with pytest.raises(RuntimeError, match="interactive terminal"):
        acquire.main(args)


def test_wrong_legacy_digest_fails_before_credentials_or_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    symbols, provenance = _write_download_inputs(tmp_path, ["NIFTY50"])
    manifest = _write_legacy_manifest(tmp_path)
    args = _main_args(tmp_path, symbols, provenance, run_id="bad-digest")
    args.extend(["--legacy-token-file", str(manifest), "--legacy-token-sha256", "0" * 64])
    monkeypatch.setattr(sys, "stdin", _InteractiveInput())
    monkeypatch.setattr(
        getpass,
        "getpass",
        lambda _: (_ for _ in ()).throw(AssertionError("credential prompt reached")),
    )
    monkeypatch.setattr(
        acquire,
        "urllib_transport",
        lambda _: (_ for _ in ()).throw(AssertionError("transport created")),
    )
    with pytest.raises(ValueError, match="digest"):
        acquire.main(args)


def test_legacy_label_duplicated_in_symbol_request_fails_before_credentials_or_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    symbols, provenance = _write_download_inputs(tmp_path, ["HDFC", "NIFTY50"])
    manifest = _write_legacy_manifest(tmp_path)
    args = _main_args(tmp_path, symbols, provenance, run_id="duplicate-route-label")
    args.extend(
        [
            "--legacy-token-file",
            str(manifest),
            "--legacy-token-sha256",
            legacy_manifest_sha256(manifest),
        ]
    )
    monkeypatch.setattr(sys, "stdin", _InteractiveInput())
    monkeypatch.setattr(
        getpass,
        "getpass",
        lambda _: (_ for _ in ()).throw(AssertionError("credential prompt reached")),
    )
    monkeypatch.setattr(
        acquire,
        "urllib_transport",
        lambda _: (_ for _ in ()).throw(AssertionError("transport created")),
    )
    with pytest.raises(ValueError, match="duplicate requested label across routes"):
        acquire.main(args)


def test_legacy_collision_uses_fresh_master_and_makes_zero_historical_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    symbols, provenance = _write_download_inputs(tmp_path, ["NIFTY50"])
    manifest = _write_legacy_manifest(tmp_path)
    args = _main_args(tmp_path, symbols, provenance, run_id="collision")
    args.extend(
        [
            "--legacy-token-file",
            str(manifest),
            "--legacy-token-sha256",
            legacy_manifest_sha256(manifest),
        ]
    )
    run_root = tmp_path / "export" / "download" / "collision"
    KiteClient(
        "key",
        "token",
        run_root,
        transport=lambda _: _instrument_master(),
        sleeper=lambda _: None,
    ).instruments()
    calls: list[Request] = []

    def transport(request: Request) -> bytes:
        calls.append(request)
        if request.path == "/instruments/NSE":
            return _instrument_master(collision=True)
        raise AssertionError("historical transport reached after collision")

    _install_fake_auth(monkeypatch, transport)
    with pytest.raises(SchemaFailure, match="legacy token present in current master"):
        acquire.main(args)
    assert [request.path for request in calls] == ["/instruments/NSE"]
    master_manifests = list(run_root.rglob("manifest.json"))
    assert len(master_manifests) == 2


def test_resume_refuses_changed_legacy_route_before_credentials_or_transport(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    symbols, provenance = _write_download_inputs(tmp_path, ["NIFTY50"])
    manifest = _write_legacy_manifest(tmp_path)
    args = _main_args(tmp_path, symbols, provenance, run_id="route-drift")
    args.extend(
        [
            "--legacy-token-file",
            str(manifest),
            "--legacy-token-sha256",
            legacy_manifest_sha256(manifest),
        ]
    )
    monkeypatch.setattr(sys, "stdin", _NonInteractiveInput())
    with pytest.raises(RuntimeError, match="interactive terminal"):
        acquire.main(args)
    changed = _write_legacy_manifest(tmp_path, 341249)
    args[-1] = legacy_manifest_sha256(changed)
    monkeypatch.setattr(
        getpass,
        "getpass",
        lambda _: (_ for _ in ()).throw(AssertionError("credential prompt reached")),
    )
    monkeypatch.setattr(
        acquire,
        "urllib_transport",
        lambda _: (_ for _ in ()).throw(AssertionError("transport created")),
    )
    with pytest.raises(ValueError, match="different acquisition inputs"):
        acquire.main(args)


@pytest.mark.parametrize(
    ("second_payload", "second_result", "expected_exit"),
    [
        (b'{"status":"success","data":{"candles":[]}}', "empty", 0),
        (
            b'{"status":"success","data":{"candles":[["2022-12-28T09:15:00+05:30",100,90,110,105,10]]}}',
            "rejected",
            3,
        ),
    ],
)
def test_resumed_legacy_results_stay_outside_accepted_coverage(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    second_payload: bytes,
    second_result: str,
    expected_exit: int,
) -> None:
    symbols, provenance = _write_download_inputs(tmp_path, ["NIFTY50"])
    manifest = _write_legacy_manifest(tmp_path)
    run_id = "legacy-resume"
    args = _main_args(tmp_path, symbols, provenance, run_id=run_id)
    args.extend(
        [
            "--legacy-token-file",
            str(manifest),
            "--legacy-token-sha256",
            legacy_manifest_sha256(manifest),
        ]
    )
    run_root = tmp_path / "export" / "download" / run_id
    start = datetime(2022, 11, 29, tzinfo=acquire.IST).astimezone(UTC)
    end = datetime(2022, 12, 30, 23, 59, 59, tzinfo=acquire.IST).astimezone(UTC)
    seed_payloads = iter((_valid_candles(), second_payload))
    seed = KiteClient(
        "key", "token", run_root, transport=lambda _: next(seed_payloads), sleeper=lambda _: None
    )
    seed.historical(340481, "day", start, end)
    seed.historical(340481, "15minute", start, end)
    calls: list[Request] = []

    def transport(request: Request) -> bytes:
        calls.append(request)
        if request.path == "/instruments/NSE":
            return _instrument_master()
        if "/historical/340481/" in request.path:
            raise AssertionError("cached legacy response was transported again")
        return _valid_candles()

    _install_fake_auth(monkeypatch, transport)
    assert acquire.main(args) == expected_exit
    report = json.loads((run_root / "report.json").read_text(encoding="utf-8"))
    assert {row["result"] for row in report["quarantined_routes"]} == {
        "success",
        second_result,
    }
    assert {row["identity_status"] for row in report["quarantined_routes"]} == {
        "QUARANTINED_IDENTITY_UNPROVED"
    }
    assert all(row.get("symbol") != "HDFC" for row in report["coverage"])
    assert report["counts"]["accepted_chunks"] == 2
    assert report["counts"]["empty_chunks"] == 0
    assert report["counts"]["quarantined_chunks"] == 2
    assert report["counts"]["requested_chunks"] == 4
    assert report["source_qualified"] is False


def test_be_candidate_requires_hash_pinned_series_evidence_before_credentials(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    symbols, provenance = _write_download_inputs(tmp_path, ["HFCL-BE", "NIFTY50"])
    args = _main_args(tmp_path, symbols, provenance, run_id="missing-be-evidence")
    monkeypatch.setattr(
        getpass,
        "getpass",
        lambda _: (_ for _ in ()).throw(AssertionError("credential prompt reached")),
    )
    with pytest.raises(ValueError, match="series route evidence"):
        acquire.main(args)


def test_be_candidate_success_is_quarantined_not_ordinary_coverage(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    symbols, provenance = _write_download_inputs(
        tmp_path,
        ["HFCL-BE", "NIFTY50"],
        classification="CURRENT_SERIES_RETRIEVAL_CANDIDATES_NOT_IDENTITY_PROOF",
    )
    args = _main_args(tmp_path, symbols, provenance, run_id="be-quarantine")
    original_evidence = tmp_path / "series-evidence.json"
    staged = tmp_path / "staged" / "series-route-evidence-be-quarantine.json"
    staged.parent.mkdir()
    original_evidence.replace(staged)
    evidence_sha256 = hashlib.sha256(staged.read_bytes()).hexdigest()
    args.extend(
        [
            "--series-route-evidence-file",
            str(staged),
            "--series-route-evidence-sha256",
            evidence_sha256,
        ]
    )

    def transport(request: Request) -> bytes:
        if request.path == "/instruments/NSE":
            return _instrument_master(include_be=True)
        return _valid_candles()

    _install_fake_auth(monkeypatch, transport)
    assert acquire.main(args) == 0
    report = json.loads(
        (tmp_path / "export" / "download" / "be-quarantine" / "report.json").read_text(
            encoding="utf-8"
        )
    )
    assert {row["symbol"] for row in report["quarantined_routes"]} == {"HFCL-BE"}
    assert {row["identity_status"] for row in report["quarantined_routes"]} == {
        "QUARANTINED_SERIES_IDENTITY_UNPROVED"
    }
    assert all(row["symbol"] == "NIFTY50" for row in report["coverage"])
    assert report["counts"]["accepted_chunks"] == 2
    assert report["counts"]["requested_chunks"] == 4


def test_be_candidate_master_token_mismatch_makes_zero_historical_calls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    symbols, provenance = _write_download_inputs(
        tmp_path,
        ["HFCL-BE", "NIFTY50"],
        classification="CURRENT_SERIES_RETRIEVAL_CANDIDATES_NOT_IDENTITY_PROOF",
    )
    args = _main_args(tmp_path, symbols, provenance, run_id="be-token-mismatch")
    evidence = tmp_path / "series-evidence.json"
    args.extend(
        [
            "--series-route-evidence-file",
            str(evidence),
            "--series-route-evidence-sha256",
            hashlib.sha256(evidence.read_bytes()).hexdigest(),
        ]
    )
    calls: list[Request] = []

    def transport(request: Request) -> bytes:
        calls.append(request)
        if request.path == "/instruments/NSE":
            return _instrument_master(include_be=True).replace(b"5620225,", b"5620226,")
        raise AssertionError("historical transport reached after series-token mismatch")

    _install_fake_auth(monkeypatch, transport)
    with pytest.raises(SchemaFailure, match="series evidence token mismatch"):
        acquire.main(args)
    assert [request.path for request in calls] == ["/instruments/NSE"]


def test_launcher_passes_bounded_dates_and_reviewed_legacy_digest() -> None:
    script = Path("scripts/start_kite_acquisition.ps1").read_text(encoding="utf-8")
    assert "[string]$HistoryStart" in script
    assert "[string]$HistoryEnd" in script
    assert "[string]$LegacyTokenFile" in script
    assert "[string]$LegacyTokenSha256" in script
    assert "[string]$SeriesRouteEvidenceFile" in script
    assert "[string]$SeriesRouteEvidenceSha256" in script
    assert '"--history-start", $HistoryStart, "--history-end", $HistoryEnd' in script
    assert '"--legacy-token-file", "/export/$legacyName"' in script
    assert '"--legacy-token-sha256", $expectedLegacyHash' in script
    assert '"--series-route-evidence-file", "/export/$seriesEvidenceName"' in script


def test_callback_parser_accepts_only_local_callback_or_bare_token() -> None:
    assert parse_callback_token("abc123") == "abc123"
    assert (
        parse_callback_token("http://127.0.0.1/callback?request_token=abc123&action=login")
        == "abc123"
    )
    with pytest.raises(ValueError):
        parse_callback_token("https://evil.example/callback?request_token=abc123")


def test_auth_failure_halts_without_retry_or_secret_disclosure(tmp_path: Path) -> None:
    attempts = 0

    def denied(_: Any) -> bytes:
        nonlocal attempts
        attempts += 1
        raise AuthFailure("denied")

    secret = "never-print-this"
    client = KiteClient("key", secret, tmp_path, transport=denied)
    with pytest.raises(AuthFailure) as error:
        client.instruments()
    assert attempts == 1
    assert secret not in str(error.value)


def test_retry_is_bounded_for_transient_failures(tmp_path: Path) -> None:
    attempts = 0

    def transient(_: Any) -> bytes:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TimeoutError
        return (
            b"instrument_token,exchange_token,tradingsymbol,name,last_price,expiry,strike,"
            b"tick_size,lot_size,instrument_type,segment,exchange\n"
        )

    client = KiteClient("key", "token", tmp_path, transport=transient, sleeper=lambda _: None)
    client.instruments()
    assert attempts == 3


def test_archive_identity_binds_requested_range(tmp_path: Path) -> None:
    validate_range(datetime(2011, 1, 1, tzinfo=UTC), datetime(2011, 1, 2, tzinfo=UTC))
    with pytest.raises(ValueError, match="timezone"):
        validate_range(datetime(2011, 1, 1), datetime(2011, 1, 2, tzinfo=UTC))
    one = archive_response(
        tmp_path,
        {"from": "2011-01-01", "to": "2011-01-02"},
        b"{}",
        "rejected",
        validation_reason="MALFORMED_JSON_OR_ENVELOPE",
        validation_class="structural",
    )
    two = archive_response(
        tmp_path,
        {"from": "2011-01-02", "to": "2011-01-03"},
        b"{}",
        "rejected",
        validation_reason="MALFORMED_JSON_OR_ENVELOPE",
        validation_class="structural",
    )
    assert one.raw_path != two.raw_path
    manifest = json.loads(one.manifest_path.read_text(encoding="utf-8"))
    assert manifest["provider_bytes_sha256"] == hashlib.sha256(b"{}").hexdigest()


def test_provider_windows_are_conservative() -> None:
    daily = _chunks(datetime(2020, 1, 1).date(), datetime(2021, 12, 31).date(), "day")
    m15 = _chunks(datetime(2020, 1, 1).date(), datetime(2020, 12, 31).date(), "15minute")
    assert max((end - start).days + 1 for start, end in daily) <= 365
    assert max((end - start).days + 1 for start, end in m15) <= 90


def test_instrument_resolution_requires_exact_unique_contract() -> None:
    index = {
        "name": "NIFTY 50",
        "tradingsymbol": "NIFTY 50",
        "instrument_type": "EQ",
        "segment": "NSE-INDICES",
        "exchange": "NSE",
        "instrument_token": "256265",
    }
    assert _resolve([index], "NIFTY50") == 256265
    with pytest.raises(SchemaFailure, match="non-unique"):
        _resolve([index, index], "NIFTY50")


def test_nifty_resolution_accepts_current_and_legacy_segments_only() -> None:
    current = {
        "name": "NIFTY 50",
        "tradingsymbol": "NIFTY 50",
        "instrument_type": "EQ",
        "segment": "INDICES",
        "exchange": "NSE",
        "instrument_token": "256265",
    }
    legacy = {**current, "segment": "NSE-INDICES"}
    assert _resolve([current], "NIFTY50") == 256265
    assert _resolve([legacy], "NIFTY50") == 256265
    assert _resolve([{**current, "segment": "NFO"}], "NIFTY50") is None
    with pytest.raises(SchemaFailure, match="non-unique"):
        _resolve([current, legacy], "NIFTY50")


def test_historical_manifest_reports_coverage_without_prices(tmp_path: Path) -> None:
    payload = (
        b'{"status":"success","data":{"candles":['
        b'["2022-01-01T09:15:00+05:30",1,2,0.5,1.5,10],'
        b'["2022-01-01T09:30:00+05:30",1.5,2,1,1.8,11]]}}'
    )
    client = KiteClient("key", "token", tmp_path, transport=lambda _: payload)
    result = client.historical(
        1, "15minute", datetime(2021, 12, 31, tzinfo=UTC), datetime(2022, 1, 2, tzinfo=UTC)
    )
    manifest = json.loads(result.manifest_path.read_text(encoding="utf-8"))
    assert manifest["coverage"] == {
        "count": 2,
        "first_timestamp": "2022-01-01T09:15:00+05:30",
        "last_timestamp": "2022-01-01T09:30:00+05:30",
    }
    assert "1.8" not in json.dumps(manifest)


def test_candles_require_positive_ohlc_and_integer_volume(tmp_path: Path) -> None:
    bad = b'{"status":"success","data":{"candles":[["2022-01-01T09:15:00+05:30",1,2,0,1.5,10.5]]}}'
    with pytest.raises(SchemaFailure):
        _validate_historical(
            bad, datetime(2021, 12, 31, tzinfo=UTC), datetime(2022, 1, 2, tzinfo=UTC)
        )


def test_candles_refuse_impossible_ohlc_envelope(tmp_path: Path) -> None:
    bad = (
        b'{"status":"success","data":{"candles":[["2022-01-01T09:15:00+05:30",100,90,110,100,10]]}}'
    )
    with pytest.raises(SchemaFailure, match="INVALID_OHLC_ENVELOPE"):
        _validate_historical(
            bad, datetime(2021, 12, 31, tzinfo=UTC), datetime(2022, 1, 2, tzinfo=UTC)
        )


def test_quality_failure_is_archived_byte_exact_and_reused_without_transport(
    tmp_path: Path,
) -> None:
    bad = (
        b'{"status":"success","data":{"candles":[["2022-01-01T09:15:00+05:30",100,90,110,100,10]]}}'
    )
    calls = 0

    def transport(_: Any) -> bytes:
        nonlocal calls
        calls += 1
        return bad

    client = KiteClient("key", "token", tmp_path, transport=transport)
    args = (1, "15minute", datetime(2021, 12, 31, tzinfo=UTC), datetime(2022, 1, 2, tzinfo=UTC))
    first = client.historical(*args)
    second = client.historical(*args)
    manifest = load_checkpoint(first.manifest_path)
    assert first == second
    assert calls == 1
    assert first.raw_path.read_bytes() == bad
    assert manifest["result"] == "rejected"
    assert manifest["validation_reason"] == "INVALID_OHLC_ENVELOPE"
    assert "coverage" not in manifest


def test_structural_failure_archives_then_halts_on_resume(tmp_path: Path) -> None:
    malformed = b'{"status":"success","data":{"candles":"wrong"}}'
    calls = 0

    def transport(_: Any) -> bytes:
        nonlocal calls
        calls += 1
        return malformed

    client = KiteClient("key", "token", tmp_path, transport=transport)
    args = (1, "day", datetime(2022, 1, 1, tzinfo=UTC), datetime(2022, 1, 2, tzinfo=UTC))
    with pytest.raises(SchemaFailure, match="MALFORMED_JSON_OR_ENVELOPE"):
        client.historical(*args)
    with pytest.raises(SchemaFailure, match="MALFORMED_JSON_OR_ENVELOPE"):
        client.historical(*args)
    assert calls == 1


def test_quality_rejection_does_not_block_independent_next_request(tmp_path: Path) -> None:
    rejected = b'{"status":"success","data":{"candles":[["2022-01-01T09:15:00+05:30",1,2,3,1,10]]}}'
    accepted = (
        b'{"status":"success","data":{"candles":[["2022-01-01T09:15:00+05:30",1,2,0.5,1,10]]}}'
    )
    payloads = iter((rejected, accepted))
    client = KiteClient("key", "token", tmp_path, transport=lambda _: next(payloads))
    start = datetime(2021, 12, 31, tzinfo=UTC)
    end = datetime(2022, 1, 2, tzinfo=UTC)
    first = load_checkpoint(client.historical(1, "15minute", start, end).manifest_path)
    second = load_checkpoint(client.historical(2, "15minute", start, end).manifest_path)
    assert first["result"] == "rejected"
    assert second["result"] == "success"
    assert "coverage" not in first
    assert second["coverage"]["count"] == 1


@pytest.mark.parametrize(
    "late_timestamp",
    ["2023-01-02T09:15:00+05:30", "2023-01-01T00:01:00+05:30", "2023-01-01T00:01:00"],
)
def test_lockbox_prescan_prevents_quarantine_of_mixed_payload(
    tmp_path: Path, late_timestamp: str
) -> None:
    payload = json.dumps(
        {
            "status": "success",
            "data": {
                "candles": [
                    ["2022-01-01T09:15:00+05:30", 100, 90, 110, 100, 10],
                    [late_timestamp, 100, 110, 90, 100, 10],
                ]
            },
        }
    ).encode()
    client = KiteClient("key", "token", tmp_path, transport=lambda _: payload)
    with pytest.raises(SchemaFailure, match="LOCKBOX_DATA"):
        client.historical(
            1,
            "15minute",
            datetime(2021, 12, 31, tzinfo=UTC),
            datetime(2022, 1, 3, tzinfo=UTC),
        )
    assert list(tmp_path.rglob("provider-response.raw")) == []
    assert list(tmp_path.rglob("manifest.json")) == []


@pytest.mark.parametrize(
    "mutation",
    [
        {"validation_reason": "UNTRUSTED_TEXT"},
        {"validation_class": "structural", "validation_reason": "INVALID_OHLC_ENVELOPE"},
        {"coverage": {"count": 1, "first_timestamp": "x", "last_timestamp": "x"}},
        {"coverage": None},
    ],
)
def test_cached_rejection_refuses_tampered_state_without_transport(
    tmp_path: Path, mutation: dict[str, object]
) -> None:
    bad = (
        b'{"status":"success","data":{"candles":[["2022-01-01T09:15:00+05:30",100,90,110,100,10]]}}'
    )
    start = datetime(2021, 12, 31, tzinfo=UTC)
    end = datetime(2022, 1, 2, tzinfo=UTC)
    archive = KiteClient("key", "token", tmp_path, transport=lambda _: bad).historical(
        1, "15minute", start, end
    )
    manifest = json.loads(archive.manifest_path.read_text(encoding="utf-8"))
    manifest.update(mutation)
    archive.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    def forbidden(_: Any) -> bytes:
        raise AssertionError("cached tamper must fail before transport")

    with pytest.raises(ValueError, match="invalid rejected checkpoint"):
        KiteClient("key", "token", tmp_path, transport=forbidden).historical(
            1, "15minute", start, end
        )


def test_cached_success_refuses_rejection_metadata_without_transport(tmp_path: Path) -> None:
    good = (
        b'{"status":"success","data":{"candles":[["2022-01-01T09:15:00+05:30",100,110,90,100,10]]}}'
    )
    start = datetime(2021, 12, 31, tzinfo=UTC)
    end = datetime(2022, 1, 2, tzinfo=UTC)
    archive = KiteClient("key", "token", tmp_path, transport=lambda _: good).historical(
        1, "15minute", start, end
    )
    manifest = json.loads(archive.manifest_path.read_text(encoding="utf-8"))
    manifest.update({"validation_class": "quality", "validation_reason": "INVALID_VOLUME"})
    archive.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="non-rejected checkpoint"):
        KiteClient(
            "key",
            "token",
            tmp_path,
            transport=lambda _: (_ for _ in ()).throw(AssertionError("transport called")),
        ).historical(1, "15minute", start, end)


@pytest.mark.parametrize("field", ["validation_class", "validation_reason"])
def test_cached_success_refuses_null_rejection_keys(tmp_path: Path, field: str) -> None:
    good = (
        b'{"status":"success","data":{"candles":[["2022-01-01T09:15:00+05:30",100,110,90,100,10]]}}'
    )
    start = datetime(2021, 12, 31, tzinfo=UTC)
    end = datetime(2022, 1, 2, tzinfo=UTC)
    archive = KiteClient("key", "token", tmp_path, transport=lambda _: good).historical(
        1, "15minute", start, end
    )
    manifest = json.loads(archive.manifest_path.read_text(encoding="utf-8"))
    manifest[field] = None
    archive.manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(ValueError, match="non-rejected checkpoint"):
        load_checkpoint(archive.manifest_path)
