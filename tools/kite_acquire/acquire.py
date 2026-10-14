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
LOCKBOX_START: Final = datetime(2023, 1, 1, tzinfo=UTC)
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


class AuthFailure(RuntimeError):
    pass


class SchemaFailure(RuntimeError):
    pass


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
) -> Archive:
    if len(payload) > MAX_RESPONSE_BYTES:
        raise ValueError("provider response exceeds size bound")
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
    _atomic_write(
        manifest_path,
        (json.dumps(manifest, sort_keys=True, indent=2) + "\n").encode("utf-8"),
    )
    return Archive(raw_path, manifest_path)


def load_checkpoint(path: Path) -> dict[str, Any]:
    manifest: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    raw = path.with_name("provider-response.raw")
    if hashlib.sha256(raw.read_bytes()).hexdigest() != manifest.get("provider_bytes_sha256"):
        raise ValueError("checkpoint provider-bytes hash mismatch")
    if hashlib.sha256(_canonical(manifest["request"])).hexdigest() != manifest.get(
        "request_identity_sha256"
    ):
        raise ValueError("checkpoint request hash mismatch")
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
        lines = payload.decode("utf-8").splitlines()
        if not lines:
            raise SchemaFailure("empty instrument master")
        rows = list(csv.DictReader(lines))
        required = {"instrument_token", "tradingsymbol", "instrument_type", "segment", "exchange"}
        if not rows and not required.issubset(set(lines[0].split(","))):
            raise SchemaFailure("instrument master columns missing")
        if rows and not required.issubset(rows[0]):
            raise SchemaFailure("instrument master columns missing")
        return archive_response(self._root, request_record, payload, "success")

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
        candles = _validate_historical(payload, start, end)
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
    except (UnicodeDecodeError, json.JSONDecodeError, KeyError, TypeError) as exc:
        raise SchemaFailure("malformed historical response") from exc
    if body.get("status") != "success" or not isinstance(candles, list):
        raise SchemaFailure("malformed historical response")
    previous: datetime | None = None
    for candle in candles:
        if not isinstance(candle, list) or len(candle) not in (6, 7):
            raise SchemaFailure("malformed candle shape")
        try:
            timestamp = datetime.fromisoformat(str(candle[0]))
        except ValueError as exc:
            raise SchemaFailure("malformed candle timestamp") from exc
        timestamp_utc = timestamp.astimezone(UTC) if timestamp.tzinfo is not None else None
        if timestamp_utc is None or not start <= timestamp_utc <= end:
            raise SchemaFailure("candle timestamp outside requested range")
        if previous is not None and timestamp_utc <= previous:
            raise SchemaFailure("candle timestamps are not strictly increasing")
        previous = timestamp_utc
        values = candle[1:]
        if any(
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            for value in values
        ):
            raise SchemaFailure("malformed candle values")
        if any(value <= 0 for value in values[:4]):
            raise SchemaFailure("non-positive OHLC value")
        open_price, high, low, close = values[:4]
        if low > high or not low <= open_price <= high or not low <= close <= high:
            raise SchemaFailure("invalid OHLC envelope")
        if not isinstance(values[4], int) or isinstance(values[4], bool) or values[4] < 0:
            raise SchemaFailure("volume must be a non-negative integer")
        if len(values) == 6 and (
            not isinstance(values[5], int) or isinstance(values[5], bool) or values[5] < 0
        ):
            raise SchemaFailure("open interest must be a non-negative integer")
    if candles and datetime.fromisoformat(str(candles[-1][0])).astimezone(UTC) >= LOCKBOX_START:
        raise ValueError("provider returned lockbox data")
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


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Isolated Kite historical acquisition")
    parser.add_argument("--mode", choices=("probe", "download"), default="probe")
    parser.add_argument("--symbols-file", type=Path)
    parser.add_argument("--provenance", type=Path)
    parser.add_argument("--export", type=Path, default=Path("/export"))
    parser.add_argument("--proxy", default="http://kite-proxy:8080")
    parser.add_argument("--run-id")
    args = parser.parse_args(argv)
    if args.mode == "download" and (args.symbols_file is None or args.provenance is None):
        parser.error("download requires --symbols-file and --provenance")
    symbols = (
        ["INFY", "NIFTY50"] if args.mode == "probe" else validate_symbol_file(args.symbols_file)
    )
    provenance = (
        None if args.mode == "probe" else validate_provenance(args.provenance, args.symbols_file)
    )
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
    master = client.instruments().raw_path.read_text(encoding="utf-8").splitlines()
    rows = list(csv.DictReader(master))
    unresolved: list[str] = []
    coverage: list[dict[str, object]] = []
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
            if load_checkpoint(probe_archive.manifest_path)["coverage"]["count"] == 0:
                raise SchemaFailure(f"required 2022 probe returned empty: {probe_symbol}")
    ranges = [
        (date(2011, 1, 1), date(2022, 12, 31), "day"),
        (date(2015, 1, 1), date(2022, 12, 31), "15minute"),
    ]
    for symbol in symbols:
        token = _resolve(rows, symbol)
        if token is None:
            unresolved.append(symbol)
            continue
        selected = (
            ranges
            if args.mode == "download"
            else [
                (date(2011, 1, 3), date(2011, 1, 7), "day"),
                (date(2015, 1, 1), date(2015, 1, 31), "15minute"),
                (date(2022, 12, 26), date(2022, 12, 30), "15minute"),
            ]
        )
        for start, end, interval in selected:
            for chunk_start, chunk_end in _chunks(start, end, interval):
                archive = client.historical(token, interval, chunk_start, chunk_end)
                metadata = load_checkpoint(archive.manifest_path)
                coverage.append(
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "requested_from": chunk_start.astimezone(IST).date().isoformat(),
                        "requested_to": chunk_end.astimezone(IST).date().isoformat(),
                        **metadata["coverage"],
                    }
                )
                print(
                    json.dumps(
                        {
                            "symbol": symbol,
                            "interval": interval,
                            "from": chunk_start.astimezone(IST).date().isoformat(),
                            "to": chunk_end.astimezone(IST).date().isoformat(),
                            "result": metadata["result"],
                            "bytes": metadata["provider_bytes_size"],
                        }
                    )
                )
    report = {
        "mode": args.mode,
        "requested_symbols": symbols,
        "unresolved_symbols": unresolved,
        "coverage": coverage,
        "request_list": (
            None
            if provenance is None
            else {
                "symbols_sha256": provenance["output"]["sha256"],
                "provenance_sha256": hashlib.sha256(args.provenance.read_bytes()).hexdigest(),
                "source_panel": provenance["source"],
                "decoded_member": provenance["decoded_member"],
                "classification": provenance["classification"],
            }
        ),
        "note": "archive acquisition only; source qualification remains separate",
    }
    (run_root / "report.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"mode": args.mode, "requested": len(symbols), "unresolved": len(unresolved)}))
    return 0


def entrypoint() -> int:
    try:
        return main()
    except (AuthFailure, SchemaFailure, RuntimeError, TimeoutError, ValueError) as exc:
        print(json.dumps({"status": "failed", "error_type": type(exc).__name__}), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(entrypoint())
