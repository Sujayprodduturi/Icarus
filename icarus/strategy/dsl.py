"""The strategy DSL — vocabulary, grammar and refusals (task 1.4a, PRD §20).

**Why a strategy is not just Python.** If a strategy were arbitrary code, three things we depend on
become impossible: a human could not read it at a glance, the Compliance agent could not verify it
is white-box (PRD §8), and the Strategy-Inventor could later write *anything at all* — including
something that quietly sidesteps a risk limit. So a strategy is written in a **restricted
vocabulary**: a fixed list of allowed words with rules about how they combine. If it is not in the
library, it cannot be said.

**The load-bearing decision (operator, 2026-07-31): name and computation live in one object.**
A :class:`Primitive` declares both which parameters are legal *and* how to compute itself from
bars. The obvious alternative — the DSL validates names, the backtester does the arithmetic — puts
the list of legal words in two places that *will* drift, and the failure is silent: the DSL accepts
``rsi`` while the backtester computes something subtly different, and every number downstream is
wrong with no error anywhere.

**The five kinds of word** (`docs/strategy-research/primitive-catalogue.md` §0.1):

===================  ======================================  ==========================
Kind                 Signature                               Example
===================  ======================================  ==========================
``SERIES``           bars → one number per bar               ``rsi(14)``
``LEVEL``            bars → one *price* per bar              ``donchian_upper(20)``
``EVENT``            bars → true/false per bar               ``cross_above(a, b)``
``CONTEXT``          external feed → one value per bar       ``delivery_pct()``
``CROSS_SECTIONAL``  *universe* of bars → rank per symbol    ``xs_rank(...)`` (1.4c)
===================  ======================================  ==========================

**The refusals are the real work.** A parser that accepts things is easy; what makes this safe is
what it declines to do:

* An unknown word is **rejected**, never ignored.
* A parameter out of range is **rejected**, never clamped to the nearest legal value.
* An **intraday-only** word used on daily bars **raises**. About twenty primitives in the catalogue
  only mean something on sub-daily bars; on daily bars they must refuse, not approximate.
* A word needing a feed we have not built **raises**. This is the most dangerous of the set: a
  ``news_veto`` that quietly returns "no veto" produces a backtest showing an edge that depended on
  a filter *which was not running*, and it looks like a great result.
* ``risk_r`` above the ``goal.yaml`` cap is **rejected, not clamped**. Silently shrinking an
  over-sized request teaches a future Inventor that asking for too much is free (invariant #4).
* An entry with **no protective stop** is rejected. Invariant #16 requires every open position to
  carry one; a strategy that never defines one cannot satisfy that at execution time.

There is no module-level registry: :func:`Registry` instances are built explicitly and passed in.
A global would make "which words exist" depend on import order, and tests that mutate it would leak
into each other.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol

import numpy as np
import yaml
from pydantic import BaseModel, ConfigDict

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator, Mapping, Sequence

    import numpy.typing as npt

    from icarus.common.types import Candle

    # How a primitive turns bars (and already-evaluated nested series) into one column. A plain
    # callable alias rather than a Protocol: every primitive takes its own named parameters, and
    # those names are declared in `Primitive.params` where the parser can actually check them.
    # A Protocol with `**params` would reject every real implementation while proving nothing.
    Compute = Callable[..., npt.NDArray[np.float64]]

# Bumped when the on-disk strategy.yaml shape changes incompatibly.
STRATEGY_SCHEMA_VERSION = 1


class DslError(ValueError):
    """A strategy could not be understood, or asked for something it may not have.

    Deliberately one type for every refusal above. Callers do not get to distinguish "unknown
    primitive" from "parameter out of range" and handle one of them leniently — every case has the
    same correct response, which is to reject the strategy.
    """


class Kind(StrEnum):
    """What a primitive produces. See the table in the module docstring."""

    SERIES = "series"
    LEVEL = "level"
    EVENT = "event"
    CONTEXT = "context"
    CROSS_SECTIONAL = "cross_sectional"


class Timeframe(StrEnum):
    """Bar size a strategy runs on. Phase 1 has daily bars only; the rest are Phase-2 (§41)."""

    DAILY = "1d"
    H1 = "1h"
    M15 = "15m"
    M5 = "5m"
    M1 = "1m"

    @property
    def is_intraday(self) -> bool:
        return self is not Timeframe.DAILY


# --------------------------------------------------------------------------------------
# Bars — the evaluation input
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Bars:
    """Column-oriented OHLCV for one symbol, ascending in time.

    Columns rather than a list of :class:`~icarus.common.types.Candle` objects because every
    primitive here is a whole-series calculation; per-bar object access would dominate the runtime
    of a walk-forward sweep for no benefit.
    """

    ts: npt.NDArray[np.datetime64]
    open: npt.NDArray[np.float64]
    high: npt.NDArray[np.float64]
    low: npt.NDArray[np.float64]
    close: npt.NDArray[np.float64]
    volume: npt.NDArray[np.float64]

    def __len__(self) -> int:
        return int(self.close.size)

    @classmethod
    def from_candles(cls, candles: Sequence[Candle]) -> Bars:
        """Build from the canonical bar type. Raises if the series is not ascending in time.

        Out-of-order bars are the quiet form of look-ahead: a shuffled series still computes a
        moving average, it is just an average of the future (PRD §30.2).
        """
        if not candles:
            raise DslError("cannot build Bars from an empty candle sequence")
        ts = np.array([c.ts for c in candles], dtype="datetime64[ns]")
        if np.any(np.diff(ts) <= np.timedelta64(0, "ns")):
            raise DslError("candles must be strictly ascending in time (PRD §30.2)")
        col = {
            name: np.array([getattr(c.ohlcv, name) for c in candles], dtype=np.float64)
            for name in ("open", "high", "low", "close", "volume")
        }
        return cls(ts=ts, **col)


# --------------------------------------------------------------------------------------
# Parameter specifications
# --------------------------------------------------------------------------------------


class ParamSpec(Protocol):
    """One declared parameter of a primitive."""

    @property
    def name(self) -> str: ...

    @property
    def required(self) -> bool: ...

    def validate(self, value: object, *, where: str) -> object:
        """Return the coerced value, or raise :class:`DslError`. Never silently corrects."""
        ...


@dataclass(frozen=True, slots=True)
class IntParam:
    """A whole number in ``[minimum, maximum]`` — a lookback, a period, a bar count."""

    name: str
    minimum: int
    maximum: int
    default: int | None = None

    @property
    def required(self) -> bool:
        return self.default is None

    def validate(self, value: object, *, where: str) -> int:
        if isinstance(value, bool) or not isinstance(value, int):
            raise DslError(f"{where}.{self.name} must be a whole number, got {value!r}")
        if not self.minimum <= value <= self.maximum:
            raise DslError(
                f"{where}.{self.name}={value} is outside the allowed range "
                f"[{self.minimum}, {self.maximum}] — rejected, not clamped"
            )
        return value


@dataclass(frozen=True, slots=True)
class FloatParam:
    """A real number in ``[minimum, maximum]`` — a multiplier, a threshold, a fraction."""

    name: str
    minimum: float
    maximum: float
    default: float | None = None

    @property
    def required(self) -> bool:
        return self.default is None

    def validate(self, value: object, *, where: str) -> float:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise DslError(f"{where}.{self.name} must be a number, got {value!r}")
        number = float(value)
        if not math.isfinite(number):
            raise DslError(f"{where}.{self.name} must be finite, got {value!r}")
        if not self.minimum <= number <= self.maximum:
            raise DslError(
                f"{where}.{self.name}={number} is outside the allowed range "
                f"[{self.minimum}, {self.maximum}] — rejected, not clamped"
            )
        return number


@dataclass(frozen=True, slots=True)
class ChoiceParam:
    """One of a fixed set of words — e.g. ``direction: up|down``."""

    name: str
    choices: tuple[str, ...]
    default: str | None = None

    @property
    def required(self) -> bool:
        return self.default is None

    def validate(self, value: object, *, where: str) -> str:
        if not isinstance(value, str) or value not in self.choices:
            raise DslError(
                f"{where}.{self.name} must be one of {list(self.choices)}, got {value!r}"
            )
        return value


@dataclass(frozen=True, slots=True)
class SeriesParam:
    """A parameter that is itself a primitive — how ``cross_above(a, b)`` takes two series.

    This is what makes the vocabulary compose rather than requiring a bespoke word for every
    combination (``sma_cross``, ``ema_cross``, ``vwap_cross``...).
    """

    name: str
    accepts: tuple[Kind, ...] = (Kind.SERIES, Kind.LEVEL, Kind.CONTEXT)

    @property
    def required(self) -> bool:
        return True

    def validate(self, value: object, *, where: str) -> object:  # pragma: no cover - see _resolve
        raise DslError(f"{where}.{self.name} must be a primitive, not a literal ({value!r})")


# --------------------------------------------------------------------------------------
# Primitives and the registry
# --------------------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Primitive:
    """One word in the vocabulary: its name, its parameter rules, and how it computes itself.

    ``intraday_only`` and ``requires_feed`` are the honesty flags. They are declared here — beside
    the computation — precisely so that adding a primitive cannot forget them.
    """

    name: str
    kind: Kind
    summary: str
    compute: Compute
    params: tuple[ParamSpec, ...] = ()
    intraday_only: bool = False
    requires_feed: str | None = None

    def spec(self, name: str) -> ParamSpec | None:
        return next((p for p in self.params if p.name == name), None)


class Registry:
    """The one authoritative list of legal words.

    Explicitly constructed and passed around rather than being a module-level global: a global
    would make the vocabulary depend on which modules happened to be imported, and a test that
    registered an extra word would silently change every later test in the session.
    """

    def __init__(self, primitives: Sequence[Primitive] = ()) -> None:
        self._by_name: dict[str, Primitive] = {}
        for primitive in primitives:
            self.register(primitive)

    def register(self, primitive: Primitive) -> None:
        if primitive.name in self._by_name:
            raise DslError(f"primitive {primitive.name!r} is already registered")
        self._by_name[primitive.name] = primitive

    def get(self, name: str) -> Primitive:
        try:
            return self._by_name[name]
        except KeyError:
            raise DslError(
                f"unknown primitive {name!r} — not in the strategy vocabulary. "
                f"Strategies may only use registered words."
            ) from None

    def __contains__(self, name: object) -> bool:
        return name in self._by_name

    def __len__(self) -> int:
        return len(self._by_name)

    def __iter__(self) -> Iterator[Primitive]:
        return iter(self._by_name.values())

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._by_name))


# --------------------------------------------------------------------------------------
# The parsed strategy tree
# --------------------------------------------------------------------------------------


class Node(BaseModel):
    """Base for a validated expression node."""

    model_config = ConfigDict(frozen=True)


class Call(Node):
    """A validated primitive invocation: every parameter present, in range and of the right kind."""

    primitive: str
    kind: Kind
    literals: dict[str, int | float | str] = {}
    nested: dict[str, Call] = {}


class Composite(Node):
    """``all`` (every term must hold) or ``any`` (whichever holds)."""

    op: str
    terms: tuple[Call | Composite, ...]


Condition = Call | Composite
Composite.model_rebuild()


class ExitRule(Node):
    """One way a position ends. A strategy needs at least one *protective* rule (invariant #16)."""

    rule: str
    literals: dict[str, int | float | str] = {}


class Sizing(Node):
    """How much to risk. Always subordinate to the Risk agent's caps — it may only reduce."""

    risk_r: float


class StrategyCandidate(Node):
    """A parsed, validated strategy. The unit the Validation gate and Strategy Registry handle."""

    schema_version: int = STRATEGY_SCHEMA_VERSION
    name: str
    version: int
    timeframe: Timeframe
    universe: str
    entry: Condition
    exits: tuple[ExitRule, ...]
    sizing: Sizing

    def primitives_used(self) -> frozenset[str]:
        """Every primitive name anywhere in the tree — what the audit log records."""
        return frozenset(_walk_names(self.entry))


def _walk_names(node: Condition) -> Iterator[str]:
    if isinstance(node, Composite):
        for term in node.terms:
            yield from _walk_names(term)
        return
    yield node.primitive
    for child in node.nested.values():
        yield from _walk_names(child)


# --------------------------------------------------------------------------------------
# Exit rules — a small fixed vocabulary of their own
# --------------------------------------------------------------------------------------

# Exits are not Events on bars: they are position-relative and only mean anything once something
# is open. Keeping them in their own tiny vocabulary means an exit cannot be used as an entry
# filter (or vice versa) by accident.
EXIT_RULES: dict[str, tuple[ParamSpec, ...]] = {
    "stop_loss_atr": (
        FloatParam("atr_mult", 0.1, 10.0),
        IntParam("atr_period", 2, 200, default=14),
    ),
    "stop_loss_pct": (FloatParam("pct", 0.001, 0.5),),
    "trailing_stop_atr": (
        FloatParam("atr_mult", 0.1, 10.0),
        IntParam("atr_period", 2, 200, default=14),
    ),
    "take_profit_r": (FloatParam("r_multiple", 0.1, 20.0),),
    "take_profit_pct": (FloatParam("pct", 0.001, 5.0),),
    "time_stop": (IntParam("bars", 1, 500),),
}

# Rules that actually bound the loss. Invariant #16 requires every open position to carry a
# broker-side protective stop, so a strategy that never defines one cannot be run honestly —
# a take-profit and a time-stop leave the downside open.
PROTECTIVE_EXITS = frozenset({"stop_loss_atr", "stop_loss_pct", "trailing_stop_atr"})


# --------------------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------------------

_COMPOSITE_OPS = ("all", "any")
_TOP_LEVEL_KEYS = frozenset({"name", "version", "timeframe", "universe", "entry", "exit", "sizing"})


def parse_strategy(
    text: str,
    *,
    registry: Registry,
    max_risk_r: float,
    available_feeds: frozenset[str] = frozenset(),
) -> StrategyCandidate:
    """Parse and fully validate a ``strategy.yaml``.

    ``max_risk_r`` comes from ``goal.yaml`` (``risk.per_trade_risk_r``) — the DSL never carries its
    own copy of a risk number. ``available_feeds`` defaults to *empty*, so a strategy using a feed
    primitive fails closed unless the caller can prove the feed exists.
    """
    try:
        raw = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise DslError(f"strategy is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise DslError(f"strategy must be a mapping, got {type(raw).__name__}")

    unknown = set(raw) - _TOP_LEVEL_KEYS
    if unknown:
        raise DslError(
            f"unknown top-level keys {sorted(unknown)}; allowed: {sorted(_TOP_LEVEL_KEYS)}"
        )
    missing = _TOP_LEVEL_KEYS - set(raw)
    if missing:
        raise DslError(f"strategy is missing required keys {sorted(missing)}")

    timeframe = _timeframe(raw["timeframe"])
    context = _Context(registry=registry, timeframe=timeframe, available_feeds=available_feeds)
    return StrategyCandidate(
        name=_text(raw["name"], "name"),
        version=_version(raw["version"]),
        timeframe=timeframe,
        universe=_text(raw["universe"], "universe"),
        entry=_condition(raw["entry"], context, where="entry"),
        exits=_exits(raw["exit"]),
        sizing=_sizing(raw["sizing"], max_risk_r=max_risk_r),
    )


@dataclass(frozen=True, slots=True)
class _Context:
    """What validation needs to know beyond the node itself."""

    registry: Registry
    timeframe: Timeframe
    available_feeds: frozenset[str]


def _text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise DslError(f"{field} must be a non-empty string, got {value!r}")
    return value.strip()


def _version(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise DslError(f"version must be a positive whole number, got {value!r}")
    return value


def _timeframe(value: object) -> Timeframe:
    if not isinstance(value, str):
        raise DslError(f"timeframe must be a string, got {value!r}")
    try:
        return Timeframe(value)
    except ValueError:
        raise DslError(
            f"unknown timeframe {value!r}; allowed: {[t.value for t in Timeframe]}"
        ) from None


def _condition(node: object, ctx: _Context, *, where: str) -> Condition:
    """A condition is either a composite (``all``/``any``) or a single primitive call."""
    if isinstance(node, dict) and len(node) == 1:
        ((key, value),) = node.items()
        if key in _COMPOSITE_OPS:
            return _composite(key, value, ctx, where=where)
    call = _call(node, ctx, where=where)
    if call.kind not in (Kind.EVENT, Kind.CONTEXT):
        raise DslError(
            f"{where}: {call.primitive!r} is a {call.kind} primitive, which produces a number "
            f"rather than a yes/no. A condition needs an event — wrap it (e.g. cross_above, "
            f"above, below)."
        )
    return call


def _composite(op: str, terms: object, ctx: _Context, *, where: str) -> Composite:
    if not isinstance(terms, list) or not terms:
        raise DslError(f"{where}.{op} must be a non-empty list of conditions, got {terms!r}")
    return Composite(
        op=op,
        terms=tuple(
            _condition(term, ctx, where=f"{where}.{op}[{i}]") for i, term in enumerate(terms)
        ),
    )


def _call(node: object, ctx: _Context, *, where: str) -> Call:
    """One primitive invocation. Accepts ``name`` alone or ``{name: {params}}``."""
    if isinstance(node, str):
        name, params = node, {}
    elif isinstance(node, dict) and len(node) == 1:
        ((name, raw_params),) = node.items()
        if raw_params is None:
            raw_params = {}
        if not isinstance(name, str):
            raise DslError(f"{where}: primitive name must be a string, got {name!r}")
        if not isinstance(raw_params, dict):
            raise DslError(
                f"{where}.{name}: parameters must be a mapping, got {type(raw_params).__name__}"
            )
        params = raw_params
    else:
        raise DslError(
            f"{where}: expected a primitive name or a single-key mapping "
            f"{{name: {{params}}}}, got {node!r}"
        )

    primitive = ctx.registry.get(name)
    _assert_available(primitive, ctx, where=where)
    literals, nested = _resolve_params(primitive, params, ctx, where=f"{where}.{name}")
    return Call(primitive=name, kind=primitive.kind, literals=literals, nested=nested)


def _assert_available(primitive: Primitive, ctx: _Context, *, where: str) -> None:
    """Refuse a primitive that cannot be computed honestly here — never approximate it."""
    if primitive.intraday_only and not ctx.timeframe.is_intraday:
        raise DslError(
            f"{where}: {primitive.name!r} is defined only on intraday bars and this strategy runs "
            f"on {ctx.timeframe.value}. It refuses rather than approximating — an approximated "
            f"filter reports an edge that was never really filtered."
        )
    if primitive.requires_feed and primitive.requires_feed not in ctx.available_feeds:
        raise DslError(
            f"{where}: {primitive.name!r} needs the {primitive.requires_feed!r} feed, which is not "
            f"available. It refuses rather than defaulting — a filter that silently passes "
            f"everything reports an edge that depended on a filter which was not running."
        )


def _resolve_params(
    primitive: Primitive, given: Mapping[str, object], ctx: _Context, *, where: str
) -> tuple[dict[str, int | float | str], dict[str, Call]]:
    declared = {spec.name for spec in primitive.params}
    unknown = set(given) - declared
    if unknown:
        raise DslError(
            f"{where}: unknown parameter(s) {sorted(unknown)}; "
            f"{primitive.name} accepts {sorted(declared)}"
        )

    literals: dict[str, int | float | str] = {}
    nested: dict[str, Call] = {}
    for spec in primitive.params:
        if spec.name not in given:
            if spec.required:
                raise DslError(f"{where}: missing required parameter {spec.name!r}")
            literals[spec.name] = _default_of(spec)
            continue
        value = given[spec.name]
        if isinstance(spec, SeriesParam):
            child = _call(value, ctx, where=f"{where}.{spec.name}")
            if child.kind not in spec.accepts:
                raise DslError(
                    f"{where}.{spec.name}: {child.primitive!r} is a {child.kind} primitive but "
                    f"a {' or '.join(spec.accepts)} is required here"
                )
            nested[spec.name] = child
        else:
            literals[spec.name] = spec.validate(value, where=where)  # type: ignore[assignment]
    return literals, nested


def _default_of(spec: ParamSpec) -> int | float | str:
    default = getattr(spec, "default", None)
    if default is None:  # pragma: no cover - required specs are handled by the caller
        raise DslError(f"parameter {spec.name!r} has no default")
    return default  # type: ignore[no-any-return]


def _exits(node: object) -> tuple[ExitRule, ...]:
    if not isinstance(node, list) or not node:
        raise DslError(f"exit must be a non-empty list of exit rules, got {node!r}")
    rules = tuple(_exit_rule(item, where=f"exit[{i}]") for i, item in enumerate(node))
    names = {rule.rule for rule in rules}
    if not names & PROTECTIVE_EXITS:
        raise DslError(
            f"exit defines no protective stop (one of {sorted(PROTECTIVE_EXITS)}). Invariant #16 "
            f"requires every open position to carry one; take-profit and time-stop leave the "
            f"downside unbounded."
        )
    return rules


def _exit_rule(node: object, *, where: str) -> ExitRule:
    if isinstance(node, str):
        name, params = node, {}
    elif isinstance(node, dict) and len(node) == 1:
        ((name, raw),) = node.items()
        params = {} if raw is None else raw
        if not isinstance(params, dict):
            raise DslError(f"{where}.{name}: parameters must be a mapping, got {raw!r}")
    else:
        raise DslError(f"{where}: expected a single-key mapping {{rule: {{params}}}}, got {node!r}")

    specs = EXIT_RULES.get(name)
    if specs is None:
        raise DslError(f"{where}: unknown exit rule {name!r}; allowed: {sorted(EXIT_RULES)}")
    unknown = set(params) - {spec.name for spec in specs}
    if unknown:
        raise DslError(f"{where}.{name}: unknown parameter(s) {sorted(unknown)}")

    literals: dict[str, int | float | str] = {}
    for spec in specs:
        if spec.name in params:
            literals[spec.name] = spec.validate(params[spec.name], where=f"{where}.{name}")  # type: ignore[assignment]
        elif spec.required:
            raise DslError(f"{where}.{name}: missing required parameter {spec.name!r}")
        else:
            literals[spec.name] = _default_of(spec)
    return ExitRule(rule=name, literals=literals)


def _sizing(node: object, *, max_risk_r: float) -> Sizing:
    if not isinstance(node, dict):
        raise DslError(f"sizing must be a mapping, got {node!r}")
    unknown = set(node) - {"risk_r"}
    if unknown:
        raise DslError(f"sizing: unknown key(s) {sorted(unknown)}")
    if "risk_r" not in node:
        raise DslError("sizing.risk_r is required — a strategy must state what it risks")
    risk_r = FloatParam("risk_r", 0.0001, 1.0).validate(node["risk_r"], where="sizing")
    if risk_r > max_risk_r:
        raise DslError(
            f"sizing.risk_r={risk_r} exceeds the goal.yaml cap of {max_risk_r} — rejected, not "
            f"clamped. Silently shrinking an over-sized request teaches the Inventor that asking "
            f"for too much is free (invariant #4)."
        )
    return Sizing(risk_r=risk_r)


# --------------------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------------------


def evaluate(node: Condition, bars: Bars, registry: Registry) -> npt.NDArray[np.float64]:
    """Compute one node over ``bars``.

    Events and composites come back as 0.0/1.0 columns rather than a bool dtype, so every node has
    one uniform return type and ``nan`` (meaning "not computable yet on this bar" — the warm-up
    window of a 50-bar average) survives instead of silently becoming ``False``.
    """
    if isinstance(node, Composite):
        terms = [evaluate(term, bars, registry) for term in node.terms]
        stacked = np.vstack(terms)
        unknown = np.isnan(stacked).any(axis=0)
        combined = np.nanmin(stacked, axis=0) if node.op == "all" else np.nanmax(stacked, axis=0)
        return np.where(unknown, np.nan, combined)

    primitive = registry.get(node.primitive)
    params: dict[str, object] = dict(node.literals)
    for name, child in node.nested.items():
        params[name] = evaluate(child, bars, registry)
    return primitive.compute(bars, **params)
