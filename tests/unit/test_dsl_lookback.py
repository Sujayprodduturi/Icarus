"""How far back does a strategy really look? — task 2b, findings F3 and F28.

The backtester uses one number, ``longest_lookback``, for two jobs:

* **The lead-in.** To simulate a span it reads that many sessions of history in front of it, and
  refuses to trade during them. Too small and the indicator is blank or half-formed at the start.
* **The purge.** Walk-forward keeps a gap between the training stretch and the test stretch, because
  a 200-session average on the first test day is *made of* training days. Too small and the exam
  contains the answers.

**What was wrong (F3): it read the ``entry`` block only.** Not ``rank_by``, which decides who gets
the scarce slots, and not ``exit``, which carries the ATR period that sizes the stop. Two of the
three shipped strategies were unaffected purely because their entry happened to be their widest
window; ``baseline_buy_and_hold`` was not, and had been selecting alphabetically for its entire
out-of-sample history as a result.

**What was also wrong (F28): three words have no honest lead-in at any size, and are granted zero.**
``obv`` and ``ad_line`` are running totals from the first bar. ``psar`` is stranger — it does not
converge as history grows, it *oscillates*, because its acceleration factor resets at whichever
trend reversal happens to fall first in the slice; and both its parameters are decimals, so the
largest-integer rule finds no number in it at all.

**What is still wrong (F29), recorded here but not fixed:** the lead-in a word is granted is its own
widest parameter, and for about a hundred words that is too little. The last test pins the count.

Every claim above is *measured* by the sweep at the bottom rather than asserted. That matters: two
earlier drafts of this file described ``psar`` wrongly — first as never-settling, then as
slow-but-finite — and the assertions are what caught both.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pytest

from icarus.engine.backtest import longest_lookback
from icarus.strategy.dsl import (
    Bars,
    Call,
    DslError,
    Kind,
    Primitive,
    StrategyCandidate,
    evaluate,
    parse_strategy,
)
from icarus.strategy.library import default_registry

if TYPE_CHECKING:
    import numpy.typing as npt

STRATEGY_DIR = Path(__file__).resolve().parents[2] / "strategies"

_ENTRY = "  above:\n    a: {close: {}}\n    b: {constant: {value: 0.0}}"


def _strategy(entry: str = _ENTRY, rank_by: str | None = None, exit_rule: str | None = None) -> str:
    rank = f"rank_by:\n  {rank_by}\n" if rank_by else ""
    return (
        f"name: t\nversion: 1\ntimeframe: 1d\nuniverse: nse_liquid\n"
        f"entry:\n{entry}\n{rank}"
        f"exit:\n  - {exit_rule or 'stop_loss_pct: {pct: 0.1}'}\n"
        f"sizing:\n  risk_r: 0.005\n  weighting: equal_weight\n"
    )


def _parse(text: str) -> StrategyCandidate:
    return parse_strategy(text, registry=default_registry(), max_risk_r=0.01)


# --------------------------------------------------------------------------------------
# All three blocks, not just entry
# --------------------------------------------------------------------------------------


def test_an_entry_with_no_window_at_all_reports_nothing_to_wait_for() -> None:
    """The starting point: "price is above zero" contains no integer, so the answer is zero.

    That is correct *for the entry alone*, which is exactly why reading only the entry was so easy
    to miss — the function was not buggy, it was pointed at a third of the strategy.
    """
    assert longest_lookback(_parse(_strategy())) == 0


def test_the_ranker_counts() -> None:
    """F3's live casualty, at the smallest scale that shows it."""
    assert longest_lookback(_parse(_strategy(rank_by="roc: {n: 252}"))) == 252


def test_the_exit_counts() -> None:
    """A stop is computed over the same span as everything else and needs the same history."""
    assert (
        longest_lookback(
            _parse(_strategy(exit_rule="stop_loss_atr: {atr_mult: 2.0, atr_period: 30}"))
        )
        == 30
    )


def test_the_widest_of_the_three_wins() -> None:
    strategy = _strategy(
        entry="  above:\n    a: {close: {}}\n    b: {sma: {n: 50}}",
        rank_by="roc: {n: 120}",
        exit_rule="stop_loss_atr: {atr_mult: 2.0, atr_period: 30}",
    )
    assert longest_lookback(_parse(strategy)) == 120


