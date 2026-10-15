"""Canonical real-input parsing and linear timed-bar indexing on invented records."""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from fractions import Fraction
from typing import Any

import numpy as np
import pytest

from icarus.engine.benchmark_match import (
    AvailabilityBasis,
    BenchmarkCandle,
    BenchmarkMode,
    FixtureIdentity,
)
from icarus.engine.data_readiness import BundlePreflight, CapturedArtifact
from icarus.engine.fills import SimBar
from icarus.engine.timed_runner import (
    EvaluationOutcome,
    EvaluationPlan,
    ExecutionBinding,
    GuardedTimedRunner,
    InputUnavailable,
    RunAuthorization,
    RunnerError,
    assemble_timed_inputs,
    parse_benchmark_candle_jsonl,
    parse_calendar_jsonl,
    parse_nifty_jsonl,
    parse_run_authorization_json,
)
from icarus.engine.timed_simulation import (
    DecisionAvailability,
    OpeningLiquidity,
    Refinement,
    ReplayBar,
    Session,
    SourceDeclaration,
    TimedFixture,
    index_timed_fixture,
    timed_fixture_digest,
)
from icarus.state.trial_ledger import (
    EvaluationReservation,
    TrialBatchReservation,
    TrialKind,
    TrialLedgerUnavailable,
    TrialReservationAuthorization,
)


def _lines(*rows: dict[str, object]) -> bytes:
    return b"".join(json.dumps(row, separators=(",", ":")).encode() + b"\n" for row in rows)


def _benchmark_identity() -> FixtureIdentity:
    return FixtureIdentity("NIFTY 50", "r1", "PRICE_INDEX", "invented-index", "b" * 64)


def _benchmark_candle_row() -> dict[str, object]:
    return {
        "schema_version": 2,
        "record_id": "nifty-m15-1",
        "revision": "r1",
        "source_index": 0,
        "instrument": "NIFTY 50",
        "venue": "NSE",
        "price_basis": "PRICE_INDEX",
        "interval_start_ts": "2020-01-01T03:45:00.000000Z",
        "interval_end_ts": "2020-01-01T04:00:00.000000Z",
        "open_numerator": 100,
        "open_denominator": 1,
        "high_numerator": 110,
        "high_denominator": 1,
        "low_numerator": 90,
        "low_denominator": 1,
        "close_numerator": 105,
        "close_denominator": 1,
        "raw_available_ts": None,
        "modeled_available_ts": "2020-01-01T04:00:00.000000Z",
        "availability_basis": "MODELED_INTERVAL_END",
        "quarantined": False,
    }


def test_descriptive_contract_keeps_unknown_raw_time_and_exact_positive_ohlc() -> None:
    source = FixtureIdentity("NIFTY 50", "r1", "PRICE_INDEX", "invented-index", "b" * 64)
    start = datetime(2020, 1, 3, 3, 45, tzinfo=UTC)
    candle = BenchmarkCandle(
        source,
        "nifty-m15-1",
        "r1",
        7,
        start,
        start + timedelta(minutes=15),
        Fraction(100),
        Fraction(110),
        Fraction(90),
        Fraction(105),
        None,
        start + timedelta(minutes=15),
        AvailabilityBasis.MODELED_INTERVAL_END,
    )
    assert candle.raw_available_ts is None
    assert candle.modeled_available_ts == candle.interval_end_ts
    assert BenchmarkMode.EXACT_OBSERVED_SESSION_CLOSE.value == "EXACT_OBSERVED_SESSION_CLOSE"


@pytest.mark.parametrize(
    ("field", "value", "reason"),
    [
        ("schema_version", 2.0, "NIFTY_CANDLE_SCHEMA"),
        ("schema_version", True, "NIFTY_CANDLE_SCHEMA"),
        ("source_index", True, "NIFTY_CANDLE_VALUE"),
        ("source_index", -1, "NIFTY_CANDLE_VALUE"),
    ],
)
def test_benchmark_candle_parser_rejects_inexact_schema_and_index(
    field: str, value: object, reason: str
) -> None:
    row = _benchmark_candle_row()
    row[field] = value
    with pytest.raises(InputUnavailable, match=reason):
        parse_benchmark_candle_jsonl(_lines(row), _benchmark_identity())


