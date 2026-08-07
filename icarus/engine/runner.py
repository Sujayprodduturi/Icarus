"""Walk-forward runner: strategy + panel -> a metric sheet (task 1.7d, PRD §30-31).

The piece that was missing. Every part it calls was already built and unit-tested against
hand-made arrays — the fill model, the portfolio simulator, the window arithmetic, 223 DSL
words — and not one of them had ever seen a real NSE price. This joins them and runs them over
the development span.

**What it does per fold.** Slice the panel to the fold's test window plus a warm-up prefix,
evaluate the strategy matrix-wise over that slice, hand the resulting signal/stop/rank columns to
the portfolio simulator, and keep the trades. Folds are then stitched into one continuous
out-of-sample record.

**The warm-up prefix is not a leak.** A 200-session moving average is ``nan`` for the first 200
bars of any slice, so a fold evaluated on its test window alone would spend its first year unable
to fire and would report a fold-length-dependent result. The slice therefore starts
``longest_lookback`` sessions early and :func:`_gate_signals` blanks every signal before
``test_start``, so the warm-up bars feed the indicators and can never open a position. That is
exactly what a live system does on the morning it starts: it reads history to compute today's
average, it does not trade yesterday.

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
from icarus.engine.taxmodel import RealizedTrade, TaxModel
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
        }


@dataclass
class BacktestResult:
    """The whole walk-forward record for one strategy."""

    strategy: str
    folds: list[FoldResult] = field(default_factory=list)
    oos: Metrics | None = None
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

    The lockbox is unreachable from here: :func:`walk_forward_windows` stops short of it and
    :func:`assert_no_lockbox_overlap` checks the same thing from the other direction. Both, because
    an overlap turns the held-out slice into training data and leaves no trace in any metric.
    """
    windows = walk_forward_windows(panel, strategy, goal.backtest, goal.data_split)
    assert_no_lockbox_overlap(windows, panel, goal.data_split)
    if not windows:
        raise DslError(
            f"no walk-forward folds fit {strategy.name} on this panel: "
            f"{len(panel)} sessions against a {goal.backtest.min_train_years}-year minimum train "
            f"plus a {longest_lookback(strategy)}-session purge"
        )

    result = BacktestResult(strategy=strategy.name)
    warmup = longest_lookback(strategy)
    dates = [str(t)[:10] for t in panel.ts]

    for i, window in enumerate(windows):
        # The SAME warm-up treatment on both sides. Training used to be called with warmup=0,
        # so its curve kept the unavoidable lead-in of dead, zero-return sessions while the test
        # curve had its prefix trimmed. Padding a return series with zeros scales its Sharpe by
        # about sqrt(active/total), so the in-sample figure was depressed and the headline
        # "was it fitted" decay ratio came out correspondingly too generous.
        train = _run_span(
            strategy, panel, window.train_start, window.train_end, warmup, goal, registry
        )
        test = _run_span(
            strategy, panel, window.test_start, window.test_end, warmup, goal, registry
        )
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
    result.oos = summarise(
        _stitch(result.folds),
        result.oos_trades,
        confidence_level=goal.stop_gate.sharpe_confidence_level,
        sessions_open=_sessions_held(result.oos_trades, _session_days(_stitch(result.folds))),
    )
    result.sharpe_decay = _decay_across_folds(result.folds)
    result.tax_years, result.tax_total = _tax(result.oos_trades, goal)

    if ledger is not None:
        record_trial(ledger, strategy, result, origin="operator")
    return result


# --------------------------------------------------------------------------------------
# One span
# --------------------------------------------------------------------------------------


def _run_span(
    strategy: StrategyCandidate,
    panel: Panel,
    start: int,
    end: int,
    warmup: int,
    goal: GoalConfig,
    registry: Registry,
) -> RunResult:
    """Simulate ``[start, end)``, reading ``warmup`` sessions of history before it."""
    frm = max(0, start - warmup)
    window = slice_panel(panel, frm, end)
    gate = start - frm

    signals = evaluate_universe(strategy.entry, window, registry)
    _gate_signals(signals, gate)
    stops = _stops(strategy, window)
    ranks = (
        evaluate_universe(strategy.rank_by, window, registry)
        if strategy.rank_by is not None
        else None
    )

    simulator = PortfolioSimulator(
        risk=goal.risk,
        costs=CostModel(goal.costs),
        fills=FillModel(goal.execution_realism),
        segment=Segment.EQUITY_DELIVERY,
    )
    run = simulator.run(
        strategy,
        window,
        signals,
        stops,
        starting_equity=Decimal(goal.backtest.starting_equity_inr),
        ranks=ranks,
    )
    # Drop the warm-up prefix from the equity curve. Its points are real — equity simply sat flat
    # because no signal could fire — but leaving them in would dilute every return-based metric
    # with sessions the fold was not actually being measured over.
    run.equity = run.equity[gate:]
    return run


def _gate_signals(signals: dict[str, Column], gate: int) -> None:
    """Blank every signal in the warm-up prefix, in place.

    Zero rather than ``nan``: the simulator reads a signal as "fire if truthy", and ``nan`` is
    truthy. A ``nan`` here would open a position on every warm-up bar of every symbol — the exact
    opposite of the intent, and it would look like an unusually active strategy rather than a bug.
    """
    if gate <= 0:
        return
    for column in signals.values():
        column[:gate] = 0.0


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


def _stitch(folds: Sequence[FoldResult]) -> list[tuple[datetime, Decimal]]:
    """One continuous equity curve from the folds' out-of-sample curves, by compounding returns.

    Folds each restart from the same nominal equity, so concatenating rupee values would produce a
    sawtooth — and a drawdown statistic measuring the resets rather than the strategy. Compounding
    the per-session returns gives the curve the strategy would have had running continuously,
    which is what the stitched Sharpe and drawdown are meant to describe.

    Anchored at 1.0 rather than at the starting equity: this curve is a return series, and giving
    it a rupee scale it never had would invite it to be read as a P&L.
    """
    curve: list[tuple[datetime, Decimal]] = []
    equity = Decimal(1)
    for fold in folds:
        previous: Decimal | None = None
        for ts, value in fold.equity_curve:
            if previous is not None and previous > 0:
                equity *= value / previous
                curve.append((ts, equity))
            previous = value
    return curve


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
            bucket=model.bucket_for(Segment.EQUITY_DELIVERY, holding_days=t.holding_days),
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
