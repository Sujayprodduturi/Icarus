"""Pure counters and exact threshold-valued simultaneous research bounds.

These deliberately coarse conservative bounds are not numerical CP endpoints.
Tail inversion follows NIST's exact-binomial section, checked 2026-10-01 in the
calendar research protocol. Thresholds/family allocation are project-owned.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from fractions import Fraction
from functools import lru_cache


def cutoff(n: int, p: Fraction, *, lower: bool) -> int:
    """Exact CP-threshold acceptance boundary; preserve impossible cutoffs."""
    if type(n) is not int or not 0 < n <= 32768 or type(p) is not Fraction:
        raise ValueError("invalid binomial denominator/threshold")
    if not 0 < p < 1 or p.denominator > 200 or type(lower) is not bool:
        raise ValueError("invalid binomial threshold/direction")
    return _cutoff(n, p, lower=lower)


@lru_cache(maxsize=512)
def _cutoff(n: int, p: Fraction, *, lower: bool) -> int:
    a, d = p.numerator, p.denominator
    c = d - a
    denominator = d**n
    total = 0
    if lower:
        term = a**n
        for k in range(n, -1, -1):
            total += term
            if total * 5600 > denominator:
                return k + 1
            if k:
                term, remainder = divmod(term * k * c, (n - k + 1) * a)
                if remainder:
                    raise ArithmeticError("nonintegral binomial recurrence")
        raise ArithmeticError("binomial tail did not cross")
    term = c**n
    for k in range(n + 1):
        total += term
        if total * 5600 > denominator:
            return k - 1
        if k < n:
            term, remainder = divmod(term * (n - k) * a, (k + 1) * c)
            if remainder:
                raise ArithmeticError("nonintegral binomial recurrence")
    raise ArithmeticError("binomial tail did not cross")


@dataclass
class Counts:
    replicates: int = 0
    arithmetic: int = 0
    covered: int = 0
    lower_tail: int = 0
    upper_tail: int = 0
    precision: int = 0
    detected: int = 0
    reasons: dict[str, int] = field(default_factory=dict)

    def validate(self) -> None:
        values = (
            self.replicates,
            self.arithmetic,
            self.covered,
            self.lower_tail,
            self.upper_tail,
            self.precision,
            self.detected,
        )
        if any(type(v) is not int or not 0 <= v <= 32768 for v in values):
            raise ValueError("invalid research counters")
        if (
            self.covered + self.lower_tail + self.upper_tail != self.arithmetic
            or not self.detected <= self.precision <= self.arithmetic <= self.replicates
            or any(
                type(k) is not str or not k or type(v) is not int or v < 0
                for k, v in self.reasons.items()
            )
        ):
            raise ValueError("inconsistent research counters")

    def add(
        self,
        lower: Decimal | None,
        upper: Decimal | None,
        truth: Fraction,
        *,
        precision: bool,
        reason: str,
        effect: int = 0,
    ) -> None:
        self.validate()
        if (
            type(truth) is not Fraction
            or type(precision) is not bool
            or type(reason) is not str
            or type(effect) is not int
            or effect not in (-1, 0, 1)
            or self.replicates >= 32768
        ):
            raise ValueError("invalid observation")
        if lower is None or upper is None:
            if lower is not None or upper is not None or precision or not reason:
                raise ValueError("incomplete endpoints/refusal")
            arithmetic = False
        else:
            if (
                type(lower) is not Decimal
                or type(upper) is not Decimal
                or not lower.is_finite()
                or not upper.is_finite()
                or lower > upper
            ):
                raise ValueError("invalid endpoints")
            arithmetic = True
        self.replicates += 1
        if reason:
            self.reasons[reason] = self.reasons.get(reason, 0) + 1
        if arithmetic:
            assert lower is not None and upper is not None
            lo, hi = Fraction(lower), Fraction(upper)
            self.arithmetic += 1
            self.covered += int(lo <= truth <= hi)
            self.lower_tail += int(truth < lo)
            self.upper_tail += int(truth > hi)
            self.precision += int(precision)
            self.detected += int(
                precision and ((effect == 1 and lo > 0) or (effect == -1 and hi < 0))
            )
        self.validate()


@dataclass(frozen=True)
class Criterion:
    name: str
    successes: int
    denominator: int
    threshold: Fraction
    lower: bool
    cutoff: int | None
    passed: bool
    certified_bound: Fraction | None
    bound_kind: str
    bound_passed: bool


def judge(counts: Counts, *, confirmation: bool, effect: bool) -> tuple[Criterion, ...]:
    """Development point criteria or exact confirmation threshold inversion."""
    counts.validate()
    if type(confirmation) is not bool or type(effect) is not bool:
        raise ValueError("invalid phase/effect declaration")
    r = counts.replicates
    definitions = [
        ("arithmetic_emission", counts.arithmetic, r, Fraction(99, 100), True),
        ("joint_coverage", counts.covered, r, Fraction(93, 100), True),
        ("lower_tail", counts.lower_tail, r, Fraction(7, 200), False),
        ("upper_tail", counts.upper_tail, r, Fraction(7, 200), False),
        ("precision", counts.precision, r, Fraction(9, 10), True),
        ("conditional_coverage", counts.covered, counts.arithmetic, Fraction(47, 50), True),
    ]
    if effect:
        definitions.append(("detection", counts.detected, r, Fraction(4, 5), True))
    out = []
    for name, k, n, p, lower in definitions:
        cut = cutoff(n, p, lower=lower) if n else None
        bound_passed = cut is not None and (k >= cut if lower else k <= cut)
        passed = (
            bound_passed
            if confirmation
            else bool(n) and (Fraction(k, n) >= p if lower else Fraction(k, n) <= p)
        )
        bound = (p if bound_passed else Fraction(0 if lower else 1)) if n else None
        out.append(
            Criterion(
                name,
                k,
                n,
                p,
                lower,
                cut,
                passed,
                bound,
                "CONSERVATIVE_THRESHOLD_BOUND",
                bound_passed,
            )
        )
    return tuple(out)
