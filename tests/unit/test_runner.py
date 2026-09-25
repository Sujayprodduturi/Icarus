"""The walk-forward runner — task 1.7d.

These pin the joins, not the parts: the parts have their own suites. What can only go wrong once
things are wired together is (a) the warm-up prefix leaking into the tradable region, (b) folds
being stitched by addition instead of compounding, (c) the exposure numerator being counted on a
different axis from its denominator, and (d) a run not reaching the trial ledger.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
import pytest
from tests.unit.simharness import REALISM

from icarus.common.config import load_goal
from icarus.engine import runner
from icarus.engine.backtest import Window, slice_panel
from icarus.engine.costmodel import Charges, CostModel
from icarus.engine.fills import FillModel
from icarus.engine.metrics import Metrics, SharpeEstimate
from icarus.engine.portfolio import (
    ClosedTrade,
    ExitReason,
    PortfolioDiscard,
    PortfolioOmission,
)
from icarus.engine.runner import (
    BacktestResult,
    FoldResult,
    _after_tax_curve,
    _Columns,
    _run_span,
    _session_days,
    _sessions_held,
    _stitch,
    evaluate_once,
    gate_verdict,
    read_trials,
    record_trial,
    run_walk_forward,
)
from icarus.engine.signaltest import SignalSimulator
from icarus.engine.simcore import SignalId
from icarus.engine.taxmodel import Bucket, BucketOutcome, FinancialYearTax
from icarus.strategy.dsl import Bars, Panel, StrategyCandidate, parse_strategy
from icarus.strategy.library import default_registry

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from icarus.common.config import GoalConfig

START = datetime(2024, 1, 1, tzinfo=UTC)

NO_CHARGES = Charges(
    brokerage=Decimal(0),
    stt=Decimal(0),
    exchange_txn=Decimal(0),
    sebi_fee=Decimal(0),
    gst=Decimal(0),
    stamp_duty=Decimal(0),
    dp_charge=Decimal(0),
    turnover=Decimal(0),
)

STRATEGY = """
name: runner_test
version: 1
timeframe: 1d
universe: nse_liquid
entry:
  cross_above:
    a: {sma: {n: 5}}
    b: {sma: {n: 20}}
exit:
  - stop_loss_atr: {atr_mult: 2.0}
sizing:
  risk_r: 0.005
"""


@pytest.fixture
def goal(repo_root: Path) -> GoalConfig:
    return load_goal(repo_root / "goal.yaml")


# --------------------------------------------------------------------------------------
# The warm-up prefix must feed the indicators and never open a position
# --------------------------------------------------------------------------------------


def _column_panel(size: int = 400) -> Panel:
    rng = np.random.default_rng(9)
    close = np.cumsum(rng.normal(0.0, 1.5, size)) + 300.0
    open_ = np.concatenate([close[:1], close[:-1]])
    start = np.datetime64("2015-01-01")
    bars = Bars(
        ts=np.arange(start, start + size).astype("datetime64[ns]"),
        open=open_,
        high=np.maximum(open_, close) + 1.0,
        low=np.minimum(open_, close) - 1.0,
        close=close,
        volume=np.full(size, 1_000_000.0),
    )
    return Panel.build({"AAA": bars}, {"AAA": np.ones(size, dtype=np.bool_)})


def test_evaluating_once_over_the_whole_span_is_not_look_ahead() -> None:
    """The property that replaced the warm-up prefix, and the one that makes it safe.

    Columns are now computed over the entire development span and sliced per fold, rather than
    recomputed on each fold's slice behind a lead-in. That is only legitimate because every
    primitive is causal: the value at bar *t* must be identical whether the series it was computed
    from ended at *t* or ran on for another two hundred bars. If that ever stops holding, this
    design leaks the future into every fold at once — so it is asserted here rather than assumed.
    """
    panel = _column_panel()
    strategy = parse_strategy(
        """
