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

**A network timeout is retried here; it is never allowed to become a market holiday.** That
distinction is the whole reason this loop exists. :func:`backfill.scan` records a weekday with no
bhavcopy in *either* archive as an exchange closure — which is correct, because NSE declining to
publish an end-of-day file is real evidence the market was shut. A read timeout is not that
evidence, so the library raises ``TransientSourceError`` and refuses to guess, and it is right to.
But a single hiccup two thousand files into an hour-long unattended download should not throw the
run away, so the *script* retries. Re-running is nearly free: every session already on disk is
served from the cache, so a retry fast-forwards to wherever it stopped.

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
from icarus.agents.data.source import TransientSourceError
from icarus.common.config import load_goal
from icarus.common.logging import get_logger

log = get_logger("scripts.backfill")

CACHE_DIR = Path("var/bhavcopy")
ARTIFACT = Path("var/calendar.json")
MAX_ATTEMPTS = 12
BACKOFF_SECONDS = 30.0
# Generous: NSE's archive is free and occasionally slow, and a longer wait costs only wall-clock
# on a run that is already measured in tens of minutes. A tight timeout buys nothing here.
REQUEST_TIMEOUT_SECONDS = 90.0


def main() -> None:
    """Parse arguments and prepare the filesystem, then hand off to the async scan.

    Setup stays synchronous and outside the event loop deliberately: blocking filesystem calls
    inside a coroutine are exactly what ``ASYNC240`` flags, and this codebase is async-first
    everywhere else, so the exception should not start here.
    """
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
    result = asyncio.run(_scan_with_retries(frm, to))
    backfill.save(result, ARTIFACT)
    log.info(
        "backfill complete",
        sessions=len(result.sessions),
        closures=len(result.closures),
        artifact=str(ARTIFACT),
    )


async def _scan_with_retries(frm: date, to: date) -> backfill.BackfillResult:
    """Scan the range, retrying the whole pass when the network — not the exchange — fails.

    Only :class:`TransientSourceError` is retried. Anything else propagates: a schema change or a
    parse failure is a real problem, and re-running it twelve times would only bury the message.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT_SECONDS) as client:
                return await backfill.scan(NseBhavcopySource(client, CACHE_DIR), frm, to)
        except TransientSourceError as exc:
            if attempt == MAX_ATTEMPTS:
                raise
            cached = await asyncio.to_thread(lambda: len(list(CACHE_DIR.glob("*"))))
            log.warning(
                "transient source failure — retrying from the cache",
                attempt=attempt,
                of=MAX_ATTEMPTS,
                sessions_on_disk=cached,
                error=str(exc),
            )
            await asyncio.sleep(BACKOFF_SECONDS)
    raise AssertionError("unreachable: the final attempt either returns or re-raises")


if __name__ == "__main__":
    main()
