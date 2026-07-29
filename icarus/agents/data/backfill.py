"""Historical archive backfill + derived trading calendar (task 1.1c, PRD §29.1).

Two jobs, done in one pass because they need the same downloads:

1. **Warm the bhavcopy day-cache** for the backtest span, so the universe builder and the
   backtester read from disk instead of the network.
2. **Derive the trading calendar** for years NSE no longer publishes holidays for. NSE's holiday
   API serves only the current year, so 2021-2025 have no authoritative list. A weekday with no
   bhavcopy in *either* archive is recorded as a closure: the exchange declining to publish an
   end-of-day file is its own evidence the market was shut (operator decision, 2026-07-29).

The residual risk is a genuine hole in NSE's archive being misread as a holiday. That is guarded
by a session-count check per complete year — NSE runs ~245-250 sessions, so a year outside
:data:`~icarus.common.calendar.MIN_SESSIONS_PER_YEAR`..``MAX`` means the archive was incomplete
and the artifact is refused rather than silently trusted (§29.4).

This module deliberately does **not** consult the calendar while scanning — it is what produces
the calendar. It walks raw weekdays instead.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, timedelta
from typing import TYPE_CHECKING

from icarus.agents.data.source import SourceUnavailableError
from icarus.common.calendar import register_derived_sessions
from icarus.common.logging import get_logger

if TYPE_CHECKING:
    from pathlib import Path

    from icarus.agents.data.nse import NseBhavcopySource

log = get_logger("data.backfill")

_ARTIFACT_SCHEMA = 1


@dataclass(frozen=True)
class BackfillResult:
    """What a scan found: the sessions that produced a file, and the weekdays that did not."""

    frm: date
    to: date
    sessions: tuple[date, ...]
    closures: tuple[date, ...]

    @property
    def sessions_by_year(self) -> dict[int, frozenset[date]]:
        by_year: dict[int, set[date]] = {}
        for day in self.sessions:
            by_year.setdefault(day.year, set()).add(day)
        return {year: frozenset(days) for year, days in by_year.items()}

    def complete_years(self) -> frozenset[int]:
        """Years fully inside the scanned range — only these can be session-count checked."""
        return frozenset(
            year
            for year in self.sessions_by_year
            if self.frm <= date(year, 1, 1) and date(year, 12, 31) <= self.to
        )


def weekdays_between(frm: date, to: date) -> list[date]:
    """Every Mon-Fri in ``[frm, to]``. The scan's candidate set, before the archive rules."""
    days: list[date] = []
    day = frm
    while day <= to:
        if day.weekday() < 5:
            days.append(day)
        day += timedelta(days=1)
    return days


async def scan(source: NseBhavcopySource, frm: date, to: date) -> BackfillResult:
    """Download every weekday's bhavcopy in range, recording which dates the exchange published.

    Sequential and rate-limited by the source: this hits a free public archive a few hundred to a
    few thousand times, and being blocked would cost far more than the wall-clock saved.
    """
    sessions: list[date] = []
    closures: list[date] = []
    candidates = weekdays_between(frm, to)
    log.info("backfill scan starting", frm=str(frm), to=str(to), weekdays=len(candidates))

    for day in candidates:
        try:
            await source.day_rows(day)
        except SourceUnavailableError:
            closures.append(day)  # no file in either archive -> the market was shut
            continue
        sessions.append(day)

    log.info(
        "backfill scan complete",
        sessions=len(sessions),
        closures=len(closures),
    )
    return BackfillResult(frm=frm, to=to, sessions=tuple(sessions), closures=tuple(closures))


def register(result: BackfillResult) -> None:
    """Load a scan into the calendar, sanity-checking every complete year it covers."""
    complete = result.complete_years()
    for year, days in result.sessions_by_year.items():
        register_derived_sessions(year, days, complete_year=year in complete)
        log.info(
            "derived calendar registered",
            year=year,
            sessions=len(days),
            complete_year=year in complete,
        )


def save(result: BackfillResult, path: Path) -> None:
    """Persist a scan so later runs need neither the network nor a re-scan."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": _ARTIFACT_SCHEMA,
                "source": "nse bhavcopy archive presence (task 1.1c)",
                "frm": result.frm.isoformat(),
                "to": result.to.isoformat(),
                "sessions": [d.isoformat() for d in result.sessions],
                "closures": [d.isoformat() for d in result.closures],
            }
        ),
        encoding="utf-8",
    )


def load(path: Path) -> BackfillResult:
    """Read a persisted scan. A missing or stale artifact raises — never assume a calendar."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SourceUnavailableError(f"unreadable calendar artifact {path}: {exc}") from exc
    if payload.get("schema") != _ARTIFACT_SCHEMA:
        raise SourceUnavailableError(
            f"calendar artifact {path} has schema {payload.get('schema')}, expected "
            f"{_ARTIFACT_SCHEMA}"
        )
    return BackfillResult(
        frm=date.fromisoformat(payload["frm"]),
        to=date.fromisoformat(payload["to"]),
        sessions=tuple(date.fromisoformat(d) for d in payload["sessions"]),
        closures=tuple(date.fromisoformat(d) for d in payload["closures"]),
    )
