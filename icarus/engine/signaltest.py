"""Typed outcomes for the signal-only diagnostic.

This module records what happened to one emitted entry signal.  It deliberately contains no
simulator, portfolio book, equity curve, gate metric, or trial persistence; those belong to later
Task-3a steps.  Actual fills and assumed stale marks remain visibly distinct.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from icarus.engine.costmodel import Charges
from icarus.engine.simcore import ExitReason, SignalId

if TYPE_CHECKING:
    from collections.abc import Iterable

_CHARGE_FIELDS = (
    "brokerage",
    "stt",
    "exchange_txn",
    "sebi_fee",
    "gst",
    "stamp_duty",
    "dp_charge",
    "turnover",
)


class SignalSkipReason(enum.StrEnum):
    """Why an emitted ``1.0`` signal did not become an entry fill."""

    NO_NEXT_BAR = "no_next_bar"
    NOT_TRADABLE = "not_tradable"
    ALREADY_OPEN = "already_open"
    PRICE_ABOVE_NOTIONAL = "price_above_notional"
    INVALID_STOP_DISTANCE = "invalid_stop_distance"
    ENTRY_NOT_FILLED = "entry_not_filled"


@dataclass(frozen=True, slots=True)
class SignalSkipped:
    """The explicit non-trade outcome of one emitted entry signal."""

    signal_id: SignalId
    reason: SignalSkipReason

    def __post_init__(self) -> None:
        if not isinstance(self.signal_id, SignalId):
            raise TypeError("SignalSkipped.signal_id must be a SignalId")
        if not isinstance(self.reason, SignalSkipReason):
            raise TypeError("SignalSkipped.reason must be a SignalSkipReason")


@dataclass(frozen=True, slots=True)
class SignalExitFragment:
    """One filled exit, or one explicitly labelled stale mark of residual shares.

    Price-source coordinates say where the price came from.  Recognition coordinates say when the
    outcome became known.  They are identical for a real fill and may differ only for a
    ``STALE_MARK`` assumption.
    """

    quantity: int
    price: Decimal
    price_source_ts: datetime
    price_source_index: int
    recognition_ts: datetime
    recognition_index: int
    reason: ExitReason
    charges: Charges
    benchmark_return: Decimal | None = None

    def __post_init__(self) -> None:
        _require_positive_count("SignalExitFragment.quantity", self.quantity)
        _require_positive_decimal("SignalExitFragment.price", self.price)
        _require_utc("SignalExitFragment.price_source_ts", self.price_source_ts)
        _require_index("SignalExitFragment.price_source_index", self.price_source_index)
        _require_utc("SignalExitFragment.recognition_ts", self.recognition_ts)
        _require_index("SignalExitFragment.recognition_index", self.recognition_index)
        if not isinstance(self.reason, ExitReason):
            raise TypeError("SignalExitFragment.reason must be an ExitReason")
        _assert_coordinates_ordered(
            "exit price source",
            self.price_source_ts,
            self.price_source_index,
            "exit recognition",
            self.recognition_ts,
            self.recognition_index,
        )
        if self.reason is not ExitReason.STALE_MARK and (
            self.price_source_ts != self.recognition_ts
            or self.price_source_index != self.recognition_index
        ):
            raise ValueError(
                "an actual exit fill must be recognised at its price-source coordinates"
            )
        _validate_charges(
            "SignalExitFragment.charges",
            self.charges,
            expected_turnover=self.price * self.quantity,
        )
        if self.benchmark_return is not None:
            _require_finite_decimal("SignalExitFragment.benchmark_return", self.benchmark_return)


@dataclass(frozen=True, slots=True)
class SignalTrade:
    """Exactly one filled entry signal, aggregating all actual and marked exit fragments."""

    signal_id: SignalId
    entry_ts: datetime
    entry_index: int
    entry_price: Decimal
    filled_quantity: int
    intended_notional: Decimal
    risk_per_share: Decimal
    entry_charges: Charges
    exit_fragments: tuple[SignalExitFragment, ...]

    def __post_init__(self) -> None:
        if not isinstance(self.signal_id, SignalId):
            raise TypeError("SignalTrade.signal_id must be a SignalId")
        _require_utc("SignalTrade.entry_ts", self.entry_ts)
        _require_index("SignalTrade.entry_index", self.entry_index)
        if self.entry_index <= self.signal_id.decision_index:
            raise ValueError("entry must occur after the signal's canonical decision bar")
        _assert_coordinates_ordered(
            "signal decision",
            self.signal_id.decision_ts,
            self.signal_id.decision_index,
            "entry",
            self.entry_ts,
            self.entry_index,
        )
        _require_positive_decimal("SignalTrade.entry_price", self.entry_price)
        _require_positive_count("SignalTrade.filled_quantity", self.filled_quantity)
        _require_positive_decimal("SignalTrade.intended_notional", self.intended_notional)
        _require_positive_decimal("SignalTrade.risk_per_share", self.risk_per_share)
        _validate_charges(
            "SignalTrade.entry_charges",
            self.entry_charges,
            expected_turnover=self.entry_price * self.filled_quantity,
        )
        if type(self.exit_fragments) is not tuple or not self.exit_fragments:
            raise ValueError("SignalTrade.exit_fragments must be a nonempty immutable tuple")

        previous_ts = self.entry_ts
        previous_index = self.entry_index
        coordinates = [
            (self.signal_id.decision_index, self.signal_id.decision_ts),
            (self.entry_index, self.entry_ts),
        ]
        exited = 0
        for fragment in self.exit_fragments:
            if not isinstance(fragment, SignalExitFragment):
                raise TypeError("SignalTrade.exit_fragments must contain SignalExitFragment values")
            _assert_coordinates_ordered(
                "entry",
                self.entry_ts,
                self.entry_index,
                "exit price source",
                fragment.price_source_ts,
                fragment.price_source_index,
            )
            _assert_coordinates_ordered(
                "entry",
                self.entry_ts,
                self.entry_index,
                "exit recognition",
                fragment.recognition_ts,
                fragment.recognition_index,
            )
            _assert_coordinates_ordered(
                "previous exit recognition",
                previous_ts,
                previous_index,
                "exit recognition",
                fragment.recognition_ts,
                fragment.recognition_index,
            )
            coordinates.extend(
                (
                    (fragment.price_source_index, fragment.price_source_ts),
                    (fragment.recognition_index, fragment.recognition_ts),
                )
            )
            previous_ts = fragment.recognition_ts
            previous_index = fragment.recognition_index
            exited += fragment.quantity

        _assert_canonical_axis(coordinates)
        if exited != self.filled_quantity:
            raise ValueError(
                "exit-fragment quantities must sum exactly to the filled entry quantity: "
                f"{exited} != {self.filled_quantity}"
            )

    @property
    def deployed_capital(self) -> Decimal:
        """Capital actually filled, never the larger intended notional."""
        return self.entry_price * self.filled_quantity

    @property
    def gross_pnl(self) -> Decimal:
        return sum(
            (
                (fragment.price - self.entry_price) * fragment.quantity
                for fragment in self.exit_fragments
            ),
            Decimal(0),
        )

    @property
    def total_charges(self) -> Charges:
        """Entry once, plus every exit fragment, itemised for contract-note reconciliation."""
        return _sum_charges((self.entry_charges, *(item.charges for item in self.exit_fragments)))

    @property
    def costs(self) -> Decimal:
        return self.total_charges.total

    @property
    def net_pnl(self) -> Decimal:
        """After statutory/broker charges and before account-level capital-gains tax."""
        return self.gross_pnl - self.costs

    @property
    def gross_return(self) -> Decimal:
        return self.gross_pnl / self.deployed_capital

    @property
    def net_return(self) -> Decimal:
        return self.net_pnl / self.deployed_capital

    @property
    def r_multiple(self) -> Decimal:
        return self.net_pnl / (self.risk_per_share * self.filled_quantity)

    @property
    def exit_fills(self) -> int:
        return sum(item.reason is not ExitReason.STALE_MARK for item in self.exit_fragments)

    @property
    def marked_quantity(self) -> int:
        return sum(
            item.quantity for item in self.exit_fragments if item.reason is ExitReason.STALE_MARK
        )

    @property
    def marked_value(self) -> Decimal:
        return sum(
            (
                item.price * item.quantity
                for item in self.exit_fragments
                if item.reason is ExitReason.STALE_MARK
            ),
            Decimal(0),
        )

    @property
    def final_recognition_index(self) -> int:
        return self.exit_fragments[-1].recognition_index

    @property
    def holding_sessions(self) -> int:
        return self.final_recognition_index - self.entry_index + 1

    @property
    def benchmark_return(self) -> Decimal | None:
        if any(item.benchmark_return is None for item in self.exit_fragments):
            return None
        weighted = sum(
            (
                item.benchmark_return * item.quantity
                for item in self.exit_fragments
                if item.benchmark_return is not None
            ),
            Decimal(0),
        )
        return weighted / self.filled_quantity

    @property
    def pre_tax_alpha(self) -> Decimal | None:
        """Market-adjusted return after charges, before capital-gains tax; never a gate alpha."""
        benchmark = self.benchmark_return
        return None if benchmark is None else self.net_return - benchmark


def _require_index(name: str, value: int) -> None:
    if type(value) is not int or value < 0:
        raise ValueError(f"{name} must be a nonnegative whole index")


def _require_positive_count(name: str, value: int) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError(f"{name} must be a positive whole-share count")


def _require_utc(name: str, value: datetime) -> None:
    if not isinstance(value, datetime):
        raise TypeError(f"{name} must be a datetime")
    if value.tzinfo is not UTC:
        raise ValueError(f"{name} must use datetime.UTC")


def _require_finite_decimal(name: str, value: Decimal) -> None:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise ValueError(f"{name} must be a finite Decimal")


def _require_positive_decimal(name: str, value: Decimal) -> None:
    _require_finite_decimal(name, value)
    if value <= 0:
        raise ValueError(f"{name} must be positive")


def _validate_charges(name: str, charges: Charges, *, expected_turnover: Decimal) -> None:
    if not isinstance(charges, Charges):
        raise TypeError(f"{name} must be Charges")
    for field_name in _CHARGE_FIELDS:
        value = getattr(charges, field_name)
        _require_finite_decimal(f"{name}.{field_name}", value)
        if value < 0:
            raise ValueError(f"{name}.{field_name} must not be negative")
    if charges.turnover != expected_turnover:
        raise ValueError(
            f"{name}.turnover must reconcile to quantity x price: "
            f"{charges.turnover} != {expected_turnover}"
        )


def _assert_coordinates_ordered(
    earlier_name: str,
    earlier_ts: datetime,
    earlier_index: int,
    later_name: str,
    later_ts: datetime,
    later_index: int,
) -> None:
    if later_index < earlier_index:
        raise ValueError(f"{later_name} index precedes {earlier_name} index")
    if later_index == earlier_index and later_ts != earlier_ts:
        raise ValueError(
            f"equal canonical indices require equal timestamps for {earlier_name} and {later_name}"
        )
    if later_index > earlier_index and later_ts <= earlier_ts:
        raise ValueError(f"an increasing index requires an increasing timestamp for {later_name}")


def _assert_canonical_axis(coordinates: Iterable[tuple[int, datetime]]) -> None:
    """All records in one trade must refer to one ordered full-source bar axis."""
    by_index: dict[int, datetime] = {}
    for index, ts in coordinates:
        known = by_index.get(index)
        if known is not None and known != ts:
            raise ValueError("one canonical source index cannot have two timestamps")
        by_index[index] = ts

    prior_ts: datetime | None = None
    for index in sorted(by_index):
        ts = by_index[index]
        if prior_ts is not None and ts <= prior_ts:
            raise ValueError("canonical source timestamps must increase with their indices")
        prior_ts = ts


def _sum_charges(charges: Iterable[Charges]) -> Charges:
    rows = tuple(charges)
    return Charges(
        brokerage=sum((row.brokerage for row in rows), Decimal(0)),
        stt=sum((row.stt for row in rows), Decimal(0)),
        exchange_txn=sum((row.exchange_txn for row in rows), Decimal(0)),
        sebi_fee=sum((row.sebi_fee for row in rows), Decimal(0)),
        gst=sum((row.gst for row in rows), Decimal(0)),
        stamp_duty=sum((row.stamp_duty for row in rows), Decimal(0)),
        dp_charge=sum((row.dp_charge for row in rows), Decimal(0)),
        turnover=sum((row.turnover for row in rows), Decimal(0)),
    )


__all__ = ["SignalExitFragment", "SignalSkipReason", "SignalSkipped", "SignalTrade"]
