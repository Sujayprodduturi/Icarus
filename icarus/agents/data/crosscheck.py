"""Two-source agreement check for daily bars (task 1.1, PRD §29.4).

Having both Yahoo and the NSE bhavcopy means we can ask a question a single source can never
answer: *is this price actually right?* Two independent vendors agreeing is real evidence; a
disagreement is a data-quality signal that must surface rather than be silently resolved by
picking a favourite.

Deliberate design choices:

* **Prices are compared relatively**, not absolutely — a 1-rupee gap means something very
  different on a ₹20 stock than on a ₹80,000 index.
* **A date present in one source and missing from the other is reported separately** from a value
  mismatch. A missing session is a coverage problem; a differing close is an accuracy problem.
  Collapsing them would hide which one we have.
* **Volume is compared only on request** (``compare_volume``). Vendors differ in what they count
  (settlement types, blocks, adjustments), so a volume gap is weak evidence of a data error while
  a price gap is strong evidence. Defaulting it on would cry wolf.

This module only *reports*. Whether a given disagreement rate halts a feed is the caller's policy
decision, made against ``goal.yaml`` — not something buried in a comparison helper.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from datetime import date

    from icarus.common.types import Candle

# Fields compared by default. Volume is handled separately (see the module docstring).
_PRICE_FIELDS = ("open", "high", "low", "close")

# 0.1%: comfortably wider than vendor rounding, far tighter than a real mis-priced bar.
DEFAULT_TOLERANCE = Decimal("0.001")


@dataclass(frozen=True)
class FieldDisagreement:
    """One field of one session where the two sources differ beyond tolerance."""

    day: date
    field: str
    value_a: Decimal
    value_b: Decimal
    relative_difference: Decimal


@dataclass(frozen=True)
class CrossCheckReport:
    """The outcome of comparing one symbol across two sources."""

    symbol: str
    source_a: str
    source_b: str
    compared_days: int
    only_in_a: tuple[date, ...]
    only_in_b: tuple[date, ...]
    disagreements: tuple[FieldDisagreement, ...]

    @property
    def agreement_rate(self) -> float:
        """Fraction of shared sessions where every compared field agreed. ``1.0`` if none shared."""
        if self.compared_days == 0:
            return 1.0
        bad_days = {d.day for d in self.disagreements}
        return (self.compared_days - len(bad_days)) / self.compared_days

    @property
    def clean(self) -> bool:
        """True when the sources agree on every field of every session they both cover."""
        return not self.disagreements

    @property
    def fully_aligned(self) -> bool:
        """True when they agree *and* cover exactly the same sessions."""
        return self.clean and not self.only_in_a and not self.only_in_b


def _relative_difference(a: Decimal, b: Decimal) -> Decimal:
    """|a-b| / max(|a|,|b|). Zero when both are zero; 1 when exactly one is."""
    scale = max(abs(a), abs(b))
    if scale == 0:
        return Decimal(0)
    return abs(a - b) / scale


def cross_check(
    symbol: str,
    source_a: str,
    bars_a: list[Candle],
    source_b: str,
    bars_b: list[Candle],
    *,
    tolerance: Decimal = DEFAULT_TOLERANCE,
    compare_volume: bool = False,
) -> CrossCheckReport:
    """Compare two sources' bars for the same symbol, matched on session (UTC) date."""
    by_day_a = {c.ts.date(): c for c in bars_a}
    by_day_b = {c.ts.date(): c for c in bars_b}
    shared = sorted(by_day_a.keys() & by_day_b.keys())
    fields = (*_PRICE_FIELDS, "volume") if compare_volume else _PRICE_FIELDS

    disagreements: list[FieldDisagreement] = []
    for day in shared:
        ohlcv_a, ohlcv_b = by_day_a[day].ohlcv, by_day_b[day].ohlcv
        for field in fields:
            value_a: Decimal = getattr(ohlcv_a, field)
            value_b: Decimal = getattr(ohlcv_b, field)
            diff = _relative_difference(value_a, value_b)
            if diff > tolerance:
                disagreements.append(
                    FieldDisagreement(
                        day=day,
                        field=field,
                        value_a=value_a,
                        value_b=value_b,
                        relative_difference=diff,
                    )
                )

    return CrossCheckReport(
        symbol=symbol,
        source_a=source_a,
        source_b=source_b,
        compared_days=len(shared),
        only_in_a=tuple(sorted(by_day_a.keys() - by_day_b.keys())),
        only_in_b=tuple(sorted(by_day_b.keys() - by_day_a.keys())),
        disagreements=tuple(disagreements),
    )
