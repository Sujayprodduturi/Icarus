"""Prepare the bounded 693-by-257 daily-pilot panel without evaluating a strategy.

This module is deliberately narrower than :mod:`icarus.engine.panelbuild`: it keeps every
requested label, including labels that are never tradable, and accepts only exact dated
label/symbol/ISIN identity.  It has no network, strategy, simulator, ledger, or authorization
path.  Its publication receipt remains pending and cannot qualify data or authorize a run.  The
pure interface receives caller-declared provenance pins.  The binding interface independently
rehashes the controls and all 514 source files, then derives each input without writing an
output.  Actual panel emission remains unsupported while source-use authorization is open.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from itertools import pairwise
from pathlib import Path
from typing import Any

import numpy as np
import numpy.typing as npt

from icarus.agents.data.corpactions import Split
from icarus.agents.data.nseactions import (
    ActionHistory,
    NseCorporateActions,
    Unpriceable,
    parse_ex_date,
)
from icarus.common.config import Universe, load_goal
from icarus.engine.daily_pilot import (
    PILOT_DATES,
    REQUESTED_LABEL_COUNT,
    SOURCE_SESSION_COUNT,
    panel_sha256,
)
from icarus.engine.daily_pilot_admission import (
    FIXED_INCOME_DISPOSITION,
    UnresolvedAction,
    guard_unresolved_action_lookback,
)
from icarus.engine.panelbuild import (
    MAX_UNEXPLAINED_GAP,
    BuildReport,
    _back_adjust,
    _membership,
    _quarantine,
    load_panel,
    save_panel,
    session_axis,
)
from icarus.strategy.dsl import Bars, Panel

_FIELDS = ("open", "high", "low", "close", "volume", "turnover")
_PANEL_FIELDS = ("open", "high", "low", "close", "volume")
_RAW_ADMITTED = frozenset({"ELIGIBLE", "CONDITIONAL_QUALIFIES"})
_RAW_STATUSES = _RAW_ADMITTED | frozenset({"BELOW_CLOSE", "BELOW_TURNOVER", "MISSING_WINDOW"})

RawRow = Sequence[str]
RawBySession = Mapping[date, Mapping[str, RawRow]]
_Matrices = dict[str, npt.NDArray[np.float64]]


def _lower_sha256(value: str, name: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _json_digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class DatedIdentitySeries:
    """One requested label's explicit identity or absence on every source session."""

    label: str
    symbols: tuple[str | None, ...]
    isins: tuple[str | None, ...]

    def __post_init__(self) -> None:
        if not self.label or type(self.symbols) is not tuple or type(self.isins) is not tuple:
            raise ValueError("dated identity series must use a nonempty label and tuple axes")


@dataclass(frozen=True, slots=True)
class PreparedDisposition:
    label: str
    raw_statuses: tuple[str, ...]
    effective_statuses: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class PrepareAudit:
    session_count: int
    requested_label_count: int
    observed_cells: int
    explicit_absent_cells: int
    research_sanity_excluded_cells: int
    priceable_action_rows: int
    priceable_action_cuts: int
    priceable_pilot_action_rows: int
    known_unpriceable_quarantines: int
    panel_nbytes: int
    session_dates_sha256: str
    requested_label_axis_sha256: str
    selected_lineage_sha256: str
    action_ledger_sha256: str
    dispositions: tuple[PreparedDisposition, ...]


@dataclass(frozen=True, slots=True)
class PreparationPins:
    source_inventory_sha256: str
    source_qa_sha256: str
    requested_labels_sha256: str
    calendar_sha256: str
    action_manifest_sha256: str
    point_in_time_identity_sha256: str
    goal_sha256: str
    session_dates_sha256: str
    requested_label_axis_sha256: str

    def __post_init__(self) -> None:
        for name in self.__dataclass_fields__:
            _lower_sha256(getattr(self, name), name)

    def as_json(self) -> dict[str, str]:
        return {name: getattr(self, name) for name in self.__dataclass_fields__}


@dataclass(frozen=True, slots=True)
class BoundPreparation:
    """Invented-testable result of verifying and deriving every preparer input."""

    panel: Panel
    audit: PrepareAudit
    pins: PreparationPins
    source_pins_verified: bool
    verified_file_count: int
    verified_source_file_count: int
    raw_isin_overrides_applied: int
    input_state_sha256: str


def _validate_axes(
    sessions: tuple[date, ...],
    requested_labels: tuple[str, ...],
    identities: tuple[DatedIdentitySeries, ...],
    raw_by_session: RawBySession,
    raw_pilot_statuses: Mapping[str, tuple[str, ...]],
    expected_session_dates_sha256: str,
    expected_requested_labels_sha256: str,
) -> None:
    _lower_sha256(expected_session_dates_sha256, "expected_session_dates_sha256")
    _lower_sha256(expected_requested_labels_sha256, "expected_requested_labels_sha256")
    if (
        len(sessions) != SOURCE_SESSION_COUNT
        or sessions[-5:] != PILOT_DATES
        or any(right <= left for left, right in pairwise(sessions))
    ):
        raise ValueError("preparer requires the canonical 257-session axis ending in pilot dates")
    if (
        len(requested_labels) != REQUESTED_LABEL_COUNT
        or len(set(requested_labels)) != REQUESTED_LABEL_COUNT
        or requested_labels != tuple(sorted(requested_labels))
    ):
        raise ValueError("preparer requires 693 unique requested labels in canonical order")
    if (
        len(identities) != REQUESTED_LABEL_COUNT
        or tuple(item.label for item in identities) != requested_labels
    ):
        raise ValueError("dated identities must contain exactly one canonical series per label")
    if _json_digest([value.isoformat() for value in sessions]) != expected_session_dates_sha256:
        raise ValueError("session axis digest differs from its fixed control")
    if _json_digest(list(requested_labels)) != expected_requested_labels_sha256:
        raise ValueError("requested-label axis digest differs from its fixed control")
    if set(raw_by_session) != set(sessions):
        raise ValueError("raw input must contain exactly the 257 selected sessions")
    if set(raw_pilot_statuses) != set(requested_labels):
        raise ValueError("source screen must retain every requested label")