def test_benchmark_candle_parser_rejects_non_m15_interval() -> None:
    row = _benchmark_candle_row()
    row["interval_end_ts"] = "2020-01-01T04:15:00.000000Z"
    row["modeled_available_ts"] = row["interval_end_ts"]
    with pytest.raises(InputUnavailable, match="NIFTY_CANDLE_VALUE"):
        parse_benchmark_candle_jsonl(_lines(row), _benchmark_identity())


def test_descriptive_availability_is_digest_bound_without_changing_strict_digest() -> None:
    source = SourceDeclaration("invented", "r1", "0" * 64)
    opened = datetime(2020, 1, 2, 3, 45, tzinfo=UTC)
    sessions = (
        Session(10, opened, opened + timedelta(minutes=15), source),
        Session(11, opened + timedelta(days=1), opened + timedelta(days=1, minutes=15), source),
    )
    bar = ReplayBar(
        10,
        SimBar(
            opened,
            *(Decimal(value) for value in ("100", "101", "99", "100", "1000")),
        ),
        opened + timedelta(minutes=15),
        OpeningLiquidity(Decimal("900"), opened - timedelta(seconds=1), source),
        source,
    )
    refinements = (Refinement("AAA", (bar,)),)
    strict = timed_fixture_digest(sessions, refinements)
    schedule = (
        DecisionAvailability(
            10,
            None,
            sessions[1].open_ts,
            AvailabilityBasis.MODELED_NEXT_SESSION_OPEN,
        ),
        DecisionAvailability(11, None, None, AvailabilityBasis.MODELED_NEXT_SESSION_OPEN),
    )
    descriptive = timed_fixture_digest(
        sessions,
        refinements,
        decision_availability=schedule,
        availability_model="MODELED_NEXT_SESSION_OPEN_V1",
    )
    mutated = timed_fixture_digest(
        sessions,
        refinements,
        decision_availability=(replace(schedule[0], modeled_available_ts=None), schedule[1]),
        availability_model="MODELED_NEXT_SESSION_OPEN_V1",
    )
    assert strict == "032c89638dcd3679fe9d7cbf84b2d8d1910dce5b95f253ea4d940bbf0de12c90"
    assert descriptive != strict and mutated != descriptive


def _captured(role: str, payload: bytes) -> CapturedArtifact:
    identity = {
        "daily_stock": ("NSE", "CASH_EQUITY", "BACK_ADJUSTED"),
        "pit_universe": ("NSE", "CASH_EQUITY", "POINT_IN_TIME_MEMBERSHIP"),
        "corporate_action": ("NSE", "CASH_EQUITY", "BACK_ADJUSTED"),
        "m15_stock": ("NSE", "CASH_EQUITY", "BACK_ADJUSTED"),
        "nifty_observation": ("NSE", "NIFTY 50", "PRICE_INDEX"),
        "session_calendar": ("NSE", "CASH_EQUITY", "EXCHANGE_SESSION"),
        "opening_liquidity": ("NSE", "CASH_EQUITY", "PRIOR_OBSERVED_QUANTITY"),
    }[role]
    metadata = {
        "format": "jsonl",
        "schema_version": 1,
        "parser_version": "icarus-real-data-v1",
        "source_revision": "r1",
        "retrieved_at": "2026-10-14T00:00:00Z",
        "coverage_start": (
            "2020-01-02T00:00:00Z" if role == "session_calendar" else "2020-01-01T00:00:00Z"
        ),
        "coverage_end": (
            "2020-01-03T18:29:59Z" if role == "session_calendar" else "2020-01-04T00:00:00Z"
        ),
        "vendor": "INVENTED_TEST_VENDOR",
        "venue": identity[0],
        "instrument": identity[1],
        "price_basis": identity[2],
        "projection_policy": (
            "EXACT_OBSERVED_SESSION_CLOSE" if role == "nifty_observation" else "NONE"
        ),
    }
    return CapturedArtifact(
        role, f"{role}.jsonl", hashlib.sha256(payload).hexdigest(), len(payload), payload, metadata
    )


