"""Safe-calling primitives for external data endpoints (task 1.1).

Everything a source needs to talk to the outside world safely lives here, so each new provider
inherits the behaviour instead of copying it:

* :class:`RateLimiter` — spaces requests so we never exceed a venue's cap. Exceeding one gets us
  throttled or blocked, and a blocked data feed is a halted plane.
* :func:`get_or_raise` — one HTTP GET that maps transport and status failures onto the error
  taxonomy in :mod:`icarus.agents.data.source`. This mapping is the thing invariant #10 depends on
  being uniform: if one source classified a 503 as fatal and another as retryable, "fail safe"
  would mean something different per venue. It is written once, here.
* :func:`with_retry` — 3 attempts with exponential backoff, and **only** for
  :class:`~icarus.agents.data.source.TransientSourceError`. A ``SchemaError`` propagates on the
  first attempt: retrying a changed response format just fails three times slower, and the correct
  response to drift is to halt the feed, not to try harder.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, TypeVar

import httpx

from icarus.agents.data.source import SourceUnavailableError, TransientSourceError
from icarus.common.logging import get_logger

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping

log = get_logger("data.fetch")

# Classic TypeVar rather than PEP 695 `def with_retry[T]`: mypy is pinned to 1.11.2 (see
# pyproject — Smart App Control blocks the compiled wheel on the dev machine) and 1.11 does not
# support PEP 695 generics. Revisit when that pin lifts.
T = TypeVar("T")

# Both Yahoo and the NSE archive refuse or throttle clients without a browser-like User-Agent
# (verified 2026-07-28). Identifying the project keeps us honest with the free hosts.
HTTP_HEADERS = {"User-Agent": "Mozilla/5.0 (compatible; icarus-research/0.1)"}

# Statuses worth retrying: rate-limit and server-side faults. Everything else is our problem.
RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})

# The free public archives publish no cap, so stay deliberately polite rather than be blocked.
# Broker caps (Kite: 3 historical/s, 1 quote/s, PRD §11.2) land with the broker-backed source.
COURTESY_PER_S = 2.0


class RateLimiter:
    """Serializes and spaces async calls to at most ``rate_per_s`` per second.

    Schedule-based rather than sleep-after-call, so a slow response does not let the next call
    fire early and burst past the cap. Safe to share across tasks — the lock makes concurrent
    ``acquire`` calls queue rather than all pass at once.
    """

    def __init__(self, rate_per_s: float) -> None:
        if rate_per_s <= 0:
            raise ValueError(f"rate_per_s must be positive, got {rate_per_s}")
        self._min_interval = 1.0 / rate_per_s
        self._lock = asyncio.Lock()
        self._next_at: float | None = None

    async def acquire(self) -> None:
        """Wait until this caller is allowed to issue its request."""
        async with self._lock:
            now = asyncio.get_running_loop().time()
            if self._next_at is not None and self._next_at > now:
                await asyncio.sleep(self._next_at - now)
                now = self._next_at
            self._next_at = now + self._min_interval


async def get_or_raise(
    client: httpx.AsyncClient,
    url: str,
    *,
    what: str,
    params: Mapping[str, str] | None = None,
    limiter: RateLimiter | None = None,
) -> httpx.Response:
    """GET ``url``, raising the right error type for the failure that occurred.

    Transport faults and retryable statuses become :class:`TransientSourceError`; any other
    non-200 becomes :class:`SourceUnavailableError`. ``limiter`` is acquired per *request*, which
    is the only granularity that works for a source issuing many requests per logical fetch.
    """
    if limiter is not None:
        await limiter.acquire()
    try:
        response = await client.get(url, params=params, headers=HTTP_HEADERS)
    except httpx.HTTPError as exc:  # timeout, connection reset, DNS — retrying is reasonable
        raise TransientSourceError(f"{what}: {exc}") from exc
    if response.status_code in RETRYABLE_STATUS:
        raise TransientSourceError(f"{what}: HTTP {response.status_code}")
    if response.status_code != httpx.codes.OK:
        raise SourceUnavailableError(f"{what}: HTTP {response.status_code}")
    return response


async def with_retry(  # noqa: UP047 — see the TypeVar note above (mypy 1.11 pin)
    op: Callable[[], Awaitable[T]],
    *,
    what: str,
    attempts: int = 3,
    base_delay_s: float = 1.0,
) -> T:
    """Run ``op``, retrying transient failures with exponential backoff (1s, 2s, 4s...).

    Only :class:`TransientSourceError` is retried. Everything else — notably ``SchemaError`` —
    propagates immediately to the caller, which halts the feed.
    """
    if attempts < 1:
        raise ValueError(f"attempts must be >= 1, got {attempts}")
    for attempt in range(1, attempts + 1):
        try:
            return await op()
        except TransientSourceError as exc:
            if attempt == attempts:
                log.error("transient fetch failed; giving up", what=what, attempts=attempts)
                raise
            delay = base_delay_s * 2 ** (attempt - 1)
            log.warning(
                "transient fetch failure; retrying",
                what=what,
                attempt=attempt,
                retry_in_s=delay,
                error=str(exc),
            )
            await asyncio.sleep(delay)
    raise AssertionError("unreachable: loop either returns or raises")  # pragma: no cover