name: causal
version: 1
timeframe: 1d
universe: nse_liquid
entry:
  above:
    a: {rsi: {n: 14}}
    b: {constant: {value: 55.0}}
exit:
  - stop_loss_atr: {atr_mult: 2.0, atr_period: 14}
sizing:
  risk_r: 0.005
""",
        registry=default_registry(),
        max_risk_r=0.005,
    )
    whole = evaluate_once(strategy, panel, default_registry())
    cut = 250
    prefix_panel = slice_panel(panel, 0, cut)
    prefix = evaluate_once(strategy, prefix_panel, default_registry())
    for name in ("AAA",):
        a, b = whole.signals[name][:cut], prefix.signals[name]
        assert np.array_equal(np.isnan(a), np.isnan(b))
        m = ~np.isnan(a)
        assert np.allclose(a[m], b[m]), "a primitive read the future"
        a, b = whole.stops[name][:cut], prefix.stops[name]
        m = ~np.isnan(a) & ~np.isnan(b)
        assert np.allclose(a[m], b[m])


def test_a_fold_sees_only_its_own_slice_of_the_columns() -> None:
    """The other half: computing over everything must not let a fold *trade* outside its window."""
    panel = _column_panel()
    strategy = parse_strategy(
        """
name: slicing
version: 1
timeframe: 1d
universe: nse_liquid
entry: {structure_bullish: {k: 2}}
exit:
  - stop_loss_pct: {pct: 0.2}
sizing:
  risk_r: 0.005
""",
        registry=default_registry(),
        max_risk_r=0.005,
    )
    columns = evaluate_once(strategy, panel, default_registry())
    signals, stops, ranks = columns.slice(100, 160)
    assert len(signals["AAA"]) == 60
    assert len(stops["AAA"]) == 60
    assert ranks is None
    assert np.array_equal(signals["AAA"], columns.signals["AAA"][100:160], equal_nan=True)


def test_run_span_preserves_full_source_signal_identity_when_sliced(goal: GoalConfig) -> None:
    """Restarting source indices at a fold boundary would create a different signal identity."""
    panel = _column_panel(size=8)
    strategy = parse_strategy(
        """
name: source_identity
version: 1
timeframe: 1d
universe: nse_liquid
entry: {structure_bullish: {k: 2}}
exit:
  - stop_loss_pct: {pct: 0.2}
sizing:
  risk_r: 0.005
""",
        registry=default_registry(),
        max_risk_r=0.005,
    )
    columns = _Columns(
        signals={"AAA": np.array([0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0])},
        stops={"AAA": np.full(8, 10.0)},
        ranks=None,
    )
    source_indices = tuple(range(90, 98))

    whole = _run_span(strategy, panel, 0, 8, columns, goal, source_indices)
    sliced = _run_span(strategy, panel, 2, 8, columns, goal, source_indices)

    assert whole.accepted_signal_ids == sliced.accepted_signal_ids
    assert whole.accepted_signal_ids[0].decision_index == 92
    assert whole.accepted_signal_ids[0].uuid == sliced.accepted_signal_ids[0].uuid

    signal_result = SignalSimulator(
        notional_inr=Decimal(100_000),
        costs=CostModel(goal.costs),
        fills=FillModel(REALISM),
        stale_after_sessions=goal.backtest.stale_position_sessions,
    ).run(
        strategy,
        panel,
        columns.signals,
        columns.stops,
        source_indices=source_indices,
    )
    signal_ids = {
        *(trade.signal_id for trade in signal_result.trades),
        *(skipped.signal_id for skipped in signal_result.skips),
    }
    assert whole.accepted_signal_ids[0] in signal_ids


def _always_signal_strategy() -> StrategyCandidate:
    return parse_strategy(
        """
name: runner_signal_records
version: 1
timeframe: 1d
universe: nse_liquid
entry:
  above:
    a: {close: {}}
    b: {constant: {value: 0.0}}