def test_all_seven_artifacts_assemble_one_causal_panel_and_timed_fixture() -> None:
    opens = ("2020-01-02T03:45:00Z", "2020-01-03T03:45:00Z")
    calendar = _lines(
        *(
            {
                "schema_version": 1,
                "record_id": f"c{i}",
                "revision": "r1",
                "source_index": i,
                "session_date": f"2020-01-0{i + 2}",
                "state": "regular",
                "open_ts": ts,
                "close_ts": ts.replace("03:45", "04:15"),
            }
            for i, ts in enumerate(opens)
        )
    )
    daily = _lines(
        *(
            {
                "schema_version": 1,
                "record_id": f"d{i}",
                "revision": "r1",
                "source_index": i,
                "symbol": "AAA",
                "event_ts": ts,
                "open": "100",
                "high": "102",
                "low": "99",
                "close": "101",
                "volume": "2000",
                "tradable": True,
                "state": "OBSERVED",
                "reason": "",
                "adjustment_basis": "BACK_ADJUSTED",
            }
            for i, ts in enumerate(opens)
        )
    )
    pit = _lines(
        *(
            {
                "schema_version": 1,
                "record_id": f"u{i}",
                "revision": "r1",
                "source_index": i,
                "symbol": "AAA",
                "event_ts": ts,
                "available_ts": ts,
                "eligible": True,
            }
            for i, ts in enumerate(opens)
        )
    )
    corporate = _lines(
        {
            "schema_version": 1,
            "record_id": "a0",
            "revision": "r1",
            "symbol": "AAA",
            "effective_ts": opens[0],
            "adjustment_basis": "BACK_ADJUSTED",
        }
    )
    m15_rows = []
    liquidity_rows = []
    for i, opened in enumerate(opens):
        start = datetime.fromisoformat(opened.replace("Z", "+00:00"))
        for k in range(2):
            at = start + timedelta(minutes=15 * k)
            end = at + timedelta(minutes=15)
            m15_rows.append(
                {
                    "schema_version": 1,
                    "record_id": f"m{i}-{k}",
                    "revision": "r1",
                    "source_index": i,
                    "symbol": "AAA",
                    "event_ts": at.isoformat().replace("+00:00", "Z"),
                    "end_ts": end.isoformat().replace("+00:00", "Z"),
                    "open": "100",
                    "high": "102",
                    "low": "99",
                    "close": "101",
                    "volume": "1000",
                    "adjustment_basis": "BACK_ADJUSTED",
                }
            )
            liquidity_rows.append(
                {
                    "schema_version": 1,
                    "record_id": f"l{i}-{k}",
                    "revision": "r1",
                    "source_index": i,
                    "symbol": "AAA",
                    "event_ts": at.isoformat().replace("+00:00", "Z"),
                    "available_ts": (at - timedelta(seconds=1)).isoformat().replace("+00:00", "Z"),
                    "quantity": "1000",
                    "method": "PRIOR_OBSERVED_QUANTITY_V1",
                }
            )
    nifty = _lines(
        *(
            {
                "schema_version": 1,
                "record_id": f"n{i}-{part}",
                "revision": "r1",
                "instrument": "NIFTY 50",
                "venue": "NSE",
                "price_basis": "PRICE_INDEX",
                "event_ts": (ts if part == "open" else ts.replace("03:45", "04:15")),
                "available_ts": (ts if part == "open" else ts.replace("03:45", "04:15")),
                "observed": True,
                "price_numerator": 100 + i + (1 if part == "close" else 0),
                "price_denominator": 1,
            }
            for i, ts in enumerate(opens)
            for part in ("open", "close")
        )
    )
    payloads = {
        "daily_stock": daily,
        "pit_universe": pit,
        "corporate_action": corporate,
        "m15_stock": _lines(*m15_rows),
        "nifty_observation": nifty,
        "session_calendar": calendar,
        "opening_liquidity": _lines(*liquidity_rows),
    }
    preflight = BundlePreflight(
        "a" * 64,
        "b" * 64,
        "c" * 64,
        tuple(_captured(role, payloads[role]) for role in payloads),
        True,
        False,
        False,
        ("DATA_PAYLOAD_NOT_ASSEMBLED",),
    )
    assembled = assemble_timed_inputs(preflight)
    assert not assembled.data_qualified and assembled.source_indices == (0, 1)
    assert assembled.nifty_source == SourceDeclaration(
        "INVENTED_TEST_VENDOR", "r1", hashlib.sha256(nifty).hexdigest()
    )
    assert assembled.panel.symbols == ("AAA",) and len(assembled.fixture.refinements[0].bars) == 4
    first_bar = assembled.fixture.refinements[0].bars[0]
    opening = first_bar.opening
    assert opening is not None and opening.available_ts <= first_bar.bar.ts
    invented = replace(preflight, status_reasons=("INVENTED_EXTERNAL_EVIDENCE",))
    assert not assemble_timed_inputs(invented).data_qualified
    intraday_nifty = _lines(
        {
            "schema_version": 1,
            "record_id": "intraday",
            "revision": "r1",
            "instrument": "NIFTY 50",
            "venue": "NSE",
            "price_basis": "PRICE_INDEX",
            "event_ts": "2020-01-02T04:00:00Z",
            "available_ts": "2020-01-02T04:00:00Z",
            "observed": True,
            "price_numerator": 201,
            "price_denominator": 2,
        }
    )
    expanded = replace(
        preflight,
        artifacts=tuple(
            _captured(item.role, item.payload + intraday_nifty)
            if item.role == "nifty_observation"
            else item
            for item in preflight.artifacts
        ),
    )
    assert len(assemble_timed_inputs(expanded).nifty) == 5
    later_m15 = replace(
        preflight,
        artifacts=tuple(
            replace(
                item,
                payload=_lines(
                    *[
                        json.loads(line)
                        for line in item.payload.decode().splitlines()
                        if json.loads(line)["source_index"] == 1
                    ]
                ),
                metadata={**item.metadata, "coverage_start": opens[1]},
            )
            if item.role in {"m15_stock", "opening_liquidity"}
            else item
            for item in preflight.artifacts
        ),
    )
    later = assemble_timed_inputs(later_m15)
    assert later.source_indices == (0, 1)
    assert {bar.session_index for bar in later.fixture.refinements[0].bars} == {1}
    absent_daily = [json.loads(line) for line in daily.decode().splitlines()]
    absent_daily[0].update(
        {
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "volume": None,
            "tradable": False,
            "state": "INACTIVE_ABSENT",
            "reason": "PRE_LISTING",
        }
    )
    absent_pit = [json.loads(line) for line in pit.decode().splitlines()]
    absent_pit[0]["eligible"] = False
    inactive = replace(
        preflight,
        artifacts=tuple(
            _captured(item.role, _lines(*absent_daily))
            if item.role == "daily_stock"
            else _captured(item.role, _lines(*absent_pit))
            if item.role == "pit_universe"
            else replace(
                item,
                payload=_lines(
                    *[
                        json.loads(line)
                        for line in item.payload.decode().splitlines()
                        if json.loads(line)["source_index"] == 1
                    ]
                ),
            )
            if item.role in {"m15_stock", "opening_liquidity"}
            else item
            for item in preflight.artifacts
        ),
    )
    inactive_result = assemble_timed_inputs(inactive)
    assert np.isnan(inactive_result.panel.bars[0].close[0])
    assert inactive_result.fixture.inactive == frozenset({("AAA", 0)})
    pit_rows = [json.loads(line) for line in pit.decode().splitlines()]
    pit_rows[0]["event_ts"] = opens[1]
    invalid_pit = replace(
        preflight,
        artifacts=tuple(
            _captured(item.role, _lines(*pit_rows)) if item.role == "pit_universe" else item
            for item in preflight.artifacts
        ),
    )
    with pytest.raises(InputUnavailable, match="PIT_TIME"):
        assemble_timed_inputs(invalid_pit)