def test_a_holding_period_is_counted_too_and_that_is_deliberate() -> None:
    """``time_stop(bars: 40)`` is not a lookback. Counting it purges forty sessions nobody needed.

    Left in on purpose: the alternative is a list of which parameter names are lookbacks, and the
    parameter names in this vocabulary (``n``, ``k``, ``period``, ``legs``, ``search``) do not
    support one. Over-purging costs a little data; under-purging leaks with no symptom at all.
    """
    both = "stop_loss_pct: {pct: 0.1}\n  - time_stop: {bars: 40}"
    assert longest_lookback(_parse(_strategy(exit_rule=both))) == 40


def test_a_boolean_is_not_a_one_session_lookback() -> None:
    """``bool`` is an ``int`` in Python, so a flag would otherwise read as a lookback of 1."""
    candidate = _parse(_strategy())
    inflated = candidate.model_copy(
        update={"exits": (candidate.exits[0].model_copy(update={"literals": {"flag": True}}),)}
    )
    assert longest_lookback(inflated) == 0


@pytest.mark.parametrize("path", sorted(STRATEGY_DIR.glob("*.yaml")), ids=lambda p: p.stem)
def test_no_shipped_strategy_looks_further_back_than_it_is_granted(path: Path) -> None:
    """The regression for F3 itself, stated as the property rather than as three numbers."""
    candidate = _parse(path.read_text(encoding="utf-8"))
    granted = longest_lookback(candidate)
    wanted = [
        value
        for call in ([candidate.rank_by] if candidate.rank_by else [])
        for value in call.literals.values()
        if isinstance(value, int) and not isinstance(value, bool)
    ]
    wanted += [
        value
        for rule in candidate.exits
        for value in rule.literals.values()
        if isinstance(value, int) and not isinstance(value, bool)
    ]
    assert granted >= max(wanted, default=0), (
        f"{path.name} is granted {granted} sessions of history but its ranker or its exit asks "
        f"for {max(wanted, default=0)}"
    )


# --------------------------------------------------------------------------------------
# Words no lead-in can satisfy
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize("word", ["obv", "ad_line"])
def test_a_running_total_is_refused_when_the_strategy_is_read(word: str) -> None:
    entry = f"  above:\n    a: {{{word}: {{}}}}\n    b: {{constant: {{value: 0.0}}}}"
    with pytest.raises(DslError, match="how much history it needs"):
        _parse(_strategy(entry=entry))


def test_psar_is_refused_too() -> None:
    """Doubly unreachable: its state persists for the length of a trend, and both its parameters
    are decimals — so the largest-integer rule sees no number and would grant it zero."""
    entry = "  above:\n    a: {close: {}}\n    b: {psar: {step: 0.02, maximum: 0.2}}"
    with pytest.raises(DslError, match="how much history it needs"):
        _parse(_strategy(entry=entry))


def test_the_refusal_reaches_a_ranker_as_well_as_an_entry() -> None:
    with pytest.raises(DslError, match="how much history it needs"):
        _parse(_strategy(rank_by="obv: {}"))


def test_exactly_three_words_claim_to_be_unbounded() -> None:
    """Pinned so that adding a fourth is a decision somebody makes, not a line somebody copies."""
    unbounded = sorted(p.name for p in default_registry() if p.opaque_lookback)
    assert unbounded == ["ad_line", "obv", "psar"]


def test_the_flag_defaults_to_false_so_it_cannot_be_forgotten_into_being_true() -> None:
    assert (
        Primitive(
            "invented", Kind.SERIES, "x", lambda bars, **_: bars.close, scale_free=True
        ).opaque_lookback
        is False
    )


# --------------------------------------------------------------------------------------
# The measured sweep — does history actually stop mattering?
# --------------------------------------------------------------------------------------
#
# For each word, compute it over a long series, then again over a short tail with a generous
# lead-in in front, and compare the overlap. A word that has genuinely stopped depending on older
# bars gives the same answer both times. One that has not, does not.
#
# The lead-in below is far wider than any word's own window, so this is not asking "is the warm-up
# exactly right" — that is a separate and much larger question (finding F29). It asks only the
# narrow thing the `opaque_lookback` flag claims: whether *any* finite history is enough.

_TAIL = 3
_GENEROUS = 900
_SERIES = 1600


