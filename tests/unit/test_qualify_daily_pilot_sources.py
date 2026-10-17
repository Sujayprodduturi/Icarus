from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from scripts import qualify_daily_pilot_sources as source_qa

LEGACY_COLUMNS = (
    "SYMBOL",
    "SERIES",
    "OPEN",
    "HIGH",
    "LOW",
    "CLOSE",
    "LAST",
    "PREVCLOSE",
    "TOTTRDQTY",
    "TOTTRDVAL",
    "TIMESTAMP",
    "TOTALTRADES",
    "ISIN",
)


def _raw_zip(*rows: dict[str, object], member: str = "cm30DEC2022bhav.csv") -> bytes:
    text = io.StringIO(newline="")
    writer = csv.DictWriter(text, fieldnames=LEGACY_COLUMNS, lineterminator="\n")
    writer.writeheader()
    for row in rows:
        complete: dict[str, object] = {
            "SYMBOL": "INFY",
            "SERIES": "EQ",
            "OPEN": "1500",
            "HIGH": "1510",
            "LOW": "1490",
            "CLOSE": "1505",
            "LAST": "1505",
            "PREVCLOSE": "1498",
            "TOTTRDQTY": "10",
            "TOTTRDVAL": "15050",
            "TIMESTAMP": "30-DEC-2022",
            "TOTALTRADES": "2",
            "ISIN": "INE009A01021",
        }
        complete.update(row)
        writer.writerow(complete)
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(member, text.getvalue().encode("utf-8"))
    return output.getvalue()


def _cache(rows: dict[str, list[object]]) -> bytes:
    return json.dumps({"schema": 2, "rows": rows}, separators=(",", ":")).encode()


def test_raw_date_prescan_rejects_non_eq_wrong_date_before_bad_eq_numeric() -> None:
    raw = _raw_zip(
        {"SYMBOL": "DEBT", "SERIES": "N1", "TIMESTAMP": "29-DEC-2022"},
        {"SYMBOL": "INFY", "OPEN": "not-a-number"},
    )

    with pytest.raises(source_qa.QualificationError, match="row date"):
        source_qa.parse_raw_archive(raw, "2022-12-30")


@pytest.mark.parametrize("bad_date", ["31-DEC-2022", "02-JAN-2023"])
def test_raw_date_prescan_rejects_wrong_or_2023_date(bad_date: str) -> None:
    with pytest.raises(source_qa.QualificationError, match="row date"):
        source_qa.parse_raw_archive(_raw_zip({"TIMESTAMP": bad_date}), "2022-12-30")


def test_raw_rejects_duplicate_identity_before_eq_selection() -> None:
    raw = _raw_zip(
        {"SYMBOL": "BOND", "SERIES": "N1"},
        {"SYMBOL": "BOND", "SERIES": "N1"},
    )

    with pytest.raises(source_qa.QualificationError, match="duplicate raw identity"):
        source_qa.parse_raw_archive(raw, "2022-12-30")