def _action_ledger(actions: ActionHistory, labels: frozenset[str]) -> tuple[str, int, int, int]:
    if actions.unrecognised:
        raise ValueError("unrecognised corporate action prevents panel preparation")

    split_rows: list[tuple[str, str, str]] = []
    seen_splits: set[tuple[str, date, Decimal]] = set()
    cuts: set[tuple[str, date]] = set()
    for symbol, splits in sorted(actions.splits.items()):
        if symbol not in labels:
            raise ValueError("corporate-action ledger contains an unrequested symbol")
        for split in splits:
            split_key = (symbol, split.ex_date, split.ratio)
            if split_key in seen_splits:
                raise ValueError("duplicate priceable corporate action")
            if not split.ratio.is_finite() or split.ratio <= 0:
                raise ValueError("invalid priceable corporate-action ratio")
            seen_splits.add(split_key)
            cuts.add((symbol, split.ex_date))
            split_rows.append((symbol, split.ex_date.isoformat(), str(split.ratio)))

    unpriceable_rows: list[tuple[str, str, str]] = []
    seen_unpriceable: set[tuple[str, date, str]] = set()
    for item in actions.unpriceable:
        if item.symbol not in labels:
            raise ValueError("corporate-action ledger contains an unrequested symbol")
        unpriceable_key = (item.symbol, item.ex_date, item.subject)
        if unpriceable_key in seen_unpriceable:
            raise ValueError("duplicate unpriceable corporate action")
        seen_unpriceable.add(unpriceable_key)
        unpriceable_rows.append((item.symbol, item.ex_date.isoformat(), item.subject))

    pilot_rows = sum(
        split.ex_date in PILOT_DATES for splits in actions.splits.values() for split in splits
    )
    digest = _json_digest(
        {
            "from": actions.frm.isoformat(),
            "to": actions.to.isoformat(),
            "splits": sorted(split_rows),
            "unpriceable": sorted(unpriceable_rows),
            "unrecognised": [],
        }
    )
    return digest, len(split_rows), len(cuts), pilot_rows


def _raw_matrices_and_lineage(
    sessions: tuple[date, ...],
    labels: tuple[str, ...],
    raw_by_session: RawBySession,
    identities: tuple[DatedIdentitySeries, ...],
) -> tuple[_Matrices, int, int, str]:
    shape = (len(labels), len(sessions))
    raw: _Matrices = {name: np.full(shape, np.nan, dtype=np.float64) for name in _FIELDS}
    lineage = hashlib.sha256()
    shared_isins: list[dict[str, str]] = [dict() for _ in sessions]
    observed = 0
    research_sanity_excluded = 0

    for row_index, item in enumerate(identities):
        if len(item.symbols) != len(sessions) or len(item.isins) != len(sessions):
            raise ValueError("each dated identity series must cover all 257 sessions")
        for column, (session, symbol, isin) in enumerate(
            zip(sessions, item.symbols, item.isins, strict=True)
        ):
            lineage.update(
                json.dumps(
                    [item.label, session.isoformat(), symbol, isin],
                    separators=(",", ":"),
                ).encode()
            )
            if (symbol is None) != (isin is None):
                raise ValueError("dated identity must declare symbol and ISIN together")
            source_rows = raw_by_session[session]
            if symbol is None:
                if item.label in source_rows:
                    raise ValueError("identity declares absence but a direct raw row exists")
                continue
            if symbol != item.label:
                raise ValueError("successor or alias identity is not proved for this bounded panel")
            if not isin:
                raise ValueError("observed dated identity requires a nonempty ISIN")
            owner = shared_isins[column].get(isin)
            if owner is not None and owner != item.label:
                raise ValueError("shared ISIN across requested labels is ambiguous")
            shared_isins[column][isin] = item.label
            source_row = source_rows.get(symbol)
            if source_row is None:
                raise ValueError("identity is declared present but raw row is absent")
            if len(source_row) != len(_FIELDS):
                raise ValueError("invalid raw row for declared identity")
            try:
                values = [float(value) for value in source_row]
            except (TypeError, ValueError) as exc:
                raise ValueError("invalid raw row for declared identity") from exc
            open_, high, low, close, volume, turnover = values
            if (
                not all(math.isfinite(value) for value in values)
                or min(open_, high, low, close) <= 0
                or volume < 0
                or turnover < 0
                or not (low <= min(open_, close) and max(open_, close) <= high)
            ):
                raise ValueError("invalid raw row for declared identity")
            observed += 1
            if min(open_, high, low, close) < 1.0:
                research_sanity_excluded += 1
                continue
            for field, value in zip(_FIELDS, values, strict=True):
                raw[field][row_index, column] = value
    return raw, observed, research_sanity_excluded, lineage.hexdigest()


