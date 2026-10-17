"""Point-in-time corporate-action admission rules for the bounded daily pilot."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from itertools import pairwise

ACTION_UNRESOLVED_LOOKBACK = "ACTION_UNRESOLVED_LOOKBACK"
FIXED_INCOME_DISPOSITION = "CLASS_INELIGIBLE_FIXED_INCOME"
ACTION_SOURCE_MANIFEST_SHA256 = "b67a2566a7df9455b4709210be69037040aebce04028ee4f1264566ba9c8e5d6"
POINT_IN_TIME_IDENTITY_SHA256 = "4c85773e03d015ddaf5c06d06d27abbf7e95e0b15f34414b84d2558e873b3ba6"


@dataclass(frozen=True, slots=True)
class UnresolvedAction:
    label: str
    ex_date: date
    kind: str
    subject: str

    def __post_init__(self) -> None:
        if not self.label or not self.kind or not self.subject:
            raise ValueError("unresolved action fields must be nonempty")


EXPECTED_UNRESOLVED_ACTIONS = (
    UnresolvedAction("MOTHERSON", date(2022, 1, 14), "DEMERGER", "Demerger"),
    UnresolvedAction(
        "WOCKPHARMA",
        date(2022, 3, 8),
        "RIGHTS",
        "Rights 3:10@ Premium Rs 220 Per Share",
    ),
    UnresolvedAction("PEL", date(2022, 8, 30), "DEMERGER", "Demerger"),
    UnresolvedAction("AARTIIND", date(2022, 10, 19), "DEMERGER", "Demerger"),
    UnresolvedAction("NMDC", date(2022, 10, 27), "DEMERGER", "Demerger"),
)


def admit_source_screen_status(label: str, raw_status: str) -> str:
    if label == "LIQUIDBEES":
        return FIXED_INCOME_DISPOSITION
    return "ELIGIBLE" if raw_status == "CONDITIONAL_QUALIFIES" else raw_status


def guard_unresolved_action_lookback(
    label: str,
    raw_statuses: tuple[str, ...],
    decision_dates: tuple[date, ...],
    source_sessions: tuple[date, ...],
    unresolved_actions: tuple[UnresolvedAction, ...],
    *,
    required_clean_prior_sessions: int = 252,
) -> tuple[str, ...]:
    if len(raw_statuses) != len(decision_dates):
        raise ValueError("raw statuses and decision dates must have equal length")
    if required_clean_prior_sessions <= 0:
        raise ValueError("required clean prior sessions must be positive")
    if any(right <= left for left, right in pairwise(source_sessions)):
        raise ValueError("source sessions must be strictly increasing")
    if not set(decision_dates).issubset(source_sessions):
        raise ValueError("decision dates must belong to source sessions")

    exact_label_actions = tuple(action for action in unresolved_actions if action.label == label)
    effective: list[str] = []
    for raw_status, decision_date in zip(raw_statuses, decision_dates, strict=True):
        admitted_status = admit_source_screen_status(label, raw_status)
        prior_actions = tuple(
            action for action in exact_label_actions if action.ex_date <= decision_date
        )
        if not prior_actions:
            effective.append(admitted_status)
            continue
        latest = max(prior_actions, key=lambda action: action.ex_date)
        effective_event_session = next(
            session for session in source_sessions if session >= latest.ex_date
        )
        clean_prior = sum(
            effective_event_session < session < decision_date for session in source_sessions
        )
        effective.append(
            admitted_status
            if clean_prior >= required_clean_prior_sessions
            else ACTION_UNRESOLVED_LOOKBACK
        )
    return tuple(effective)