exit:
  - stop_loss_pct: {pct: 0.2}
sizing:
  risk_r: 0.005
""",
        registry=default_registry(),
        max_risk_r=0.005,
    )


def _observation_indices(fold: FoldResult) -> set[int]:
    return {
        *(signal_id.decision_index for signal_id in fold.accepted_signal_ids),
        *(discard.signal_id.decision_index for discard in fold.portfolio_discards),
    }


def test_public_walk_forward_carries_only_test_observations_and_source_offsets(
    goal: GoalConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Copying training records or restarting IDs at a fold boundary corrupts the OOS ledger."""
    panel = _column_panel(size=8)
    windows = [Window(0, 2, 2, 5, 0), Window(0, 5, 5, 8, 0)]
    monkeypatch.setattr(runner, "walk_forward_windows", lambda *_args: windows)

    result = run_walk_forward(
        _always_signal_strategy(),
        panel,
        goal=goal,
        registry=default_registry(),
        ledger=None,
        source_indices=tuple(range(100, 108)),
    )

    assert [_observation_indices(fold) for fold in result.folds] == [
        {102, 103, 104},
        {105, 106, 107},
    ]
    assert {signal_id.decision_index for signal_id in result.oos_accepted_signal_ids} | {
        discard.signal_id.decision_index for discard in result.oos_portfolio_discards
    } == {102, 103, 104, 105, 106, 107}
    assert result.oos_emitted_signals == 6