def _effective_unpriceable_days(
    actions: ActionHistory, sessions: tuple[date, ...]
) -> frozenset[tuple[str, date]]:
    effective: set[tuple[str, date]] = set()
    for item in actions.unpriceable:
        first = next((session for session in sessions if session >= item.ex_date), None)
        if first is not None:
            effective.add((item.symbol, first))
    return frozenset(effective)


def _derived_source_status(
    raw: _Matrices,
    row_index: int,
    column: int,
    universe: Universe,
) -> str:
    window = universe.turnover_window_sessions
    start = column - window + 1
    if start < 0:
        return "MISSING_WINDOW"
    close = raw["close"][row_index, start : column + 1]
    turnover = raw["turnover"][row_index, start : column + 1]
    if np.isnan(close).any() or np.isnan(turnover).any():
        return "MISSING_WINDOW"
    if close[-1] < float(universe.min_close_inr):
        return "BELOW_CLOSE"
    if float(np.mean(turnover)) < float(universe.min_avg_turnover_inr):
        return "BELOW_TURNOVER"
    return "CONDITIONAL_QUALIFIES"


def _refuse_unexplained_discontinuities(
    labels: tuple[str, ...],
    adjusted: _Matrices,
    sessions: tuple[date, ...],
    allowed: frozenset[tuple[str, date]],
) -> None:
    close = adjusted["close"]
    open_ = adjusted["open"]
    threshold = math.log(1.0 + MAX_UNEXPLAINED_GAP)
    for row_index, label in enumerate(labels):
        present = np.flatnonzero(~np.isnan(close[row_index]))
        if present.size < 2:
            continue
        consecutive = np.diff(present) == 1
        previous = present[:-1][consecutive]
        current = present[1:][consecutive]
        for before, after in zip(previous, current, strict=True):
            ratio = float(open_[row_index, after] / close[row_index, before])
            if abs(math.log(ratio)) > threshold and (label, sessions[int(after)]) not in allowed:
                raise ValueError("unexplained discontinuity remains after exact action adjustment")


def prepare_daily_pilot_panel(
    *,
    sessions: Sequence[date],
    requested_labels: Sequence[str],
    raw_by_session: RawBySession,
    identities: Sequence[DatedIdentitySeries],
    raw_pilot_statuses: Mapping[str, tuple[str, ...]],
    actions: ActionHistory,
    unresolved_actions: tuple[UnresolvedAction, ...],
    universe: Universe,
    expected_session_dates_sha256: str,
    expected_requested_labels_sha256: str,
) -> tuple[Panel, PrepareAudit]:
    """Build an evidence-pending panel from already validated, local inputs only."""

    session_axis_values = tuple(sessions)
    labels = tuple(requested_labels)
    identity_values = tuple(identities)
    _validate_axes(
        session_axis_values,
        labels,
        identity_values,
        raw_by_session,
        raw_pilot_statuses,
        expected_session_dates_sha256,
        expected_requested_labels_sha256,
    )
    if actions.frm > session_axis_values[0] or actions.to < session_axis_values[-1]:
        raise ValueError("corporate-action ledger does not cover the selected interval")

    action_digest, action_rows, action_cuts, pilot_action_rows = _action_ledger(
        actions, frozenset(labels)
    )
    if pilot_action_rows:
        raise ValueError("priceable actions on decision dates require an unavailable holding model")
    expected_unpriceable = {(item.label, item.ex_date, item.subject) for item in unresolved_actions}
    actual_unpriceable = {(item.symbol, item.ex_date, item.subject) for item in actions.unpriceable}
    if expected_unpriceable != actual_unpriceable:
        raise ValueError("unresolved action guard differs from the complete action ledger")

    raw, observed, research_sanity_excluded, lineage_digest = _raw_matrices_and_lineage(
        session_axis_values, labels, raw_by_session, identity_values
    )
    raw_membership = _membership(raw, universe, session_axis_values)

    dispositions: list[PreparedDisposition] = []
    final_membership = raw_membership.copy()
    for row_index, label in enumerate(labels):
        statuses = raw_pilot_statuses[label]
        if len(statuses) != len(PILOT_DATES) or not set(statuses).issubset(_RAW_STATUSES):
            raise ValueError("source screen uses an unreviewed status or wrong pilot axis")
        expected_raw = np.array([status in _RAW_ADMITTED for status in statuses], dtype=np.bool_)
        if not np.array_equal(raw_membership[row_index, -5:], expected_raw):
            raise ValueError("source-screen status differs from raw membership")
        derived = tuple(
            _derived_source_status(raw, row_index, column, universe)
            for column in range(SOURCE_SESSION_COUNT - 5, SOURCE_SESSION_COUNT)
        )
        if statuses != derived:
            raise ValueError("source-screen reason differs from raw data")
        effective = guard_unresolved_action_lookback(
            label,
            statuses,
            PILOT_DATES,
            session_axis_values,
            unresolved_actions,
        )
        if label == "LIQUIDBEES":
            if effective != (FIXED_INCOME_DISPOSITION,) * 5:
                raise ValueError("LIQUIDBEES must retain its fixed-income disposition")
            final_membership[row_index, :] = False
        final_membership[row_index, -5:] = np.array(
            [status == "ELIGIBLE" for status in effective], dtype=np.bool_
        )
        dispositions.append(PreparedDisposition(label, statuses, effective))

    adjusted, applied = _back_adjust(labels, raw, actions, session_axis_values)
    if applied != action_rows:
        raise ValueError("priceable action ledger was not applied exactly once")
    for name in _PANEL_FIELDS:
        present = ~np.isnan(raw[name])
        if np.any(~np.isfinite(adjusted[name][present])):
            raise ValueError("corporate-action transform produced a non-finite value")

    quarantine_report = BuildReport(sessions=len(session_axis_values))
    audited_membership = final_membership.copy()
    allowed_quarantines = _effective_unpriceable_days(actions, session_axis_values)
    _refuse_unexplained_discontinuities(
        labels,
        adjusted,
        session_axis_values,
        allowed_quarantines,
    )
    _quarantine(
        labels,
        adjusted,
        audited_membership,
        actions,
        session_axis_values,
        quarantine_report,
    )
    unexpected = tuple(
        item
        for item in quarantine_report.quarantines
        if (item.symbol, item.at) not in allowed_quarantines
    )
    if unexpected:
        raise ValueError("unexplained discontinuity remains after exact action adjustment")
    final_membership = audited_membership
    # The action guard is authoritative for the five decision dates even if the old quarantine
    # would otherwise permit a later re-entry.
    for row_index, disposition in enumerate(dispositions):
        final_membership[row_index, -5:] = np.array(
            [status == "ELIGIBLE" for status in disposition.effective_statuses],
            dtype=np.bool_,
        )
    final_membership[labels.index("LIQUIDBEES"), :] = False

    ts = session_axis(session_axis_values)
    bars = {
        label: Bars(
            ts=ts,
            **{name: adjusted[name][row_index] for name in _PANEL_FIELDS},
        )
        for row_index, label in enumerate(labels)
    }
    membership = {label: final_membership[row_index] for row_index, label in enumerate(labels)}
    panel = Panel.build(bars, membership, benchmark=None)
    panel_nbytes = (
        sum(getattr(series, name).nbytes for series in panel.bars for name in _PANEL_FIELDS)
        + panel.tradable.nbytes
    )
    audit = PrepareAudit(
        session_count=len(session_axis_values),
        requested_label_count=len(labels),
        observed_cells=observed,
        explicit_absent_cells=len(labels) * len(session_axis_values) - observed,
        research_sanity_excluded_cells=research_sanity_excluded,
        priceable_action_rows=action_rows,
        priceable_action_cuts=action_cuts,
        priceable_pilot_action_rows=pilot_action_rows,
        known_unpriceable_quarantines=len(quarantine_report.quarantines),
        panel_nbytes=panel_nbytes,
        session_dates_sha256=_json_digest([value.isoformat() for value in session_axis_values]),
        requested_label_axis_sha256=_json_digest(list(labels)),
        selected_lineage_sha256=lineage_digest,
        action_ledger_sha256=action_digest,
        dispositions=tuple(dispositions),
    )
    return panel, audit