def test_canonical_calendar_keeps_special_and_closed_dates_with_full_source_indices() -> None:
    raw = _lines(
        {
            "schema_version": 1,
            "record_id": "s0",
            "revision": "r1",
            "source_index": 10,
            "session_date": "2022-12-29",
            "state": "regular",
            "open_ts": "2022-12-29T03:45:00Z",
            "close_ts": "2022-12-29T10:00:00Z",
        },
        {
            "schema_version": 1,
            "record_id": "closed",
            "revision": "r1",
            "source_index": None,
            "session_date": "2022-12-30",
            "state": "closed",
            "open_ts": None,
            "close_ts": None,
        },
        {
            "schema_version": 1,
            "record_id": "s2",
            "revision": "r1",
            "source_index": 11,
            "session_date": "2022-12-31",
            "state": "special",
            "open_ts": "2022-12-31T04:00:00Z",
            "close_ts": "2022-12-31T06:00:00Z",
        },
    )
    rows = parse_calendar_jsonl(raw)
    assert [row.source_index for row in rows] == [10, None, 11]
    assert [row.state for row in rows] == ["regular", "closed", "special"]
    assert rows[1].open_ts is None and rows[2].open_ts == datetime(2022, 12, 31, 4, tzinfo=UTC)
    contradictory = raw.replace(b'"2022-12-29"', b'"2040-12-29"')
    with pytest.raises(InputUnavailable, match="CALENDAR_DATE_TIME"):
        parse_calendar_jsonl(contradictory)
    missing_day = raw.replace(b'"2022-12-30"', b'"2023-01-01"').replace(
        b'"2022-12-31"', b'"2023-01-02"'
    )
    with pytest.raises(InputUnavailable, match="CALENDAR_DATE_GAP"):
        parse_calendar_jsonl(missing_day)
    missing_open = raw.replace(b'"2022-12-29T03:45:00Z"', b"null")
    with pytest.raises(InputUnavailable, match="CALENDAR_HOURS"):
        parse_calendar_jsonl(missing_open)


