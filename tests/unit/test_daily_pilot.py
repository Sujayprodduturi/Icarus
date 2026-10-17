"""Seven-card daily pilot: fail closed before actual prices and keep warm-up out of trading."""

from __future__ import annotations

import hashlib
import json
import sys
from collections.abc import Sequence
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
import tools.run_daily_pilot as daily_cli

from icarus.common.config import load_goal
from icarus.engine.costmodel import Charges
from icarus.engine.daily_pilot import (
    DailyPilotAdmission,
    DailyPilotPayload,
    LabelDisposition,
    build_invented_admission,
    build_invented_panel,
    build_pilot_plans,
    daily_runner_sha256,
    load_actual_admission,
    load_daily_pilot_spec,
    panel_sha256,
    publish_json_once,
    run_actual_daily_pilot,
    run_invented_daily_pilot,
)
from icarus.engine.daily_pilot_admission import (
    ACTION_SOURCE_MANIFEST_SHA256,
    ACTION_UNRESOLVED_LOOKBACK,
    EXPECTED_UNRESOLVED_ACTIONS,
    POINT_IN_TIME_IDENTITY_SHA256,
    guard_unresolved_action_lookback,
)
from icarus.engine.runner import evaluate_once
from icarus.engine.signaltest import (
    SignalExitFragment,
    SignalRunResult,
    SignalSimulator,
    SignalTrade,
)
from icarus.engine.simcore import ExitReason, SignalId
from icarus.engine.timed_runner import (
    ExecutionBinding,
    RunAuthorization,
    RunnerError,
)
from icarus.state.trial_ledger import (
    TrialBatchReceipt,
    TrialBatchReservation,
    TrialBatchTerminal,
    TrialEvaluationResult,
    TrialReservationAuthorization,
    TrialTerminalState,
)
from icarus.strategy.dsl import Panel, Registry, StrategyCandidate


def _spec(repo_root: Path) -> Any:
    return load_daily_pilot_spec(
        repo_root,
        repo_root / "config/daily_pilot_inventory.json",
        load_goal(repo_root / "goal.yaml"),
    )


def _authorization(
    spec: Any | None = None, admission: DailyPilotAdmission | None = None
) -> RunAuthorization:
    bundle_sha256 = "a" * 64 if admission is None else admission.panel_file_sha256
    qualification_sha256 = "d" * 64 if admission is None else admission.qualification_sha256
    assert bundle_sha256 is not None
    assert qualification_sha256 is not None
    return RunAuthorization(
        "daily-pilot-test",
        datetime.now(UTC) - timedelta(minutes=1),
        datetime.now(UTC) + timedelta(minutes=10),
        bundle_sha256,
        "b" * 64,
        "c" * 64,
        qualification_sha256,
        "e" * 64 if spec is None else spec.goal_sha256,
        "f" * 64 if spec is None else spec.cards_sha256,
        "1" * 64 if spec is None else daily_runner_sha256(),
        True,
        False,
    )


def _binding(auth: RunAuthorization | None = None) -> ExecutionBinding:
    auth = auth or _authorization()
    return ExecutionBinding(
        auth.bundle_sha256,
        auth.approval_sha256,
        auth.policy_sha256,
        auth.qualification_sha256,
        auth.goal_sha256,
        auth.cards_sha256,
        auth.runner_sha256,
    )


def _json_digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(payload.encode()).hexdigest()


