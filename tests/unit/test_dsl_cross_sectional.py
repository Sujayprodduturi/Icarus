"""Cross-sectional and benchmark words — catalogue §8-9 (task 1.4c).

The per-symbol library's look-ahead guard truncates one series and demands the past not change.
That guard is structurally blind to the two ways a *cross-section* lies, because neither involves
reading a future bar:

* **Survivorship.** Ranking 2013 against the symbols that are liquid in 2026 filters out everything
  that failed, and the survivors look extraordinary because they were chosen by surviving. No
  amount of truncating the time axis detects it — the bug is on the *symbol* axis.
* **Sample-wide normalisation.** "Subtract the market average" is honest as today's average of
  today's names and a look-ahead bug as the average over the whole backtest. Identical arithmetic,
  identical shape, and truncation only catches it near the cut.

So this file carries a panel-wide version of the sweep (whole universe truncated, every symbol's
overlap must match) *and* direct tests for both bugs above, plus hand-derived fixtures where the
ranking is readable by eye.

**The fixtures use 25 symbols because the thin-universe floor is real.** Below 20 eligible names
every cross-sectional word reports "not knowable", and the floor's lower bound is also 20, so a
test cannot shrink it to make a 4-symbol fixture work. Symbol ``S00`` carries value 0, ``S01``
value 1, and so on — which makes every expected rank derivable without arithmetic.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pytest

from icarus.strategy.dsl import (
    Bars,
    Call,
    ChoiceParam,
    DslError,
    FloatParam,
    IntParam,
    Panel,
    Registry,
    Sizing,
    assert_partitions_risk,
    evaluate,
    evaluate_universe,
    parse_strategy,
)
from icarus.strategy.library import default_registry

if TYPE_CHECKING:
    import numpy.typing as npt

SYMBOLS = tuple(f"S{i:02d}" for i in range(25))
DATES = 30


def _bars_at(level: float, size: int = DATES, start: str = "2024-01-01") -> Bars:
    """A gently rising series at a given level — distinct per symbol, and never crossing."""
    close = np.arange(size, dtype=np.float64) * 0.1 + level
    return Bars(
        ts=np.arange(np.datetime64(start), np.datetime64(start) + size).astype("datetime64[ns]"),
        open=close.copy(),
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=np.full(size, 1000.0),
    )


def _levelled() -> dict[str, Bars]:
    """The default universe: symbol ``S<i>`` at price level ``i``, so ranking by close is ranking
    by symbol index and every expected rank below is readable without arithmetic."""
    return {symbol: _bars_at(float(i)) for i, symbol in enumerate(SYMBOLS)}


def _all_tradable(size: int = DATES) -> dict[str, npt.NDArray[np.bool_]]:
    return {symbol: np.ones(size, dtype=np.bool_) for symbol in SYMBOLS}


def _panel(
    *,
    symbols: tuple[str, ...] = SYMBOLS,
    size: int = DATES,
    tradable: dict[str, npt.NDArray[np.bool_]] | None = None,
    benchmark: bool = True,
) -> Panel:
    """Symbol ``S<i>`` sits at price level ``i``, so ranking by close is ranking by index."""
    bars = {symbol: _bars_at(float(i), size) for i, symbol in enumerate(symbols)}
    membership = tradable or {s: np.ones(size, dtype=np.bool_) for s in symbols}
    index = _bars_at(500.0, size) if benchmark else None
    return Panel.build(bars, membership, benchmark=index)


def _call(name: str, registry: Registry, **params: object) -> Call:
    primitive = registry.get(name)
    literals: dict[str, int | float | str] = {}
    nested: dict[str, Call] = {}
    for spec in primitive.params:
        if isinstance(spec, IntParam | FloatParam | ChoiceParam):
            value = params.get(spec.name, getattr(spec, "default", None))
            assert value is not None, f"{name}.{spec.name} needs a value in this test"
            literals[spec.name] = value  # type: ignore[assignment]
        else:
            supplied = params.get(spec.name)
            assert supplied is None or isinstance(supplied, Call)
            nested[spec.name] = supplied or _call("close", registry)
    return Call(primitive=name, kind=primitive.kind, literals=literals, nested=nested)


def _universe(name: str, panel: Panel, **params: object) -> dict[str, npt.NDArray[np.float64]]:
    registry = default_registry()
    return evaluate_universe(_call(name, registry, **params), panel, registry)


# --------------------------------------------------------------------------------------
# The Panel itself — it refuses more than it accepts
# --------------------------------------------------------------------------------------


def test_a_panel_cannot_be_built_without_point_in_time_membership() -> None:
    """The refusal that makes survivorship bias unrepresentable rather than merely discouraged."""
    bars = _levelled()
    partial = {s: v for s, v in _all_tradable().items() if s != SYMBOLS[-1]}
    with pytest.raises(DslError, match="survivorship"):
        Panel.build(bars, partial)


def test_a_panel_refuses_membership_for_a_symbol_it_has_no_bars_for() -> None:
    """The other direction of the same hole: the caller thinks the universe holds a name it never
    supplied, and ranking without it is survivorship arriving through a different door."""
    membership = _all_tradable()
    membership["S99"] = np.ones(DATES, dtype=np.bool_)
    with pytest.raises(DslError, match="disagree about the universe"):
        Panel.build(_levelled(), membership)


def test_each_symbol_gets_its_own_row_even_for_a_market_wide_word() -> None:
    """Breadth is one number for everybody, but not one *buffer* for everybody — a shared view
    would let a caller writing to one symbol's column silently rewrite every other symbol's."""
    breadth = _universe("breadth_pct_above_ma", _panel(), n=5)
    breadth["S00"][:] = -1.0
    assert breadth["S24"][-1] != -1.0


def test_a_panel_refuses_symbols_on_different_date_axes() -> None:
    """A mis-aligned panel ranks one symbol's Monday against another's Tuesday, silently."""
    bars = _levelled()
    bars["S07"] = _bars_at(7.0, start="2024-06-01")
    membership = _all_tradable()
    with pytest.raises(DslError, match="not aligned"):
        Panel.build(bars, membership)


def test_a_cross_sectional_word_refuses_a_single_symbol() -> None:
    """ "Rank among one stock" would be 1.0 on every bar — plausible, and meaningless."""
    registry = default_registry()
    with pytest.raises(DslError, match="needs the whole universe"):
        evaluate(_call("xs_rank", registry), _bars_at(1.0), registry)


def test_a_benchmark_word_refuses_a_panel_without_one() -> None:
    registry = default_registry()
    panel = _panel(benchmark=False)
    with pytest.raises(DslError, match="needs the benchmark"):
        evaluate_universe(_call("relative_strength", registry, n=5), panel, registry)


# --------------------------------------------------------------------------------------
# Ranking — hand-derivable by construction
# --------------------------------------------------------------------------------------


def test_rank_one_is_the_highest_value_and_the_order_is_exactly_the_price_order() -> None:
    """S24 sits at the top level, so it is rank 1; S00 is at the bottom, so it is rank 25."""
    ranks = _universe("xs_rank", _panel())
    assert ranks["S24"][-1] == pytest.approx(1.0)
    assert ranks["S23"][-1] == pytest.approx(2.0)
    assert ranks["S00"][-1] == pytest.approx(25.0)


def test_ties_share_the_average_rank_rather_than_the_alphabet() -> None:
    """Ordinal ranking would break ties by symbol order, handing every S0* name a permanent edge.

    Three symbols share the top price here, so they span ranks 1, 2 and 3 and each gets 2.0.
    """
    bars = _levelled()
    for tied in ("S00", "S01", "S02"):
        bars[tied] = _bars_at(99.0)
    membership = _all_tradable()
    ranks = _universe("xs_rank", Panel.build(bars, membership))
    for tied in ("S00", "S01", "S02"):
        assert ranks[tied][-1] == pytest.approx(2.0)
    assert ranks["S24"][-1] == pytest.approx(4.0)  # the best untied name follows the tied block


def test_percentile_is_one_for_the_best_and_zero_for_the_worst() -> None:
    percentile = _universe("xs_percentile", _panel())
    assert percentile["S24"][-1] == pytest.approx(1.0)
    assert percentile["S00"][-1] == pytest.approx(0.0)


def test_demeaning_uses_the_days_own_average_not_the_samples() -> None:
    """The whole content of the word. Both readings are one line and produce a plausible column.

    Levels 0..24 give a mean of 12.0 on every date, and every symbol's price rises 0.1 a day —
    so a sample-wide mean would be 12.0 plus the *middle* date's drift and would leave S12 with a
    non-zero, drifting demeaned value instead of exactly zero on every bar.
    """
    demeaned = _universe("xs_demean", _panel())
    assert demeaned["S12"] == pytest.approx(np.zeros(DATES))
    assert demeaned["S24"] == pytest.approx(np.full(DATES, 12.0))
    assert demeaned["S00"] == pytest.approx(np.full(DATES, -12.0))


def test_zscore_is_symmetric_about_the_middle_of_the_universe() -> None:
    z = _universe("xs_zscore", _panel())
    assert z["S12"][-1] == pytest.approx(0.0)
    assert z["S24"][-1] == pytest.approx(-z["S00"][-1])


def test_top_n_selects_exactly_n_names() -> None:
    top = _universe("xs_top_n", _panel(), n=5)
    chosen = [s for s in SYMBOLS if top[s][-1] == 1.0]
    assert chosen == ["S20", "S21", "S22", "S23", "S24"]


def test_bottom_n_selects_the_other_end() -> None:
    bottom = _universe("xs_bottom_n", _panel(), n=3)
    chosen = [s for s in SYMBOLS if bottom[s][-1] == 1.0]
    assert chosen == ["S00", "S01", "S02"]


def test_a_cohort_as_large_as_the_universe_is_not_a_selection() -> None:
    """`xs_top_n(n=25)` on 25 names would mark everybody — "buy everything", which nobody wrote."""
    top = _universe("xs_top_n", _panel(), n=25)
    assert all(np.isnan(top[s]).all() for s in SYMBOLS)


# --------------------------------------------------------------------------------------
# Point-in-time membership — the bug the time-axis sweep cannot see
# --------------------------------------------------------------------------------------


def test_a_symbol_that_had_not_listed_yet_is_absent_from_earlier_rankings() -> None:
    """The survivorship test. S24 is the strongest name in the universe — and it listed halfway
    through, so it must not appear in any ranking before that, and the names below it must rank
    one place better while it is absent."""
    listed_late = np.zeros(DATES, dtype=np.bool_)
    listed_late[15:] = True
    membership = _all_tradable()
    membership["S24"] = listed_late
    ranks = _universe("xs_rank", _panel(tradable=membership))

    assert np.isnan(ranks["S24"][14]), "a symbol that had not listed cannot hold a rank"
    assert ranks["S24"][15] == pytest.approx(1.0)
    assert ranks["S23"][14] == pytest.approx(1.0), "S23 is the best name while S24 is absent"
    assert ranks["S23"][15] == pytest.approx(2.0)


def test_an_untradable_symbol_does_not_dilute_the_universe_it_is_excluded_from() -> None:
    """Excluding a name must shrink the cross-section, not leave a hole in the middle of it."""
    membership = _all_tradable()
    membership["S24"] = np.zeros(DATES, dtype=np.bool_)
    percentile = _universe("xs_percentile", _panel(tradable=membership))
    assert np.isnan(percentile["S24"]).all()
    assert percentile["S23"][-1] == pytest.approx(1.0), "S23 is now the top of a 24-name universe"


def test_a_universe_too_thin_to_rank_reports_nothing_rather_than_a_number() -> None:
    """Ranking four names produces a confident-looking result from noise. Below the floor the
    whole date is refused — for everybody, not just for the names that fell out."""
    thin = tuple(f"S{i:02d}" for i in range(4))
    ranks = _universe("xs_rank", _panel(symbols=thin))
    assert all(np.isnan(ranks[s]).all() for s in thin)


def test_the_thin_universe_floor_can_be_raised_but_never_lowered() -> None:
    """Same shape as risk_r: a request below the floor is rejected, not quietly clamped up to it."""
    registry = default_registry()
    spec = registry.get("xs_rank").spec("min_symbols")
    assert spec is not None
    assert spec.validate(50, where="xs_rank") == 50
    with pytest.raises(DslError, match="rejected, not clamped"):
        spec.validate(5, where="xs_rank")


# --------------------------------------------------------------------------------------
# Breadth and the benchmark
# --------------------------------------------------------------------------------------


def test_breadth_is_one_when_every_name_is_above_its_own_average() -> None:
    """Every series in the fixture rises, so on a rising universe breadth saturates at 1.0."""
    breadth = _universe("breadth_pct_above_ma", _panel(), n=5)
    assert breadth["S00"][-1] == pytest.approx(1.0)
    assert breadth["S00"][-1] == breadth["S24"][-1], "breadth is one number for the whole market"


def test_relative_strength_is_zero_when_a_symbol_matches_the_index() -> None:
    """Excess return, not a ratio — a ratio flips sign whenever the index return crosses zero."""
    bars = _levelled()
    index = _bars_at(7.0)  # identical series to S07, so its excess return must be exactly zero
    membership = _all_tradable()
    rs = _universe("relative_strength", Panel.build(bars, membership, benchmark=index), n=5)
    assert rs["S07"][-1] == pytest.approx(0.0)
    assert rs["S24"][-1] < 0.0, "a higher-priced series gains a smaller *fraction* on equal drift"


def test_beta_to_an_identical_series_is_one() -> None:
    bars = _levelled()
    membership = _all_tradable()
    panel = Panel.build(bars, membership, benchmark=_bars_at(7.0))
    assert _universe("beta_to", panel, n=10)["S07"][-1] == pytest.approx(1.0)
    assert _universe("correlation_to", panel, n=10)["S07"][-1] == pytest.approx(1.0)


# --------------------------------------------------------------------------------------
# The panel-wide look-ahead sweep
# --------------------------------------------------------------------------------------


def _noisy_panel(size: int, seed: int = 20260805) -> Panel:
    """A random-walk universe where symbols list on staggered dates.

    Each symbol draws its own generator rather than sharing one. With a shared generator, asking
    for a shorter series changes where every *later* symbol starts reading the stream — so the
    truncated panel would be a different universe rather than a prefix of the same one, and the
    sweep below would report look-ahead in every word while proving nothing at all.
    """
    bars, membership = {}, {}
    for i, symbol in enumerate(SYMBOLS):
        close = np.cumsum(np.random.default_rng(seed + i).normal(0.0, 1.0, size)) + 100.0 + i
        bars[symbol] = Bars(
            ts=np.arange(np.datetime64("2024-01-01"), np.datetime64("2024-01-01") + size).astype(
                "datetime64[ns]"
            ),
            open=np.concatenate([close[:1], close[:-1]]),
            high=close + 1.0,
            low=close - 1.0,
            close=close,
            volume=np.full(size, 1000.0),
        )
        # Every symbol listing on a different date, so truncation and membership interact.
        live = np.zeros(size, dtype=np.bool_)
        live[i % 5 :] = True
        membership[symbol] = live
    index = _bars_at(500.0, size)
    return Panel.build(bars, membership, benchmark=index)


def test_the_truncated_panel_really_is_a_prefix_of_the_full_one() -> None:
    """Guards the sweep's own fixture. If truncation produced a *different* universe rather than a
    shorter one, the sweep would fail everywhere and prove nothing — which is exactly what the
    first version of it did."""
    full, short = _noisy_panel(120), _noisy_panel(60)
    for i, symbol in enumerate(SYMBOLS):
        assert symbol == full.symbols[i]
        np.testing.assert_array_equal(full.bars[i].close[:60], short.bars[i].close)
        np.testing.assert_array_equal(full.tradable[i][:60], short.tradable[i])


def test_no_panel_primitive_sees_the_future() -> None:
    """The per-symbol sweep, over a whole universe: truncate every symbol at once and demand each
    symbol's overlap match exactly.

    Fifteen words are skipped by ``test_no_primitive_sees_the_future`` because they cannot be
    evaluated against one symbol at all. Without this they would carry no look-ahead guard —
    which, given a cross-sectional word touches every symbol in the universe, is the worst place
    in the library to have a blind spot.
    """
    registry = default_registry()
    full_size = 120
    full = _noisy_panel(full_size)
    cuts = range(60, full_size, 10)

    checked = 0
    for primitive in registry:
        if not primitive.needs_panel or primitive.name == "xs_sector_neutral":
            continue
        node = _call(primitive.name, registry, n=5)
        whole = evaluate_universe(node, full, registry)
        for cut in cuts:
            prefix = evaluate_universe(node, _noisy_panel(cut), registry)
            for symbol in SYMBOLS:
                seen, early = whole[symbol][:cut], prefix[symbol]
                assert np.array_equal(np.isnan(seen), np.isnan(early)), (
                    f"{primitive.name} knows a value for {symbol} earlier when more future data "
                    f"is present (cut at bar {cut})"
                )
                both = ~np.isnan(seen) & ~np.isnan(early)
                np.testing.assert_allclose(
                    seen[both],
                    early[both],
                    rtol=1e-9,
                    atol=1e-9,
                    err_msg=f"{primitive.name} changes {symbol}'s past when the future is removed "
                    f"(cut at bar {cut})",
                )
        checked += 1
    assert checked == 14, f"only {checked} panel primitives were swept — the guard has gone slack"


def test_an_intraday_style_refusal_still_raises_at_panel_evaluation() -> None:
    registry = default_registry()
    with pytest.raises(DslError, match="cannot be computed"):
        evaluate_universe(_call("xs_sector_neutral", registry), _panel(), registry)


# --------------------------------------------------------------------------------------
# The sizing vocabulary — declarations, with the one guard that makes them safe to ship early
# --------------------------------------------------------------------------------------

_STRATEGY = """
name: cross-sectional momentum
version: 1
timeframe: 1d
universe: nse_liquid_100
entry:
  all:
    - xs_top_n:
        expr: {roc: {n: 5}}
        n: 10
    - index_above_ma: {n: 20}
