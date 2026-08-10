"""Assemble a point-in-time :class:`~icarus.strategy.dsl.Panel` from the bhavcopy archive (1.7c).

This is the seam between fifteen years of downloaded end-of-day files and the engine. Everything
upstream of it is a source; everything downstream assumes an aligned, back-adjusted, honestly
membered matrix. Four jobs, in an order that matters:

1. **Align.** Every symbol onto one session axis, ``nan`` where it did not trade. :class:`Panel`
   refuses a mis-aligned panel, and rightly — a shifted symbol ranks Monday's RELIANCE against
   Tuesday's TCS and nothing downstream could tell.
2. **Decide membership from the RAW prices.** The turnover floor and the ₹30 penny floor are
   point-in-time facts about what a trader could see on the day, so they are computed *before* any
   back-adjustment. Applying them after would be a subtle look-ahead in the other direction: a
   ₹45 stock in 2012 that later did a 1:10 bonus back-adjusts to ₹4.50 and would be wrongly
   excluded as a penny stock by a rule that only exists because of what happened afterwards.
3. **Back-adjust.** Only then are prices made continuous, using NSE's own ratios
   (:mod:`icarus.agents.data.nseactions`).
4. **Reject bad ticks** against each symbol's own volatility. See :func:`_reject_bad_ticks`.
5. **Audit what is left.** Any residual overnight gap the adjustment did not explain gets the
   symbol's prior history quarantined, with a count and a named list. See :func:`_quarantine`.

**On step 5's direction of bias.** A 50% down-gap is either an unadjusted capital change (fake) or a
genuine collapse (real). Deleting it outright would flatter the results by removing real losses;
keeping it would let a fabricated crash trigger real stops. The chosen answer is to remove the
symbol's history *up to and including* the gap and keep everything after — symmetric in sign, so
it removes fabricated gains and fabricated losses alike, and the count is reported rather than
absorbed. If that count is ever large, the run is not trustworthy and the report says so.

**Where the data-QA layer lives, and why it is not simply called** (1.1, 2026-08-10). An audit found
that :class:`~icarus.agents.data.quality.DataQualityGate` was imported only by the *live* ingestion
agent and had never touched the panel. Checking its rules one by one against what happens here:

=============================  =================================================================
non-positive price             already enforced in :func:`_row_values`, and *more* strictly — the
                               panel rejects below ``_MIN_SANE_PRICE``, the gate only at zero
incoherent OHLC                already enforced in :func:`_row_values`
negative volume                already enforced in :func:`_row_values` (turnover too)
non-trading day                impossible here: ``sessions`` comes from the validated calendar
duplicate timestamp            impossible here: the panel is a date-indexed matrix
**implausible jump**           **was genuinely missing.** Now :func:`_reject_bad_ticks`
probable corporate action      superseded by :func:`_quarantine` at ``MAX_UNEXPLAINED_GAP`` —
                               tighter than the gate's 50%, and with a stronger remedy
=============================  =================================================================

The gate is a *stateful stream validator over Decimal candles*; this is a *batch float64 matrix
builder*. Forcing one implementation on both would be the wrong shape for one of them. So the
structural rules exist twice — and a differential test in ``test_panelbuild.py`` runs both over
the same bars and asserts they agree, because two copies that are never compared are how the
day-cache schema constant drifted. **Prove the equivalence; do not assume it.**

Porting the gate's ≥50% corporate-action check was considered and **deliberately rejected**: it
would blank the bar to ``nan``, :func:`_quarantine` only compares *consecutive present* sessions,
and so a genuine unexplained repricing would become invisible and never quarantine anything. The
check would have made the panel worse than not having it.
"""

from __future__ import annotations

import json
import math
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import TYPE_CHECKING

import numpy as np
import numpy.typing as npt

from icarus.agents.data.nse import DAY_CACHE_SCHEMA, TURNOVER_INDEX
from icarus.common.calendar import session_open_utc
from icarus.common.logging import get_logger
from icarus.strategy.dsl import Bars, DslError, Panel

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path

    from icarus.agents.data.nseactions import ActionHistory
    from icarus.common.config import DataQuality as DataQualityConfig
    from icarus.common.config import Universe as UniverseConfig

