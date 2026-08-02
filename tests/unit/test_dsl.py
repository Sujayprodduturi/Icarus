"""Tests for the strategy DSL grammar and its refusals (task 1.4a).

**The refusals are the point of this file.** A parser that accepts a valid strategy is easy and
proves little; what keeps a bad strategy off real money is the set of things it declines to do. So
the happy-path tests here are few and the rejection tests are many, and each rejection test names
the specific harm it prevents rather than just asserting that an exception was raised.

The two most dangerous cases are the *silent* ones, and both get their own section: a primitive
that cannot be computed honestly on the available data (intraday-only, or needing an unbuilt feed)
must **raise**, because the alternative — quietly returning a neutral value — produces a backtest
reporting an edge that depended on a filter which was never running.
"""

from __future__ import annotations

import pytest

from icarus.strategy.dsl import (
    Composite,
    DslError,
    Kind,
    Registry,
    StrategyCandidate,
    Timeframe,
    parse_strategy,
)
from icarus.strategy.library import default_registry

MAX_RISK_R = 0.005

VALID = """
name: ma_cross_baseline
version: 1
timeframe: 1d
universe: nifty_100
entry:
  all:
    - cross_above:
        a: {sma: {n: 20}}
        b: {sma: {n: 50}}
    - below:
        a: {rsi: {n: 14}}
        b: {close: {}}
exit:
  - stop_loss_atr: {atr_mult: 1.5, atr_period: 14}
  - take_profit_r: {r_multiple: 2.0}
  - time_stop: {bars: 15}
sizing:
  risk_r: 0.004
"""


@pytest.fixture
def registry() -> Registry:
    return default_registry()


def _parse(text: str, registry: Registry, **kwargs: object) -> StrategyCandidate:
    return parse_strategy(text, registry=registry, max_risk_r=MAX_RISK_R, **kwargs)  # type: ignore[arg-type]


def _swap(original: str, replacement: str) -> str:
    return VALID.replace(original, replacement)


# --------------------------------------------------------------------------------------
# Happy path
# --------------------------------------------------------------------------------------


def test_a_valid_strategy_parses(registry: Registry) -> None:
    strategy = _parse(VALID, registry)
    assert strategy.name == "ma_cross_baseline"
    assert strategy.timeframe is Timeframe.DAILY
    assert strategy.sizing.risk_r == 0.004
    assert len(strategy.exits) == 3


def test_nested_primitives_are_resolved(registry: Registry) -> None:
    """`cross_above(a, b)` takes two *series*, which is what makes the vocabulary compose."""
    strategy = _parse(VALID, registry)
    assert isinstance(strategy.entry, Composite)
    cross = strategy.entry.terms[0]
    assert cross.primitive == "cross_above"  # type: ignore[union-attr]
    assert cross.nested["a"].literals["n"] == 20  # type: ignore[union-attr]
    assert cross.nested["b"].literals["n"] == 50  # type: ignore[union-attr]


def test_every_primitive_used_is_reported(registry: Registry) -> None:
    """The audit log records what a strategy actually used, including nested arguments."""
    assert _parse(VALID, registry).primitives_used() == {
        "cross_above",
        "sma",
        "below",
        "rsi",
        "close",
    }


def test_omitted_parameters_take_their_declared_default(registry: Registry) -> None:
    parsed = _parse(_swap("{rsi: {n: 14}}", "{rsi: {}}"), registry)
    assert isinstance(parsed.entry, Composite)
    assert parsed.entry.terms[1].nested["a"].literals["n"] == 14  # type: ignore[union-attr]


def test_a_zero_parameter_primitive_may_be_named_bare(registry: Registry) -> None:
    parsed = _parse(_swap("b: {close: {}}", "b: close"), registry)
    assert isinstance(parsed.entry, Composite)
    assert parsed.entry.terms[1].nested["b"].primitive == "close"  # type: ignore[union-attr]


# --------------------------------------------------------------------------------------
# Vocabulary refusals
# --------------------------------------------------------------------------------------


def test_an_unknown_primitive_is_rejected(registry: Registry) -> None:
    with pytest.raises(DslError, match="unknown primitive 'moon_phase'"):
        _parse(_swap("{sma: {n: 20}}", "{moon_phase: {n: 20}}"), registry)


