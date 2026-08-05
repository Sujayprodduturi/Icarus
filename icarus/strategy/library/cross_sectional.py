"""Cross-sectional and benchmark-relative words — catalogue §8-9 (task 1.4c).

**Every other word in this library asks a question about one stock in isolation.** These ask a
question that has no answer for one stock: *of everything I can trade today, which are the
strongest ten?* Answering it for RELIANCE requires every other symbol's bar for **today** — so
these words are handed a :class:`~icarus.strategy.dsl.Panel` rather than ``Bars``, compute the
whole universe at once, and return one row per symbol (or a single row when the answer is the same
for everyone, like market breadth).

The payoff is worth the structural cost: cross-sectional momentum is one of the two best-evidenced
edges in the entire research survey, it works on NSE, and a hundred-name liquid universe is exactly
the setting it was designed for.

**The look-ahead bug here is not about time.** 1.4b's hazard was reading tomorrow's bar; this
module's is reading *today's list of symbols*. Rank the 2013 universe using the names that are
liquid in 2026 and every company that went bust has been silently filtered out — the survivors look
extraordinary because they were selected by having survived. It is the most common way a
cross-sectional backtest manufactures an edge, and it is invisible in the results. The defence is
mechanical, not procedural: ``Panel`` refuses to be built without point-in-time membership, and
every word here masks by it before computing anything.

**Two subtler versions of the same mistake, both guarded:**

* *Normalising with the whole sample.* Subtracting "the market average" is honest when it is
  today's average of today's names. Computed over 2011-2026 it hands every bar of 2013 information
  from 2025, and it is the same one-line call either way. Every statistic here is computed **per
  date, down the symbol axis**, never pooled.
* *Ranking a universe too thin to rank.* "Top decile" of four names is a coin toss that returns a
  confident-looking number. ``min_symbols`` defaults to 20 and its **lower bound is also 20** — a
  strategy may raise the floor but cannot lower it, and asking for less is rejected rather than
  clamped, exactly as ``risk_r`` is (invariant #4).

**Ties get the average rank.** Ordinal ranking would break ties by position in the symbol list,
which is alphabetical — handing every ADANI* name a permanent, invisible edge over every ZEE* one.

**Deliberately absent: ``pairs_spread`` / ``pairs_zscore``** (operator, 2026-08-05). A pairs
strategy needs pair *selection* — evidence that two names genuinely move together — and the
catalogue puts cointegration testing in validation, not the DSL. The spread on its own is a word no
honest strategy can yet be built from, so it is recorded here rather than shipped half-usable, the
same call made on ``liquidity_void`` in 1.4b.

``xs_sector_neutral`` is defined and **refuses**: it needs a point-in-time sector map, and NSE
publishes index constituents but not a classification we can date. Approximating it with today's
sectors would reintroduce the exact bias this module exists to prevent.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from icarus.strategy.dsl import DslError, IntParam, Kind, Panel, Primitive, SeriesParam
from icarus.strategy.library import _ops

if TYPE_CHECKING:
    import numpy.typing as npt

    Column = npt.NDArray[np.float64]
    Matrix = npt.NDArray[np.float64]
    Mask = npt.NDArray[np.bool_]

# The thin-universe floor (operator, 2026-08-05). Below this many eligible names on a date, every
# cross-sectional word reports "not knowable" for that date rather than a number. 20 is a judgement
# call rather than a derived constant: it is roughly where a decile stops being a single name.
MIN_SYMBOLS = 20


def _min_symbols_param() -> IntParam:
    """The floor is a parameter so a strategy can be *stricter*, and its minimum is the floor
    itself so it can never be looser. A request for 10 is rejected, not quietly raised to 20."""
    return IntParam("min_symbols", MIN_SYMBOLS, 500, default=MIN_SYMBOLS)


def _expr() -> SeriesParam:
    """What to rank by — any per-symbol expression in the vocabulary.

    Nested rather than a fixed list of rankable quantities, which is what makes one word cover
    ``xs_rank(momentum(126))``, ``xs_rank(delivery_pct())`` and everything else at once.
    """
    return SeriesParam("expr")


# --------------------------------------------------------------------------------------
# Eligibility — the gate every cross-sectional statistic passes through
# --------------------------------------------------------------------------------------


def _eligible(panel: Panel, values: Matrix, min_symbols: int) -> Mask:
    """Which ``(symbol, date)`` cells may take part in that date's cross-section.

    Three conditions, all of which must hold: the symbol was **tradable** on that date under the
    point-in-time universe rules, the expression being ranked has a **value** there (a warm-up
    ``nan`` cannot be ranked), and the date has **enough** participants to be worth ranking at all.

    The third is applied to the whole column at once — a date that fails it produces no ranking for
    anybody, rather than a ranking among the handful that happened to qualify.
    """
    usable = panel.tradable & ~np.isnan(values)
    deep_enough = usable.sum(axis=0) >= min_symbols
    out: Mask = usable & deep_enough
    return out


def _blank(values: Matrix) -> Matrix:
    return np.full(values.shape, np.nan, dtype=np.float64)


def _per_date_ranks(values: Matrix, eligible: Mask) -> Matrix:
    """Rank 1 = highest value, ties sharing the average of the ranks they span.

    The loop is over dates, not symbols: each date's cross-section is independent, and pooling them
    to vectorise would be the sample-wide-normalisation bug this module warns about.
    """
    out = _blank(values)
    for t in range(values.shape[1]):
        live = eligible[:, t]
        count = int(live.sum())
        if count == 0:
            continue
        # np.unique sorts ascending, so negating makes group 0 the *highest* value. A group
        # starting at 0-based offset "s" and holding "c" members spans the ranks from s plus one up
        # to s plus c, and the mean of those is s plus half of c plus one.
        _, inverse, counts = np.unique(-values[live, t], return_inverse=True, return_counts=True)
        starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
        out[live, t] = (starts + (counts + 1.0) / 2.0)[inverse]
    return out


def _xs_rank(panel: Panel, *, expr: Matrix, min_symbols: int, **_: object) -> Matrix:
    return _per_date_ranks(expr, _eligible(panel, expr, min_symbols))


def _xs_percentile(panel: Panel, *, expr: Matrix, min_symbols: int, **_: object) -> Matrix:
    """1.0 = best in the universe that day, 0.0 = worst.

    The comparable form of ``xs_rank``. A raw rank of 20 means something different in a universe of
    50 than in one of 200, so a strategy thresholding on rank across a growing universe is silently
    changing its own rule every year; a percentile is not.
    """
    eligible = _eligible(panel, expr, min_symbols)
    ranks = _per_date_ranks(expr, eligible)
    count = eligible.sum(axis=0).astype(np.float64)
    return _ops.safe_divide(count - ranks, count - 1.0)


def _per_date_moments(values: Matrix, eligible: Mask) -> tuple[Matrix, Matrix]:
    """``(mean, sample std)`` of each date's cross-section, broadcast back over the symbol axis."""
    live = np.where(eligible, values, np.nan)
    count = eligible.sum(axis=0).astype(np.float64)
    with np.errstate(invalid="ignore"):
        mean = np.where(count > 0, np.nansum(live, axis=0) / np.maximum(count, 1.0), np.nan)
        deviations = np.where(eligible, live - mean, np.nan)
        variance = np.where(
            count > 1, np.nansum(deviations**2, axis=0) / np.maximum(count - 1.0, 1.0), np.nan
        )
    return np.broadcast_to(mean, values.shape), np.broadcast_to(_ops.sqrt(variance), values.shape)