def _bars(seed: int, span: slice) -> Bars:
    rng = np.random.default_rng(seed)
    close = np.cumsum(rng.normal(0.0, 1.5, _SERIES)) + 400.0
    open_ = np.concatenate([close[:1], close[:-1]])
    high = np.maximum(open_, close) + np.abs(rng.normal(0.0, 1.0, _SERIES)) + 0.05
    low = np.minimum(open_, close) - np.abs(rng.normal(0.0, 1.0, _SERIES)) - 0.05
    volume = np.abs(rng.normal(5.0e5, 1.0e5, _SERIES))
    start = np.datetime64("2011-01-03")
    ts = np.arange(start, start + _SERIES).astype("datetime64[ns]")
    return Bars(
        ts=ts[span],
        open=open_[span],
        high=high[span],
        low=low[span],
        close=close[span],
        volume=volume[span],
    )


def _call_of(primitive: Primitive) -> Call:
    literals: dict[str, int | float | str] = {}
    nested: dict[str, Call] = {}
    close = Call(primitive="close", kind=Kind.SERIES, literals={}, nested={})
    for spec in primitive.params:
        default = getattr(spec, "default", None)
        if spec.name in ("series", "a"):
            nested[spec.name] = close
        elif spec.name == "b":
            nested[spec.name] = Call(primitive="open", kind=Kind.SERIES, literals={}, nested={})
        elif default is not None:
            literals[spec.name] = default
        else:
            # 60 rather than something small so that a required window is wider than every
            # *default* in the vocabulary (the largest is 26). With 5 here, `roc_skip` came out as
            # n=5 / skip=21 — a pair the parser refuses outright — and the meaningless column it
            # produced compared equal to itself, quietly dropping the word from the sweep.
            literals[spec.name] = 1.0 if spec.name == "value" else 60
    for lower, upper in primitive.requires_lt:
        lo_v, hi_v = literals[lower], literals[upper]
        assert isinstance(lo_v, int | float) and isinstance(hi_v, int | float), (
            f"{primitive.name} declares an ordered pair on a non-numeric parameter"
        )
        assert lo_v < hi_v, (
            f"the sweep built {primitive.name} with {lower}={literals[lower]} and "
            f"{upper}={literals[upper]}, which the parser would reject — it would be measuring a "
            f"column no strategy can ask for"
        )
    return Call(primitive=primitive.name, kind=primitive.kind, literals=literals, nested=nested)


def _agrees(primitive: Primitive, seed: int, lead_in: int) -> bool | None:
    """Does ``lead_in`` sessions of history give the same answer as the whole series?

    ``None`` means **nothing was compared** — the word is ``nan`` on both sides across the whole
    tail, so there is no evidence either way. An earlier version returned ``True`` there, which
    scored "never measured" as "agrees" and silently excused six zone words (``bpr_top``,
    ``darvas_box_top``, the ``fvg_down_*`` pair and their partners) from the F29 count below —
    precisely the blank-not-wrong class that count exists to describe.
    """
    registry = default_registry()
    call = _call_of(primitive)
    whole = evaluate(call, _bars(seed, slice(None)), registry)[-_TAIL:]
    cut = evaluate(call, _bars(seed, slice(_SERIES - _TAIL - lead_in, _SERIES)), registry)[-_TAIL:]
    known: npt.NDArray[np.bool_] = ~np.isnan(whole)
    if not known.any() and not (~np.isnan(cut)).any():
        return None
    if not bool((np.isnan(whole) == np.isnan(cut)).all()):
        return False
    return bool(np.allclose(whole[known], cut[known], rtol=1e-6, atol=1e-6))


def _granted(primitive: Primitive) -> int:
    """What ``longest_lookback`` would allow a strategy whose widest word is this one.

    Mirrors ``_whole_numbers`` in the engine, ``bool`` exclusion included — a model of production
    that quietly differs from it is worse than no model.
    """
    return max(
        (
            v
            for v in _call_of(primitive).literals.values()
            if isinstance(v, int) and not isinstance(v, bool)
        ),
        default=0,
    )


def _measurable() -> list[Primitive]:
    return [
        p for p in default_registry() if not (p.intraday_only or p.requires_feed or p.needs_panel)
    ]


@pytest.mark.parametrize("name", sorted(p.name for p in _measurable() if p.opaque_lookback))
def test_a_word_marked_opaque_is_wrong_at_the_lead_in_it_would_be_granted(name: str) -> None:
    """What justifies the refusal, measured rather than asserted.

    A word wrongly marked here is silently deleted from the vocabulary, so the flag needs evidence
    in both directions: this is the "it really is broken" half.
    """
    primitive = default_registry().get(name)
    verdicts = [_agrees(primitive, seed, _granted(primitive)) for seed in (1, 2, 3)]
    assert any(v is not None for v in verdicts), f"{name} produced no values — nothing was tested"
    assert not any(verdicts), (
        f"{name} is marked opaque_lookback=True but already agrees with full history at the "
        f"{_granted(primitive)} sessions it would be granted, so it is refused for no reason."
    )