log = get_logger("engine.panelbuild")

_PANEL_CACHE_SCHEMA = 2

# A back-adjusted overnight move beyond this is treated as an unexplained discontinuity. NSE
# equity carries daily price bands — 20% for most names, and F&O names trade within a flexing
# band — so a clean 25% *opening* gap is essentially never an ordinary session. It is a capital
# change we could not price, or a halt/relisting. Either way it is not something to trade through.
MAX_UNEXPLAINED_GAP = 0.25

# Prices below this are dropped as unusable regardless of the universe floor: a sub-rupee quote
# has a tick size that is a large fraction of the price, so no fill model of ours is honest there.
_MIN_SANE_PRICE = 1.0

_FLOAT = np.float64


@dataclass(frozen=True, slots=True)
class Quarantine:
    """One symbol's history removed up to a discontinuity we could not explain away."""

    symbol: str
    at: date
    ratio: float
    """Observed ``open / previous close`` after back-adjustment. 1.0 would be continuous."""

    had_action_on_file: bool
    """True when NSE listed *some* event near this date — so the adjustment failed rather than
    the event being unknown. Distinguishing them is what tells us whether the ratio parser or the
    coverage is at fault."""


@dataclass
class BuildReport:
    """What the build did, in numbers the operator can sanity-check. Never a bare success flag."""

    sessions: int = 0
    symbols_seen: int = 0
    symbols_kept: int = 0
    splits_applied: int = 0
    bad_ticks_rejected: int = 0
    symbols_with_bad_ticks: int = 0
    low_quality_sessions: list[tuple[date, float]] = field(default_factory=list)
    """Sessions whose accepted share fell below ``data_quality.min_day_score``.

    Reported, never acted on. §29.4 turns a low day score into ``NEEDS_MORE_DATA`` at the
    *validation gate*; deciding it here would let the panel builder silently drop a day of
    history, and a hole nobody was told about is the failure the score exists to surface.
    """

    quarantines: list[Quarantine] = field(default_factory=list)
    tradable_symbol_days: int = 0
    dropped_symbol_days: int = 0
    median_universe_size: float = 0.0
    min_universe_size: int = 0
    max_universe_size: int = 0

    def as_json(self) -> dict[str, object]:
        return {
            "sessions": self.sessions,
            "symbols_seen": self.symbols_seen,
            "symbols_kept": self.symbols_kept,
            "splits_applied": self.splits_applied,
            "bad_ticks_rejected": self.bad_ticks_rejected,
            "symbols_with_bad_ticks": self.symbols_with_bad_ticks,
            "low_quality_sessions": len(self.low_quality_sessions),
            "worst_day_score": (
                round(min(score for _, score in self.low_quality_sessions), 4)
                if self.low_quality_sessions
                else 1.0
            ),
            "quarantined_symbols": len(self.quarantines),
            "quarantined_with_action_on_file": sum(
                1 for q in self.quarantines if q.had_action_on_file
            ),
            "tradable_symbol_days": self.tradable_symbol_days,
            "dropped_symbol_days_to_quarantine": self.dropped_symbol_days,
            "universe_size_min": self.min_universe_size,
            "universe_size_median": self.median_universe_size,
            "universe_size_max": self.max_universe_size,
        }


def session_axis(sessions: Sequence[date]) -> npt.NDArray[np.datetime64]:
    """The panel's date axis: each session stamped at its 09:15 IST open, in UTC.

    One function rather than one construction per caller. :meth:`Panel.build` compares the
    benchmark's axis to the symbols' with ``array_equal``, so a benchmark built at midnight and a
    panel built at the session open are silently incompatible — and the error surfaces as
    "benchmark not aligned" long after the mistake, if at all.
    """
    return np.array(
        [np.datetime64(session_open_utc(d).replace(tzinfo=None), "ns") for d in sessions]
    )


def sessions_in(calendar_artifact: Path, frm: date, to: date) -> list[date]:
    """Trading sessions in ``[frm, to]`` from the backfill artifact, ascending.

    Reads the artifact rather than the live calendar module on purpose: this is exactly the range
    the backfill validated, and a session list that disagrees with the files on disk is the one
    thing that would silently shorten a backtest.
    """
    payload = json.loads(calendar_artifact.read_text(encoding="utf-8"))
    days = [date.fromisoformat(d) for d in payload["sessions"]]
    span = sorted(d for d in days if frm <= d <= to)
    if not span:
        raise DslError(f"no sessions in {frm}..{to} in {calendar_artifact}")
    return span