def test_public_walk_forward_refuses_overlapping_oos_signal_ids(
    goal: GoalConfig, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Duplicate OOS records would make later trial evidence count one decision twice."""
    panel = _column_panel(size=8)
    windows = [Window(0, 2, 2, 5, 0), Window(0, 3, 3, 6, 0)]
    monkeypatch.setattr(runner, "walk_forward_windows", lambda *_args: windows)

    with pytest.raises(ValueError, match="duplicate OOS"):
        run_walk_forward(
            _always_signal_strategy(),
            panel,
            goal=goal,
            registry=default_registry(),
            ledger=None,
            source_indices=tuple(range(100, 108)),
        )


def test_portfolio_observations_propagate_as_counts_without_raw_identifiers() -> None:
    """Publishing IDs before the ledger barrier would create an unlogged per-signal artifact."""
    discarded_id = SignalId("runner_test", 1, "AAA", START, 90)
    accepted_id = SignalId("runner_test", 1, "AAA", START + timedelta(days=1), 91)
    discard = PortfolioDiscard(discarded_id, PortfolioOmission.NO_NEXT_BAR)
    fold = FoldResult(
        index=0,
        window=Window(0, 1, 1, 2, 0),
        train_from="2024-01-01",
        train_to="2024-01-01",
        test_from="2024-01-02",
        test_to="2024-01-02",
        in_sample=_metrics_stub(),
        out_of_sample=_metrics_stub(),
        trades=(),
        skipped={},
        stale_marks=0,
        stale_mark_value=Decimal(0),
        concentration_capped=0,
        unfilled_exits=0,
        ambiguous_selection_days=0,
        equity_curve=((START, Decimal(100_000)),),
        emitted_signals=2,
        accepted_signal_ids=(accepted_id,),
        portfolio_discards=(discard,),
    )
    result = BacktestResult(
        strategy="runner_test",
        folds=[fold],
        oos_emitted_signals=2,
        oos_accepted_signal_ids=[accepted_id],
        oos_portfolio_discards=[discard],
    )

    fold_json = fold.as_json()
    result_json = result.as_json()

    assert fold_json["portfolio_discard_counts"] == {"no_next_bar": 1}
    assert result_json["oos_portfolio_discard_counts"] == {"no_next_bar": 1}
    assert fold_json["accepted_signals"] == result_json["oos_accepted_signals"] == 1
    rendered = json.dumps({"fold": fold_json, "result": result_json})
    assert "portfolio_discards" not in fold_json
    assert "accepted_signal_ids" not in fold_json
    assert str(discarded_id.uuid) not in rendered
    assert str(accepted_id.uuid) not in rendered
    assert discarded_id.decision_ts.isoformat() not in rendered
    assert accepted_id.decision_ts.isoformat() not in rendered


# --------------------------------------------------------------------------------------
# Stitching compounds; it does not add
# --------------------------------------------------------------------------------------


def _metrics_stub(
    *,
    sharpe_lower: float | None = None,
    trades: int = 0,
    expectancy: float = 0.0,
    sharpe_point: float | None = None,
) -> Metrics:
    nan = float("nan")
    if sharpe_point is not None:
        sharpe = SharpeEstimate(
            sharpe_point, sharpe_point - 1.0, sharpe_point + 1.0, 1.0, trades, 0.95
        )
    elif sharpe_lower is None:
        sharpe = SharpeEstimate(nan, nan, nan, nan, 0, 0.95)
    else:
        sharpe = SharpeEstimate(
            sharpe_lower + 1.0, sharpe_lower, sharpe_lower + 2.0, 1.0, trades, 0.95
        )
    return Metrics(
        sharpe=sharpe,
        sortino=nan,
        calmar=nan,
        cagr=0.0,
        total_return=0.0,
        volatility_annual=0.0,
        max_drawdown=0.0,
        max_drawdown_days=0,
        trades=trades,
        win_rate=0.0,
        profit_factor=nan,
        expectancy_r=expectancy,
        avg_win_r=0.0,
        avg_loss_r=0.0,
        avg_holding_days=0.0,
        sessions=0,
        exposure=0.0,
    )


def _fold(index: int, values: list[float], day0: int) -> FoldResult:
    curve = tuple((START + timedelta(days=day0 + i), Decimal(str(v))) for i, v in enumerate(values))
    return FoldResult(
        index=index,
        window=None,  # type: ignore[arg-type]
        train_from="",
        train_to="",
        test_from="",
        test_to="",
        in_sample=_metrics_stub(),
        out_of_sample=_metrics_stub(),
        trades=(),
        skipped={},
        stale_marks=0,
        stale_mark_value=Decimal(0),
        concentration_capped=0,
        unfilled_exits=0,
        ambiguous_selection_days=0,
        equity_curve=curve,
    )


def test_two_folds_that_each_gained_ten_percent_compound_to_twenty_one() -> None:
    """Both folds start from 100,000 and end at 110,000. Run back to back that is 1.1 x 1.1.

    Concatenating rupee values instead would show equity falling from 110,000 back to 100,000 at
    the seam — a 9% drawdown that never happened, in every walk-forward result.
    """
    folds = [_fold(0, [100_000, 110_000], 0), _fold(1, [100_000, 110_000], 10)]
    stitched, _books = _stitch(folds)
    assert float(stitched[-1][1]) == pytest.approx(1.21)


def test_a_losing_fold_after_a_winning_one_compounds_downward() -> None:
    """+100% then -50% is exactly flat, which addition would report as +50%."""
    folds = [_fold(0, [100.0, 200.0], 0), _fold(1, [100.0, 50.0], 10)]
    assert float(_stitch(folds)[0][-1][1]) == pytest.approx(1.0)


def test_the_stitched_curve_has_one_point_per_session_after_the_first_of_each_fold() -> None:
    """Each fold's first point establishes a base and produces no return of its own."""
    folds = [_fold(0, [100.0, 101.0, 102.0], 0), _fold(1, [100.0, 101.0], 10)]
    curve, books = _stitch(folds)
    assert len(curve) == 3
    assert len(books) == 3


def test_the_book_is_the_folds_own_equity_not_the_compounded_index() -> None:
    """The denominator a rupee bill is converted against (finding F41).

    Fold 2 opens a fresh 100,000 book even though the stitched index has already reached 1.1. A
    40,000 tax bill is 40% of the account that earned it and must stay 40% — reading the index
    instead would call it 36%, and the error grows with every fold the strategy wins.
    """
    folds = [_fold(0, [100_000, 110_000], 0), _fold(1, [100_000, 110_000], 10)]
    curve, books = _stitch(folds)
    assert float(curve[-1][1]) == pytest.approx(1.21)
    assert books == [Decimal(110_000), Decimal(110_000)]


# --------------------------------------------------------------------------------------
# Exposure is counted on the session axis
# --------------------------------------------------------------------------------------


def _held(entry: datetime, exit_: datetime) -> ClosedTrade:
    return ClosedTrade(
        symbol="AAA",
        quantity=1,
        entry_ts=entry,
        entry_price=Decimal(100),
        exit_ts=exit_,
        exit_price=Decimal(100),
        reason=ExitReason.TIME_STOP,
        entry_charges=NO_CHARGES,
        exit_charges=NO_CHARGES,
        risk_per_share=Decimal(10),
    )


def test_a_weekend_inside_a_holding_period_is_not_an_exposed_session() -> None:
    """Friday to Monday is four calendar days and two sessions.

    Counting calendar days gave an exposure of 1.48 against a session denominator. The fix is to
    intersect with the run's own session axis, so a day the market was shut cannot be a day the
    strategy was exposed.
    """
    friday, monday = datetime(2024, 1, 5, tzinfo=UTC), datetime(2024, 1, 8, tzinfo=UTC)
    sessions = _session_days([(friday, Decimal(1)), (monday, Decimal(1))])
    assert _sessions_held([_held(friday, monday)], sessions) == 2


def test_two_positions_open_on_one_day_count_as_one_exposed_session() -> None:
    """Exposure asks whether the strategy was in the market, not in how many ways."""
    day = datetime(2024, 1, 5, tzinfo=UTC)
    sessions = _session_days([(day, Decimal(1))])
    assert _sessions_held([_held(day, day), _held(day, day)], sessions) == 1


# --------------------------------------------------------------------------------------
# The trial ledger (invariant #24)
# --------------------------------------------------------------------------------------


def _result() -> BacktestResult:
    return BacktestResult(strategy="runner_test", folds=[], oos=None, oos_trades=[])


def test_a_run_appends_to_the_ledger_rather_than_replacing_it(tmp_path: Path) -> None:
    """The count is the whole point. Two runs of the same strategy are two trials, not one:
    re-running after a tweak is exactly the search DSR has to correct for."""
    strategy = parse_strategy(STRATEGY, registry=default_registry(), max_risk_r=0.005)
    path = tmp_path / "trials.json"
    assert record_trial(path, strategy, _result(), origin="operator") == 1
    assert record_trial(path, strategy, _result(), origin="operator") == 2
    assert len(read_trials(path)) == 2


def test_the_ledger_records_the_sharpe_the_gate_actually_judges(tmp_path: Path) -> None:
    """Finding F43. The ledger wrote only the pre-tax Sharpe while the gate moved to the after-tax
    one, so the DSR correction in 1.9 — which reads this file — and the promotion decision it
    exists to correct would have been computed on two different quantities.

    Both are recorded, and they are asserted to be *different* here: a mutation that pointed the
    new field back at the pre-tax record would otherwise pass unnoticed.
    """
    strategy = parse_strategy(STRATEGY, registry=default_registry(), max_risk_r=0.005)
    path = tmp_path / "trials.json"
    result = BacktestResult(
        strategy="probe",
        oos=_metrics_stub(sharpe_point=2.0),
        oos_after_tax=_metrics_stub(sharpe_point=1.0),
    )
    record_trial(path, strategy, result, origin="operator")
    entry = read_trials(path)[0]
    assert entry["oos_sharpe"] == 2.0
    assert entry["oos_sharpe_after_tax"] == 1.0


def test_a_human_run_is_recorded_with_the_same_weight_as_an_inventor_run(tmp_path: Path) -> None:
    """Phase 1's only searcher is the operator. A ledger counting only machine candidates would
    be blind during exactly the phase it exists to protect."""
    strategy = parse_strategy(STRATEGY, registry=default_registry(), max_risk_r=0.005)
    path = tmp_path / "trials.json"
    record_trial(path, strategy, _result(), origin="operator")
    record_trial(path, strategy, _result(), origin="inventor")
    origins = [t["origin"] for t in read_trials(path)]
    assert origins == ["operator", "inventor"]
    assert len(read_trials(path)) == 2


def test_an_unreadable_ledger_raises_rather_than_starting_a_fresh_one(tmp_path: Path) -> None:
    """Silently starting over would reset the lifetime trial count to zero and make every DSR
    figure computed afterwards too generous."""
    path = tmp_path / "trials.json"
    path.write_text(json.dumps({"schema": 99, "trials": []}), encoding="utf-8")
    with pytest.raises(Exception, match="schema"):
        read_trials(path)


def test_a_missing_ledger_is_an_empty_history_not_an_error(tmp_path: Path) -> None:
    assert read_trials(tmp_path / "nope.json") == []


def test_the_recorded_trial_names_the_primitives_that_were_searched(tmp_path: Path) -> None:
    """The effective trial count depends on how *similar* the things tried were; two runs of the
    same primitives are closer to one trial than two, and 1.9b needs the vocabulary to judge it."""
    strategy = parse_strategy(STRATEGY, registry=default_registry(), max_risk_r=0.005)
    path = tmp_path / "trials.json"
    record_trial(path, strategy, _result(), origin="operator")
    assert "sma" in read_trials(path)[0]["primitives"]  # type: ignore[operator]


def test_the_ledger_survives_a_date_change(tmp_path: Path) -> None:
    """Entries carry their own timestamp, so the ledger is a record and not a snapshot."""
    strategy = parse_strategy(STRATEGY, registry=default_registry(), max_risk_r=0.005)
    path = tmp_path / "trials.json"
    record_trial(path, strategy, _result(), origin="operator")
    stamped = str(read_trials(path)[0]["at"])
    assert date.fromisoformat(stamped[:10]) <= datetime.now(UTC).date()


# --------------------------------------------------------------------------------------
# The gate reads after tax (finding F38)
# --------------------------------------------------------------------------------------


def _fy_tax(year: int, total: Decimal) -> FinancialYearTax:
    """A financial-year bill of exactly ``total``, expressed as a single non-speculative bucket."""
    return FinancialYearTax(
        fy_start_year=year,
        buckets=(
            BucketOutcome(
                bucket=Bucket.NONSPECULATIVE,
                net_pnl=total,
                loss_absorbed=Decimal(0),
                exempt=Decimal(0),
                taxable=total,
                tax=total,
                loss_carried_out=Decimal(0),
            ),
        ),
        cess=Decimal(0),
    )


def _fy_curve(years: int = 3) -> list[tuple[datetime, Decimal]]:
    """A flat index of 1.0, one point per month, spanning several financial years."""
    out, ts = [], datetime(2026, 4, 1, tzinfo=UTC)
    for i in range(years * 12):
        out.append((ts.replace(year=2026 + (i // 12), month=(i % 12) + 1), Decimal(1)))
    return out


def _books(curve: Sequence[tuple[datetime, Decimal]], each: int = 100_000) -> list[Decimal]:
    """The fold-local rupee book at every point — a flat 100,000 unless a test says otherwise."""
    return [Decimal(each)] * len(curve)


def test_tax_lands_in_one_step_not_smeared_across_sessions() -> None:
    """Tax is annual on the aggregate — that is why the model consumes a ledger and returns one
    bill per year. Spreading it would invent a liability that existed on none of those days."""
    curve = _fy_curve(1)
    after = _after_tax_curve(curve, _books(curve), [_fy_tax(2026, Decimal(10_000))])
    assert {a[1] for a in after} == {Decimal(1), Decimal("0.9")}, "one step, not a slope"
    assert all(a[1] == Decimal(1) for a in after[:-1])


def test_the_last_financial_years_bill_is_not_silently_discarded() -> None:
    """The bill lands **on** the session it falls due, not on the one after it.

    The first version appended the point and only then applied the bill, so a bill at index *i*
    reduced *i+1* onward. The last financial year's last session is by definition the final index,
    so its bill — with the shipped config, roughly a ninth of the total — hit nothing at all and
    vanished from ``oos_after_tax``, the record the gate reads. The sheet then printed a different
    after-tax P&L from the full bill a few lines below, and the two disagreed.
    """
    curve = _fy_curve(1)
    after = _after_tax_curve(curve, _books(curve), [_fy_tax(2026, Decimal(10_000))])
    assert after[-1][1] == Decimal("0.9"), "the final year's tax was thrown away"


def test_the_bill_reduces_everything_after_it_and_compounds() -> None:
    """Money paid to the tax office is not available to trade with afterwards."""
    curve = [
        (datetime(2026, 6, 1, tzinfo=UTC), Decimal(1)),
        (datetime(2027, 3, 31, tzinfo=UTC), Decimal(1)),
        (datetime(2027, 6, 1, tzinfo=UTC), Decimal(1)),
    ]
    after = _after_tax_curve(curve, _books(curve), [_fy_tax(2026, Decimal(10_000))])
    assert after[0][1] == Decimal(1)
    assert after[1][1] == Decimal("0.9")  # the bill settles ON the last session of the FY
    assert after[2][1] == Decimal("0.9")  # and stays paid


def test_the_bill_is_a_share_of_the_book_that_earned_it_not_of_the_index() -> None:
    """Finding F41 — and the error always flattered the strategy.

    The bill was divided by ``starting_equity x index``. Folds restart the book at
    ``starting_equity``, so once the stitched index reached 4.0 a bill worth 40% of the account
    that earned it was charged as 10%. Tax drag was understated in direct proportion to how well
    the strategy had compounded, on the number the gate reads.
    """
    curve = [(datetime(2027, 3, 31, tzinfo=UTC), Decimal(4))]  # index has quadrupled
    after = _after_tax_curve(curve, _books(curve), [_fy_tax(2026, Decimal(40_000))])
    # 40,000 of a 100,000 book is 40%, whatever the index says: 4.0 x 0.6.
    assert after[0][1] == Decimal("2.4")


def test_a_tax_year_with_no_session_on_the_curve_is_refused() -> None:
    """Fail loud rather than absorb (invariant #10).

    ``_stitch`` drops each fold's opening bar, so a financial year whose only trade exited on one
    of those has no representative point. The bill was previously dropped in silence, leaving the
    sheet showing two after-tax numbers that did not agree and no indication which was wrong.
    """
    curve = _fy_curve(1)  # FY2026 only
    with pytest.raises(ValueError, match="no session in those years"):
        _after_tax_curve(curve, _books(curve), [_fy_tax(2030, Decimal(10_000))])


def test_no_tax_means_the_curve_is_untouched() -> None:
    curve = _fy_curve(2)
    assert _after_tax_curve(curve, _books(curve), []) == list(curve)


def test_the_after_tax_record_is_never_better_than_the_pre_tax_one() -> None:
    """The property that matters, whatever the shape of the bill: tax cannot help."""
    curve = _fy_curve(3)
    years = [_fy_tax(2026, Decimal(5_000)), _fy_tax(2027, Decimal(7_000))]
    after = _after_tax_curve(curve, _books(curve), years)
    assert all(b[1] <= a[1] for a, b in zip(curve, after, strict=True))


def _pnl_trade(pnl: int) -> ClosedTrade:
    """One closed trade worth exactly ``pnl`` rupees, charges zeroed."""
    return ClosedTrade(
        symbol="AAA",
        quantity=1,
        entry_ts=START,
        entry_price=Decimal(100),
        exit_ts=START + timedelta(days=1),
        exit_price=Decimal(100 + pnl),
        reason=ExitReason.TIME_STOP,
        entry_charges=NO_CHARGES,
        exit_charges=NO_CHARGES,
        risk_per_share=Decimal(10),
    )


def _gate_input(
    sharpe_lower: float,
    trades: int,
    expectancy: float,
    *,
    gross: int = 10_000,
    tax: int = 1_000,
) -> BacktestResult:
    """A result whose PRE-tax record is deliberately excellent and post-tax record is the one
    under test — so a gate reading the wrong field passes when it should fail."""
    good = _metrics_stub(sharpe_lower=5.0, trades=10_000, expectancy=9.0)
    tested = _metrics_stub(sharpe_lower=sharpe_lower, trades=trades, expectancy=expectancy)
    return BacktestResult(
        strategy="probe",
        oos=good,
        oos_after_tax=tested,
        oos_trades=[_pnl_trade(gross)],
        tax_total=Decimal(tax),
    )


def test_the_gate_reads_the_after_tax_record(goal: GoalConfig) -> None:
    """The most consequential decision in Phase 1 — does this strategy get money — had no test.

    It was three lines inside a print loop, and a mutation pointing it at the pre-tax record
    passed the entire suite (finding F38). The pre-tax figures here are deliberately superb, so
    reading the wrong field flips the verdict.
    """
    verdict, checks = gate_verdict(_gate_input(-1.0, 10_000, 9.0), goal)
    assert verdict == "FAIL"
    assert checks[0][1] is False, "the Sharpe check must read the after-tax lower bound"


def test_the_gate_passes_only_when_every_check_passes(goal: GoalConfig) -> None:
    assert gate_verdict(_gate_input(0.5, 10_000, 1.0), goal)[0] == "PASS"
    assert gate_verdict(_gate_input(0.5, 1, 1.0), goal)[0] == "FAIL"  # too few trades
    assert gate_verdict(_gate_input(0.5, 10_000, -0.1), goal)[0] == "FAIL"  # negative expectancy


def test_a_strategy_profitable_before_tax_and_not_after_it_is_refused(goal: GoalConfig) -> None:
    """Finding F42 — F38 surviving inside its own fix.

    ``expectancy_r``, ``win_rate`` and ``trades`` are derived from the trade *ledger*, and tax
    never touches a trade, so ``oos_after_tax.expectancy_r`` is identical to the pre-tax figure by
    construction. Two of the three checks under the AFTER TAX heading were therefore pre-tax, and a
    strategy that earned 10,000 and owed 12,000 passed on a positive expectancy it no longer had.

    Tax cannot honestly be attributed to individual trades — it is annual, on the aggregate, with
    set-off between buckets — so the aggregate is checked as an aggregate instead of inventing a
    per-trade number.
    """
    passes = _gate_input(0.5, 10_000, 1.0, gross=10_000, tax=1_000)
    assert gate_verdict(passes, goal)[0] == "PASS"

    eaten = _gate_input(0.5, 10_000, 1.0, gross=10_000, tax=12_000)
    verdict, checks = gate_verdict(eaten, goal)
    assert verdict == "FAIL"
    assert dict(checks)["P&L after tax > 0"] is False
    assert dict(checks)["expectancy > 0R (before tax)"] is True, (
        "the pre-tax check is still true — which is exactly why it cannot be the only one, and "
        "why its label has to say 'before tax'"
    )


def test_a_run_with_no_after_tax_record_is_not_silently_a_pass(goal: GoalConfig) -> None:
    verdict, checks = gate_verdict(BacktestResult(strategy="probe"), goal)
    assert verdict == "NO RESULT"
    assert checks == []
