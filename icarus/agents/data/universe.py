"""Point-in-time tradable universe (task 1.1c, PRD §29.1-29.2, invariant #14).

The backtester must select the universe **as it existed on the simulated date** — never today's
list. Using today's list is how a backtest quietly becomes fiction: every name in it survived to
the present, so the sample is missing exactly the companies that failed, and the "edge" is partly
just survival.

**Built from the archived bhavcopies, and nothing else.** Each day's file lists what actually
traded that session, with its turnover and series. That makes it point-in-time by construction:

* A name that had not listed yet simply is not in the file.
* A name that was delisted or suspended stops appearing — the delisting *is* the absence, so no
  separate delisting feed is needed to avoid survivorship bias.
* Series ``EQ`` excludes ``BE``/``BZ``, which is how NSE marks trade-to-trade and surveillance
  names, satisfying §29.2's non-surveillance requirement without a second source.

**What we deliberately do not use:** NSE's F&O list and equity master list. §29.2 says the
universe should ideally be F&O-eligible, but those files are *today's* snapshots — applying them
to a 2022 date would mark stocks eligible before they were, which is precisely the look-ahead
§29.1 forbids. Point-in-time turnover from the bhavcopy is the honest substitute.

**The two filters** come from ``goal.yaml``:

* *Liquidity* — average turnover over the trailing window must clear the floor. This is what makes
  modelled fills defensible; it is the real content of the penny/illiquid ban.
* *Price* — a close-price floor. Note that share price does **not** affect returns (profit is
  capital x percent move, and a share price is an arbitrary function of how many shares a company
  issued). The floor exists for two other reasons: the very cheapest names are where survivorship
  and fill fantasy do the most damage, and a price floor set too high makes position sizing
  impossible at seed capital, where one indivisible share can exceed the per-trade risk budget.

**Full-window requirement.** A name must be present in every session of the trailing window. For a
name clearing a ₹50cr turnover floor that is effectively automatic, and it cleanly excludes
freshly-listed names whose liquidity we cannot yet measure — an IPO has no trailing record, and
guessing one would be inventing history.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal, InvalidOperation
from typing import TYPE_CHECKING

from icarus.agents.data.nse import CLOSE_INDEX, TURNOVER_INDEX
from icarus.common.calendar import is_nse_trading_day
from icarus.common.logging import get_logger

if TYPE_CHECKING:
    from icarus.agents.data.nse import NseBhavcopySource
    from icarus.common.config import Universe as UniverseConfig

log = get_logger("data.universe")


@dataclass(frozen=True)
class UniverseMember:
    """One qualifying name, with the numbers it qualified on — auditable, not a bare symbol."""

    symbol: str
    close: Decimal
    avg_turnover: Decimal


@dataclass(frozen=True)
class UniverseSnapshot:
    """The tradable set on one date, as it would have been known on that date."""

    as_of: date
    members: tuple[UniverseMember, ...]
    considered: int

    @property
    def symbols(self) -> frozenset[str]:
        return frozenset(m.symbol for m in self.members)

    def __contains__(self, symbol: str) -> bool:
        return symbol.removesuffix(".NS").upper() in self.symbols


class PointInTimeUniverse:
    """Builds the tradable set for a date from bhavcopies at or before that date."""

    def __init__(self, source: NseBhavcopySource, config: UniverseConfig) -> None:
        self._source = source
        self._cfg = config

    async def as_of(self, day: date) -> UniverseSnapshot:
        """The universe on ``day``. Reads no session after ``day`` — that is the whole point."""
        window = trailing_sessions(day, self._cfg.turnover_window_sessions)
        rows_by_day = {session: await self._source.day_rows(session) for session in window}
        today_rows = rows_by_day[day]

        members: list[UniverseMember] = []
        for symbol, row in today_rows.items():
            close = _decimal(row[CLOSE_INDEX])
            if close is None or close < Decimal(str(self._cfg.min_close_inr)):
                continue
            turnovers = _window_turnovers(symbol, window, rows_by_day)
            if turnovers is None:  # absent from some session -> no measurable trailing liquidity
                continue
            average = sum(turnovers, Decimal(0)) / Decimal(len(turnovers))
            if average < Decimal(str(self._cfg.min_avg_turnover_inr)):
                continue
            members.append(UniverseMember(symbol=symbol, close=close, avg_turnover=average))

        members.sort(key=lambda m: m.avg_turnover, reverse=True)
        log.info(
            "universe built",
            as_of=str(day),
            considered=len(today_rows),
            qualified=len(members),
        )
        return UniverseSnapshot(as_of=day, members=tuple(members), considered=len(today_rows))


def trailing_sessions(day: date, count: int) -> list[date]:
    """The ``count`` NSE trading days ending at ``day`` inclusive, ascending.

    Walks strictly backwards, so no date after ``day`` is ever produced — the mechanical guarantee
    behind "point-in-time". Raises ``CalendarDataMissing`` if the calendar for a year in the walk
    is unknown, rather than guessing which days traded.
    """
    if count < 1:
        raise ValueError(f"count must be >= 1, got {count}")
    if not is_nse_trading_day(day):
        raise ValueError(f"{day} is not an NSE trading day; a universe has no meaning on it")
    sessions: list[date] = []
    cursor = day
    while len(sessions) < count:
        if is_nse_trading_day(cursor):
            sessions.append(cursor)
        cursor -= timedelta(days=1)
    return sorted(sessions)


def _window_turnovers(
    symbol: str, window: list[date], rows_by_day: dict[date, dict[str, list[str]]]
) -> list[Decimal] | None:
    """Turnover for ``symbol`` across every session, or ``None`` if it is missing from any."""
    turnovers: list[Decimal] = []
    for session in window:
        row = rows_by_day[session].get(symbol)
        if row is None:
            return None
        value = _decimal(row[TURNOVER_INDEX])
        if value is None:
            return None
        turnovers.append(value)
    return turnovers


def _decimal(raw: str) -> Decimal | None:
    """Parse a bhavcopy numeric field, or ``None`` when it is blank/malformed.

    A single unparseable field disqualifies the name for that date rather than raising: unlike a
    schema change, one odd cell is a data defect, and the honest response is to leave the name out
    of the universe rather than halt every backtest.
    """
    try:
        return Decimal(raw)
    except (InvalidOperation, ValueError):
        return None