def build_panel(
    *,
    sessions: Sequence[date],
    cache_dir: Path,
    actions: ActionHistory,
    universe: UniverseConfig,
    quality: DataQualityConfig,
    benchmark: Bars | None = None,
) -> tuple[Panel, BuildReport]:
    """Read the day-cache and assemble the panel. Touches no network.

    ``sessions`` must be the exact trading days to build over, ascending; ``cache_dir`` the
    bhavcopy day-cache written by ``scripts/backfill_bhavcopy.py``.
    """
    report = BuildReport(sessions=len(sessions))
    symbols, raw = _read_days(sessions, cache_dir, report)

    # Order is load-bearing, and two of the four steps moved on 2026-08-10.
    #
    # Back-adjust BEFORE looking for bad ticks: on raw prices every split is a huge jump, so a
    # volatility-relative test run there would reject the 614 legitimate repricings in this span
    # and nothing else.
    #
    # Reject bad ticks BEFORE membership and BEFORE the quarantine. Before membership because a
    # fabricated print would otherwise still count toward the 20-session turnover window that
    # decides who was tradable. Before the quarantine because the gap audit cannot tell a bad
    # print from a capital change and its remedy is to delete everything prior — so a single
    # spurious tick used to erase a symbol's whole history.
    adjusted, splits_applied = _back_adjust(symbols, raw, actions, sessions)
    report.splits_applied = splits_applied
    _reject_bad_ticks(symbols, adjusted, raw, quality, sessions, report)

    tradable = _membership(raw, universe, sessions)
    _quarantine(symbols, adjusted, tradable, actions, sessions, report)
    symbols, adjusted, tradable = _drop_never_tradable(symbols, adjusted, tradable, report)

    per_date = tradable.sum(axis=0)
    report.tradable_symbol_days = int(tradable.sum())
    report.median_universe_size = float(np.median(per_date))
    report.min_universe_size = int(per_date.min())
    report.max_universe_size = int(per_date.max())
    report.symbols_kept = len(symbols)

    ts = session_axis(sessions)
    bars = {
        symbol: Bars(
            ts=ts,
            open=adjusted["open"][i],
            high=adjusted["high"][i],
            low=adjusted["low"][i],
            close=adjusted["close"][i],
            volume=adjusted["volume"][i],
        )
        for i, symbol in enumerate(symbols)
    }
    membership = {symbol: tradable[i] for i, symbol in enumerate(symbols)}
    panel = Panel.build(bars, membership, benchmark=benchmark)
    log.info("panel built", **report.as_json())
    return panel, report


# --------------------------------------------------------------------------------------
# Reading
# --------------------------------------------------------------------------------------

_Matrices = dict[str, npt.NDArray[np.float64]]


def _read_days(
    sessions: Sequence[date], cache_dir: Path, report: BuildReport
) -> tuple[list[str], _Matrices]:
    """One pass over the day-cache into ``(symbols x dates)`` matrices, ``nan`` where absent.

    Two passes over the files would double the parse cost of ~4.4 million rows, so the symbol
    index is discovered on the fly and the matrices are grown once at the end — the row payloads
    are held as (date-index, symbol, values) triples in between.
    """
    index: dict[str, int] = {}
    columns: list[list[tuple[int, list[float]]]] = []

    for t, day in enumerate(sessions):
        path = cache_dir / f"{day:%Y%m%d}.json"
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise DslError(
                f"session {day} is in the calendar but has no cached bhavcopy at {path}. Run "
                f"scripts/backfill_bhavcopy.py — a missing session is a hole in the backtest, "
                f"never a day to skip (§29.4)"
            ) from exc
        if payload.get("schema") != DAY_CACHE_SCHEMA:
            # Imported, never restated: a second copy of this number would let the writer and
            # the reader drift apart and the panel would be built from a layout it misreads.
            raise DslError(
                f"{path} has day-cache schema {payload.get('schema')}, expected "
                f"{DAY_CACHE_SCHEMA} — re-run scripts/backfill_bhavcopy.py"
            )
        for symbol, row in payload["rows"].items():
            values = _row_values(row)
            if values is None:
                continue
            slot = index.get(symbol)
            if slot is None:
                slot = index[symbol] = len(index)
                columns.append([])
            columns[slot].append((t, values))

    report.symbols_seen = len(index)
    symbols = sorted(index)
    n, m = len(symbols), len(sessions)
    fields = ("open", "high", "low", "close", "volume", "turnover")
    out: _Matrices = {name: np.full((n, m), np.nan, dtype=_FLOAT) for name in fields}
    for i, symbol in enumerate(symbols):
        entries = columns[index[symbol]]
        if not entries:
            continue
        at = np.fromiter((t for t, _ in entries), dtype=np.intp, count=len(entries))
        block = np.array([v for _, v in entries], dtype=_FLOAT)
        for k, name in enumerate(fields):
            out[name][i, at] = block[:, k]
    log.info("day-cache read", sessions=m, symbols=n)
    return symbols, out


