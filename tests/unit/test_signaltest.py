"""Synthetic contract tests for Task 3a's signal identity and outcome records."""

from __future__ import annotations

import ast
import importlib.util
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from icarus.engine import signaltest as st
from icarus.engine import simcore
from icarus.engine.costmodel import Charges


def test_signal_record_module_exists_as_a_separate_engine_surface() -> None:
    """Removing the sibling module would collapse the diagnostic into the portfolio path."""
    assert importlib.util.find_spec("icarus.engine.signaltest") is not None


def _at(day: int) -> datetime:
    return datetime(2020, 1, day, tzinfo=UTC)


def _charges(
    turnover: str,
    *,
    brokerage: str = "0",
    stt: str = "0",
    exchange_txn: str = "0",
    sebi_fee: str = "0",
    gst: str = "0",
    stamp_duty: str = "0",
    dp_charge: str = "0",
) -> Charges:
    return Charges(
        brokerage=Decimal(brokerage),
        stt=Decimal(stt),
        exchange_txn=Decimal(exchange_txn),
        sebi_fee=Decimal(sebi_fee),
        gst=Decimal(gst),
        stamp_duty=Decimal(stamp_duty),
        dp_charge=Decimal(dp_charge),
        turnover=Decimal(turnover),
    )


def _signal_id(**changes: object) -> simcore.SignalId:
    fields: dict[str, object] = {
        "strategy_id": "breakout",
        "strategy_version": 2,
        "symbol": "AAA",
        "decision_ts": _at(1),
        "decision_index": 10,
    }
    fields.update(changes)
    return simcore.SignalId(**fields)  # type: ignore[arg-type]


def _fragment(**changes: object) -> st.SignalExitFragment:
    fields: dict[str, object] = {
        "quantity": 6,
        "price": Decimal("110"),
        "price_source_ts": _at(3),
        "price_source_index": 12,
        "recognition_ts": _at(3),
        "recognition_index": 12,
        "reason": simcore.ExitReason.TAKE_PROFIT,
        "charges": _charges("660", brokerage="2"),
        "benchmark_return": Decimal("0.03"),
    }
    fields.update(changes)
    return st.SignalExitFragment(**fields)  # type: ignore[arg-type]


def _trade(**changes: object) -> st.SignalTrade:
    fields: dict[str, object] = {
        "signal_id": _signal_id(),
        "entry_ts": _at(2),
        "entry_index": 11,
        "entry_price": Decimal("100"),
        "filled_quantity": 6,
        "intended_notional": Decimal("1000"),
        "risk_per_share": Decimal("10"),
        "entry_charges": _charges("600", brokerage="1"),
        "exit_fragments": (_fragment(),),
    }
    fields.update(changes)
    return st.SignalTrade(**fields)  # type: ignore[arg-type]


def test_signal_identity_is_stable_across_reconstruction_and_fold_views() -> None:
    """Including run/fold-local state would make one emitted signal fail to join to itself."""
    full_span = _signal_id()
    fold_view = _signal_id(decision_index=10)
    assert full_span == fold_view
    assert full_span.uuid == fold_view.uuid


@pytest.mark.parametrize(
    "change",
    [
        {"strategy_id": "reversal"},
        {"strategy_version": 3},
        {"symbol": "BBB"},
        {"decision_ts": _at(2)},
        {"decision_index": 11},
    ],
)
def test_signal_identity_changes_when_any_canonical_component_changes(
    change: dict[str, object],
) -> None:
    """Dropping any component would alias distinct signals in later fold/portfolio joins."""
    assert _signal_id(**change).uuid != _signal_id().uuid


@pytest.mark.parametrize(
    "change",
    [
        {"strategy_id": ""},
        {"strategy_version": 0},
        {"strategy_version": -1},
        {"strategy_version": True},
        {"strategy_version": 1.0},
        {"strategy_version": "v2"},
        {"symbol": ""},
        {"decision_ts": datetime(2020, 1, 1)},
        {"decision_ts": datetime(2020, 1, 1, tzinfo=timezone(timedelta(hours=5, minutes=30)))},
        {"decision_ts": datetime(2020, 1, 1, tzinfo=timezone(timedelta(0), "NOT_UTC"))},
        {"decision_index": -1},
        {"decision_index": True},
        {"decision_index": 1.0},
    ],
)
def test_signal_identity_refuses_noncanonical_components(change: dict[str, object]) -> None:
    """Malformed identity must halt rather than create a plausible but unjoinable UUID."""
    with pytest.raises((TypeError, ValueError)):
        _signal_id(**change)


