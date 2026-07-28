"""On-disk daily-bar cache + read-through source wrapper (task 1.1).

A daily bar for a past session never changes, so it is worth fetching exactly once. Backtests
re-read the same years of history on every run; without a cache we would hammer the provider,
run slowly, and risk being blocked. Cache hit-rate is an explicit acceptance criterion for 1.1,
so :class:`CacheStats` is measured, not assumed.

**Storage.** One JSON file per (source, symbol) under ``<root>/<source>/<symbol>.json``, holding
the bars keyed by session date plus the contiguous ``[covered_from, covered_to]`` range actually
fetched. Prices are stored as *strings* and re-read as ``Decimal``: JSON floats would silently
round money, which is a correctness bug in a trading system, not a cosmetic one.

**Contiguity.** A cached range must be truthful — "I hold every bar between these dates" — or a
gap would masquerade as a run of holidays. :class:`CachedDailySource` therefore always refetches
the *union* of the stored range and the requested one, so the covered window never grows a hole.

**Session-date keying.** Bars are keyed by the UTC date of their timestamp. Every source stamps a
bar at its session open (see :func:`icarus.common.calendar.session_open_utc`), and the whole NSE
session sits inside one UTC date, so the UTC date and the IST trading date agree. That keeps bars
from different vendors directly comparable for the cross-check (PRD §29.5, invariant #22).

:func:`read_versioned_json` and :func:`write_atomic_json` are shared with the bhavcopy day-cache in
:mod:`icarus.agents.data.nse` so there is one implementation of "versioned JSON that survives a
corrupt file and an interrupted write", not two that can drift apart.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING, Any

from icarus.agents.data.fetch import with_retry
from icarus.common.logging import get_logger
from icarus.common.types import OHLCV, Candle

if TYPE_CHECKING:
    from icarus.agents.data.source import DailyBarSource
    from icarus.common.types import AssetClass

log = get_logger("data.cache")

_CACHE_SCHEMA = 1
_UNSAFE_PATH_CHARS = re.compile(r"[^A-Za-z0-9._-]")


def safe_name(name: str) -> str:
    """Filesystem-safe file stem for a symbol or source (``BTC/USDT`` -> ``BTC_USDT``)."""
    return _UNSAFE_PATH_CHARS.sub("_", name)


def read_versioned_json(path: Path, schema: int) -> dict[str, Any] | None:
    """Read a schema-stamped JSON file, or ``None`` if absent, stale-schema, or unreadable.

    A corrupt cache file must never take the system down or, worse, yield junk bars — discarding
    and refetching is always safe because the cache holds no information the source cannot resupply.
    """
    if not path.exists():
        return None
    try:
        payload: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        log.warning("discarding unreadable cache file", path=str(path), error=str(exc))
        return None
    if not isinstance(payload, dict) or payload.get("schema") != schema:
        return None  # absent or an older layout: treat as a miss and refetch
    return payload


def write_atomic_json(path: Path, payload: dict[str, Any]) -> None:
    """Write ``payload`` via a temp file + rename, so an interrupted write leaves no half file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(payload), encoding="utf-8")
    tmp.replace(path)


@dataclass
class CacheStats:
    """Hit/miss counters for one cache instance (1.1 AC: cache hit-rate measured)."""

    hits: int = 0
    misses: int = 0

    def record(self, *, hit: bool) -> None:
        if hit:
            self.hits += 1
        else:
            self.misses += 1

    @property
    def hit_rate(self) -> float:
        """Fraction of lookups served from disk. ``0.0`` before any lookup."""
        total = self.hits + self.misses
        return self.hits / total if total else 0.0


@dataclass(frozen=True)
class Entry:
    """One cached (source, symbol) file: the covered window and the bars inside it."""

    covered_from: date
    covered_to: date
    bars: dict[date, Candle]

    def covers(self, frm: date, to: date) -> bool:
        return self.covered_from <= frm and to <= self.covered_to

    def slice(self, frm: date, to: date) -> list[Candle]:
        """Bars within ``[frm, to]``, ascending. Filters before sorting — the window is small."""
        return sorted((c for day, c in self.bars.items() if frm <= day <= to), key=lambda c: c.ts)