def test_an_unknown_parameter_is_rejected(registry: Registry) -> None:
    """A typo'd parameter must not be silently ignored — the strategy would run a different rule."""
    with pytest.raises(DslError, match="unknown parameter"):
        _parse(_swap("{sma: {n: 20}}", "{sma: {n: 20, lenght: 5}}"), registry)


def test_a_missing_required_parameter_is_rejected(registry: Registry) -> None:
    with pytest.raises(DslError, match="missing required parameter 'atr_mult'"):
        _parse(
            _swap("- stop_loss_atr: {atr_mult: 1.5, atr_period: 14}", "- stop_loss_atr: {}"),
            registry,
        )


def test_an_out_of_range_parameter_is_rejected_not_clamped(registry: Registry) -> None:
    """Clamping would run a strategy nobody wrote and report the result under its name."""
    with pytest.raises(DslError, match="rejected, not clamped"):
        _parse(_swap("{sma: {n: 20}}", "{sma: {n: 99999}}"), registry)


def test_a_non_integer_period_is_rejected(registry: Registry) -> None:
    with pytest.raises(DslError, match="must be a whole number"):
        _parse(_swap("{sma: {n: 20}}", "{sma: {n: 20.5}}"), registry)


def test_a_boolean_is_not_accepted_as_a_number(registry: Registry) -> None:
    """Python treats True as 1; a config that says `n: true` is a mistake, not a 1-bar average."""
    with pytest.raises(DslError, match="must be a whole number"):
        _parse(_swap("{sma: {n: 20}}", "{sma: {n: true}}"), registry)


def test_a_series_used_where_a_condition_belongs_is_rejected(registry: Registry) -> None:
    """`rsi` is a number, not a yes/no. Treating a number as truthy is how 0 becomes 'no signal'."""
    with pytest.raises(DslError, match="produces a number rather than a yes/no"):
        _parse(
            _swap(
                "    - below:\n        a: {rsi: {n: 14}}\n        b: {close: {}}",
                "    - rsi: {n: 14}",
            ),
            registry,
        )


def test_an_event_cannot_be_passed_where_a_series_is_required(registry: Registry) -> None:
    with pytest.raises(DslError, match="is a event primitive but"):
        _parse(_swap("a: {sma: {n: 20}}", "a: {squeeze_on: {}}"), registry)


# --------------------------------------------------------------------------------------
# Honesty refusals — the silent failures
# --------------------------------------------------------------------------------------


def test_an_intraday_primitive_refuses_on_daily_bars(registry: Registry) -> None:
    """Approximating a session VWAP with a rolling one reports an edge that was never tested."""
    with pytest.raises(DslError, match="defined only on intraday bars"):
        _parse(_swap("b: {close: {}}", "b: {session_vwap: {}}"), registry)


def test_the_same_primitive_is_accepted_on_intraday_bars(registry: Registry) -> None:
    text = _swap("b: {close: {}}", "b: {session_vwap: {}}").replace(
        "timeframe: 1d", "timeframe: 5m"
    )
    assert _parse(text, registry).timeframe is Timeframe.M5


def test_a_feed_primitive_refuses_when_its_source_is_absent(registry: Registry) -> None:
    """The most dangerous default: a filter that silently passes everything."""
    with pytest.raises(DslError, match="which is not available"):
        _parse(_swap("b: {close: {}}", "b: {delivery_pct: {}}"), registry)


def test_feeds_default_to_absent(registry: Registry) -> None:
    """Fail-closed: a caller must prove a feed exists, not merely fail to deny it."""
    with pytest.raises(DslError, match="which is not available"):
        parse_strategy(
            _swap("b: {close: {}}", "b: {in_fno_ban: {}}"),
            registry=registry,
            max_risk_r=MAX_RISK_R,
        )


def test_a_feed_primitive_is_accepted_once_its_source_is_declared(registry: Registry) -> None:
    text = _swap(
        "    - below:\n        a: {rsi: {n: 14}}\n        b: {close: {}}",
        "    - delivery_pct: {}",
    )
    parsed = _parse(text, registry, available_feeds=frozenset({"nse-delivery"}))
    assert "delivery_pct" in parsed.primitives_used()