def _row_values(row: Sequence[str]) -> list[float] | None:
    """``[o,h,l,c,volume,turnover]`` as floats, or ``None`` for a row we will not price.

    Rejects rather than repairs (§29.3): a non-numeric field, a non-positive price or an OHLC
    ordering violation means the row is not a description of a real session, and inventing a
    plausible substitute is how a backtest ends up trading prices that never existed.
    """
    try:
        o, h, low, c = (float(row[k]) for k in range(4))
        volume, turnover = float(row[4]), float(row[TURNOVER_INDEX])
    except (TypeError, ValueError, IndexError):
        return None
    if min(o, h, low, c) < _MIN_SANE_PRICE or volume < 0 or turnover < 0:
        return None
    if not (low <= min(o, c) and max(o, c) <= h):
        return None
    return [o, h, low, c, volume, turnover]


# --------------------------------------------------------------------------------------
# Point-in-time membership — computed on RAW prices, before any adjustment
# --------------------------------------------------------------------------------------


def _membership(
    raw: _Matrices, universe: UniverseConfig, sessions: Sequence[date]
) -> npt.NDArray[np.bool_]:
    """The tradable mask: who cleared the liquidity and price floors, as known on each date.

    Mirrors :class:`~icarus.agents.data.universe.PointInTimeUniverse` exactly — trailing average
    turnover over ``turnover_window_sessions``, presence required in *every* session of that
    window, plus the ₹30 penny floor — but computed matrix-wise, because doing it per date across
    2,950 dates and 2,000 symbols through the per-date class would re-read the same windows
    millions of times.

    The full-window presence requirement is what excludes freshly-listed names: an IPO has no
    trailing record and guessing one would be inventing history.
    """
    window = universe.turnover_window_sessions
    close, turnover = raw["close"], raw["turnover"]
    present = ~np.isnan(close)

    rolling_turnover = _rolling_sum(np.where(present, turnover, 0.0), window)
    rolling_present = _rolling_sum(present.astype(_FLOAT), window)

    qualified = np.zeros_like(present)
    # Each rolling column is the window ENDING at date `window - 1 + j`, so the first `window - 1`
    # dates have no complete window and stay False. An off-by-one here is a look-ahead bug: it
    # would let a name qualify on liquidity it had not yet demonstrated.
    liquid = (rolling_present == window) & (
        rolling_turnover / window >= float(universe.min_avg_turnover_inr)
    )
    qualified[:, window - 1 :] = liquid

    priced = np.zeros_like(present)
    np.greater_equal(close, float(universe.min_close_inr), out=priced, where=present)
    out: npt.NDArray[np.bool_] = qualified & priced & present
    return out


# --------------------------------------------------------------------------------------
# Back-adjustment
# --------------------------------------------------------------------------------------


def _rolling_sum(block: npt.NDArray[np.float64], window: int) -> npt.NDArray[np.float64]:
    """Trailing ``window``-wide sums along the date axis, one column per complete window.

    By cumulative-sum difference rather than a strided view: at ~2,000 symbols x 2,950 dates a
    stride trick allocates a 20x copy for no gain, and the leading zero column removes the special
    case for the first window entirely.
    """
    cumulative = np.concatenate(
        [np.zeros((block.shape[0], 1), dtype=_FLOAT), np.cumsum(block, axis=1)], axis=1
    )
    out: npt.NDArray[np.float64] = cumulative[:, window:] - cumulative[:, :-window]
    return out