def test_one_signal_identity_can_label_either_a_trade_or_a_typed_skip() -> None:
    """Changing identity by outcome would break the one-signal-one-observation accounting."""
    signal_id = _signal_id()
    trade = _trade(signal_id=signal_id)
    skipped = st.SignalSkipped(signal_id=signal_id, reason=st.SignalSkipReason.NOT_TRADABLE)
    assert trade.signal_id is signal_id
    assert skipped.signal_id is signal_id
    with pytest.raises((TypeError, ValueError)):
        st.SignalSkipped(signal_id=signal_id, reason="not_tradable")  # type: ignore[arg-type]


def test_partial_exits_remain_one_observation_and_reconcile_by_hand() -> None:
    """Emitting one trade per exit fill would inflate the sample and double-count entry costs."""
    exits = (
        _fragment(
            quantity=2,
            price=Decimal("120"),
            charges=_charges("240", stt="2"),
            benchmark_return=Decimal("0.12"),
        ),
        _fragment(
            quantity=4,
            price=Decimal("90"),
            price_source_ts=_at(5),
            price_source_index=14,
            recognition_ts=_at(5),
            recognition_index=14,
            reason=simcore.ExitReason.STOP_LOSS,
            charges=_charges("360", dp_charge="3"),
            benchmark_return=Decimal("-0.03"),
        ),
    )
    trade = _trade(exit_fragments=exits)
    assert trade.deployed_capital == Decimal("600")
    assert trade.gross_pnl == Decimal("0")
    assert trade.total_charges == Charges(
        brokerage=Decimal("1"),
        stt=Decimal("2"),
        exchange_txn=Decimal("0"),
        sebi_fee=Decimal("0"),
        gst=Decimal("0"),
        stamp_duty=Decimal("0"),
        dp_charge=Decimal("3"),
        turnover=Decimal("1200"),
    )
    assert trade.costs == Decimal("6")
    assert trade.net_pnl == Decimal("-6")
    assert trade.gross_return == Decimal("0")
    assert trade.net_return == Decimal("-0.01")
    assert trade.r_multiple == Decimal("-0.1")
    assert trade.benchmark_return == Decimal("0.02")
    assert trade.pre_tax_alpha == Decimal("-0.03")
    assert trade.exit_fills == 2
    assert trade.holding_sessions == 4


def test_actual_fill_and_stale_residual_keep_price_and_recognition_coordinates_separate() -> None:
    """Dating a stale mark by its old price source would understate the holding period."""
    exits = (
        _fragment(
            quantity=3,
            price=Decimal("115"),
            price_source_ts=_at(5),
            price_source_index=14,
            recognition_ts=_at(5),
            recognition_index=14,
            charges=_charges("345", exchange_txn="1"),
        ),
        _fragment(
            quantity=3,
            price=Decimal("80"),
            price_source_ts=_at(4),
            price_source_index=13,
            recognition_ts=_at(7),
            recognition_index=16,
            reason=simcore.ExitReason.STALE_MARK,
            charges=_charges("240", dp_charge="2"),
        ),
    )
    trade = _trade(exit_fragments=exits)
    assert trade.exit_fills == 1
    assert trade.marked_quantity == 3
    assert trade.marked_value == Decimal("240")
    assert trade.final_recognition_index == 16
    assert trade.holding_sessions == 6


def test_entry_bar_exit_is_one_holding_session() -> None:
    """A next-bar entry can exit on that same bar without looking ahead at decision time."""
    exit_on_entry = _fragment(
        price_source_ts=_at(2),
        price_source_index=11,
        recognition_ts=_at(2),
        recognition_index=11,
    )
    trade = _trade(exit_fragments=(exit_on_entry,))
    assert trade.holding_sessions == 1
    assert trade.exit_fills == 1