# --------------------------------------------------------------------------------------
# Risk and exits
# --------------------------------------------------------------------------------------


def test_risk_r_above_the_goal_yaml_cap_is_rejected_not_clamped(registry: Registry) -> None:
    """Silently shrinking an over-sized request teaches the Inventor that asking is free (#4)."""
    with pytest.raises(DslError, match=r"exceeds the goal\.yaml cap"):
        _parse(_swap("risk_r: 0.004", "risk_r: 0.05"), registry)


def test_risk_r_at_exactly_the_cap_is_allowed(registry: Registry) -> None:
    assert (
        _parse(_swap("risk_r: 0.004", f"risk_r: {MAX_RISK_R}"), registry).sizing.risk_r
        == MAX_RISK_R
    )


def test_a_strategy_with_no_protective_stop_is_rejected(registry: Registry) -> None:
    """Invariant #16 needs a broker-side stop; take-profit and time-stop leave the downside open."""
    text = _swap("  - stop_loss_atr: {atr_mult: 1.5, atr_period: 14}\n", "")
    with pytest.raises(DslError, match="defines no protective stop"):
        _parse(text, registry)


def test_a_trailing_stop_counts_as_protection(registry: Registry) -> None:
    text = _swap(
        "- stop_loss_atr: {atr_mult: 1.5, atr_period: 14}", "- trailing_stop_atr: {atr_mult: 2.0}"
    )
    assert _parse(text, registry).exits[0].rule == "trailing_stop_atr"


def test_an_unknown_exit_rule_is_rejected(registry: Registry) -> None:
    with pytest.raises(DslError, match="unknown exit rule 'exit_when_sad'"):
        _parse(_swap("- time_stop: {bars: 15}", "- exit_when_sad: {}"), registry)


def test_sizing_must_state_what_it_risks(registry: Registry) -> None:
    with pytest.raises(DslError, match=r"sizing\.risk_r is required"):
        _parse(_swap("  risk_r: 0.004", "  {}"), registry)


# --------------------------------------------------------------------------------------
# Document shape
# --------------------------------------------------------------------------------------


def test_an_unknown_top_level_key_is_rejected(registry: Registry) -> None:
    with pytest.raises(DslError, match="unknown top-level keys"):
        _parse(VALID + "\nleverage: 5\n", registry)


def test_a_missing_top_level_key_is_rejected(registry: Registry) -> None:
    with pytest.raises(DslError, match="missing required keys"):
        _parse(_swap("universe: nifty_100\n", ""), registry)


def test_an_unknown_timeframe_is_rejected(registry: Registry) -> None:
    with pytest.raises(DslError, match="unknown timeframe"):
        _parse(_swap("timeframe: 1d", "timeframe: 3d"), registry)


def test_malformed_yaml_is_rejected(registry: Registry) -> None:
    with pytest.raises(DslError, match="not valid YAML"):
        _parse("entry: [unclosed", registry)


def test_an_empty_composite_is_rejected(registry: Registry) -> None:
    """`all: []` is vacuously true — it would enter on every single bar."""
    text = VALID[: VALID.index("entry:")] + "entry:\n  all: []\n" + VALID[VALID.index("exit:") :]
    with pytest.raises(DslError, match="non-empty list"):
        _parse(text, registry)


# --------------------------------------------------------------------------------------
# The registry itself
# --------------------------------------------------------------------------------------


def test_registering_a_duplicate_name_is_rejected() -> None:
    """One word, one meaning — a second registration would silently shadow the first."""
    registry = default_registry()
    existing = next(iter(registry))
    with pytest.raises(DslError, match="already registered"):
        registry.register(existing)


def test_the_registry_is_not_a_global(registry: Registry) -> None:
    """Two calls give independent instances, so a test cannot leak a word into the next one."""
    other = default_registry()
    assert other is not registry
    assert other.names() == registry.names()


def test_the_library_covers_all_five_kinds_it_claims(registry: Registry) -> None:
    kinds = {p.kind for p in registry}
    assert {Kind.SERIES, Kind.LEVEL, Kind.EVENT, Kind.CONTEXT} <= kinds
    # Cross-sectional is 1.4c; asserting its absence keeps this test honest about scope.
    assert Kind.CROSS_SECTIONAL not in kinds
