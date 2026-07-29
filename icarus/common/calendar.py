"""Trading calendar & sessions (task 0.15, PRD §28, §29.5, §33).

Prevents two backtest/live invalidators: fabricated bars on holidays, and orders on a closed
market. Timestamps arrive tz-aware UTC and are converted to IST only here, at the session
boundary (invariant #22, §29.5).

Fail-safe: if the holiday list for a year isn't loaded, :func:`is_nse_trading_day` RAISES
rather than guessing — "I don't know if the market is open" must never silently become "open".

NSE 2026 equity holidays (full-day closures) cross-checked against two sources 2026-07-27:
Zerodha holiday calendar + ClearTax (both agree). ⚠️ VERIFY-BEFORE-LIVE (PRD Appendix B): re-pull
the official NSE circular before Phase 2, as dates can change by circular.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from icarus.common.types import AssetClass

IST = ZoneInfo("Asia/Kolkata")

# NSE equity/capital-market normal session (IST). Pre-open (09:00-09:15) excluded from "open".
EQUITY_SESSION_OPEN = time(9, 15)
EQUITY_SESSION_CLOSE = time(15, 30)

# Source: Zerodha holiday-calendar + ClearTax, both as-of 2026-07-27 (agree). Muhurat special
# session on 2026-11-08 (Sun) is a special session, not a normal trading day — excluded here.
NSE_HOLIDAYS: dict[int, frozenset[date]] = {
    2026: frozenset(
        {
            date(2026, 1, 15),  # Municipal Corporation Elections (Maharashtra)
            date(2026, 1, 26),  # Republic Day
            date(2026, 3, 3),  # Holi
            date(2026, 3, 26),  # Ram Navami
            date(2026, 3, 31),  # Mahavir Jayanti
            date(2026, 4, 3),  # Good Friday
            date(2026, 4, 14),  # Ambedkar Jayanti
            date(2026, 5, 1),  # Maharashtra Day
            date(2026, 5, 28),  # Bakri Eid
            date(2026, 6, 26),  # Muharram
            date(2026, 9, 14),  # Ganesh Chaturthi
            date(2026, 10, 2),  # Gandhi Jayanti
            date(2026, 10, 20),  # Dussehra
            date(2026, 11, 10),  # Diwali Balipratipada
            date(2026, 11, 24),  # Guru Nanak Jayanti
            date(2026, 12, 25),  # Christmas
        }
    ),
}


class CalendarDataMissing(RuntimeError):
    """Raised when the holiday list for a requested year isn't loaded (fail-safe, don't guess)."""


# Sessions derived from the exchange's own archive for years with no verified holiday list
# (task 1.1c; operator decision 2026-07-29). NSE publishes holidays only for the current year, so
# for 2021-2025 a weekday with no bhavcopy in EITHER archive is taken as a closure — the exchange
# not publishing an end-of-day file is its own evidence the market was shut. Populated by
# :mod:`icarus.agents.data.backfill`; empty until a backfill artifact is loaded.
_DERIVED_SESSIONS: dict[int, frozenset[date]] = {}

# NSE runs ~245-250 sessions a year. A complete derived year outside this band means the archive
# had holes, not that the market took a month off — refuse it rather than backtest on a fiction.
MIN_SESSIONS_PER_YEAR = 240
MAX_SESSIONS_PER_YEAR = 255


def register_derived_sessions(year: int, sessions: frozenset[date], *, complete_year: bool) -> None:
    """Record archive-derived trading days for ``year``.

    ``complete_year`` says whether the backfill covered all 12 months; only then is the
    session-count sanity check meaningful. A partial year is accepted as-is — it is still the
    truth about the range that was scanned.
    """
    if complete_year and not MIN_SESSIONS_PER_YEAR <= len(sessions) <= MAX_SESSIONS_PER_YEAR:
        raise CalendarDataMissing(
            f"derived calendar for {year} has {len(sessions)} sessions, outside the plausible "
            f"{MIN_SESSIONS_PER_YEAR}-{MAX_SESSIONS_PER_YEAR}; the archive is incomplete (§29.4)"
        )
    _DERIVED_SESSIONS[year] = sessions


def clear_derived_sessions() -> None:
    """Drop all derived calendars. For tests and for reloading a corrected artifact."""
    _DERIVED_SESSIONS.clear()


def is_nse_trading_day(d: date) -> bool:
    """True if ``d`` is an NSE equity trading day (weekday and not a holiday).

    Prefers the verified holiday list; falls back to archive-derived sessions for years that have
    one. Raises :class:`CalendarDataMissing` when neither exists — "I don't know whether the
    market was open" must never silently become "it was".
    """
    holidays = NSE_HOLIDAYS.get(d.year)
    if holidays is not None:
        return d.weekday() < 5 and d not in holidays
    derived = _DERIVED_SESSIONS.get(d.year)
    if derived is not None:
        return d in derived
    raise CalendarDataMissing(
        f"no NSE holiday list or derived calendar for {d.year}; "
        f"refusing to assume market state (§28)"
    )


def session_open_utc(day: date) -> datetime:
    """The UTC instant the NSE equity session opens on ``day`` (09:15 IST).

    Bars are stamped here so their UTC date equals the IST trading date — the whole session sits
    inside one UTC date — which is what lets bars from different vendors be matched by date.
    Derived from :data:`EQUITY_SESSION_OPEN` rather than restated, so there is one source of truth.
    """
    return datetime.combine(day, EQUITY_SESSION_OPEN, tzinfo=IST).astimezone(UTC)


def session_closed(asset_class: AssetClass, day: date, now_utc: datetime) -> bool:
    """Whether ``day``'s session has ended, so its daily bar is final rather than in-progress.

    A bar for the session still running is a partial: its close is only the last trade so far and
    its high/low can still move. Treating it as complete would hand a strategy a close that has
    not happened yet — the look-ahead that invariants #12/#13 exist to prevent.

    Equity sessions end at 15:30 IST on the bar's own date; a crypto daily bar runs to UTC
    midnight, so it is final only once the date has rolled over.
    """
    if now_utc.tzinfo is None:
        raise ValueError("now_utc must be tz-aware UTC (§29.5)")
    if asset_class is AssetClass.CRYPTO:
        return day < now_utc.astimezone(UTC).date()
    close_utc = datetime.combine(day, EQUITY_SESSION_CLOSE, tzinfo=IST).astimezone(UTC)
    return now_utc >= close_utc


def is_market_open(asset_class: AssetClass, ts_utc: datetime) -> bool:
    """Whether the market for ``asset_class`` is open at ``ts_utc`` (tz-aware UTC).

    Crypto is 24/7. Equity follows NSE trading days + the 09:15-15:30 IST session.
    """
    if ts_utc.tzinfo is None:
        raise ValueError("ts_utc must be tz-aware UTC (§29.5)")
    if asset_class is AssetClass.CRYPTO:
        return True
    ist = ts_utc.astimezone(IST)
    if not is_nse_trading_day(ist.date()):
        return False
    return EQUITY_SESSION_OPEN <= ist.time() <= EQUITY_SESSION_CLOSE