def test_final_bar_stale_mark_is_not_counted_as_an_execution_fill() -> None:
    """A quoted final price can still be an assumption rather than an exit fill."""
    final_mark = _fragment(reason=simcore.ExitReason.STALE_MARK)
    trade = _trade(exit_fragments=(final_mark,))
    assert trade.marked_quantity == 6
    assert trade.exit_fills == 0
    assert trade.holding_sessions == 2


def test_missing_benchmark_fragment_makes_whole_trade_alpha_unavailable() -> None:
    """Reweighting only observed fragments would turn missing data into flattering precision."""
    exits = (
        _fragment(quantity=2, charges=_charges("220"), benchmark_return=Decimal("0.04")),
        _fragment(
            quantity=4,
            price=Decimal("105"),
            price_source_ts=_at(4),
            price_source_index=13,
            recognition_ts=_at(4),
            recognition_index=13,
            charges=_charges("420"),
            benchmark_return=None,
        ),
    )
    trade = _trade(exit_fragments=exits)
    assert trade.benchmark_return is None
    assert trade.pre_tax_alpha is None


def test_observed_zero_benchmark_remains_zero_and_produces_alpha() -> None:
    """Treating a real zero as missing would erase a valid market-adjusted observation."""
    trade = _trade(exit_fragments=(_fragment(benchmark_return=Decimal("0")),))
    assert trade.benchmark_return == Decimal("0")
    assert trade.pre_tax_alpha == trade.net_return


@pytest.mark.parametrize(
    "change",
    [
        {"quantity": 0},
        {"quantity": True},
        {"quantity": 1.5},
        {"price": Decimal("0")},
        {"price": Decimal("Infinity")},
        {"benchmark_return": Decimal("NaN")},
        {"charges": _charges("660", brokerage="-1")},
        {"charges": _charges("659")},
        {"price_source_ts": datetime(2020, 1, 3)},
        {"recognition_ts": datetime(2020, 1, 3)},
        {"recognition_ts": datetime(2020, 1, 3, tzinfo=timezone(timedelta(0), "NOT_UTC"))},
        {"price_source_index": -1},
        {"recognition_index": True},
    ],
)
def test_exit_fragment_refuses_malformed_prices_quantities_charges_and_coordinates(
    change: dict[str, object],
) -> None:
    """A malformed fragment must fail at construction rather than poison later statistics."""
    with pytest.raises((TypeError, ValueError)):
        _fragment(**change)


def test_actual_fill_coordinates_must_match_exactly() -> None:
    """A real fill cannot be recognised later or at a different source bar like an estimate."""
    with pytest.raises(ValueError):
        _fragment(recognition_ts=_at(4), recognition_index=13)


@pytest.mark.parametrize(
    "change",
    [
        {"entry_index": 10, "entry_ts": _at(1)},
        {"entry_index": 11, "entry_ts": _at(1)},
        {"entry_ts": datetime(2020, 1, 2)},
        {"entry_price": Decimal("NaN")},
        {"filled_quantity": 0},
        {"filled_quantity": False},
        {"intended_notional": Decimal("0")},
        {"risk_per_share": Decimal("-1")},
        {"entry_charges": _charges("601")},
        {"entry_charges": _charges("600", gst="Infinity")},
        {"exit_fragments": ()},
    ],
)
def test_trade_refuses_malformed_entry_accounting_or_exit_quantity(
    change: dict[str, object],
) -> None:
    """Invalid capital or share reconciliation must never reach a diagnostic metric."""
    with pytest.raises((TypeError, ValueError)):
        _trade(**change)


@pytest.mark.parametrize("quantity", [5, 7])
def test_trade_refuses_underfilled_or_overfilled_exit_quantity(quantity: int) -> None:
    """Exit fragments must account for every filled share exactly once."""
    with pytest.raises(ValueError):
        _trade(
            exit_fragments=(_fragment(quantity=quantity, charges=_charges(str(quantity * 110))),)
        )


