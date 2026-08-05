"""Warm the bhavcopy day-cache and derive the trading calendar for the backtest span.

A one-off operational script, not library code. It walks every weekday from
``data_split.walk_forward_start`` to yesterday, downloading each session's end-of-day file into
``var/bhavcopy/`` and writing the derived session calendar to ``var/calendar.json``.

Run it once before the first real backtest; afterwards the engine reads from disk and never
touches the network. Interrupting and re-running is safe — a session already on disk is served
from the cache and costs no request.

It is slow by design: NSE serves this archive for free and every source in this codebase holds
itself to a 2 requests/second courtesy limit. Roughly 3,700 sessions since 2011 is half an hour
at best. Being blocked by NSE is a halted data plane (invariant #10), which is a far worse
outcome than waiting.

    uv run python scripts/backfill_bhavcopy.py [--from YYYY-MM-DD] [--to YYYY-MM-DD]
"""

from __future__ import annotations

import argparse
import asyncio
from datetime import date, timedelta
from pathlib import Path

import httpx

from icarus.agents.data import backfill
from icarus.agents.data.nse import NseBhavcopySource
from icarus.common.config import load_goal
from icarus.common.logging import get_logger

log = get_logger("scripts.backfill")

CACHE_DIR = Path("var/bhavcopy")
ARTIFACT = Path("var/calendar.json")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--from", dest="frm", type=date.fromisoformat, default=None)
    parser.add_argument("--to", dest="to", type=date.fromisoformat, default=None)
    args = parser.parse_args()

    goal = load_goal()
    frm = args.frm or goal.data_split.walk_forward_start
    to = args.to or (date.today() - timedelta(days=1))
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT.parent.mkdir(parents=True, exist_ok=True)

    log.info("backfill starting", frm=str(frm), to=str(to), cache=str(CACHE_DIR))
    async with httpx.AsyncClient(timeout=30.0) as client:
        source = NseBhavcopySource(client, CACHE_DIR)
        result = await backfill.scan(source, frm, to)
    backfill.save(result, ARTIFACT)
    log.info(
        "backfill complete",
        sessions=len(result.sessions),
        closures=len(result.closures),
        artifact=str(ARTIFACT),
    )


if __name__ == "__main__":
    asyncio.run(main())
