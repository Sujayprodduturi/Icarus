"""Corporate-action admission guard for the bounded daily pilot."""

from __future__ import annotations

from datetime import date, timedelta

from icarus.engine.daily_pilot_admission import (
    ACTION_UNRESOLVED_LOOKBACK,
    FIXED_INCOME_DISPOSITION,
    UnresolvedAction,
    guard_unresolved_action_lookback,
)


def _sessions(count: int) -> tuple[date, ...]:
    start = date(2022, 1, 1)
    return tuple(start + timedelta(days=index) for index in range(count))


def test_action_guard_clears_only_after_252_strictly_post_event_prior_sessions() -> None:
    sessions = _sessions(254)
    event = UnresolvedAction("TARGET", sessions[0], "DEMERGER", "Demerger")
    decisions = (sessions[252], sessions[253])

    effective = guard_unresolved_action_lookback(
        "TARGET",
        ("ELIGIBLE", "BELOW_CLOSE"),
        decisions,
        sessions,
        (event,),
    )

    assert effective == (ACTION_UNRESOLVED_LOOKBACK, "BELOW_CLOSE")


def test_action_guard_maps_non_session_event_to_the_same_strict_prior_rule() -> None:
    start = date(2022, 1, 2)
    sessions = tuple(start + timedelta(days=index * 2) for index in range(255))
    between_sessions = sessions[0] + timedelta(days=1)
    event = UnresolvedAction("TARGET", between_sessions, "RIGHTS", "Rights 1:2")

    effective = guard_unresolved_action_lookback(
        "TARGET",
        ("ELIGIBLE", "ELIGIBLE"),
        (sessions[253], sessions[254]),
        sessions,
        (event,),
    )

    assert effective == (ACTION_UNRESOLVED_LOOKBACK, "ELIGIBLE")


def test_action_guard_rejects_decision_outside_source_sessions() -> None:
    sessions = _sessions(20)

    try:
        guard_unresolved_action_lookback(
            "TARGET",
            ("ELIGIBLE",),
            (date(2024, 1, 1),),
            sessions,
            (),
        )
    except ValueError as exc:
        assert str(exc) == "decision dates must belong to source sessions"
    else:
        raise AssertionError("out-of-axis decision was accepted")


def test_action_guard_uses_latest_exact_label_event_without_alias_inference() -> None:
    sessions = _sessions(400)
    events = (
        UnresolvedAction("TARGET", sessions[0], "DEMERGER", "Demerger"),
        UnresolvedAction("TARGET", sessions[300], "RIGHTS", "Rights 1:2"),
        UnresolvedAction("TARGET-OLD", sessions[399], "DEMERGER", "Demerger"),
    )

    target = guard_unresolved_action_lookback(
        "TARGET", ("ELIGIBLE",), (sessions[399],), sessions, events
    )
    similarly_named = guard_unresolved_action_lookback(
        "TARGET-OLDISH", ("ELIGIBLE",), (sessions[399],), sessions, events
    )

    assert target == (ACTION_UNRESOLVED_LOOKBACK,)
    assert similarly_named == ("ELIGIBLE",)


def test_action_guard_preserves_raw_status_input() -> None:
    sessions = _sessions(20)
    raw = ("MISSING_WINDOW", "BELOW_TURNOVER")
    event = UnresolvedAction("TARGET", sessions[1], "DEMERGER", "Demerger")

    effective = guard_unresolved_action_lookback(
        "TARGET", raw, (sessions[10], sessions[11]), sessions, (event,)
    )

    assert raw == ("MISSING_WINDOW", "BELOW_TURNOVER")
    assert effective == (ACTION_UNRESOLVED_LOOKBACK, ACTION_UNRESOLVED_LOOKBACK)


def test_source_conditional_status_becomes_eligible_but_remains_raw_evidence() -> None:
    sessions = _sessions(2)
    raw = ("CONDITIONAL_QUALIFIES",)

    effective = guard_unresolved_action_lookback("TARGET", raw, (sessions[1],), sessions, ())

    assert raw == ("CONDITIONAL_QUALIFIES",)
    assert effective == ("ELIGIBLE",)


def test_fixed_income_class_overrides_source_conditional_status() -> None:
    sessions = _sessions(2)

    effective = guard_unresolved_action_lookback(
        "LIQUIDBEES", ("CONDITIONAL_QUALIFIES",), (sessions[1],), sessions, ()
    )

    assert effective == (FIXED_INCOME_DISPOSITION,)
