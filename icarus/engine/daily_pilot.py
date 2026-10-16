"""Bounded seven-card daily descriptive pilot.

Actual inputs cross the counted-trial barrier before this module calls the injected price decoder.
The invented proof exercises the same card compiler and signal simulator without a ledger, market
data, credentials, or performance inference.
"""

from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Protocol, cast
from uuid import uuid4

import numpy as np
import numpy.typing as npt

from icarus.common.config import GoalConfig
from icarus.engine.backtest import slice_panel
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel
from icarus.engine.runner import evaluate_once
from icarus.engine.signaltest import SignalMissingReason, SignalRunResult, SignalSimulator
from icarus.engine.simcore import ExitReason
from icarus.engine.timed_evaluation import StrategySpec, load_strategy_catalogue
from icarus.engine.timed_runner import (
    EvaluationOutcome,
    EvaluationPlan,
    ExecutionBinding,
    GuardedTimedRunner,
    RunAuthorization,
)
from icarus.state.trial_ledger import (
    EvaluationReservation,
    TrialBatchReceipt,
    TrialBatchReservation,
    TrialBatchTerminal,
    TrialEvaluationResult,
    TrialKind,
)
from icarus.strategy.dsl import Bars, Panel
from icarus.strategy.library import default_registry

PILOT_DATES = tuple(date(2022, 12, day) for day in range(26, 31))
SOURCE_START = date(2021, 12, 21)
SOURCE_END = date(2022, 12, 30)
SOURCE_SESSION_COUNT = 257
PILOT_START_INDEX = 252
REQUESTED_LABEL_COUNT = 693
FIXED_INCOME_DISPOSITION = "CLASS_INELIGIBLE_FIXED_INCOME"
RESET_IDENTITY = "daily_descriptive_pilot_v1"
SOURCE_INVENTORY_SHA256 = "191008c1b34c4a9b88285c0758d1725b8dca65555e96d16bbcbd09f313d10a7a"
REQUESTED_LABELS_SHA256 = "a88632590be0f8344e962e0b27179516e977161e113c59e9ef2f5d9748c25fd3"
CALENDAR_SHA256 = "4d7902c85909cba50b00dfccd6c0d3b1051225ba547e33bc010b56ad0e683c91"
SESSION_IDENTITIES_SHA256 = "061958ca5e9606bc0e5ec79db8b347d7dcaee2bc62924d01475e33821da0956d"
LABEL_IDENTITIES_SHA256 = "0cb9acc3eeb45ebdbf5443467d326c6f87f038c58957f7a7ff015390f9894790"
DISPOSITION_STATUSES = frozenset(
    {
        "ELIGIBLE",
        "BELOW_CLOSE",
        "BELOW_TURNOVER",
        "MISSING_WINDOW",
        FIXED_INCOME_DISPOSITION,
    }
)
EXPECTED_CARDS = (
    (
        "baseline_buy_and_hold",
        2,
        "b1bded2f21c1817adced9d4e789ae79f5e9058e433827276d0d1e434c1fd721e",
    ),
    (
        "defensive_low_vol_252_q63",
        1,
        "5fa59770122b26c1c8a16c835a6da0f5e9ad5801a774667b993ce7b79faab5de",
    ),
    (
        "donchian_55_20",
        1,
        "3214826be9dce200ca0696b9577f57bf0fb5a944131cd43b3000984a8d3bfcc0",
    ),
    (
        "donlevey_sweep_reclaim",
        2,
        "a39f9d507b16550b1bcf4a4997abd1ba73643fcf8b52b2aec4ea036a3bdfb295",
    ),
    (
        "short_term_reversal_uptrend",
        1,
        "3c32817984012706e8c2e9fc1e7c6a10ce13f2fd249ea45ee0c390e7a8eb4880",
    ),
    (
        "xs_momentum_20",
        2,
        "8905d1162d1fea9d2194e0a39312e2512b726b24db4b06f5d20fc5533614d725",
    ),
    (
        "xs_momentum_252_21",
        1,
        "814023ec6f40f245f68cdd82e010f56883601faeed0d24e6dffe2e4b6643fcec",
    ),
)


class _Ledger(Protocol):
    def reserve(self, batch: TrialBatchReservation) -> TrialBatchReceipt: ...

    def complete(
        self, receipt: TrialBatchReceipt, results: tuple[TrialEvaluationResult, ...]
    ) -> TrialBatchTerminal: ...

    def fail(self, receipt: TrialBatchReceipt, *, failure_code: str) -> TrialBatchTerminal: ...


def _sha(value: str | None, name: str, *, required: bool) -> None:
    if value is None:
        if required:
            raise ValueError(f"{name} is required")
        return
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise ValueError(f"{name} must be a lowercase SHA-256")