def test_nifty_requires_raw_event_and_availability_and_price_index_identity() -> None:
    base = {
        "schema_version": 1,
        "record_id": "n0",
        "revision": "r1",
        "instrument": "NIFTY 50",
        "venue": "NSE",
        "price_basis": "PRICE_INDEX",
        "event_ts": "2022-01-03T03:45:00Z",
        "available_ts": "2022-01-03T03:45:01Z",
        "observed": True,
        "price_numerator": 180001,
        "price_denominator": 10,
    }
    assert parse_nifty_jsonl(_lines(base))[0].price.numerator == 180001
    for field, replacement in (("available_ts", None), ("price_basis", "TRI")):
        invalid = dict(base)
        invalid[field] = replacement
        with pytest.raises(InputUnavailable):
            parse_nifty_jsonl(_lines(invalid))
    with pytest.raises(InputUnavailable, match="JSONL_SYNTAX"):
        parse_nifty_jsonl(b'{"schema_version":1,"schema_version":1}\n')
    loose = dict(base)
    loose["schema_version"] = True
    with pytest.raises(InputUnavailable, match="NIFTY_SCHEMA"):
        parse_nifty_jsonl(_lines(loose))
    overprecise = dict(base)
    overprecise["event_ts"] = "2022-01-03T03:45:00.000000999Z"
    with pytest.raises(InputUnavailable, match="UTC_TIMESTAMP"):
        parse_nifty_jsonl(_lines(overprecise))