def _xs_zscore(panel: Panel, *, expr: Matrix, min_symbols: int, **_: object) -> Matrix:
    eligible = _eligible(panel, expr, min_symbols)
    mean, std = _per_date_moments(expr, eligible)
    return np.where(eligible, _ops.safe_divide(expr - mean, std), np.nan)


def _xs_demean(panel: Panel, *, expr: Matrix, min_symbols: int, **_: object) -> Matrix:
    """Subtract the day's own universe mean — market-neutral by construction.

    "The day's own" is the entire content of the word. Demeaning by the mean over the whole
    backtest would be the same arithmetic and a look-ahead bug.
    """
    eligible = _eligible(panel, expr, min_symbols)
    mean, _std = _per_date_moments(expr, eligible)
    return np.where(eligible, expr - mean, np.nan)


def _cohort(panel: Panel, expr: Matrix, n: int, min_symbols: int, *, top: bool) -> Matrix:
    """Membership of the best or worst ``n`` names on each date.

    A cohort as large as the universe is not a selection, so a date with ``n >= count`` reports
    "not knowable" rather than marking everybody. Without that, ``xs_top_n(n=50)`` on a 40-name day
    would silently become "buy everything" — a rule nobody wrote, producing trades nobody intended.
    """
    eligible = _eligible(panel, expr, min_symbols)
    ranks = _per_date_ranks(expr, eligible)
    count = eligible.sum(axis=0)
    selectable = count > n
    inside = (ranks <= n) if top else (ranks > count - n)
    return np.where(eligible & selectable, inside.astype(np.float64), np.nan)


def _xs_top_n(panel: Panel, *, expr: Matrix, n: int, min_symbols: int, **_: object) -> Matrix:
    return _cohort(panel, expr, n, min_symbols, top=True)


def _xs_bottom_n(panel: Panel, *, expr: Matrix, n: int, min_symbols: int, **_: object) -> Matrix:
    return _cohort(panel, expr, n, min_symbols, top=False)