def _digest_json(value: object) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


@dataclass(frozen=True, slots=True)
class LabelDisposition:
    label: str
    pilot_statuses: tuple[str, ...]

    def __post_init__(self) -> None:
        if (
            not self.label
            or type(self.pilot_statuses) is not tuple
            or len(self.pilot_statuses) != 5
        ):
            raise ValueError("each requested label needs five daily pilot dispositions")
        if any(type(value) is not str or not value for value in self.pilot_statuses):
            raise ValueError("daily pilot dispositions must be nonempty strings")
        if not set(self.pilot_statuses).issubset(DISPOSITION_STATUSES):
            raise ValueError("daily pilot disposition uses an unreviewed status")


@dataclass(frozen=True, slots=True)
class DailyPilotAdmission:
    invented: bool
    data_qualified: bool
    source_use_authorized: bool
    calendar_qualified: bool
    actions_qualified: bool
    point_in_time_qualified: bool
    full_manifest_sha256: str | None
    qualification_sha256: str | None
    requested_labels_sha256: str | None
    calendar_sha256: str | None
    panel_file_sha256: str | None
    panel_sha256: str | None
    goal_sha256: str | None
    cards_sha256: str | None
    evidence_binding_sha256: str | None
    session_dates: tuple[date, ...]
    dispositions: tuple[LabelDisposition, ...]

    def __post_init__(self) -> None:
        flags = (
            self.invented,
            self.data_qualified,
            self.source_use_authorized,
            self.calendar_qualified,
            self.actions_qualified,
            self.point_in_time_qualified,
        )
        if any(type(value) is not bool for value in flags):
            raise TypeError("daily pilot qualification flags must be booleans")
        _sha(self.full_manifest_sha256, "full_manifest_sha256", required=not self.invented)
        _sha(self.qualification_sha256, "qualification_sha256", required=not self.invented)
        for name in (
            "requested_labels_sha256",
            "calendar_sha256",
            "panel_file_sha256",
            "panel_sha256",
            "goal_sha256",
            "cards_sha256",
            "evidence_binding_sha256",
        ):
            _sha(getattr(self, name), name, required=not self.invented)
        if (
            type(self.session_dates) is not tuple
            or len(self.session_dates) != SOURCE_SESSION_COUNT
            or self.session_dates[0] != SOURCE_START
            or self.session_dates[-1] != SOURCE_END
            or self.session_dates[-5:] != PILOT_DATES
            or any(
                right <= left
                for left, right in zip(self.session_dates, self.session_dates[1:], strict=False)
            )
        ):
            raise ValueError("source sessions must match the fixed pilot axis without 2023 bars")
        if type(self.dispositions) is not tuple or len(self.dispositions) != REQUESTED_LABEL_COUNT:
            raise ValueError("all 693 requested labels need unique daily dispositions")
        if any(not isinstance(item, LabelDisposition) for item in self.dispositions):
            raise ValueError("all 693 requested labels need unique daily dispositions")
        if len({item.label for item in self.dispositions}) != REQUESTED_LABEL_COUNT:
            raise ValueError("all 693 requested labels need unique daily dispositions")
        liquid = tuple(item for item in self.dispositions if item.label == "LIQUIDBEES")
        if len(liquid) != 1 or liquid[0].pilot_statuses != (FIXED_INCOME_DISPOSITION,) * 5:
            raise ValueError("LIQUIDBEES must remain the counted fixed-income disposition")

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(item.label for item in self.dispositions)

    def require_actual(self) -> None:
        if self.invented or not all(
            (
                self.data_qualified,
                self.source_use_authorized,
                self.calendar_qualified,
                self.actions_qualified,
                self.point_in_time_qualified,
            )
        ):
            raise ValueError("actual pilot admission is incomplete")
        _sha(self.full_manifest_sha256, "full_manifest_sha256", required=True)
        _sha(self.qualification_sha256, "qualification_sha256", required=True)
        if (
            self.full_manifest_sha256 != SOURCE_INVENTORY_SHA256
            or self.requested_labels_sha256 != REQUESTED_LABELS_SHA256
            or self.calendar_sha256 != CALENDAR_SHA256
            or _digest_json([value.isoformat() for value in self.session_dates])
            != SESSION_IDENTITIES_SHA256
            or _digest_json(list(self.labels)) != LABEL_IDENTITIES_SHA256
            or self.evidence_binding_sha256 != self._evidence_binding()
        ):
            raise ValueError("actual pilot evidence binding is invalid")

    def _evidence_binding(self) -> str:
        return _digest_json(
            {
                "qualification_sha256": self.qualification_sha256,
                "source_inventory_sha256": self.full_manifest_sha256,
                "requested_labels_sha256": self.requested_labels_sha256,
                "calendar_sha256": self.calendar_sha256,
                "panel_file_sha256": self.panel_file_sha256,
                "panel_sha256": self.panel_sha256,
                "goal_sha256": self.goal_sha256,
                "cards_sha256": self.cards_sha256,
                "session_dates": [value.isoformat() for value in self.session_dates],
                "dispositions": [
                    {"label": item.label, "pilot_statuses": list(item.pilot_statuses)}
                    for item in self.dispositions
                ],
            }
        )


