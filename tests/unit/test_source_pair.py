from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal

import pytest

from icarus.engine.source_pair import (
    PairRefusal,
    parse_source_pair_qualification,
    reconcile_source_pair,
    validate_source_pair_identities,
)


def _raw(**changes: object) -> bytes:
    value: dict[str, object] = {
        "schema_version": 1,
        "pair_id": "invented-pair-v1",
        "reviewer": "independent-invented-reviewer",
        "approved_at": "2026-10-15T01:00:00Z",
        "effective_start": "2020-01-01T00:00:00Z",
        "effective_end": "2022-12-31T23:59:59Z",
        "daily_sha256": "a" * 64,
        "m15_sha256": "b" * 64,
        "action_sha256": "c" * 64,
        "calendar_sha256": "d" * 64,
        "daily_source": {"vendor": "NSE_OFFICIAL_DAILY", "source_revision": "r1"},
        "m15_source": {"vendor": "INDEPENDENT_VENDOR_M15", "source_revision": "r1"},
        "daily_close_rule": "OFFICIAL_SESSION_CLOSE",
        "m15_capture_rule": "VENDOR_INTERVAL_CAPTURE_V1",
        "session_rule": "PINNED_NSE_CALENDAR_V1",
        "price_basis": {
            "split": "BACK_ADJUSTED",
            "bonus": "BACK_ADJUSTED",
            "rights": "BACK_ADJUSTED",
            "dividend": "UNADJUSTED",
        },
        "relations": {"open": "EQUAL", "extrema_containment": "SUPPORTED", "volume": "EQUAL"},
        "mappings": [
            {
                "symbol": "S0",
                "isin": "INE000000001",
                "daily_symbol": "S0",
                "m15_symbol": "S0",
                "m15_token": "vendor-101",
                "lineage_sha256": "e" * 64,
                "split_factor": "1",
                "bonus_factor": "1",
                "rights_factor": "1",
                "effective_start": "2020-01-01T00:00:00Z",
                "effective_end": "2022-12-31T23:59:59Z",
            }
        ],
        "invented": False,
    }
    value.update(changes)
    return json.dumps(value, separators=(",", ":")).encode()


def test_pair_qualification_binds_independent_sources_and_effective_mapping() -> None:
    pair = parse_source_pair_qualification(_raw())
    assert pair.daily_source != pair.m15_source
    assert pair.mapping_for("S0", datetime(2021, 1, 4, tzinfo=UTC)).m15_token == "vendor-101"


@pytest.mark.parametrize(
    ("change", "code"),
    [
        (
            {"daily_source": {"vendor": "INDEPENDENT_VENDOR_M15", "source_revision": "r1"}},
            "PAIR_SOURCE_IDENTITY",
        ),
        (
            {"relations": {"open": "EQUAL", "extrema_containment": "UNKNOWN", "volume": "EQUAL"}},
            "PAIR_RELATION",
        ),
        ({"invented": True}, "PAIR_INVENTED"),
    ],
)
def test_pair_qualification_refuses_duplicate_unknown_or_self_qualified(
    change: dict[str, object], code: str
) -> None:
    with pytest.raises(PairRefusal, match=code):
        parse_source_pair_qualification(_raw(**change))


def test_different_daily_close_passes_only_when_extrema_are_contained() -> None:
    pair = parse_source_pair_qualification(_raw())
    reconcile_source_pair(
        pair,
        symbol="S0",
        session_open=datetime(2021, 1, 4, 3, 45, tzinfo=UTC),
        session_close=datetime(2021, 1, 4, 10, tzinfo=UTC),
        daily=(Decimal("100"), Decimal("110"), Decimal("90"), Decimal("108"), Decimal("1000")),
        m15=(Decimal("100"), Decimal("109"), Decimal("91"), Decimal("107"), Decimal("1000")),
    )
    with pytest.raises(PairRefusal, match="PAIR_EXTREMA_CONTAINMENT"):
        reconcile_source_pair(
            pair,
            symbol="S0",
            session_open=datetime(2021, 1, 4, 3, 45, tzinfo=UTC),
            session_close=datetime(2021, 1, 4, 10, tzinfo=UTC),
            daily=(Decimal("100"), Decimal("108"), Decimal("92"), Decimal("108"), Decimal("999")),
            m15=(Decimal("100"), Decimal("109"), Decimal("91"), Decimal("107"), Decimal("1000")),
        )


def test_volume_is_checked_only_when_source_contract_supports_it() -> None:
    value = json.loads(_raw())
    value["relations"]["volume"] = "EQUAL"
    pair = parse_source_pair_qualification(json.dumps(value).encode())
    with pytest.raises(PairRefusal, match="PAIR_VOLUME"):
        reconcile_source_pair(
            pair,
            symbol="S0",
            session_open=datetime(2021, 1, 4, 3, 45, tzinfo=UTC),
            session_close=datetime(2021, 1, 4, 10, tzinfo=UTC),
            daily=(Decimal("100"), Decimal("110"), Decimal("90"), Decimal("108"), Decimal("999")),
            m15=(Decimal("100"), Decimal("109"), Decimal("91"), Decimal("107"), Decimal("1000")),
        )


def test_common_session_open_must_match_even_when_close_conventions_differ() -> None:
    pair = parse_source_pair_qualification(_raw())
    with pytest.raises(PairRefusal, match="PAIR_OPEN"):
        reconcile_source_pair(
            pair,
            symbol="S0",
            session_open=datetime(2021, 1, 4, 3, 45, tzinfo=UTC),
            session_close=datetime(2021, 1, 4, 10, tzinfo=UTC),
            daily=(Decimal("99"), Decimal("110"), Decimal("90"), Decimal("108"), Decimal("1000")),
            m15=(Decimal("100"), Decimal("109"), Decimal("91"), Decimal("107"), Decimal("1000")),
        )


