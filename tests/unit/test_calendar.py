"""Trading-calendar tests (task 0.15): holidays, weekends, sessions, crypto 24/7, unknown year."""

from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from icarus.common.calendar import (
    IST,
    CalendarDataMissing,
    is_market_open,
    is_nse_trading_day,
)
from icarus.common.types import AssetClass


def _ist(y: int, m: int, d: int, hh: int, mm: int) -> datetime:
    return datetime(y, m, d, hh, mm, tzinfo=IST).astimezone(UTC)


def test_weekday_is_trading_day() -> None:
    assert is_nse_trading_day(date(2026, 7, 27))  # Monday, not a holiday


def test_weekend_is_not_trading_day() -> None:
    assert not is_nse_trading_day(date(2026, 7, 25))  # Saturday


def test_holiday_is_not_trading_day() -> None:
    assert not is_nse_trading_day(date(2026, 1, 26))  # Republic Day


def test_unknown_year_raises_not_guesses() -> None:
    with pytest.raises(CalendarDataMissing):
        is_nse_trading_day(date(2099, 1, 4))


def test_equity_open_during_session() -> None:
    assert is_market_open(AssetClass.EQUITY, _ist(2026, 7, 27, 11, 0))  # Mon 11:00 IST


def test_equity_closed_before_open() -> None:
    assert not is_market_open(AssetClass.EQUITY, _ist(2026, 7, 27, 9, 0))  # 09:00 pre-open


def test_equity_closed_after_close() -> None:
    assert not is_market_open(AssetClass.EQUITY, _ist(2026, 7, 27, 16, 0))


def test_equity_closed_on_holiday_intraday() -> None:
    assert not is_market_open(AssetClass.EQUITY, _ist(2026, 1, 26, 11, 0))  # Republic Day 11:00


def test_crypto_always_open() -> None:
    # Even on an NSE holiday at 3am IST.
    assert is_market_open(AssetClass.CRYPTO, _ist(2026, 1, 26, 3, 0))


def test_naive_ts_rejected() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        is_market_open(AssetClass.EQUITY, datetime(2026, 7, 27, 11, 0))