def test_raw_rejects_duplicate_csv_heading() -> None:
    text = (
        "SYMBOL,SERIES,OPEN,OPEN,HIGH,LOW,CLOSE,TOTTRDQTY,TOTTRDVAL,TIMESTAMP\n"
        "INFY,EQ,1500,1500,1510,1490,1505,10,15050,30-DEC-2022\n"
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("cm30DEC2022bhav.csv", text)

    with pytest.raises(source_qa.QualificationError, match="duplicate raw CSV heading"):
        source_qa.parse_raw_archive(output.getvalue(), "2022-12-30")


def test_raw_rejects_extra_row_field() -> None:
    text = (
        ",".join(LEGACY_COLUMNS)
        + "\n"
        + ",".join(
            [
                "INFY",
                "EQ",
                "1500",
                "1510",
                "1490",
                "1505",
                "1505",
                "1498",
                "10",
                "15050",
                "30-DEC-2022",
                "2",
                "INE009A01021",
                "unexpected",
            ]
        )
    )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("cm30DEC2022bhav.csv", text)

    with pytest.raises(source_qa.QualificationError, match="row shape"):
        source_qa.parse_raw_archive(output.getvalue(), "2022-12-30")


@pytest.mark.parametrize(
    ("row", "message"),
    [
        (["NaN", "1", "1", "1", "1", "1"], "finite"),
        ([True, "1", "1", "1", "1", "1"], "bool"),
        (["1", "2", "1", "3", "1", "1"], "OHLC"),
        (["1", "1", "1", "1", "-1", "1"], "volume"),
        (["1", "1", "1", "1", "1", None], "numeric"),
    ],
)
def test_cache_rejects_nonfinite_bool_and_domain_errors(row: list[object], message: str) -> None:
    with pytest.raises(source_qa.QualificationError, match=message):
        source_qa.parse_cache(_cache({"INFY": row}))


def test_cache_rejects_duplicate_symbol_key() -> None:
    raw = b'{"schema":2,"rows":{"INFY":["1","1","1","1","1","1"],"INFY":["1","1","1","1","1","1"]}}'

    with pytest.raises(source_qa.QualificationError, match="duplicate JSON key"):
        source_qa.parse_cache(raw)


def test_raw_cache_alignment_rejects_field_mismatch() -> None:
    raw = source_qa.parse_raw_archive(_raw_zip({}), "2022-12-30")
    cache = source_qa.parse_cache(_cache({"INFY": ["1500", "1510", "1490", "1504", "10", "15050"]}))

    with pytest.raises(source_qa.QualificationError, match="raw/cache field mismatch"):
        source_qa.require_raw_cache_alignment(raw.eq_rows, cache)


def test_file_pin_detects_mutation(tmp_path: Path) -> None:
    path = tmp_path / "input.bin"
    path.write_bytes(b"before")
    pin = source_qa.FilePin(
        role="test", path=path, size=6, sha256=hashlib.sha256(b"before").hexdigest()
    )
    assert source_qa.verify_file_pin(pin).sha256 == pin.sha256

    path.write_bytes(b"after")
    with pytest.raises(source_qa.QualificationError, match="pin mismatch"):
        source_qa.verify_file_pin(pin)


def test_calendar_scope_is_exact_and_stays_unqualified() -> None:
    resolved = [
        {
            "date": "2022-12-29",
            "market_wide_status": "REGULAR_SESSION_BASELINE",
        },
        {"date": "2022-12-30", "market_wide_status": "REGULAR_SESSION_BASELINE"},
        {"date": "2022-12-31", "market_wide_status": "CLOSED_WEEKEND_RULE"},
    ]
    certificate = {
        "calendar_qualified": False,
        "resolved_dates": resolved,
        "scope": {"start": "2021-01-01", "end": "2022-12-31"},
    }

    result = source_qa.validate_calendar_scope(
        certificate,
        required_dates=("2022-12-29", "2022-12-30"),
        included_statuses=("REGULAR_SESSION_BASELINE",),
    )

    assert result == {
        "required_dates": 2,
        "first_required_date": "2022-12-29",
        "last_required_date": "2022-12-30",
        "calendar_qualified": False,
        "required_dates_match_certificate": True,
    }


def test_fixed_income_override_keeps_other_etfs_counted() -> None:
    rows = [
        {"requested_name": "LIQUIDBEES", "status": "CONDITIONAL_QUALIFIES"},
        {"requested_name": "BANKBEES", "status": "BELOW_TURNOVER"},
        {"requested_name": "NIFTYBEES", "status": "CONDITIONAL_QUALIFIES"},
    ]

    changed = source_qa.apply_class_policy(rows)

    assert [row["status"] for row in changed] == [
        "CLASS_INELIGIBLE_FIXED_INCOME",
        "BELOW_TURNOVER",
        "CONDITIONAL_QUALIFIES",
    ]


def test_raw_and_cache_match_happy_path() -> None:
    raw = source_qa.parse_raw_archive(_raw_zip({}), "2022-12-30")
    cache = source_qa.parse_cache(_cache({"INFY": ["1500", "1510", "1490", "1505", "10", "15050"]}))

    assert source_qa.require_raw_cache_alignment(raw.eq_rows, cache) == 1
    assert raw.total_rows == 1
    assert raw.eq_rows_count == 1


def test_raw_cache_alignment_compares_finite_decimal_values() -> None:
    raw = source_qa.parse_raw_archive(_raw_zip({"OPEN": "1500.00"}), "2022-12-30")
    cache = source_qa.parse_cache(_cache({"INFY": [1500, "1510", "1490", "1505", "10", "15050"]}))

    assert source_qa.require_raw_cache_alignment(raw.eq_rows, cache) == 1


def test_pair_scan_records_one_bad_date_and_continues(tmp_path: Path) -> None:
    raw_bad = tmp_path / "raw-20221229.zip"
    raw_good = tmp_path / "raw-20221230.zip"
    cache_bad = tmp_path / "20221229.json"
    cache_good = tmp_path / "20221230.json"
    raw_bad.write_bytes(_raw_zip({"TIMESTAMP": "28-DEC-2022"}))
    raw_good.write_bytes(_raw_zip({}))
    cache_bad.write_bytes(_cache({"INFY": ["1500", "1510", "1490", "1505", "10", "15050"]}))
    cache_good.write_bytes(_cache({"INFY": ["1500", "1510", "1490", "1505", "10", "15050"]}))
    pairs = (
        source_qa.SourcePair("2022-12-29", raw_bad, cache_bad),
        source_qa.SourcePair("2022-12-30", raw_good, cache_good),
    )

    result = source_qa.scan_source_pairs(pairs)

    assert result["sessions_attempted"] == 2
    assert result["sessions_aligned"] == 1
    assert result["aligned_eq_rows"] == 1
    assert result["issues"] == [
        {
            "date": "2022-12-29",
            "stage": "raw",
            "reason": ("raw row date mismatch at CSV row 2: 2022-12-28 != 2022-12-29"),
        }
    ]


def test_inventory_pair_builder_requires_exact_ordered_dates(tmp_path: Path) -> None:
    inventory: dict[str, object] = {
        "required_interval": {
            "start": "2022-12-29",
            "end": "2022-12-30",
            "session_count": 2,
            "dates": ["2022-12-29", "2022-12-30"],
        },
        "raw_nse_archives": {
            "files": [
                {
                    "date": "2022-12-29",
                    "path": "raw/raw-20221229.zip",
                    "bytes": 1,
                    "sha256": "a" * 64,
                },
                {
                    "date": "2022-12-30",
                    "path": "raw/raw-20221230.zip",
                    "bytes": 2,
                    "sha256": "b" * 64,
                },
            ]
        },
        "daily_cache": {
            "files": [
                {
                    "date": "2022-12-29",
                    "path": "cache/20221229.json",
                    "bytes": 3,
                    "sha256": "c" * 64,
                },
                {
                    "date": "2022-12-30",
                    "path": "cache/20221230.json",
                    "bytes": 4,
                    "sha256": "d" * 64,
                },
            ]
        },
    }

    pins, pairs = source_qa.inventory_pairs(
        inventory,
        raw_dir=tmp_path / "raw",
        cache_dir=tmp_path / "cache",
        expected_start="2022-12-29",
        expected_end="2022-12-30",
        expected_sessions=2,
    )

    assert len(pins) == 4
    assert [pair.date for pair in pairs] == ["2022-12-29", "2022-12-30"]
    daily_cache = inventory["daily_cache"]
    assert isinstance(daily_cache, dict)
    files = daily_cache["files"]
    assert isinstance(files, list)
    files.reverse()
    with pytest.raises(source_qa.QualificationError, match="cache dates"):
        source_qa.inventory_pairs(
            inventory,
            raw_dir=tmp_path / "raw",
            cache_dir=tmp_path / "cache",
            expected_start="2022-12-29",
            expected_end="2022-12-30",
            expected_sessions=2,
        )


def test_pair_scan_reports_domain_failure_but_still_checks_exact_alignment(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw-20221230.zip"
    cache_path = tmp_path / "20221230.json"
    raw_path.write_bytes(
        _raw_zip(
            {"SYMBOL": "PENNY", "OPEN": "0", "HIGH": "0", "LOW": "0", "CLOSE": "0"},
            {"SYMBOL": "INFY"},
        )
    )
    cache_path.write_bytes(
        _cache(
            {
                "PENNY": ["0", "0", "0", "0", "10", "15050"],
                "INFY": ["1500", "1510", "1490", "1505", "10", "15050"],
            }
        )
    )

    result = source_qa.scan_source_pairs(
        (source_qa.SourcePair("2022-12-30", raw_path, cache_path),)
    )

    assert result["sessions_aligned"] == 1
    assert result["aligned_eq_rows"] == 2
    assert result["issues"] == [
        {
            "date": "2022-12-30",
            "stage": "raw_domain",
            "key": "PENNY",
            "reason": "raw[PENNY] price domain requires positive OHLC",
        },
        {
            "date": "2022-12-30",
            "stage": "cache_domain",
            "key": "PENNY",
            "reason": "cache[PENNY] price domain requires positive OHLC",
        },
    ]


def test_positive_subunit_source_aligns_but_is_research_sanity_excluded(tmp_path: Path) -> None:
    raw_path = tmp_path / "raw-20221230.zip"
    cache_path = tmp_path / "20221230.json"
    raw_path.write_bytes(
        _raw_zip({"SYMBOL": "PENNY", "OPEN": "0.5", "HIGH": "0.5", "LOW": "0.5", "CLOSE": "0.5"})
    )
    cache_path.write_bytes(_cache({"PENNY": ["0.50", "0.50", "0.50", "0.50", "10", "15050"]}))

    result = source_qa.scan_source_pairs(
        (source_qa.SourcePair("2022-12-30", raw_path, cache_path),)
    )

    assert result["sessions_aligned"] == 1
    assert result["aligned_eq_rows"] == 1
    assert result["raw_research_sanity_excluded_rows"] == 1
    assert result["cache_research_sanity_excluded_rows"] == 1
    assert result["issues"] == []
