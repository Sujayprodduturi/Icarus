from __future__ import annotations

import argparse
import csv
import getpass
import hashlib
import json
import math
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any, Final, cast
from zoneinfo import ZoneInfo

API_ROOT: Final = "https://api.kite.trade"
IST: Final = ZoneInfo("Asia/Kolkata")
MAX_RESPONSE_BYTES: Final = 128 * 1024 * 1024
TOKEN_PATTERN: Final = re.compile(r"^[A-Za-z0-9_-]{3,256}$")
# Conservative request windows, checked 2026-10-14. Provider stated maxima were
# 2,000 days for daily and 200 days for 15-minute data; smaller windows reduce
# retry cost without asserting anything about historical availability.
# Sources: https://kite.trade/forum/discussion/2875/is-there-any-limitation-on-getting-historical-data
# https://kite.trade/forum/discussion/16124/historical-15-minute-ohlc-data-availability-pricing-and-api-limits-for-equity-stocks
DAILY_CHUNK_DAYS: Final = 365
M15_CHUNK_DAYS: Final = 90
BOUNDED_HISTORY_START: Final = date(2022, 11, 29)
BOUNDED_HISTORY_END: Final = date(2022, 12, 30)
SERIES_CANDIDATE_CLASSIFICATION: Final = "CURRENT_SERIES_RETRIEVAL_CANDIDATES_NOT_IDENTITY_PROOF"


class AuthFailure(RuntimeError):
    pass


class SchemaFailure(RuntimeError):
    pass


class CandleQualityFailure(SchemaFailure):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class StructuralFailure(SchemaFailure):
    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class LockboxFailure(SchemaFailure):
    pass


QUALITY_REASONS: Final = {
    "TIMESTAMP_OUT_OF_RANGE",
    "TIMESTAMPS_NOT_STRICTLY_INCREASING",
    "NON_POSITIVE_OHLC",
    "INVALID_OHLC_ENVELOPE",
    "INVALID_VOLUME",
    "INVALID_OI",
}
STRUCTURAL_REASONS: Final = {
    "MALFORMED_JSON_OR_ENVELOPE",
    "PROVIDER_STATUS_FAILURE",
    "INVALID_CANDLE_SHAPE",
    "INVALID_TIMESTAMP_SYNTAX",
    "INVALID_NUMERIC_TYPE",
    "NONFINITE_NUMERIC",
}


@dataclass(frozen=True)
class Request:
    method: str
    path: str
    headers: Mapping[str, str]
    body: bytes | None = None


@dataclass(frozen=True)
class Archive:
    raw_path: Path
    manifest_path: Path


@dataclass(frozen=True)
class LegacyTokenRoute:
    requested_label: str
    historical_tradingsymbol: str
    instrument_token: int
    nse_series: str
    nse_isin: str
    evidence_url: str


Transport = Callable[[Request], bytes]


def validate_range(start: datetime, end: datetime) -> None:
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("timestamps must be timezone-aware")
    if start >= end:
        raise ValueError("range start must precede end")
    if end.astimezone(IST).date() >= date(2023, 1, 1):
        raise ValueError("lockbox data at or after 2023-01-01 is forbidden")


def parse_callback_token(value: str) -> str:
    candidate = value.strip()
    if candidate.startswith("http://127.0.0.1/") or candidate.startswith("http://localhost/"):
        query = urllib.parse.parse_qs(urllib.parse.urlsplit(candidate).query)
        candidate = query.get("request_token", [""])[0]
    elif "://" in candidate:
        raise ValueError("only a local callback URL is accepted")
    if not TOKEN_PATTERN.fullmatch(candidate):
        raise ValueError("invalid request token")
    return candidate


def validate_symbol_file(path: Path) -> list[str]:
    symbols = [
        line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]
    if len(symbols) != len(set(symbols)):
        raise ValueError("duplicate requested symbol")
    if "NIFTY50" not in symbols:
        raise ValueError("symbols file must include NIFTY50")
    for symbol in symbols:
        if not re.fullmatch(r"[A-Z0-9&.-]{1,64}", symbol):
            raise ValueError(f"invalid symbol: {symbol}")
    return symbols