def test_trade_refuses_fragment_before_entry_or_out_of_recognition_order() -> None:
    """Unordered recognition would make the final holding index depend on tuple accidents."""
    before_entry = _fragment(
        price_source_ts=_at(1),
        price_source_index=10,
        recognition_ts=_at(1),
        recognition_index=10,
    )
    with pytest.raises(ValueError):
        _trade(exit_fragments=(before_entry,))

    later = _fragment(
        quantity=3,
        price_source_ts=_at(5),
        price_source_index=14,
        recognition_ts=_at(5),
        recognition_index=14,
        charges=_charges("330"),
    )
    earlier = _fragment(quantity=3, charges=_charges("330"))
    with pytest.raises(ValueError):
        _trade(exit_fragments=(later, earlier))


def test_equal_indices_require_equal_timestamps() -> None:
    """Two times for one canonical session index would make chronology internally contradictory."""
    with pytest.raises(ValueError):
        _fragment(
            price_source_ts=_at(3),
            price_source_index=12,
            recognition_ts=_at(4),
            recognition_index=12,
            reason=simcore.ExitReason.STALE_MARK,
        )


def test_fragments_share_one_canonical_index_to_timestamp_axis() -> None:
    """A stale source cannot redefine an index already used by another fill."""
    actual = _fragment(quantity=3, charges=_charges("330"))
    stale = _fragment(
        quantity=3,
        price=Decimal("80"),
        price_source_ts=_at(4),
        price_source_index=12,
        recognition_ts=_at(7),
        recognition_index=16,
        reason=simcore.ExitReason.STALE_MARK,
        charges=_charges("240"),
    )
    with pytest.raises(ValueError, match="canonical"):
        _trade(exit_fragments=(actual, stale))


def test_fragments_reject_reversed_source_time_for_increasing_index() -> None:
    """The whole-source axis must stay ordered even when a stale price is recognised later."""
    actual = _fragment(
        quantity=3,
        price_source_ts=_at(5),
        price_source_index=14,
        recognition_ts=_at(5),
        recognition_index=14,
        charges=_charges("330"),
    )
    stale = _fragment(
        quantity=3,
        price=Decimal("80"),
        price_source_ts=_at(4),
        price_source_index=15,
        recognition_ts=_at(7),
        recognition_index=16,
        reason=simcore.ExitReason.STALE_MARK,
        charges=_charges("240"),
    )
    with pytest.raises(ValueError, match="canonical"):
        _trade(exit_fragments=(actual, stale))


def test_records_are_frozen_slotted_and_have_no_portfolio_metrics() -> None:
    """Adding gate-shaped fields would let this diagnostic masquerade as a portfolio result."""
    records: tuple[tuple[object, str, object], ...] = (
        (_signal_id(), "symbol", "MUTATED"),
        (
            st.SignalSkipped(_signal_id(), st.SignalSkipReason.NO_NEXT_BAR),
            "reason",
            st.SignalSkipReason.NOT_TRADABLE,
        ),
        (_fragment(), "price", Decimal("1")),
        (_trade(), "entry_price", Decimal("1")),
    )
    for record, field_name, replacement in records:
        assert not hasattr(record, "__dict__")
        with pytest.raises(FrozenInstanceError):
            setattr(record, field_name, replacement)

    trade = _trade()
    for forbidden in (
        "alpha",
        "sharpe",
        "sortino",
        "calmar",
        "cagr",
        "volatility",
        "max_drawdown",
        "equity",
        "promotion_verdict",
    ):
        assert not hasattr(trade, forbidden)


def test_signaltest_does_not_import_portfolio_runner_or_metrics() -> None:
    """A sibling import would let promotion-path changes silently alter the diagnostic records."""
    source = Path(st.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported = {
        alias.name
        for node in ast.walk(tree)
        if isinstance(node, ast.Import)
        for alias in node.names
    }
    imported.update(
        node.module or "" for node in ast.walk(tree) if isinstance(node, ast.ImportFrom)
    )
    assert imported.isdisjoint(
        {"icarus.engine.portfolio", "icarus.engine.runner", "icarus.engine.metrics"}
    )