@dataclass(frozen=True, slots=True)
class DailyPilotSpec:
    cards: tuple[StrategySpec, ...]
    inventory_sha256: str
    goal_sha256: str
    goal_fingerprint: str

    def __post_init__(self) -> None:
        identity = tuple(
            (card.candidate.name, card.candidate.version, card.sha256) for card in self.cards
        )
        if identity != EXPECTED_CARDS:
            raise ValueError("daily pilot requires the exact seven frozen strategy cards")
        _sha(self.inventory_sha256, "inventory_sha256", required=True)
        _sha(self.goal_sha256, "goal_sha256", required=True)
        _sha(self.goal_fingerprint, "goal_fingerprint", required=True)

    @property
    def cards_sha256(self) -> str:
        return _digest_json(
            [[card.candidate.name, card.candidate.version, card.sha256] for card in self.cards]
        )


@dataclass(frozen=True, slots=True)
class DailyPilotPayload:
    panel: Panel
    session_dates: tuple[date, ...]
    source_indices: tuple[int, ...]
    dispositions: tuple[LabelDisposition, ...]
    admission_binding_sha256: str | None

    def __post_init__(self) -> None:
        if not isinstance(self.panel, Panel):
            raise TypeError("daily pilot payload requires a Panel")
        if self.panel.benchmark is not None:
            raise ValueError("daily pilot has Nifty=None and refuses a hidden benchmark")
        if len(self.panel) != SOURCE_SESSION_COUNT or self.source_indices != tuple(
            range(SOURCE_SESSION_COUNT)
        ):
            raise ValueError("daily pilot panel must retain canonical source indices 0..256")
        if self.panel.symbols != tuple(item.label for item in self.dispositions):
            raise ValueError("decoded panel must retain all requested labels in admitted order")
        panel_dates = tuple(
            date.fromisoformat(str(value.astype("datetime64[D]"))) for value in self.panel.ts
        )
        if panel_dates != self.session_dates:
            raise ValueError("decoded price axis differs from admitted session metadata")
        _sha(
            self.admission_binding_sha256,
            "admission_binding_sha256",
            required=False,
        )

    @classmethod
    def from_panel(cls, panel: Panel, admission: DailyPilotAdmission) -> DailyPilotPayload:
        pilot_membership = panel.tradable[:, PILOT_START_INDEX:SOURCE_SESSION_COUNT]
        expected = np.array(
            [
                [status == "ELIGIBLE" for status in item.pilot_statuses]
                for item in admission.dispositions
            ],
            dtype=np.bool_,
        )
        if not np.array_equal(pilot_membership, expected):
            raise ValueError("decoded pilot tradability differs from admitted label dispositions")
        if not admission.invented and panel_sha256(panel) != admission.panel_sha256:
            raise ValueError("decoded panel differs from the qualified panel digest")
        return cls(
            panel,
            admission.session_dates,
            tuple(range(SOURCE_SESSION_COUNT)),
            admission.dispositions,
            admission.evidence_binding_sha256,
        )