def test_timed_index_is_linear_reuses_rows_and_rejects_duplicate_order() -> None:
    source = SourceDeclaration("invented", "r1", "a" * 64)
    start = datetime(2020, 1, 2, 3, 45, tzinfo=UTC)
    sessions = tuple(
        Session(i, start + timedelta(days=i), start + timedelta(days=i, minutes=30), source)
        for i in range(3)
    )
    bars = tuple(
        ReplayBar(
            session.index,
            SimBar(
                session.open_ts + timedelta(minutes=15 * k),
                *(Decimal(x) for x in ("100", "101", "99", "100", "1000")),
            ),
            session.open_ts + timedelta(minutes=15 * (k + 1)),
            OpeningLiquidity(Decimal("1000"), session.open_ts, source),
            source,
        )
        for session in sessions
        for k in range(2)
    )
    fixture = TimedFixture(sessions, (Refinement("AAA", bars),), source)
    indexed = index_timed_fixture(fixture)
    assert indexed.visited_bars == len(bars)
    assert indexed.rows("AAA", 1)[0] is bars[2]
    with pytest.raises(TypeError):
        indexed.by_symbol_session["AAA"] = {}  # type: ignore[index]
    with pytest.raises(TypeError):
        indexed.by_symbol_session["AAA"][0] = ()  # type: ignore[index]
    broken = replace(fixture, refinements=(Refinement("AAA", (bars[0], bars[0])),))
    with pytest.raises(ValueError, match="ordered and unique"):
        index_timed_fixture(broken)


class _Receipt:
    authorization = TrialReservationAuthorization.NEW_EVALUATION


class _Ledger:
    def __init__(
        self,
        events: list[str],
        *,
        recovery_at: int | None = None,
        fail_terminal_at: int | None = None,
        complete_outage: bool = False,
    ) -> None:
        self.events = events
        self.recovery_at = recovery_at
        self.fail_terminal_at = fail_terminal_at
        self.complete_outage = complete_outage
        self.reservations: list[TrialBatchReservation] = []
        self.completed: list[tuple[Any, ...]] = []

    def reserve(self, batch: TrialBatchReservation) -> Any:
        self.events.append("reserve")
        self.reservations.append(batch)
        receipt = _Receipt()
        if len(self.reservations) == self.recovery_at:
            receipt.authorization = TrialReservationAuthorization.RECOVERY_ONLY
        return receipt

    def complete(self, receipt: Any, results: tuple[Any, ...]) -> object:
        del receipt
        self.events.append("terminal")
        if self.complete_outage:
            raise TrialLedgerUnavailable("invented terminal outage")
        self.completed.append(results)
        return object()

    def fail(self, receipt: Any, *, failure_code: str) -> object:
        del receipt, failure_code
        self.events.append("failed-terminal")
        if (
            len([event for event in self.events if event == "failed-terminal"])
            == self.fail_terminal_at
        ):
            raise RuntimeError("invented terminal outage")
        return object()


def _authorization() -> RunAuthorization:
    return RunAuthorization(
        authorization_id="external-run-1",
        issued_at=datetime.now(UTC) - timedelta(days=1),
        expires_at=datetime.now(UTC) + timedelta(days=1),
        bundle_sha256="a" * 64,
        approval_sha256="b" * 64,
        policy_sha256="c" * 64,
        qualification_sha256="d" * 64,
        goal_sha256="e" * 64,
        cards_sha256="f" * 64,
        runner_sha256="1" * 64,
        actual_ledger_activated=True,
        invented=False,
    )


def _binding() -> ExecutionBinding:
    auth = _authorization()
    return ExecutionBinding(
        auth.bundle_sha256,
        auth.approval_sha256,
        auth.policy_sha256,
        auth.qualification_sha256,
        auth.goal_sha256,
        auth.cards_sha256,
        auth.runner_sha256,
    )