def _strict_json(raw: bytes, label: str) -> dict[str, Any]:
    def reject_constant(value: str) -> None:
        raise ValueError(f"{label} contains non-finite JSON constant {value}")

    def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        output: dict[str, Any] = {}
        for key, value in pairs:
            if key in output:
                raise ValueError(f"{label} contains duplicate JSON key {key!r}")
            output[key] = value
        return output

    try:
        value = json.loads(
            raw,
            parse_constant=reject_constant,
            object_pairs_hook=unique_object,
        )
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"{label} is not valid JSON") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be a JSON object")
    return value


def _bound_path(root: Path, value: str | Path) -> Path:
    base = root.resolve()
    candidate = Path(value)
    path = candidate.resolve() if candidate.is_absolute() else (base / candidate).resolve()
    if not path.is_relative_to(base):
        raise ValueError("bound source path escapes the preparation root")
    return path


def _read_pinned(
    root: Path,
    value: str | Path,
    expected_sha256: str,
    states: dict[str, tuple[int, str]],
    *,
    expected_bytes: int | None = None,
) -> bytes:
    _lower_sha256(expected_sha256, "expected file sha256")
    path = _bound_path(root, value)
    raw = path.read_bytes()
    actual = hashlib.sha256(raw).hexdigest()
    if actual != expected_sha256 or (expected_bytes is not None and len(raw) != expected_bytes):
        raise ValueError(f"pinned file changed: {path.relative_to(root.resolve()).as_posix()}")
    key = path.relative_to(root.resolve()).as_posix()
    state = (len(raw), actual)
    prior = states.setdefault(key, state)
    if prior != state:
        raise ValueError(f"conflicting pins for {key}")
    return raw


