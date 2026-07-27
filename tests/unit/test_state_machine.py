"""Plane state-machine tests (task 0.5, invariant #16: RECOVERY before TRADING)."""

from __future__ import annotations

import pytest

from icarus.orchestrator.state import IllegalTransition, PlaneState, PlaneStateMachine


def test_happy_path_sequence() -> None:
    sm = PlaneStateMachine()
    for state in [
        PlaneState.AUTH,
        PlaneState.RECOVERY,
        PlaneState.TRADING,
        PlaneState.POST_CLOSE,
        PlaneState.RESEARCH,
        PlaneState.SLEEP,
        PlaneState.PRE_OPEN,
    ]:
        sm.transition(state)
    assert sm.state is PlaneState.PRE_OPEN


def test_cannot_skip_recovery_into_trading() -> None:
    sm = PlaneStateMachine()
    sm.transition(PlaneState.AUTH)
    with pytest.raises(IllegalTransition):
        sm.transition(PlaneState.TRADING)  # must go through RECOVERY (invariant #16)


def test_trading_only_from_recovery() -> None:
    sm = PlaneStateMachine(PlaneState.RECOVERY)
    sm.transition(PlaneState.TRADING)
    assert sm.can_trade


def test_can_drop_to_sleep_from_anywhere() -> None:
    for start in PlaneState:
        assert PlaneStateMachine(start).can_transition(PlaneState.SLEEP)


def test_illegal_transition_raises() -> None:
    sm = PlaneStateMachine(PlaneState.PRE_OPEN)
    with pytest.raises(IllegalTransition):
        sm.transition(PlaneState.RESEARCH)


def test_can_trade_only_in_trading() -> None:
    assert not PlaneStateMachine(PlaneState.RECOVERY).can_trade
    assert PlaneStateMachine(PlaneState.TRADING).can_trade
