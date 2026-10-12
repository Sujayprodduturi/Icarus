"""Scalar acquisition accounting shared by daily and timed portfolio paths."""

from dataclasses import fields, replace
from decimal import ROUND_DOWN, Decimal, getcontext, localcontext

from icarus.engine.costmodel import Charges


def whole_shares(budget: Decimal, unit_price: Decimal) -> int:
    return int((budget / unit_price).to_integral_value(rounding=ROUND_DOWN))


def entry_outlay(price: Decimal, quantity: int, charges: Charges) -> Decimal:
    return price * quantity + charges.total


def scaled_charges(charges: Charges, fraction: Decimal) -> Charges:
    return replace(
        charges, **{f.name: getattr(charges, f.name) * fraction for f in fields(charges)}
    )


def charge_difference(first: Charges, second: Charges) -> Charges:
    def exact_difference(left: Decimal, right: Decimal) -> Decimal:
        # Preserve finite allocation digits beyond ambient monetary precision.
        exponent = min(int(left.as_tuple().exponent), int(right.as_tuple().exponent))
        with localcontext() as context:
            context.prec = max(
                getcontext().prec, max(left.adjusted(), right.adjusted()) - exponent + 2
            )
            return left - right

    return replace(
        first,
        **{
            f.name: exact_difference(getattr(first, f.name), getattr(second, f.name))
            for f in fields(first)
        },
    )