def _file_entry(value: object, label: str) -> tuple[str, int, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{label} file pin must be an object")
    path, size, digest = value.get("path"), value.get("bytes"), value.get("sha256")
    if not isinstance(path, str) or type(size) is not int or not isinstance(digest, str):
        raise ValueError(f"{label} file pin is malformed")
    return path, size, digest


def _source_statuses(qa: dict[str, Any], labels: tuple[str, ...]) -> dict[str, tuple[str, ...]]:
    expected_scope = {
        "start": "2021-12-21",
        "end": "2022-12-30",
        "sessions": SOURCE_SESSION_COUNT,
        "raw_files": SOURCE_SESSION_COUNT,
        "cache_files": SOURCE_SESSION_COUNT,
        "requested_labels": REQUESTED_LABEL_COUNT,
        "pilot_dates": len(PILOT_DATES),
    }
    scan = qa.get("source_scan")
    if (
        qa.get("status") != "SOURCE_PAYLOAD_QA_PASS_OTHER_ADMISSION_GATES_OPEN"
        or qa.get("payload_checks_pass") is not True
        or qa.get("scope") != expected_scope
        or not isinstance(scan, dict)
        or scan.get("issues") != []
        or scan.get("sessions_attempted") != SOURCE_SESSION_COUNT
        or scan.get("sessions_aligned") != SOURCE_SESSION_COUNT
        or scan.get("raw_eq_rows") != scan.get("cache_rows")
        or scan.get("cache_rows") != scan.get("aligned_eq_rows")
        or qa.get("input_state_unchanged") is not True
        or qa.get("input_state_before") != qa.get("input_state_after")
    ):
        raise ValueError("source QA does not prove the exact clean 257-session payload scope")
    eligibility = qa.get("eligibility")
    if not isinstance(eligibility, dict) or eligibility.get("requested_labels_retained") != len(
        labels
    ):
        raise ValueError("source QA does not retain the complete requested-label axis")
    dates = eligibility.get("dates")
    if not isinstance(dates, dict) or tuple(dates) != tuple(d.isoformat() for d in PILOT_DATES):
        raise ValueError("source QA decision-date axis differs from the fixed pilot")
    output: dict[str, list[str]] = {label: [] for label in labels}
    for pilot_date in PILOT_DATES:
        day = dates[pilot_date.isoformat()]
        rows = day.get("all_693_results") if isinstance(day, dict) else None
        if not isinstance(rows, list) or [row.get("requested_name") for row in rows] != list(
            labels
        ):
            raise ValueError("source QA ordered all-693 results differ from the label control")
        for row in rows:
            status = row.get("source_screen_status")
            if not isinstance(status, str):
                raise ValueError("source QA status is malformed")
            output[row["requested_name"]].append(status)
    return {label: tuple(values) for label, values in output.items()}


def _derive_actions(
    payloads: Sequence[dict[str, Any]], labels: frozenset[str], frm: date, to: date
) -> ActionHistory:
    splits: dict[str, list[Split]] = {}
    unpriceable: list[Unpriceable] = []
    unrecognised: list[Unpriceable] = []
    seen: set[tuple[str, date, str]] = set()
    for payload in payloads:
        if payload.get("schema") != 1 or not isinstance(payload.get("rows"), list):
            raise ValueError("corporate-action cache schema differs from 1")
        for row in payload["rows"]:
            if not isinstance(row, dict) or row.get("series") != "EQ":
                continue
            symbol = row.get("symbol")
            if not isinstance(symbol, str):
                continue
            symbol = symbol.strip().upper()
            if symbol not in labels:
                continue
            subject = row.get("subject")
            ex_date = parse_ex_date(str(row.get("exDate", "")))
            if not isinstance(subject, str) or ex_date is None:
                raise ValueError("requested corporate-action row is malformed")
            if not frm <= ex_date <= to:
                continue
            key = (symbol, ex_date, subject)
            if key in seen:
                raise ValueError("duplicate requested corporate-action source row")
            seen.add(key)
            NseCorporateActions._classify(
                symbol, ex_date, subject, splits, unpriceable, unrecognised
            )
    return ActionHistory(
        frm=frm,
        to=to,
        splits={symbol: tuple(rows) for symbol, rows in splits.items()},
        unpriceable=tuple(unpriceable),
        unrecognised=tuple(unrecognised),
    )


def bind_and_prepare_daily_pilot(
    *,
    root: Path,
    source_inventory_path: Path,
    source_qa_path: Path,
    requested_labels_path: Path,
    calendar_path: Path,
    action_manifest_path: Path,
    identity_path: Path,
    goal_path: Path,
    expected_pins: PreparationPins,
    universe: Universe,
) -> BoundPreparation:
    """Verify local source bytes, derive exact inputs, and call the pure bounded preparer.

    This function intentionally does not publish an NPZ and does not set any policy qualification
    or run-authorization flag. Raw ZIP archives are rehashed but never opened here; the pinned
    source-QA receipt is the payload-validation authority for their alignment with the caches.
    """

    states: dict[str, tuple[int, str]] = {}
    inventory_raw = _read_pinned(
        root, source_inventory_path, expected_pins.source_inventory_sha256, states
    )
    qa_raw = _read_pinned(root, source_qa_path, expected_pins.source_qa_sha256, states)
    labels_raw = _read_pinned(
        root, requested_labels_path, expected_pins.requested_labels_sha256, states
    )
    calendar_raw = _read_pinned(root, calendar_path, expected_pins.calendar_sha256, states)
    manifest_raw = _read_pinned(
        root, action_manifest_path, expected_pins.action_manifest_sha256, states
    )
    identity_raw = _read_pinned(
        root, identity_path, expected_pins.point_in_time_identity_sha256, states
    )
    _read_pinned(root, goal_path, expected_pins.goal_sha256, states)

    inventory = _strict_json(inventory_raw, "source inventory")
    qa = _strict_json(qa_raw, "source QA")
    labels_payload = _strict_json(labels_raw, "requested labels")
    calendar = _strict_json(calendar_raw, "calendar certificate")
    manifest = _strict_json(manifest_raw, "action manifest")
    identity = _strict_json(identity_raw, "point-in-time identity")

    records = labels_payload.get("records")
    if not isinstance(records, list):
        raise ValueError("requested-label control has no records")
    labels = tuple(str(item.get("requested_name")) for item in records if isinstance(item, dict))
    if labels_payload.get("requested_count") != REQUESTED_LABEL_COUNT:
        raise ValueError("requested-label count differs from 693")

    interval = inventory.get("required_interval")
    raw_group, cache_group = inventory.get("raw_nse_archives"), inventory.get("daily_cache")
    if (
        not isinstance(interval, dict)
        or not isinstance(raw_group, dict)
        or not isinstance(cache_group, dict)
    ):
        raise ValueError("source inventory is malformed")
    sessions = tuple(date.fromisoformat(value) for value in interval.get("dates", []))
    if interval.get("start") != "2021-12-21" or interval.get("end") != "2022-12-30":
        raise ValueError("source inventory interval differs from the bounded scope")
    if (
        _json_digest([value.isoformat() for value in sessions])
        != expected_pins.session_dates_sha256
    ):
        raise ValueError("inventory session axis differs from its expected pin")
    if _json_digest(list(labels)) != expected_pins.requested_label_axis_sha256:
        raise ValueError("requested-label axis differs from its expected pin")

    calendar_info, universe_info = inventory.get("calendar"), inventory.get("universe")
    if (
        not isinstance(calendar_info, dict)
        or calendar_info.get("path") != str(calendar_path).replace("\\", "/")
        or calendar_info.get("sha256") != expected_pins.calendar_sha256
        or not isinstance(universe_info, dict)
        or universe_info.get("stock_label_inventory_path")
        != str(requested_labels_path).replace("\\", "/")
        or universe_info.get("stock_label_inventory_sha256")
        != expected_pins.requested_labels_sha256
    ):
        raise ValueError("inventory control pins differ from the selected controls")

    raw_entries, cache_entries = raw_group.get("files"), cache_group.get("files")
    if not isinstance(raw_entries, list) or not isinstance(cache_entries, list):
        raise ValueError("inventory source-file lists are malformed")
    if len(raw_entries) != SOURCE_SESSION_COUNT or len(cache_entries) != SOURCE_SESSION_COUNT:
        raise ValueError("full source bundle must contain 257 raw and 257 cache files")
    cache_by_session: dict[date, dict[str, RawRow]] = {}
    for role, entries in (("raw", raw_entries), ("cache", cache_entries)):
        for index, entry in enumerate(entries):
            file_path, size, digest = _file_entry(entry, role)
            raw = _read_pinned(root, file_path, digest, states, expected_bytes=size)
            if entry.get("date") != sessions[index].isoformat():
                raise ValueError(f"{role} source dates differ from the canonical session axis")
            if role == "cache":
                payload = _strict_json(raw, f"cache {entry['date']}")
                rows = payload.get("rows")
                if payload.get("schema") != 2 or not isinstance(rows, dict):
                    raise ValueError("daily cache schema differs from 2")
                if any(
                    not isinstance(symbol, str)
                    or not symbol
                    or symbol != symbol.strip().upper()
                    or not isinstance(row, list)
                    or len(row) != len(_FIELDS)
                    for symbol, row in rows.items()
                ):
                    raise ValueError("daily cache row shape or symbol is malformed")
                cache_by_session[sessions[index]] = {
                    str(symbol): tuple(str(value) for value in row)
                    for symbol, row in rows.items()
                    if symbol in labels
                }

    if qa.get("source_inventory_sha256") != expected_pins.source_inventory_sha256:
        raise ValueError("source QA names a different source inventory")
    statuses = _source_statuses(qa, labels)
    qa_states = qa.get("input_state_before")
    if not isinstance(qa_states, list):
        raise ValueError("source QA lacks pinned input state")
    qa_index = {
        item.get("path"): (item.get("bytes"), item.get("sha256"))
        for item in qa_states
        if isinstance(item, dict)
    }
    if len(qa_index) != len(qa_states):
        raise ValueError("source QA input-state paths are duplicated")
    control_pins = (
        (source_inventory_path, expected_pins.source_inventory_sha256),
        (requested_labels_path, expected_pins.requested_labels_sha256),
        (calendar_path, expected_pins.calendar_sha256),
        (goal_path, expected_pins.goal_sha256),
    )
    for control_path, digest in control_pins:
        key = _bound_path(root, control_path).relative_to(root.resolve()).as_posix()
        if qa_index.get(key) != states[key] or states[key][1] != digest:
            raise ValueError("source QA control pins differ from the selected controls")
    for entry in (*raw_entries, *cache_entries):
        if qa_index.get(entry.get("path")) != (entry.get("bytes"), entry.get("sha256")):
            raise ValueError("source QA source-file pins differ from the inventory")

    included = set(interval.get("included_calendar_statuses", []))
    resolved = calendar.get("resolved_dates")
    if not isinstance(resolved, list):
        raise ValueError("calendar certificate lacks resolved dates")
    derived_sessions = tuple(
        date.fromisoformat(item["date"])
        for item in resolved
        if isinstance(item, dict)
        and interval["start"] <= item.get("date", "") <= interval["end"]
        and item.get("status") in included
    )
    if derived_sessions != sessions:
        raise ValueError("calendar control does not derive the complete source-session axis")

    manifest_scope = manifest.get("scope")
    if manifest_scope != {
        "start": "2021-12-21",
        "end": "2022-12-30",
        "requested_label_count": REQUESTED_LABEL_COUNT,
        "session_count": SOURCE_SESSION_COUNT,
    }:
        raise ValueError("action manifest scope differs from the bounded pilot")
    manifest_controls = (
        ("source_inventory", source_inventory_path, expected_pins.source_inventory_sha256),
        ("requested_labels", requested_labels_path, expected_pins.requested_labels_sha256),
        ("calendar_certificate", calendar_path, expected_pins.calendar_sha256),
        ("point_in_time_identity", identity_path, expected_pins.point_in_time_identity_sha256),
    )
    for name, control_path, digest in manifest_controls:
        entry = manifest.get(name)
        entry_path, entry_size, entry_digest = _file_entry(entry, name)
        if entry_path != str(control_path).replace("\\", "/"):
            raise ValueError(f"action manifest {name} control path differs")
        if entry_digest != digest:
            raise ValueError(f"action manifest {name} control hash differs")
        _read_pinned(root, entry_path, digest, states, expected_bytes=entry_size)

    action_payloads: list[dict[str, Any]] = []
    action_entries = manifest.get("corporate_action_caches")
    if not isinstance(action_entries, list) or not action_entries:
        raise ValueError("action manifest has no corporate-action caches")
    for entry in action_entries:
        file_path, size, digest = _file_entry(entry, "corporate action")
        action_payloads.append(
            _strict_json(
                _read_pinned(root, file_path, digest, states, expected_bytes=size),
                "corporate-action cache",
            )
        )
    actions = _derive_actions(action_payloads, frozenset(labels), sessions[0], sessions[-1])
    unresolved_rows = manifest.get("unresolved_actions")
    if not isinstance(unresolved_rows, list):
        raise ValueError("action manifest unresolved-action list is malformed")
    unresolved = tuple(
        UnresolvedAction(
            label=str(item["label"]),
            ex_date=date.fromisoformat(str(item["ex_date"])),
            kind=str(item["kind"]),
            subject=str(item["subject"]),
        )
        for item in unresolved_rows
        if isinstance(item, dict)
    )
    if {(item.label, item.ex_date, item.subject) for item in unresolved} != {
        (item.symbol, item.ex_date, item.subject) for item in actions.unpriceable
    }:
        raise ValueError("derived unresolved actions differ from the action manifest")

    identity_records, conflicts = identity.get("records"), identity.get("conflicts")
    if not isinstance(identity_records, list) or not isinstance(conflicts, list):
        raise ValueError("point-in-time identity payload is malformed")
    if [item.get("requested_name") for item in identity_records] != list(labels):
        raise ValueError("point-in-time identity labels differ from the requested-label axis")
    overrides: dict[tuple[str, date], tuple[str, str]] = {}
    for item in conflicts:
        if not isinstance(item, dict) or item.get("requested_name") not in labels:
            continue
        at = date.fromisoformat(str(item.get("date")))
        if at not in sessions:
            continue
        label = str(item["requested_name"])
        symbol = item.get("symbol")
        existing_isin, raw_isin = item.get("existing_isin"), item.get("raw_isin")
        if (
            symbol != label
            or not isinstance(existing_isin, str)
            or not existing_isin
            or not isinstance(raw_isin, str)
            or not raw_isin
        ):
            raise ValueError("in-scope PIT conflict override is malformed or aliased")
        override_key = (label, at)
        value = (existing_isin, raw_isin)
        if override_key in overrides:
            raise ValueError("duplicate in-scope PIT conflict override")
        overrides[override_key] = value

    identities: list[DatedIdentitySeries] = []
    applied_overrides: set[tuple[str, date]] = set()
    for record in identity_records:
        label = str(record["requested_name"])
        observations: dict[date, tuple[str, str | None]] = {}
        for item in record.get("dated_observations", []):
            if not isinstance(item, dict):
                raise ValueError("dated identity observation is malformed")
            at = date.fromisoformat(str(item.get("date")))
            if at not in sessions:
                continue
            symbol = str(item.get("symbol"))
            if item.get("series") != "EQ" or symbol != label or at in observations:
                raise ValueError("in-scope identity is duplicated, aliased, or not EQ")
            isin = item.get("isin")
            observations[at] = (symbol, None if isin is None else str(isin))
        symbols: list[str | None] = []
        isins: list[str | None] = []
        for at in sessions:
            source_present = label in cache_by_session[at]
            observation = observations.get(at)
            if source_present != (observation is not None):
                raise ValueError("PIT identity presence differs from the selected source cache")
            if observation is None:
                symbols.append(None)
                isins.append(None)
                continue
            symbol, isin = observation
            override = overrides.get((label, at))
            if override is not None:
                if isin != override[0]:
                    raise ValueError("PIT conflict existing ISIN differs from the observed cell")
                isin = override[1]
                applied_overrides.add((label, at))
            if not isin:
                raise ValueError("in-scope PIT observed cell lacks an authoritative ISIN")
            symbols.append(symbol)
            isins.append(isin)
        identities.append(DatedIdentitySeries(label, tuple(symbols), tuple(isins)))
    if applied_overrides != set(overrides):
        raise ValueError("an in-scope relevant PIT conflict override was not applied")

    loaded_universe = load_goal(_bound_path(root, goal_path)).universe
    if loaded_universe != universe:
        raise ValueError("caller universe differs from the pinned goal.yaml universe")
    panel, audit = prepare_daily_pilot_panel(
        sessions=sessions,
        requested_labels=labels,
        raw_by_session=cache_by_session,
        identities=tuple(identities),
        raw_pilot_statuses=statuses,
        actions=actions,
        unresolved_actions=unresolved,
        universe=universe,
        expected_session_dates_sha256=expected_pins.session_dates_sha256,
        expected_requested_labels_sha256=expected_pins.requested_label_axis_sha256,
    )

    before = dict(states)
    for path, (size, digest) in before.items():
        _read_pinned(root, path, digest, states, expected_bytes=size)
    if states != before:
        raise ValueError("bound input state changed during preparation")
    state_digest = _json_digest(
        [[path, size, digest] for path, (size, digest) in sorted(states.items())]
    )
    return BoundPreparation(
        panel=panel,
        audit=audit,
        pins=expected_pins,
        source_pins_verified=True,
        verified_file_count=len(states),
        verified_source_file_count=len(raw_entries) + len(cache_entries),
        raw_isin_overrides_applied=len(applied_overrides),
        input_state_sha256=state_digest,
    )


def _transform_sha256() -> str:
    root = Path(__file__).resolve().parents[2]
    paths = (
        Path(__file__).resolve(),
        root / "icarus/engine/panelbuild.py",
        root / "icarus/engine/daily_pilot_admission.py",
        root / "icarus/agents/data/nseactions.py",
    )
    digest = hashlib.sha256()
    for path in paths:
        content = path.read_bytes()
        relative = path.relative_to(root).as_posix().encode()
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(content).to_bytes(8, "big"))
        digest.update(content)
    return digest.hexdigest()