@pytest.mark.parametrize("name", ["obv", "ad_line"])
def test_a_running_total_never_settles_however_much_history_it_is_given(name: str) -> None:
    """The strongest form: not "needs more", but "no amount is enough"."""
    primitive = default_registry().get(name)
    assert not any(_agrees(primitive, seed, _GENEROUS) for seed in (1, 2, 3))


def test_psar_does_not_converge_it_oscillates() -> None:
    """The measurement that settled how ``psar`` should be described.

    A first draft called it "unbounded", an assertion here disproved that (it matched full history
    at 900 sessions on one seed), and a second draft called it "slow but finite". Both were wrong.
    Sweeping the lead-in shows it agreeing at 300, disagreeing at 700, agreeing again at 900 — the
    acceleration factor resets at whatever reversal happens to fall first in the slice, so where the
    history starts changes the answer *without* converging as it grows. There is no lead-in anyone
    could name and defend, which is the real reason it is refused.
    """
    primitive = default_registry().get("psar")
    assert _granted(primitive) == 0  # both parameters are decimals; the rule sees no number
    grid = (0, 100, 300, 500, 700, 900, 1200)
    reliable = [lead for lead in grid if all(_agrees(primitive, s, lead) for s in (1, 2, 3))]
    assert reliable == [], f"psar reproduces full history at every seed for lead-ins {reliable}"


def test_how_many_words_are_still_short_changed_is_pinned_not_ignored() -> None:
    """Finding F29, recorded as a number so it cannot grow quietly.

    The lead-in a word is granted equals its own widest parameter — and for most of the vocabulary
    that is not enough. A Wilder average is recursive, so ``rsi(14)`` given exactly 14 sessions is
    **32% out** on the first bar of a span; ``macd`` is 41% out. Structure words are blank rather
    than wrong, because the swing that would confirm them is behind the cut. Neither is fixed here:
    2b's job was the scope bug (F3) and the three words that get nothing at all (F28).

    The counts are pinned rather than asserted to zero because zero is currently false, and a test
    that asserts a comfortable falsehood is worse than no test.

    **Three buckets, not two.** The words that produce no value at all on this series are counted
    separately instead of being folded into "fine": they are the SMC zone words that need a chart
    shape a random walk does not contain, and calling them fine would be the same vacuous pass that
    finding F24 records against the look-ahead sweep. An earlier version of this test did exactly
    that and understated the first bucket by six.
    """
    short, unmeasured = [], []
    for p in _measurable():
        if p.opaque_lookback:
            continue
        verdicts = [_agrees(p, seed, _granted(p)) for seed in (1, 2, 3)]
        if all(v is None for v in verdicts):
            unmeasured.append(p.name)
        elif not all(v in (True, None) for v in verdicts):
            short.append(p.name)
    assert (len(short), len(unmeasured)) == (112, 4), (
        f"{len(short)} words disagree with full history at the lead-in they are granted and "
        f"{len(unmeasured)} produced nothing to compare, against the (112, 4) recorded when F29 "
        f"was raised. If the first went down, update it and say what fixed it; if either went up, "
        f"a word was added without enough history or without a chart shape this series produces."
    )


# --------------------------------------------------------------------------------------
# Parameter pairs that are individually legal and jointly meaningless (finding F39)
# --------------------------------------------------------------------------------------

_ORDERED = {
    "macd": ("fast", "slow"),
    "macd_signal": ("fast", "slow"),
    "macd_hist": ("fast", "slow"),
    "ppo": ("fast", "slow"),
    "kama": ("fast", "slow"),
    "roc_skip": ("skip", "n"),
}

# Words that take a plausible-looking ordered pair and are deliberately NOT constrained, with the
# measurement that settled each one. This half of the list is the more important half: the first
# version of this table had fifteen entries, nine of them arrived at by pattern-matching parameter
# *names* rather than by asking what the word does, and every one of those nine refused
# configurations that are perfectly well defined.
_UNCONSTRAINED = {
    "trend_template": "takes fast/slow; transposing them changes the output not at all",
    "vol_percentile": "n/lookback transposed is a coarse percentile — weak, not degenerate",
    "stage": "slope_n >= n is a longer-horizon slope on a shorter MA; meaningful",
    "stage_basing": "as stage",
    "stage_advancing": "as stage",
    "stage_topping": "as stage",
    "stage_declining": "as stage",
    "darvas_box_top": "confirm >= n asks a short high to hold longer; meaningful",
    "darvas_box_bottom": "as darvas_box_top",
    "darvas_breakout_up": "as darvas_box_top",
}


