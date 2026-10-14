from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from tools.kite_acquire.acquire import (
    AuthFailure,
    KiteClient,
    Request,
    SchemaFailure,
    _chunks,
    _resolve,
    _validate_historical,
    archive_response,
    load_checkpoint,
    parse_callback_token,
    urllib_transport,
    validate_provenance,
    validate_range,
    validate_symbol_file,
)
from tools.kite_acquire.proxy import proxy_decision


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