def _back_adjust(
    symbols: Sequence[str],
    raw: _Matrices,
    actions: ActionHistory,
    sessions: Sequence[date],
) -> tuple[_Matrices, int]:
    """Rescale pre-ex-date prices so each symbol's series is continuous.

    The cumulative factor for a bar is the product of every split whose ex-date is strictly after
    it; prices divide by it and volume multiplies, preserving traded value. Bars on or after the
    last split are untouched, so recent prices stay equal to the prices a live order would fill
    at. Turnover is deliberately *not* rescaled — it is only ever read by :func:`_membership`,
    which has already run on the raw numbers.
    """
    at = {day: i for i, day in enumerate(sessions)}
    out: _Matrices = {k: v.copy() for k, v in raw.items()}
    applied = 0

    for i, symbol in enumerate(symbols):
        splits = actions.splits_for(symbol)
        if not splits:
            continue
        factor = np.ones(len(sessions), dtype=_FLOAT)
        for split in splits:
            # An ex-date on a holiday belongs to the next session that traded; searchsorted gives
            # the first session at or after it, which is where the repriced quote first appears.
            cut = at.get(split.ex_date)
            if cut is None:
                cut = int(np.searchsorted([str(d) for d in sessions], str(split.ex_date)))
            if not 0 < cut < len(sessions):
                continue  # ex-date outside the built span: nothing in this panel to rescale
            factor[:cut] *= float(split.ratio)
            applied += 1
        for name in ("open", "high", "low", "close"):
            out[name][i] /= factor
        out["volume"][i] *= factor
    return out, applied


# --------------------------------------------------------------------------------------
# Bad ticks — the one data-QA rule the panel was missing (1.1, 2026-08-10)
# --------------------------------------------------------------------------------------


def _reject_bad_ticks(
    symbols: Sequence[str],
    adjusted: _Matrices,
    raw: _Matrices,
    quality: DataQualityConfig,
    sessions: Sequence[date],
    report: BuildReport,
) -> None:
    """Blank bars whose intrabar excursion is absurd against the symbol's own recent volatility.

    Mutates both matrices in place: a bar rejected here must be gone from ``raw`` too, or
    :func:`_membership` would still count a fabricated print towards a turnover window.

    **A bad tick and a repricing are different animals and must not be confused.**

    * A *bad tick* is a spike in the high or the low that the **close does not confirm** — a print
      that never represented a tradable price. Remedy: drop the bar.
    * A *repricing* is an overnight move the adjustment could not explain. Remedy:
      :func:`_quarantine` truncates the symbol's history.

    So this only fires when the overnight move is **inside** ``MAX_UNEXPLAINED_GAP``. Without that
    guard the two mechanisms would hide each other: blanking a repricing bar to ``nan`` makes its
    neighbours non-consecutive, and :func:`_quarantine` deliberately does not compare across holes
    — so the discontinuity would vanish silently and the history would never be quarantined.

    **This runs before the quarantine, and that is the point.** The gap audit cannot tell a bad
    print from a genuine capital change, and its remedy is to delete everything before it. One
    spurious tick above the band therefore erased a symbol's entire prior history. Removing bad
    ticks first should *reduce* what the quarantine takes.

    **The ATR excludes the current bar** and is a simple mean of the last ``atr_window`` true
    ranges, matching :class:`~icarus.agents.data.quality.DataQualityGate` exactly — judging a bar
    partly against itself would let a big enough spike raise the very threshold meant to catch it.

    **One sequential pass, deliberately, even though a vectorised pre-filter would be faster.**
    The first version had one: a cheap matrix scan to find symbols with any candidate at all, then
    the walk on those alone. It was correct, and it was untestable. Mutation-testing the walk's
    band guard and its warm-up guard found both mutations *surviving* — because the pre-filter
    carried copies of the same two conditions and skipped the symbol before the walk ever ran. Two
    of the guards that matter most had no single site where breaking them showed up.

    A rule with two homes is a rule that can drift, and the saving was on a build that runs once
    and caches a ``.npz``. So the pre-filter is gone and the walk keeps a running true-range total
    to stay O(1) per bar.
    """
    window = quality.atr_window
    limit = float(quality.max_bar_move_atr)
    band = math.log(1.0 + MAX_UNEXPLAINED_GAP)
    high, low, close, open_ = (adjusted[k] for k in ("high", "low", "close", "open"))

    rejected_at: list[tuple[int, int]] = []
    for i in range(len(symbols)):
        present = np.flatnonzero(~np.isnan(close[i]))
        if present.size <= window:
            continue
        bars = (open_[i][present], high[i][present], low[i][present], close[i][present])
        hits = _walk_for_bad_ticks(bars, window, limit, band)
        rejected_at.extend((i, int(present[j])) for j in hits)

    if not rejected_at:
        _score_days(adjusted, {}, quality, sessions, report)
        return

    rows = np.fromiter((i for i, _ in rejected_at), dtype=np.intp, count=len(rejected_at))
    cols = np.fromiter((t for _, t in rejected_at), dtype=np.intp, count=len(rejected_at))
    per_session: dict[int, int] = {}
    for t in cols.tolist():
        per_session[t] = per_session.get(t, 0) + 1

    # `raw` before `adjusted`: they are separate arrays (back-adjustment copies), and a bar left
    # alive in `raw` would still feed the turnover window that decides membership.
    for matrices in (raw, adjusted):
        for block in matrices.values():
            block[rows, cols] = np.nan

    report.bad_ticks_rejected = len(rejected_at)
    report.symbols_with_bad_ticks = len(set(rows.tolist()))
    _score_days(adjusted, per_session, quality, sessions, report)
    log.info(
        "bad ticks rejected",
        bars=report.bad_ticks_rejected,
        symbols=report.symbols_with_bad_ticks,
    )