def test_pair_bytes_are_not_their_own_qualification() -> None:
    raw = _raw()
    pair = parse_source_pair_qualification(raw)
    assert pair.document_sha256 == hashlib.sha256(raw).hexdigest()
    assert not hasattr(pair, "data_qualified")


def test_unsupported_volume_relation_cannot_waive_reconciliation() -> None:
    value = json.loads(_raw())
    value["relations"]["volume"] = "UNSUPPORTED"
    with pytest.raises(PairRefusal, match="PAIR_RELATION"):
        parse_source_pair_qualification(json.dumps(value).encode())


@pytest.mark.parametrize("factor", ["split_factor", "bonus_factor", "rights_factor"])
def test_nonunit_relative_action_factor_refuses_before_execution(factor: str) -> None:
    value = json.loads(_raw())
    value["mappings"][0][factor] = "0.5"
    with pytest.raises(PairRefusal, match="PAIR_BASIS"):
        parse_source_pair_qualification(json.dumps(value).encode())


def test_mapping_must_cover_the_whole_session_not_only_its_open() -> None:
    value = json.loads(_raw())
    value["mappings"][0]["effective_end"] = "2021-01-04T05:00:00Z"
    pair = parse_source_pair_qualification(json.dumps(value).encode())
    with pytest.raises(PairRefusal, match="PAIR_MAPPING"):
        reconcile_source_pair(
            pair,
            symbol="S0",
            session_open=datetime(2021, 1, 4, 3, 45, tzinfo=UTC),
            session_close=datetime(2021, 1, 4, 10, tzinfo=UTC),
            daily=(Decimal("100"), Decimal("110"), Decimal("90"), Decimal("108"), Decimal("1000")),
            m15=(Decimal("100"), Decimal("109"), Decimal("91"), Decimal("107"), Decimal("1000")),
        )


@pytest.mark.parametrize("shared", ["isin", "m15_token"])
def test_overlapping_symbols_cannot_share_security_or_vendor_identity(shared: str) -> None:
    value = json.loads(_raw())
    second = dict(value["mappings"][0])
    second.update(
        {
            "symbol": "S1",
            "isin": "INE000000002",
            "daily_symbol": "S1",
            "m15_symbol": "S1",
            "m15_token": "vendor-102",
            "lineage_sha256": "f" * 64,
        }
    )
    second[shared] = value["mappings"][0][shared]
    value["mappings"].append(second)
    with pytest.raises(PairRefusal, match="PAIR_MAPPING"):
        parse_source_pair_qualification(json.dumps(value).encode())


@pytest.mark.parametrize(
    ("role", "field", "value"),
    [
        ("daily_stock", "vendor", "WRONG_VENDOR"),
        ("m15_stock", "source_revision", "wrong-revision"),
    ],
)
def test_declared_lane_identity_must_match_captured_metadata(
    role: str, field: str, value: str
) -> None:
    pair = parse_source_pair_qualification(_raw())
    metadata = {
        "daily_stock": {"vendor": "NSE_OFFICIAL_DAILY", "source_revision": "r1"},
        "m15_stock": {"vendor": "INDEPENDENT_VENDOR_M15", "source_revision": "r1"},
    }
    metadata[role][field] = value
    with pytest.raises(PairRefusal, match="PAIR_SOURCE_IDENTITY"):
        validate_source_pair_identities(pair, metadata)


def test_captured_daily_and_m15_identity_must_be_independent() -> None:
    pair = parse_source_pair_qualification(_raw())
    metadata = {
        "daily_stock": {"vendor": "NSE_OFFICIAL_DAILY", "source_revision": "r1"},
        "m15_stock": {"vendor": "NSE_OFFICIAL_DAILY", "source_revision": "r1"},
    }
    with pytest.raises(PairRefusal, match="PAIR_SOURCE_IDENTITY"):
        validate_source_pair_identities(pair, metadata)


@pytest.mark.parametrize(
    ("lane", "values", "code"),
    [
        (
            "daily",
            (Decimal("100"), Decimal("110"), Decimal("90"), Decimal("9999"), Decimal("1000")),
            "PAIR_OHLC",
        ),
        (
            "daily",
            (Decimal("100"), Decimal("110"), Decimal("90"), Decimal("80"), Decimal("1000")),
            "PAIR_OHLC",
        ),
        (
            "m15",
            (Decimal("100"), Decimal("109"), Decimal("91"), Decimal("107"), Decimal("-1")),
            "PAIR_VALUE",
        ),
        (
            "daily",
            (Decimal("NaN"), Decimal("110"), Decimal("90"), Decimal("108"), Decimal("1000")),
            "PAIR_VALUE",
        ),
    ],
)
def test_each_lane_requires_valid_finite_ohlcv_before_cross_source_rules(
    lane: str, values: tuple[Decimal, ...], code: str
) -> None:
    pair = parse_source_pair_qualification(_raw())
    valid_daily = (Decimal("100"), Decimal("110"), Decimal("90"), Decimal("108"), Decimal("1000"))
    valid_m15 = (Decimal("100"), Decimal("109"), Decimal("91"), Decimal("107"), Decimal("1000"))
    with pytest.raises(PairRefusal, match=code):
        reconcile_source_pair(
            pair,
            symbol="S0",
            session_open=datetime(2021, 1, 4, 3, 45, tzinfo=UTC),
            session_close=datetime(2021, 1, 4, 10, tzinfo=UTC),
            daily=values if lane == "daily" else valid_daily,
            m15=values if lane == "m15" else valid_m15,
        )
