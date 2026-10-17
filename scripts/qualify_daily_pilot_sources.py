"""Bounded offline qualification of the daily-pilot NSE source payloads.

This script inspects source data only.  It never imports a strategy, writes a trial,
computes a return, or contacts a provider.  Run the actual payload scan only in the
reviewed UID-10002, network-disabled container described in the operator record.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.util
import io
import json
import zipfile
from argparse import ArgumentParser
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, cast

LEGACY_REQUIRED_COLUMNS = (
    "SYMBOL",
    "SERIES",
    "OPEN",
    "HIGH",
    "LOW",
    "CLOSE",
    "TOTTRDQTY",
    "TOTTRDVAL",
    "TIMESTAMP",
)
LEGACY_OPTIONAL_COLUMNS = ("LAST", "PREVCLOSE", "TOTALTRADES", "ISIN", "")
FIXED_INCOME_DISPOSITION = "CLASS_INELIGIBLE_FIXED_INCOME"
_MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


class QualificationError(ValueError):
    """The selected source bundle failed a fail-closed qualification check."""


@dataclass(frozen=True)
class ValidatedRow:
    source_values: tuple[str, str, str, str, str, str]
    numeric_values: tuple[Decimal, Decimal, Decimal, Decimal, Decimal, Decimal]


@dataclass(frozen=True)
class RawDay:
    total_rows: int
    unique_identities: int
    eq_rows: dict[str, ValidatedRow]

    @property
    def eq_rows_count(self) -> int:
        return len(self.eq_rows)


@dataclass(frozen=True)
class RawSourceDay:
    total_rows: int
    unique_identities: int
    eq_rows: dict[str, tuple[str, str, str, str, str, str]]


@dataclass(frozen=True)
class FilePin:
    role: str
    path: Path
    size: int
    sha256: str
    display_path: str | None = None


@dataclass(frozen=True)
class FileState:
    role: str
    path: str
    size: int
    sha256: str

    def as_json(self) -> dict[str, object]:
        return {
            "role": self.role,
            "path": self.path,
            "bytes": self.size,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class SourcePair:
    date: str
    raw_path: Path
    cache_path: Path


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    output: dict[str, object] = {}
    for key, value in pairs:
        if key in output:
            raise QualificationError(f"duplicate JSON key: {key}")
        output[key] = value
    return output


def _reject_json_constant(value: str) -> object:
    raise QualificationError(f"non-finite JSON constant: {value}")


def strict_json_loads(raw: bytes) -> object:
    try:
        return json.loads(
            raw,
            object_pairs_hook=_unique_object,
            parse_constant=_reject_json_constant,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QualificationError(f"malformed JSON: {exc}") from exc


def _decimal(value: object, *, field: str) -> Decimal:
    if isinstance(value, bool):
        raise QualificationError(f"{field} must not be bool")
    if not isinstance(value, (str, int, float, Decimal)):
        raise QualificationError(f"{field} must be numeric")
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise QualificationError(f"{field} must be numeric") from exc
    if not parsed.is_finite():
        raise QualificationError(f"{field} must be finite")
    return parsed


def _numeric_row(row: object, *, label: str) -> ValidatedRow:
    if not isinstance(row, list) or len(row) != 6:
        raise QualificationError(f"{label} must contain exactly six fields")
    names = ("open", "high", "low", "close", "volume", "turnover")
    parsed = [
        _decimal(value, field=f"{label}.{name}") for name, value in zip(names, row, strict=True)
    ]
    open_, high, low, close, volume, turnover = parsed
    values = (open_, high, low, close, volume, turnover)
    source_values = cast(tuple[str, str, str, str, str, str], tuple(str(value) for value in row))
    return ValidatedRow(source_values=source_values, numeric_values=values)


def _validated_row(row: object, *, label: str) -> ValidatedRow:
    validated = _numeric_row(row, label=label)
    open_, high, low, close, volume, turnover = validated.numeric_values
    if min(open_, high, low, close) <= 0:
        raise QualificationError(f"{label} price domain requires positive OHLC")
    if volume < 0:
        raise QualificationError(f"{label} volume must be nonnegative")
    if turnover < 0:
        raise QualificationError(f"{label} turnover must be nonnegative")
    if not (low <= min(open_, close) and max(open_, close) <= high):
        raise QualificationError(f"{label} violates OHLC ordering")
    return validated


def _legacy_date(value: object) -> str:
    if not isinstance(value, str):
        raise QualificationError("raw row date must be text")
    pieces = value.strip().upper().split("-")
    if len(pieces) != 3 or pieces[1] not in _MONTHS:
        raise QualificationError(f"raw row date is malformed: {value!r}")
    try:
        day = int(pieces[0])
        year = int(pieces[2])
        from datetime import date

        parsed = date(year, _MONTHS[pieces[1]], day)
    except ValueError as exc:
        raise QualificationError(f"raw row date is malformed: {value!r}") from exc
    return parsed.isoformat()


def _raw_source_day(raw: bytes, expected_date: str) -> RawSourceDay:
    try:
        archive = zipfile.ZipFile(io.BytesIO(raw))
        names = archive.namelist()
        if len(names) != 1 or names[0].endswith("/"):
            raise QualificationError(
                f"raw archive must contain exactly one CSV member, got {len(names)}"
            )
        text = archive.read(names[0]).decode("utf-8")
    except (zipfile.BadZipFile, UnicodeDecodeError) as exc:
        raise QualificationError(f"raw archive is unreadable: {exc}") from exc

    reader = csv.DictReader(io.StringIO(text))
    fields = tuple(reader.fieldnames or ())
    duplicates = sorted({field for field in fields if fields.count(field) > 1})
    if duplicates:
        raise QualificationError(f"duplicate raw CSV heading: {duplicates}")
    missing = sorted(set(LEGACY_REQUIRED_COLUMNS) - set(fields))
    if missing:
        raise QualificationError(f"raw CSV header is missing required columns: {missing}")
    unknown = sorted(set(fields) - set(LEGACY_REQUIRED_COLUMNS) - set(LEGACY_OPTIONAL_COLUMNS))
    if unknown:
        raise QualificationError(f"raw CSV header has unknown columns: {unknown}")
    rows = list(reader)

    # D55 review requires this pass over every row, including non-EQ rows, before
    # numeric conversion or selection.
    for index, row in enumerate(rows, start=2):
        if None in row or any(row.get(field) is None for field in fields if field):
            raise QualificationError(f"raw CSV row shape mismatch at row {index}")
        if "" in row and row[""] not in (None, ""):
            raise QualificationError(f"raw CSV terminal field is nonempty at row {index}")
        actual_date = _legacy_date(row.get("TIMESTAMP"))
        if actual_date != expected_date or actual_date >= "2023-01-01":
            raise QualificationError(
                f"raw row date mismatch at CSV row {index}: {actual_date} != {expected_date}"
            )

    identities: set[tuple[str, str]] = set()
    eq_rows: dict[str, tuple[str, str, str, str, str, str]] = {}
    for index, row in enumerate(rows, start=2):
        symbol = (row.get("SYMBOL") or "").strip().upper()
        series = (row.get("SERIES") or "").strip().upper()
        if not symbol or not series:
            raise QualificationError(f"raw identity is blank at CSV row {index}")
        identity = (symbol, series)
        if identity in identities:
            raise QualificationError(f"duplicate raw identity at CSV row {index}: {identity}")
        identities.add(identity)
        if series != "EQ":
            continue
        if symbol in eq_rows:
            raise QualificationError(f"duplicate raw EQ symbol at CSV row {index}: {symbol}")
        eq_rows[symbol] = (
            row["OPEN"],
            row["HIGH"],
            row["LOW"],
            row["CLOSE"],
            row["TOTTRDQTY"],
            row["TOTTRDVAL"],
        )
    return RawSourceDay(total_rows=len(rows), unique_identities=len(identities), eq_rows=eq_rows)


def parse_raw_archive(raw: bytes, expected_date: str) -> RawDay:
    """Validate one legacy bhavcopy ZIP without extracting any archive member."""

    source = _raw_source_day(raw, expected_date)
    eq_rows = {
        symbol: _validated_row(list(row), label=f"raw[{symbol}]")
        for symbol, row in source.eq_rows.items()
    }
    return RawDay(
        total_rows=source.total_rows,
        unique_identities=source.unique_identities,
        eq_rows=eq_rows,
    )


def _cache_source_rows(raw: bytes) -> dict[str, list[object]]:
    payload = strict_json_loads(raw)
    if not isinstance(payload, dict) or payload.get("schema") != 2:
        raise QualificationError("cache schema must equal 2")
    rows = payload.get("rows")
    if not isinstance(rows, dict):
        raise QualificationError("cache rows must be an object")
    output: dict[str, list[object]] = {}
    for raw_symbol, row in rows.items():
        symbol = str(raw_symbol).strip().upper()
        if not symbol or symbol != raw_symbol:
            raise QualificationError(f"cache symbol is not canonical: {raw_symbol!r}")
        if not isinstance(row, list) or len(row) != 6:
            raise QualificationError(f"cache[{symbol}] must contain exactly six fields")
        output[symbol] = row
    return output


def parse_cache(raw: bytes) -> dict[str, ValidatedRow]:
    return {
        symbol: _validated_row(row, label=f"cache[{symbol}]")
        for symbol, row in _cache_source_rows(raw).items()
    }


def require_raw_cache_alignment(
    raw_rows: Mapping[str, ValidatedRow], cache_rows: Mapping[str, ValidatedRow]
) -> int:
    raw_keys = set(raw_rows)
    cache_keys = set(cache_rows)
    if raw_keys != cache_keys:
        missing = sorted(raw_keys - cache_keys)[:10]
        extra = sorted(cache_keys - raw_keys)[:10]
        raise QualificationError(
            f"raw/cache key mismatch: missing_cache={missing}, extra_cache={extra}"
        )
    for symbol in sorted(raw_keys):
        if raw_rows[symbol].numeric_values != cache_rows[symbol].numeric_values:
            raise QualificationError(f"raw/cache field mismatch for {symbol}")
    return len(raw_keys)


def verify_file_pin(pin: FilePin) -> FileState:
    try:
        raw = pin.path.read_bytes()
    except OSError as exc:
        raise QualificationError(f"cannot read pinned {pin.role} file: {pin.path}") from exc
    actual_hash = hashlib.sha256(raw).hexdigest()
    if len(raw) != pin.size or actual_hash != pin.sha256:
        raise QualificationError(f"pin mismatch for {pin.role}: {pin.path}")
    return FileState(
        role=pin.role,
        path=pin.display_path or pin.path.as_posix(),
        size=len(raw),
        sha256=actual_hash,
    )


def verify_file_pins(pins: Iterable[FilePin]) -> tuple[FileState, ...]:
    return tuple(verify_file_pin(pin) for pin in pins)


def validate_calendar_scope(
    certificate: object,
    *,
    required_dates: Sequence[str],
    included_statuses: Sequence[str],
) -> dict[str, object]:
    if not required_dates or len(required_dates) != len(set(required_dates)):
        raise QualificationError("required calendar dates must be nonempty and unique")
    if tuple(required_dates) != tuple(sorted(required_dates)):
        raise QualificationError("required calendar dates must be ordered")
    if any(day >= "2023-01-01" for day in required_dates):
        raise QualificationError("required calendar scope crosses into 2023")
    if not isinstance(certificate, dict):
        raise QualificationError("calendar certificate must be an object")
    resolved = certificate.get("resolved_dates")
    if not isinstance(resolved, list):
        raise QualificationError("calendar certificate resolved_dates must be a list")
    included = set(included_statuses)
    first, last = required_dates[0], required_dates[-1]
    observed: list[str] = []
    for record in resolved:
        if not isinstance(record, dict):
            raise QualificationError("calendar resolved date must be an object")
        day = record.get("date")
        status = record.get("market_wide_status")
        if isinstance(day, str) and first <= day <= last and status in included:
            observed.append(day)
    if observed != list(required_dates):
        raise QualificationError("required calendar dates differ from the bounded certificate")
    qualified = certificate.get("calendar_qualified")
    if not isinstance(qualified, bool):
        raise QualificationError("calendar_qualified must be boolean")
    return {
        "required_dates": len(required_dates),
        "first_required_date": first,
        "last_required_date": last,
        "calendar_qualified": qualified,
        "required_dates_match_certificate": True,
    }


def apply_class_policy(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for item in rows:
        row = dict(item)
        if row.get("requested_name") == "LIQUIDBEES":
            row["status"] = FIXED_INCOME_DISPOSITION
            row["qualifying_observed_symbols"] = []
        output.append(row)
    return output


def _inventory_file_rows(inventory: Mapping[str, object], group: str) -> list[dict[str, object]]:
    value = inventory.get(group)
    if not isinstance(value, dict) or not isinstance(value.get("files"), list):
        raise QualificationError(f"source inventory {group}.files must be a list")
    rows = value["files"]
    if not all(isinstance(item, dict) for item in rows):
        raise QualificationError(f"source inventory {group}.files contains a non-object")
    return cast(list[dict[str, object]], rows)


def inventory_pairs(
    inventory: Mapping[str, object],
    *,
    raw_dir: Path,
    cache_dir: Path,
    expected_start: str,
    expected_end: str,
    expected_sessions: int,
) -> tuple[tuple[FilePin, ...], tuple[SourcePair, ...]]:
    interval = inventory.get("required_interval")
    if not isinstance(interval, dict):
        raise QualificationError("source inventory required_interval must be an object")
    dates = interval.get("dates")
    if not isinstance(dates, list) or not all(isinstance(day, str) for day in dates):
        raise QualificationError("source inventory dates must be strings")
    if (
        interval.get("start") != expected_start
        or interval.get("end") != expected_end
        or interval.get("session_count") != expected_sessions
        or len(dates) != expected_sessions
        or dates[0] != expected_start
        or dates[-1] != expected_end
        or dates != sorted(set(dates))
        or any(day >= "2023-01-01" for day in dates)
    ):
        raise QualificationError("source inventory interval is not the exact approved scope")
    raw_rows = _inventory_file_rows(inventory, "raw_nse_archives")
    cache_rows = _inventory_file_rows(inventory, "daily_cache")
    raw_dates = [row.get("date") for row in raw_rows]
    cache_dates = [row.get("date") for row in cache_rows]
    if raw_dates != dates:
        raise QualificationError("source inventory raw dates differ from required dates")
    if cache_dates != dates:
        raise QualificationError("source inventory cache dates differ from required dates")

    pins: list[FilePin] = []
    pairs: list[SourcePair] = []
    for day, raw_row, cache_row in zip(dates, raw_rows, cache_rows, strict=True):
        compact = day.replace("-", "")
        raw_name = f"raw-{compact}.zip"
        cache_name = f"{compact}.json"
        if Path(str(raw_row.get("path"))).name != raw_name:
            raise QualificationError(f"unexpected raw filename for {day}")
        if Path(str(cache_row.get("path"))).name != cache_name:
            raise QualificationError(f"unexpected cache filename for {day}")
        raw_path = raw_dir / raw_name
        cache_path = cache_dir / cache_name
        raw_pin = _file_pin_from_inventory("raw", raw_path, raw_row)
        cache_pin = _file_pin_from_inventory("cache", cache_path, cache_row)
        pins.extend((raw_pin, cache_pin))
        pairs.append(SourcePair(day, raw_path, cache_path))
    return tuple(pins), tuple(pairs)


def _file_pin_from_inventory(role: str, actual_path: Path, row: Mapping[str, object]) -> FilePin:
    size = row.get("bytes")
    sha256 = row.get("sha256")
    display_path = row.get("path")
    if (
        not isinstance(size, int)
        or isinstance(size, bool)
        or size < 0
        or not isinstance(sha256, str)
        or len(sha256) != 64
        or not isinstance(display_path, str)
    ):
        raise QualificationError(f"malformed {role} file pin for {display_path}")
    return FilePin(
        role=role,
        path=actual_path,
        size=size,
        sha256=sha256,
        display_path=display_path,
    )


def scan_source_pairs(pairs: Sequence[SourcePair]) -> dict[str, object]:
    issues: list[dict[str, str]] = []
    per_session: list[dict[str, object]] = []
    aligned_sessions = 0
    aligned_eq_rows = 0
    total_raw_rows = 0
    total_raw_eq_rows = 0
    total_cache_rows = 0
    raw_research_sanity_excluded_rows = 0
    cache_research_sanity_excluded_rows = 0
    for pair in pairs:
        raw_day: RawSourceDay | None = None
        cache_rows: dict[str, list[object]] | None = None
        try:
            raw_day = _raw_source_day(pair.raw_path.read_bytes(), pair.date)
            total_raw_rows += raw_day.total_rows
            total_raw_eq_rows += len(raw_day.eq_rows)
        except (OSError, QualificationError) as exc:
            issues.append({"date": pair.date, "stage": "raw", "reason": str(exc)})
        try:
            cache_rows = _cache_source_rows(pair.cache_path.read_bytes())
            total_cache_rows += len(cache_rows)
        except (OSError, QualificationError) as exc:
            issues.append({"date": pair.date, "stage": "cache", "reason": str(exc)})
        if raw_day is None or cache_rows is None:
            continue
        raw_numeric: dict[str, ValidatedRow] = {}
        cache_numeric: dict[str, ValidatedRow] = {}
        for symbol, raw_row in raw_day.eq_rows.items():
            try:
                numeric = _numeric_row(list(raw_row), label=f"raw[{symbol}]")
                raw_numeric[symbol] = numeric
                validated = _validated_row(list(raw_row), label=f"raw[{symbol}]")
                if min(validated.numeric_values[:4]) < Decimal("1"):
                    raw_research_sanity_excluded_rows += 1
            except QualificationError as exc:
                issues.append(
                    {
                        "date": pair.date,
                        "stage": "raw_domain",
                        "key": symbol,
                        "reason": str(exc),
                    }
                )
        for symbol, cache_row in cache_rows.items():
            try:
                numeric = _numeric_row(cache_row, label=f"cache[{symbol}]")
                cache_numeric[symbol] = numeric
                validated = _validated_row(cache_row, label=f"cache[{symbol}]")
                if min(validated.numeric_values[:4]) < Decimal("1"):
                    cache_research_sanity_excluded_rows += 1
            except QualificationError as exc:
                issues.append(
                    {
                        "date": pair.date,
                        "stage": "cache_domain",
                        "key": symbol,
                        "reason": str(exc),
                    }
                )
        raw_keys = set(raw_day.eq_rows)
        cache_keys = set(cache_rows)
        if raw_keys != cache_keys:
            issues.append(
                {
                    "date": pair.date,
                    "stage": "alignment",
                    "reason": (
                        "raw/cache key mismatch: "
                        f"missing_cache={sorted(raw_keys - cache_keys)[:10]}, "
                        f"extra_cache={sorted(cache_keys - raw_keys)[:10]}"
                    ),
                }
            )
            continue
        comparable_keys = raw_keys & cache_keys & set(raw_numeric) & set(cache_numeric)
        mismatch = next(
            (
                symbol
                for symbol in sorted(comparable_keys)
                if raw_numeric[symbol].numeric_values != cache_numeric[symbol].numeric_values
            ),
            None,
        )
        if mismatch is not None:
            issues.append(
                {
                    "date": pair.date,
                    "stage": "alignment",
                    "key": mismatch,
                    "reason": f"raw/cache field mismatch for {mismatch}",
                }
            )
            continue
        if len(comparable_keys) != len(raw_keys):
            issues.append(
                {
                    "date": pair.date,
                    "stage": "alignment",
                    "reason": "raw/cache numeric alignment unavailable for invalid source rows",
                }
            )
            continue
        aligned = len(comparable_keys)
        aligned_sessions += 1
        aligned_eq_rows += aligned
        per_session.append(
            {
                "date": pair.date,
                "raw_rows": raw_day.total_rows,
                "raw_unique_identities": raw_day.unique_identities,
                "raw_eq_rows": len(raw_day.eq_rows),
                "cache_rows": len(cache_rows),
                "aligned_eq_rows": aligned,
            }
        )
    return {
        "sessions_attempted": len(pairs),
        "sessions_aligned": aligned_sessions,
        "raw_rows": total_raw_rows,
        "raw_eq_rows": total_raw_eq_rows,
        "cache_rows": total_cache_rows,
        "aligned_eq_rows": aligned_eq_rows,
        "raw_research_sanity_excluded_rows": raw_research_sanity_excluded_rows,
        "cache_research_sanity_excluded_rows": cache_research_sanity_excluded_rows,
        "per_session": per_session,
        "issues": issues,
    }


def validate_requested_labels(
    payload: object,
    *,
    expected_count: int,
    expected_matrix_sha256: str,
) -> list[dict[str, Any]]:
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise QualificationError("requested-label inventory schema must equal 1")
    records = payload.get("records")
    if (
        payload.get("requested_count") != expected_count
        or not isinstance(records, list)
        or len(records) != expected_count
        or payload.get("source_matrix_sha256") != expected_matrix_sha256
    ):
        raise QualificationError("requested-label inventory count or source binding differs")
    output: list[dict[str, Any]] = []
    names: set[str] = set()
    for item in records:
        if not isinstance(item, dict):
            raise QualificationError("requested-label record must be an object")
        name = item.get("requested_name")
        candidates = item.get("candidate_symbols")
        current = item.get("current_mapping_present")
        if (
            not isinstance(name, str)
            or not name
            or name != name.upper()
            or name in names
            or not isinstance(candidates, list)
            or not candidates
            or not all(
                isinstance(symbol, str) and symbol and symbol == symbol.upper()
                for symbol in candidates
            )
            or len(candidates) != len(set(candidates))
            or not isinstance(current, bool)
        ):
            raise QualificationError(f"malformed or duplicate requested-label record: {name!r}")
        names.add(name)
        output.append(dict(item))
    required = {"LIQUIDBEES", "BANKBEES", "NIFTYBEES"}
    if not required <= names:
        raise QualificationError("requested-label inventory lacks required ETF class controls")
    return output


def _load_module(path: Path, expected_sha256: str) -> Any:
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise QualificationError("eligibility helper pin mismatch")
    spec = importlib.util.spec_from_file_location("approved_daily_eligibility", path)
    if spec is None or spec.loader is None:
        raise QualificationError("eligibility helper cannot be loaded")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for name in ("goal_thresholds", "screen_requests", "validate_cache"):
        if not callable(getattr(module, name, None)):
            raise QualificationError(f"eligibility helper lacks {name}")
    return module


def build_eligibility_report(
    *,
    helper: Any,
    helper_sha256: str,
    records: list[dict[str, Any]],
    required_dates: Sequence[str],
    cache_paths: Mapping[str, Path],
    goal_raw: bytes,
    source_issue_count: int,
) -> dict[str, object]:
    min_turnover, window_size, min_close = helper.goal_thresholds(goal_raw)
    if window_size != 20:
        raise QualificationError("approved eligibility config no longer uses 20 sessions")
    pilot_dates = (
        "2022-12-26",
        "2022-12-27",
        "2022-12-28",
        "2022-12-29",
        "2022-12-30",
    )
    rows_by_day: dict[str, dict[str, tuple[Decimal, Decimal]]] = {}
    sessions = list(required_dates)
    needed: set[str] = set()
    for day in pilot_dates:
        try:
            position = sessions.index(day)
        except ValueError as exc:
            raise QualificationError(
                f"pilot date missing from approved source interval: {day}"
            ) from exc
        window = sessions[position - window_size + 1 : position + 1]
        if len(window) != window_size:
            raise QualificationError(f"incomplete approved eligibility window for {day}")
        needed.update(window)
    for day in sorted(needed):
        cache_payload = strict_json_loads(cache_paths[day].read_bytes())
        rows_by_day[day] = helper.validate_cache(cache_payload)

    dates: dict[str, object] = {}
    for day in pilot_dates:
        position = sessions.index(day)
        window = sessions[position - window_size + 1 : position + 1]
        screened = helper.screen_requests(
            records,
            window,
            rows_by_day,
            min_close,
            min_turnover,
        )
        source_rows = screened.get("results")
        if not isinstance(source_rows, list) or len(source_rows) != len(records):
            raise QualificationError(f"eligibility helper lost requested labels on {day}")
        annotated: list[dict[str, Any]] = []
        for source_row in source_rows:
            if not isinstance(source_row, dict) or not isinstance(source_row.get("status"), str):
                raise QualificationError(f"eligibility helper emitted malformed row on {day}")
            row = dict(source_row)
            row["source_screen_status"] = row["status"]
            annotated.append(row)
        result_rows = apply_class_policy(annotated)
        names = [row.get("requested_name") for row in result_rows]
        if len(set(names)) != len(records):
            raise QualificationError(f"eligibility helper duplicated requested labels on {day}")
        counts: dict[str, int] = {}
        for row in result_rows:
            status = str(row["status"])
            counts[status] = counts.get(status, 0) + 1
        if sum(counts.values()) != len(records):
            raise QualificationError(f"eligibility counts do not reconcile on {day}")
        dates[day] = {
            "inclusive_window_start": window[0],
            "inclusive_window_sessions": len(window),
            "status_counts": dict(sorted(counts.items())),
            "conditional_qualified_requested_names": sorted(
                str(row["requested_name"])
                for row in result_rows
                if row["status"]
                in {"CONDITIONAL_QUALIFIES", "AMBIGUOUS_MULTIPLE_QUALIFYING_ALIASES"}
            ),
            "shared_qualified_symbols": screened.get("shared_qualified_symbols", {}),
            "all_693_results": result_rows,
        }
    return {
        "status": "CONDITIONAL_PRICE_LIQUIDITY_SCREEN_REPRODUCED",
        "source_payload_issues_recorded_before_screen": source_issue_count,
        "admission_from_this_screen": False,
        "helper_sha256": helper_sha256,
        "requested_labels_retained": len(records),
        "thresholds": {
            "turnover_window_sessions": window_size,
            "min_avg_turnover_inr": str(min_turnover),
            "min_close_inr": str(min_close),
        },
        "window_convention": (
            "20 observed sessions ending at and including the decision date; "
            "current-day close; >= comparisons"
        ),
        "class_policy": {
            "LIQUIDBEES": FIXED_INCOME_DISPOSITION,
            "BANKBEES": "ordinary counted source-screen disposition retained",
            "NIFTYBEES": "ordinary counted source-screen disposition retained",
        },
        "dates": dates,
    }


def _control_pin(source_inventory: Mapping[str, object], role: str, actual_path: Path) -> FilePin:
    controls = source_inventory.get("control_files")
    if not isinstance(controls, list):
        raise QualificationError("source inventory control_files must be a list")
    matches = [item for item in controls if isinstance(item, dict) and item.get("role") == role]
    if len(matches) != 1:
        raise QualificationError(f"source inventory must contain one control role {role}")
    return _file_pin_from_inventory(role, actual_path, matches[0])


def _publish_once(path: Path, value: Mapping[str, object]) -> tuple[int, str]:
    payload = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as handle:
        handle.write(payload)
    return len(payload), hashlib.sha256(payload).hexdigest()


def qualify(args: Any) -> dict[str, object]:
    inventory_raw = args.inventory.read_bytes()
    inventory_hash = hashlib.sha256(inventory_raw).hexdigest()
    if inventory_hash != args.inventory_sha256:
        raise QualificationError("source inventory pin mismatch")
    inventory = strict_json_loads(inventory_raw)
    if not isinstance(inventory, dict):
        raise QualificationError("source inventory must be an object")
    pins, pairs = inventory_pairs(
        inventory,
        raw_dir=args.raw_dir,
        cache_dir=args.cache_dir,
        expected_start="2021-12-21",
        expected_end="2022-12-30",
        expected_sessions=257,
    )
    control_args = dict(args.control)
    expected_roles = {
        item["role"]
        for item in inventory.get("control_files", [])
        if isinstance(item, dict) and isinstance(item.get("role"), str)
    }
    if set(control_args) != expected_roles:
        raise QualificationError("explicit control mounts differ from source inventory roles")
    control_pins = tuple(
        _control_pin(inventory, role, Path(control_args[role])) for role in sorted(expected_roles)
    )
    warmup_pin = next(pin for pin in control_pins if pin.role == "reviewed_warmup_inventory")
    warmup_raw = warmup_pin.path.read_bytes()
    warmup = strict_json_loads(warmup_raw)
    if not isinstance(warmup, dict):
        raise QualificationError("warmup inventory must be an object")
    universe = warmup.get("universe")
    if not isinstance(universe, dict) or not isinstance(universe.get("goal_yaml_sha256"), str):
        raise QualificationError("warmup inventory lacks goal.yaml pin")
    goal_raw = args.goal.read_bytes()
    goal_hash = hashlib.sha256(goal_raw).hexdigest()
    if goal_hash != universe["goal_yaml_sha256"]:
        raise QualificationError("goal.yaml pin mismatch")
    helper_raw = args.eligibility_helper.read_bytes()
    helper_hash = hashlib.sha256(helper_raw).hexdigest()
    if helper_hash != args.eligibility_helper_sha256:
        raise QualificationError("eligibility helper pin mismatch")

    extra_pins = (
        FilePin(
            "source_inventory",
            args.inventory,
            len(inventory_raw),
            args.inventory_sha256,
            "var/daily-descriptive-pilot/2026-10-16/source-inventory/source-inventory.json",
        ),
        FilePin("goal_yaml", args.goal, len(goal_raw), goal_hash, "goal.yaml"),
        FilePin(
            "approved_eligibility_helper",
            args.eligibility_helper,
            len(helper_raw),
            helper_hash,
            "var/kite-qualification/2026-10-15/pilot-universe-qa/screen.py",
        ),
    )
    all_pins = (*pins, *control_pins, *extra_pins)
    before = verify_file_pins(all_pins)

    calendar_pin = next(pin for pin in control_pins if pin.role == "reviewed_calendar_certificate")
    calendar = strict_json_loads(calendar_pin.path.read_bytes())
    interval = inventory["required_interval"]
    if not isinstance(interval, dict):
        raise QualificationError("source inventory interval is malformed")
    required_dates = interval["dates"]
    if not isinstance(required_dates, list):
        raise QualificationError("source inventory dates are malformed")
    calendar_info = validate_calendar_scope(
        calendar,
        required_dates=required_dates,
        included_statuses=interval["included_calendar_statuses"],
    )

    label_pin = next(pin for pin in control_pins if pin.role == "original_693_label_inventory")
    label_payload = strict_json_loads(label_pin.path.read_bytes())
    inventory_universe = inventory.get("universe")
    if not isinstance(inventory_universe, dict):
        raise QualificationError("source inventory universe is malformed")
    records = validate_requested_labels(
        label_payload,
        expected_count=693,
        expected_matrix_sha256=str(inventory_universe.get("source_matrix_sha256")),
    )

    source_scan = scan_source_pairs(pairs)
    source_issues = source_scan["issues"]
    if not isinstance(source_issues, list):
        raise QualificationError("source scan issues are malformed")
    helper = _load_module(args.eligibility_helper, helper_hash)
    eligibility = build_eligibility_report(
        helper=helper,
        helper_sha256=helper_hash,
        records=records,
        required_dates=required_dates,
        cache_paths={pair.date: pair.cache_path for pair in pairs},
        goal_raw=goal_raw,
        source_issue_count=len(source_issues),
    )
    after = verify_file_pins(all_pins)
    if before != after:
        raise QualificationError("selected input state changed during qualification")
    payload_checks_pass = not source_issues and source_scan["sessions_aligned"] == 257
    return {
        "schema_version": 1,
        "as_of": args.as_of,
        "created_at_utc": datetime.now(UTC).isoformat(),
        "status": (
            "SOURCE_PAYLOAD_QA_PASS_OTHER_ADMISSION_GATES_OPEN"
            if payload_checks_pass
            else "SOURCE_PAYLOAD_QA_FAIL"
        ),
        "payload_checks_pass": payload_checks_pass,
        "data_qualified": False,
        "run_authorized": False,
        "scope": {
            "start": "2021-12-21",
            "end": "2022-12-30",
            "sessions": 257,
            "raw_files": 257,
            "cache_files": 257,
            "requested_labels": 693,
            "pilot_dates": 5,
        },
        "source_inventory_sha256": inventory_hash,
        "input_state_before": [state.as_json() for state in before],
        "input_state_after": [state.as_json() for state in after],
        "input_state_unchanged": True,
        "calendar_control": calendar_info,
        "source_scan": source_scan,
        "eligibility": eligibility,
        "boundaries": {
            "prices_returns_fills_pnl_emitted": False,
            "strategy_evaluated": False,
            "trial_ledger_used": False,
            "network_used": False,
            "provider_contacted": False,
            "lockbox_2023_accessed": False,
            "overall_admission_still_requires": [
                "calendar admission",
                "corporate-action basis",
                "point-in-time identity and class",
                "applicable source-use and retention disposition",
            ],
        },
    }


def _parse_control(value: str) -> tuple[str, str]:
    role, separator, path = value.partition("=")
    if not separator or not role or not path:
        raise ValueError("control must be ROLE=PATH")
    return role, path


def main() -> None:
    parser = ArgumentParser()
    parser.add_argument("--inventory", type=Path, required=True)
    parser.add_argument("--inventory-sha256", required=True)
    parser.add_argument("--raw-dir", type=Path, required=True)
    parser.add_argument("--cache-dir", type=Path, required=True)
    parser.add_argument("--control", action="append", type=_parse_control, required=True)
    parser.add_argument("--goal", type=Path, required=True)
    parser.add_argument("--eligibility-helper", type=Path, required=True)
    parser.add_argument("--eligibility-helper-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--as-of", default="2026-10-17")
    args = parser.parse_args()
    try:
        report = qualify(args)
    except Exception as exc:
        failure = {
            "schema_version": 1,
            "as_of": args.as_of,
            "created_at_utc": datetime.now(UTC).isoformat(),
            "status": "SOURCE_PAYLOAD_QA_FAIL",
            "payload_checks_pass": False,
            "data_qualified": False,
            "run_authorized": False,
            "fatal_error": f"{type(exc).__name__}: {exc}",
        }
        size, digest = _publish_once(args.output, failure)
        print(json.dumps({"status": failure["status"], "bytes": size, "sha256": digest}))
        raise SystemExit(2) from exc
    size, digest = _publish_once(args.output, report)
    source_scan = cast(Mapping[str, object], report["source_scan"])
    print(
        json.dumps(
            {
                "status": report["status"],
                "bytes": size,
                "sha256": digest,
                "sessions_aligned": source_scan["sessions_aligned"],
            },
            sort_keys=True,
        )
    )
    if not report["payload_checks_pass"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
