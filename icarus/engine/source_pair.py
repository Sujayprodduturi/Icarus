"""Externally reviewed daily/M15 source-pair contract and deterministic reconciliation."""

from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

from icarus.strategy.dsl import Panel

_SHA = re.compile(r"[0-9a-f]{64}")


class PairRefusal(ValueError):
    """Stable fail-closed source-pair refusal."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True, slots=True)
class PairMapping:
    symbol: str
    isin: str
    daily_symbol: str
    m15_symbol: str
    m15_token: str
    lineage_sha256: str
    split_factor: Decimal
    bonus_factor: Decimal
    rights_factor: Decimal
    effective_start: datetime
    effective_end: datetime


@dataclass(frozen=True, slots=True)
class PairSourceIdentity:
    vendor: str
    source_revision: str


@dataclass(frozen=True, slots=True)
class PairQualification:
    pair_id: str
    reviewer: str
    approved_at: datetime
    effective_start: datetime
    effective_end: datetime
    daily_sha256: str
    m15_sha256: str
    action_sha256: str
    calendar_sha256: str
    daily_source: PairSourceIdentity
    m15_source: PairSourceIdentity
    daily_close_rule: str
    m15_capture_rule: str
    session_rule: str
    price_basis: tuple[tuple[str, str], ...]
    extrema_relation: str
    open_relation: str
    volume_relation: str
    mappings: tuple[PairMapping, ...]
    document_sha256: str

    def mapping_for(
        self, symbol: str, session_open: datetime, session_close: datetime | None = None
    ) -> PairMapping:
        end = session_open if session_close is None else session_close
        matches = tuple(
            row
            for row in self.mappings
            if row.symbol == symbol
            and row.effective_start <= session_open
            and row.effective_end >= end
        )
        if len(matches) != 1:
            raise PairRefusal("PAIR_MAPPING")
        return matches[0]


@dataclass(frozen=True, slots=True)
class BoundPairQualification:
    qualification: PairQualification
    daily_projection_sha256: str


def daily_projection_digest(panel: Panel, source_indices: Sequence[int]) -> str:
    digest = hashlib.sha256()

    def add(value: object) -> None:
        encoded = str(value).encode()
        digest.update(len(encoded).to_bytes(8, "big"))
        digest.update(encoded)

    add("axis")
    for index, value in zip(source_indices, panel.ts, strict=True):
        add(index)
        add(value)
    for symbol, bars, tradable in zip(panel.symbols, panel.bars, panel.tradable, strict=True):
        add(symbol)
        for i in range(len(source_indices)):
            for name in ("open", "high", "low", "close", "volume"):
                add(float(getattr(bars, name)[i]))
            add(bool(tradable[i]))
    if panel.benchmark is not None:
        add("benchmark")
        for i in range(len(source_indices)):
            for name in ("open", "high", "low", "close", "volume"):
                add(float(getattr(panel.benchmark, name)[i]))
    else:
        add("no-benchmark")
    return digest.hexdigest()


def _bind_source_pair(
    pair: PairQualification,
    artifact_hashes: Mapping[str, str],
    artifact_metadata: Mapping[str, Mapping[str, Any]],
    panel: Panel,
    source_indices: Sequence[int],
) -> BoundPairQualification:
    validate_source_pair_artifacts(pair, artifact_hashes)
    validate_source_pair_identities(pair, artifact_metadata)
    return BoundPairQualification(pair, daily_projection_digest(panel, source_indices))


def validate_source_pair_artifacts(
    pair: PairQualification, artifact_hashes: Mapping[str, str]
) -> None:
    expected = {
        "daily_stock": pair.daily_sha256,
        "m15_stock": pair.m15_sha256,
        "corporate_action": pair.action_sha256,
        "session_calendar": pair.calendar_sha256,
    }
    if any(artifact_hashes.get(role) != digest for role, digest in expected.items()):
        raise PairRefusal("PAIR_ARTIFACT_BINDING")


def validate_source_pair_identities(
    pair: PairQualification, artifact_metadata: Mapping[str, Mapping[str, Any]]
) -> None:
    captured = {
        role: PairSourceIdentity(
            _text(artifact_metadata[role].get("vendor")),
            _text(artifact_metadata[role].get("source_revision")),
        )
        for role in ("daily_stock", "m15_stock")
    }
    if captured["daily_stock"] == captured["m15_stock"]:
        raise PairRefusal("PAIR_SOURCE_IDENTITY")
    if pair.daily_source != captured["daily_stock"] or pair.m15_source != captured["m15_stock"]:
        raise PairRefusal("PAIR_SOURCE_IDENTITY")


def _object(raw: bytes) -> dict[str, Any]:
    def pairs(items: list[tuple[str, Any]]) -> dict[str, Any]:
        value: dict[str, Any] = {}
        for key, item in items:
            if key in value:
                raise PairRefusal("PAIR_SCHEMA")
            value[key] = item
        return value

    try:
        value = json.loads(
            raw,
            object_pairs_hook=pairs,
            parse_constant=lambda _: (_ for _ in ()).throw(ValueError()),
        )
    except (UnicodeDecodeError, json.JSONDecodeError, ValueError) as exc:
        raise PairRefusal("PAIR_SCHEMA") from exc
    if type(value) is not dict:
        raise PairRefusal("PAIR_SCHEMA")
    return value


def _text(value: object) -> str:
    if type(value) is not str or not value.strip():
        raise PairRefusal("PAIR_SCHEMA")
    return value


def _sha(value: object) -> str:
    result = _text(value)
    if _SHA.fullmatch(result) is None:
        raise PairRefusal("PAIR_SCHEMA")
    return result


def _utc(value: object) -> datetime:
    text = _text(value)
    if not text.endswith("Z"):
        raise PairRefusal("PAIR_SCHEMA")
    try:
        result = datetime.fromisoformat(text[:-1] + "+00:00")
    except ValueError as exc:
        raise PairRefusal("PAIR_SCHEMA") from exc
    if result.tzinfo is not UTC:
        raise PairRefusal("PAIR_SCHEMA")
    return result


def parse_source_pair_qualification(raw: bytes) -> PairQualification:
    value = _object(raw)
    wanted = {
        "schema_version",
        "pair_id",
        "reviewer",
        "approved_at",
        "effective_start",
        "effective_end",
        "daily_sha256",
        "m15_sha256",
        "action_sha256",
        "calendar_sha256",
        "daily_source",
        "m15_source",
        "daily_close_rule",
        "m15_capture_rule",
        "session_rule",
        "price_basis",
        "relations",
        "mappings",
        "invented",
    }
    if (
        set(value) != wanted
        or type(value["schema_version"]) is not int
        or value["schema_version"] != 1
    ):
        raise PairRefusal("PAIR_SCHEMA")
    if value["invented"] is not False:
        raise PairRefusal("PAIR_INVENTED")

    def source_identity(raw: object) -> PairSourceIdentity:
        if type(raw) is not dict or set(raw) != {"vendor", "source_revision"}:
            raise PairRefusal("PAIR_SOURCE_IDENTITY")
        return PairSourceIdentity(_text(raw["vendor"]), _text(raw["source_revision"]))

    daily_source = source_identity(value["daily_source"])
    m15_source = source_identity(value["m15_source"])
    if daily_source == m15_source:
        raise PairRefusal("PAIR_SOURCE_IDENTITY")
    if value["daily_close_rule"] not in ("OFFICIAL_SESSION_CLOSE", "OFFICIAL_AUCTION_CLOSE"):
        raise PairRefusal("PAIR_RULE")
    if value["m15_capture_rule"] not in ("VENDOR_INTERVAL_CAPTURE_V1",):
        raise PairRefusal("PAIR_RULE")
    if value["session_rule"] not in ("PINNED_NSE_CALENDAR_V1",):
        raise PairRefusal("PAIR_RULE")
    basis = value["price_basis"]
    if type(basis) is not dict or set(basis) != {"split", "bonus", "rights", "dividend"}:
        raise PairRefusal("PAIR_BASIS")
    typed_basis = tuple(
        (key, _text(basis[key])) for key in ("split", "bonus", "rights", "dividend")
    )
    if dict(typed_basis) != {
        "split": "BACK_ADJUSTED",
        "bonus": "BACK_ADJUSTED",
        "rights": "BACK_ADJUSTED",
        "dividend": "UNADJUSTED",
    }:
        raise PairRefusal("PAIR_BASIS")
    relations = value["relations"]
    if type(relations) is not dict or set(relations) != {"open", "extrema_containment", "volume"}:
        raise PairRefusal("PAIR_RELATION")
    open_relation, extrema, volume = (
        relations["open"],
        relations["extrema_containment"],
        relations["volume"],
    )
    if (
        open_relation != "EQUAL"
        or extrema != "SUPPORTED"
        or volume not in ("EQUAL", "M15_LE_DAILY")
    ):
        raise PairRefusal("PAIR_RELATION")
    start, end, approved = (
        _utc(value["effective_start"]),
        _utc(value["effective_end"]),
        _utc(value["approved_at"]),
    )
    if end < start:
        raise PairRefusal("PAIR_EFFECTIVE_INTERVAL")
    raw_mappings = value["mappings"]
    if type(raw_mappings) is not list or not raw_mappings:
        raise PairRefusal("PAIR_MAPPING")
    mappings: list[PairMapping] = []
    identities: set[tuple[str, str, str, str, str]] = set()
    for row in raw_mappings:
        if type(row) is not dict or set(row) != {
            "symbol",
            "isin",
            "daily_symbol",
            "m15_symbol",
            "m15_token",
            "lineage_sha256",
            "split_factor",
            "bonus_factor",
            "rights_factor",
            "effective_start",
            "effective_end",
        }:
            raise PairRefusal("PAIR_MAPPING")
        row_start, row_end = _utc(row["effective_start"]), _utc(row["effective_end"])
        identity = (
            _text(row["symbol"]),
            _text(row["isin"]),
            _text(row["daily_symbol"]),
            _text(row["m15_symbol"]),
            _text(row["m15_token"]),
        )
        if identity in identities or row_end < row_start or row_start < start or row_end > end:
            raise PairRefusal("PAIR_MAPPING")
        identities.add(identity)
        try:
            factors = tuple(
                Decimal(_text(row[name]))
                for name in ("split_factor", "bonus_factor", "rights_factor")
            )
        except Exception as exc:
            raise PairRefusal("PAIR_BASIS") from exc
        if any(not factor.is_finite() or factor != 1 for factor in factors):
            raise PairRefusal("PAIR_BASIS")
        mappings.append(
            PairMapping(
                identity[0],
                identity[1],
                identity[2],
                identity[3],
                identity[4],
                _sha(row["lineage_sha256"]),
                factors[0],
                factors[1],
                factors[2],
                row_start,
                row_end,
            )
        )
    for left_position, left in enumerate(mappings):
        for right in mappings[left_position + 1 :]:
            overlaps = (
                left.effective_start <= right.effective_end
                and right.effective_start <= left.effective_end
            )
            shared_identity = (
                left.isin == right.isin
                or left.daily_symbol == right.daily_symbol
                or left.m15_token == right.m15_token
            )
            if overlaps and shared_identity and left.symbol != right.symbol:
                raise PairRefusal("PAIR_MAPPING")
    return PairQualification(
        _text(value["pair_id"]),
        _text(value["reviewer"]),
        approved,
        start,
        end,
        _sha(value["daily_sha256"]),
        _sha(value["m15_sha256"]),
        _sha(value["action_sha256"]),
        _sha(value["calendar_sha256"]),
        daily_source,
        m15_source,
        _text(value["daily_close_rule"]),
        _text(value["m15_capture_rule"]),
        _text(value["session_rule"]),
        typed_basis,
        extrema,
        open_relation,
        volume,
        tuple(mappings),
        hashlib.sha256(raw).hexdigest(),
    )


def reconcile_source_pair(
    pair: PairQualification,
    *,
    symbol: str,
    session_open: datetime,
    session_close: datetime,
    daily: Sequence[Decimal],
    m15: Sequence[Decimal],
) -> None:
    if len(daily) != 5 or len(m15) != 5:
        raise PairRefusal("PAIR_SCHEMA")

    def validate_lane(values: Sequence[Decimal]) -> None:
        open_price, high, low, close, volume = values
        if (
            any(not price.is_finite() or price <= 0 for price in values[:4])
            or not volume.is_finite()
            or volume < 0
        ):
            raise PairRefusal("PAIR_VALUE")
        if not (low <= min(open_price, close) <= max(open_price, close) <= high):
            raise PairRefusal("PAIR_OHLC")

    validate_lane(daily)
    validate_lane(m15)
    if not (pair.effective_start <= session_open and pair.effective_end >= session_close):
        raise PairRefusal("PAIR_EFFECTIVE_INTERVAL")
    mapping = pair.mapping_for(symbol, session_open, session_close)
    factor = mapping.split_factor * mapping.bonus_factor * mapping.rights_factor
    if factor != 1:
        raise PairRefusal("PAIR_BASIS")
    if m15[0] != daily[0]:
        raise PairRefusal("PAIR_OPEN")
    if m15[1] > daily[1] or m15[2] < daily[2]:
        raise PairRefusal("PAIR_EXTREMA_CONTAINMENT")
    if pair.volume_relation == "EQUAL" and m15[4] != daily[4]:
        raise PairRefusal("PAIR_VOLUME")
    if pair.volume_relation == "M15_LE_DAILY" and m15[4] > daily[4]:
        raise PairRefusal("PAIR_VOLUME")
