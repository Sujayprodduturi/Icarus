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


@dataclass(frozen=True, slots=True)
class Panel:
    """Every symbol's bars on one shared date axis, plus who was tradable on each date (1.4c).

    **This exists because a ranking cannot be computed one symbol at a time.** "Is RELIANCE in the
    strongest ten today?" needs every other symbol's bar *for today* before it can be answered for
    RELIANCE — so the evaluator needs a way to see the whole universe at once, which :class:`Bars`
    by construction cannot give it.

    ``tradable`` is the load-bearing field and the reason this class validates rather than being a
    plain dict. It is the **point-in-time** membership: which symbols the universe rules admitted on
    each date, as known on that date. Ranking against a list of symbols chosen today is the classic
    survivorship bug (PRD §29, invariant #14) — the winners look extraordinary because they were
    picked by having survived, and it is invisible in the results. Having bars for a symbol is not
    the same as it having been tradable: a name can trade and still fail the liquidity floor.

    Bars must already be aligned to one date axis — a symbol with no session on a date carries
    ``nan`` there. Alignment is the backtester's job (1.7); this class only refuses to hold a panel
    that is not aligned, because a silently mis-aligned panel would rank Monday's RELIANCE against
    Tuesday's TCS and nothing downstream could tell.
    """

    symbols: tuple[str, ...]
    bars: tuple[Bars, ...]
    tradable: npt.NDArray[np.bool_]
    benchmark: Bars | None = None

    @classmethod
    def build(
        cls,
        bars: Mapping[str, Bars],
        tradable: Mapping[str, npt.NDArray[np.bool_]],
        *,
        benchmark: Bars | None = None,
    ) -> Panel:
        """Validate and assemble. Raises rather than repairing anything it is handed."""
        if not bars:
            raise DslError("a Panel needs at least one symbol")
        symbols = tuple(sorted(bars))
        if set(tradable) != set(symbols):
            # Symmetric on purpose. Missing membership is the survivorship hole; *extra* membership
            # means the caller believes the universe contains a symbol whose bars it did not supply,
            # and silently ranking without that name is the same bias arriving by a different door.
            raise DslError(
                f"membership and bars disagree about the universe: "
                f"{sorted(set(symbols) ^ set(tradable))}. A Panel cannot be built without exact "
                f"point-in-time membership, because ranking against a symbol list chosen today is "
                f"survivorship bias (invariant #14)"
            )
        first = bars[symbols[0]]
        columns = []
        for symbol in symbols:
            series = bars[symbol]
            if len(series) != len(first) or not np.array_equal(series.ts, first.ts):
                raise DslError(
                    f"{symbol!r} is not aligned to the panel's date axis. Align before building; a "
                    f"mis-aligned panel ranks one symbol's Monday against another's Tuesday."
                )
            if tradable[symbol].shape != (len(first),):
                raise DslError(f"{symbol!r} membership has the wrong length for the date axis")
            columns.append(series)
        if benchmark is not None and not np.array_equal(benchmark.ts, first.ts):
            raise DslError("the benchmark is not aligned to the panel's date axis")
        mask = np.vstack([tradable[symbol] for symbol in symbols]).astype(np.bool_)
        return cls(symbols=symbols, bars=tuple(columns), tradable=mask, benchmark=benchmark)

    def __len__(self) -> int:
        """Number of dates. The symbol count is ``len(panel.symbols)`` — deliberately not this."""
        return len(self.bars[0])

    @property
    def ts(self) -> npt.NDArray[np.datetime64]:
        return self.bars[0].ts

    def index_of(self, symbol: str) -> int:
        try:
            return self.symbols.index(symbol)
        except ValueError:
            raise DslError(f"{symbol!r} is not in this panel") from None

    def require_benchmark(self, where: str) -> Bars:
        """The benchmark, or a refusal. Never a silent substitute for it.

        A word that quietly fell back to the universe mean when the index was missing would report
        an alpha that was measured against something else entirely.
        """
        if self.benchmark is None:
            raise DslError(
                f"{where} needs the benchmark series, which this panel does not carry. It refuses "
                f"rather than substituting one — a relative-strength number measured against the "
                f"wrong thing is worse than no number."
            )
        return self.benchmark


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
    requires_scale_free: bool = False
    """Refuse an input whose magnitude tracks the symbol's own price.

    See :attr:`Primitive.scale_free` for what that means and why it is not a naming convention.

    Set only where the value is compared **between symbols**. Within one symbol every unit is fine:
    ``above(close, sma(200))`` compares two rupee quantities on the same instrument and is exactly
    right. It is the cross-section that breaks — which is why this is a property of the parameter
    and not of the word supplying it.
    """

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

    ``intraday_only``, ``requires_feed``, ``intermittent``, ``needs_panel``, ``scale_free``,
    ``opaque_lookback`` and ``unrankable_reason`` are the honesty flags. They are declared here —
    beside the computation — precisely so that adding a primitive cannot forget them. Each one
    exists because a word once claimed something it could not deliver and nothing caught it.

    ``needs_panel`` says the word cannot be computed from one symbol's bars at all: it is handed a
    :class:`Panel` instead of :class:`Bars`, computes the whole universe at once, and returns either
    one row per symbol or a single row when the answer is the same for everyone (market breadth,
    the index's own trend). It is **separate from** ``kind`` on purpose — ``xs_top_n`` needs the
    universe and is still an ``EVENT``, so a strategy can use it as a condition. Collapsing the two
    would have forced every cross-sectional word into a kind that cannot be a condition.

    ``scale_free`` says whether comparing this word's output **between two different symbols** is
    meaningful. A percentage, a ratio, a rank, a bar count and a z-score are all comparable; a rupee
    quantity is not, because its size tracks the share price rather than the behaviour being
    measured. Ranking ``close - close[-20]`` across a universe sorts by *price level* wearing a
    momentum label — the ₹3,000 stock that rose 5% beats the ₹300 one that rose 40% — and the result
    looks exactly like a working ranker, which is why this had to become a declared property rather
    than a naming convention. It is **required** for ``SERIES``, ``CONTEXT`` and ``CROSS_SECTIONAL``
    words and derived for the other two: an ``EVENT`` is a yes/no and always comparable, a ``LEVEL``
    is a price and never is.

    ``intermittent`` says that ``nan`` in this word's output can mean *"no such level exists right
    now"* and not only *"not knowable yet"*. Almost every primitive warms up once and then produces
    a value on every subsequent bar, so a hole in the middle of its output is the fingerprint of a
    filled warm-up (the bug fixed in 1.4a). Zone words break that rule honestly: a fair value gap
    that price has traded through has *stopped existing*, and an order block price closed beyond
    has been invalidated. Rather than let the warm-up test guess which is which, the word declares
    it — so a genuinely broken new primitive cannot hide behind a heuristic exemption.
    """

    name: str
    kind: Kind
    summary: str
    compute: Compute
    params: tuple[ParamSpec, ...] = ()
    intraday_only: bool = False
    requires_feed: str | None = None
    intermittent: bool = False
    needs_panel: bool = False
    requires_lt: tuple[tuple[str, str], ...] = ()
    """Parameter pairs ``(a, b)`` that must satisfy ``a < b``, checked when the strategy is read.

    Some parameter combinations are individually in range and jointly meaningless — ``roc_skip``
    with ``skip >= n`` asks for the return over a window that ends before it starts. The honest
    answer is a refusal, and the range on each parameter alone cannot express it.
    """
    opaque_lookback: bool = False
    """How much history this word needs cannot be read off its parameters (finding F28).

    The backtester simulates a span by reading some sessions of history in front of it, and it
    sizes that lead-in from the largest integer in the strategy. For most words that is a fair
    reading — a 20-session average is written ``sma(20)``. These three defeat it outright, and all
    three are granted a lead-in of **zero**:

    * ``obv`` and ``ad_line`` are running totals from the first bar. There is no finite lead-in
      that reproduces them, at any size.
    * ``psar`` does not converge as history grows — it *oscillates*, matching full history at 300
      sessions of lead-in, missing at 700, matching again at 900, because its acceleration factor
      resets at whichever trend reversal falls first in the slice. And both its parameters are
      decimals, so the largest-integer rule finds no number in it at all.

    Measured rather than assumed; ``test_dsl_lookback.py`` derives both facts and would fail if a
    word were marked here without deserving it. Refused at parse time rather than warned about,
    because the failure is invisible: the word returns a full column of plausible numbers either
    way, and only a side-by-side run against full history shows the difference.

    **This is the extreme end of a wider problem, not the whole of it (finding F29).** About a
    hundred other words also need more history than their own widest parameter — recursive ones
    like ``rsi`` and ``macd`` most of all. They are granted *something*, which is why they are not
    refused here, and the general fix is a separate decision.
    """
    unrankable_reason: str | None = None
    """Why this word may not be used as ``rank_by``, if it may not be. Quoted in the refusal.

    ``rank_by`` means *"a larger value is a better candidate"* — the simulator sorts descending. A
    word whose own definition promises the opposite ordering is not merely a poor choice there, it
    silently fills the book with the losers. Declared here rather than listed in the parser so the
    reason lives beside the computation that causes it.
    """
    scale_free: bool | None = None
    """Never ``None`` after construction — :meth:`__post_init__` resolves or rejects it.

    Typed optional so that "not declared" is representable at the call site and can be *refused*.
    Every reader treats a falsy value as not-comparable, so the one direction this can fail in is
    the safe one.
    """

    def __post_init__(self) -> None:
        object.__setattr__(self, "scale_free", self._resolve_scale_free())
        self._check_requires_lt()

    def _check_requires_lt(self) -> None:
        """Catch a mis-declared pair when the word is built, not when a strategy first uses it.

        Without this, naming a parameter that does not exist (or a nested series, which has no
        scalar to compare) surfaces as a bare ``KeyError`` from inside ``parse_strategy`` — and only
        for a strategy that happens to use this primitive, which could be the first one parsed in
        production. Everything else about a ``Primitive`` is now validated here; this belongs too.
        """
        scalars = {spec.name for spec in self.params if not isinstance(spec, SeriesParam)}
        for pair in self.requires_lt:
            unknown = [name for name in pair if name not in scalars]
            if unknown:
                raise DslError(
                    f"primitive {self.name!r} declares requires_lt={pair} but {unknown} "
                    f"{
                        'is not a scalar parameter'
                        if len(unknown) == 1
                        else 'are not scalar parameters'
                    } of it; it accepts {sorted(scalars)}"
                )

    def _resolve_scale_free(self) -> bool:
        derived = {Kind.EVENT: True, Kind.LEVEL: False}.get(self.kind)
        if derived is None:
            if self.scale_free is None:
                raise DslError(
                    f"primitive {self.name!r} is a {self.kind} word and must declare "
                    f"scale_free=True or scale_free=False. It says whether comparing this number "
                    f"between two symbols is meaningful — a percentage or a ratio yes, a rupee "
                    f"amount no. There is no safe default: guessing True lets a price-denominated "
                    f"quantity be ranked across the universe, which sorts by share price while "
                    f"looking like it sorts by the thing you named."
                )
            return self.scale_free
        if self.scale_free is not None and self.scale_free is not derived:
            raise DslError(
                f"primitive {self.name!r} declares scale_free={self.scale_free} but a "
                f"{self.kind} word is always {derived}: a yes/no compares across symbols, a "
                f"price never does."
            )
        return derived

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


# How a basket is split across its members, once the strategy has chosen the members. Only
# meaningful for a strategy that holds several names at once, which is why the vocabulary arrives
# with the cross-sectional words (1.4c) rather than with the per-symbol ones.
#
# **Every one of these divides `risk_r`; none of them multiplies it.** A basket of ten names at
# `risk_r` each would be ten times the intended exposure. The weights a scheme produces are a
# partition of one unit of risk, and `assert_partitions_risk` below is what any consumer must call
# to prove that before sizing anything (invariant #4 — sizing vocabulary may only reduce).
WEIGHTING_SCHEMES = ("equal_weight", "inverse_vol_weight", "rank_weight")


class Sizing(Node):
    """How much to risk, and how to split it across a basket.

    ``weighting`` and ``vol_target_pct`` are **declarations only** in 1.4c: they parse, validate,
    and are capped here, but nothing consumes them until the backtester builds portfolios (1.7).
    They are declared now so that a strategy file written today still parses then — and so the
    "may only reduce" refusal lives beside ``risk_r``, which is the number it constrains, rather
    than being reinvented in the consumer.

    Both are optional, so a strategy that names only ``risk_r`` is unchanged and no schema version
    moves. A required key here would have broken every strategy file already written.
    """

    risk_r: float
    weighting: str = "equal_weight"
    vol_target_pct: float | None = None


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
    rank_by: Call | None = None
    """Which candidate wins when more fire than there are open slots. Higher is preferred.

    Optional, and the backtester records how often it *would* have been needed: a strategy on a
    hundred-name universe with four slots will regularly have five names fire on one day, and with
    no ranking the choice between them has to come from somewhere. Picking in symbol order is the
    obvious default and is quietly alphabetical — every ADANI* name ahead of every ZEE* one, which
    is the same bias the cross-sectional tie-breaking rule exists to avoid. So the ambiguity is
    counted and surfaced rather than resolved silently, and a strategy that hits it often is one
    whose author needs to say what "best" means.
    """

    def primitives_used(self) -> frozenset[str]:
        """Every primitive name anywhere in the tree — what the audit log records."""
        used = set(_walk_names(self.entry))
        if self.rank_by is not None:
            used |= set(_walk_names(self.rank_by))
        return frozenset(used)


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
_REQUIRED_KEYS = frozenset({"name", "version", "timeframe", "universe", "entry", "exit", "sizing"})
# Optional keys are listed separately so "unknown key" and "missing key" stay two different
# refusals. Folding them into one set would make every optional key silently required.
_OPTIONAL_KEYS = frozenset({"rank_by"})
_TOP_LEVEL_KEYS = _REQUIRED_KEYS | _OPTIONAL_KEYS


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
    missing = _REQUIRED_KEYS - set(raw)
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
        rank_by=_rank_by(raw.get("rank_by"), context),
    )


def _rank_by(node: object, ctx: _Context) -> Call | None:
    """A number per symbol, highest first. Must produce a number — an event cannot rank anything.

    A yes/no here would sort every candidate into two buckets and leave the choice *within* the
    winning bucket exactly as arbitrary as it was without a ranking, while looking like it had been
    resolved.

    ``rank_by`` decides which of the day's candidates get the limited slots, so it is a comparison
    *between symbols* and carries the same scale-free requirement as ``xs_*``. This is the second
    half of finding F1: all three shipped strategies said ``rank_by: momentum``, so even the ones
    that were not cross-sectional at entry were filling the book price-first.
    """
    if node is None:
        return None
    call = _call(node, ctx, where="rank_by")
    if call.kind not in (Kind.SERIES, Kind.LEVEL, Kind.CROSS_SECTIONAL, Kind.CONTEXT):
        raise DslError(
            f"rank_by: {call.primitive!r} is a {call.kind} primitive, which produces a yes/no "
            f"rather than a number. Ranking needs an ordering — a boolean only re-splits the "
            f"candidates into two groups and leaves the choice inside the winning one arbitrary."
        )
    primitive = ctx.registry.get(call.primitive)
    if primitive.unrankable_reason:
        raise DslError(f"rank_by: {call.primitive!r} may not rank — {primitive.unrankable_reason}")
    _assert_scale_free(call, ctx, where="rank_by")
    return call


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
    if primitive.opaque_lookback:
        raise DslError(
            f"{where}: nothing in {primitive.name!r} says how much history it needs, so the "
            f"backtester grants it whatever its widest whole-number parameter says — which for "
            f"this word is not what it needs — and each fold computes a different number from the "
            f"same bars, every one of them plausible. Rewriting it as a change over a fixed "
            f"window would be safe, but the DSL has no series arithmetic yet (finding F22)."
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
            if spec.requires_scale_free:
                _assert_scale_free(child, ctx, where=f"{where}.{spec.name}")
            nested[spec.name] = child
        else:
            literals[spec.name] = spec.validate(value, where=where)  # type: ignore[assignment]

    for lower, upper in primitive.requires_lt:
        if not literals[lower] < literals[upper]:  # type: ignore[operator]
            raise DslError(
                f"{where}: {lower}={literals[lower]} must be less than {upper}={literals[upper]}. "
                f"Both are individually in range but the pair describes nothing computable."
            )
    return literals, nested


def _assert_scale_free(call: Call, ctx: _Context, *, where: str) -> None:
    """Refuse to compare a price-denominated quantity between symbols (finding F1).

    Rejected at parse time rather than warned about at run time because the wrong version computes
    perfectly happily: ``xs_top_n(momentum(20), 10)`` returns ten names every day, all the machinery
    downstream works, and the only symptom is that the ten names are the expensive ones. A backtest
    like that is not a failed strategy, it is a *plausible* one — and it took a full result set and
    an audit to notice. The one place it can be caught for free is when the words are read.
    """
    if ctx.registry.get(call.primitive).scale_free:
        return
    raise DslError(
        f"{where}: {call.primitive!r} is denominated in the symbol's own price (or share count), "
        f"so comparing it between symbols compares price levels, not behaviour — a ₹3,000 stock "
        f"that rose 5% would outrank a ₹300 one that rose 40%. Use the scale-free form: 'roc' or "
        f"'roc_skip' for return, 'natr' for volatility, 'ppo' for MACD, 'relative_volume' for "
        f"volume, or wrap it in 'zscore'/'percentile_rank' to normalise against its own history."
    )


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


_SIZING_KEYS = frozenset({"risk_r", "weighting", "vol_target_pct"})


def _sizing(node: object, *, max_risk_r: float) -> Sizing:
    if not isinstance(node, dict):
        raise DslError(f"sizing must be a mapping, got {node!r}")
    unknown = set(node) - _SIZING_KEYS
    if unknown:
        raise DslError(f"sizing: unknown key(s) {sorted(unknown)}; allowed: {sorted(_SIZING_KEYS)}")
    if "risk_r" not in node:
        raise DslError("sizing.risk_r is required — a strategy must state what it risks")
    risk_r = FloatParam("risk_r", 0.0001, 1.0).validate(node["risk_r"], where="sizing")
    if risk_r > max_risk_r:
        raise DslError(
            f"sizing.risk_r={risk_r} exceeds the goal.yaml cap of {max_risk_r} — rejected, not "
            f"clamped. Silently shrinking an over-sized request teaches the Inventor that asking "
            f"for too much is free (invariant #4)."
        )
    weighting = ChoiceParam("weighting", WEIGHTING_SCHEMES, default="equal_weight").validate(
        node.get("weighting", "equal_weight"), where="sizing"
    )
    target = node.get("vol_target_pct")
    # The upper bound is not cosmetic. Volatility targeting works by scaling exposure up when
    # realised vol is below target, so an unbounded target is a leverage request wearing a
    # different word — and it would arrive at the Risk agent as a *multiplier* on risk_r, which
    # invariant #4 forbids outright.
    vol_target_pct = (
        None
        if target is None
        else FloatParam("vol_target_pct", 0.01, 1.0).validate(target, where="sizing")
    )
    return Sizing(risk_r=risk_r, weighting=weighting, vol_target_pct=vol_target_pct)


def assert_partitions_risk(weights: Sequence[float], sizing: Sizing, *, where: str) -> None:
    """Refuse a weight vector that hands out more risk than the strategy declared.

    The one guard that makes the sizing vocabulary safe to have shipped before its consumer exists.
    Any future portfolio builder must call this before sizing anything: whatever scheme produced
    the weights, they are a partition of **one** unit of ``risk_r`` and must sum to no more than 1.
    A ten-name basket at full ``risk_r`` each is ten times the exposure the strategy asked for, and
    nothing downstream would flag it — the per-trade number would look perfectly compliant.
    """
    total = sum(weights)
    if any(w < 0.0 for w in weights):
        raise DslError(f"{where}: a negative portfolio weight is not a size, it is a direction")
    if total > 1.0 + 1e-9:
        raise DslError(
            f"{where}: weights sum to {total:.6f} under {sizing.weighting!r}, which spends "
            f"{total:.2f}x the declared risk_r={sizing.risk_r}. Sizing vocabulary may only reduce "
            f"(invariant #4) — rejected, not normalised."
        )


# --------------------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------------------


def _combine(terms: Sequence[npt.NDArray[np.float64]], op: str) -> npt.NDArray[np.float64]:
    """``all``/``any`` over already-evaluated terms. Works on columns and on panel matrices alike.

    Any unknown term makes the whole condition unknown, so the value substituted for ``nan`` below
    can never reach the output — it exists only to keep min/max defined on a slice that is entirely
    ``nan``. ``np.nanmin`` would warn on exactly that slice, and a warning printed once per bar of a
    walk-forward sweep is how real errors get lost.
    """
    stacked = np.stack(terms, axis=0)
    unknown = np.isnan(stacked).any(axis=0)
    neutral = 1.0 if op == "all" else 0.0
    filled = np.where(unknown, neutral, stacked)
    combined = filled.min(axis=0) if op == "all" else filled.max(axis=0)
    return np.where(unknown, np.nan, combined)


def evaluate(node: Condition, bars: Bars, registry: Registry) -> npt.NDArray[np.float64]:
    """Compute one node over one symbol's ``bars``.

    Events and composites come back as 0.0/1.0 columns rather than a bool dtype, so every node has
    one uniform return type and ``nan`` (meaning "not computable yet on this bar" — the warm-up
    window of a 50-bar average) survives instead of silently becoming ``False``.

    A cross-sectional word **raises** here rather than degrading to a one-symbol universe. "Rank
    among one stock" would return 1.0 on every bar — a perfectly plausible column that means
    nothing, and a strategy filtering on it would appear to have a working universe filter.
    """
    if isinstance(node, Composite):
        return _combine([evaluate(term, bars, registry) for term in node.terms], node.op)

    primitive = registry.get(node.primitive)
    if primitive.needs_panel:
        raise DslError(
            f"{node.primitive!r} needs the whole universe and was given one symbol. Evaluate it "
            f"with evaluate_universe(); a rank computed against a universe of one is meaningless."
        )
    params: dict[str, object] = dict(node.literals)
    for name, child in node.nested.items():
        params[name] = evaluate(child, bars, registry)
    return primitive.compute(bars, **params)


def evaluate_universe(
    node: Condition, panel: Panel, registry: Registry
) -> dict[str, npt.NDArray[np.float64]]:
    """Compute one node for every symbol in ``panel``, returning a column per symbol.

    The whole tree is evaluated **matrix-wise** — every node produces a ``(symbols x dates)`` array
    in one pass, rather than the tree being walked once per symbol. That is not only faster: a
    cross-sectional node evaluated per-symbol would recompute the entire universe's ranking once for
    every symbol it was asked about, which for a 100-name universe is a hundredfold waste on the
    hottest path in the backtester.
    """
    matrix = _matrix(node, panel, registry)
    return {symbol: matrix[i] for i, symbol in enumerate(panel.symbols)}


def _matrix(node: Condition, panel: Panel, registry: Registry) -> npt.NDArray[np.float64]:
    """One ``(symbols x dates)`` array for ``node``."""
    if isinstance(node, Composite):
        return _combine([_matrix(term, panel, registry) for term in node.terms], node.op)

    primitive = registry.get(node.primitive)
    nested = {name: _matrix(child, panel, registry) for name, child in node.nested.items()}
    if primitive.needs_panel:
        out = primitive.compute(panel, **node.literals, **nested)
        # A word whose answer is the same for everyone (breadth, the index's own trend) returns one
        # row; widening it here means such a word never has to know the universe size. The copy is
        # deliberate: a broadcast view would make every symbol's row the *same* buffer, so a caller
        # that wrote to one symbol's column would silently rewrite all of them — and every other
        # node in this function hands back an independent row.
        if out.ndim == 1:
            return np.repeat(out[np.newaxis, :], len(panel.symbols), axis=0)
        return out

    rows = [
        primitive.compute(
            bars, **node.literals, **{name: values[i] for name, values in nested.items()}
        )
        for i, bars in enumerate(panel.bars)
    ]
    return np.vstack(rows)