def _plan(card: str, mode: str, capital: int | None) -> EvaluationPlan:
    at = datetime(2020, 1, 1, tzinfo=UTC)
    evaluations = (
        (
            EvaluationReservation(
                0,
                TrialKind.PORTFOLIO,
                None,
                0,
                2,
                at,
                at + timedelta(days=1),
                "walk_forward_portfolio_v1",
            ),
        )
        if mode == "portfolio"
        else (
            EvaluationReservation(
                0,
                TrialKind.SIGNAL_FULL,
                None,
                0,
                2,
                at,
                at + timedelta(days=1),
                "continuous_full_development_v1",
            ),
            EvaluationReservation(
                1, TrialKind.SIGNAL_FOLD, 0, 0, 1, at, at, "fresh_signal_simulator_per_fold_v1"
            ),
        )
    )
    return EvaluationPlan(
        card, 1, hashlib.sha256(card.encode()).hexdigest(), mode, capital, evaluations
    )


def test_guarded_runner_reserves_every_mode_and_capital_before_decoding() -> None:
    events: list[str] = []
    ledger = _Ledger(events)
    cards = ("control", "trend", "donchian", "momentum", "reversal", "low_vol", "breakout")
    plans = tuple(
        _plan(card, mode, capital)
        for card in cards
        for mode, capital in (("signal", None), ("portfolio", 100_000), ("portfolio", 1_000_000))
    )

    def decode() -> object:
        events.append("decode")
        return object()

    results = GuardedTimedRunner(ledger).run(
        _authorization(),
        _binding(),
        plans,
        decode,
        lambda plan, payload: tuple(
            EvaluationOutcome(
                {"card": plan.card, "mode": plan.mode, "payload": payload is not None},
                item.ordinal + 1,
            )
            for item in plan.evaluations
        ),
    )
    assert events[:21] == ["reserve"] * 21
    assert events[21] == "decode"
    assert events.count("terminal") == 21 and len(results) == 21
    assert len({batch.config_sha256 for batch in ledger.reservations}) == 3
    assert [row.observation_count for row in ledger.completed[0]] == [1, 2]


def test_evaluation_plan_persists_sorted_unique_primitive_inventory() -> None:
    plan = replace(_plan("one", "signal", None), primitives=("atr", "sma"))
    ledger = _Ledger([])
    GuardedTimedRunner(ledger).run(
        _authorization(),
        _binding(),
        (plan,),
        object,
        lambda current, _payload: tuple(
            EvaluationOutcome({"invented": True}, 0) for _ in current.evaluations
        ),
    )
    assert ledger.reservations[0].primitives == ("atr", "sma")
    with pytest.raises(ValueError, match="sorted unique"):
        replace(plan, primitives=("sma", "atr"))


def test_recovery_receipt_blocks_all_decoding_and_reruns() -> None:
    events: list[str] = []
    ledger = _Ledger(events, recovery_at=2)
    plans = (_plan("one", "signal", None), _plan("one", "portfolio", 100_000))
    with pytest.raises(RunnerError, match="RECOVERY_ONLY"):
        GuardedTimedRunner(ledger).run(
            _authorization(),
            _binding(),
            plans,
            lambda: pytest.fail("must not decode"),
            lambda *_: (),
        )
    assert events == ["reserve", "reserve", "failed-terminal"]


def test_decode_failure_terminalizes_every_reserved_evaluation_without_retry() -> None:
    events: list[str] = []
    ledger = _Ledger(events)
    plans = (_plan("one", "signal", None), _plan("one", "portfolio", 100_000))
    with pytest.raises(RunnerError, match="PRICE_DECODE_FAILED"):
        GuardedTimedRunner(ledger).run(
            _authorization(),
            _binding(),
            plans,
            lambda: (_ for _ in ()).throw(InputUnavailable("BAD_PAYLOAD")),
            lambda *_: pytest.fail("must not evaluate"),
        )
    assert events == ["reserve", "reserve", "failed-terminal", "failed-terminal"]


