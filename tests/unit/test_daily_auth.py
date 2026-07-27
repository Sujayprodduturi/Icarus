"""Daily-auth tests (task 0.11). Core AC: a failed auth never leads to TRADING."""

from __future__ import annotations

import pytest

from icarus.agents.daily_auth import DailyAuthAgent
from icarus.common.types import Plane, Session
from icarus.orchestrator.state import PlaneState, PlaneStateMachine

REGISTERED_IP = "203.0.113.10"


class _Recorder:
    """Captures alert messages so tests can assert the operator was paged."""

    def __init__(self) -> None:
        self.alerts: list[str] = []

    async def alert(self, msg: str) -> None:
        self.alerts.append(msg)


def _agent(
    *,
    plane: Plane = Plane.EQUITY,
    authenticated: bool = True,
    raise_login: bool = False,
    ip: str = REGISTERED_IP,
    rec: _Recorder | None = None,
) -> DailyAuthAgent:
    rec = rec or _Recorder()

    async def authenticate() -> Session:
        if raise_login:
            raise RuntimeError("2FA rejected")
        return Session(broker="zerodha", authenticated=authenticated)

    async def egress_ip() -> str:
        return ip

    return DailyAuthAgent(
        plane,
        authenticate=authenticate,
        egress_ip=egress_ip,
        registered_ip=REGISTERED_IP,
        alert=rec.alert,
    )


@pytest.mark.asyncio
async def test_successful_auth() -> None:
    outcome = await _agent().run()
    assert outcome.ok


@pytest.mark.asyncio
async def test_login_failure_stays_non_trading_and_alerts() -> None:
    rec = _Recorder()
    outcome = await _agent(raise_login=True, rec=rec).run()
    assert not outcome.ok
    assert rec.alerts  # operator was paged


@pytest.mark.asyncio
async def test_ip_mismatch_fails() -> None:
    outcome = await _agent(ip="198.51.100.7").run()
    assert not outcome.ok
    assert "egress IP" in outcome.reason


@pytest.mark.asyncio
async def test_unauthenticated_session_fails() -> None:
    outcome = await _agent(authenticated=False).run()
    assert not outcome.ok


@pytest.mark.asyncio
async def test_failed_auth_never_enters_trading() -> None:
    # The core AC. Model the orchestrator's rule: advance toward TRADING ONLY on ok auth.
    sm = PlaneStateMachine(PlaneState.PRE_OPEN)
    sm.transition(PlaneState.AUTH)
    outcome = await _agent(raise_login=True).run()
    if outcome.ok:
        sm.transition(PlaneState.RECOVERY)
        sm.transition(PlaneState.TRADING)
    assert not sm.can_trade  # stayed out of TRADING


@pytest.mark.asyncio
async def test_equity_auth_failure_isolates_crypto() -> None:
    equity = await _agent(plane=Plane.EQUITY, raise_login=True).run()
    crypto = await _agent(plane=Plane.CRYPTO, authenticated=True).run()
    assert not equity.ok  # equity down
    assert crypto.ok  # crypto unaffected (§38 plane isolation)