def publish_prepared_panel_once(
    panel: Panel,
    audit: PrepareAudit,
    path: Path,
    pins: PreparationPins,
) -> dict[str, Any]:
    """Write a new NPZ exclusively, verify its decoded digest, and return a pending receipt."""

    if path.exists():
        raise FileExistsError(path)
    if (
        len(panel.symbols) != REQUESTED_LABEL_COUNT
        or len(panel) != SOURCE_SESSION_COUNT
        or panel.benchmark is not None
        or audit.requested_label_count != REQUESTED_LABEL_COUNT
        or audit.session_count != SOURCE_SESSION_COUNT
    ):
        raise ValueError("only the bounded 693-by-257 benchmark-free panel may be published")
    if (
        pins.session_dates_sha256 != audit.session_dates_sha256
        or pins.requested_label_axis_sha256 != audit.requested_label_axis_sha256
    ):
        raise ValueError("pending publication pins differ from the prepared axes")
    path.parent.mkdir(parents=True, exist_ok=True)
    report = BuildReport(
        sessions=len(panel),
        symbols_seen=len(panel.symbols),
        symbols_kept=len(panel.symbols),
        tradable_symbol_days=int(panel.tradable.sum()),
        min_universe_size=int(panel.tradable.sum(axis=0).min()),
        median_universe_size=float(np.median(panel.tradable.sum(axis=0))),
        max_universe_size=int(panel.tradable.sum(axis=0).max()),
    )
    handle, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".npz"
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        save_panel(panel, report, temporary)
        decoded = load_panel(temporary)
        decoded_digest = panel_sha256(decoded)
        expected_digest = panel_sha256(panel)
        if decoded_digest != expected_digest:
            raise ValueError("prepared NPZ decoded panel digest differs before publication")
        file_digest = hashlib.sha256(temporary.read_bytes()).hexdigest()
        if os.name == "nt":
            # Windows rename is same-volume atomic and refuses an existing destination.  Hard
            # links are unavailable under the production sandbox's restricted file ACL.
            os.rename(temporary, path)
        else:
            # POSIX rename replaces an existing path, so link provides the exclusive atomic
            # publication primitive there instead.
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)

    published = load_panel(path)
    if panel_sha256(published) != decoded_digest:
        raise ValueError("prepared NPZ changed during exclusive publication")
    return {
        "schema_version": 1,
        "status": "PENDING_SOURCE_USE_AND_FINAL_QUALIFICATION",
        "data_qualified": False,
        "source_use_authorized": False,
        "calendar_qualified": False,
        "actions_qualified": False,
        "point_in_time_qualified": False,
        "run_authorized": False,
        "session_count": len(panel),
        "requested_label_count": len(panel.symbols),
        "canonical_source_indices": list(range(SOURCE_SESSION_COUNT)),
        "benchmark_present": False,
        "pins_verified_by_preparer": False,
        "actual_emission_supported": False,
        "pins": pins.as_json(),
        "selected_lineage_sha256": audit.selected_lineage_sha256,
        "action_ledger_sha256": audit.action_ledger_sha256,
        "transform_sha256": _transform_sha256(),
        "panel_file_sha256": file_digest,
        "panel_sha256": decoded_digest,
        "panel_nbytes": audit.panel_nbytes,
        "observed_cells": audit.observed_cells,
        "explicit_absent_cells": audit.explicit_absent_cells,
        "research_sanity_excluded_cells": audit.research_sanity_excluded_cells,
        "priceable_action_rows": audit.priceable_action_rows,
        "priceable_action_cuts": audit.priceable_action_cuts,
        "priceable_pilot_action_rows": audit.priceable_pilot_action_rows,
        "dispositions": [
            {
                "label": item.label,
                "raw_statuses": list(item.raw_statuses),
                "effective_statuses": list(item.effective_statuses),
            }
            for item in audit.dispositions
        ],
    }


__all__ = [
    "BoundPreparation",
    "DatedIdentitySeries",
    "PreparationPins",
    "PrepareAudit",
    "PreparedDisposition",
    "bind_and_prepare_daily_pilot",
    "prepare_daily_pilot_panel",
    "publish_prepared_panel_once",
]
