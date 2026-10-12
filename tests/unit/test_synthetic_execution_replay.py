"""Invented M15 execution, causal opening capacity and the real exact matcher."""

from dataclasses import FrozenInstanceError, replace
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from fractions import Fraction
from importlib import import_module
from types import ModuleType
from typing import Any

import pytest
from scripts.research.synthetic_benchmark_match import (
    BenchmarkObservation,
    FixtureIdentity,
    ObservationState,
    Precision,
    RefusalReason,
)

from icarus.common.config import load_goal
from icarus.common.types import OrderSide
from icarus.engine.costmodel import CostModel, Segment
from icarus.engine.fills import FillModel, Intent, NoFillReason, OrderKind, SimBar
from icarus.engine.simcore import SignalId

OPEN = datetime(2020, 1, 3, 3, 45, tzinfo=UTC)
STEP = timedelta(minutes=15)


@pytest.fixture
def m() -> ModuleType:
    try:
        return import_module("scripts.research.synthetic_execution_replay")
    except ModuleNotFoundError:
        pytest.fail("reviewed synthetic replay is not implemented")


def fixture(m: ModuleType, *, days: int = 2, quantity: int = 100) -> Any:
    source = m.SourceDeclaration("invented-stock-and-sessions", "v1", "a" * 64)
    sessions = tuple(
        m.Session(
            252 + d, OPEN + timedelta(days=d - 1), OPEN + timedelta(days=d - 1) + 4 * STEP, source
        )
        for d in range(days + 1)
    )
    bars = tuple(
        m.ReplayBar(
            s.index,
            SimBar(
                s.open_ts + k * STEP, *(Decimal(x) for x in ("100", "101", "99", "100", "10000"))
            ),
            s.open_ts + (k + 1) * STEP,
            m.OpeningLiquidity(Decimal("10000"), s.open_ts + k * STEP, source),
            source,
        )
        for s in sessions[1:]
        for k in range(4)
    )
    request = m.ReplayRequest(
        SignalId("preset", 1, "SYNTH", sessions[0].open_ts, 252),
        sessions[0].close_ts,
        quantity,
        Decimal("95"),
    )
    return bind(m, request, sessions, bars)


def bind(m: ModuleType, request: Any, sessions: Any, bars: Any) -> Any:
    source = replace(sessions[0].source, sha256=m.fixture_digest(sessions, bars))
    sessions = tuple(replace(s, source=source) for s in sessions)
    bars = tuple(
        replace(
            b,
            source=source,
            opening=None if b.opening is None else replace(b.opening, source=source),
        )
        for b in bars
    )
    return request, sessions, bars, source


def change(
    m: ModuleType,
    data: Any,
    at: int,
    *,
    proxy: str | None = "10000",
    available: datetime | None = None,
    **ohlcv: str,
) -> Any:
    request, sessions, bars, _ = data
    row = bars[at]
    raw = replace(row.bar, **{k: Decimal(v) for k, v in ohlcv.items()})
    opening = (
        None
        if proxy is None
        else m.OpeningLiquidity(Decimal(proxy), available or row.bar.ts, row.source)
    )
    return bind(
        m, request, sessions, (*bars[:at], replace(row, bar=raw, opening=opening), *bars[at + 1 :])
    )


def run(m: ModuleType, data: Any, **realism: Any) -> Any:
    goal = load_goal()
    return m.replay_trade(
        *data,
        execution=goal.execution_realism.model_copy(update=realism),
        costs=CostModel(goal.costs),
    )


def weighted(m: ModuleType, *, next_day: bool = False) -> Any:
    data = fixture(m)
    data = change(m, data, 1, proxy="500", open="94", high="94", low="93", close="94")
    if next_day:
        for at in (2, 3):
            data = change(m, data, at, proxy="0")
        at = 4
    else:
        at = 2
    return change(m, data, at, proxy="1500", open="100", high="101", low="99", close="100")


def quotes(data: Any, last: int = 104) -> tuple[FixtureIdentity, tuple[BenchmarkObservation, ...]]:
    identity = FixtureIdentity("invented-index", "v1", "PRICE_INDEX", "index", "b" * 64)
    bars = data[2]
    return identity, tuple(
        BenchmarkObservation(
            identity, str(k), bars[k].bar.ts, bars[k].bar.ts, Fraction(p), ObservationState.OBSERVED
        )
        for k, p in ((0, 100), (1, 102), (2, last))
    )