class DailyBarCache:
    """JSON-on-disk cache of daily bars. Storage only — no fetching, no policy.

    Reads and writes are synchronous; callers on the event loop must wrap them in
    ``asyncio.to_thread`` (:class:`CachedDailySource` does).
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.stats = CacheStats()

    def _path(self, source: str, symbol: str) -> Path:
        return self.root / safe_name(source) / f"{safe_name(symbol)}.json"

    def load(self, source: str, symbol: str) -> Entry | None:
        """The stored entry for (source, symbol), or ``None`` if there is nothing usable."""
        payload = read_versioned_json(self._path(source, symbol), _CACHE_SCHEMA)
        if payload is None:
            return None
        try:
            return Entry(
                covered_from=date.fromisoformat(payload["covered_from"]),
                covered_to=date.fromisoformat(payload["covered_to"]),
                bars={
                    date.fromisoformat(day): _decode_candle(row)
                    for day, row in payload["bars"].items()
                },
            )
        except (KeyError, TypeError, ValueError) as exc:
            log.warning(
                "discarding malformed cache entry", source=source, symbol=symbol, error=str(exc)
            )
            return None

    def store(
        self,
        source: str,
        symbol: str,
        frm: date,
        to: date,
        bars: list[Candle],
        existing: Entry | None,
    ) -> None:
        """Merge ``bars`` into the entry and record ``[frm, to]`` as covered.

        ``frm``/``to`` must be the range actually fetched, not the range the caller wanted —
        recording an uncovered window as covered would turn a gap into phantom holidays.
        ``existing`` is passed in rather than re-read: the caller has just loaded it.
        """
        merged: dict[date, Candle] = dict(existing.bars) if existing else {}
        merged.update({c.ts.date(): c for c in bars})
        covered_from = min(frm, existing.covered_from) if existing else frm
        covered_to = max(to, existing.covered_to) if existing else to
        write_atomic_json(
            self._path(source, symbol),
            {
                "schema": _CACHE_SCHEMA,
                "covered_from": covered_from.isoformat(),
                "covered_to": covered_to.isoformat(),
                "bars": {day.isoformat(): _encode_candle(c) for day, c in sorted(merged.items())},
            },
        )


def _encode_candle(c: Candle) -> dict[str, str]:
    return {
        "ts": c.ts.isoformat(),
        "o": str(c.ohlcv.open),
        "h": str(c.ohlcv.high),
        "l": str(c.ohlcv.low),
        "c": str(c.ohlcv.close),
        "v": str(c.ohlcv.volume),
    }


def _decode_candle(row: dict[str, str]) -> Candle:
    return Candle(
        ts=datetime.fromisoformat(row["ts"]),
        ohlcv=OHLCV(
            open=Decimal(row["o"]),
            high=Decimal(row["h"]),
            low=Decimal(row["l"]),
            close=Decimal(row["c"]),
            volume=Decimal(row["v"]),
        ),
    )


class CachedDailySource:
    """Wraps a :class:`DailyBarSource` with a read-through cache and retry.

    Implements ``DailyBarSource`` itself, so the agent above cannot tell the difference — it just
    gets bars, cheaply on the second call. Rate limiting lives in the sources (per HTTP request),
    not here: a source that issues many requests per logical fetch cannot be paced from outside.
    """

    def __init__(self, inner: DailyBarSource, cache: DailyBarCache) -> None:
        self._inner = inner
        self._cache = cache

    @property
    def name(self) -> str:
        return self._inner.name

    def supports(self, asset_class: AssetClass) -> bool:
        return self._inner.supports(asset_class)

    async def daily_bars(self, symbol: str, frm: date, to: date) -> list[Candle]:
        """Serve from cache when the range is fully covered, else fetch the union and store it.

        The entry is loaded exactly once and threaded through the miss path, so a miss costs one
        file read rather than three.
        """
        entry = await asyncio.to_thread(self._cache.load, self.name, symbol)
        hit = entry is not None and entry.covers(frm, to)
        self._cache.stats.record(hit=hit)
        if hit and entry is not None:
            return entry.slice(frm, to)

        # Fetch the union of what we hold and what was asked for, so "covered" stays contiguous.
        fetch_from = min(frm, entry.covered_from) if entry else frm
        fetch_to = max(to, entry.covered_to) if entry else to

        async def _call() -> list[Candle]:
            return await self._inner.daily_bars(symbol, fetch_from, fetch_to)

        bars = await with_retry(_call, what=f"{self.name}:{symbol}")
        await asyncio.to_thread(
            self._cache.store, self.name, symbol, fetch_from, fetch_to, bars, entry
        )
        return [c for c in bars if frm <= c.ts.date() <= to]