def validate_bounded_history_dates(start_value: str, end_value: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(start_value)
        end = date.fromisoformat(end_value)
    except ValueError:
        raise ValueError("invalid bounded history range") from None
    if (start, end) != (BOUNDED_HISTORY_START, BOUNDED_HISTORY_END):
        raise ValueError("bounded history range must be exactly 2022-11-29 through 2022-12-30")
    return start, end


def validate_optional_history_dates(
    start_value: str | None, end_value: str | None
) -> tuple[date, date] | None:
    if start_value is None and end_value is None:
        return None
    if start_value is None or end_value is None:
        raise ValueError("history start and end must be supplied together")
    try:
        start = date.fromisoformat(start_value)
        end = date.fromisoformat(end_value)
    except ValueError:
        raise ValueError("invalid history range") from None
    if start > end or end >= date(2023, 1, 1):
        raise ValueError("invalid history range")
    return start, end


def legacy_manifest_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_legacy_token_file(path: Path, expected_sha256: str) -> list[LegacyTokenRoute]:
    if re.fullmatch(r"[0-9a-fA-F]{64}", expected_sha256) is None:
        raise ValueError("invalid expected legacy manifest digest")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256.lower():
        raise ValueError("legacy manifest digest mismatch")
    try:
        manifest = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("malformed legacy token manifest") from None
    top_keys = {"schema_version", "status", "as_of_date", "scope", "routes", "limits"}
    if not isinstance(manifest, dict) or set(manifest) != top_keys:
        raise ValueError("malformed legacy token manifest")
    if (
        manifest["schema_version"] != 1
        or manifest["status"] != "EXPLICIT_LEGACY_TOKEN_CANDIDATES_NOT_IDENTITY_PROOF"
        or manifest["as_of_date"] != "2026-10-16"
        or manifest["scope"] != "metadata routing for the bounded 2022 pilot and its warmup only"
        or not isinstance(manifest["routes"], list)
        or not manifest["routes"]
        or not isinstance(manifest["limits"], list)
        or not manifest["limits"]
        or any(not isinstance(item, str) or not item for item in manifest["limits"])
    ):
        raise ValueError("malformed legacy token manifest")
    route_keys = {
        "requested_label",
        "historical_tradingsymbol",
        "historical_instrument_token",
        "provider_evidence_date",
        "provider_evidence_url",
        "provider_evidence_observation",
        "nse_2022_12_30_series",
        "nse_2022_12_30_isin",
        "pilot_disposition",
        "route_status",
        "identity_status",
        "token_continuity",
    }
    routes: list[LegacyTokenRoute] = []
    labels: set[str] = set()
    tokens: set[int] = set()
    for item in manifest["routes"]:
        if not isinstance(item, dict) or set(item) != route_keys:
            raise ValueError("malformed legacy token route")
        label = item["requested_label"]
        historical_symbol = item["historical_tradingsymbol"]
        token = item["historical_instrument_token"]
        evidence_date = item["provider_evidence_date"]
        evidence_url = item["provider_evidence_url"]
        observation = item["provider_evidence_observation"]
        nse_series = item["nse_2022_12_30_series"]
        nse_isin = item["nse_2022_12_30_isin"]
        dispositions = item["pilot_disposition"]
        parsed_url = urllib.parse.urlsplit(evidence_url) if isinstance(evidence_url, str) else None
        if (
            not isinstance(label, str)
            or re.fullmatch(r"[A-Z0-9&.-]{1,64}", label) is None
            or historical_symbol != label
            or isinstance(token, bool)
            or not isinstance(token, int)
            or token <= 0
            or not isinstance(evidence_date, str)
            or re.fullmatch(r"[0-9]{4}-[0-9]{2}", evidence_date) is None
            or parsed_url is None
            or parsed_url.scheme != "https"
            or parsed_url.netloc != "kite.trade"
            or not parsed_url.path.startswith("/forum/")
            or not isinstance(observation, str)
            or not observation.strip()
            or nse_series != "EQ"
            or not isinstance(nse_isin, str)
            or re.fullmatch(r"[A-Z0-9]{12}", nse_isin) is None
            or not isinstance(dispositions, list)
            or len(dispositions) != 5
            or any(
                value not in {"CONDITIONAL_QUALIFIES", "BELOW_TURNOVER"} for value in dispositions
            )
            or item["route_status"] != "COLLECTION_CANDIDATE_ONLY"
            or item["identity_status"] != "UNKNOWN"
            or item["token_continuity"] != "UNKNOWN"
        ):
            raise ValueError("malformed legacy token route")
        if label in labels or token in tokens:
            raise ValueError("duplicate legacy token route")
        labels.add(label)
        tokens.add(token)
        routes.append(
            LegacyTokenRoute(label, historical_symbol, token, nse_series, nse_isin, evidence_url)
        )
    return routes


def validate_provenance(path: Path, symbols_path: Path) -> dict[str, Any]:
    try:
        provenance: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        declared = provenance["output"]["sha256"]
        classification = provenance["classification"]
        source = provenance["source"]
        member = provenance["decoded_member"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        raise ValueError("malformed request-list provenance") from None
    actual = hashlib.sha256(symbols_path.read_bytes()).hexdigest()
    if declared != actual:
        raise ValueError("request-list provenance hash mismatch")
    if (
        not isinstance(classification, str)
        or not isinstance(source, dict)
        or not isinstance(member, dict)
    ):
        raise ValueError("malformed request-list provenance")
    return provenance


def validate_series_route_evidence(
    provenance: Mapping[str, Any],
    symbols: Sequence[str],
    evidence_path: Path | None,
    expected_evidence_sha256: str | None,
) -> tuple[str, dict[str, int]] | None:
    series_symbols = {symbol for symbol in symbols if symbol.endswith("-BE")}
    classification = provenance.get("classification")
    if not series_symbols:
        if (
            classification == SERIES_CANDIDATE_CLASSIFICATION
            or evidence_path is not None
            or expected_evidence_sha256 is not None
        ):
            raise ValueError("series route evidence classification has no BE candidate")
        return None
    if classification != SERIES_CANDIDATE_CLASSIFICATION:
        raise ValueError("BE candidate requires hash-pinned series route evidence")
    if evidence_path is None or expected_evidence_sha256 is None:
        raise ValueError("BE candidate requires hash-pinned series route evidence")
    if any(symbol != "NIFTY50" and symbol not in series_symbols for symbol in symbols):
        raise ValueError("series route evidence classification contains an ordinary symbol")
    member = provenance.get("decoded_member")
    if not isinstance(member, dict):
        raise ValueError("malformed series route evidence provenance")
    expected_sha256 = member.get("sha256")
    if (
        not isinstance(expected_sha256, str)
        or re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None
        or re.fullmatch(r"[0-9a-fA-F]{64}", expected_evidence_sha256) is None
        or expected_sha256 != expected_evidence_sha256.lower()
    ):
        raise ValueError("malformed series route evidence provenance")
    try:
        raw = evidence_path.read_bytes()
        evidence = json.loads(raw)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raise ValueError("malformed series route evidence") from None
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise ValueError("series route evidence hash mismatch")
    if (
        not isinstance(evidence, dict)
        or evidence.get("schema_version") != 1
        or evidence.get("status") != "CURRENT_SERIES_RETRIEVAL_CANDIDATES_ONLY"
        or not isinstance(evidence.get("routes"), list)
    ):
        raise ValueError("malformed series route evidence")
    evidence_tokens: dict[str, int] = {}
    for route in evidence["routes"]:
        if not isinstance(route, dict):
            raise ValueError("malformed series route evidence")
        retrieval_symbol = route.get("retrieval_symbol")
        current_token = route.get("current_instrument_token")
        if (
            not isinstance(retrieval_symbol, str)
            or not retrieval_symbol.endswith("-BE")
            or isinstance(current_token, bool)
            or not isinstance(current_token, int)
            or current_token <= 0
            or route.get("current_exchange") != "NSE"
            or route.get("current_series") != "BE"
            or route.get("current_instrument_type") != "EQ"
            or route.get("nse_2022_12_30_series") != "EQ"
            or route.get("route_status") != "COLLECTION_CANDIDATE_ONLY"
            or route.get("series_continuity") != "UNKNOWN"
            or route.get("token_continuity") != "UNKNOWN"
        ):
            raise ValueError("malformed series route evidence")
        if retrieval_symbol in evidence_tokens:
            raise ValueError("duplicate series route evidence")
        evidence_tokens[retrieval_symbol] = current_token
    if set(evidence_tokens) != series_symbols:
        raise ValueError("series route evidence does not match requested BE candidates")
    return expected_sha256, evidence_tokens


def _validate_legacy_tokens_not_current(
    rows: list[dict[str, str]], routes: Sequence[LegacyTokenRoute]
) -> None:
    try:
        current_tokens = {int(row["instrument_token"]) for row in rows}
    except (KeyError, TypeError, ValueError):
        raise SchemaFailure("malformed instrument token in fresh current master") from None
    reused = sorted(
        route.instrument_token for route in routes if route.instrument_token in current_tokens
    )
    if reused:
        raise SchemaFailure(f"legacy token present in current master: {reused}")


def _canonical(request: Mapping[str, object]) -> bytes:
    return json.dumps(request, sort_keys=True, separators=(",", ":")).encode()


def _archive_paths(root: Path, request: Mapping[str, object]) -> Archive:
    run = root / hashlib.sha256(_canonical(request)).hexdigest()
    return Archive(run / "provider-response.raw", run / "manifest.json")


def _atomic_write(path: Path, payload: bytes) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("xb") as stream:
        stream.write(payload)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


def _existing_checkpoint(paths: Archive) -> Archive | None:
    if paths.raw_path.exists() != paths.manifest_path.exists():
        raise ValueError("incomplete archive exists; preserve it for operator inspection")
    if paths.manifest_path.exists():
        load_checkpoint(paths.manifest_path)
        return paths
    return None


def _bind_run(root: Path, identity: Mapping[str, object]) -> None:
    path = root / "request-identity.json"
    encoded = json.dumps(identity, sort_keys=True, indent=2).encode() + b"\n"
    root.mkdir(parents=True, exist_ok=True)
    if path.exists():
        if path.read_bytes() != encoded:
            raise ValueError("run id is already bound to different acquisition inputs")
        return
    _atomic_write(path, encoded)


def archive_response(
    root: Path,
    request: Mapping[str, object],
    payload: bytes,
    result: str,
    *,
    coverage: Mapping[str, object] | None = None,
    validation_reason: str | None = None,
    validation_class: str | None = None,
) -> Archive:
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("provider response exceeds size bound")
    if result not in {"success", "empty", "rejected"}:
        raise ValueError("unknown archive result")
    if (validation_reason is None) != (validation_class is None):
        raise ValueError("validation class and reason must be supplied together")
    if validation_reason is not None:
        if validation_class not in {"quality", "structural"}:
            raise ValueError("unknown validation class")
        allowed = QUALITY_REASONS if validation_class == "quality" else STRUCTURAL_REASONS
        if validation_reason not in allowed:
            raise ValueError("unknown validation reason")
    if result == "rejected":
        if coverage is not None or validation_reason is None:
            raise ValueError("invalid rejected archive state")
    elif validation_reason is not None:
        raise ValueError("non-rejected archive carries rejection metadata")
    if request.get("kind") == "historical" and result != "rejected":
        if not isinstance(coverage, Mapping) or set(coverage) != {
            "count",
            "first_timestamp",
            "last_timestamp",
        }:
            raise ValueError("historical archive requires coverage")
    identity = hashlib.sha256(_canonical(request)).hexdigest()
    paths = _archive_paths(root, request)
    paths.raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path = paths.raw_path
    manifest_path = paths.manifest_path
    payload_hash = hashlib.sha256(payload).hexdigest()
    if raw_path.exists() != manifest_path.exists():
        raise ValueError("incomplete archive exists; preserve it for operator inspection")
    if raw_path.exists():
        existing = load_checkpoint(manifest_path)
        if existing["provider_bytes_sha256"] != payload_hash:
            raise ValueError("valid archive already exists; refusing overwrite")
        return Archive(raw_path, manifest_path)
    _atomic_write(raw_path, payload)
    manifest = {
        "archive_schema": 1,
        "request": request,
        "request_identity_sha256": identity,
        "provider_bytes_sha256": payload_hash,
        "provider_bytes_size": len(payload),
        "retrieved_at_utc": datetime.now(UTC).isoformat(),
        "result": result,
    }
    if coverage is not None:
        manifest["coverage"] = dict(coverage)
    if validation_reason is not None:
        manifest["validation_reason"] = validation_reason
        manifest["validation_class"] = validation_class
    _atomic_write(
        manifest_path,
        (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    )
    return Archive(raw_path, manifest_path)


def load_checkpoint(path: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    raw = path.with_name("provider-response.raw")
    raw_bytes = raw.read_bytes()
    request = manifest.get("request")
    provider_hash = manifest.get("provider_bytes_sha256")
    request_hash = manifest.get("request_identity_sha256")
    if (
        manifest.get("archive_schema") != 1
        or not isinstance(request, dict)
        or not isinstance(provider_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", provider_hash) is None
        or not isinstance(request_hash, str)
        or re.fullmatch(r"[0-9a-f]{64}", request_hash) is None
        or not isinstance(manifest.get("provider_bytes_size"), int)
        or isinstance(manifest.get("provider_bytes_size"), bool)
        or manifest["provider_bytes_size"] != len(raw_bytes)
        or not isinstance(manifest.get("retrieved_at_utc"), str)
    ):
        raise ValueError("invalid checkpoint metadata")
    if hashlib.sha256(raw_bytes).hexdigest() != provider_hash:
        raise ValueError("checkpoint provider-bytes hash mismatch")
    if hashlib.sha256(_canonical(request)).hexdigest() != request_hash:
        raise ValueError("checkpoint request hash mismatch")
    result = manifest.get("result")
    coverage = manifest.get("coverage")
    validation_class = manifest.get("validation_class")
    validation_reason = manifest.get("validation_reason")
    if result not in {"success", "empty", "rejected"}:
        raise ValueError("invalid checkpoint result")
    if result == "rejected":
        if "coverage" in manifest or validation_class not in {"quality", "structural"}:
            raise ValueError("invalid rejected checkpoint state")
        allowed = QUALITY_REASONS if validation_class == "quality" else STRUCTURAL_REASONS
        if validation_reason not in allowed:
            raise ValueError("invalid rejected checkpoint reason")
    else:
        if "validation_class" in manifest or "validation_reason" in manifest:
            raise ValueError("non-rejected checkpoint carries rejection metadata")
        if request.get("kind") == "historical":
            if not isinstance(coverage, dict) or set(coverage) != {
                "count",
                "first_timestamp",
                "last_timestamp",
            }:
                raise ValueError("invalid historical checkpoint coverage")
            count = coverage.get("count")
            first = coverage.get("first_timestamp")
            last = coverage.get("last_timestamp")
            if (
                not isinstance(count, int)
                or isinstance(count, bool)
                or count < 0
                or not (first is None or isinstance(first, str))
                or not (last is None or isinstance(last, str))
                or (result == "empty" and (count != 0 or first is not None or last is not None))
                or (result == "success" and (count == 0 or first is None or last is None))
            ):
                raise ValueError("invalid historical checkpoint coverage")
    return manifest


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(
        self, req: Any, fp: Any, code: int, msg: str, headers: Any, newurl: str
    ) -> None:
        return None


def urllib_transport(proxy_url: str, timeout: float = 20.0) -> Transport:
    if not proxy_url.startswith("http://"):
        raise ValueError("proxy URL must be explicit HTTP")
    opener = urllib.request.build_opener(
        urllib.request.ProxyHandler({"https": proxy_url, "http": proxy_url}), _NoRedirect()
    )

    def send(request: Request) -> bytes:
        allowed = (
            (request.method == "POST" and request.path == "/session/token")
            or (request.method == "GET" and request.path == "/instruments/NSE")
            or (
                request.method == "GET"
                and re.fullmatch(
                    r"/instruments/historical/[0-9]+/(day|15minute)\?[^#]+", request.path
                )
                is not None
            )
        )
        if not allowed:
            raise ValueError("request is outside the fixed read-only Kite routes")
        url = API_ROOT + request.path
        if not url.startswith(API_ROOT + "/"):
            raise ValueError("request escaped fixed Kite API root")
        req = urllib.request.Request(
            url, data=request.body, headers=dict(request.headers), method=request.method
        )
        try:
            with opener.open(req, timeout=timeout) as response:
                data = response.read(MAX_RESPONSE_BYTES + 1)
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                raise AuthFailure("Kite authentication failed; acquisition halted") from None
            if exc.code == 429 or 500 <= exc.code <= 599:
                raise TimeoutError("transient Kite response") from None
            raise RuntimeError(f"Kite HTTP failure {exc.code}") from None
        except urllib.error.URLError:
            raise TimeoutError("Kite network failure") from None
        if len(data) > MAX_RESPONSE_BYTES:
            raise ValueError("provider response exceeds size bound")
        return cast(bytes, data)

    return send


class KiteClient:
    def __init__(
        self,
        api_key: str,
        access_token: str,
        export_root: Path,
        *,
        transport: Transport,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        self._headers = {"X-Kite-Version": "3", "Authorization": f"token {api_key}:{access_token}"}
        self._root = export_root
        self._transport = transport
        self._sleep = sleeper
        self._last_request = 0.0

    def _send(self, request: Request) -> bytes:
        for attempt in range(3):
            delay = 0.5 - (time.monotonic() - self._last_request)
            if delay > 0:
                self._sleep(delay)
            try:
                payload = self._transport(request)
                self._last_request = time.monotonic()
                return payload
            except AuthFailure:
                raise
            except TimeoutError:
                if attempt == 2:
                    raise RuntimeError("Kite request failed after bounded retries") from None
                self._sleep(float(2**attempt))
        raise AssertionError("unreachable")

    def instruments(self) -> Archive:
        request_record = {"kind": "instruments", "exchange": "NSE"}
        checkpoint = _archive_paths(self._root, request_record)
        existing = _existing_checkpoint(checkpoint)
        if existing is not None:
            return existing
        payload = self._send(Request("GET", "/instruments/NSE", self._headers))
        self._validate_instrument_master(payload)
        return archive_response(self._root, request_record, payload, "success")

    def fresh_instruments(self) -> Archive:
        retrieved_at = datetime.now(UTC).isoformat()
        request_record = {
            "kind": "instruments",
            "exchange": "NSE",
            "purpose": "legacy-token-reuse-check",
            "retrieval_attempted_at_utc": retrieved_at,
        }
        payload = self._send(Request("GET", "/instruments/NSE", self._headers))
        self._validate_instrument_master(payload)
        return archive_response(self._root, request_record, payload, "success")

    @staticmethod
    def _validate_instrument_master(payload: bytes) -> None:
        lines = payload.decode("utf-8").splitlines()
        if not lines:
            raise SchemaFailure("empty instrument master")
        rows = list(csv.DictReader(lines))
        required = {"instrument_token", "tradingsymbol", "instrument_type", "segment", "exchange"}
        if not rows and not required.issubset(set(lines[0].split(","))):
            raise SchemaFailure("instrument master columns missing")
        if rows and not required.issubset(rows[0]):
            raise SchemaFailure("instrument master columns missing")

    def historical(
        self, instrument_token: int, interval: str, start: datetime, end: datetime
    ) -> Archive:
        validate_range(start, end)
        if interval not in ("day", "15minute"):
            raise ValueError("unsupported interval")
        request_record: dict[str, object] = {
            "kind": "historical",
            "instrument_token": instrument_token,
            "interval": interval,
            "from": start.isoformat(),
            "to": end.isoformat(),
        }
        checkpoint = _archive_paths(self._root, request_record)
        existing = _existing_checkpoint(checkpoint)
        if existing is not None:
            manifest = load_checkpoint(existing.manifest_path)
            if manifest.get("validation_class") == "structural":
                raise StructuralFailure(str(manifest["validation_reason"]))
            return existing
        query = urllib.parse.urlencode(
            {
                "from": start.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S"),
                "to": end.astimezone(IST).strftime("%Y-%m-%d %H:%M:%S"),
                "continuous": 0,
                "oi": 0,
            }
        )
        payload = self._send(
            Request(
                "GET",
                f"/instruments/historical/{instrument_token}/{interval}?{query}",
                self._headers,
            )
        )
        try:
            candles = _validate_historical(payload, start, end)
        except LockboxFailure:
            raise
        except CandleQualityFailure as exc:
            return archive_response(
                self._root,
                request_record,
                payload,
                "rejected",
                validation_reason=exc.reason,
                validation_class="quality",
            )
        except StructuralFailure as exc:
            archive_response(
                self._root,
                request_record,
                payload,
                "rejected",
                validation_reason=exc.reason,
                validation_class="structural",
            )
            raise
        coverage = {
            "count": len(candles),
            "first_timestamp": str(candles[0][0]) if candles else None,
            "last_timestamp": str(candles[-1][0]) if candles else None,
        }
        return archive_response(
            self._root,
            request_record,
            payload,
            "empty" if not candles else "success",
            coverage=coverage,
        )


def _validate_historical(payload: bytes, start: datetime, end: datetime) -> list[list[object]]:
    try:
        body = json.loads(payload)
        candles = body["data"]["candles"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        raise StructuralFailure("MALFORMED_JSON_OR_ENVELOPE") from None
    if not isinstance(candles, list):
        raise StructuralFailure("MALFORMED_JSON_OR_ENVELOPE")
    for candidate in candles:
        if not isinstance(candidate, list) or not candidate:
            continue
        try:
            timestamp = datetime.fromisoformat(str(candidate[0]))
        except ValueError:
            continue
        if timestamp.tzinfo is None:
            if timestamp.date() >= date(2023, 1, 1):
                raise LockboxFailure("LOCKBOX_DATA")
        elif timestamp.astimezone(IST).date() >= date(2023, 1, 1):
            raise LockboxFailure("LOCKBOX_DATA")
    if body.get("status") != "success":
        raise StructuralFailure("PROVIDER_STATUS_FAILURE")
    previous: datetime | None = None
    for candle in candles:
        if not isinstance(candle, list) or len(candle) not in (6, 7):
            raise StructuralFailure("INVALID_CANDLE_SHAPE")
        try:
            timestamp = datetime.fromisoformat(str(candle[0]))
        except ValueError:
            raise StructuralFailure("INVALID_TIMESTAMP_SYNTAX") from None
        timestamp_utc = timestamp.astimezone(UTC) if timestamp.tzinfo is not None else None
        if timestamp_utc is None:
            raise StructuralFailure("INVALID_TIMESTAMP_SYNTAX")
        if timestamp.astimezone(IST).date() >= date(2023, 1, 1):
            raise LockboxFailure("LOCKBOX_DATA")
        if not start <= timestamp_utc <= end:
            raise CandleQualityFailure("TIMESTAMP_OUT_OF_RANGE")
        if previous is not None and timestamp_utc <= previous:
            raise CandleQualityFailure("TIMESTAMPS_NOT_STRICTLY_INCREASING")
        previous = timestamp_utc
        values = candle[1:]
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) for value in values):
            raise StructuralFailure("INVALID_NUMERIC_TYPE")
        if any(not math.isfinite(value) for value in values):
            raise StructuralFailure("NONFINITE_NUMERIC")
        if any(value <= 0 for value in values[:4]):
            raise CandleQualityFailure("NON_POSITIVE_OHLC")
        open_price, high, low, close = values[:4]
        if low > high or not low <= open_price <= high or not low <= close <= high:
            raise CandleQualityFailure("INVALID_OHLC_ENVELOPE")
        if not isinstance(values[4], int) or isinstance(values[4], bool) or values[4] < 0:
            raise CandleQualityFailure("INVALID_VOLUME")
        if len(values) == 6 and (
            not isinstance(values[5], int) or isinstance(values[5], bool) or values[5] < 0
        ):
            raise CandleQualityFailure("INVALID_OI")
    return candles


def create_session(api_key: str, api_secret: str, request_token: str, transport: Transport) -> str:
    checksum = hashlib.sha256((api_key + request_token + api_secret).encode()).hexdigest()
    body = urllib.parse.urlencode(
        {"api_key": api_key, "request_token": request_token, "checksum": checksum}
    ).encode()
    payload = transport(Request("POST", "/session/token", {"X-Kite-Version": "3"}, body))
    try:
        result = json.loads(payload)["data"]["access_token"]
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError):
        raise AuthFailure("Kite session creation failed; acquisition halted") from None
    if not isinstance(result, str) or not TOKEN_PATTERN.fullmatch(result):
        raise AuthFailure("Kite session creation failed; acquisition halted")
    return result


def _resolve(rows: list[dict[str, str]], symbol: str) -> int | None:
    if symbol == "NIFTY50":
        # /instruments/NSE observed 2026-10-14 uses INDICES; older provider examples
        # use NSE-INDICES. Venue, EQ type and exact Nifty 50 identity stay required.
        matches = [
            r
            for r in rows
            if r["name"] == "NIFTY 50"
            and r["tradingsymbol"] == "NIFTY 50"
            and r["instrument_type"] == "EQ"
            and r["segment"] in {"INDICES", "NSE-INDICES"}
            and r["exchange"] == "NSE"
        ]
    else:
        matches = [
            r
            for r in rows
            if r["tradingsymbol"] == symbol
            and r["instrument_type"] == "EQ"
            and r["exchange"] == "NSE"
        ]
    if len(matches) > 1:
        raise SchemaFailure(f"non-unique instrument: {symbol}")
    return int(matches[0]["instrument_token"]) if matches else None


def _chunks(start: date, end: date, interval: str) -> list[tuple[datetime, datetime]]:
    output = []
    cursor = start
    days = DAILY_CHUNK_DAYS if interval == "day" else M15_CHUNK_DAYS
    while cursor <= end:
        chunk_end = min(cursor + timedelta(days=days - 1), end)
        output.append(
            (
                datetime.combine(cursor, datetime.min.time(), IST).astimezone(UTC),
                datetime.combine(
                    chunk_end, datetime.max.time().replace(microsecond=0), IST
                ).astimezone(UTC),
            )
        )
        cursor = chunk_end + timedelta(days=1)
    return output


def _quarantined_report_row(
    *,
    symbol: str,
    retrieval_kind: str,
    identity_status: str,
    instrument_token: int,
    interval: str,
    chunk_start: datetime,
    chunk_end: datetime,
    metadata: Mapping[str, Any],
) -> dict[str, object]:
    row: dict[str, object] = {
        "symbol": symbol,
        "retrieval_kind": retrieval_kind,
        "identity_status": identity_status,
        "instrument_token": instrument_token,
        "interval": interval,
        "requested_from": chunk_start.astimezone(IST).date().isoformat(),
        "requested_to": chunk_end.astimezone(IST).date().isoformat(),
        "result": metadata["result"],
        "request_identity_sha256": metadata["request_identity_sha256"],
        "provider_bytes_sha256": metadata["provider_bytes_sha256"],
    }
    if metadata["result"] == "rejected":
        row["validation_reason"] = metadata["validation_reason"]
    else:
        row.update(cast(Mapping[str, object], metadata["coverage"]))
    return row


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Isolated Kite historical acquisition")
    parser.add_argument("--mode", choices=("probe", "download"), default="probe")
    parser.add_argument("--symbols-file", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--history-start")
    parser.add_argument("--history-end")
    parser.add_argument("--legacy-token-file", type=Path)
    parser.add_argument("--legacy-token-sha256")
    parser.add_argument("--series-route-evidence-file", type=Path)
    parser.add_argument("--series-route-evidence-sha256")
    parser.add_argument("--export", type=Path, default=Path("/export"))
    parser.add_argument("--proxy", default="http://kite-proxy:8080")
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    if args.mode == "download":
        if args.symbols_file is None or args.provenance is None:
            parser.error("download requires --symbols-file and --provenance")
        requested_history_dates = validate_optional_history_dates(
            args.history_start, args.history_end
        )
        symbols = validate_symbol_file(args.symbols_file)
        provenance = validate_provenance(args.provenance, args.symbols_file)
        series_evidence = validate_series_route_evidence(
            provenance,
            symbols,
            args.series_route_evidence_file,
            args.series_route_evidence_sha256,
        )
        series_evidence_sha256 = None if series_evidence is None else series_evidence[0]
        series_evidence_tokens = {} if series_evidence is None else series_evidence[1]
        if (args.legacy_token_file is None) != (args.legacy_token_sha256 is None):
            parser.error("legacy token file and reviewed SHA-256 must be supplied together")
        legacy_routes = (
            []
            if args.legacy_token_file is None
            else validate_legacy_token_file(args.legacy_token_file, args.legacy_token_sha256)
        )
        if {route.requested_label for route in legacy_routes}.intersection(symbols):
            raise ValueError("duplicate requested label across routes")
        if series_evidence_sha256 is not None or legacy_routes:
            if requested_history_dates is None:
                raise ValueError(
                    "candidate routes require bounded history range 2022-11-29 through 2022-12-30"
                )
            history_start, history_end = validate_bounded_history_dates(
                args.history_start, args.history_end
            )
        elif requested_history_dates is None:
            history_start = None
            history_end = None
        else:
            history_start, history_end = requested_history_dates
    else:
        if any(
            value is not None
            for value in (
                args.symbols_file,
                args.provenance,
                args.history_start,
                args.history_end,
                args.legacy_token_file,
                args.legacy_token_sha256,
                args.series_route_evidence_file,
                args.series_route_evidence_sha256,
            )
        ):
            parser.error("probe mode does not accept download inputs")
        symbols = ["INFY", "NIFTY50"]
        provenance = None
        series_evidence_sha256 = None
        series_evidence_tokens = {}
        legacy_routes = []
        history_start = None
        history_end = None
    run_id = args.run_id or datetime.now(UTC).strftime("%Y%m%dT%H%M%S.%fZ")
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,80}", run_id):
        parser.error("run id contains unsafe characters")
    run_root = args.export / args.mode / run_id
    identity: dict[str, object] = {"mode": args.mode, "symbols": symbols}
    if provenance is not None:
        identity.update(
            {
                "symbols_sha256": provenance["output"]["sha256"],
                "provenance_sha256": hashlib.sha256(args.provenance.read_bytes()).hexdigest(),
                "classification": provenance["classification"],
                "source_panel": provenance["source"],
                "decoded_member": provenance["decoded_member"],
            }
        )
        if history_start is not None and history_end is not None:
            identity["history_start"] = history_start.isoformat()
            identity["history_end"] = history_end.isoformat()
    if series_evidence_sha256 is not None:
        identity["series_route_evidence_sha256"] = series_evidence_sha256
    if legacy_routes:
        identity["legacy_token_manifest_sha256"] = args.legacy_token_sha256.lower()
        identity["legacy_routes"] = [
            {
                "requested_label": route.requested_label,
                "historical_tradingsymbol": route.historical_tradingsymbol,
                "instrument_token": route.instrument_token,
                "nse_series": route.nse_series,
                "nse_isin": route.nse_isin,
                "evidence_url": route.evidence_url,
                "identity_status": "QUARANTINED_IDENTITY_UNPROVED",
            }
            for route in legacy_routes
        ]
        identity["fresh_master_required"] = True
    _bind_run(run_root, identity)
    if not sys.stdin.isatty():
        raise RuntimeError("interactive terminal required for hidden credential prompts")
    api_key = getpass.getpass("Kite API key: ")
    api_secret = getpass.getpass("Kite API secret: ")
    print(
        f"Open in your browser and log in manually: https://kite.zerodha.com/connect/login?v=3&api_key={urllib.parse.quote(api_key)}"
    )
    request_token = parse_callback_token(getpass.getpass("Request token or local callback URL: "))
    transport = urllib_transport(args.proxy)
    access_token = create_session(api_key, api_secret, request_token, transport)
    client = KiteClient(api_key, access_token, run_root, transport=transport)
    master_archive = client.fresh_instruments() if legacy_routes else client.instruments()
    master = master_archive.raw_path.read_text(encoding="utf-8").splitlines()
    rows = list(csv.DictReader(master))
    if legacy_routes:
        _validate_legacy_tokens_not_current(rows, legacy_routes)
    for symbol, expected_token in series_evidence_tokens.items():
        if _resolve(rows, symbol) != expected_token:
            raise SchemaFailure(f"series evidence token mismatch: {symbol}")
    unresolved: list[str] = []
    coverage: list[dict[str, object]] = []
    rejected_chunks: list[dict[str, object]] = []
    quarantined_routes: list[dict[str, object]] = []
    accepted_count = 0
    empty_count = 0
    if args.mode == "download":
        for probe_symbol in ("INFY", "NIFTY50"):
            probe_token = _resolve(rows, probe_symbol)
            if probe_token is None:
                raise SchemaFailure(f"required probe instrument unresolved: {probe_symbol}")
            probe_archive = client.historical(
                probe_token,
                "15minute",
                datetime(2022, 12, 26, tzinfo=IST).astimezone(UTC),
                datetime(2022, 12, 30, 23, 59, 59, tzinfo=IST).astimezone(UTC),
            )
            probe_metadata = load_checkpoint(probe_archive.manifest_path)
            if probe_metadata["result"] != "success" or probe_metadata["coverage"]["count"] == 0:
                raise SchemaFailure(f"required 2022 probe returned empty: {probe_symbol}")
    ranges = (
        [
            (date(2011, 1, 1), date(2022, 12, 31), "day"),
            (date(2015, 1, 1), date(2022, 12, 31), "15minute"),
        ]
        if history_start is None or history_end is None
        else [(history_start, history_end, "day"), (history_start, history_end, "15minute")]
    )
    selected = (
        ranges
        if args.mode == "download"
        else [
            (date(2011, 1, 3), date(2011, 1, 7), "day"),
            (date(2015, 1, 1), date(2015, 1, 31), "15minute"),
            (date(2022, 12, 26), date(2022, 12, 30), "15minute"),
        ]
    )
    for symbol in symbols:
        token = _resolve(rows, symbol)
        if token is None:
            unresolved.append(symbol)
            continue
        for start, end, interval in selected:
            for chunk_start, chunk_end in _chunks(start, end, interval):
                archive = client.historical(token, interval, chunk_start, chunk_end)
                metadata = load_checkpoint(archive.manifest_path)
                if series_evidence_sha256 is not None and symbol != "NIFTY50":
                    quarantined_routes.append(
                        _quarantined_report_row(
                            symbol=symbol,
                            retrieval_kind="current_series_candidate",
                            identity_status="QUARANTINED_SERIES_IDENTITY_UNPROVED",
                            instrument_token=token,
                            interval=interval,
                            chunk_start=chunk_start,
                            chunk_end=chunk_end,
                            metadata=metadata,
                        )
                    )
                    continue
                if metadata["result"] == "rejected":
                    rejected_chunks.append(
                        {
                            "symbol": symbol,
                            "interval": interval,
                            "requested_from": chunk_start.astimezone(IST).date().isoformat(),
                            "requested_to": chunk_end.astimezone(IST).date().isoformat(),
                            "request_identity_sha256": metadata["request_identity_sha256"],
                            "validation_reason": metadata["validation_reason"],
                            "provider_bytes_sha256": metadata["provider_bytes_sha256"],
                        }
                    )
                    continue
                if metadata["result"] == "success":
                    accepted_count += 1
                else:
                    empty_count += 1
                coverage.append(
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "requested_from": chunk_start.astimezone(IST).date().isoformat(),
                        "requested_to": chunk_end.astimezone(IST).date().isoformat(),
                        **metadata["coverage"],
                    }
                )
    for route in legacy_routes:
        for start, end, interval in ranges:
            for chunk_start, chunk_end in _chunks(start, end, interval):
                archive = client.historical(
                    route.instrument_token, interval, chunk_start, chunk_end
                )
                metadata = load_checkpoint(archive.manifest_path)
                quarantined_routes.append(
                    _quarantined_report_row(
                        symbol=route.requested_label,
                        retrieval_kind="legacy_token_candidate",
                        identity_status="QUARANTINED_IDENTITY_UNPROVED",
                        instrument_token=route.instrument_token,
                        interval=interval,
                        chunk_start=chunk_start,
                        chunk_end=chunk_end,
                        metadata=metadata,
                    )
                )
    quarantined_rejections = sum(row["result"] == "rejected" for row in quarantined_routes)
    master_metadata = load_checkpoint(master_archive.manifest_path)
    report = {
        "mode": args.mode,
        "requested_symbols": symbols,
        "legacy_requested_labels": [route.requested_label for route in legacy_routes],
        "unresolved_symbols": unresolved,
        "coverage": coverage,
        "rejected_chunks": rejected_chunks,
        "quarantined_routes": quarantined_routes,
        "counts": {
            "requested_symbols": len(symbols),
            "resolved_symbols": len(symbols) - len(unresolved),
            "unresolved_symbols": len(unresolved),
            "accepted_chunks": accepted_count,
            "empty_chunks": empty_count,
            "rejected_chunks": len(rejected_chunks),
            "quarantined_chunks": len(quarantined_routes),
            "requested_chunks": (
                accepted_count + empty_count + len(rejected_chunks) + len(quarantined_routes)
            ),
        },
        "staging_status": (
            "COMPLETED_WITH_REJECTIONS"
            if rejected_chunks or quarantined_rejections
            else "COMPLETED_UNQUALIFIED"
        ),
        "source_qualified": False,
        "request_list": (
            None
            if provenance is None
            else {
                "symbols_sha256": provenance["output"]["sha256"],
                "provenance_sha256": hashlib.sha256(args.provenance.read_bytes()).hexdigest(),
                "source_panel": provenance["source"],
                "decoded_member": provenance["decoded_member"],
                "classification": provenance["classification"],
                "series_route_evidence_sha256": series_evidence_sha256,
            }
        ),
        "fresh_master": (
            None
            if not legacy_routes
            else {
                "request_identity_sha256": master_metadata["request_identity_sha256"],
                "provider_bytes_sha256": master_metadata["provider_bytes_sha256"],
            }
        ),
        "note": "archive acquisition only; source qualification remains separate",
    }
    _atomic_write(run_root / "report.json", (json.dumps(report, indent=2) + "\n").encode())
    print(json.dumps({"mode": args.mode, "requested": len(symbols), "unresolved": len(unresolved)}))
    return 3 if rejected_chunks or quarantined_rejections else 0


def entrypoint() -> int:
    try:
        return main()
    except (AuthFailure, SchemaFailure, RuntimeError, TimeoutError, ValueError) as exc:
        if isinstance(exc, StructuralFailure):
            reason = exc.reason
        elif isinstance(exc, LockboxFailure):
            reason = "LOCKBOX_DATA"
        elif isinstance(exc, AuthFailure):
            reason = "AUTH_FAILURE"
        elif isinstance(exc, SchemaFailure):
            reason = "SCHEMA_OR_PREFLIGHT_FAILURE"
        else:
            reason = "NETWORK_OR_RUNTIME_FAILURE"
        print(json.dumps({"status": "failed", "reason_code": reason}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(entrypoint())