# --------------------------------------------------------------------------------------
# Breadth — one number for the whole market
# --------------------------------------------------------------------------------------


def _breadth(panel: Panel, per_symbol: Matrix, min_symbols: int) -> Column:
    """Fraction of the day's eligible universe for which ``per_symbol`` is true. One row."""
    eligible = _eligible(panel, per_symbol, min_symbols)
    count = eligible.sum(axis=0).astype(np.float64)
    hits = np.where(eligible, per_symbol, 0.0).sum(axis=0)
    return _ops.safe_divide(hits, count)


def _breadth_pct_above_ma(panel: Panel, *, n: int, min_symbols: int, **_: object) -> Column:
    """How much of the market is above its *own* moving average — real participation.

    The cheapest honest regime switch there is, and unlike an index-level filter it cannot be held
    up by five large names while everything else falls.
    """
    rows = []
    for bars in panel.bars:
        average = _ops.rolling_mean(bars.close, n)
        rows.append(_ops.boolean(bars.close > average, np.isnan(average)))
    return _breadth(panel, np.vstack(rows), min_symbols)


def _advance_decline_ratio(panel: Panel, *, min_symbols: int, **_: object) -> Column:
    """Advancers divided by decliners among the day's eligible names.

    Unbounded above by construction — a day with no decliners has no ratio, and reports ``nan``
    rather than a large number standing in for infinity.
    """
    changes = np.vstack([bars.close - _ops.shift(bars.close, 1) for bars in panel.bars])
    eligible = _eligible(panel, changes, min_symbols)
    advances = np.where(eligible & (changes > 0.0), 1.0, 0.0).sum(axis=0)
    declines = np.where(eligible & (changes < 0.0), 1.0, 0.0).sum(axis=0)
    ratio = _ops.safe_divide(advances, declines)
    return np.where(eligible.any(axis=0), ratio, np.nan)


def _new_highs_minus_new_lows(panel: Panel, *, n: int, min_symbols: int, **_: object) -> Column:
    """``(new highs - new lows) / eligible names``, so it is comparable across universe sizes.

    A raw count would rise simply because the tradable universe grew, which over a fifteen-year
    NSE backtest it substantially does.
    """
    rows = []
    for bars in panel.bars:
        high = _ops.rolling_max(bars.high, n)
        low = _ops.rolling_min(bars.low, n)
        at_high = bars.high >= high
        at_low = bars.low <= low
        rows.append(np.where(np.isnan(high), np.nan, at_high.astype(np.float64) - at_low))
    net = np.vstack(rows)
    eligible = _eligible(panel, net, min_symbols)
    count = eligible.sum(axis=0).astype(np.float64)
    return _ops.safe_divide(np.where(eligible, net, 0.0).sum(axis=0), count)


# --------------------------------------------------------------------------------------
# Versus the benchmark
# --------------------------------------------------------------------------------------
#
# The catalogue writes these as `beta_to(benchmark, n)`. The benchmark is **not** a parameter here:
# it is fixed by `goal.yaml -> objective.benchmark_equity` and carried on the panel. A parameter
# would let a strategy name an index we have no data for, and the honest response to that is a
# refusal at parse time — but the DSL cannot check a symbol name against a data source it does not
# have. Taking it from the panel makes the wrong answer unrepresentable instead of merely rejected.


def _returns(close: Column, n: int) -> Column:
    past = _ops.shift(close, n)
    return _ops.safe_divide(close - past, past)


def _benchmark_return(panel: Panel, *, n: int, **_: object) -> Column:
    return _returns(panel.require_benchmark("benchmark_return").close, n)


def _index_above_ma(panel: Panel, *, n: int, **_: object) -> Column:
    close = panel.require_benchmark("index_above_ma").close
    average = _ops.rolling_mean(close, n)
    return _ops.boolean(close > average, np.isnan(average))


def _relative_strength(panel: Panel, *, n: int, **_: object) -> Matrix:
    """Excess ``n``-bar return over the index — the per-symbol cousin of the RS rating.

    A *difference* of returns rather than a ratio: the ratio is unstable wherever the index return
    is near zero, and flips sign when it crosses, which would make the word's meaning depend on
    something that has nothing to do with the stock.
    """
    index = _returns(panel.require_benchmark("relative_strength").close, n)
    return np.vstack([_returns(bars.close, n) - index for bars in panel.bars])


def _log_changes(close: Column) -> Column:
    out: Column = np.log(_ops.safe_divide(close, _ops.shift(close, 1)))
    return out