_Bars4 = tuple[
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
    npt.NDArray[np.float64],
]


def _walk_for_bad_ticks(bars: _Bars4, window: int, limit: float, band: float) -> list[int]:
    """The single implementation. Returns indices *into the present series* that were rejected.

    Mirrors ``DataQualityGate``: the reference close and the true-range window advance only on
    **accepted** bars, so a rejected print cannot become the baseline the next bar is judged
    against — which is exactly how one bad tick otherwise manufactures a second one.

    A bar whose overnight move is outside ``band`` is accepted here **and remembered**. That is a
    deliberate choice over skipping it: not advancing the reference close would leave every
    subsequent bar compared against a stale price and cascade into false rejections. Its true range
    does enter the window and will raise the threshold for the next ``window`` bars — conservative,
    in the direction of keeping data, and the symbol is the quarantine's problem by then anyway.

    ``total`` tracks the sum of ``trailing`` so the ATR is O(1) rather than O(window) per bar.
    That is what makes one honest sequential pass affordable across every symbol, and therefore
    what lets every rule below live at exactly one site where a mutation can find it.
    """
    open_, high, low, close = bars
    rejected: list[int] = []
    trailing: deque[float] = deque(maxlen=window)
    total = 0.0
    reference: float | None = None

    for j in range(close.size):
        span = float(high[j] - low[j])
        if reference is None:
            total += span
            trailing.append(span)
            reference = float(close[j])
            continue
        excursion = max(abs(high[j] - reference), abs(low[j] - reference))
        overnight = abs(math.log(open_[j] / reference)) if open_[j] > 0 else math.inf
        if len(trailing) == window and overnight <= band:
            atr = total / window
            if atr > 0 and excursion > limit * atr:
                rejected.append(j)
                continue
        true_range = max(span, excursion)
        # Read the evicted value before appending: a full deque discards it on append, and losing
        # it would leave `total` drifting upward forever.
        if len(trailing) == window:
            total -= trailing[0]
        total += true_range
        trailing.append(true_range)
        reference = float(close[j])
    return rejected


