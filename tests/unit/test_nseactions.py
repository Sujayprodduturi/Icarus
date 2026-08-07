"""NSE corporate-action parsing (task 1.7c).

Every subject line in this file is a **real string from NSE's archive**, kept verbatim including
its typos. They are here because each one either broke the first version of the parser or is the
reason a rule is shaped the way it is. A regex tuned against invented examples would have passed
its tests and still fabricated an 80% crash in the panel.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from icarus.agents.data.nseactions import parse_ex_date, parse_subject
from icarus.common.schemas import SchemaError

# --------------------------------------------------------------------------------------
# Bonuses
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Bonus 1:1", 2),
        (" Bonus 1:1", 2),  # NSE's own leading space, 2017 RELIANCE
        ("Bonus 1:34", Decimal(35) / 34),
        ("Bonus 4:5", Decimal(9) / 5),
        ("Bonus Shares In The Ratio Of 1:1", 2),
    ],
)
def test_a_bonus_becomes_the_share_multiplier_it_implies(subject: str, expected: object) -> None:
    """`a:b` means a new shares for every b held, so the holder ends with (a+b)/b times as many.

    'Bonus Shares In The Ratio Of 1:1' is the one that matters: the first version required the
    ratio within twenty characters of the word 'bonus' and this sits twenty-four away, so a real
    1:1 bonus was classified as unrecognised and RELIANCE-sized 50% gaps went unadjusted.
    """
    assert parse_subject(subject) == Decimal(str(expected))


# --------------------------------------------------------------------------------------
# Splits
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("subject", "expected"),
    [
        ("Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 5/- Per Share", 2),
        ("Fv Splt Frm Rs 10 To Rs 2", 5),  # abbreviated AND 'Frm', not 'From'
        ("Fv Splt Frm Rs 10 To Re 1", 10),
        ("Face Value Split From Rs.10/- To Re.1/-", 10),
    ],
)
def test_a_split_is_the_ratio_of_the_face_values(subject: str, expected: int) -> None:
    """A sub-division from ₹10 to ₹2 multiplies the share count by five and divides the price by
    five. 'Fv Splt Frm' is real NSE shorthand and matched none of the first version's patterns."""
    assert parse_subject(subject) == Decimal(expected)


def test_a_consolidation_is_the_same_arithmetic_backwards() -> None:
    """Face value going *up* is a reverse split — fewer shares, higher price. No special case."""
    assert parse_subject("Face Value Split From Re 1 To Rs 10") == Decimal(1) / 10


# --------------------------------------------------------------------------------------
# The compound case — the bug the panel's gap audit caught
# --------------------------------------------------------------------------------------


def test_a_bonus_and_a_split_on_one_ex_date_compound() -> None:
    """HINDZINC, 2011-03-07. Both happen the same morning, so the factors multiply.

    Returning the bonus alone gave 2 where the truth was 10, and left a 4.8x discontinuity in
    HINDZINC's series that no test caught — only the panel's residual-gap audit did, and only
    because it ran against real prices. This is the regression test for that.
    """
    subject = "Bonus - 1:1 And Face Value Split From Rs. 10 To Rs. 2"
    assert parse_subject(subject) == Decimal(10)


def test_the_other_compound_case_from_the_same_audit() -> None:
    """DPSCLTD, 2011-12-15: a 22:1 bonus and a 10-to-1 split — 23 x 10 = 230."""
    subject = "Bonus 22:1 And Face Value Split From Rs.10/- To Re.1/-"
    assert parse_subject(subject) == Decimal(230)


# --------------------------------------------------------------------------------------
# Refusals — the whole point is that these do NOT return a plausible number
# --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "subject",
    [
        "Demerger",
        "Scheme Of Arrangement",
        "Composite Scheme Of Arrangement",
        "Scheme Of Amalgamation",
        "Capital Reduction",
        "Rights 2:5 @ Premium Rs.140/- Per Share",
    ],
)
def test_an_event_with_no_stated_ratio_is_refused_not_guessed(subject: str) -> None:
    """These reprice the stock by an amount the subject line does not contain.

    Raising sends them to the quarantine list. Returning ``None`` instead would say "nothing
    happened here", and the panel would trade straight through a real discontinuity.
    """
    with pytest.raises(SchemaError):
        parse_subject(subject)


def test_a_bonus_bundled_into_a_scheme_is_refused_even_though_it_has_a_ratio() -> None:
    """'Bonus 4:5 (Pursuant To Scheme Of Amalgamation)' — the 4:5 is readable and insufficient.

    The amalgamation moves the price too, by an amount not stated. Applying the bonus half alone
    would produce a *worse* series than applying nothing, because it would look adjusted.
    """
    with pytest.raises(SchemaError):
        parse_subject("Bonus 4:5 (Pursuant To Scheme Of Amalgamation)")


@pytest.mark.parametrize(
    "subject",
    [
        "Interim Dividend - Rs 0.75 Per Share",
        "Annual General Meeting",
        "Annual General Meeting/Dividend Rs 19 Per Share",
        "Interim Dividend Rs 7 Per Share (Purpose Revised)",
    ],
)
def test_a_dividend_moves_no_ratio_and_returns_nothing(subject: str) -> None:
    """``dividend_convention: price_return`` — the ex-dividend drop is a real drop the strategy
    actually experiences, so it is neither adjusted nor flagged (§29.3)."""
    assert parse_subject(subject) is None


def test_an_empty_subject_is_not_an_error() -> None:
    assert parse_subject("   ") is None


# --------------------------------------------------------------------------------------
# Dates
# --------------------------------------------------------------------------------------


def test_the_ex_date_is_read_in_nses_own_format() -> None:
    assert parse_ex_date("28-Oct-2024") == date(2024, 10, 28)
    assert parse_ex_date("07-Sep-2017") == date(2017, 9, 7)


@pytest.mark.parametrize("raw", ["-", "", "2024-10-28", "28-Xxx-2024", "garbage"])
def test_an_unreadable_ex_date_is_none_rather_than_a_wrong_date(raw: str) -> None:
    """A row with no usable ex-date is skipped by the caller. Coercing it to *some* date would
    apply a real split on the wrong session, which is worse than not applying it."""
    assert parse_ex_date(raw) is None