def panel_sha256(panel: Panel) -> str:
    digest = hashlib.sha256(
        json.dumps(
            {
                "symbols": panel.symbols,
                "sessions": len(panel),
                "benchmark": panel.benchmark is not None,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    )
    for symbol, bars in zip(panel.symbols, panel.bars, strict=True):
        for name in ("ts", "open", "high", "low", "close", "volume"):
            values = np.ascontiguousarray(getattr(bars, name))
            digest.update(symbol.encode())
            digest.update(name.encode())
            digest.update(values.dtype.str.encode())
            digest.update(str(values.shape).encode())
            digest.update(values.tobytes())
    digest.update(np.ascontiguousarray(panel.tradable).tobytes())
    return digest.hexdigest()


def daily_runner_sha256(project_root: Path | None = None) -> str:
    """Bind the entry point and every local dependency that can change pilot behavior."""
    root = Path(__file__).resolve().parents[2] if project_root is None else project_root.resolve()
    paths = (
        *sorted((root / "icarus").rglob("*.py")),
        root / "tools/run_daily_pilot.py",
        root / "config/daily_pilot_inventory.json",
        root / "pyproject.toml",
        root / "uv.lock",
    )
    digest = hashlib.sha256()
    for path in paths:
        relative = path.relative_to(root).as_posix().encode()
        before = path.read_bytes()
        if path.read_bytes() != before:
            raise ValueError("daily pilot runner dependency changed while being bound")
        digest.update(len(relative).to_bytes(4, "big"))
        digest.update(relative)
        digest.update(len(before).to_bytes(8, "big"))
        digest.update(before)
    return digest.hexdigest()


def _read_json(path: Path) -> tuple[dict[str, Any], str]:
    before = path.read_bytes()
    try:
        value: object = json.loads(before)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("daily pilot inventory is malformed") from exc
    if path.read_bytes() != before or not isinstance(value, dict):
        raise ValueError("daily pilot inventory changed while being read")
    return cast(dict[str, Any], value), hashlib.sha256(before).hexdigest()


def load_daily_pilot_spec(
    project_root: Path, inventory_path: Path, goal: GoalConfig
) -> DailyPilotSpec:
    root = project_root.resolve()
    inventory, digest = _read_json(inventory_path)
    goal_path = root / "goal.yaml"
    goal_bytes = goal_path.read_bytes()
    goal_sha256 = hashlib.sha256(goal_bytes).hexdigest()
    if goal_path.read_bytes() != goal_bytes:
        raise ValueError("goal.yaml changed while being bound")
    try:
        pilot = inventory["pilot"]
        interval = pilot["required_source_interval"]
        evaluation = inventory["intended_actual_evaluation_set"]
        universe = inventory["universe"]
        raw_cards = inventory["cards"]
        if (
            inventory["schema_version"] != 1
            or evaluation["surface"] != "SignalSimulator"
            or evaluation["evaluation_count"] != 7
            or evaluation["portfolio_simulator_separate_evaluations"] != 0
            or tuple(pilot["decision_dates"]) != tuple(value.isoformat() for value in PILOT_DATES)
            or interval
            != {
                "start": SOURCE_START.isoformat(),
                "end": SOURCE_END.isoformat(),
                "session_count": SOURCE_SESSION_COUNT,
                "reason": interval["reason"],
            }
            or universe["requested_labels"] != REQUESTED_LABEL_COUNT
            or universe["class_policy"]["LIQUIDBEES"] != FIXED_INCOME_DISPOSITION
            or not isinstance(raw_cards, list)
            or len(raw_cards) != 7
        ):
            raise ValueError
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("daily pilot inventory violates the fixed reviewed contract") from exc

    paths: list[Path] = []
    for item in raw_cards:
        if not isinstance(item, dict) or not isinstance(item.get("path"), str):
            raise ValueError("daily pilot card record is malformed")
        path = (root / item["path"]).resolve()
        if not path.is_relative_to(root):
            raise ValueError("daily pilot card path escapes the project")
        paths.append(path)
    cards = load_strategy_catalogue(tuple(paths), goal)
    actual = tuple((card.candidate.name, card.candidate.version, card.sha256) for card in cards)
    declared = tuple(
        (item.get("name"), item.get("version"), item.get("sha256")) for item in raw_cards
    )
    if actual != EXPECTED_CARDS or declared != EXPECTED_CARDS:
        raise ValueError("daily pilot inventory/card identity mismatch")
    forbidden = {primitive.name for primitive in default_registry() if primitive.require_benchmark}
    used = forbidden.intersection(
        primitive for card in cards for primitive in card.candidate.primitives_used()
    )
    if used:
        raise ValueError(f"Nifty=None refuses benchmark-dependent primitives: {sorted(used)}")
    return DailyPilotSpec(
        cards,
        digest,
        goal_sha256,
        _digest_json(goal.model_dump(mode="json")),
    )


def load_actual_admission(
    qualification_path: Path,
    source_inventory_path: Path,
    requested_labels_path: Path,
) -> DailyPilotAdmission:
    """Load externally reviewed metadata without opening a price payload."""
    source, source_digest = _read_json(source_inventory_path)
    labels_document, labels_digest = _read_json(requested_labels_path)
    qualification, qualification_digest = _read_json(qualification_path)
    if source_digest != SOURCE_INVENTORY_SHA256 or labels_digest != REQUESTED_LABELS_SHA256:
        raise ValueError("actual pilot source controls differ from the reviewed snapshots")
    try:
        session_dates = tuple(
            date.fromisoformat(value) for value in source["required_interval"]["dates"]
        )
        if (
            source["required_interval"]["session_count"] != SOURCE_SESSION_COUNT
            or source["calendar"]["sha256"] != CALENDAR_SHA256
            or source["universe"]["stock_label_inventory_sha256"] != REQUESTED_LABELS_SHA256
            or labels_document["schema_version"] != 1
            or labels_document["requested_count"] != REQUESTED_LABEL_COUNT
        ):
            raise ValueError
        labels = tuple(item["requested_name"] for item in labels_document["records"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(
            "reviewed source inventory or requested-label control is malformed"
        ) from exc
    if (
        len(session_dates) != SOURCE_SESSION_COUNT
        or len(labels) != REQUESTED_LABEL_COUNT
        or len(set(labels)) != REQUESTED_LABEL_COUNT
    ):
        raise ValueError("reviewed controls do not contain the exact session/label cardinality")

    fields = {
        "schema_version",
        "status",
        "data_qualified",
        "source_use_authorized",
        "calendar_qualified",
        "actions_qualified",
        "point_in_time_qualified",
        "source_inventory_sha256",
        "requested_labels_sha256",
        "calendar_sha256",
        "panel_sha256",
        "panel_file_sha256",
        "goal_sha256",
        "cards_sha256",
        "label_dispositions",
    }
    flags = (
        "data_qualified",
        "source_use_authorized",
        "calendar_qualified",
        "actions_qualified",
        "point_in_time_qualified",
    )
    if (
        set(qualification) != fields
        or qualification.get("schema_version") != 1
        or qualification.get("status") != "QUALIFIED_FOR_DAILY_DESCRIPTIVE_PILOT"
        or any(qualification.get(name) is not True for name in flags)
        or qualification.get("source_inventory_sha256") != source_digest
        or qualification.get("requested_labels_sha256") != labels_digest
        or qualification.get("calendar_sha256") != CALENDAR_SHA256
    ):
        raise ValueError("daily pilot qualification is absent, incomplete, or not evidence-bound")
    raw_dispositions = qualification.get("label_dispositions")
    if not isinstance(raw_dispositions, list):
        raise ValueError("daily pilot qualification lacks label dispositions")
    try:
        dispositions = tuple(
            LabelDisposition(item["label"], tuple(item["pilot_statuses"]))
            for item in raw_dispositions
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("daily pilot qualification has malformed label dispositions") from exc
    if tuple(item.label for item in dispositions) != labels:
        raise ValueError("qualification dispositions differ from the original 693 label identities")
    for name in ("panel_file_sha256", "panel_sha256", "goal_sha256", "cards_sha256"):
        value = qualification.get(name)
        if not isinstance(value, str):
            raise ValueError(f"qualification {name} is missing")
        _sha(value, name, required=True)
    binding = _digest_json(
        {
            "qualification_sha256": qualification_digest,
            "source_inventory_sha256": source_digest,
            "requested_labels_sha256": labels_digest,
            "calendar_sha256": CALENDAR_SHA256,
            "panel_file_sha256": qualification["panel_file_sha256"],
            "panel_sha256": qualification["panel_sha256"],
            "goal_sha256": qualification["goal_sha256"],
            "cards_sha256": qualification["cards_sha256"],
            "session_dates": [value.isoformat() for value in session_dates],
            "dispositions": [
                {"label": item.label, "pilot_statuses": list(item.pilot_statuses)}
                for item in dispositions
            ],
        }
    )
    return DailyPilotAdmission(
        invented=False,
        data_qualified=True,
        source_use_authorized=True,
        calendar_qualified=True,
        actions_qualified=True,
        point_in_time_qualified=True,
        full_manifest_sha256=source_digest,
        qualification_sha256=qualification_digest,
        requested_labels_sha256=labels_digest,
        calendar_sha256=CALENDAR_SHA256,
        panel_file_sha256=cast(str, qualification["panel_file_sha256"]),
        panel_sha256=cast(str, qualification["panel_sha256"]),
        goal_sha256=cast(str, qualification["goal_sha256"]),
        cards_sha256=cast(str, qualification["cards_sha256"]),
        evidence_binding_sha256=binding,
        session_dates=session_dates,
        dispositions=dispositions,
    )


def build_pilot_plans(
    spec: DailyPilotSpec, admission: DailyPilotAdmission
) -> tuple[EvaluationPlan, ...]:
    if not isinstance(spec, DailyPilotSpec) or not isinstance(admission, DailyPilotAdmission):
        raise TypeError("daily pilot planning requires typed spec and admission")
    start_ts = datetime.combine(PILOT_DATES[0], datetime.min.time(), tzinfo=UTC)
    end_ts = datetime.combine(PILOT_DATES[-1], datetime.min.time(), tzinfo=UTC)
    return tuple(
        EvaluationPlan(
            card=card.candidate.name,
            card_version=card.candidate.version,
            card_sha256=card.sha256,
            mode="signal",
            capital=None,
            evaluations=(
                EvaluationReservation(
                    0,
                    TrialKind.DESCRIPTIVE_PILOT,
                    None,
                    PILOT_START_INDEX,
                    SOURCE_SESSION_COUNT,
                    start_ts,
                    end_ts,
                    RESET_IDENTITY,
                ),
            ),
            primitives=tuple(sorted(card.candidate.primitives_used())),
        )
        for card in spec.cards
    )


def _result_payload(card: StrategySpec, run: SignalRunResult) -> dict[str, Any]:
    fragments = tuple(fragment for trade in run.trades for fragment in trade.exit_fragments)
    marked = tuple(fragment for fragment in fragments if fragment.reason is ExitReason.STALE_MARK)

    def charges(value: Any) -> dict[str, str]:
        return {
            name: str(getattr(value, name))
            for name in (
                "brokerage",
                "stt",
                "exchange_txn",
                "sebi_fee",
                "gst",
                "stamp_duty",
                "dp_charge",
                "turnover",
                "total",
            )
        }

    fragment_rows = [
        {
            "symbol": trade.signal_id.symbol,
            "decision_date": trade.signal_id.decision_ts.date().isoformat(),
            "quantity": fragment.quantity,
            "price": str(fragment.price),
            "price_source_date": fragment.price_source_ts.date().isoformat(),
            "price_source_index": fragment.price_source_index,
            "recognition_date": fragment.recognition_ts.date().isoformat(),
            "recognition_index": fragment.recognition_index,
            "reason": fragment.reason.value,
            "executed_sale": fragment.reason is not ExitReason.STALE_MARK,
            "estimated_final_mark": fragment.reason is ExitReason.STALE_MARK,
            "estimated_charges": charges(fragment.charges),
        }
        for trade in run.trades
        for fragment in trade.exit_fragments
    ]
    return {
        "strategy": card.candidate.name,
        "strategy_version": card.candidate.version,
        "strategy_sha256": card.sha256,
        "surface": "SignalSimulator",
        "modeled_execution_frequency": "DAILY",
        "decision_dates": [value.isoformat() for value in PILOT_DATES],
        "emitted_signals": run.emitted_signals,
        "filled_trade_count": len(run.trades),
        "skipped_signal_count": len(run.skips),
        "executed_exit_fragment_count": len(fragments) - len(marked),
        "final_stale_mark_fragment_count": len(marked),
        "final_stale_mark_quantity": sum(item.quantity for item in marked),
        "final_stale_mark_value": str(
            sum((item.price * item.quantity for item in marked), Decimal(0))
        ),
        "aggregate_net_pnl_including_final_marks_after_charges_before_capital_gains_tax": str(
            sum((trade.net_pnl for trade in run.trades), Decimal(0))
        ),
        "unfilled_exits": run.unfilled_exits,
        "exit_fragments": fragment_rows,
        "skips": [
            {
                "symbol": item.signal_id.symbol,
                "decision_date": item.signal_id.decision_ts.date().isoformat(),
                "decision_index": item.signal_id.decision_index,
                "reason": item.reason.value,
            }
            for item in run.skips
        ],
        "skip_reason_counts": dict(
            sorted(Counter(item.reason.value for item in run.skips).items())
        ),
        "missing_signal_reason_counts": dict(
            sorted(Counter(item.reason.value for item in run.missing).items())
        ),
        "benchmark_return": None,
        "pre_tax_alpha": None,
        "promotion_eligible": False,
        "inference_available": False,
    }


class DailyPilotEvaluator:
    def __init__(
        self,
        spec: DailyPilotSpec,
        goal: GoalConfig,
        admission: DailyPilotAdmission,
    ) -> None:
        self._cards = {card.candidate.name: card for card in spec.cards}
        self._goal = goal
        self._registry = default_registry()
        self._admission = admission
        if _digest_json(goal.model_dump(mode="json")) != spec.goal_fingerprint:
            raise ValueError("goal configuration differs from the spec-bound goal")

    def evaluate(self, plan: EvaluationPlan, payload: object) -> tuple[EvaluationOutcome, ...]:
        if not isinstance(payload, DailyPilotPayload):
            raise TypeError("decoded pilot payload must be DailyPilotPayload")
        if (
            payload.session_dates != self._admission.session_dates
            or payload.dispositions != self._admission.dispositions
            or payload.admission_binding_sha256 != self._admission.evidence_binding_sha256
        ):
            raise ValueError("decoded payload differs from the pre-ledger admission")
        expected_membership = np.array(
            [
                [status == "ELIGIBLE" for status in item.pilot_statuses]
                for item in self._admission.dispositions
            ],
            dtype=np.bool_,
        )
        if not np.array_equal(
            payload.panel.tradable[:, PILOT_START_INDEX:SOURCE_SESSION_COUNT],
            expected_membership,
        ):
            raise ValueError("decoded pilot eligibility differs from the pre-ledger admission")
        if (
            not self._admission.invented
            and panel_sha256(payload.panel) != self._admission.panel_sha256
        ):
            raise ValueError("decoded panel differs from the pre-ledger qualified digest")
        card = self._cards.get(plan.card)
        if (
            card is None
            or plan.card_version != card.candidate.version
            or plan.card_sha256 != card.sha256
            or len(plan.evaluations) != 1
            or plan.evaluations[0].kind is not TrialKind.DESCRIPTIVE_PILOT
        ):
            raise ValueError("daily pilot plan differs from the frozen catalogue")
        columns = evaluate_once(
            card.candidate,
            payload.panel,
            self._registry,
            source_indices=payload.source_indices,
        )
        panel = slice_panel(payload.panel, PILOT_START_INDEX, SOURCE_SESSION_COUNT)
        signals, stops, ranks, exits, pulses = columns.slice(
            PILOT_START_INDEX, SOURCE_SESSION_COUNT
        )
        indices = payload.source_indices[PILOT_START_INDEX:SOURCE_SESSION_COUNT]
        missing = {
            symbol: {
                indices[local]: SignalMissingReason.MISSING_INPUT
                for local in np.flatnonzero(np.isnan(values)).tolist()
            }
            for symbol, values in signals.items()
        }
        run = SignalSimulator(
            notional_inr=Decimal(self._goal.signal_test.notional_inr),
            costs=CostModel(self._goal.costs),
            fills=FillModel(self._goal.execution_realism),
            stale_after_sessions=self._goal.backtest.stale_position_sessions,
        ).run(
            card.candidate,
            panel,
            signals,
            stops,
            source_indices=indices,
            exit_signals=exits,
            ranks=ranks,
            rebalance_pulses=pulses,
            missing_reasons=missing,
        )
        return (EvaluationOutcome(_result_payload(card, run), len(run.trades)),)


def _report(
    spec: DailyPilotSpec,
    admission: DailyPilotAdmission,
    results: tuple[tuple[EvaluationOutcome, ...], ...],
    *,
    actual_ledger_used: bool,
) -> dict[str, Any]:
    if len(results) != 7 or any(len(item) != 1 for item in results):
        raise ValueError("daily pilot requires one completed outcome for every frozen card")
    daily_counts = []
    for offset, session in enumerate(PILOT_DATES):
        counts = Counter(item.pilot_statuses[offset] for item in admission.dispositions)
        if sum(counts.values()) != REQUESTED_LABEL_COUNT:
            raise ValueError("daily eligibility accounting lost a requested label")
        daily_counts.append({"date": session.isoformat(), "counts": dict(sorted(counts.items()))})
    return {
        "schema_version": 1,
        "scope": (
            "ACTUAL_DAILY_DESCRIPTIVE_PILOT"
            if actual_ledger_used
            else "INVENTED_MECHANICS_ONLY_NO_PERFORMANCE_INFERENCE"
        ),
        "inventory_sha256": spec.inventory_sha256,
        "actual_market_data": actual_ledger_used,
        "actual_trial_ledger_used": actual_ledger_used,
        "evaluation_surface": "SignalSimulator",
        "evaluation_count": 7,
        "portfolio_evaluation_count": 0,
        "requested_label_count": REQUESTED_LABEL_COUNT,
        "label_dispositions": [
            {"label": item.label, "pilot_statuses": list(item.pilot_statuses)}
            for item in admission.dispositions
        ],
        "daily_disposition_counts": daily_counts,
        "liquidbees_disposition": FIXED_INCOME_DISPOSITION,
        "pilot_dates": [value.isoformat() for value in PILOT_DATES],
        "source_session_count": SOURCE_SESSION_COUNT,
        "warmup_session_count": PILOT_START_INDEX,
        "benchmark": None,
        "pre_tax_alpha": None,
        "promotion_eligible": False,
        "inference_available": False,
        "evaluations": [cast(dict[str, Any], item[0].payload) for item in results],
    }


def publish_json_once(path: Path, value: dict[str, Any]) -> None:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        with temporary.open("xb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        if os.name == "nt":
            os.rename(temporary, path)
        else:
            os.link(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def run_actual_daily_pilot(
    spec: DailyPilotSpec,
    admission: DailyPilotAdmission,
    goal: GoalConfig,
    authorization: RunAuthorization,
    binding: ExecutionBinding,
    ledger: _Ledger,
    decode_prices: Callable[[], object],
    output_path: Path,
) -> dict[str, Any]:
    admission.require_actual()
    if (
        admission.goal_sha256 != spec.goal_sha256
        or admission.cards_sha256 != spec.cards_sha256
        or authorization.bundle_sha256 != admission.panel_file_sha256
        or authorization.qualification_sha256 != admission.qualification_sha256
        or authorization.goal_sha256 != spec.goal_sha256
        or authorization.cards_sha256 != spec.cards_sha256
        or authorization.runner_sha256 != daily_runner_sha256()
    ):
        raise ValueError("actual authorization does not bind the reviewed pilot evidence")
    plans = build_pilot_plans(spec, admission)
    evaluator = DailyPilotEvaluator(spec, goal, admission)
    results = GuardedTimedRunner(ledger).run(
        authorization,
        binding,
        plans,
        decode_prices,
        evaluator.evaluate,
    )
    report = _report(spec, admission, results, actual_ledger_used=True)
    publish_json_once(output_path, report)
    return report


def _invented_session_dates() -> tuple[date, ...]:
    start = int(np.datetime64(SOURCE_START, "D").astype(np.int64))
    end = int(np.datetime64("2022-12-23", "D").astype(np.int64))
    prefix = tuple(
        date.fromisoformat(str(np.datetime64(int(value), "D")))
        for value in np.linspace(start, end, PILOT_START_INDEX, dtype=np.int64)
    )
    return prefix + PILOT_DATES


def build_invented_admission() -> DailyPilotAdmission:
    labels = tuple(sorted(("LIQUIDBEES", *(f"SYN{index:03d}" for index in range(692)))))
    dispositions = tuple(
        LabelDisposition(
            label,
            ((FIXED_INCOME_DISPOSITION,) if label == "LIQUIDBEES" else ("ELIGIBLE",)) * 5,
        )
        for label in labels
    )
    return DailyPilotAdmission(
        invented=True,
        data_qualified=False,
        source_use_authorized=False,
        calendar_qualified=False,
        actions_qualified=False,
        point_in_time_qualified=False,
        full_manifest_sha256=None,
        qualification_sha256=None,
        requested_labels_sha256=None,
        calendar_sha256=None,
        panel_file_sha256=None,
        panel_sha256=None,
        goal_sha256=None,
        cards_sha256=None,
        evidence_binding_sha256=None,
        session_dates=_invented_session_dates(),
        dispositions=dispositions,
    )


def build_invented_panel(admission: DailyPilotAdmission) -> Panel:
    if not admission.invented:
        raise ValueError("invented panel helper cannot stand in for actual data")
    axis = np.array(admission.session_dates, dtype="datetime64[D]")
    step = np.arange(SOURCE_SESSION_COUNT, dtype=np.float64)
    bars: dict[str, Bars] = {}
    membership: dict[str, npt.NDArray[np.bool_]] = {}
    for offset, label in enumerate(admission.labels):
        close = (
            80.0
            + float(offset % 100)
            + (0.02 + float(offset % 17) * 0.002) * step
            + np.sin(step / 11.0 + float(offset % 13))
        )
        bars[label] = Bars(
            ts=axis.copy(),
            open=close - 0.1,
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=np.full(SOURCE_SESSION_COUNT, 1_000_000.0 + offset),
        )
        membership[label] = np.full(SOURCE_SESSION_COUNT, label != "LIQUIDBEES", dtype=np.bool_)
    return Panel.build(bars, membership)


def run_invented_daily_pilot(
    spec: DailyPilotSpec, admission: DailyPilotAdmission, goal: GoalConfig
) -> dict[str, Any]:
    if not admission.invented:
        raise ValueError("invented proof requires an explicitly invented admission")
    plans = build_pilot_plans(spec, admission)
    payload = DailyPilotPayload.from_panel(build_invented_panel(admission), admission)
    evaluator = DailyPilotEvaluator(spec, goal, admission)
    results = tuple(evaluator.evaluate(plan, payload) for plan in plans)
    return _report(spec, admission, results, actual_ledger_used=False)


__all__ = [
    "DailyPilotAdmission",
    "DailyPilotEvaluator",
    "DailyPilotPayload",
    "DailyPilotSpec",
    "LabelDisposition",
    "build_invented_admission",
    "build_invented_panel",
    "build_pilot_plans",
    "daily_runner_sha256",
    "load_actual_admission",
    "load_daily_pilot_spec",
    "panel_sha256",
    "publish_json_once",
    "run_actual_daily_pilot",
    "run_invented_daily_pilot",
]