def test_evaluation_failure_terminalizes_current_and_every_unexecuted_reservation() -> None:
    events: list[str] = []
    ledger = _Ledger(events)
    plans = tuple(_plan(name, "portfolio", 100_000) for name in ("one", "two", "three"))
    calls = 0

    def evaluate(plan: EvaluationPlan, payload: object) -> tuple[EvaluationOutcome, ...]:
        nonlocal calls
        del plan, payload
        calls += 1
        raise InputUnavailable("BROKEN_EVALUATION")

    with pytest.raises(RunnerError, match="EVALUATION_FAILED"):
        GuardedTimedRunner(ledger).run(_authorization(), _binding(), plans, object, evaluate)
    assert calls == 1
    assert events == ["reserve"] * 3 + ["failed-terminal"] * 3


def test_terminal_failure_still_attempts_every_remaining_receipt() -> None:
    events: list[str] = []
    ledger = _Ledger(events, fail_terminal_at=1)
    plans = tuple(_plan(name, "portfolio", 100_000) for name in ("one", "two", "three"))
    with pytest.raises(RunnerError, match="TERMINAL_WRITE_FAILED"):
        GuardedTimedRunner(ledger).run(
            _authorization(),
            _binding(),
            plans,
            lambda: (_ for _ in ()).throw(InputUnavailable("BROKEN")),
            lambda *_: pytest.fail("must not evaluate"),
        )
    assert events == ["reserve"] * 3 + ["failed-terminal"] * 3


def test_repeated_complete_failure_terminalizes_every_later_unstarted_receipt() -> None:
    events: list[str] = []
    ledger = _Ledger(events, complete_outage=True)
    plans = tuple(_plan(name, "portfolio", 100_000) for name in ("one", "two", "three"))
    with pytest.raises(RunnerError, match="TERMINAL_WRITE_FAILED"):
        GuardedTimedRunner(ledger).run(
            _authorization(),
            _binding(),
            plans,
            object,
            lambda *_: (EvaluationOutcome({"invented": True}, 1),),
        )
    assert events == ["reserve"] * 3 + ["terminal", "terminal"] + ["failed-terminal"] * 2


def test_authorization_must_be_external_activated_unexpired_and_bound() -> None:
    plan = (_plan("one", "signal", None),)
    for authorization in (
        replace(_authorization(), invented=True),
        replace(_authorization(), actual_ledger_activated=False),
        replace(_authorization(), expires_at=datetime(2020, 1, 1, tzinfo=UTC)),
    ):
        with pytest.raises(RunnerError):
            GuardedTimedRunner(_Ledger([])).run(
                authorization, _binding(), plan, lambda: object(), lambda *_: ()
            )


def test_authorization_json_is_strictly_typed_and_bound() -> None:
    authorization = _authorization()
    row = {
        "schema_version": 1,
        "authorization_id": authorization.authorization_id,
        "issued_at": authorization.issued_at.isoformat().replace("+00:00", "Z"),
        "expires_at": authorization.expires_at.isoformat().replace("+00:00", "Z"),
        "bundle_sha256": authorization.bundle_sha256,
        "approval_sha256": authorization.approval_sha256,
        "policy_sha256": authorization.policy_sha256,
        "qualification_sha256": authorization.qualification_sha256,
        "goal_sha256": authorization.goal_sha256,
        "cards_sha256": authorization.cards_sha256,
        "runner_sha256": authorization.runner_sha256,
        "actual_ledger_activated": True,
        "invented": False,
    }
    assert parse_run_authorization_json(_lines(row)) == authorization
    row["actual_ledger_activated"] = "true"
    with pytest.raises(RunnerError, match="AUTHORIZATION_SCHEMA"):
        parse_run_authorization_json(_lines(row))