def test_every_word_with_an_ordered_pair_declares_it() -> None:
    """The list is the finding, and the test of membership is **inversion, not oddity**.

    ``requires_lt`` shipped in task 2b with one user, and 2f then applied it to fourteen more by
    scanning for parameter names that looked ordered — ``fast``/``slow``, ``confirm``/``n``,
    ``slope_n``/``n``. Nine of those fourteen were wrong, and wrong in the direction that matters
    least visibly: the parser began refusing strategies that were fine. That is the same
    "fixed the instance, not the class" reflex this repo keeps catching, wearing the opposite
    costume — over-applying a rule is as much a failure to think as under-applying it.

    The standard a pair has to meet is that transposing it makes the word mean **the opposite of
    its own name**, so a strategy reading ``macd > 0`` is silently short. Measured on real bars:
    ``macd``, ``macd_signal``, ``macd_hist``, ``ppo`` and ``roc_skip`` flip sign on 100% of bars;
    ``kama``'s correlation between trend-cleanliness and smoothing speed goes +0.978 to -0.978, so
    it smooths *most* exactly where its docstring says it smooths least. Merely unusual is not
    enough — see :data:`_UNCONSTRAINED`.
    """
    declared = {p.name: p.requires_lt for p in default_registry() if p.requires_lt}
    assert {k: v[0] for k, v in declared.items()} == _ORDERED


@pytest.mark.parametrize("word", sorted(_UNCONSTRAINED))
def test_a_plausible_pair_that_was_measured_and_left_alone(word: str) -> None:
    """Refusing a legal configuration is a real cost, so each of these carries its measurement.

    Named individually rather than asserted as "everything else is unconstrained", because the
    point is that somebody looked at each one. A future word that needs a constraint should fail
    :func:`test_every_word_with_an_ordered_pair_declares_it`, not slip through here.
    """
    assert not default_registry().get(word).requires_lt, _UNCONSTRAINED[word]


@pytest.mark.parametrize("word", sorted(_ORDERED))
def test_the_transposed_pair_is_refused_at_parse_time(word: str) -> None:
    lo, hi = _ORDERED[word]
    primitive = default_registry().get(word)
    literals = {
        s.name: getattr(s, "default", None) or 5 for s in primitive.params if s.name != "series"
    }
    literals[lo], literals[hi] = 40, 10  # transposed: lo must be < hi
    lines = ["  above:", f"    a: {{{word}: {literals}}}", "    b: {constant: {value: 0.0}}"]
    with pytest.raises(DslError, match="must be less than"):
        _parse(_strategy(entry="\n".join(lines)))


def test_the_constrained_words_really_do_invert() -> None:
    """The membership rule, enforced rather than described.

    Without this, :data:`_ORDERED` is an assertion that somebody once measured something. Here the
    sign flip is re-measured on every run for the five sign-carrying words, so a word cannot be
    added to the list on the strength of its parameter names — which is exactly how nine wrong
    entries got in.
    """
    registry = default_registry()
    bars = _bars(11, slice(None))
    for word in ("macd", "macd_signal", "macd_hist", "ppo", "roc_skip"):
        primitive = registry.get(word)
        lower, upper = _ORDERED[word]
        call = _call_of(primitive)
        ordered = evaluate(call, bars, registry)
        swapped = Call(
            primitive=word,
            kind=primitive.kind,
            literals={
                **call.literals,
                lower: call.literals[upper],
                upper: call.literals[lower],
            },
            nested=call.nested,
        )
        transposed = evaluate(swapped, bars, registry)
        both = ~np.isnan(ordered) & ~np.isnan(transposed)
        both &= (np.abs(ordered) > 1e-9) & (np.abs(transposed) > 1e-9)
        assert both.sum() > 100, f"{word}: too few comparable bars to judge"
        flipped = float((np.sign(ordered[both]) != np.sign(transposed[both])).mean())
        assert flipped == 1.0, (
            f"{word} transposed does NOT mean the opposite — it flips sign on only {flipped:.1%} "
            f"of bars, so `requires_lt` is refusing a configuration that is merely unusual"
        )
