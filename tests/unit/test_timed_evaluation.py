"""The timed catalogue evaluator uses exact geometry and real simulator entry points."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, cast

import pytest
from scripts.run_timed_backtest import (
    EVIDENCE_KEYS,
    TimedCliError,
    _assert_external_path,
    main,
    parse_matching_policy,
    parse_qualification_certificate,
)
from scripts.synthetic_strategy_demo import invented_panel

from icarus.common.config import load_goal
from icarus.engine.backtest import Window
from icarus.engine.benchmark_match import MatchingPolicy, SelectionPolicy
from icarus.engine.data_readiness import BundlePreflight
from icarus.engine.fills import SimBar
from icarus.engine.timed_evaluation import (
    CAPITALS,
    CataloguePayload,
    EvaluationClock,
    TimedCatalogueEvaluator,
    _slice_fixture,
    build_evaluation_plans,
    load_strategy_catalogue,
)
from icarus.engine.timed_runner import AssembledTimedInputs
from icarus.engine.timed_simulation import (
    OpeningLiquidity,
    Refinement,
    ReplayBar,
    Session,
    SourceDeclaration,
    TimedFixture,
    index_timed_fixture,
    timed_fixture_digest,
)


def _fixture(panel: Any) -> TimedFixture:
    source = SourceDeclaration("invented", "v1", "a" * 64)
    sessions = tuple(
        Session(
            i,
            datetime.fromtimestamp(int(ts.astype("datetime64[s]").astype(int)), UTC),
            datetime.fromtimestamp(int(ts.astype("datetime64[s]").astype(int)), UTC)
            + timedelta(minutes=15),
            source,
        )
        for i, ts in enumerate(panel.ts)
    )
    refinements = tuple(
        Refinement(
            symbol,
            tuple(
                ReplayBar(
                    i,
                    SimBar(
                        sessions[i].open_ts,
                        *(
                            Decimal(str(float(getattr(bars, field)[i])))
                            for field in ("open", "high", "low", "close", "volume")
                        ),
                    ),
                    sessions[i].close_ts,
                    OpeningLiquidity(Decimal("1000000"), sessions[i].open_ts, source),
                    source,
                )
                for i in range(len(panel))
            ),
        )
        for symbol, bars in zip(panel.symbols, panel.bars, strict=True)
    )
    digest = timed_fixture_digest(sessions, refinements)
    bound = replace(source, sha256=digest)
    sessions = tuple(replace(item, source=bound) for item in sessions)
    refinements = tuple(
        Refinement(
            item.symbol,
            tuple(
                replace(
                    row,
                    source=bound,
                    opening=replace(row.opening, source=bound) if row.opening is not None else None,
                )
                for row in item.bars
            ),
        )
        for item in refinements
    )
    return TimedFixture(sessions, refinements, bound)


def _policy() -> MatchingPolicy:
    return MatchingPolicy(
        "invented-pinned-asof", SelectionPolicy.LATEST_AVAILABLE_OBSERVED, timedelta(days=2)
    )


def _assembled(panel: Any, fixture: TimedFixture) -> AssembledTimedInputs:
    nifty_source = SourceDeclaration("invented-nifty", "v1", "d" * 64)
    return AssembledTimedInputs(panel, fixture, tuple(range(len(panel))), (), False, nifty_source)


def _with_inactive_prefix(fixture: TimedFixture, count: int) -> TimedFixture:
    symbol = fixture.refinements[0].symbol
    inactive = frozenset((symbol, item.index) for item in fixture.sessions[:count])
    refinements = (
        replace(
            fixture.refinements[0],
            bars=tuple(row for row in fixture.refinements[0].bars if row.session_index >= count),
        ),
        *fixture.refinements[1:],
    )
    digest = timed_fixture_digest(fixture.sessions, refinements, inactive)
    source = replace(fixture.source, sha256=digest)
    sessions = tuple(replace(item, source=source) for item in fixture.sessions)
    bound = tuple(
        replace(
            item,
            bars=tuple(
                replace(
                    row,
                    source=source,
                    opening=(None if row.opening is None else replace(row.opening, source=source)),
                )
                for row in item.bars
            ),
        )
        for item in refinements
    )
    return TimedFixture(sessions, bound, source, inactive)


def test_catalogue_loads_exactly_seven_cards_and_builds_twenty_one_plans(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panel = invented_panel()
    goal = load_goal()
    cards = load_strategy_catalogue(tuple(sorted(Path("strategies").glob("*.yaml"))), goal)
    monkeypatch.setattr(
        "icarus.engine.timed_evaluation._clock_windows",
        lambda *_: (Window(0, 300, 305, 400, 5), Window(0, 400, 405, 500, 5)),
    )
    fixture = _fixture(panel)
    clock = EvaluationClock(
        tuple(item.index for item in fixture.sessions),
        tuple(item.open_ts for item in fixture.sessions),
    )
    plans = build_evaluation_plans(cards, clock, goal)
    assert len(cards) == 7 and len(plans) == 21
    assert {plan.capital for plan in plans if plan.mode == "portfolio"} == set(CAPITALS)
    assert all(len(plan.evaluations) == 3 for plan in plans if plan.mode == "signal")
    assert all(len(plan.evaluations) == 1 for plan in plans if plan.mode == "portfolio")
    card_by_name = {card.candidate.name: card for card in cards}
    assert all(
        plan.primitives == tuple(sorted(card_by_name[plan.card].candidate.primitives_used()))
        for plan in plans
    )
    signal_full = next(plan for plan in plans if plan.mode == "signal").evaluations[0]
    assert signal_full.end_index_exclusive == len(panel)


def test_whole_clock_rejects_lockbox_before_geometry_is_selected() -> None:
    goal = load_goal()
    cards = load_strategy_catalogue((Path("strategies/baseline_buy_and_hold.yaml"),), goal)
    clock = EvaluationClock(
        (0, 1),
        (
            datetime(2022, 12, 30, tzinfo=UTC),
            datetime(2023, 1, 2, tzinfo=UTC),
        ),
    )
    with pytest.raises(ValueError, match="whole source clock reaches lockbox"):
        build_evaluation_plans(cards, clock, goal)


def test_actual_signal_and_portfolio_modes_use_shared_columns_and_fresh_books(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panel = invented_panel()
    goal = load_goal()
    cards = load_strategy_catalogue((Path("strategies/baseline_buy_and_hold.yaml"),), goal)
    fixture = _fixture(panel)
    assembled = _assembled(panel, fixture)
    payload = CataloguePayload.from_assembled(assembled, cards)
    monkeypatch.setattr(
        "icarus.engine.timed_evaluation._clock_windows",
        lambda *_: (Window(0, 300, 305, 500, 5),),
    )
    clock = EvaluationClock(
        tuple(item.index for item in fixture.sessions),
        tuple(item.open_ts for item in fixture.sessions),
    )
    plans = build_evaluation_plans(cards, clock, goal)
    evaluator = TimedCatalogueEvaluator(cards, goal, _policy())
    outcomes = [evaluator.evaluate(plan, payload) for plan in plans]
    assert [len(value) for value in outcomes] == [2, 1, 1]
    payloads = [cast(dict[str, object], item.payload) for rows in outcomes for item in rows]
    assert all(item["pre_tax_diagnostic"] is True for item in payloads)
    assert all(item["run_valid"] is True for item in payloads)
    assert all(item.observation_count >= 1 for rows in outcomes for item in rows)
    assert payload.column_evaluations == 1


@pytest.mark.parametrize("mutation", ["daily", "benchmark"])
def test_paired_evaluator_refuses_projection_mutated_after_assembly(
    monkeypatch: pytest.MonkeyPatch,
    mutation: str,
) -> None:
    from tests.unit.test_source_pair import _raw

    from icarus.engine.source_pair import (
        BoundPairQualification,
        daily_projection_digest,
        parse_source_pair_qualification,
    )

    panel = invented_panel()
    if mutation == "benchmark":
        source = panel.bars[0]
        benchmark = replace(
            source,
            ts=source.ts.copy(),
            open=source.open.copy(),
            high=source.high.copy(),
            low=source.low.copy(),
            close=source.close.copy(),
            volume=source.volume.copy(),
        )
        panel = replace(panel, benchmark=benchmark)
    fixture = _fixture(panel)
    pair = BoundPairQualification(
        parse_source_pair_qualification(_raw()),
        daily_projection_digest(panel, tuple(range(len(panel)))),
    )
    digest = timed_fixture_digest(
        fixture.sessions, fixture.refinements, fixture.inactive, pair.qualification.document_sha256
    )
    source = replace(fixture.source, sha256=digest)
    fixture = replace(
        fixture,
        sessions=tuple(replace(row, source=source) for row in fixture.sessions),
        refinements=tuple(
            Refinement(
                item.symbol,
                tuple(
                    replace(row, source=source, opening=replace(row.opening, source=source))
                    for row in item.bars
                ),
            )
            for item in fixture.refinements
        ),
        source=source,
        pair_qualification=pair,
    )
    goal = load_goal()
    cards = load_strategy_catalogue((Path("strategies/baseline_buy_and_hold.yaml"),), goal)
    assembled = _assembled(panel, fixture)
    assert not hasattr(assembled, "source_pair")
    payload = CataloguePayload.from_assembled(assembled, cards)
    if mutation == "daily":
        panel.bars[0].close[10] += 0.01
    else:
        assert panel.benchmark is not None
        stock_close = panel.bars[0].close[10]
        assert panel.benchmark.close is not panel.bars[0].close
        panel.benchmark.close[10] += 0.01
        assert panel.bars[0].close[10] == stock_close
    monkeypatch.setattr(
        "icarus.engine.timed_evaluation._clock_windows",
        lambda *_: (Window(0, 300, 305, 500, 5),),
    )
    plan = build_evaluation_plans(
        cards,
        EvaluationClock(
            tuple(item.index for item in fixture.sessions),
            tuple(item.open_ts for item in fixture.sessions),
        ),
        goal,
    )[0]
    with pytest.raises(ValueError, match="daily projection changed"):
        TimedCatalogueEvaluator(cards, goal, _policy()).evaluate(plan, payload)


def test_all_seven_cards_run_twenty_one_actual_modes_with_management_events(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panel = invented_panel()
    goal = load_goal()
    cards = load_strategy_catalogue(tuple(sorted(Path("strategies").glob("*.yaml"))), goal)
    fixture = _fixture(panel)
    assembled = _assembled(panel, fixture)
    payload = CataloguePayload.from_assembled(assembled, cards)
    monkeypatch.setattr(
        "icarus.engine.timed_evaluation._clock_windows",
        lambda *_: (Window(0, 300, 305, 500, 5),),
    )
    plans = build_evaluation_plans(
        cards,
        EvaluationClock(
            tuple(item.index for item in fixture.sessions),
            tuple(item.open_ts for item in fixture.sessions),
        ),
        goal,
    )
    evaluator = TimedCatalogueEvaluator(cards, goal, _policy())
    results = [evaluator.evaluate(plan, payload) for plan in plans]
    summaries = [cast(dict[str, Any], item.payload) for rows in results for item in rows]
    fold_summaries = [
        cast(dict[str, Any], fold)
        for summary in summaries
        for fold in cast(list[object], summary.get("folds", []))
    ]
    all_runs = [*summaries, *fold_summaries]
    assert len(plans) == 21 and len(results) == 21 and payload.column_evaluations == 7
    assert sum(int(run.get("entry_count", 0)) for run in all_runs) > 0
    assert sum(int(run.get("exit_count", 0)) for run in all_runs) > 0
    assert sum(int(run.get("rebalance_events", 0)) for run in all_runs) > 0
    benchmark_rows = [
        cast(dict[str, Any], benchmark)
        for run in all_runs
        for benchmark in cast(list[object], run.get("benchmark", []))
    ]
    assert benchmark_rows and any(row["return"] is None and row["legs"] for row in benchmark_rows)
    assert all(
        summary.get("book_reset_each_fold") is True
        for plan, rows in zip(plans, results, strict=True)
        for summary in [cast(dict[str, object], rows[0].payload)]
        if plan.mode == "portfolio"
    )


def test_plan_or_payload_identity_mismatch_refuses_before_simulation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panel = invented_panel()
    goal = load_goal()
    cards = load_strategy_catalogue((Path("strategies/baseline_buy_and_hold.yaml"),), goal)
    fixture = _fixture(panel)
    payload = CataloguePayload.from_assembled(_assembled(panel, fixture), cards)
    monkeypatch.setattr(
        "icarus.engine.timed_evaluation._clock_windows",
        lambda *_: (Window(0, 300, 305, 500, 5),),
    )
    bad = replace(cards[0], sha256="b" * 64)
    with pytest.raises(ValueError, match="catalogue identity"):
        TimedCatalogueEvaluator((bad,), goal, _policy()).evaluate(
            build_evaluation_plans(
                cards,
                EvaluationClock(
                    tuple(item.index for item in fixture.sessions),
                    tuple(item.open_ts for item in fixture.sessions),
                ),
                goal,
            )[0],
            payload,
        )

    valid_plan = build_evaluation_plans(
        cards,
        EvaluationClock(
            tuple(item.index for item in fixture.sessions),
            tuple(item.open_ts for item in fixture.sessions),
        ),
        goal,
    )[0]
    with pytest.raises(ValueError, match="catalogue identity"):
        TimedCatalogueEvaluator(cards, goal, _policy()).evaluate(
            replace(valid_plan, card_version=valid_plan.card_version + 1), payload
        )


def test_inactive_ipo_cells_survive_cached_slice_and_mask_tamper_refuses(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    panel = invented_panel()
    goal = load_goal()
    cards = load_strategy_catalogue((Path("strategies/baseline_buy_and_hold.yaml"),), goal)
    fixture = _with_inactive_prefix(_fixture(panel), 20)
    sliced = _slice_fixture(fixture, index_timed_fixture(fixture), 0, 500)
    assert sliced.inactive == fixture.inactive
    assert sliced.source.sha256 == timed_fixture_digest(
        sliced.sessions, sliced.refinements, sliced.inactive
    )

    assembled = _assembled(panel, fixture)
    payload = CataloguePayload.from_assembled(assembled, cards)
    monkeypatch.setattr(
        "icarus.engine.timed_evaluation._clock_windows",
        lambda *_: (Window(0, 300, 305, 500, 5),),
    )
    plan = build_evaluation_plans(
        cards,
        EvaluationClock(
            tuple(item.index for item in fixture.sessions),
            tuple(item.open_ts for item in fixture.sessions),
        ),
        goal,
    )[0]
    assert TimedCatalogueEvaluator(cards, goal, _policy()).evaluate(plan, payload)

    tampered = replace(fixture, inactive=frozenset())
    with pytest.raises(ValueError, match="fixture source digest"):
        CataloguePayload.from_assembled(_assembled(panel, tampered), cards)


def test_external_qualification_must_be_outside_bundle() -> None:
    inside = Path(__file__).resolve()
    bundle = inside.parents[2]
    with pytest.raises(TimedCliError, match="EXTERNAL_EVIDENCE_PATH"):
        _assert_external_path(inside, bundle)


def test_cli_defaults_to_metadata_only_check_without_execution_imports(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    preflight = BundlePreflight(
        "a" * 64,
        "b" * 64,
        "c" * 64,
        (),
        True,
        False,
        False,
        ("EXTERNAL_QUALIFICATION_REQUIRED",),
    )
    monkeypatch.setattr("scripts.run_timed_backtest.preflight_bundle", lambda *_: preflight)
    assert (
        main(
            [
                "--manifest",
                "manifest.json",
                "--approval",
                "approval.json",
                "--source-policy",
                "source-policy.json",
            ]
        )
        == 0
    )
    result = json.loads(capsys.readouterr().out)
    assert result["metadata_verified"] is True
    assert result["data_qualified"] is False
    assert result["run_authorized"] is False


def test_qualification_and_matching_policy_are_strict_and_noninvented() -> None:
    qualification = {
        "schema_version": 1,
        "qualification_id": "operator-review-1",
        "reviewer": "independent-reviewer",
        "approved_at": "2026-10-14T01:00:00Z",
        "policy_registered_at": "2026-10-14T00:00:00Z",
        "manifest_sha256": "a" * 64,
        "approval_sha256": "b" * 64,
        "policy_sha256": "c" * 64,
        "matching_policy_sha256": "d" * 64,
        "evidence_sha256": {key: "e" * 64 for key in EVIDENCE_KEYS},
        "invented": False,
    }
    parsed = parse_qualification_certificate(json.dumps(qualification).encode())
    assert parsed.qualification_id == "operator-review-1" and not parsed.invented
    qualification["invented"] = True
    with pytest.raises(TimedCliError, match="INVENTED_QUALIFICATION"):
        parse_qualification_certificate(json.dumps(qualification).encode())
    policy = {
        "schema_version": 1,
        "policy_id": "source-asof-v1",
        "selection": "latest_available_observed",
        "max_age_seconds": 60,
        "registered_at": "2026-10-14T00:00:00Z",
        "source_binding": "reviewed-source-revision",
    }
    assert parse_matching_policy(json.dumps(policy).encode()).max_age == timedelta(seconds=60)
    policy["registered_at"] = "2026-10-14T00:00:00.000000999Z"
    with pytest.raises(TimedCliError, match="MATCHING_POLICY_TIME"):
        parse_matching_policy(json.dumps(policy).encode())