exit:
  - stop_loss_atr: {atr_mult: 2.0}
  - time_stop: {bars: 21}
sizing:
  risk_r: 0.005
  weighting: equal_weight
"""


def test_the_cross_sectional_momentum_strategy_parses_and_evaluates() -> None:
    """The acceptance criterion: the shape of strategy 1.4c exists to make sayable."""
    registry = default_registry()
    candidate = parse_strategy(_STRATEGY, registry=registry, max_risk_r=0.01)
    assert candidate.sizing.weighting == "equal_weight"
    assert {"xs_top_n", "roc", "index_above_ma"} <= candidate.primitives_used()

    signal = evaluate_universe(candidate.entry, _panel(), registry)
    assert set(signal) == set(SYMBOLS)
    assert all(column.size == DATES for column in signal.values())


def test_a_strategy_without_a_weighting_scheme_still_parses_unchanged() -> None:
    """The key is optional on purpose: every strategy file written before 1.4c must still load,
    which is also why no schema version moved."""
    older = _STRATEGY.replace("  weighting: equal_weight\n", "")
    sizing = parse_strategy(older, registry=default_registry(), max_risk_r=0.01).sizing
    assert sizing.weighting == "equal_weight"
    assert sizing.vol_target_pct is None


def test_declaring_a_volatility_target_is_refused() -> None:
    """The partner of the weighting refusal, and it was missed on the first pass.

    ``vol_target_pct`` parsed, was range-checked, and was applied by nothing — so a strategy could
    declare a 15% volatility target, be backtested with no targeting whatsoever, and appear on the
    metric sheet as though it had been. 2e's own acceptance criteria said to reject it; only its
    sibling got done.
    """
    with_target = _STRATEGY.replace(
        "  weighting: equal_weight\n", "  weighting: equal_weight\n  vol_target_pct: 0.15\n"
    )
    with pytest.raises(DslError, match="nothing applies it"):
        parse_strategy(with_target, registry=default_registry(), max_risk_r=0.01)


def test_an_unknown_weighting_scheme_is_rejected() -> None:
    bad = _STRATEGY.replace("equal_weight", "martingale")
    with pytest.raises(DslError, match="weighting must be one of"):
        parse_strategy(bad, registry=default_registry(), max_risk_r=0.01)


@pytest.mark.parametrize("scheme", ["inverse_vol_weight", "rank_weight"])
def test_a_declared_but_unimplemented_weighting_scheme_is_refused(scheme: str) -> None:
    """In the vocabulary, implemented nowhere — so refused rather than accepted and ignored.

    This file used to assert the opposite. The shared fixture declared ``inverse_vol_weight`` and
    the acceptance test checked that it *parsed*, which it did — and then the simulator sized every
    position from ``risk_r`` and its own stop, exactly as it would have for ``equal_weight``. A
    green test on a strategy whose stated sizing scheme the engine never applied (finding F11).
    """
    bad = _STRATEGY.replace("equal_weight", scheme)
    with pytest.raises(DslError, match="implemented"):
        parse_strategy(bad, registry=default_registry(), max_risk_r=0.01)


def test_weights_that_spend_more_than_the_declared_risk_are_rejected() -> None:
    """The guard that makes it safe to ship sizing words before their consumer exists.

    Ten names at full risk_r each is ten times the exposure the strategy asked for, and nothing
    downstream would flag it — every individual position would look perfectly compliant.
    """
    sizing = Sizing(risk_r=0.005, weighting="equal_weight")
    assert_partitions_risk([0.1] * 10, sizing, where="portfolio")  # sums to 1.0 — a partition
    with pytest.raises(DslError, match="may only reduce"):
        assert_partitions_risk([1.0] * 10, sizing, where="portfolio")


def test_a_negative_weight_is_rejected_as_a_direction_not_a_size() -> None:
    with pytest.raises(DslError, match="not a size"):
        assert_partitions_risk([0.5, -0.2], Sizing(risk_r=0.005), where="portfolio")
