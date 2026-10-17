from __future__ import annotations

import hashlib
import json
import math
import shutil
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path

import numpy as np
import pytest

from icarus.agents.data.corpactions import Split
from icarus.agents.data.nseactions import ActionHistory, Unpriceable
from icarus.common.config import Universe, load_goal
from icarus.engine.daily_pilot import PILOT_DATES, build_invented_admission, panel_sha256
from icarus.engine.daily_pilot_admission import (
    ACTION_UNRESOLVED_LOOKBACK,
    UnresolvedAction,
)
from icarus.engine.daily_pilot_prepare import (
    BoundPreparation,
    DatedIdentitySeries,
    PreparationPins,
    PrepareAudit,
    bind_and_prepare_daily_pilot,
    prepare_daily_pilot_panel,
    publish_prepared_panel_once,
)
from icarus.engine.panelbuild import load_panel
from icarus.strategy.dsl import Panel

_SESSIONS = build_invented_admission().session_dates
_LABELS = build_invented_admission().labels
_ACTIVE = "SYN000"
_SECOND = "SYN001"
_LIQUID = "LIQUIDBEES"
_ISIN_ACTIVE = "INE000000001"
_ISIN_SECOND = "INE000000002"
_ISIN_LIQUID = "INE000000003"


def _digest(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


_SESSION_AXIS_SHA256 = _digest([value.isoformat() for value in _SESSIONS])
_LABEL_AXIS_SHA256 = _digest(list(_LABELS))


def _universe() -> Universe:
    return Universe(
        min_avg_turnover_inr=500_000_000,
        turnover_window_sessions=20,
        min_close_inr=30,
        dividend_convention="price_return",
        history_years=1,
    )


def _row(price: float) -> tuple[str, str, str, str, str, str]:
    return (
        str(price),
        str(price + 1.0),
        str(price - 1.0),
        str(price),
        "1000000",
        "1000000000",
    )


def _identity_series(
    observed: dict[str, str] | None = None,
) -> tuple[DatedIdentitySeries, ...]:
    observed = {_ACTIVE: _ISIN_ACTIVE, _LIQUID: _ISIN_LIQUID} if observed is None else observed
    return tuple(
        DatedIdentitySeries(
            label,
            tuple(label if label in observed else None for _ in _SESSIONS),
            tuple(observed.get(label) for _ in _SESSIONS),
        )
        for label in _LABELS
    )


def _raw(
    *,
    active_prices: tuple[float, ...] | None = None,
    include_second: bool = False,
) -> dict[date, dict[str, tuple[str, str, str, str, str, str]]]:
    prices = active_prices or (100.0,) * len(_SESSIONS)
    assert len(prices) == len(_SESSIONS)
    return {
        session: {
            _ACTIVE: _row(prices[index]),
            _LIQUID: _row(1000.0),
            **({_SECOND: _row(120.0)} if include_second else {}),
        }
        for index, session in enumerate(_SESSIONS)
    }


def _statuses(
    *, active: tuple[str, ...] = ("CONDITIONAL_QUALIFIES",) * 5
) -> dict[str, tuple[str, ...]]:
    return {
        label: (
            ("CONDITIONAL_QUALIFIES",) * 5
            if label == _LIQUID
            else active
            if label == _ACTIVE
            else ("MISSING_WINDOW",) * 5
        )
        for label in _LABELS
    }


def _actions(
    *,
    splits: dict[str, tuple[Split, ...]] | None = None,
    unpriceable: tuple[Unpriceable, ...] = (),
    unrecognised: tuple[Unpriceable, ...] = (),
) -> ActionHistory:
    return ActionHistory(
        frm=_SESSIONS[0],
        to=_SESSIONS[-1],
        splits={} if splits is None else splits,
        unpriceable=unpriceable,
        unrecognised=unrecognised,
    )


def _prepare(
    *,
    raw: dict[date, dict[str, tuple[str, str, str, str, str, str]]] | None = None,
    identities: tuple[DatedIdentitySeries, ...] | None = None,
    statuses: dict[str, tuple[str, ...]] | None = None,
    actions: ActionHistory | None = None,
    unresolved: tuple[UnresolvedAction, ...] = (),
) -> tuple[Panel, PrepareAudit]:
    return prepare_daily_pilot_panel(
        sessions=_SESSIONS,
        requested_labels=_LABELS,
        raw_by_session=_raw() if raw is None else raw,
        identities=_identity_series() if identities is None else identities,
        raw_pilot_statuses=_statuses() if statuses is None else statuses,
        actions=_actions() if actions is None else actions,
        unresolved_actions=unresolved,
        universe=_universe(),
        expected_session_dates_sha256=_SESSION_AXIS_SHA256,
        expected_requested_labels_sha256=_LABEL_AXIS_SHA256,
    )


def test_retains_all_693_labels_and_explicit_absence_without_survivor_drop() -> None:
    panel, audit = _prepare()

    assert len(panel.symbols) == 693
    assert len(panel) == 257
    absent = panel.index_of(_SECOND)
    liquid = panel.index_of(_LIQUID)
    active = panel.index_of(_ACTIVE)
    assert np.isnan(panel.bars[absent].close).all()
    assert not panel.tradable[absent].any()
    assert not panel.tradable[liquid].any()
    assert not panel.tradable[active, :19].any()
    assert panel.tradable[active, 19:].all()
    assert audit.observed_cells == 514
    assert audit.explicit_absent_cells == 693 * 257 - 514
    assert audit.panel_nbytes == 693 * 257 * (5 * 8 + 1)
    assert audit.panel_nbytes < 8_000_000


def test_declared_identity_must_be_direct_unique_and_have_its_raw_row() -> None:
    identities = list(_identity_series())
    at = _LABELS.index(_ACTIVE)
    identities[at] = replace(
        identities[at],
        symbols=("OLD_SUCCESSOR", *identities[at].symbols[1:]),
    )
    with pytest.raises(ValueError, match="successor or alias"):
        _prepare(identities=tuple(identities))

    identities = list(_identity_series())
    identities[at] = replace(
        identities[at],
        isins=(None, *identities[at].isins[1:]),
    )
    with pytest.raises(ValueError, match="symbol and ISIN together"):
        _prepare(identities=tuple(identities))

    raw = _raw()
    del raw[_SESSIONS[17]][_ACTIVE]
    with pytest.raises(ValueError, match="declared present but raw row is absent"):
        _prepare(raw=raw)


def test_shared_same_date_isin_is_refused() -> None:
    identities = _identity_series(
        {_ACTIVE: _ISIN_ACTIVE, _SECOND: _ISIN_ACTIVE, _LIQUID: _ISIN_LIQUID}
    )
    with pytest.raises(ValueError, match="shared ISIN"):
        _prepare(identities=identities, raw=_raw(include_second=True))


def test_raw_membership_precedes_compound_adjustment_and_input_is_not_double_adjusted() -> None:
    cut = 100
    prices = (600.0,) * cut + (100.0,) * (len(_SESSIONS) - cut)
    actions = _actions(
        splits={
            _ACTIVE: (
                Split(_SESSIONS[cut], Decimal("2")),
                Split(_SESSIONS[cut], Decimal("3")),
            )
        }
    )
    raw = _raw(active_prices=prices)

    first, first_audit = _prepare(raw=raw, actions=actions)
    second, second_audit = _prepare(raw=raw, actions=actions)

    active = first.index_of(_ACTIVE)
    assert first.bars[active].close[cut - 1] == pytest.approx(100.0)
    assert first.bars[active].close[cut] == pytest.approx(100.0)
    assert first.bars[active].volume[cut - 1] == pytest.approx(6_000_000.0)
    assert first_audit.priceable_action_rows == 2
    assert first_audit.priceable_action_cuts == 1
    assert first_audit.priceable_pilot_action_rows == 0
    assert panel_sha256(first) == panel_sha256(second)
    assert first_audit.action_ledger_sha256 == second_audit.action_ledger_sha256


def test_action_guard_changes_final_membership_after_raw_screen_reconciliation() -> None:
    event = UnresolvedAction(_ACTIVE, _SESSIONS[10], "DEMERGER", "Demerger")
    actions = _actions(unpriceable=(Unpriceable(_ACTIVE, _SESSIONS[10], "Demerger"),))

    panel, audit = _prepare(actions=actions, unresolved=(event,))

    item = next(item for item in audit.dispositions if item.label == _ACTIVE)
    assert item.raw_statuses == ("CONDITIONAL_QUALIFIES",) * 5
    assert item.effective_statuses == (ACTION_UNRESOLVED_LOOKBACK,) * 5
    assert not panel.tradable[panel.index_of(_ACTIVE), -5:].any()


def test_unknown_action_and_unexplained_discontinuity_are_refused() -> None:
    unknown = Unpriceable(_ACTIVE, _SESSIONS[10], "Unknown capital change")
    with pytest.raises(ValueError, match="unrecognised corporate action"):
        _prepare(actions=_actions(unrecognised=(unknown,)))

    prices = (100.0,) * 100 + (50.0,) * (len(_SESSIONS) - 100)
    with pytest.raises(ValueError, match="unexplained discontinuity"):
        _prepare(raw=_raw(active_prices=prices))

    hidden_prices = (100.0,) * 100 + (50.0,) * 100 + (40.0,) * (len(_SESSIONS) - 200)
    event = UnresolvedAction(_ACTIVE, _SESSIONS[200], "DEMERGER", "Demerger")
    with pytest.raises(ValueError, match="unexplained discontinuity"):
        _prepare(
            raw=_raw(active_prices=hidden_prices),
            actions=_actions(unpriceable=(Unpriceable(_ACTIVE, _SESSIONS[200], "Demerger"),)),
            unresolved=(event,),
        )


def test_full_session_axis_digest_is_required() -> None:
    altered = list(_SESSIONS)
    index = next(
        index
        for index in range(1, len(altered) - 5)
        if (altered[index] - altered[index - 1]).days > 1
    )
    altered[index] = altered[index] - (altered[index] - altered[index - 1]) / 2

    with pytest.raises(ValueError, match="session axis digest"):
        prepare_daily_pilot_panel(
            sessions=tuple(altered),
            requested_labels=_LABELS,
            raw_by_session=_raw(),
            identities=_identity_series(),
            raw_pilot_statuses=_statuses(),
            actions=_actions(),
            unresolved_actions=(),
            universe=_universe(),
            expected_session_dates_sha256=_SESSION_AXIS_SHA256,
            expected_requested_labels_sha256=_LABEL_AXIS_SHA256,
        )


def test_priceable_action_on_a_decision_date_is_refused() -> None:
    split = Split(_SESSIONS[-1], Decimal("2"))
    with pytest.raises(ValueError, match="decision dates"):
        _prepare(actions=_actions(splits={_ACTIVE: (split,)}))


def test_source_statuses_must_reconcile_independently_with_raw_membership() -> None:
    with pytest.raises(ValueError, match="source-screen status differs from raw membership"):
        _prepare(statuses=_statuses(active=("BELOW_TURNOVER",) * 5))

    below_close = _raw(active_prices=(20.0,) * len(_SESSIONS))
    with pytest.raises(ValueError, match="source-screen reason differs from raw data"):
        _prepare(
            raw=below_close,
            statuses=_statuses(active=("MISSING_WINDOW",) * 5),
        )


def test_write_once_npz_round_trip_and_pending_packet_bind_all_provenance(
    tmp_path: Path,
) -> None:
    panel, audit = _prepare()
    output = tmp_path / "prepared-panel.npz"
    pins = PreparationPins(
        source_inventory_sha256="1" * 64,
        source_qa_sha256="2" * 64,
        requested_labels_sha256="3" * 64,
        calendar_sha256="4" * 64,
        action_manifest_sha256="5" * 64,
        point_in_time_identity_sha256="6" * 64,
        goal_sha256="7" * 64,
        session_dates_sha256=_SESSION_AXIS_SHA256,
        requested_label_axis_sha256=_LABEL_AXIS_SHA256,
    )

    packet = publish_prepared_panel_once(panel, audit, output, pins)
    reloaded = load_panel(output)

    assert reloaded.benchmark is None
    assert reloaded.symbols == panel.symbols
    assert np.array_equal(reloaded.tradable, panel.tradable)
    assert np.array_equal(reloaded.bars[0].close, panel.bars[0].close, equal_nan=True)
    assert packet["panel_sha256"] == panel_sha256(panel) == panel_sha256(reloaded)
    assert packet["selected_lineage_sha256"] == audit.selected_lineage_sha256
    assert packet["action_ledger_sha256"] == audit.action_ledger_sha256
    assert packet["pins"] == {
        "source_inventory_sha256": "1" * 64,
        "source_qa_sha256": "2" * 64,
        "requested_labels_sha256": "3" * 64,
        "calendar_sha256": "4" * 64,
        "action_manifest_sha256": "5" * 64,
        "point_in_time_identity_sha256": "6" * 64,
        "goal_sha256": "7" * 64,
        "session_dates_sha256": _SESSION_AXIS_SHA256,
        "requested_label_axis_sha256": _LABEL_AXIS_SHA256,
    }
    assert all(
        packet[name] is False
        for name in (
            "data_qualified",
            "source_use_authorized",
            "calendar_qualified",
            "actions_qualified",
            "point_in_time_qualified",
            "run_authorized",
        )
    )
    assert len(packet["transform_sha256"]) == 64
    assert len(packet["panel_file_sha256"]) == 64
    assert packet["status"] == "PENDING_SOURCE_USE_AND_FINAL_QUALIFICATION"
    assert packet["pins_verified_by_preparer"] is False
    assert packet["actual_emission_supported"] is False

    with pytest.raises(FileExistsError):
        publish_prepared_panel_once(panel, audit, output, pins)
    assert panel_sha256(load_panel(output)) == packet["panel_sha256"]


def test_nonfinite_raw_value_is_never_copied_into_the_panel() -> None:
    raw = _raw()
    row = list(raw[_SESSIONS[7]][_ACTIVE])
    row[4] = str(math.inf)
    raw[_SESSIONS[7]][_ACTIVE] = tuple(row)  # type: ignore[assignment]

    with pytest.raises(ValueError, match="invalid raw row"):
        _prepare(raw=raw)


def test_physically_valid_subunit_row_is_observed_but_research_excluded() -> None:
    raw = _raw()
    raw[_SESSIONS[-20]][_ACTIVE] = ("0.5", "0.6", "0.4", "0.5", "100", "50")

    panel, audit = _prepare(
        raw=raw,
        statuses=_statuses(active=("MISSING_WINDOW",) * 5),
    )

    active = panel.index_of(_ACTIVE)
    assert np.isnan(panel.bars[active].close[-20])
    assert not panel.tradable[active, -5:].any()
    assert audit.observed_cells == 514
    assert audit.research_sanity_excluded_cells == 1


def _write_json(root: Path, relative: str, value: object) -> dict[str, object]:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    path.write_bytes(raw)
    return {"path": relative, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def _invented_bound_fixture(tmp_path: Path) -> tuple[dict[str, Path], PreparationPins, Universe]:
    paths = {
        "inventory": Path("inventory.json"),
        "qa": Path("source-qa.json"),
        "labels": Path("labels.json"),
        "calendar": Path("calendar.json"),
        "manifest": Path("action-manifest.json"),
        "identity": Path("identity.json"),
        "goal": Path("goal.yaml"),
    }
    repository = Path(__file__).resolve().parents[2]
    shutil.copyfile(repository / "goal.yaml", tmp_path / paths["goal"])
    goal_raw = (tmp_path / paths["goal"]).read_bytes()
    goal_pin = {
        "path": paths["goal"].as_posix(),
        "bytes": len(goal_raw),
        "sha256": hashlib.sha256(goal_raw).hexdigest(),
    }
    universe = load_goal(tmp_path / paths["goal"]).universe
    label_pin = _write_json(
        tmp_path,
        paths["labels"].as_posix(),
        {
            "schema_version": 1,
            "requested_count": len(_LABELS),
            "records": [{"requested_name": label} for label in _LABELS],
        },
    )
    calendar_pin = _write_json(
        tmp_path,
        paths["calendar"].as_posix(),
        {
            "resolved_dates": [
                {"date": value.isoformat(), "status": "REGULAR_SESSION_BASELINE"}
                for value in _SESSIONS
            ]
        },
    )
    identity_pin = _write_json(
        tmp_path,
        paths["identity"].as_posix(),
        {
            "records": [
                {
                    "requested_name": label,
                    "dated_observations": [
                        {
                            "date": value.isoformat(),
                            "symbol": label,
                            "series": "EQ",
                            "isin": (
                                "INE000000000"
                                if label == _ACTIVE and value == _SESSIONS[0]
                                else _ISIN_ACTIVE
                                if label == _ACTIVE
                                else _ISIN_LIQUID
                            ),
                        }
                        for value in _SESSIONS
                    ]
                    if label in {_ACTIVE, _LIQUID}
                    else [],
                }
                for label in _LABELS
            ],
            "conflicts": [
                {
                    "date": _SESSIONS[0].isoformat(),
                    "requested_name": _ACTIVE,
                    "symbol": _ACTIVE,
                    "existing_isin": "INE000000000",
                    "raw_isin": _ISIN_ACTIVE,
                }
            ],
        },
    )
    raw_entries: list[dict[str, object]] = []
    cache_entries: list[dict[str, object]] = []
    for index, session in enumerate(_SESSIONS):
        raw_path = f"raw/raw-{index:03d}.zip"
        raw_file = tmp_path / raw_path
        raw_file.parent.mkdir(parents=True, exist_ok=True)
        raw_bytes = f"invented raw {session.isoformat()}".encode()
        raw_file.write_bytes(raw_bytes)
        raw_entries.append(
            {
                "date": session.isoformat(),
                "path": raw_path,
                "bytes": len(raw_bytes),
                "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            }
        )
        cache_path = f"cache/cache-{index:03d}.json"
        cache_entries.append(
            {
                "date": session.isoformat(),
                **_write_json(
                    tmp_path,
                    cache_path,
                    {
                        "schema": 2,
                        "rows": {
                            _ACTIVE: list(_row(100)),
                            _LIQUID: list(_row(1000)),
                            "UNREQUESTED": list(_row(80)),
                        },
                    },
                ),
            }
        )
    inventory_pin = _write_json(
        tmp_path,
        paths["inventory"].as_posix(),
        {
            "required_interval": {
                "start": "2021-12-21",
                "end": "2022-12-30",
                "dates": [value.isoformat() for value in _SESSIONS],
                "included_calendar_statuses": ["REGULAR_SESSION_BASELINE"],
            },
            "calendar": {"path": paths["calendar"].as_posix(), "sha256": calendar_pin["sha256"]},
            "universe": {
                "stock_label_inventory_path": paths["labels"].as_posix(),
                "stock_label_inventory_sha256": label_pin["sha256"],
            },
            "raw_nse_archives": {"files": raw_entries},
            "daily_cache": {"files": cache_entries},
        },
    )
    qa_states = [*raw_entries, *cache_entries, inventory_pin, label_pin, calendar_pin, goal_pin]
    qa_pin = _write_json(
        tmp_path,
        paths["qa"].as_posix(),
        {
            "status": "SOURCE_PAYLOAD_QA_PASS_OTHER_ADMISSION_GATES_OPEN",
            "payload_checks_pass": True,
            "scope": {
                "start": "2021-12-21",
                "end": "2022-12-30",
                "sessions": 257,
                "raw_files": 257,
                "cache_files": 257,
                "requested_labels": 693,
                "pilot_dates": 5,
            },
            "source_inventory_sha256": inventory_pin["sha256"],
            "source_scan": {
                "issues": [],
                "sessions_attempted": 257,
                "sessions_aligned": 257,
                "raw_eq_rows": 771,
                "cache_rows": 771,
                "aligned_eq_rows": 771,
            },
            "input_state_unchanged": True,
            "input_state_before": qa_states,
            "input_state_after": qa_states,
            "eligibility": {
                "requested_labels_retained": 693,
                "dates": {
                    pilot.isoformat(): {
                        "all_693_results": [
                            {
                                "requested_name": label,
                                "source_screen_status": (
                                    "CONDITIONAL_QUALIFIES"
                                    if label in {_ACTIVE, _LIQUID}
                                    else "MISSING_WINDOW"
                                ),
                            }
                            for label in _LABELS
                        ]
                    }
                    for pilot in PILOT_DATES
                },
            },
        },
    )
    action_pin = _write_json(tmp_path, "actions.json", {"schema": 1, "rows": []})
    manifest_pin = _write_json(
        tmp_path,
        paths["manifest"].as_posix(),
        {
            "scope": {
                "start": "2021-12-21",
                "end": "2022-12-30",
                "requested_label_count": 693,
                "session_count": 257,
            },
            "source_inventory": inventory_pin,
            "requested_labels": label_pin,
            "calendar_certificate": calendar_pin,
            "point_in_time_identity": identity_pin,
            "corporate_action_caches": [action_pin],
            "unresolved_actions": [],
        },
    )
    pins = PreparationPins(
        source_inventory_sha256=str(inventory_pin["sha256"]),
        source_qa_sha256=str(qa_pin["sha256"]),
        requested_labels_sha256=str(label_pin["sha256"]),
        calendar_sha256=str(calendar_pin["sha256"]),
        action_manifest_sha256=str(manifest_pin["sha256"]),
        point_in_time_identity_sha256=str(identity_pin["sha256"]),
        goal_sha256=str(goal_pin["sha256"]),
        session_dates_sha256=_SESSION_AXIS_SHA256,
        requested_label_axis_sha256=_LABEL_AXIS_SHA256,
    )
    return paths, pins, universe


def _bind_fixture(
    root: Path, paths: dict[str, Path], pins: PreparationPins, universe: Universe
) -> BoundPreparation:
    return bind_and_prepare_daily_pilot(
        root=root,
        source_inventory_path=paths["inventory"],
        source_qa_path=paths["qa"],
        requested_labels_path=paths["labels"],
        calendar_path=paths["calendar"],
        action_manifest_path=paths["manifest"],
        identity_path=paths["identity"],
        goal_path=paths["goal"],
        expected_pins=pins,
        universe=universe,
    )


def test_source_binding_rehashes_full_bundle_and_applies_exact_pit_override(
    tmp_path: Path,
) -> None:
    paths, pins, universe = _invented_bound_fixture(tmp_path)

    bound = _bind_fixture(tmp_path, paths, pins, universe)

    assert isinstance(bound, BoundPreparation)
    assert bound.source_pins_verified is True
    assert bound.verified_source_file_count == 514
    assert bound.raw_isin_overrides_applied == 1
    assert len(bound.panel.symbols) == 693
    assert bound.audit.observed_cells == 514

    first_raw = tmp_path / "raw/raw-000.zip"
    first_raw.write_bytes(first_raw.read_bytes() + b"mutation")
    with pytest.raises(ValueError, match="pinned file changed"):
        _bind_fixture(tmp_path, paths, pins, universe)


def test_source_binding_refuses_semantic_status_and_manifest_control_mismatch(
    tmp_path: Path,
) -> None:
    paths, pins, universe = _invented_bound_fixture(tmp_path)
    qa_path = tmp_path / paths["qa"]
    original_qa = qa_path.read_bytes()
    qa = json.loads(original_qa)
    qa["eligibility"]["dates"][PILOT_DATES[0].isoformat()]["all_693_results"][
        _LABELS.index(_ACTIVE)
    ]["source_screen_status"] = "BELOW_TURNOVER"
    qa_raw = json.dumps(qa, sort_keys=True, separators=(",", ":")).encode()
    qa_path.write_bytes(qa_raw)
    with pytest.raises(ValueError, match="source-screen status differs"):
        _bind_fixture(
            tmp_path,
            paths,
            replace(pins, source_qa_sha256=hashlib.sha256(qa_raw).hexdigest()),
            universe,
        )

    qa_path.write_bytes(original_qa)
    manifest_path = tmp_path / paths["manifest"]
    manifest = json.loads(manifest_path.read_bytes())
    manifest["requested_labels"]["sha256"] = "f" * 64
    manifest_raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest_path.write_bytes(manifest_raw)
    with pytest.raises(ValueError, match="requested_labels control hash differs"):
        _bind_fixture(
            tmp_path,
            paths,
            replace(
                pins,
                action_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
            ),
            universe,
        )


def test_source_binding_requires_every_relevant_pit_conflict_override(tmp_path: Path) -> None:
    paths, pins, universe = _invented_bound_fixture(tmp_path)
    identity_path = tmp_path / paths["identity"]
    identity = json.loads(identity_path.read_bytes())
    identity["conflicts"].append(
        {
            "date": _SESSIONS[0].isoformat(),
            "requested_name": _SECOND,
            "symbol": _SECOND,
            "existing_isin": "INE000000099",
            "raw_isin": _ISIN_SECOND,
        }
    )
    identity_raw = json.dumps(identity, sort_keys=True, separators=(",", ":")).encode()
    identity_path.write_bytes(identity_raw)
    identity_digest = hashlib.sha256(identity_raw).hexdigest()

    manifest_path = tmp_path / paths["manifest"]
    manifest = json.loads(manifest_path.read_bytes())
    manifest["point_in_time_identity"]["bytes"] = len(identity_raw)
    manifest["point_in_time_identity"]["sha256"] = identity_digest
    manifest_raw = json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
    manifest_path.write_bytes(manifest_raw)

    with pytest.raises(ValueError, match="conflict override was not applied"):
        _bind_fixture(
            tmp_path,
            paths,
            replace(
                pins,
                point_in_time_identity_sha256=identity_digest,
                action_manifest_sha256=hashlib.sha256(manifest_raw).hexdigest(),
            ),
            universe,
        )
