"""Compliance gate core (task 0.10, PRD §8, §11.5, §14, invariants #4,#5,#6).

The independent policy enforcer every order passes before Execution. It holds the hard limits
no strategy or learned logic can override. Two failure modes, kept distinct:

* **REJECT** — this order is not allowed (LIMIT-only, market closed, over the OPS throttle,
  not white-box). The system keeps running; the order simply doesn't go.
* **HALT** — something is structurally wrong (egress IP != registered static IP, per-minute or
  per-day order tripwire tripped, calendar data missing). Execution must stop until cleared.

The persistent HALT *flag* (checked by every plane, surviving a wedged orchestrator) is task
0.14; this gate returns ``halt=True`` and the caller persists it. The gate itself is pure given
its injected clock + market-open function, so tests are deterministic.
"""

from __future__ import annotations

from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from icarus.common.calendar import CalendarDataMissing, is_market_open
from icarus.common.config import Compliance
from icarus.common.types import AssetClass, OrderType, SizedOrder


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    halt: bool
    reason: str

    @staticmethod
    def allow() -> PolicyDecision:
        return PolicyDecision(allowed=True, halt=False, reason="ok")

    @staticmethod
    def reject(reason: str) -> PolicyDecision:
        return PolicyDecision(allowed=False, halt=False, reason=reason)

    @staticmethod
    def halt_now(reason: str) -> PolicyDecision:
        return PolicyDecision(allowed=False, halt=True, reason=reason)


@dataclass(frozen=True)
class RateResult:
    admitted: bool
    halt: bool
    reason: str


class RateGovernor:
    """Sliding-window order-rate governor (PRD §11.5).

    ``max_orders_per_sec`` is a *throttle* (reject, keep running). ``per_min``/``per_day`` are
    *tripwires* set below broker limits — exceeding them signals runaway behaviour and HALTs.
    ``try_admit`` records the event only if admitted (rejected orders still count toward broker
    limits in reality, but a throttled order never reaches the broker, so we don't record it).
    """

    def __init__(self, cfg: Compliance) -> None:
        self._per_sec = cfg.max_orders_per_sec
        self._per_min = cfg.max_orders_per_min
        self._per_day = cfg.max_orders_per_day
        self._events: deque[float] = deque()  # unix-second timestamps of admitted orders

    def _count_within(self, now: float, window_s: float) -> int:
        return sum(1 for t in self._events if now - t < window_s)

    def try_admit(self, now: datetime) -> RateResult:
        ts = now.timestamp()
        # Prune anything older than a day so the deque stays bounded.
        while self._events and ts - self._events[0] >= 86_400:
            self._events.popleft()

        if self._count_within(ts, 86_400.0) >= self._per_day:
            return RateResult(False, True, f"per-day order tripwire {self._per_day} hit -> HALT")
        if self._count_within(ts, 60.0) >= self._per_min:
            return RateResult(False, True, f"per-minute order tripwire {self._per_min} hit -> HALT")
        if self._count_within(ts, 1.0) >= self._per_sec:
            return RateResult(False, False, f"order-rate throttle {self._per_sec}/s")
        self._events.append(ts)
        return RateResult(True, False, "ok")


class ComplianceGate:
    """Checks one :class:`SizedOrder` against every hard compliance rule."""

    def __init__(self, cfg: Compliance, registered_static_ip: str) -> None:
        self._cfg = cfg
        self._registered_ip = registered_static_ip
        self._rate = RateGovernor(cfg)

    def check_order(
        self,
        order: SizedOrder,
        *,
        egress_ip: str,
        now: datetime,
        white_box: bool,
        market_open_fn: Callable[[AssetClass, datetime], bool] = is_market_open,
    ) -> PolicyDecision:
        # 1. LIMIT-only — NSE bars MARKET via algo (invariant #5). Hard reject.
        if order.order_type is not OrderType.LIMIT:
            return PolicyDecision.reject(
                f"non-LIMIT order rejected: {order.order_type} (invariant #5)"
            )

        # 2. Algo-ID tag required on every API order (invariant #6, PRD §8).
        if self._cfg.algo_id_tagging_required and not order.algo_id:
            return PolicyDecision.reject("missing algo-ID tag (invariant #6)")

        # 3. White-box only — a non-explainable strategy must never reach the exchange (PRD §8).
        if self._cfg.white_box_only and not white_box:
            return PolicyDecision.reject("strategy is not white-box (PRD §8)")

        # 4. Static-IP assertion — orders originate only from the registered IP (invariant #6).
        #    A mismatch is structural: HALT, don't just skip this order.
        if self._cfg.static_ip_required and egress_ip != self._registered_ip:
            return PolicyDecision.halt_now(
                f"egress IP {egress_ip} != registered {self._registered_ip} -> HALT (invariant #6)"
            )

        # 5. Market hours / calendar. Missing calendar data -> fail-safe HALT (can't confirm open).
        try:
            if not market_open_fn(order.asset_class, now):
                return PolicyDecision.reject(f"market closed for {order.asset_class} (blackout)")
        except CalendarDataMissing as exc:
            return PolicyDecision.halt_now(f"calendar data missing -> HALT: {exc}")

        # 6. Order-rate governor last (only count orders that pass every other gate).
        rate = self._rate.try_admit(now)
        if rate.halt:
            return PolicyDecision.halt_now(rate.reason)
        if not rate.admitted:
            return PolicyDecision.reject(rate.reason)

        return PolicyDecision.allow()