def _beta_to(panel: Panel, *, n: int, **_: object) -> Matrix:
    index = _log_changes(panel.require_benchmark("beta_to").close)
    variance = _ops.rolling_cov(index, index, n)
    return np.vstack(
        [
            _ops.safe_divide(_ops.rolling_cov(_log_changes(bars.close), index, n), variance)
            for bars in panel.bars
        ]
    )


def _correlation_to(panel: Panel, *, n: int, **_: object) -> Matrix:
    index = _log_changes(panel.require_benchmark("correlation_to").close)
    return np.vstack([_ops.rolling_corr(_log_changes(bars.close), index, n) for bars in panel.bars])


def _refuses(name: str, reason: str) -> object:
    def compute(panel: Panel, **_: object) -> Matrix:
        raise DslError(f"{name} cannot be computed: {reason}")

    return compute


def primitives() -> tuple[Primitive, ...]:
    """Catalogue §8-9."""
    floor = _min_symbols_param()
    cohort_n = IntParam("n", 1, 500)
    return (
        # ---- ranking ----
        Primitive(
            "xs_rank",
            Kind.CROSS_SECTIONAL,
            "Rank across the day's universe by any expression; 1 = highest.",
            _xs_rank,
            (_expr(), floor),
            needs_panel=True,
        ),
        Primitive(
            "xs_percentile",
            Kind.CROSS_SECTIONAL,
            "Rank as a 0-1 fraction; comparable across dates as the universe grows.",
            _xs_percentile,
            (_expr(), floor),
            needs_panel=True,
        ),
        Primitive(
            "xs_zscore",
            Kind.CROSS_SECTIONAL,
            "Standard deviations from the day's universe mean.",
            _xs_zscore,
            (_expr(), floor),
            needs_panel=True,
        ),
        Primitive(
            "xs_demean",
            Kind.CROSS_SECTIONAL,
            "Expression minus the day's universe mean — market-neutral by construction.",
            _xs_demean,
            (_expr(), floor),
            needs_panel=True,
        ),
        Primitive(
            "xs_top_n",
            Kind.EVENT,
            "In the best n of the day's universe by this expression.",
            _xs_top_n,
            (_expr(), cohort_n, floor),
            needs_panel=True,
        ),
        Primitive(
            "xs_bottom_n",
            Kind.EVENT,
            "In the worst n of the day's universe by this expression.",
            _xs_bottom_n,
            (_expr(), cohort_n, floor),
            needs_panel=True,
        ),
        Primitive(
            "xs_sector_neutral",
            Kind.CROSS_SECTIONAL,
            "Demeaned within sector. Needs a point-in-time sector map we do not have.",
            _refuses(  # type: ignore[arg-type]
                "xs_sector_neutral",
                "it needs a sector map dated to each bar; today's classification applied to 2013 "
                "would reintroduce exactly the survivorship bias the panel exists to prevent",
            ),
            (_expr(), floor),
            needs_panel=True,
        ),
        # ---- breadth ----
        Primitive(
            "breadth_pct_above_ma",
            Kind.SERIES,
            "Fraction of the universe trading above its own n-bar average.",
            _breadth_pct_above_ma,
            (_ops.period_param(default=50), floor),
            needs_panel=True,
        ),
        Primitive(
            "advance_decline_ratio",
            Kind.SERIES,
            "Advancers divided by decliners across the day's universe.",
            _advance_decline_ratio,
            (floor,),
            needs_panel=True,
        ),
        Primitive(
            "new_highs_minus_new_lows",
            Kind.SERIES,
            "Net new n-bar highs as a fraction of the universe.",
            _new_highs_minus_new_lows,
            (_ops.period_param(default=252), floor),
            needs_panel=True,
        ),
        # ---- versus the benchmark ----
        Primitive(
            "relative_strength",
            Kind.SERIES,
            "n-bar return minus the benchmark's over the same window.",
            _relative_strength,
            (_ops.period_param(default=126),),
            needs_panel=True,
        ),
        Primitive(
            "index_above_ma",
            Kind.EVENT,
            "The benchmark index is above its own n-bar average.",
            _index_above_ma,
            (_ops.period_param(default=200),),
            needs_panel=True,
        ),
        Primitive(
            "benchmark_return",
            Kind.SERIES,
            "The benchmark's own n-bar return.",
            _benchmark_return,
            (_ops.period_param(default=126),),
            needs_panel=True,
        ),
        Primitive(
            "beta_to",
            Kind.SERIES,
            "Rolling beta of this symbol's log returns to the benchmark's.",
            _beta_to,
            (_ops.period_param(default=126),),
            needs_panel=True,
        ),
        Primitive(
            "correlation_to",
            Kind.SERIES,
            "Rolling correlation of this symbol's log returns to the benchmark's.",
            _correlation_to,
            (_ops.period_param(default=126),),
            needs_panel=True,
        ),
    )


__all__ = ["MIN_SYMBOLS", "primitives"]