@pytest.mark.parametrize("volume", ["500", "1000"])
def test_open_proxy_not_future_whole_bar_volume(m: ModuleType, volume: str) -> None:
    data = change(m, fixture(m), 0, proxy="500", volume=volume)
    trace = run(m, data)
    assert trace.original_quantity == 25
    assert trace.entry is not None and trace.entry.timing.event_ts == OPEN
    assert trace.entry.convention == "MODEL_OPEN_EVENT"
    goal = load_goal()
    expected = FillModel(goal.execution_realism).execute(
        Intent(OrderSide.BUY, OrderKind.MARKETABLE_LIMIT, 100, data[0].decision_available_ts),
        replace(data[2][0].bar, volume=Decimal("500")),
    )
    assert trace.entry.fill == expected
    assert expected.price is not None
    assert trace.entry.charges == CostModel(goal.costs).charges(
        Segment.EQUITY_DELIVERY, OrderSide.BUY, expected.price, Decimal(25)
    )


def test_impossible_opening_candidate_refuses_without_fee_or_accepted_leg(m: ModuleType) -> None:
    trace = run(m, change(m, fixture(m), 0, proxy="500", volume="1"))
    assert trace.refusal is m.ReplayRefusal.LIQUIDITY_UNAVAILABLE
    assert trace.entry is None and trace.original_quantity == 0
    assert trace.attempts == ()
    rejected = trace.rejected_opening
    assert rejected.session_index == 253 and rejected.raw_bar_ts == OPEN
    assert rejected.candidate.filled_quantity == 25 and rejected.candidate.price == Decimal(
        "100.05"
    )
    assert rejected.realized_capacity == 0
    with pytest.raises(FrozenInstanceError):
        rejected.realized_capacity = 25


def test_impossible_later_opening_exit_keeps_valid_inventory(m: ModuleType) -> None:
    data = change(
        m, fixture(m), 1, proxy="500", volume="1", open="94", high="94", low="93", close="94"
    )
    identity, observations = quotes(data)
    goal = load_goal()
    result = m.replay_and_match(
        *data,
        execution=goal.execution_realism,
        costs=CostModel(goal.costs),
        observations=observations,
        expected_benchmark=identity,
    )
    assert result.trace.refusal is m.ReplayRefusal.LIQUIDITY_UNAVAILABLE
    assert result.trace.remaining_quantity == result.trace.original_quantity == 100
    assert result.trace.exits == () and len(result.trace.attempts) == 1
    assert result.benchmark.benchmark_return is None
    rejected = result.trace.rejected_opening
    assert rejected.raw_bar_ts == OPEN + STEP
    assert rejected.candidate.filled_quantity == 25 and rejected.candidate.price == Decimal("93.95")
    assert rejected.realized_capacity == 0


@pytest.mark.parametrize(
    "proxy,delay,reason",
    [(None, 0, "MISSING_OPENING_LIQUIDITY"), ("10000", 1, "LATE_OPENING_LIQUIDITY")],
)
def test_unavailable_open_proxy_refuses(
    m: ModuleType, proxy: str | None, delay: int, reason: str
) -> None:
    trace = run(m, change(m, fixture(m), 0, proxy=proxy, available=OPEN + timedelta(seconds=delay)))
    assert trace.refusal is getattr(m.ReplayRefusal, reason)
    assert trace.entry is None and trace.original_quantity == 0


def test_latency_rounds_forward_without_same_session_entry(m: ModuleType) -> None:
    data = fixture(m)
    request = replace(data[0], decision_available_ts=OPEN)
    trace = run(m, (request, *data[1:]))
    assert trace.entry.raw_bar_ts == OPEN + STEP
    assert trace.signal_id == request.signal_id
    assert trace.entry.session_index == 253


def test_no_eligible_next_session_open_does_not_roll_into_third_session(m: ModuleType) -> None:
    data = fixture(m)
    request = replace(data[0], decision_available_ts=data[1][1].close_ts)
    trace = run(m, (request, *data[1:]))
    assert trace.refusal is m.ReplayRefusal.NO_ELIGIBLE_OPEN
    assert trace.entry is None and trace.attempts == ()


@pytest.mark.parametrize("proxy,partial", [("0", True), ("500", False)])
def test_no_entry_is_not_a_trade(m: ModuleType, proxy: str, partial: bool) -> None:
    trace = run(m, change(m, fixture(m), 0, proxy=proxy), model_partial_fills=partial)
    assert trace.status is m.ReplayStatus.NO_ENTRY
    assert trace.original_quantity == trace.remaining_quantity == 0
    assert len(trace.attempts) == 1 and not trace.attempts[0].fill.filled


