"""Assemble the backtest panel from the bhavcopy day-cache and NSE's corporate actions (1.7c).

Run once after ``backfill_bhavcopy.py``; every backtest afterwards loads the ``.npz`` it writes
and touches neither the network nor the 2,950 JSON day files again.

    uv run python scripts/build_panel.py [--from YYYY-MM-DD] [--to YYYY-MM-DD]

**The default range stops at the lockbox and it is meant to.** ``--to`` defaults to the day before
``data_split.lockbox_start``, so an ordinary run cannot reach into the held-out slice by accident.
Building across it is refused outright: the lockbox is consumed exactly once, deliberately, by the
final go/no-go — and a panel quietly containing it would let every later run read it for free
(invariant #26). ``--lockbox`` is the only way in, and it says so in the log.

The benchmark (Nifty 50, ``^NSEI``) comes from Yahoo because bhavcopy carries no index rows. It is
optional here: without it the panel still builds and the index-relative words simply refuse to
evaluate, which is the correct failure — a benchmark quietly replaced by a universe average would
report alpha measured against something else entirely.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from datetime import date, timedelta
from pathlib import Path

import httpx
import numpy as np

from icarus.agents.data.nseactions import NseCorporateActions
from icarus.agents.data.source import SourceUnavailableError
from icarus.agents.data.yahoo import YahooDailySource
from icarus.common.config import load_goal
from icarus.common.logging import get_logger
from icarus.common.types import AssetClass
from icarus.engine.panelbuild import build_panel, save_panel, session_axis, sessions_in
from icarus.strategy.dsl import Bars

log = get_logger("scripts.build_panel")

CALENDAR = Path("var/calendar.json")
BHAVCOPY = Path("var/bhavcopy")
ACTIONS = Path("var/corpactions")
PANEL = Path("var/panel.npz")
REPORT = Path("var/panel_report.json")

BENCHMARK_SYMBOL = "^NSEI"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="frm", type=date.fromisoformat, default=None)
    parser.add_argument("--to", dest="to", type=date.fromisoformat, default=None)
    parser.add_argument("--out", type=Path, default=PANEL)
    parser.add_argument(
        "--lockbox",
        action="store_true",
        help="build ACROSS the lockbox boundary. Only for the single final evaluation.",
    )
    parser.add_argument("--no-benchmark", action="store_true", help="skip the Nifty 50 fetch")
    args = parser.parse_args()

    goal = load_goal()
    split = goal.data_split
    frm = args.frm or split.walk_forward_start
    to = args.to or (split.lockbox_start - timedelta(days=1))

    if to >= split.lockbox_start and not args.lockbox:
        raise SystemExit(
            f"refusing to build a panel reaching {to}: the lockbox opens {split.lockbox_start} "
            f"and is spent exactly once (invariant #26). A panel containing it would let every "
            f"run read it for free. Pass --lockbox only for the final go/no-go."
        )
    if args.lockbox:
        log.warning(
            "BUILDING ACROSS THE LOCKBOX BOUNDARY — this panel must be used once and only for "
            "the final evaluation",
            lockbox_start=str(split.lockbox_start),
            to=str(to),
        )

    # Filesystem setup stays outside the event loop (ASYNC240): blocking pathlib calls inside a
    # coroutine are exactly what that rule exists to catch, and this script is async-first.
    ACTIONS.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    sessions = sessions_in(CALENDAR, frm, to)
    log.info("panel span", frm=str(sessions[0]), to=str(sessions[-1]), sessions=len(sessions))

    panel, report = asyncio.run(_assemble(sessions, goal, skip_benchmark=args.no_benchmark))
    save_panel(panel, report, args.out)

    REPORT.write_text(
        json.dumps(
            {
                "frm": str(sessions[0]),
                "to": str(sessions[-1]),
                "has_benchmark": panel.benchmark is not None,
                **report.as_json(),
                "low_quality_sessions_detail": [
                    {"session": str(day), "score": round(score, 4)}
                    for day, score in sorted(report.low_quality_sessions)
                ],
                "quarantined": [
                    {
                        "symbol": q.symbol,
                        "at": str(q.at),
                        "ratio": round(q.ratio, 4),
                        "action_on_file": q.had_action_on_file,
                    }
                    for q in sorted(report.quarantines, key=lambda q: q.symbol)
                ],
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    log.info("panel written", panel=str(args.out), report=str(REPORT))


async def _assemble(sessions: list[date], goal: object, *, skip_benchmark: bool) -> tuple:
    frm, to = sessions[0], sessions[-1]
    async with httpx.AsyncClient(timeout=90.0, follow_redirects=True) as client:
        actions = await NseCorporateActions(client, ACTIONS).history(frm, to)
        benchmark = None if skip_benchmark else await _benchmark(client, sessions)
    return build_panel(
        sessions=sessions,
        cache_dir=BHAVCOPY,
        actions=actions,
        universe=goal.universe,  # type: ignore[attr-defined]
        quality=goal.data_quality,  # type: ignore[attr-defined]
        benchmark=benchmark,
    )


async def _benchmark(client: httpx.AsyncClient, sessions: list[date]) -> Bars | None:
    """Nifty 50 aligned to the panel's session axis, or ``None`` if Yahoo will not serve it.

    Index levels are forward-filled onto sessions Yahoo is missing rather than left as ``nan``:
    an index has no "did not trade" state, and a hole in the benchmark would make every
    index-relative word nan for that date across the whole universe at once. Leading sessions
    before Yahoo's first point stay ``nan`` — there is nothing to carry forward from.
    """
    try:
        candles = await YahooDailySource(client).daily_bars(
            BENCHMARK_SYMBOL, sessions[0], sessions[-1]
        )
    except SourceUnavailableError as exc:
        log.warning("no benchmark: index-relative words will refuse to evaluate", error=str(exc))
        return None

    by_day = {c.ts.date(): c for c in candles}
    fields = ("open", "high", "low", "close", "volume")
    columns = {name: np.full(len(sessions), np.nan, dtype=np.float64) for name in fields}
    last = None
    for t, day in enumerate(sessions):
        candle = by_day.get(day) or last
        if candle is None:
            continue
        for name in fields:
            columns[name][t] = float(getattr(candle.ohlcv, name))
        last = candle

    covered = int(np.count_nonzero(~np.isnan(columns["close"])))
    log.info(
        "benchmark loaded",
        symbol=BENCHMARK_SYMBOL,
        asset_class=AssetClass.EQUITY.value,
        sessions_covered=covered,
        of=len(sessions),
    )
    return Bars(ts=session_axis(sessions), **columns)


if __name__ == "__main__":
    main()
