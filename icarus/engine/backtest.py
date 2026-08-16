"""Walk-forward, purge/embargo and the single-use lockbox (task 1.7, PRD §13, §29-31).

**A backtest that lets you tune until it works measures your persistence, not an edge.** Try two
hundred variations and keep the best and the result is guaranteed to look good and guaranteed to
mean nothing. Three defences, in increasing order of how easy they are to get subtly wrong:

**1. Walk-forward, never a single split.** Train on the past, test on the year that follows, step
forward, repeat. Every number reported comes from a window the strategy had not seen. One split is
one lucky draw; nine windows are nine chances to fail.

The windows are **anchored** — training starts at ``walk_forward_start`` and expands, rather than
sliding a fixed-length window forward. A rolling window would drop 2011-2013 as the sample
advances, and those years carry the taper tantrum and demonetisation: exactly the conditions a
strategy most needs to have survived, and exactly the ones a fixed window quietly forgets.

**2. Purge and embargo, because the seam bleeds.** Even with clean windows the boundary leaks in
both directions. A 200-day average on the first day of the test period is made almost entirely of
training-period bars. A trade opened in December closes in February and straddles the line.

*Purge* is the gap cut before the test window, and it is **derived from the strategy, not
configured** — its width is that strategy's own longest lookback. A word with a 252-day window
leaks 252 days across the seam; a 20-day word leaks 20. One constant would be too small for the
first and wasteful for the second, and the too-small case leaks silently, which is the worst
property a guard can have. It is computed conservatively: the largest integer parameter anywhere
in the strategy tree, so a lookback cannot be missed by failing to recognise its parameter name.

*Embargo* is the gap cut after the test window before training resumes, so the next training
window does not begin inside bars whose own indicator history overlaps the period just tested.

**3. The lockbox is consumed exactly once (invariant #26).** Everything from
``data_split.lockbox_start`` is held back for one final go/no-go. The moment it is evaluated a
second time it *is* training data — you are tuning against it like everything else, just more
slowly, and every number it produces afterwards is meaningless.

Two things guard it, deliberately separate. Reaching it at all requires an explicit
``use_lockbox=True``, so no routine walk-forward run can wander into it by accident. And each use
appends to a permanent, dated log which the guard reads before allowing another.

**The log is append-only, not immutable.** (Operator decision, 2026-08-05.) A bug or a mistyped
date could otherwise destroy the only clean evaluation window this project has, with no remedy,
turning a coding error into a project-ending event. So a reset is possible — and it writes a
permanent, dated, reasoned entry that any later reader will see. The discipline is preserved by
the record, not by the counter being unmovable: **you can recover from an accident, you cannot
make the accident invisible.** It is the same shape as the ``min_sharpe`` amendment log.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import TYPE_CHECKING

from icarus.common.logging import get_logger
from icarus.strategy.dsl import Bars, Composite, DslError, Panel

if TYPE_CHECKING:
    from collections.abc import Iterator, Mapping, Sequence

    from icarus.common.config import Backtest as BacktestConfig
    from icarus.common.config import DataSplit
    from icarus.strategy.dsl import Condition, StrategyCandidate

log = get_logger("engine.backtest")

_SESSIONS_PER_YEAR = 252
_LOG_SCHEMA = 1
DEFAULT_LOCKBOX_LOG = Path("var/lockbox_uses.json")


@dataclass(frozen=True, slots=True)
class Window:
    """One walk-forward fold, as bar **indices** into the panel's date axis.

    Indices rather than dates because purge and embargo are counted in *sessions*, and a calendar
    gap of five days is three sessions over a weekend and five over a quiet stretch. Counting
    sessions keeps the guard the same size wherever it lands.
    """

    train_start: int
    train_end: int  # exclusive, already purged
    test_start: int
    test_end: int  # exclusive
    purge_sessions: int
    embargo_sessions: int

    def __post_init__(self) -> None:
        if self.train_end <= self.train_start:
            raise ValueError("a walk-forward window with no training data is not a window")
        if self.test_end <= self.test_start:
            raise ValueError("a walk-forward window with no test data is not a window")
        if self.train_end > self.test_start:
            raise ValueError(
                f"train window ends at {self.train_end} but test starts at {self.test_start} — "
                f"they overlap, which is the leak purge exists to prevent"
            )


def longest_lookback(strategy: StrategyCandidate) -> int:
    """The widest window the strategy could be looking back over, as a session count.

    **Deliberately over-inclusive**: it takes the largest integer literal anywhere in the strategy,
    rather than trying to recognise which parameters are lookbacks. Parameter names are not a
    reliable signal (``n``, ``k``, ``period``, ``slope_n``, ``search``, ``legs``…), and the failure
    modes are wildly asymmetric — purging a few sessions too many costs a little data, while
    missing one lets the training window leak into the test window with no symptom at all.

    **Reads all three blocks, not just ``entry`` (finding F3).** It used to read ``entry`` alone,
    which was wrong twice over: ``rank_by`` decides which candidates get the scarce slots, and an
    ``exit`` rule carries the ATR period that sizes the stop. Both are computed over the same span
    and both need the same history. The live casualty was ``baseline_buy_and_hold``, whose entry is
    "price is above zero" and therefore contains no integer at all: it was granted a **zero**
    lead-in while its ``rank_by`` asked for ``roc(252)``, so its ranker was ``nan`` across the whole
    one-year test window, every candidate tied, and the sort fell through to the symbol name. The
    control built to prove the machinery works was selecting alphabetically.

    ``exit`` contributes some integers that are not lookbacks at all — ``time_stop(bars: 20)`` is a
    holding period. That is the over-inclusive policy working as intended, not an oversight.
    """
    return max(_strategy_integers(strategy), default=0)


def _strategy_integers(strategy: StrategyCandidate) -> Iterator[int]:
    yield from _integer_literals(strategy.entry)
    if strategy.rank_by is not None:
        yield from _integer_literals(strategy.rank_by)
    for rule in strategy.exits:
        yield from _whole_numbers(rule.literals)


def _integer_literals(node: Condition) -> Iterator[int]:
    if isinstance(node, Composite):
        for term in node.terms:
            yield from _integer_literals(term)
        return
    yield from _whole_numbers(node.literals)
    for child in node.nested.values():
        yield from _integer_literals(child)


def _whole_numbers(literals: Mapping[str, int | float | str]) -> Iterator[int]:
    """``bool`` is an ``int`` in Python, and a flag set to ``True`` is not a one-bar lookback."""
    for value in literals.values():
        if isinstance(value, int) and not isinstance(value, bool):
            yield value


def walk_forward_windows(
    panel: Panel, strategy: StrategyCandidate, config: BacktestConfig, split: DataSplit
) -> list[Window]:
    """Anchored walk-forward folds over the panel's development span.

    Bounded at **both** ends by ``data_split``. Reaching past ``walk_forward_end`` is not a matter
    of care in the caller: the lockbox has to be unreachable from the ordinary path, so this
    function cannot produce a window that touches it.

    ``walk_forward_start`` was honoured from 2026-08-16 (finding F37). It had been validated and
    then ignored — every window anchored on the panel's own first session — which was invisible
    only because the two dates currently coincide. Narrowing it to exclude a regime would have left
    the folds training from 2011 with no error and no log line, and the config reading as though the
    exclusion had taken effect.
    """
    dates = _dates_of(panel)
    development = [
        i
        for i, day in enumerate(dates)
        if split.walk_forward_start <= day <= split.walk_forward_end
    ]
    if not development:
        raise DslError(
            f"the panel contains no sessions inside the walk-forward span "
            f"{split.walk_forward_start}..{split.walk_forward_end}"
        )

    purge = longest_lookback(strategy)
    embargo = config.embargo_sessions
    train_min = int(config.min_train_years * _SESSIONS_PER_YEAR)
    test_len = int(config.test_window_years * _SESSIONS_PER_YEAR)
    step = int(config.step_years * _SESSIONS_PER_YEAR)
    last = development[-1] + 1

    windows: list[Window] = []
    # `purge + embargo`, not `purge`. The embargo was read from config, stamped on every window and
    # printed in the fold record, and never once entered the arithmetic — setting it to 100 gave
    # byte-identical windows while the log line said 100 (finding F30).
    #
    # **What this gap actually buys, stated honestly (finding F40).** The purge's original
    # justification was that "a 200-session average on the first test day is built from training
    # days". That is now true of *every* test day by construction, because `evaluate_once`
    # deliberately evaluates the strategy over the whole span — and it is not a leak, it is what a
    # live system does on any given morning. So the gap is not preventing the thing it was
    # introduced to prevent. Two real things remain:
    #   1. It keeps the in-sample and out-of-sample *trading* periods separated by a gap, so
    #      `sharpe_decay` compares genuinely distinct stretches rather than adjacent ones.
    #   2. It is the harness being correct in advance of Phase 2. Nothing here fits parameters per
    #      fold today — strategies are pre-registered and the in-sample record is measured, not
    #      optimised against — so no choice made in training can leak. The moment the Inventor
    #      starts fitting per fold, it can, and the gap has to already be there.
    # The deeper question the gap does *not* answer — with an anchored window, every later fold
    # trains on every earlier test period, and no gap before the test window changes that — is
    # recorded as F40 for an operator decision rather than settled quietly here.
    seam = purge + embargo
    test_start = development[0] + train_min + seam
    while test_start + test_len <= last:
        windows.append(
            Window(
                train_start=development[0],
                train_end=test_start - seam,
                test_start=test_start,
                test_end=test_start + test_len,
                purge_sessions=purge,
                embargo_sessions=embargo,
            )
        )
        test_start += step
    if not windows:
        raise DslError(
            f"no walk-forward window fits: {len(development)} sessions available, but one fold "
            f"needs {train_min} training + {purge} purged + {embargo} embargoed + {test_len} "
            f"test sessions. Either the panel is too short or the strategy's longest lookback "
            f"({purge}) is too wide for it."
        )
    log.info(
        "walk-forward windows built",
        folds=len(windows),
        purge_sessions=purge,
        embargo_sessions=embargo,
    )
    return windows


def lockbox_window(panel: Panel, split: DataSplit) -> Window:
    """The single final fold. Reachable only through :class:`LockboxGuard`.

    Trains on the **same span** the walk-forward folds do, bounded at both ends. The lower bound
    was added on 2026-08-16 with the one in :func:`walk_forward_windows`, and missing it here would
    have been the worse of the two omissions: narrowing ``walk_forward_start`` to exclude a regime
    would have left the walk-forward honouring it and the final go/no-go fold quietly training on
    the excluded years. The lockbox is evaluated **once** (invariant #26), so that discrepancy is
    not something a later run can correct.
    """
    dates = _dates_of(panel)
    inside = [
        i
        for i, day in enumerate(dates)
        if day >= split.lockbox_start and (split.lockbox_end is None or day <= split.lockbox_end)
    ]
    before = [
        i
        for i, day in enumerate(dates)
        if split.walk_forward_start <= day <= split.walk_forward_end
    ]
    if not inside or not before:
        raise DslError("the panel does not span both the development window and the lockbox")
    return Window(
        train_start=before[0],
        train_end=before[-1] + 1,
        test_start=inside[0],
        test_end=inside[-1] + 1,
        purge_sessions=0,
        embargo_sessions=0,
    )


def _dates_of(panel: Panel) -> list[date]:
    return [d.astype("datetime64[D]").astype(date) for d in panel.ts]


# --------------------------------------------------------------------------------------
# The lockbox
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class LockboxUse:
    """One recorded touch of the lockbox — or one recorded reset."""

    at: datetime
    strategy: str
    reason: str
    is_reset: bool = False

    def as_json(self) -> dict[str, object]:
        return {
            "at": self.at.isoformat(),
            "strategy": self.strategy,
            "reason": self.reason,
            "is_reset": self.is_reset,
        }

    @classmethod
    def from_json(cls, raw: dict[str, object]) -> LockboxUse:
        return cls(
            at=datetime.fromisoformat(str(raw["at"])),
            strategy=str(raw["strategy"]),
            reason=str(raw["reason"]),
            is_reset=bool(raw.get("is_reset", False)),
        )


class LockboxExhausted(DslError):
    """The lockbox has already been consumed. Any further number from it is meaningless."""


class LockboxGuard:
    """Append-only record of every lockbox evaluation, and the gate that reads it.

    The counter that matters is *uses since the last reset*. Resets are entries in the same log
    rather than deletions, so the history always shows how many times the window was really
    touched, whatever the current count says.
    """

    def __init__(self, path: Path = DEFAULT_LOCKBOX_LOG, *, allowed: int = 1) -> None:
        self._path = path
        self._allowed = allowed

    def history(self) -> list[LockboxUse]:
        if not self._path.exists():
            return []
        payload = json.loads(self._path.read_text(encoding="utf-8"))
        if payload.get("schema") != _LOG_SCHEMA:
            raise DslError(
                f"lockbox log at {self._path} has schema {payload.get('schema')!r}, expected "
                f"{_LOG_SCHEMA} — refusing to interpret it rather than guessing"
            )
        return [LockboxUse.from_json(entry) for entry in payload["uses"]]

    def uses_since_reset(self) -> int:
        history = self.history()
        for index in range(len(history) - 1, -1, -1):
            if history[index].is_reset:
                return sum(1 for use in history[index + 1 :] if not use.is_reset)
        return sum(1 for use in history if not use.is_reset)

    def consume(self, strategy: str, reason: str, *, now: datetime | None = None) -> None:
        """Record one evaluation, or refuse because the budget is spent."""
        spent = self.uses_since_reset()
        if spent >= self._allowed:
            raise LockboxExhausted(
                f"the lockbox has been evaluated {spent} time(s) and the budget is "
                f"{self._allowed}. A second look makes it training data, and every number from it "
                f"afterwards is meaningless (invariant #26). If it was burned by mistake, record a "
                f"dated reset — the accident can be recovered from, it cannot be made invisible."
            )
        self._append(
            LockboxUse(at=now or datetime.now(UTC), strategy=strategy, reason=reason),
        )
        log.warning("lockbox consumed", strategy=strategy, reason=reason, uses=spent + 1)

    def reset(self, reason: str, *, now: datetime | None = None) -> None:
        """Restore the budget, permanently and visibly.

        There is no argument that makes this invisible, which is the whole design: the entry stays
        in the log for every future reader, so a reset can always be weighed against the results
        that came after it.
        """
        if not reason.strip():
            raise DslError("a lockbox reset needs a reason — an unexplained reset is a deletion")
        self._append(
            LockboxUse(at=now or datetime.now(UTC), strategy="-", reason=reason, is_reset=True),
        )
        log.warning("lockbox reset", reason=reason)

    def _append(self, use: LockboxUse) -> None:
        history = [*self.history(), use]
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps(
                {"schema": _LOG_SCHEMA, "uses": [entry.as_json() for entry in history]}, indent=2
            ),
            encoding="utf-8",
        )


def slice_panel(panel: Panel, start: int, end: int) -> Panel:
    """A view of the panel over ``[start, end)``, membership included.

    Slicing rather than masking so a windowed run physically cannot read a bar outside its window
    — the future is *absent*, not merely filtered. That is the same property replay mode (1.10)
    relies on, and the reason a leakage bug cannot hide behind an off-by-one in a mask.
    """
    if not 0 <= start < end <= len(panel):
        raise DslError(f"window [{start}, {end}) is outside the panel's {len(panel)} sessions")
    bars = {
        symbol: Bars(
            ts=panel.bars[i].ts[start:end],
            open=panel.bars[i].open[start:end],
            high=panel.bars[i].high[start:end],
            low=panel.bars[i].low[start:end],
            close=panel.bars[i].close[start:end],
            volume=panel.bars[i].volume[start:end],
        )
        for i, symbol in enumerate(panel.symbols)
    }
    tradable = {symbol: panel.tradable[i][start:end] for i, symbol in enumerate(panel.symbols)}
    benchmark = None
    if panel.benchmark is not None:
        b = panel.benchmark
        benchmark = Bars(
            ts=b.ts[start:end],
            open=b.open[start:end],
            high=b.high[start:end],
            low=b.low[start:end],
            close=b.close[start:end],
            volume=b.volume[start:end],
        )
    return Panel.build(bars, tradable, benchmark=benchmark)


def assert_panel_stops_before_lockbox(panel: Panel, split: DataSplit) -> None:
    """Refuse a panel that reaches into the lockbox at all.

    **Separate from the window check, and stricter.** While each fold was evaluated on its own
    slice, a panel reaching past ``lockbox_start`` could not matter: the future was *absent* from
    the array the DSL ever saw. Evaluating once over the whole span
    (:func:`~icarus.engine.runner.evaluate_once`) removed that slicing, and with it the structural
    guarantee — the only remaining defence was that every primitive is causal, which is true and
    tested but is a property of 223 words rather than a property of the data. ``build_panel
    --lockbox`` exists and produces exactly the panel that would rely on it.

    Kept out of :func:`assert_no_lockbox_overlap` deliberately: that function answers "do these
    windows touch the lockbox", which is a question worth being able to ask *about a panel that
    spans it* — the test that proves :func:`walk_forward_windows` never reaches the lockbox has to
    build such a panel to prove anything. Folding the two together made that test unable to run.
    """
    dates = _dates_of(panel)
    if dates and dates[-1] >= split.lockbox_start:
        raise DslError(
            f"this panel runs to {dates[-1]}, at or past lockbox_start {split.lockbox_start} — "
            f"the walk-forward path evaluates the strategy over the whole panel, so a panel that "
            f"contains the lockbox puts it in reach. Build one that stops before it (invariant #26)"
        )


def assert_no_lockbox_overlap(windows: Sequence[Window], panel: Panel, split: DataSplit) -> None:
    """Refuse a fold that reaches into the lockbox.

    Belt and braces over :func:`walk_forward_windows`, which already stops short of it — an
    overlap turns the lockbox into training data and leaves no trace in any metric, so it is worth
    checking twice from two directions.
    """
    dates = _dates_of(panel)
    for window in windows:
        for index in (window.train_end - 1, window.test_end - 1):
            if dates[index] >= split.lockbox_start:
                raise DslError(
                    f"a walk-forward window reaches {dates[index]}, at or past lockbox_start "
                    f"{split.lockbox_start} — that contaminates the lockbox (invariant #26)"
                )


__all__ = [
    "DEFAULT_LOCKBOX_LOG",
    "LockboxExhausted",
    "LockboxGuard",
    "LockboxUse",
    "Window",
    "assert_no_lockbox_overlap",
    "assert_panel_stops_before_lockbox",
    "lockbox_window",
    "longest_lookback",
    "slice_panel",
    "walk_forward_windows",
]