def test_partial_stop_latches_through_rebound_and_exact_weighted_match(
    m: ModuleType, monkeypatch: Any
) -> None:
    data = weighted(m)
    identity, observations = quotes(data)
    calls: list[Any] = []
    original = m.match_benchmark

    def observe(*args: Any) -> Any:
        calls.append(args[0])
        return original(*args)

    monkeypatch.setattr(m, "match_benchmark", observe)
    goal = load_goal()
    result = m.replay_and_match(
        *data,
        execution=goal.execution_realism,
        costs=CostModel(goal.costs),
        observations=observations,
        expected_benchmark=identity,
    )
    assert result.trace.status is m.ReplayStatus.COMPLETE
    assert [a.fill.filled_quantity for a in result.trace.exits] == [25, 75]
    assert result.trace.exits[1].reason is m.ExitCause.STOP
    assert result.benchmark.benchmark_return == Fraction(7, 200)
    assert len(calls) == 1 and calls[0].original_quantity == 100
    assert result.trace.exits[0].charges.dp_charge > 0
    assert result.trace.exits[1].charges.dp_charge == 0


@pytest.mark.parametrize(
    "last,missing,expected", [(80, False, Fraction(-29, 200)), (80, True, None)]
)
def test_losing_or_missing_majority_never_renormalizes(
    m: ModuleType, last: int, missing: bool, expected: Any
) -> None:
    data = weighted(m)
    identity, observations = quotes(data, last)
    goal = load_goal()
    result = m.replay_and_match(
        *data,
        execution=goal.execution_realism,
        costs=CostModel(goal.costs),
        observations=observations[:-1] if missing else observations,
        expected_benchmark=identity,
    )
    assert result.benchmark.benchmark_return == expected


def test_dp_next_ist_day_charged_again(m: ModuleType) -> None:
    trace = run(m, weighted(m, next_day=True))
    assert [a.fill.filled_quantity for a in trace.exits] == [25, 75]
    assert all(a.charges.dp_charge > 0 for a in trace.exits)


def test_actual_partial_entry_quantity_is_matcher_original_q(m: ModuleType) -> None:
    data = change(m, fixture(m), 0, proxy="500", volume="500")
    data = change(m, data, 1, proxy="500", volume="500", open="94", high="94", low="93", close="94")
    identity, observations = quotes(data)
    goal = load_goal()
    result = m.replay_and_match(
        *data,
        execution=goal.execution_realism,
        costs=CostModel(goal.costs),
        observations=observations,
        expected_benchmark=identity,
    )
    assert result.trace.requested_quantity == 100 and result.trace.original_quantity == 25
    assert result.benchmark.benchmark_return == Fraction(1, 50)


def test_triggered_no_fill_stop_remains_latched_after_rebound(m: ModuleType) -> None:
    data = change(m, fixture(m), 1, volume="0", low="94")
    trace = run(m, data)
    assert trace.attempts[1].fill.reason is NoFillReason.NO_VOLUME
    assert len(trace.exits) == 1 and trace.exits[0].raw_bar_ts == OPEN + 2 * STEP
    assert trace.exits[0].reason is m.ExitCause.STOP


@pytest.mark.parametrize("partial,expected", [(True, 25), (False, 0)])
def test_intrabar_quantity_is_bounded_by_opening_proxy(
    m: ModuleType, partial: bool, expected: int
) -> None:
    data = fixture(m)
    data = (replace(data[0], target_price=Decimal("105")), *data[1:])
    trace = run(m, change(m, data, 1, proxy="500", high="106"), model_partial_fills=partial)
    assert sum(a.fill.filled_quantity for a in trace.exits) == expected
    if not partial:
        assert trace.attempts[1].fill.reason is NoFillReason.TOO_LARGE_FOR_BAR


def test_entry_protection_never_calls_fill_twice_on_same_bar(
    m: ModuleType, monkeypatch: Any
) -> None:
    data = change(m, fixture(m), 0, proxy="500", volume="500", low="94")
    calls: list[datetime] = []
    execute = FillModel.execute

    def observe(self: FillModel, intent: Intent, bar: SimBar) -> Any:
        calls.append(bar.ts)
        return execute(self, intent, bar)

    monkeypatch.setattr(FillModel, "execute", observe)
    trace = run(m, data)
    assert calls == [OPEN]
    assert trace.original_quantity == trace.remaining_quantity == 25
    assert trace.refusal is m.ReplayRefusal.PATH_ORDER_UNAVAILABLE