def _score_days(
    adjusted: _Matrices,
    rejected_per_session: dict[int, int],
    quality: DataQualityConfig,
    sessions: Sequence[date],
    report: BuildReport,
) -> None:
    """Record sessions whose accepted share fell below ``min_day_score`` (§29.4).

    The denominator is bars *seen* on that session — present after rejection, plus the rejected
    ones. A symbol that simply did not trade is not a data-quality failure, so absence must not
    dilute the score in either direction.
    """
    surviving = np.count_nonzero(~np.isnan(adjusted["close"]), axis=0)
    for t, day in enumerate(sessions):
        dropped = rejected_per_session.get(t, 0)
        seen = int(surviving[t]) + dropped
        if not seen:
            continue
        score = (seen - dropped) / seen
        if score < quality.min_day_score:
            report.low_quality_sessions.append((day, score))
    if report.low_quality_sessions:
        log.warning(
            "sessions below min_day_score",
            count=len(report.low_quality_sessions),
            threshold=quality.min_day_score,
            worst=min(score for _, score in report.low_quality_sessions),
        )


# --------------------------------------------------------------------------------------
# The audit: what did the adjustment fail to explain?
# --------------------------------------------------------------------------------------


def _quarantine(
    symbols: Sequence[str],
    adjusted: _Matrices,
    tradable: npt.NDArray[np.bool_],
    actions: ActionHistory,
    sessions: Sequence[date],
    report: BuildReport,
) -> None:
    """Blank each symbol's membership up to any overnight gap adjustment did not explain.

    Mutates ``tradable`` in place. Only *consecutive* present sessions are compared: a symbol that
    was suspended for a month and came back lower has not gapped, it has been away, and treating
    absence as a discontinuity would quarantine every name that ever took a trading halt.
    """
    close, open_ = adjusted["close"], adjusted["open"]
    action_dates = {
        (a.symbol, a.ex_date) for a in (*actions.unpriceable, *actions.unrecognised)
    } | {(s, sp.ex_date) for s, sps in actions.splits.items() for sp in sps}

    # A capital change NSE listed but we could not price — a demerger, a rights issue, a scheme of
    # arrangement — reprices the stock by an amount nobody wrote down. Quarantining only what the
    # gap audit *detected* left every such event under 25% being traded through: flagged upstream,
    # ignored by the adjuster, invisible to the audit, and then experienced by the strategy as a
    # real 15% loss it stopped out on. So the known-unpriceable dates seed the quarantine directly.
    unpriceable_at: dict[str, list[int]] = {}
    session_index = {day: t for t, day in enumerate(sessions)}
    for action in (*actions.unpriceable, *actions.unrecognised):
        t = session_index.get(action.ex_date)
        if t is not None:
            unpriceable_at.setdefault(action.symbol, []).append(t)

    for i, symbol in enumerate(symbols):
        present = np.flatnonzero(~np.isnan(close[i]))
        cut, ratio_at_cut, detected = -1, float("nan"), False
        if present.size >= 2:
            consecutive = np.diff(present) == 1
            prev, cur = present[:-1][consecutive], present[1:][consecutive]
            if prev.size:
                with np.errstate(invalid="ignore", divide="ignore"):
                    ratio = open_[i][cur] / close[i][prev]
                breached = np.flatnonzero(
                    np.abs(np.log(ratio)) > math.log(1.0 + MAX_UNEXPLAINED_GAP)
                )
                if breached.size:
                    cut = int(cur[breached[-1]])
                    ratio_at_cut = float(ratio[breached[-1]])
                    detected = True

        listed = unpriceable_at.get(symbol, [])
        if listed:
            cut = max(cut, max(listed))
        if cut < 0:
            continue

        gap_day = sessions[cut]
        # An action listed within a couple of sessions either side means NSE knew about an event
        # here and our ratio was wrong or unparseable — a different failure from a gap with no
        # corporate action on file at all, and worth telling apart in the report.
        nearby = not detected or any(
            (symbol, sessions[j]) in action_dates
            for j in range(max(0, cut - 2), min(len(sessions), cut + 3))
        )
        report.quarantines.append(
            Quarantine(symbol=symbol, at=gap_day, ratio=ratio_at_cut, had_action_on_file=nearby)
        )
        report.dropped_symbol_days += int(tradable[i, : cut + 1].sum())
        tradable[i, : cut + 1] = False