def _actual_fixture(
    tmp_path: Path, spec: Any, monkeypatch: pytest.MonkeyPatch
) -> tuple[DailyPilotAdmission, Any]:
    import icarus.engine.daily_pilot as pilot

    invented = build_invented_admission()
    dates = invented.session_dates
    replaced = {f"SYN{index:03d}" for index in range(len(EXPECTED_UNRESOLVED_ACTIONS))}
    labels = tuple(
        sorted(
            (
                *(label for label in invented.labels if label not in replaced),
                *(action.label for action in EXPECTED_UNRESOLVED_ACTIONS),
            )
        )
    )
    dispositions = tuple(
        LabelDisposition(
            label,
            guard_unresolved_action_lookback(
                label,
                ("CONDITIONAL_QUALIFIES",) * 5,
                dates[-5:],
                dates,
                EXPECTED_UNRESOLVED_ACTIONS,
            ),
            ("CONDITIONAL_QUALIFIES",) * 5,
        )
        for label in labels
    )
    invented = replace(invented, dispositions=dispositions)
    panel = build_invented_panel(invented)
    labels_document = {
        "schema_version": 1,
        "requested_count": len(labels),
        "records": [{"requested_name": label} for label in labels],
    }
    labels_path = tmp_path / "invented-requested-labels.json"
    labels_path.write_text(json.dumps(labels_document), encoding="utf-8")
    labels_digest = hashlib.sha256(labels_path.read_bytes()).hexdigest()
    calendar_digest = "c" * 64
    source = {
        "required_interval": {
            "dates": [value.isoformat() for value in dates],
            "session_count": len(dates),
        },
        "calendar": {"sha256": calendar_digest},
        "universe": {"stock_label_inventory_sha256": labels_digest},
    }
    source_path = tmp_path / "invented-source-inventory.json"
    source_path.write_text(json.dumps(source), encoding="utf-8")
    source_digest = hashlib.sha256(source_path.read_bytes()).hexdigest()
    monkeypatch.setattr(pilot, "SOURCE_INVENTORY_SHA256", source_digest)
    monkeypatch.setattr(pilot, "REQUESTED_LABELS_SHA256", labels_digest)
    monkeypatch.setattr(pilot, "CALENDAR_SHA256", calendar_digest)
    monkeypatch.setattr(
        pilot,
        "SESSION_IDENTITIES_SHA256",
        _json_digest([value.isoformat() for value in dates]),
    )
    monkeypatch.setattr(pilot, "LABEL_IDENTITIES_SHA256", _json_digest(list(labels)))
    qualification = {
        "schema_version": 1,
        "status": "QUALIFIED_FOR_DAILY_DESCRIPTIVE_PILOT",
        "data_qualified": True,
        "source_use_authorized": True,
        "calendar_qualified": True,
        "actions_qualified": True,
        "point_in_time_qualified": True,
        "source_inventory_sha256": source_digest,
        "requested_labels_sha256": labels_digest,
        "calendar_sha256": calendar_digest,
        "action_source_manifest_sha256": ACTION_SOURCE_MANIFEST_SHA256,
        "point_in_time_identity_sha256": POINT_IN_TIME_IDENTITY_SHA256,
        "unresolved_actions": [
            {
                "label": action.label,
                "ex_date": action.ex_date.isoformat(),
                "kind": action.kind,
                "subject": action.subject,
            }
            for action in EXPECTED_UNRESOLVED_ACTIONS
        ],
        "panel_file_sha256": "7" * 64,
        "panel_sha256": panel_sha256(panel),
        "goal_sha256": spec.goal_sha256,
        "cards_sha256": spec.cards_sha256,
        "label_dispositions": [
            {"label": item.label, "raw_screen_statuses": list(item.raw_screen_statuses)}
            for item in dispositions
        ],
    }
    qualification_path = tmp_path / "qualification.json"
    qualification_path.write_text(json.dumps(qualification), encoding="utf-8")
    return (
        load_actual_admission(qualification_path, source_path, labels_path),
        panel,
    )


