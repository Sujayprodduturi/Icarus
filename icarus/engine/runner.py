"""Walk-forward runner: strategy + panel -> a metric sheet (task 1.7d, PRD §30-31).

The piece that was missing. Every part it calls was already built and unit-tested against
hand-made arrays — the fill model, the portfolio simulator, the window arithmetic, 223 DSL
words — and not one of them had ever seen a real NSE price. This joins them and runs them over
the development span.

**What it does per fold.** Evaluate the strategy matrix-wise once over the whole development span,
slice the resulting signal/stop/rank columns to the fold's window, hand those to the portfolio
simulator, and keep the trades. Folds are then stitched into one continuous out-of-sample record.

**There is no warm-up prefix, because there is no slicing before evaluation.** The strategy is
evaluated **once, over the whole development span**, and each fold slices the resulting columns.
That is what a live system has on the morning it starts — all the history there is — and it is
not look-ahead, because every primitive is causal, so bar *t* holds the same value whether it was
computed from ``[0..t]`` or from the whole series. The previous design gave each fold a lead-in of
``longest_lookback`` sessions, which is right for an average and wrong for anything recursive: a
Wilder-smoothed word needs about twenty times its own window to agree with full history, and
``rsi(200)`` needs more sessions than this panel contains, so no lead-in was both sufficient and
affordable (finding F29). See :func:`evaluate_once`.

**Stitching compounds returns, it does not add rupees.** Each fold starts from the same nominal
equity, so concatenating the curves would show a sawtooth. Compounding the per-session returns
gives the curve the strategy would have produced had it run continuously, which is the thing the
Sharpe and drawdown of the whole record should describe.

**Every run is a trial** (invariant #24). :func:`record_trial` appends to an append-only ledger
before the result is returned, whether the run was launched by the Inventor or by a human trying
one more idea. DSR corrects for multiple testing using the effective trial count, and a ledger
that counts only machine-generated candidates is blind during Phase 1 — when the operator is the
only searcher and therefore the only source of overfitting.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from icarus.agents.data.cache import write_atomic_json
from icarus.common.logging import get_logger
from icarus.engine.backtest import (
    assert_no_lockbox_overlap,
    assert_panel_stops_before_lockbox,
    longest_lookback,
    slice_panel,
    walk_forward_windows,
)
from icarus.engine.costmodel import CostModel, Segment
from icarus.engine.fills import FillModel
from icarus.engine.metrics import Metrics, summarise
from icarus.engine.portfolio import (
    ClosedTrade,
    PortfolioSimulator,
    RunResult,
    stop_distance_from_exits,
)
from icarus.engine.taxmodel import RealizedTrade, TaxModel, financial_year
from icarus.strategy.dsl import DslError, evaluate_universe
from icarus.strategy.library import _ops

if TYPE_CHECKING:
    from collections.abc import Sequence

    from icarus.common.config import GoalConfig
    from icarus.engine.backtest import Window
    from icarus.engine.taxmodel import FinancialYearTax
    from icarus.strategy.dsl import Panel, Registry, StrategyCandidate

log = get_logger("engine.runner")

DEFAULT_TRIAL_LEDGER = Path("var/trial_ledger.json")
_LEDGER_SCHEMA = 1

Column = npt.NDArray[np.float64]


@dataclass(frozen=True, slots=True)
class FoldResult:
    """One walk-forward fold: what it looked like in training, and what it did out of sample."""

    index: int
    window: Window
    train_from: str
    train_to: str
    test_from: str
    test_to: str
    in_sample: Metrics
    out_of_sample: Metrics
    trades: tuple[ClosedTrade, ...]
    skipped: dict[str, int]
    stale_marks: int
    stale_mark_value: Decimal
    """Positions closed at a price nobody quoted, and the gross rupees involved.

    On the sheet beside the metrics rather than buried, because they are the part of the result the
    operator has to take on trust: nothing traded at that price, it was carried from the last bar
    the symbol printed (finding F4)."""

    unfilled_exits: int
    """Exits the fill model refused or capped mid-run, leaving the position open and still exposed.

    Surfaced for the same reason as the marks: it was being counted and then never shown, so a run
    could reassure the operator that nothing was assumed while capital had been left exposed by an
    exit that silently did not happen."""

    equity_curve: tuple[tuple[datetime, Decimal], ...]
    """The fold's own out-of-sample curve, kept so the folds can be stitched into one continuous
    record afterwards. A summary cannot be un-summarised."""

    def as_json(self) -> dict[str, object]:
        return {
            "fold": self.index,
            "train": f"{self.train_from}..{self.train_to}",
            "test": f"{self.test_from}..{self.test_to}",
            "purge_sessions": self.window.purge_sessions,
            "embargo_sessions": self.window.embargo_sessions,
            "in_sample": self.in_sample.as_json(),
            "out_of_sample": self.out_of_sample.as_json(),
            "skipped": self.skipped,
            "stale_marks": self.stale_marks,
            "stale_mark_value": str(self.stale_mark_value),
            "unfilled_exits": self.unfilled_exits,
        }


@dataclass
class BacktestResult:
    """The whole walk-forward record for one strategy."""

    strategy: str
    folds: list[FoldResult] = field(default_factory=list)
    oos: Metrics | None = None
    oos_after_tax: Metrics | None = None
    """The same record with each year's tax bill deducted on the day it falls due.

    **This is what the stop gate reads**, from 2026-08-16. `stop_gate.net_of_cost_and_tax` had been
    asserted `True` by the loader since the gate was written, with the message "gross-only metrics
    are a bug", and was read by no code: the gate tested Sharpe, trade count and expectancy off a
    curve net of **costs only**, while tax was computed afterwards and printed as an informational
    line (finding F38). CLAUDE.md §5 requires cost *and tax* inside every backtest and invariant #21
    gates on alpha after both.

    Tax is annual on the aggregate, so it cannot be spread across sessions without inventing a
    liability that never existed. It is deducted in one step at the last session of each financial
    year — which is lumpy, and is lumpy in reality too. The pre-tax record stays beside it so the
    drag is visible rather than absorbed."""

    oos_trades: list[ClosedTrade] = field(default_factory=list)
    tax_years: list[FinancialYearTax] = field(default_factory=list)
    tax_total: Decimal = Decimal(0)
    sharpe_decay: float = float("nan")

    def as_json(self) -> dict[str, object]:
        return {
            "strategy": self.strategy,
            "folds": [f.as_json() for f in self.folds],
            "out_of_sample_stitched": self.oos.as_json() if self.oos else None,
            "sharpe_decay_is_to_oos": round(self.sharpe_decay, 3),
            "out_of_sample_after_tax": (
                self.oos_after_tax.as_json() if self.oos_after_tax else None
            ),
            "tax_total_inr": float(self.tax_total),
            "tax_by_year": [
                {"fy": t.fy_start_year, "tax_inr": float(t.total_tax)} for t in self.tax_years
            ],
        }


def run_walk_forward(
    strategy: StrategyCandidate,
    panel: Panel,
    *,
    goal: GoalConfig,
    registry: Registry,
    ledger: Path | None = DEFAULT_TRIAL_LEDGER,
) -> BacktestResult:
    """Run every walk-forward fold and stitch the out-of-sample record.

    The lockbox is unreachable from here, checked three ways: the panel may not contain it at all
    (:func:`assert_panel_stops_before_lockbox`), :func:`walk_forward_windows` stops short of it,
    and :func:`assert_no_lockbox_overlap` checks the windows from the other direction. All three,
    because an overlap turns the held-out slice into training data and leaves no trace in any
    metric — there is no number afterwards that looks wrong.
    """
    # The panel first, then the windows. `evaluate_once` runs the strategy over everything the
    # panel contains, so a panel that includes the lockbox puts it in reach however careful the
    # window arithmetic is (invariant #26).
    assert_panel_stops_before_lockbox(panel, goal.data_split)
    windows = walk_forward_windows(panel, strategy, goal.backtest, goal.data_split)
    assert_no_lockbox_overlap(windows, panel, goal.data_split)
    if not windows:
        raise DslError(
            f"no walk-forward folds fit {strategy.name} on this panel: "
            f"{len(panel)} sessions against a {goal.backtest.min_train_years}-year minimum train "
            f"plus a {longest_lookback(strategy)}-session purge"
        )

    result = BacktestResult(strategy=strategy.name)
    # Once, over the whole span, rather than per fold over a slice with a lead-in in front of it.
    # See `evaluate_once` for why the lead-in could not be made large enough to be honest.
    columns = evaluate_once(strategy, panel, registry)
    dates = [str(t)[:10] for t in panel.ts]

    for i, window in enumerate(windows):
        train = _run_span(strategy, panel, window.train_start, window.train_end, columns, goal)
        test = _run_span(strategy, panel, window.test_start, window.test_end, columns, goal)
        result.folds.append(
            FoldResult(
                index=i,
                window=window,
                train_from=dates[window.train_start],
                train_to=dates[window.train_end - 1],
                test_from=dates[window.test_start],
                test_to=dates[window.test_end - 1],
                in_sample=_metrics(train, goal),
                out_of_sample=_metrics(test, goal),
                trades=tuple(test.trades),
                skipped={k.value: v for k, v in test.skipped.items()},
                stale_marks=test.stale_marks,
                stale_mark_value=test.stale_mark_value,
                unfilled_exits=test.unfilled_exits,
                equity_curve=tuple(test.equity),
            )
        )
        log.info(
            "fold complete",
            fold=i,
            test=f"{dates[window.test_start]}..{dates[window.test_end - 1]}",
            trades=len(test.trades),
            oos_sharpe=round(result.folds[-1].out_of_sample.sharpe.point, 2),
        )

    result.oos_trades = [t for fold in result.folds for t in fold.trades]
    stitched, books = _stitch(result.folds)
    result.oos = summarise(
        stitched,
        result.oos_trades,
        confidence_level=goal.stop_gate.sharpe_confidence_level,
        sessions_open=_sessions_held(result.oos_trades, _session_days(stitched)),
    )
    result.sharpe_decay = _decay_across_folds(result.folds)
    result.tax_years, result.tax_total = _tax(result.oos_trades, goal)
    after_tax = _after_tax_curve(stitched, books, result.tax_years)
    result.oos_after_tax = summarise(
        after_tax,
        result.oos_trades,
        confidence_level=goal.stop_gate.sharpe_confidence_level,
        sessions_open=_sessions_held(result.oos_trades, _session_days(after_tax)),
    )

    if ledger is not None:
        record_trial(ledger, strategy, result, origin="operator")
    return result


# --------------------------------------------------------------------------------------
# One span
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _Columns:
    """The strategy evaluated once, over the whole development span."""

    signals: dict[str, Column]
    stops: dict[str, Column]
    ranks: dict[str, Column] | None

    def slice(
        self, start: int, end: int
    ) -> tuple[dict[str, Column], dict[str, Column], dict[str, Column] | None]:
        return (
            {s: c[start:end] for s, c in self.signals.items()},
            {s: c[start:end] for s, c in self.stops.items()},
            None if self.ranks is None else {s: c[start:end] for s, c in self.ranks.items()},
        )


def evaluate_once(strategy: StrategyCandidate, panel: Panel, registry: Registry) -> _Columns:
    """Compute every column the simulator needs, over the full development history.

    **This replaces the warm-up prefix, and it is not an optimisation — it is the only correct
    version.** Each fold used to be evaluated on its own slice, preceded by ``longest_lookback``
    sessions of lead-in, on the reasoning that a 200-session average needs 200 sessions. That is
    true of an average and false of everything recursive: measured against full history, a
    Wilder-smoothed word needs roughly **twenty times** its own window before it agrees, so
    ``rsi(14)`` given fourteen sessions was **32% out** on the first bar of every span and ``macd``
    41% out. Worse, the error has no fix by enlargement — ``rsi(200)`` needs more sessions than
    this panel contains, so no multiplier exists that is both sufficient and affordable
    (finding F29).

    Evaluating over the whole span removes the approximation instead of tuning it. **It is not
    look-ahead**: every primitive is causal — proved by ``test_no_primitive_sees_the_future`` — so
    the value at bar *t* is identical whether it was computed from ``[0..t]`` or from the whole
    series. What changes is that the earlier bars are no longer *missing*, which is exactly the
    state a live system is in: on the morning it starts it has all the history there is.

    **The lockbox is kept out of reach by refusing the panel, not by trusting causality.** Removing
    the per-fold slicing removed the property that made the future *absent* from the array the DSL
    ever saw, leaving causality as the only defence — true, and tested, but a property of 223 words
    rather than of the data. :func:`~icarus.engine.backtest.assert_no_lockbox_overlap` therefore
    rejects a panel that reaches past ``lockbox_start`` before this is ever called (invariant #26).

    It is also cheaper: one evaluation instead of two per fold.
    """
    return _Columns(
        signals=evaluate_universe(strategy.entry, panel, registry),
        stops=_stops(strategy, panel),
        ranks=(
            evaluate_universe(strategy.rank_by, panel, registry)
            if strategy.rank_by is not None
            else None
        ),
    )


def _run_span(
    strategy: StrategyCandidate,
    panel: Panel,
    start: int,
    end: int,
    columns: _Columns,
    goal: GoalConfig,
) -> RunResult:
    """Simulate ``[start, end)`` against columns already computed over the whole span."""
    window = slice_panel(panel, start, end)
    signals, stops, ranks = columns.slice(start, end)

    simulator = PortfolioSimulator(
        risk=goal.risk,
        costs=CostModel(goal.costs),
        fills=FillModel(goal.execution_realism),
        segment=Segment.EQUITY_DELIVERY,
        stale_after_sessions=goal.backtest.stale_position_sessions,
    )
    run = simulator.run(
        strategy,
        window,
        signals,
        stops,
        # `str` first: Decimal(100000.10) is 100000.0999999999985448... and this seeds the
        # whole money ledger. costmodel and taxmodel both use the same guard.
        starting_equity=Decimal(str(goal.backtest.starting_equity_inr)),
        ranks=ranks,
    )
    return run


def _stops(strategy: StrategyCandidate, panel: Panel) -> dict[str, Column]:
    """Per-share stop distance for every symbol, from the strategy's own protective exit."""
    period = _atr_period(strategy)
    out: dict[str, Column] = {}
    for i, symbol in enumerate(panel.symbols):
        bars = panel.bars[i]
        out[symbol] = stop_distance_from_exits(
            strategy.exits,
            atr=_ops.atr(bars.high, bars.low, bars.close, period),
            close=bars.close,
        )
    return out


def _atr_period(strategy: StrategyCandidate) -> int:
    """The ATR period the strategy's own stop asked for, defaulting to the DSL's 14.

    Read from the rule rather than fixed here: a strategy that declares ``atr_period: 30`` and is
    then stopped on a 14-period ATR is being risk-managed by a number it never chose.
    """
    for rule in strategy.exits:
        if rule.rule in ("stop_loss_atr", "trailing_stop_atr"):
            return int(rule.literals.get("atr_period", 14))
    return 14


# --------------------------------------------------------------------------------------
# Stitching, metrics, tax
# --------------------------------------------------------------------------------------


def _metrics(run: RunResult, goal: GoalConfig) -> Metrics:
    return summarise(
        run.equity,
        run.trades,
        confidence_level=goal.stop_gate.sharpe_confidence_level,
        sessions_open=_sessions_held(run.trades, _session_days(run.equity)),
    )


def _session_days(equity: Sequence[tuple[datetime, Decimal]]) -> frozenset[int]:
    """The trading days the run covered, as ordinals — the exposure denominator's own dates."""
    return frozenset(ts.date().toordinal() for ts, _ in equity)


def _sessions_held(trades: Sequence[ClosedTrade], sessions: frozenset[int]) -> int:
    """How many *sessions* held at least one open position — the exposure numerator.

    Intersected with the run's own session days, not merely counted. Walking the calendar between
    entry and exit sweeps up weekends and holidays, and dividing that by a count of sessions gave
    an exposure of 1.48 — a fraction above one, which is how the bug announced itself. Anything
    below about 1.45 would have looked entirely plausible and been just as wrong.

    Days, not bar indices: two positions open on the same day count once, because exposure asks
    "was I in the market", not "in how many ways".
    """
    days: set[int] = set()
    for trade in trades:
        first, last = trade.entry_ts.date().toordinal(), trade.exit_ts.date().toordinal()
        days.update(range(first, last + 1))
    return len(days & sessions)


def gate_verdict(result: BacktestResult, goal: GoalConfig) -> tuple[str, list[tuple[str, bool]]]:
    """PASS or FAIL against the pre-registered gate, and every check that produced it.

    Lifted out of the metric-sheet printer on 2026-08-16. It had been three lines inside a
    ``print`` loop, which meant the single most consequential decision in Phase 1 — does this
    strategy get money — was the only logic in the engine with no test at all. A mutation pointing
    it at the pre-tax record passed the whole suite.

    Reads :attr:`BacktestResult.oos_after_tax`, because ``stop_gate.net_of_cost_and_tax`` says so
    and, until this was written, nothing did (finding F38).

    **Only the curve-derived checks are after tax, and the labels now say which are not.** The
    first version of this function read ``oos_after_tax`` and stopped there, under a heading that
    said AFTER TAX — but :func:`~icarus.engine.metrics.summarise` derives ``expectancy_r``,
    ``win_rate`` and ``trades`` from the *trade ledger*, and tax never touches a trade. So
    ``oos_after_tax.expectancy_r`` was identical to the pre-tax figure, and a strategy at +0.03R
    before tax and negative after it passed an "expectancy > 0R" check labelled after-tax. That is
    F38 surviving inside its own fix (finding F42).

    Tax cannot honestly be attributed to individual trades — it is annual, on the aggregate, with
    set-off rules between buckets — so no per-trade after-tax expectancy is invented here. The
    pre-tax check keeps its pre-registered form and is labelled truthfully, and the aggregate it
    could not see is added as a check of its own. That makes the gate strictly harder to pass,
    which is the only direction it may be moved once results exist (invariant #25).
    """
    metrics = result.oos_after_tax
    if metrics is None:
        return "NO RESULT", []
    bound = goal.stop_gate.require_sharpe_lower_bound_above
    promote = goal.stop_gate.trade_count_promote
    after_tax_pnl = sum((t.net_pnl for t in result.oos_trades), Decimal(0)) - result.tax_total
    checks = [
        (
            f"Sharpe lower bound > {bound} (after tax)",
            metrics.sharpe.is_estimable and metrics.sharpe.lower > bound,
        ),
        (f"trades >= {promote}", metrics.trades >= promote),
        ("expectancy > 0R (before tax)", metrics.expectancy_r > 0),
        ("P&L after tax > 0", after_tax_pnl > 0),
    ]
    return ("PASS" if all(ok for _, ok in checks) else "FAIL"), checks


def _after_tax_curve(
    curve: Sequence[tuple[datetime, Decimal]],
    books: Sequence[Decimal],
    years: Sequence[FinancialYearTax],
) -> list[tuple[datetime, Decimal]]:
    """The stitched curve with each year's tax deducted on the session it falls due.

    **Tax cannot be spread across sessions.** It is annual on the aggregate — that is the whole
    reason ``taxmodel`` consumes a ledger and returns one bill per year — so smoothing it into a
    per-session drag would invent a liability that never existed on any of those days. It lands in
    one step at the last session of the financial year, which is lumpy, and is lumpy in a real
    account too.

    The curve is a **return index anchored at 1.0**, not rupees, so a rupee bill has to be
    converted where it lands. It is converted against ``books[i]`` — the fold-local rupee account
    the trades were actually sized against — and **not** against ``starting_equity x index``. The
    first version did the latter, which understated the drag by exactly the compounding factor: a
    ₹40,000 bill earned on a ₹1,00,000 book is 40% of it, but once the stitched index reached 4.0
    it was being charged as 10%. The error flattered the strategy in direct proportion to how well
    it had compounded, and it landed on the number the gate reads (finding F41).

    The deduction is applied to the session it falls due on, **before** that point is emitted. The
    first version appended first, so a bill only bit from the *next* session onward — and since the
    last financial year's last session is the final point of the curve, its bill hit nothing at all
    and silently vanished from the gated metrics.
    """
    if not curve or not years:
        return list(curve)
    due = {y.fy_start_year: y.total_tax for y in years}
    # Last index wins, so this ends up holding the final session of each financial year.
    last_session_of = {financial_year(ts): i for i, (ts, _v) in enumerate(curve)}
    # Fail loud rather than absorb (invariant #10). `_stitch` drops each fold's opening bar, so a
    # financial year whose only trade exited on one of those has no representative point on the
    # curve — and its bill would otherwise be dropped here with nothing said, leaving the sheet
    # showing two after-tax numbers that disagree.
    orphaned = sorted(set(due) - set(last_session_of))
    if orphaned:
        raise ValueError(
            f"tax is due for FY {orphaned} but the stitched curve has no session in those years, "
            f"so {sum(due[fy] for fy in orphaned)} rupees of tax would go uncharged — refusing to "
            f"report an after-tax curve that is missing part of the tax"
        )
    bill_at = {i: due[fy] for fy, i in last_session_of.items() if fy in due}

    out: list[tuple[datetime, Decimal]] = []
    carry = Decimal(1)
    for i, (ts, value) in enumerate(curve):
        bill = bill_at.get(i, Decimal(0))
        if bill > 0 and books[i] > 0:
            carry *= max(Decimal(0), (books[i] - bill) / books[i])
        out.append((ts, value * carry))
    return out


def _stitch(folds: Sequence[FoldResult]) -> tuple[list[tuple[datetime, Decimal]], list[Decimal]]:
    """One continuous equity curve from the folds' out-of-sample curves, by compounding returns.

    Folds each restart from the same nominal equity, so concatenating rupee values would produce a
    sawtooth — and a drawdown statistic measuring the resets rather than the strategy. Compounding
    the per-session returns gives the curve the strategy would have had running continuously,
    which is what the stitched Sharpe and drawdown are meant to describe.

    Anchored at 1.0 rather than at the starting equity: this curve is a return series, and giving
    it a rupee scale it never had would invite it to be read as a P&L.

    Returns the **fold-local rupee book** alongside it, one entry per curve point. That is the
    account the trades of that session were actually sized against, and it is not
    ``starting_equity x index``: the index compounds across folds while the simulated book resets
    to ``starting_equity`` at the start of each one. Anything that has to convert rupees into a
    fraction of the account — the tax bill, so far — needs the book that earned them, not the
    counterfactual compounded one (finding F41).
    """
    curve: list[tuple[datetime, Decimal]] = []
    books: list[Decimal] = []
    equity = Decimal(1)
    for fold in folds:
        previous: Decimal | None = None
        for ts, value in fold.equity_curve:
            if previous is not None and previous > 0:
                equity *= value / previous
                curve.append((ts, equity))
                books.append(value)
            previous = value
    return curve, books


def _decay_across_folds(folds: Sequence[FoldResult]) -> float:
    """How much of the average in-sample Sharpe survived out of sample.

    Averaged across folds rather than taken from one, because a single fold's decay is as noisy as
    a single fold's Sharpe. Folds whose Sharpe was not estimable at all are skipped rather than
    counted as zero — too few observations is not the same as no edge.
    """
    pairs = [
        (f.in_sample.sharpe.point, f.out_of_sample.sharpe.point)
        for f in folds
        if f.in_sample.sharpe.is_estimable and f.out_of_sample.sharpe.is_estimable
    ]
    if not pairs:
        return float("nan")
    mean_is = float(np.mean([p for p, _ in pairs]))
    mean_oos = float(np.mean([o for _, o in pairs]))
    if mean_is <= 0:
        return float("nan")
    return mean_oos / mean_is


def _tax(trades: Sequence[ClosedTrade], goal: GoalConfig) -> tuple[list[FinancialYearTax], Decimal]:
    """The tax bill on the out-of-sample trade ledger, by financial year.

    Delivery equity, so the bucket is capital gains: short-term below
    ``tax.ltcg_holding_months``, long-term above. Applied to the trade ledger rather than to the
    equity curve because tax is settled annually on realised gains — spreading it across sessions
    would invent a daily liability that never existed, and netting it into each trade would deny
    the set-off rules the whole model exists to honour.
    """
    model = TaxModel(goal.tax)
    realized = [
        RealizedTrade(
            # `bucket_for`, never a local re-derivation of the holding-period split. The first
            # version inlined `LTCG if holding_days > months*30 else STCG`, which skipped the
            # branch on `tax.equity_delivery`: flipping the config to the business-income reading
            # — the open CA question, item O7 — would have left every after-tax number in every
            # backtest silently on the cheaper capital-gains rates.
            #
            # It passed the two *dates* rather than a day count from 2026-08-16. `months * 30` was
            # not only inlined in the wrong place, it was wrong arithmetic wherever it lived: the
            # statute counts calendar months, and twelve of those are 365 or 366 days depending on
            # where the leap day falls — never 360.
            bucket=model.bucket_for(
                Segment.EQUITY_DELIVERY, entry_ts=t.entry_ts, exit_ts=t.exit_ts
            ),
            pnl=t.net_pnl,
            exit_ts=t.exit_ts,
        )
        for t in trades
    ]
    years = model.annual_tax(realized)
    return years, sum((y.total_tax for y in years), Decimal(0))


# --------------------------------------------------------------------------------------
# Trial ledger (invariant #24)
# --------------------------------------------------------------------------------------


def record_trial(
    path: Path, strategy: StrategyCandidate, result: BacktestResult, *, origin: str
) -> int:
    """Append this evaluation to the lifetime trial ledger and return the new count.

    Append-only, and it counts human attempts too. Every hand-authored strategy, every re-tuned
    parameter and every re-run is a trial: DSR corrects for multiple testing using the *effective*
    number of things tried, so a ledger that only counted Inventor candidates would leave the
    overfitting guard blind during exactly the phase it exists to protect (invariant #24).
    """
    history = read_trials(path)
    history.append(
        {
            "at": datetime.now(UTC).isoformat(),
            "strategy": strategy.name,
            "version": strategy.version,
            "origin": origin,
            "primitives": sorted(strategy.primitives_used()),
            "oos_sharpe": (
                round(result.oos.sharpe.point, 4)
                if result.oos and result.oos.sharpe.is_estimable
                else None
            ),
            # Both, from 2026-08-16. The ledger recorded only the pre-tax Sharpe while the gate
            # moved to the after-tax one, so the DSR correction in 1.9 — which reads this file —
            # would have been computed on a different quantity from the promotion decision it is
            # meant to correct (finding F43).
            "oos_sharpe_after_tax": (
                round(result.oos_after_tax.sharpe.point, 4)
                if result.oos_after_tax and result.oos_after_tax.sharpe.is_estimable
                else None
            ),
            "oos_trades": len(result.oos_trades),
            "folds": len(result.folds),
        }
    )
    # Atomic: a crash midway through an in-place rewrite leaves a truncated JSON document, after
    # which `read_trials` raises and the lifetime count invariant #24 depends on is unrecoverable.
    write_atomic_json(path, {"schema": _LEDGER_SCHEMA, "trials": history})
    log.info("trial recorded", strategy=strategy.name, lifetime_trials=len(history))
    return len(history)


def read_trials(path: Path) -> list[dict[str, object]]:
    """The lifetime trial ledger, or an empty list if it does not exist yet."""
    if not path.exists():
        return []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema") != _LEDGER_SCHEMA:
        raise DslError(
            f"trial ledger {path} has schema {payload.get('schema')}, expected {_LEDGER_SCHEMA}. "
            f"Migrate it — never start a fresh one, the count is the point."
        )
    trials: list[dict[str, object]] = payload["trials"]
    return trials


__all__ = [
    "DEFAULT_TRIAL_LEDGER",
    "BacktestResult",
    "FoldResult",
    "read_trials",
    "record_trial",
    "run_walk_forward",
]
