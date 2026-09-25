"""Typed outcomes for the signal-only diagnostic.

This module simulates and records what happened to each emitted entry signal. It deliberately
contains no portfolio book, equity curve, gate metric, trial persistence, or broker path.
Actual fills and assumed stale marks remain visibly distinct.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from itertools import pairwise
from typing import TYPE_CHECKING

import numpy as np

from icarus.common.types import OrderSide
from icarus.engine.costmodel import Charges, CostModel, Segment
from icarus.engine.fills import FillModel, Intent, OrderKind
from icarus.engine.simcore import (
    ExitPlan,
    ExitReason,
    SignalId,
    _dec,
    _exit_intent,
    _last_traded_close,
    _sim_bar,
    _trail_stop,
    _ts_at,
)

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping, Sequence

    import numpy.typing as npt

    from icarus.strategy.dsl import Panel, StrategyCandidate

    Column = npt.NDArray[np.float64]

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


class SignalMissingReason(enum.StrEnum):
    """Why an entry-condition cell is unavailable rather than false."""

    WARMUP = "warmup"
    MISSING_INPUT = "missing_input"


@dataclass(frozen=True, slots=True)
class SignalMissing:
    """One explicitly labelled missing entry-condition observation."""

    symbol: str
    decision_ts: datetime
    decision_index: int
    reason: SignalMissingReason

    def __post_init__(self) -> None:
        if not isinstance(self.symbol, str) or not self.symbol:
            raise ValueError("SignalMissing.symbol must be a nonempty string")
        _require_utc("SignalMissing.decision_ts", self.decision_ts)
        _require_index("SignalMissing.decision_index", self.decision_index)
        if not isinstance(self.reason, SignalMissingReason):
            raise TypeError("SignalMissing.reason must be a SignalMissingReason")


class SignalSkipReason(enum.StrEnum):
    """Why an emitted ``1.0`` signal did not become an entry fill."""

    NO_NEXT_BAR = "no_next_bar"
    NOT_TRADABLE = "not_tradable"
    ALREADY_OPEN = "already_open"
    NO_EXECUTION_BAR = "no_execution_bar"
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


@dataclass(slots=True)
class _SignalPosition:
    signal_id: SignalId
    quantity: int
    entry_quantity: int
    entry_price: Decimal
    entry_ts: datetime
    entry_index: int
    decided_at: datetime
    entry_charges: Charges
    stop_price: Decimal
    risk_per_share: Decimal
    take_profit: Decimal | None
    time_stop_bars: int | None
    trailing: bool
    bars_held: int = 0
    peak_close: Decimal = Decimal(0)
    dark_sessions: int = 0
    fragments: list[SignalExitFragment] = field(default_factory=list)

    def trade(self, intended_notional: Decimal) -> SignalTrade:
        return SignalTrade(
            signal_id=self.signal_id,
            entry_ts=self.entry_ts,
            entry_index=self.entry_index,
            entry_price=self.entry_price,
            filled_quantity=self.entry_quantity,
            intended_notional=intended_notional,
            risk_per_share=self.risk_per_share,
            entry_charges=self.entry_charges,
            exit_fragments=tuple(self.fragments),
        )


@dataclass(frozen=True, slots=True)
class SignalRunResult:
    """Immutable accounting of every emitted signal and labelled missing cell."""

    trades: tuple[SignalTrade, ...]
    skips: tuple[SignalSkipped, ...]
    missing: tuple[SignalMissing, ...]
    emitted_signals: int
    unfilled_exits: int

    def __post_init__(self) -> None:
        for name, values, expected in (
            ("trades", self.trades, SignalTrade),
            ("skips", self.skips, SignalSkipped),
            ("missing", self.missing, SignalMissing),
        ):
            if type(values) is not tuple or not all(
                isinstance(value, expected) for value in values
            ):
                raise TypeError(
                    f"SignalRunResult.{name} must be an immutable tuple of {expected.__name__}"
                )
        if type(self.emitted_signals) is not int or self.emitted_signals < 0:
            raise ValueError("SignalRunResult.emitted_signals must be a nonnegative whole count")
        if type(self.unfilled_exits) is not int or self.unfilled_exits < 0:
            raise ValueError("SignalRunResult.unfilled_exits must be a nonnegative whole count")
        if self.emitted_signals != len(self.trades) + len(self.skips):
            raise ValueError("emitted signal count must equal completed trades plus explicit skips")
        trade_ids = [trade.signal_id for trade in self.trades]
        skip_ids = [skip.signal_id for skip in self.skips]
        if len(set(trade_ids)) != len(trade_ids):
            raise ValueError("trade signal IDs must be unique")
        if len(set(skip_ids)) != len(skip_ids):
            raise ValueError("skip signal IDs must be unique")
        if set(trade_ids) & set(skip_ids):
            raise ValueError("trade and skip signal IDs must be disjoint")


class SignalSimulator:
    """Synthetic signal diagnostic with no portfolio constraints or external side effects."""

    def __init__(
        self,
        *,
        notional_inr: Decimal,
        costs: CostModel,
        fills: FillModel,
        stale_after_sessions: int,
        segment: Segment = Segment.EQUITY_DELIVERY,
    ) -> None:
        _require_positive_decimal("SignalSimulator.notional_inr", notional_inr)
        if type(stale_after_sessions) is not int or stale_after_sessions <= 0:
            raise ValueError("stale_after_sessions must be a positive whole count")
        self._notional = notional_inr
        self._costs = costs
        self._fills = fills
        self._stale_after = stale_after_sessions
        self._segment = segment

    def run(
        self,
        strategy: StrategyCandidate,
        panel: Panel,
        signals: Mapping[str, Column],
        stops: Mapping[str, Column],
        *,
        source_indices: Sequence[int],
        missing_reasons: Mapping[str, Mapping[int, SignalMissingReason]] | None = None,
    ) -> SignalRunResult:
        """Preflight the complete input before simulating any event."""
        source, missing, emitted = self._preflight(
            panel, signals, stops, source_indices, missing_reasons or {}
        )
        plan = ExitPlan.of(strategy.exits)
        book: dict[str, _SignalPosition] = {}
        trades: list[SignalTrade] = []
        skips: list[SignalSkipped] = []
        unfilled_exits = 0
        last = len(source) - 1

        for local in range(last + 1):
            ts = _ts_at(panel, local)
            unfilled_exits += self._process_exits(
                book, trades, panel, stops, source, local, ts, final=local == last
            )
            for symbol in panel.symbols:
                if float(signals[symbol][local]) != 1.0:
                    continue
                skipped = self._process_entry(
                    strategy,
                    plan,
                    book,
                    panel,
                    stops,
                    source,
                    symbol,
                    local,
                    ts,
                )
                if skipped is not None:
                    skips.append(skipped)

        return SignalRunResult(tuple(trades), tuple(skips), missing, emitted, unfilled_exits)

    def _process_entry(
        self,
        strategy: StrategyCandidate,
        plan: ExitPlan,
        book: dict[str, _SignalPosition],
        panel: Panel,
        stops: Mapping[str, Column],
        source: tuple[int, ...],
        symbol: str,
        local: int,
        ts: datetime,
    ) -> SignalSkipped | None:
        signal_id = SignalId(strategy.name, strategy.version, symbol, ts, source[local])
        index = panel.index_of(symbol)
        last = len(source) - 1
        if local == last:
            return SignalSkipped(signal_id, SignalSkipReason.NO_NEXT_BAR)
        if not bool(panel.tradable[index, local]):
            return SignalSkipped(signal_id, SignalSkipReason.NOT_TRADABLE)
        if symbol in book:
            return SignalSkipped(signal_id, SignalSkipReason.ALREADY_OPEN)

        next_local = local + 1
        next_ts = _ts_at(panel, next_local)
        bar = _sim_bar(panel, index, next_local, next_ts)
        if bar is None:
            return SignalSkipped(signal_id, SignalSkipReason.NO_EXECUTION_BAR)
        raw_stop = float(stops[symbol][local])
        if not np.isfinite(raw_stop) or raw_stop <= 0:
            return SignalSkipped(signal_id, SignalSkipReason.INVALID_STOP_DISTANCE)
        stop_distance = _dec(raw_stop)
        price = self._fills.marketable_price(bar.open, side=OrderSide.BUY)
        quantity = int(self._notional / price)
        if quantity <= 0:
            return SignalSkipped(signal_id, SignalSkipReason.PRICE_ABOVE_NOTIONAL)

        fill = self._fills.execute(
            Intent(OrderSide.BUY, OrderKind.MARKETABLE_LIMIT, quantity, ts), bar
        )
        if not fill.filled or fill.price is None or fill.ts is None:
            return SignalSkipped(signal_id, SignalSkipReason.ENTRY_NOT_FILLED)
        if fill.price * fill.filled_quantity > self._notional:
            raise ValueError("filled entry deployment exceeded intended signal notional")
        charges = self._costs.charges(
            self._segment, OrderSide.BUY, fill.price, Decimal(fill.filled_quantity)
        )
        book[symbol] = _SignalPosition(
            signal_id=signal_id,
            quantity=fill.filled_quantity,
            entry_quantity=fill.filled_quantity,
            entry_price=fill.price,
            entry_ts=fill.ts,
            entry_index=source[next_local],
            decided_at=ts,
            entry_charges=charges,
            stop_price=fill.price - stop_distance,
            risk_per_share=stop_distance,
            take_profit=plan.target_for(fill.price, stop_distance),
            time_stop_bars=plan.time_stop_bars,
            trailing=plan.trailing,
            peak_close=fill.price,
        )
        return None

    def _process_exits(
        self,
        book: dict[str, _SignalPosition],
        trades: list[SignalTrade],
        panel: Panel,
        stops: Mapping[str, Column],
        source: tuple[int, ...],
        local: int,
        ts: datetime,
        *,
        final: bool,
    ) -> int:
        unfilled = 0
        for symbol in list(book):
            position = book[symbol]
            index = panel.index_of(symbol)
            bar = _sim_bar(panel, index, local, ts)
            if bar is None:
                position.dark_sessions += 1
                if position.dark_sessions >= self._stale_after:
                    self._mark_position(book, trades, panel, source, symbol, local, ts)
                continue
            position.dark_sessions = 0
            position.bars_held += 1
            position.peak_close = max(position.peak_close, bar.close)
            _trail_stop(position, float(stops[symbol][local]))
            intent, reason = _exit_intent(position, bar, ts, final=final)
            if intent is None or reason is None:
                continue
            fill = self._fills.execute(intent, bar)
            if not fill.filled or fill.price is None or fill.ts is None:
                unfilled += 1
                continue
            charges = self._costs.charges(
                self._segment, OrderSide.SELL, fill.price, Decimal(fill.filled_quantity)
            )
            position.fragments.append(
                SignalExitFragment(
                    quantity=fill.filled_quantity,
                    price=fill.price,
                    price_source_ts=fill.ts,
                    price_source_index=source[local],
                    recognition_ts=fill.ts,
                    recognition_index=source[local],
                    reason=reason,
                    charges=charges,
                    benchmark_return=None,
                )
            )
            position.quantity -= fill.filled_quantity
            if position.quantity == 0:
                trades.append(position.trade(self._notional))
                del book[symbol]

        if final:
            for symbol in list(book):
                self._mark_position(book, trades, panel, source, symbol, local, ts)
        return unfilled

    def _mark_position(
        self,
        book: dict[str, _SignalPosition],
        trades: list[SignalTrade],
        panel: Panel,
        source: tuple[int, ...],
        symbol: str,
        local: int,
        recognition_ts: datetime,
    ) -> None:
        position = book.pop(symbol)
        price, price_local = _last_traded_close(panel, panel.index_of(symbol), local)
        charges = self._costs.charges(
            self._segment, OrderSide.SELL, price, Decimal(position.quantity)
        )
        position.fragments.append(
            SignalExitFragment(
                quantity=position.quantity,
                price=price,
                price_source_ts=_ts_at(panel, price_local),
                price_source_index=source[price_local],
                recognition_ts=recognition_ts,
                recognition_index=source[local],
                reason=ExitReason.STALE_MARK,
                charges=charges,
                benchmark_return=None,
            )
        )
        position.quantity = 0
        trades.append(position.trade(self._notional))

    @staticmethod
    def _preflight(
        panel: Panel,
        signals: Mapping[str, Column],
        stops: Mapping[str, Column],
        source_indices: Sequence[int],
        missing_reasons: Mapping[str, Mapping[int, SignalMissingReason]],
    ) -> tuple[tuple[int, ...], tuple[SignalMissing, ...], int]:
        sessions = int(np.asarray(panel.ts).size)
        symbols = tuple(panel.symbols)
        if not symbols or len(set(symbols)) != len(symbols):
            raise ValueError("panel symbols must be nonempty and unique")
        if len(panel.bars) != len(symbols):
            raise ValueError("panel bars must have exactly one series per symbol")
        if panel.tradable.shape != (len(symbols), sessions):
            raise ValueError("panel tradable shape must be symbols x sessions")
        if set(signals) != set(symbols):
            raise ValueError("signals symbols must exactly match panel symbols")
        if set(stops) != set(symbols):
            raise ValueError("stops symbols must exactly match panel symbols")

        axis = np.asarray(panel.ts)
        if axis.shape != (sessions,):
            raise ValueError("panel date axis has the wrong shape")
        try:
            axis_ns = axis.astype("datetime64[ns]")
        except (TypeError, ValueError, OverflowError) as exc:
            raise ValueError("panel date axis must be UTC-convertible") from exc
        if np.any(np.isnat(axis_ns)):
            raise ValueError("panel date axis must not contain NaT")
        if sessions > 1 and (
            np.any(np.diff(axis_ns) <= np.timedelta64(0, "ns"))
            or np.any(np.diff(axis_ns.astype("datetime64[D]")) <= np.timedelta64(0, "D"))
        ):
            raise ValueError("panel date axis must be strictly increasing with unique sessions")

        for symbol, bars in zip(symbols, panel.bars, strict=True):
            for name in ("ts", "open", "high", "low", "close", "volume"):
                if np.asarray(getattr(bars, name)).shape != (sessions,):
                    raise ValueError(f"panel bar shape is invalid for {symbol}.{name}")
            if not np.array_equal(bars.ts.astype("datetime64[ns]"), axis_ns):
                raise ValueError(f"panel date axis is not aligned for {symbol}")
        if panel.benchmark is not None:
            for name in ("ts", "open", "high", "low", "close", "volume"):
                if np.asarray(getattr(panel.benchmark, name)).shape != (sessions,):
                    raise ValueError(f"panel bar shape is invalid for benchmark.{name}")
            if not np.array_equal(panel.benchmark.ts.astype("datetime64[ns]"), axis_ns):
                raise ValueError("panel benchmark date axis is not aligned")

        source = tuple(source_indices)
        if len(source) != sessions:
            raise ValueError("source_indices must have exactly one item per panel session")
        if any(type(index) is not int or index < 0 for index in source):
            raise ValueError("source_indices must contain nonnegative whole indices")
        if any(right != left + 1 for left, right in pairwise(source)):
            raise ValueError("source_indices must be strictly increasing and contiguous")
        local_by_source = {canonical: local for local, canonical in enumerate(source)}

        unknown_reason_symbols = set(missing_reasons) - set(symbols)
        if unknown_reason_symbols:
            raise ValueError(
                f"missingness reason names unknown symbol: {sorted(unknown_reason_symbols)}"
            )
        for reasons in missing_reasons.values():
            for canonical, declared_reason in reasons.items():
                if type(canonical) is not int or canonical not in local_by_source:
                    raise ValueError(f"missingness reason uses unknown canonical index {canonical}")
                if not isinstance(declared_reason, SignalMissingReason):
                    raise ValueError("missingness reason must be SignalMissingReason")

        missing: list[SignalMissing] = []
        emitted = 0
        for symbol in symbols:
            signal = np.asarray(signals[symbol])
            stop = np.asarray(stops[symbol])
            if signal.shape != (sessions,) or stop.shape != (sessions,):
                raise ValueError(f"signal or stop column has wrong length for {symbol}")
            reasons = missing_reasons.get(symbol, {})
            for local, raw in enumerate(signal):
                value = float(raw)
                canonical = source[local]
                reason = reasons.get(canonical)
                if np.isnan(value):
                    if reason is None:
                        raise ValueError(f"unlabelled NaN signal for {symbol} at {canonical}")
                    missing.append(SignalMissing(symbol, _ts_at(panel, local), canonical, reason))
                elif not np.isfinite(value) or value not in (0.0, 1.0):
                    raise ValueError(f"invalid signal value for {symbol} at {canonical}: {value}")
                elif reason is not None:
                    raise ValueError(
                        f"missingness reason attached to finite signal at {symbol} {canonical}"
                    )
                else:
                    emitted += int(value == 1.0)
        return source, tuple(missing), emitted


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


__all__ = [
    "SignalExitFragment",
    "SignalMissing",
    "SignalMissingReason",
    "SignalRunResult",
    "SignalSimulator",
    "SignalSkipReason",
    "SignalSkipped",
    "SignalTrade",
]