def test_actual_admission_binds_action_identity_and_preserves_raw_screen_statuses(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(repo_root)
    admission, _ = _actual_fixture(tmp_path, spec, monkeypatch)
    mother = next(item for item in admission.dispositions if item.label == "MOTHERSON")

    assert admission.action_source_manifest_sha256 == ACTION_SOURCE_MANIFEST_SHA256
    assert admission.point_in_time_identity_sha256 == POINT_IN_TIME_IDENTITY_SHA256
    assert mother.raw_screen_statuses == ("CONDITIONAL_QUALIFIES",) * 5
    assert mother.pilot_statuses == (ACTION_UNRESOLVED_LOOKBACK,) * 5


def test_actual_admission_rejects_unbound_point_in_time_identity(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(repo_root)
    _actual_fixture(tmp_path, spec, monkeypatch)
    qualification_path = tmp_path / "qualification.json"
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    qualification["point_in_time_identity_sha256"] = "0" * 64
    qualification_path.write_text(json.dumps(qualification), encoding="utf-8")

    with pytest.raises(ValueError, match="evidence-bound"):
        load_actual_admission(
            qualification_path,
            tmp_path / "invented-source-inventory.json",
            tmp_path / "invented-requested-labels.json",
        )


def test_actual_admission_rejects_legacy_qualification_before_price_decode(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(repo_root)
    _actual_fixture(tmp_path, spec, monkeypatch)
    qualification_path = tmp_path / "qualification.json"
    qualification = json.loads(qualification_path.read_text(encoding="utf-8"))
    for field in (
        "action_source_manifest_sha256",
        "point_in_time_identity_sha256",
        "unresolved_actions",
    ):
        qualification.pop(field)
    for item in qualification["label_dispositions"]:
        item["pilot_statuses"] = item.pop("raw_screen_statuses")
    qualification_path.write_text(json.dumps(qualification), encoding="utf-8")

    with pytest.raises(ValueError, match="evidence-bound"):
        load_actual_admission(
            qualification_path,
            tmp_path / "invented-source-inventory.json",
            tmp_path / "invented-requested-labels.json",
        )


class _Ledger:
    def __init__(self, *, fail_reserve_at: int | None = None) -> None:
        self.events: list[str] = []
        self.batches: list[TrialBatchReservation] = []
        self.fail_reserve_at = fail_reserve_at

    def reserve(self, batch: TrialBatchReservation) -> TrialBatchReceipt:
        if self.fail_reserve_at == len(self.batches) + 1:
            self.events.append("reserve-failed")
            raise RuntimeError("invented reservation failure")
        self.events.append(f"reserve:{batch.strategy_name}")
        self.batches.append(batch)
        return TrialBatchReceipt(
            batch.run_group_id,
            hashlib.sha256(batch.strategy_name.encode()).hexdigest(),
            (uuid4(),),
            len(self.batches),
            True,
            TrialReservationAuthorization.NEW_EVALUATION,
        )

    def complete(
        self, receipt: TrialBatchReceipt, results: tuple[TrialEvaluationResult, ...]
    ) -> TrialBatchTerminal:
        del receipt, results
        self.events.append("complete")
        return TrialBatchTerminal(
            self.batches[-1].run_group_id,
            TrialTerminalState.COMPLETED,
            "a" * 64,
            None,
        )

    def fail(self, receipt: TrialBatchReceipt, *, failure_code: str) -> TrialBatchTerminal:
        del failure_code
        self.events.append("fail")
        return TrialBatchTerminal(
            receipt.run_group_id,
            TrialTerminalState.FAILED,
            None,
            "TEST_FAILURE",
        )


def test_inventory_and_invented_proof_run_exactly_seven_without_alpha(repo_root: Path) -> None:
    spec = _spec(repo_root)
    admission = build_invented_admission()
    report = run_invented_daily_pilot(spec, admission, load_goal(repo_root / "goal.yaml"))

    assert [item["strategy"] for item in report["evaluations"]] == [
        card.candidate.name for card in spec.cards
    ]
    assert len(report["evaluations"]) == 7
    assert report["requested_label_count"] == 693
    assert report["liquidbees_disposition"] == "CLASS_INELIGIBLE_FIXED_INCOME"
    assert report["benchmark"] is None
    assert report["pre_tax_alpha"] is None
    assert report["promotion_eligible"] is False
    assert report["inference_available"] is False
    assert report["portfolio_evaluation_count"] == 0
    assert all(item["surface"] == "SignalSimulator" for item in report["evaluations"])
    assert (
        sum(item["skip_reason_counts"].get("no_next_bar", 0) for item in report["evaluations"]) > 0
    )


def test_catalogue_tamper_is_rejected_before_a_plan_exists(repo_root: Path, tmp_path: Path) -> None:
    source = repo_root / "config/daily_pilot_inventory.json"
    inventory = json.loads(source.read_text(encoding="utf-8"))
    inventory["cards"][0]["sha256"] = "0" * 64
    tampered = tmp_path / "tampered-inventory.json"
    tampered.write_text(json.dumps(inventory), encoding="utf-8")

    with pytest.raises(ValueError, match="card identity"):
        load_daily_pilot_spec(
            repo_root,
            tampered,
            load_goal(repo_root / "goal.yaml"),
        )


@pytest.mark.parametrize(
    "changed",
    (
        "icarus/engine/example.py",
        "tools/run_daily_pilot.py",
        "config/daily_pilot_inventory.json",
    ),
)
def test_runner_hash_binds_engine_entrypoint_and_inventory(tmp_path: Path, changed: str) -> None:
    dependencies = {
        "icarus/engine/example.py": b"ENGINE = 1\n",
        "tools/run_daily_pilot.py": b"ENTRYPOINT = 1\n",
        "config/daily_pilot_inventory.json": b"{}",
        "pyproject.toml": b"[project]\nname = 'invented'\n",
        "uv.lock": b"version = 1\n",
    }
    for relative, value in dependencies.items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(value)
    before = daily_runner_sha256(tmp_path)
    (tmp_path / changed).write_bytes(dependencies[changed] + b"# changed\n")
    assert daily_runner_sha256(tmp_path) != before


def test_invented_proof_does_not_read_ignored_actual_controls(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real_read_bytes = Path.read_bytes

    def guarded_read_bytes(path: Path) -> bytes:
        value = path.as_posix()
        if "source-inventory/source-inventory.json" in value or value.endswith(
            "pilot-universe-qa/requested-labels.json"
        ):
            raise AssertionError("ignored actual control read")
        return real_read_bytes(path)

    monkeypatch.setattr(Path, "read_bytes", guarded_read_bytes)
    spec = _spec(repo_root)
    report = run_invented_daily_pilot(
        spec,
        build_invented_admission(),
        load_goal(repo_root / "goal.yaml"),
    )
    assert report["evaluation_count"] == 7


def test_stale_mark_report_preserves_individual_nonexecuted_provenance(repo_root: Path) -> None:
    import icarus.engine.daily_pilot as pilot

    spec = _spec(repo_root)
    decision = datetime(2022, 12, 26, tzinfo=UTC)
    entry = datetime(2022, 12, 27, tzinfo=UTC)
    price_source = datetime(2022, 12, 29, tzinfo=UTC)
    recognition = datetime(2022, 12, 30, tzinfo=UTC)

    def empty(turnover: str) -> Charges:
        return Charges(
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal(0),
            Decimal(turnover),
        )

    fragment = SignalExitFragment(
        2,
        Decimal("105"),
        price_source,
        255,
        recognition,
        256,
        ExitReason.STALE_MARK,
        empty("210"),
    )
    trade = SignalTrade(
        SignalId(
            spec.cards[0].candidate.name,
            spec.cards[0].candidate.version,
            "SYN",
            decision,
            252,
        ),
        entry,
        253,
        Decimal("100"),
        2,
        Decimal("200"),
        Decimal("5"),
        empty("200"),
        (fragment,),
    )
    row = pilot._result_payload(spec.cards[0], SignalRunResult((trade,), (), (), 1, 0))
    mark = row["exit_fragments"][0]
    assert mark["quantity"] == 2
    assert mark["price"] == "105"
    assert mark["price_source_date"] == "2022-12-29"
    assert mark["recognition_date"] == "2022-12-30"
    assert mark["estimated_charges"]["turnover"] == "210"
    assert mark["estimated_final_mark"] is True
    assert mark["executed_sale"] is False


def test_indicators_use_257_rows_but_simulator_receives_only_five(
    repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import icarus.engine.daily_pilot as pilot

    spec = _spec(repo_root)
    admission = build_invented_admission()
    payload = DailyPilotPayload.from_panel(build_invented_panel(admission), admission)
    seen: dict[str, object] = {}
    real_evaluate = evaluate_once

    def evaluate(
        strategy: StrategyCandidate,
        panel: Panel,
        registry: Registry,
        *,
        source_indices: Sequence[int] | None = None,
    ) -> Any:
        seen["indicator_rows"] = len(panel)
        return real_evaluate(
            strategy,
            panel,
            registry,
            source_indices=source_indices,
        )

    def simulate(
        self: SignalSimulator,
        strategy: object,
        panel: Panel,
        signals: object,
        stops: object,
        *,
        source_indices: Sequence[int],
        **kwargs: object,
    ) -> SignalRunResult:
        del self, strategy, signals, stops, kwargs
        seen["simulator_rows"] = len(panel)
        seen["source_indices"] = tuple(source_indices)
        return SignalRunResult((), (), (), 0, 0)

    monkeypatch.setattr("icarus.engine.daily_pilot.evaluate_once", evaluate)
    monkeypatch.setattr(SignalSimulator, "run", simulate)
    plans = build_pilot_plans(spec, admission)
    result = pilot.DailyPilotEvaluator(
        spec, load_goal(repo_root / "goal.yaml"), admission
    ).evaluate(plans[0], payload)

    assert len(result) == 1
    assert seen == {
        "indicator_rows": 257,
        "simulator_rows": 5,
        "source_indices": (252, 253, 254, 255, 256),
    }


def test_actual_applicability_failure_is_before_ledger_and_decode(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(repo_root)
    admission, _ = _actual_fixture(tmp_path, spec, monkeypatch)
    authorization = _authorization(spec, admission)
    ledger = _Ledger()
    decoded = False

    def decode() -> DailyPilotPayload:
        nonlocal decoded
        decoded = True
        raise AssertionError("price decoder reached")

    with pytest.raises(ValueError, match="693"):
        run_actual_daily_pilot(
            spec,
            replace(admission, dispositions=admission.dispositions[:-1]),
            load_goal(repo_root / "goal.yaml"),
            authorization,
            _binding(authorization),
            ledger,
            decode,
            repo_root / "var/verification/2026-10-16/daily-pilot/never.json",
        )
    assert ledger.events == []
    assert decoded is False


def test_actual_run_reserves_all_seven_before_decode_and_publishes_once(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(repo_root)
    admission, panel = _actual_fixture(tmp_path, spec, monkeypatch)
    authorization = _authorization(spec, admission)
    ledger = _Ledger()

    def decode() -> DailyPilotPayload:
        ledger.events.append("decode")
        return DailyPilotPayload.from_panel(panel, admission)

    monkeypatch.setattr(
        SignalSimulator,
        "run",
        lambda self, *args, **kwargs: SignalRunResult((), (), (), 0, 0),
    )
    output = tmp_path / "report.json"
    report = run_actual_daily_pilot(
        spec,
        admission,
        load_goal(repo_root / "goal.yaml"),
        authorization,
        _binding(authorization),
        ledger,
        decode,
        output,
    )

    assert ledger.events[:7] == [f"reserve:{card.candidate.name}" for card in spec.cards]
    assert ledger.events[7] == "decode"
    assert ledger.events.count("complete") == 7
    assert ledger.events.count("fail") == 0
    assert output.is_file()
    assert len(report["evaluations"]) == 7


def test_publication_collision_keeps_completed_terminals_and_releases_no_new_report(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(repo_root)
    admission, panel = _actual_fixture(tmp_path, spec, monkeypatch)
    authorization = _authorization(spec, admission)
    ledger = _Ledger()
    output = tmp_path / "report.json"
    output.write_text("old", encoding="utf-8")
    monkeypatch.setattr(
        SignalSimulator,
        "run",
        lambda self, *args, **kwargs: SignalRunResult((), (), (), 0, 0),
    )

    with pytest.raises(FileExistsError):
        run_actual_daily_pilot(
            spec,
            admission,
            load_goal(repo_root / "goal.yaml"),
            authorization,
            _binding(authorization),
            ledger,
            lambda: DailyPilotPayload.from_panel(panel, admission),
            output,
        )
    assert ledger.events.count("complete") == 7
    assert ledger.events.count("fail") == 0
    assert output.read_text(encoding="utf-8") == "old"


def test_partial_reservation_failure_decodes_nothing_and_fails_prior_counts(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(repo_root)
    admission, _ = _actual_fixture(tmp_path, spec, monkeypatch)
    authorization = _authorization(spec, admission)
    ledger = _Ledger(fail_reserve_at=4)
    decoded = False

    def decode() -> object:
        nonlocal decoded
        decoded = True
        return object()

    with pytest.raises(RunnerError, match="RESERVATION_SET_INCOMPLETE"):
        run_actual_daily_pilot(
            spec,
            admission,
            load_goal(repo_root / "goal.yaml"),
            authorization,
            _binding(authorization),
            ledger,
            decode,
            tmp_path / "report.json",
        )
    assert decoded is False
    assert ledger.events.count("fail") == 3
    assert not (tmp_path / "report.json").exists()


def test_decode_or_evaluation_failure_fails_all_seven_without_output(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(repo_root)
    admission, panel = _actual_fixture(tmp_path, spec, monkeypatch)
    authorization = _authorization(spec, admission)
    ledger = _Ledger()
    with pytest.raises(RunnerError, match="PRICE_DECODE_FAILED"):
        run_actual_daily_pilot(
            spec,
            admission,
            load_goal(repo_root / "goal.yaml"),
            authorization,
            _binding(authorization),
            ledger,
            lambda: (_ for _ in ()).throw(RuntimeError("invented decode failure")),
            tmp_path / "decode.json",
        )
    assert ledger.events.count("fail") == 7
    assert not (tmp_path / "decode.json").exists()

    ledger = _Ledger()
    monkeypatch.setattr(
        "icarus.engine.daily_pilot.DailyPilotEvaluator.evaluate",
        lambda *args: (_ for _ in ()).throw(RuntimeError("invented evaluation failure")),
    )
    with pytest.raises(RunnerError, match="EVALUATION_FAILED"):
        run_actual_daily_pilot(
            spec,
            admission,
            load_goal(repo_root / "goal.yaml"),
            authorization,
            _binding(authorization),
            ledger,
            lambda: DailyPilotPayload.from_panel(panel, admission),
            tmp_path / "evaluate.json",
        )
    assert ledger.events.count("fail") == 7
    assert not (tmp_path / "evaluate.json").exists()


def test_admission_rejects_post_2022_axis_and_wrong_liquidbees_disposition() -> None:
    admission = build_invented_admission()
    with pytest.raises(ValueError, match="fixed pilot axis"):
        replace(
            admission,
            session_dates=(
                *admission.session_dates[:-1],
                datetime(2023, 1, 2, tzinfo=UTC).date(),
            ),
        )
    with pytest.raises(ValueError, match="action guard"):
        LabelDisposition("LIQUIDBEES", ("ELIGIBLE",) * 5)
    with pytest.raises(ValueError, match="unreviewed status"):
        LabelDisposition("X", ("TYPO_EXCLUSION",) * 5)

    forged = replace(
        admission,
        invented=False,
        data_qualified=True,
        source_use_authorized=True,
        calendar_qualified=True,
        actions_qualified=True,
        point_in_time_qualified=True,
        full_manifest_sha256="191008c1b34c4a9b88285c0758d1725b8dca65555e96d16bbcbd09f313d10a7a",
        qualification_sha256="8" * 64,
        requested_labels_sha256="a88632590be0f8344e962e0b27179516e977161e113c59e9ef2f5d9748c25fd3",
        calendar_sha256="4d7902c85909cba50b00dfccd6c0d3b1051225ba547e33bc010b56ad0e683c91",
        panel_file_sha256="7" * 64,
        panel_sha256="6" * 64,
        goal_sha256="5" * 64,
        cards_sha256="4" * 64,
        evidence_binding_sha256="0" * 64,
        action_source_manifest_sha256=ACTION_SOURCE_MANIFEST_SHA256,
        point_in_time_identity_sha256=POINT_IN_TIME_IDENTITY_SHA256,
        unresolved_actions=EXPECTED_UNRESOLVED_ACTIONS,
    )
    forged = replace(forged, evidence_binding_sha256=forged._evidence_binding())
    with pytest.raises(ValueError, match="evidence binding"):
        forged.require_actual()


def test_actual_admission_content_cannot_be_self_rebound(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(repo_root)
    admission, _ = _actual_fixture(tmp_path, spec, monkeypatch)

    changed_dispositions = list(admission.dispositions)
    changed_label_index = next(
        index for index, item in enumerate(changed_dispositions) if item.label != "LIQUIDBEES"
    )
    changed_dispositions[changed_label_index] = replace(
        changed_dispositions[changed_label_index], label="SYN_FORGED"
    )
    forged_labels = replace(admission, dispositions=tuple(changed_dispositions))
    forged_labels = replace(
        forged_labels,
        evidence_binding_sha256=forged_labels._evidence_binding(),
    )
    with pytest.raises(ValueError, match="evidence binding"):
        forged_labels.require_actual()

    dates = list(admission.session_dates)
    changed_index = next(
        index for index in range(1, len(dates) - 1) if (dates[index] - dates[index - 1]).days > 1
    )
    dates[changed_index] = dates[changed_index - 1] + timedelta(days=1)
    forged_dates = replace(admission, session_dates=tuple(dates))
    forged_dates = replace(
        forged_dates,
        evidence_binding_sha256=forged_dates._evidence_binding(),
    )
    with pytest.raises(ValueError, match="evidence binding"):
        forged_dates.require_actual()


def test_payload_refuses_tradability_that_disagrees_with_admission(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(repo_root)
    admission, panel = _actual_fixture(tmp_path, spec, monkeypatch)
    liquid = panel.index_of("LIQUIDBEES")
    panel.tradable[liquid, -1] = True
    with pytest.raises(ValueError, match="tradability"):
        DailyPilotPayload.from_panel(panel, admission)


def test_atomic_publication_never_overwrites(tmp_path: Path) -> None:
    destination = tmp_path / "one.json"
    publish_json_once(destination, {"value": 1})
    with pytest.raises(FileExistsError):
        publish_json_once(destination, {"value": 2})
    assert destination.read_text(encoding="utf-8").strip() == '{"value":1}'


def test_actual_cli_rejects_stale_authorization_before_engine_or_panel(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(repo_root)
    admission, _ = _actual_fixture(tmp_path, spec, monkeypatch)
    stale = replace(
        _authorization(spec, admission),
        issued_at=datetime(2020, 1, 1, tzinfo=UTC),
        expires_at=datetime(2020, 1, 2, tzinfo=UTC),
    )
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "authorization_id": stale.authorization_id,
                "issued_at": stale.issued_at.isoformat().replace("+00:00", "Z"),
                "expires_at": stale.expires_at.isoformat().replace("+00:00", "Z"),
                "bundle_sha256": stale.bundle_sha256,
                "approval_sha256": stale.approval_sha256,
                "policy_sha256": stale.policy_sha256,
                "qualification_sha256": stale.qualification_sha256,
                "goal_sha256": stale.goal_sha256,
                "cards_sha256": stale.cards_sha256,
                "runner_sha256": stale.runner_sha256,
                "actual_ledger_activated": True,
                "invented": False,
            }
        )
        + "\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(daily_cli, "load_goal", lambda path: load_goal(repo_root / "goal.yaml"))
    monkeypatch.setattr(daily_cli, "load_daily_pilot_spec", lambda *args: spec)
    monkeypatch.setattr(daily_cli, "load_actual_admission", lambda *args: admission)
    monkeypatch.setattr(
        daily_cli,
        "create_engine",
        lambda dsn: (_ for _ in ()).throw(AssertionError("ledger engine reached")),
    )
    monkeypatch.setattr(
        daily_cli,
        "_file_sha256",
        lambda path: (_ for _ in ()).throw(AssertionError("panel reached")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_daily_pilot.py",
            "--actual",
            "--qualification",
            str(tmp_path / "qualification.json"),
            "--authorization",
            str(authorization_path),
            "--panel",
            str(tmp_path / "panel.npz"),
            "--activated-ledger-dsn",
            "postgresql://invented",
            "--output",
            str(tmp_path / "report.json"),
        ],
    )

    with pytest.raises(RunnerError, match="AUTHORIZATION_EXPIRED"):
        daily_cli.main()


def test_actual_cli_checks_panel_file_binding_before_decode(
    repo_root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    spec = _spec(repo_root)
    admission, _ = _actual_fixture(tmp_path, spec, monkeypatch)
    authorization = _authorization(spec, admission)
    authorization_path = tmp_path / "authorization.json"
    authorization_path.write_text("{}", encoding="utf-8")
    panel_path = tmp_path / "panel.npz"
    panel_path.write_bytes(b"invented wrong panel bytes")
    events: list[str] = []

    class _Engine:
        def dispose(self) -> None:
            events.append("dispose")

    monkeypatch.setattr(daily_cli, "load_goal", lambda path: load_goal(repo_root / "goal.yaml"))
    monkeypatch.setattr(daily_cli, "load_daily_pilot_spec", lambda *args: spec)
    monkeypatch.setattr(daily_cli, "load_actual_admission", lambda *args: admission)
    monkeypatch.setattr(daily_cli, "parse_run_authorization_json", lambda raw: authorization)
    monkeypatch.setattr(daily_cli, "create_engine", lambda dsn: _Engine())
    monkeypatch.setattr(daily_cli, "PostgresTrialLedger", lambda engine: object())

    def invoke_decoder(*args: Any) -> dict[str, Any]:
        events.append("seven-reservations-complete")
        decoder = args[6]
        assert callable(decoder)
        decoder()
        raise AssertionError("unreachable")

    monkeypatch.setattr(daily_cli, "run_actual_daily_pilot", invoke_decoder)
    monkeypatch.setattr(
        "icarus.engine.panelbuild.load_panel",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("price decode reached")),
    )
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "run_daily_pilot.py",
            "--actual",
            "--qualification",
            str(tmp_path / "qualification.json"),
            "--authorization",
            str(authorization_path),
            "--panel",
            str(panel_path),
            "--activated-ledger-dsn",
            "postgresql://invented",
            "--output",
            str(tmp_path / "report.json"),
        ],
    )

    with pytest.raises(ValueError, match="panel file differs"):
        daily_cli.main()
    assert events == ["seven-reservations-complete", "dispose"]
