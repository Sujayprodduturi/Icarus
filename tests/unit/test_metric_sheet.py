"""The metric sheet has to survive printing — task 2g, found by the code review of F40.

The sheet is the operator-facing deliverable: it is where every promote/reject verdict, every
refused signal and every rupee of tax is read. It is also the only part of the system whose output
goes through a *console encoder*, and on Windows that encoder is cp1252, not UTF-8.

**The bug this file exists to make unrepeatable.** F40 added a warning header carrying ``U+26A0
WARNING SIGN``, which cp1252 cannot encode. Printing it raises ``UnicodeEncodeError`` — and it sat
on the branch that only runs when the strategies' spans *disagree*, so the sheet would have died
precisely when it had something to warn about, taking the fold listing, the stale-mark section, the
concentration counter, the skip-reason table and the trial-ledger count down with it. The benign
branch is pure ASCII, so nothing would have shown up until the day it mattered.

``₹`` (U+20B9) is the same trap waiting to be stepped in: it is all over the comments and
docstrings, where it is harmless, and it would crash the moment somebody moved one into a printed
line. Hence a check over the rendered sheet rather than over one character.
"""

from __future__ import annotations

import io
from contextlib import redirect_stdout
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import pytest
from scripts.run_backtest import _print_sheet

from icarus.common.config import load_goal
from icarus.engine.backtest import Window
from icarus.engine.metrics import Metrics, SharpeEstimate
from icarus.engine.runner import BacktestResult, FoldResult

if TYPE_CHECKING:
    from icarus.common.config import GoalConfig

# The operator's console today. Latin-1 with the Windows extensions — it has `—` and `§` but
# neither `₹` nor `⚠`.
_CONSOLE = "cp1252"


@pytest.fixture
def goal(repo_root: Path) -> GoalConfig:
    return load_goal(repo_root / "goal.yaml")


def _metrics() -> Metrics:
    return Metrics(
        sharpe=SharpeEstimate(0.4, 0.1, 0.7, 1.0, 30, 0.95),
        sortino=0.5,
        calmar=0.3,
        cagr=0.08,
        total_return=0.2,
        volatility_annual=0.15,
        max_drawdown=0.1,
        max_drawdown_days=12,
        trades=30,
        win_rate=0.5,
        profit_factor=1.2,
        expectancy_r=0.1,
        avg_win_r=1.0,
        avg_loss_r=-0.8,
        avg_holding_days=5.0,
        sessions=250,
        exposure=0.4,
    )


def _fold(index: int, test_from: str, test_to: str) -> FoldResult:
    return FoldResult(
        index=index,
        window=Window(0, 100, 105, 200, seam_sessions=5),
        train_from="2011-01-03",
        train_to="2014-01-02",
        test_from=test_from,
        test_to=test_to,
        in_sample=_metrics(),
        out_of_sample=_metrics(),
        trades=(),
        skipped={"no_slot": 12},
        stale_marks=1,
        stale_mark_value=Decimal(1234),
        concentration_capped=3,
        unfilled_exits=2,
        ambiguous_selection_days=4,
        equity_curve=((datetime(2014, 1, 3, tzinfo=UTC), Decimal(1)),),
    )


def _result(name: str, test_from: str, test_to: str) -> BacktestResult:
    result = BacktestResult(strategy=name)
    result.folds = [_fold(0, test_from, test_to)]
    result.oos = _metrics()
    result.oos_after_tax = _metrics()
    return result


def _render(results: list[BacktestResult], goal: GoalConfig) -> str:
    """Print the sheet through a real cp1252 encoder, exactly as a console would."""
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding=_CONSOLE, newline="")
    with redirect_stdout(stream):
        _print_sheet(results, goal)
    stream.flush()
    return raw.getvalue().decode(_CONSOLE)


def test_the_metric_sheet_prints_on_the_operators_console(goal: GoalConfig) -> None:
    """The ordinary case: every section renders, nothing raises."""
    sheet = _render([_result("alpha", "2014-01-03", "2014-12-31")], goal)
    assert "WALK-FORWARD OUT-OF-SAMPLE" in sheet
    assert "ALL STRATEGIES MEASURED OVER THE SAME WINDOW" in sheet


def test_the_spans_differ_warning_prints_rather_than_killing_the_sheet(goal: GoalConfig) -> None:
    """The branch that carried the un-encodable character, and the reason it was never noticed.

    It runs only when the strategies disagree, so a crash here would have surfaced on the first run
    that had a real problem to report — and would have destroyed every section printed after it.
    """
    sheet = _render(
        [
            _result("alpha", "2014-01-03", "2014-12-31"),
            _result("beta", "2015-01-02", "2015-12-31"),
        ],
        goal,
    )
    assert "THE SPANS DIFFER" in sheet
    # ...and the sections *after* the warning still got printed, which is what a crash would take.
    assert "SIGNALS THE BOOK COULD NOT TAKE" in sheet
    assert "entries resized by the position cap" in sheet


def test_a_strategy_with_no_folds_does_not_break_the_span_table(goal: GoalConfig) -> None:
    """`r.folds[0]` is indexed in the span section; an empty result must not reach it."""
    empty = BacktestResult(strategy="never_fired")
    sheet = _render([_result("alpha", "2014-01-03", "2014-12-31"), empty], goal)
    assert "never_fired" in sheet