@pytest.mark.parametrize("kind", ["stop", "target", "both"])
def test_entry_bar_activation_order_refuses_without_sale(m: ModuleType, kind: str) -> None:
    data = fixture(m)
    request = replace(data[0], target_price=Decimal("105"))
    data = change(
        m,
        (request, *data[1:]),
        0,
        low="94" if kind != "target" else "99",
        high="106" if kind != "stop" else "101",
    )
    trace = run(m, data)
    assert trace.refusal is m.ReplayRefusal.PATH_ORDER_UNAVAILABLE
    assert trace.remaining_quantity == 100 and trace.exits == ()


def test_carried_both_levels_refuses_unknown_order(m: ModuleType) -> None:
    data = fixture(m)
    data = (replace(data[0], target_price=Decimal("105")), *data[1:])
    trace = run(m, change(m, data, 1, low="94", high="106"))
    assert trace.refusal is m.ReplayRefusal.ORDER_UNAVAILABLE
    assert trace.exits == () and trace.remaining_quantity == 100


def test_intrabar_stop_is_interval_and_matcher_refuses(m: ModuleType) -> None:
    data = change(m, fixture(m), 1, low="94")
    identity, observations = quotes(data)
    goal = load_goal()
    result = m.replay_and_match(
        *data,
        execution=goal.execution_realism,
        costs=CostModel(goal.costs),
        observations=observations,
        expected_benchmark=identity,
    )
    leg = result.trace.exits[0]
    assert leg.timing.precision is Precision.BAR_RESOLVED
    assert leg.timing.event_ts is None
    assert leg.recognition_ts == OPEN + 2 * STEP
    assert result.benchmark.benchmark_return is None
    assert result.benchmark.legs[1].refusal is RefusalReason.UNRESOLVED_PRECISION


@pytest.mark.parametrize(
    "high,volume,filled,reason",
    [
        ("105", "10000", 0, None),
        ("106", "100", 0, NoFillReason.QUEUE_TOO_DEEP),
        ("106", "1000", 50, None),
    ],
)
def test_target_touch_queue_and_shared_intrabar_capacity(
    m: ModuleType, high: str, volume: str, filled: int, reason: Any
) -> None:
    data = fixture(m)
    data = (replace(data[0], target_price=Decimal("105")), *data[1:])
    trace = run(m, change(m, data, 1, high=high, volume=volume))
    assert sum(a.fill.filled_quantity for a in trace.exits) == filled
    if reason is not None:
        assert trace.attempts[1].fill.reason is reason
    if filled:
        assert trace.exits[0].timing.precision is Precision.BAR_RESOLVED


@pytest.mark.parametrize("threshold,at", [(1, 1), (2, 4)])
def test_time_stop_counts_sessions_and_pays_activation_latency(
    m: ModuleType, threshold: int, at: int
) -> None:
    data = fixture(m)
    trace = run(m, (replace(data[0], time_stop_sessions=threshold), *data[1:]))
    assert len(trace.exits) == 1
    assert trace.exits[0].raw_bar_ts == data[2][at].bar.ts
    assert trace.exits[0].reason is m.ExitCause.TIME_STOP


def test_active_gap_stop_precedes_timer_and_timer_precedes_later_low(m: ModuleType) -> None:
    data = fixture(m)
    data = (replace(data[0], time_stop_sessions=2), *data[1:])
    trace = run(m, change(m, data, 4, open="94", high="94", low="93", close="94"))
    assert trace.exits[0].reason is m.ExitCause.STOP
    trace = run(m, change(m, data, 4, low="94"))
    assert trace.exits[0].reason is m.ExitCause.TIME_STOP
    assert trace.exits[0].timing.precision is Precision.EVENT_RESOLVED


def test_terminal_residual_stays_open_and_real_matcher_reports_q_mismatch(m: ModuleType) -> None:
    data = fixture(m)
    goal = load_goal()
    identity, observations = quotes(data)
    result = m.replay_and_match(
        *data,
        execution=goal.execution_realism,
        costs=CostModel(goal.costs),
        observations=observations,
        expected_benchmark=identity,
    )
    assert result.trace.status is m.ReplayStatus.OPEN
    assert result.trace.remaining_quantity == 100 and result.trace.exits == ()
    assert result.benchmark.benchmark_return is None
    assert result.benchmark.trade_refusals == (RefusalReason.QUANTITY_COVERAGE_MISMATCH,)


