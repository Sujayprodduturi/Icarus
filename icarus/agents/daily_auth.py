"""Daily-auth agent (task 0.11, PRD §11.6, §38, invariant #10).

Before each session a broker session must be (re)established — Kite tokens expire ~6 AM daily
(regulatory). The load-bearing safety rule: a FAILED auth never leads to TRADING. On any failure
(login error, or egress IP != the registered static IP) the plane stays in a safe non-trading
state and the operator is paged.

Plane isolation (§38): an equity-auth failure disables ONLY the equity plane; the crypto plane
(HMAC-keyed, no daily OAuth) is unaffected. Each plane runs its own auth.

Default login mode is ``one_tap`` (a pre-open login link the operator taps); ``totp_auto``
(scripted 2FA) is an explicit, operator-owned opt-in — never the silent default.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from icarus.common.logging import get_logger
from icarus.common.types import Plane, Session

log = get_logger("daily_auth")


@dataclass(frozen=True)
class AuthOutcome:
    """Result of a session's auth attempt. ``ok`` gates whether the plane may proceed to TRADING."""

    plane: Plane
    ok: bool
    reason: str


class DailyAuthAgent:
    """Runs one plane's daily authentication and enforces fail-safe-to-non-trading."""

    def __init__(
        self,
        plane: Plane,
        *,
        authenticate: Callable[[], Awaitable[Session]],
        egress_ip: Callable[[], Awaitable[str]],
        registered_ip: str,
        alert: Callable[[str], Awaitable[None]],
    ) -> None:
        self._plane = plane
        self._authenticate = authenticate
        self._egress_ip = egress_ip
        self._registered_ip = registered_ip
        self._alert = alert

    async def run(self) -> AuthOutcome:
        """Attempt auth. Returns ``ok=True`` only on a clean login from the registered IP."""
        # 1. Static-IP assertion first — orders may originate only from the registered IP (#6).
        ip = await self._egress_ip()
        if ip != self._registered_ip:
            return await self._fail(f"egress IP {ip} != registered {self._registered_ip}")

        # 2. Broker login. Any error, or a non-authenticated session, is a failure -> stay safe.
        try:
            session = await self._authenticate()
        except Exception as exc:  # login/network/2FA failure -> never proceed to TRADING
            return await self._fail(f"auth error: {exc}")

        if not session.authenticated:
            return await self._fail("broker returned unauthenticated session")

        log.info("daily auth ok", plane=self._plane)
        return AuthOutcome(plane=self._plane, ok=True, reason="authenticated")

    async def _fail(self, reason: str) -> AuthOutcome:
        log.error("daily auth FAILED — plane stays non-trading", plane=self._plane, reason=reason)
        await self._alert(f"[{self._plane}] daily auth failed: {reason}")
        return AuthOutcome(plane=self._plane, ok=False, reason=reason)