def _drop_never_tradable(
    symbols: Sequence[str],
    adjusted: _Matrices,
    tradable: npt.NDArray[np.bool_],
    report: BuildReport,
) -> tuple[list[str], _Matrices, npt.NDArray[np.bool_]]:
    """Drop symbols tradable on no date in this span.

    Purely a size reduction — a name that never clears the liquidity floor can never be selected,
    so carrying it changes no result while costing memory on every matrix-wise evaluation. It does
    *not* touch survivorship: membership was already decided point-in-time above, and this removes
    rows that are False everywhere rather than choosing symbols by how they turned out.
    """
    keep = np.flatnonzero(tradable.any(axis=1))
    if keep.size == 0:
        raise DslError(
            "no symbol cleared the universe floors on any date in this span — check "
            "universe.min_avg_turnover_inr against the era being built"
        )
    kept = [symbols[i] for i in keep]
    log.info("symbols dropped as never tradable", dropped=len(symbols) - len(kept), kept=len(kept))
    return kept, {name: block[keep] for name, block in adjusted.items()}, tradable[keep]


# --------------------------------------------------------------------------------------
# Panel cache
# --------------------------------------------------------------------------------------


_FIELDS = ("open", "high", "low", "close", "volume")


def save_panel(panel: Panel, report: BuildReport, path: Path) -> None:
    """Persist a built panel so a re-run costs a load rather than a four-minute rebuild.

    **The benchmark is saved with it.** It was not, in the first version, and the cache round-trip
    silently returned a panel with ``benchmark=None`` — so every index-relative word would have
    refused to evaluate and the alpha gate (invariant #21) would have had nothing to measure
    against, on a panel whose build log said the benchmark had loaded fine.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    extra: dict[str, npt.NDArray[np.float64] | npt.NDArray[np.datetime64]] = {}
    if panel.benchmark is not None:
        extra = {f"benchmark_{name}": getattr(panel.benchmark, name) for name in _FIELDS}
    np.savez_compressed(
        path,
        schema=np.array([_PANEL_CACHE_SCHEMA]),
        symbols=np.array(panel.symbols),
        ts=panel.ts,
        tradable=panel.tradable,
        report=np.array([json.dumps(report.as_json())]),
        **{name: np.vstack([getattr(b, name) for b in panel.bars]) for name in _FIELDS},
        **extra,
    )
    log.info(
        "panel cached",
        path=str(path),
        symbols=len(panel.symbols),
        sessions=len(panel),
        benchmark=panel.benchmark is not None,
    )


def load_panel(path: Path, *, benchmark: Bars | None = None) -> Panel:
    """Read a cached panel. A schema mismatch raises rather than being coerced.

    ``benchmark`` overrides whatever the cache holds; passing one when the cache already has a
    different index is a caller error we cannot detect, so the explicit argument wins.
    """
    with np.load(path, allow_pickle=False) as data:
        if int(data["schema"][0]) != _PANEL_CACHE_SCHEMA:
            raise DslError(
                f"panel cache {path} has schema {int(data['schema'][0])}, expected "
                f"{_PANEL_CACHE_SCHEMA} — rebuild it rather than reading it"
            )
        if benchmark is None and "benchmark_close" in data:
            benchmark = Bars(ts=data["ts"], **{name: data[f"benchmark_{name}"] for name in _FIELDS})
        symbols = [str(s) for s in data["symbols"]]
        ts = data["ts"]
        blocks = {name: data[name] for name in _FIELDS}
        tradable = data["tradable"]
    bars = {
        symbol: Bars(ts=ts, **{name: blocks[name][i] for name in blocks})
        for i, symbol in enumerate(symbols)
    }
    return Panel.build(bars, {s: tradable[i] for i, s in enumerate(symbols)}, benchmark=benchmark)


def utc_dates(panel: Panel) -> list[date]:
    """The panel's session dates. Convenience for reporting, not for logic."""
    return [datetime.fromisoformat(str(t)[:19]).date() for t in panel.ts]


__all__ = [
    "MAX_UNEXPLAINED_GAP",
    "BuildReport",
    "Quarantine",
    "build_panel",
    "load_panel",
    "save_panel",
    "session_axis",
    "sessions_in",
    "utc_dates",
]