@pytest.mark.parametrize("kind", ["missing", "duplicate", "wrong_session", "source", "content"])
def test_preflight_refuses_before_any_fill(m: ModuleType, kind: str, monkeypatch: Any) -> None:
    data = fixture(m)
    request, sessions, bars, source = data
    if kind == "missing":
        bars = bars[1:]
    elif kind == "duplicate":
        bars = (bars[0], *bars)
    elif kind == "wrong_session":
        bars = (replace(bars[0], session_index=999), *bars[1:])
    elif kind == "source":
        bars = (replace(bars[0], source=replace(source, version="wrong")), *bars[1:])
    else:
        bars = (replace(bars[0], bar=replace(bars[0].bar, close=Decimal("100.5"))), *bars[1:])

    def forbidden(*args: Any) -> Any:
        pytest.fail("preflight must precede every FillModel call")

    monkeypatch.setattr(FillModel, "execute", forbidden)
    trace = run(m, (request, sessions, bars, source))
    assert trace.status is m.ReplayStatus.REFUSED and trace.entry is None


@pytest.mark.parametrize(
    "field,value",
    [
        ("quantity", True),
        ("quantity", 0),
        ("stop_price", Decimal("NaN")),
        ("stop_price", Decimal("0")),
        ("time_stop_sessions", True),
        ("target_price", Decimal("Infinity")),
        ("decision_available_ts", OPEN.replace(tzinfo=None)),
    ],
)
def test_malformed_request_errors(m: ModuleType, field: str, value: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(fixture(m)[0], **{field: value})


@pytest.mark.parametrize(
    "field,value",
    [("open", Decimal("NaN")), ("high", Decimal("99")), ("volume", Decimal("-1")), ("close", 100)],
)
def test_malformed_bar_errors(m: ModuleType, field: str, value: Any) -> None:
    row = fixture(m)[2][0]
    with pytest.raises((TypeError, ValueError)):
        replace(row, bar=replace(row.bar, **{field: value}))


def test_same_ist_day_and_exact_m15_validation(m: ModuleType) -> None:
    data = fixture(m)
    with pytest.raises(ValueError):
        replace(data[1][0], close_ts=data[1][0].open_ts + timedelta(days=1))
    with pytest.raises(ValueError):
        replace(data[2][0], end_ts=OPEN + timedelta(minutes=14))
    with pytest.raises(ValueError):
        replace(data[1][0], open_ts=OPEN.astimezone(timezone(timedelta(hours=5, minutes=30))))


def test_records_and_results_are_frozen(m: ModuleType) -> None:
    data = fixture(m)
    trace = run(m, data)
    with pytest.raises(FrozenInstanceError):
        trace.remaining_quantity = 0
    with pytest.raises(FrozenInstanceError):
        data[2][0].opening.quantity = Decimal(0)


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("schema_version", 2),
        ("sha256", "A" * 64),
        ("version", ""),
        ("artifact_id", 3),
    ],
)
def test_malformed_source_declaration_errors(m: ModuleType, field: str, value: Any) -> None:
    with pytest.raises((TypeError, ValueError)):
        replace(fixture(m)[3], **{field: value})


def test_missing_session_and_early_decision_refuse(m: ModuleType) -> None:
    data = fixture(m)
    trace = run(m, (data[0], (data[1][0], data[1][2]), data[2], data[3]))
    assert trace.refusal is m.ReplayRefusal.MISSING_REFINEMENT
    trace = run(m, (replace(data[0], decision_available_ts=data[1][0].open_ts), *data[1:]))
    assert trace.refusal is m.ReplayRefusal.INVALID_DECISION


def test_declared_special_windows_keep_session_clock(m: ModuleType) -> None:
    data = fixture(m)
    sessions = tuple(replace(s, close_ts=s.open_ts + 2 * STEP) for s in data[1])
    bars = tuple(b for b in data[2] if b.bar.ts < sessions[b.session_index - 252].close_ts)
    request = replace(data[0], decision_available_ts=sessions[0].close_ts, time_stop_sessions=2)
    trace = run(m, bind(m, request, sessions, bars))
    assert trace.exits[0].raw_bar_ts == sessions[2].open_ts
    assert trace.exits[0].session_index == 254
