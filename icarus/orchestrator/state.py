"""Plane state machine (task 0.5, PRD §9.5, invariant #16).

States: PRE_OPEN → AUTH → RECOVERY → TRADING → POST_CLOSE → RESEARCH → SLEEP.

Two invariants enforced structurally here:
* **RECOVERY before TRADING** on every startup (invariant #16): TRADING is reachable ONLY from
  RECOVERY. You cannot jump AUTH → TRADING.
* Any state may drop to SLEEP (fail-safe / session end / halt). Illegal transitions raise.

Equity and crypto run on **independent** machines (PRD §9.5): equity sleeps outside NSE hours;
crypto never sleeps. Same class, driven differently by the orchestrator.
"""

from __future__ import annotations

import enum


class PlaneState(enum.StrEnum):
    PRE_OPEN = "pre_open"
    AUTH = "auth"
    RECOVERY = "recovery"
    TRADING = "trading"
    POST_CLOSE = "post_close"
    RESEARCH = "research"
    SLEEP = "sleep"


# Allowed forward transitions. SLEEP is reachable from anywhere (fail-safe / halt) and is added
# to every set below.
_ALLOWED: dict[PlaneState, set[PlaneState]] = {
    PlaneState.PRE_OPEN: {PlaneState.AUTH},
    PlaneState.AUTH: {PlaneState.RECOVERY, PlaneState.PRE_OPEN},  # auth fail -> back to PRE_OPEN
    PlaneState.RECOVERY: {PlaneState.TRADING},  # only RECOVERY -> TRADING (invariant #16)
    PlaneState.TRADING: {PlaneState.POST_CLOSE},
    PlaneState.POST_CLOSE: {PlaneState.RESEARCH},
    PlaneState.RESEARCH: {PlaneState.SLEEP, PlaneState.PRE_OPEN},  # crypto loops back, no sleep
    PlaneState.SLEEP: {PlaneState.PRE_OPEN},
}


class IllegalTransition(RuntimeError):
    """Raised when a state transition isn't allowed (e.g. AUTH -> TRADING skipping RECOVERY)."""


class PlaneStateMachine:
    """Tracks one plane's state and enforces legal transitions."""

    def __init__(self, initial: PlaneState = PlaneState.PRE_OPEN) -> None:
        self._state = initial

    @property
    def state(self) -> PlaneState:
        return self._state

    def can_transition(self, to: PlaneState) -> bool:
        if to is PlaneState.SLEEP:
            return True  # fail-safe drop allowed from anywhere
        return to in _ALLOWED.get(self._state, set())

    def transition(self, to: PlaneState) -> None:
        if not self.can_transition(to):
            raise IllegalTransition(f"{self._state} -> {to} is not allowed (PRD §9.5)")
        self._state = to

    @property
    def can_trade(self) -> bool:
        return self._state is PlaneState.TRADING
