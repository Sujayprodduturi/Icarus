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
4. **Audit what is left.** Any residual overnight gap the adjustment did not explain gets the
   symbol's prior history quarantined, with a count and a named list. See :func:`_quarantine`.

**On step 4's direction of bias.** A 50% down-gap is either an unadjusted capital change (fake) or a
genuine collapse (real). Deleting it outright would flatter the results by removing real losses;
keeping it would let a fabricated crash trigger real stops. The chosen answer is to remove the
symbol's history *up to and including* the gap and keep everything after — symmetric in sign, so
it removes fabricated gains and fabricated losses alike, and the count is reported rather than
absorbed. If that count is ever large, the run is not trustworthy and the report says so.
"""

from __future__ import annotations

import json
import math
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
    benchmark: Bars | None = None,
) -> tuple[Panel, BuildReport]:
    """Read the day-cache and assemble the panel. Touches no network.

    ``sessions`` must be the exact trading days to build over, ascending; ``cache_dir`` the
    bhavcopy day-cache written by ``scripts/backfill_bhavcopy.py``.
    """
    report = BuildReport(sessions=len(sessions))
    symbols, raw = _read_days(sessions, cache_dir, report)

    tradable = _membership(raw, universe, sessions)
    adjusted, splits_applied = _back_adjust(symbols, raw, actions, sessions)
    report.splits_applied = splits_applied

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

    for i, symbol in enumerate(symbols):
        present = np.flatnonzero(~np.isnan(close[i]))
        if present.size < 2:
            continue
        consecutive = np.diff(present) == 1
        prev, cur = present[:-1][consecutive], present[1:][consecutive]
        if prev.size == 0:
            continue
        with np.errstate(invalid="ignore", divide="ignore"):
            ratio = open_[i][cur] / close[i][prev]
        breached = np.flatnonzero(np.abs(np.log(ratio)) > math.log(1.0 + MAX_UNEXPLAINED_GAP))
        if breached.size == 0:
            continue

        last = int(cur[breached[-1]])
        gap_day = sessions[last]
        # An action listed within a couple of sessions either side means NSE knew about an event
        # here and our ratio was wrong or unparseable — a different failure from a gap with no
        # corporate action on file at all, and worth telling apart in the report.
        nearby = any(
            (symbol, sessions[j]) in action_dates
            for j in range(max(0, last - 2), min(len(sessions), last + 3))
        )
        report.quarantines.append(
            Quarantine(
                symbol=symbol,
                at=gap_day,
                ratio=float(ratio[breached[-1]]),
                had_action_on_file=nearby,
            )
        )
        report.dropped_symbol_days += int(tradable[i, : last + 1].sum())
        tradable[i, : last + 1] = False


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
