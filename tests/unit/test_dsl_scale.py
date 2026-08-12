"""Can this number be compared between two symbols? — task 2a, findings F1 and F22.

**The bug this file exists to make unrepeatable.** The vocabulary had a word called ``momentum``
that returned the change in *rupees*. Three strategies ranked their universe with it. On a panel
whose median share price is ₹470 and whose top 5% trade above ₹3,748, that is not a momentum
ranking — it is a standing bet on expensive shares, because a ₹3,000 stock that rises 5% gains
₹150 and a ₹300 stock that rises 40% gains ₹120. The strategies ran for fifteen simulated years,
produced ten names a day, and reported a plausible Sharpe. Nothing failed. Nothing warned.

That is the whole difficulty: **the wrong version works.** A unit test of ``momentum`` would have
passed (it computed exactly what it said), and a unit test of ``xs_top_n`` would have passed (it
ranked exactly what it was given). The defect lived in the join, where nobody was looking.

So the guard is a declared property — :attr:`Primitive.scale_free` — and this file checks it three
ways, in increasing order of how much they prove:

1. The **parser refuses** a rupee-denominated expression wherever symbols are compared.
2. The **classification is complete**: a new word cannot be added without answering the question.
3. The **classification is true**, by the split test below — which is the only one of the three
   that could catch a word marked comparable that isn't.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from icarus.strategy.dsl import (
    Bars,
    Call,
    DslError,
    IntParam,
    Kind,
    Panel,
    Primitive,
    Registry,
    evaluate,
    evaluate_universe,
    parse_strategy,
)
from icarus.strategy.library import default_registry

if TYPE_CHECKING:
    import numpy.typing as npt

STRATEGY_DIR = Path(__file__).resolve().parents[2] / "strategies"


def _strategy(rank_by: str = "roc: {n: 20}", entry: str | None = None) -> str:
    body = entry or "  above:\n    a: {close: {}}\n    b: {sma: {n: 20}}"
    return (
        f"name: t\nversion: 1\ntimeframe: 1d\nuniverse: nse_liquid\n"
        f"entry:\n{body}\n"
        f"rank_by:\n  {rank_by}\n"
        f"exit:\n  - stop_loss_pct: {{pct: 0.1}}\n"
        f"sizing:\n  risk_r: 0.005\n  weighting: equal_weight\n"
    )


def _parse(text: str) -> object:
    return parse_strategy(text, registry=default_registry(), max_risk_r=0.01)


# --------------------------------------------------------------------------------------
# The word itself is gone
# --------------------------------------------------------------------------------------


def test_the_word_momentum_no_longer_exists() -> None:
    """Deleted rather than renamed, and deliberately given no alias.

    An alias would have let all three strategy files keep parsing while still meaning the thing
    they did not say. Breaking them was the point: a file that says ``momentum`` has to be opened
    and a decision recorded about which quantity it actually wanted.
    """
    with pytest.raises(DslError, match="unknown primitive 'momentum'"):
        default_registry().get("momentum")


def test_the_rupee_form_survives_under_a_name_that_says_so() -> None:
    """Within one symbol, rupees are the right unit — it is only the cross-section that breaks."""
    registry = default_registry()
    assert registry.get("momentum_abs").scale_free is False
    assert registry.get("roc").scale_free is True


# --------------------------------------------------------------------------------------
# The parser refuses, at read time
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "expr",
    [
        "{sma: {n: 20}}",  # a price
        "{close: {}}",  # a price
        "{momentum_abs: {n: 20}}",  # the exact shape of the original bug
        "{atr: {n: 14}}",  # a price range
        "{macd: {}}",  # an EMA difference, in rupees
        "{volume: {}}",  # a share count
        "{obv: {}}",  # cumulative share count
    ],
)
def test_xs_top_n_refuses_an_expression_that_is_not_comparable_across_symbols(expr: str) -> None:
    entry = f"  xs_top_n:\n    expr: {expr}\n    n: 10"
    with pytest.raises(DslError, match="denominated in the symbol's own price"):
        _parse(_strategy(entry=entry))


def test_the_refusal_names_a_replacement_rather_than_only_complaining() -> None:
    """An error that says "no" and stops has moved the problem to whoever reads it."""
    entry = "  xs_top_n:\n    expr: {momentum_abs: {n: 20}}\n    n: 10"
    with pytest.raises(DslError) as caught:
        _parse(_strategy(entry=entry))
    assert "'roc'" in str(caught.value)


@pytest.mark.parametrize("word", ["sma: {n: 20}", "close: {}", "momentum_abs: {n: 20}"])
def test_rank_by_refuses_the_same_quantities(word: str) -> None:
    """``rank_by`` decides who gets the scarce slots, so it is a comparison between symbols too.

    This half mattered more than it looks: only one of the three shipped strategies ranked
    cross-sectionally at *entry*, but all three said ``rank_by: momentum``, so all three were
    filling the book most-expensive-first.
    """
    with pytest.raises(DslError, match="denominated in the symbol's own price"):
        _parse(_strategy(rank_by=word))


@pytest.mark.parametrize(
    "word", ["roc: {n: 20}", "natr: {n: 14}", "rsi: {n: 14}", "traded_value: {n: 20}"]
)
def test_rank_by_accepts_a_comparable_quantity(word: str) -> None:
    assert _parse(_strategy(rank_by=word)) is not None


def test_rank_by_refuses_xs_rank_because_its_ordering_runs_the_other_way() -> None:
    """Found by the code review of this very task, and it is F1's shape exactly.

    ``xs_rank`` counts upward from the best (1 = highest). ``rank_by`` fills the book from the
    largest value down. Put together they buy the *weakest* candidates — a ranker that computes
    cleanly and picks backwards. ``xs_percentile`` (1.0 = best) agrees with the sort and is fine.
    """
    with pytest.raises(DslError, match="may not rank"):
        _parse(_strategy(rank_by="xs_rank: {expr: {roc: {n: 20}}}"))
    assert _parse(_strategy(rank_by="xs_percentile: {expr: {roc: {n: 20}}}")) is not None


def test_refusing_xs_rank_in_rank_by_leaves_it_with_no_legal_position_at_all() -> None:
    """Stated as a test so the consequence cannot be forgotten (finding F26).

    ``rank_by`` is the only place a ``CROSS_SECTIONAL`` word may appear: ``_condition`` needs an
    event, and no ``SeriesParam`` in the library accepts the kind. So the refusal above does not
    narrow ``xs_rank``, it retires it. That is still the right trade — a word that reliably picks
    the losers is worse than a word nobody can reach, and ``xs_percentile`` does the same job with
    the ordering the sort expects.
    """
    entry = "  below:\n    a: {xs_rank: {expr: {roc: {n: 20}}}}\n    b: {constant: {value: 11.0}}"
    with pytest.raises(DslError, match="is a cross_sectional primitive but"):
        _parse(_strategy(entry=entry))


def test_a_misdeclared_requires_lt_pair_fails_when_the_word_is_built() -> None:
    """Not when some future strategy first happens to use it, which could be in production."""
    with pytest.raises(DslError, match="requires_lt"):
        Primitive(
            "invented",
            Kind.SERIES,
            "x",
            lambda bars, **_: bars.close,
            (IntParam("n", 2, 100, default=10),),
            requires_lt=(("skip", "n"),),
            scale_free=True,
        )


def test_a_price_is_still_free_to_meet_a_price_within_one_symbol() -> None:
    """The guard is on the cross-section only. ``close`` above ``sma(200)`` compares two rupee
    quantities on the same instrument, which is exactly right and must keep working."""
    assert _parse(_strategy()) is not None


# --------------------------------------------------------------------------------------
# Every word answers the question
# --------------------------------------------------------------------------------------


def test_no_word_in_the_vocabulary_leaves_it_undeclared() -> None:
    assert [p.name for p in default_registry() if p.scale_free is None] == []


def test_a_new_series_word_that_forgets_to_declare_is_refused_at_construction() -> None:
    """The check is in ``__post_init__``, so the failure is at import of the library module —
    before any test runs, and impossible to skip by not writing a test for the new word."""
    with pytest.raises(DslError, match="must declare"):
        Primitive("invented", Kind.SERIES, "x", lambda bars, **_: bars.close)


@pytest.mark.parametrize("kind", [Kind.CONTEXT, Kind.CROSS_SECTIONAL])
def test_the_other_two_undecidable_kinds_must_declare_as_well(kind: Kind) -> None:
    with pytest.raises(DslError, match="must declare"):
        Primitive("invented", kind, "x", lambda bars, **_: bars.close)


def test_an_event_and_a_level_are_derived_rather_than_declared() -> None:
    """A yes/no always compares; a price never does. Asking the author to restate that would be
    131 lines of ceremony, each one a place to paste the wrong value."""
    compute = lambda bars, **_: bars.close  # noqa: E731
    assert Primitive("e", Kind.EVENT, "x", compute).scale_free is True
    assert Primitive("l", Kind.LEVEL, "x", compute).scale_free is False


@pytest.mark.parametrize(("kind", "wrong"), [(Kind.EVENT, False), (Kind.LEVEL, True)])
def test_contradicting_the_derivation_is_an_error_not_an_override(kind: Kind, wrong: bool) -> None:
    with pytest.raises(DslError, match="is always"):
        Primitive("x", kind, "x", lambda bars, **_: bars.close, scale_free=wrong)


# --------------------------------------------------------------------------------------
# The split test — the only check that can catch a *wrong* classification
# --------------------------------------------------------------------------------------
#
# A share split changes a symbol's price and share count without changing anything about the
# company or how the market is treating it. So it is exactly the transform that separates the two
# classes: a quantity worth comparing between symbols must come out unchanged, and one that is not
# worth comparing must not. Nothing else here could catch `traded_value` being marked wrongly, or a
# future oscillator that quietly returns rupees.

_SPLIT = 7.0  # not a power of ten, so an accidental exactness cannot pass for invariance

# Only the words that *declared* the flag are swept. EVENT and LEVEL derive theirs from the kind,
# so there is no classification there to be wrong about — and including them would drag in sixty
# SMC zone words that need a hand-built chart to produce any value at all, whose all-nan output
# would pass both sweeps below without checking anything.
_DECLARED_KINDS = (Kind.SERIES, Kind.CONTEXT, Kind.CROSS_SECTIONAL)

# `zscore` and `percentile_rank` are handed `close`, which scales — so if they come out invariant
# it is the outer word normalising, not an invariant input.
_NESTED_CLOSE = ("zscore", "percentile_rank")

# `constant` is the one declared-not-comparable word that survives a split, because it ignores the
# bars entirely. Its units are whatever it is compared against (usually a price), and one number
# repeated across the universe is not an ordering — so False is right for it on both counts.
_INVARIANT_BUT_NOT_COMPARABLE = frozenset({"constant"})


def _series(closes: npt.NDArray[np.float64], volume: npt.NDArray[np.float64]) -> Bars:
    """A random walk with a genuinely random intrabar range.

    The obvious construction — ``high = max(open, close) + c`` for a fixed ``c`` — looks fine and
    silently defeats the whole structure half of the vocabulary: consecutive bars share a close, so
    a local peak produces two *equal* highs, no swing is ever strictly confirmed, and every SMC
    word returns all-nan. They would then pass both sweeps below having computed nothing.
    """
    rng = np.random.default_rng(11)
    open_ = np.concatenate([closes[:1], closes[:-1]])
    return Bars(
        ts=np.arange(closes.size).astype("datetime64[D]").astype("datetime64[ns]"),
        open=open_,
        high=np.maximum(open_, closes) + np.abs(rng.normal(0.0, 1.0, closes.size)) + 0.05,
        low=np.minimum(open_, closes) - np.abs(rng.normal(0.0, 1.0, closes.size)) - 0.05,
        close=closes,
        volume=volume,
    )


def _split(bars: Bars) -> Bars:
    """The same company at ``_SPLIT`` times the price and a ``_SPLIT``-th of the shares."""
    return Bars(
        ts=bars.ts,
        open=bars.open * _SPLIT,
        high=bars.high * _SPLIT,
        low=bars.low * _SPLIT,
        close=bars.close * _SPLIT,
        volume=bars.volume / _SPLIT,
    )


def _sweepable(registry: Registry) -> list[Primitive]:
    return [
        p
        for p in registry
        if p.kind in _DECLARED_KINDS and not (p.intraday_only or p.requires_feed or p.needs_panel)
    ]


def _invoke(primitive: Primitive, bars: Bars, registry: Registry) -> npt.NDArray[np.float64]:
    literals: dict[str, int | float | str] = {}
    nested: dict[str, Call] = {}
    for spec in primitive.params:
        default = getattr(spec, "default", None)
        if primitive.name in _NESTED_CLOSE and spec.name == "series":
            nested["series"] = Call(primitive="close", kind=Kind.SERIES, literals={}, nested={})
        elif default is not None:
            literals[spec.name] = default
        else:
            literals[spec.name] = 5 if spec.name != "value" else 1.0
    call = Call(primitive=primitive.name, kind=primitive.kind, literals=literals, nested=nested)
    return evaluate(call, bars, registry)


def _both(primitive: Primitive, registry: Registry) -> tuple[npt.NDArray[np.float64], ...]:
    rng = np.random.default_rng(20260812)
    closes = np.cumsum(rng.normal(0.0, 1.5, 400)) + 200.0
    volume = np.abs(rng.normal(5.0e5, 1.0e5, 400))
    plain = _series(closes, volume)
    return _invoke(primitive, plain, registry), _invoke(primitive, _split(plain), registry)


def test_the_split_test_can_tell_the_two_classes_apart() -> None:
    """Guards the guard: if the transform below were a no-op, every assertion in the two sweeps
    would pass vacuously and the file would prove nothing."""
    registry = default_registry()
    before, after = _both(registry.get("sma"), registry)
    assert not np.allclose(before, after, equal_nan=True)


@pytest.mark.parametrize(
    "name",
    sorted(p.name for p in _sweepable(default_registry()) if p.scale_free),
)
def test_a_word_marked_comparable_survives_a_split_unchanged(name: str) -> None:
    registry = default_registry()
    before, after = _both(registry.get(name), registry)
    finite = ~np.isnan(before)
    assert finite.any(), f"{name} produced no values on the test series — nothing was checked"
    assert np.allclose(before[finite], after[finite], rtol=1e-9, atol=1e-9), (
        f"{name} is declared scale_free=True but changes when the same company is re-denominated. "
        f"Either it is rupee-denominated and the flag is wrong, or the flag is right and the "
        f"computation is not doing what its name says."
    )


@pytest.mark.parametrize(
    "name",
    sorted(
        p.name
        for p in _sweepable(default_registry())
        if not p.scale_free and p.name not in _INVARIANT_BUT_NOT_COMPARABLE
    ),
)
def test_a_word_marked_not_comparable_really_does_move_with_the_denomination(name: str) -> None:
    """The other direction, which stops the flag drifting conservative.

    A word marked ``False`` "just to be safe" is not free: it is a word no strategy can rank by,
    silently removed from the vocabulary. If it survives the split it belongs in the other class.
    """
    registry = default_registry()
    before, after = _both(registry.get(name), registry)
    finite = ~np.isnan(before) & ~np.isnan(after)
    assert finite.any(), f"{name} produced no values on the test series — nothing was checked"
    assert not np.allclose(before[finite], after[finite], rtol=1e-9, atol=1e-9), (
        f"{name} is declared scale_free=False but is unaffected by re-denomination, so it is "
        f"comparable across symbols and is being kept out of every ranking for no reason."
    )


# --------------------------------------------------------------------------------------
# What the bug actually did to a ranking
# --------------------------------------------------------------------------------------


def _grower(level: float, growth: float, size: int = 30) -> Bars:
    """A symbol starting at ``level`` and rising ``growth`` over the first 20 bars."""
    close = level * (1.0 + growth * np.minimum(np.arange(size, dtype=np.float64), 20.0) / 20.0)
    return Bars(
        ts=np.arange(np.datetime64("2024-01-01"), np.datetime64("2024-01-01") + size).astype(
            "datetime64[ns]"
        ),
        open=close.copy(),
        high=close * 1.001,
        low=close * 0.999,
        close=close,
        volume=np.full(size, 1000.0),
    )


def test_the_two_rankings_pick_different_winners_and_only_one_is_momentum() -> None:
    """The bug, reproduced at the smallest scale that shows it.

    A ₹3,000 share that gained 5% and a ₹300 share that gained 40%, in a universe of twenty-five.
    ``roc`` puts the 40% first, which is what "the strongest name" means. ``momentum_abs`` puts the
    5% first, because ₹150 is more rupees than ₹120. Both rankings are computed correctly; they are
    answering different questions, and for fifteen simulated years the strategies asked the second
    one while their comments described the first.
    """
    registry = default_registry()
    bars = {"EXPENSIVE": _grower(3000.0, 0.05), "CHEAP": _grower(300.0, 0.40)}
    # Filler so the twenty-name floor is met; none of them beats either headline name on gain.
    bars.update({f"F{i:02d}": _grower(100.0 + 100.0 * i, 0.01) for i in range(23)})
    panel = Panel.build(bars, {s: np.ones(30, dtype=np.bool_) for s in bars}, benchmark=None)

    def winner(word: str) -> str:
        inner = Call(primitive=word, kind=Kind.SERIES, literals={"n": 20}, nested={})
        ranked = evaluate_universe(
            Call(
                primitive="xs_rank",
                kind=Kind.CROSS_SECTIONAL,
                literals={"min_symbols": 20},
                nested={"expr": inner},
            ),
            panel,
            registry,
        )
        return min(ranked, key=lambda s: ranked[s][20])

    assert winner("roc") == "CHEAP"
    assert winner("momentum_abs") == "EXPENSIVE"


# --------------------------------------------------------------------------------------
# roc_skip — 12-1 momentum becomes expressible (F22)
# --------------------------------------------------------------------------------------


def test_roc_skip_measures_the_window_that_ends_before_the_recent_bars() -> None:
    """``skip`` is not a refinement of the factor, it *is* the factor: the most recent month
    carries short-horizon reversal, which points the other way and cancels much of the signal."""
    registry = default_registry()
    closes = np.array([100.0] * 5 + [120.0] * 3 + [90.0] * 3, dtype=np.float64)
    bars = _series(closes, np.full(closes.size, 1.0e5))
    call = Call(primitive="roc_skip", kind=Kind.SERIES, literals={"n": 10, "skip": 3}, nested={})
    # bar 10: close 10 bars back is 100.0, close 3 bars back is 120.0 -> +20%, and the -25%
    # collapse in the final three bars is deliberately not counted.
    assert evaluate(call, bars, registry)[10] == pytest.approx(20.0)


def test_roc_skip_warms_up_over_the_longer_of_its_two_windows() -> None:
    registry = default_registry()
    closes = np.linspace(100.0, 200.0, 40)
    bars = _series(closes, np.full(closes.size, 1.0e5))
    call = Call(primitive="roc_skip", kind=Kind.SERIES, literals={"n": 20, "skip": 5}, nested={})
    out = evaluate(call, bars, registry)
    assert np.isnan(out[:20]).all()
    assert np.isfinite(out[20:]).all()


@pytest.mark.parametrize(("n", "skip"), [(20, 20), (20, 30)])
def test_roc_skip_refuses_a_window_that_ends_before_it_starts(n: int, skip: int) -> None:
    """Both parameters are individually in range; only the pair is nonsense. Returning ``nan``
    would have been the silent version of the same refusal."""
    entry = (
        f"  above:\n    a: {{roc_skip: {{n: {n}, skip: {skip}}}}}\n"
        f"    b: {{constant: {{value: 0.0}}}}"
    )
    with pytest.raises(DslError, match="must be less than"):
        _parse(_strategy(entry=entry))


# --------------------------------------------------------------------------------------
# The shipped strategy files
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("path", sorted(STRATEGY_DIR.glob("*.yaml")), ids=lambda p: p.stem)
def test_every_shipped_strategy_parses_and_ranks_on_a_comparable_quantity(path: Path) -> None:
    """The regression for F1 itself. Had this existed on 2026-08-07, all three files would have
    failed it on the day they were written, before a single backtest was run."""
    candidate = _parse(path.read_text(encoding="utf-8"))
    rank_by = candidate.rank_by  # type: ignore[attr-defined]
    if rank_by is not None:
        assert default_registry().get(rank_by.primitive).scale_free, path.name
