"""Task 1.1 — data ingestion: happy path AND the halt paths (CLAUDE.md §6).

The halt paths matter most here: a feed that keeps running on a misunderstood response is how a
backtest silently becomes fiction. Every source therefore gets an induced-drift test.
"""

from __future__ import annotations

import asyncio
import csv
import io
import json
import zipfile
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from icarus.agents.base import RunContext
from icarus.agents.data.agent import DataIngestionAgent, FeedSpec
from icarus.agents.data.cache import CachedDailySource, DailyBarCache
from icarus.agents.data.crosscheck import cross_check
from icarus.agents.data.fetch import RateLimiter, with_retry
from icarus.agents.data.nse import NseBhavcopySource, bhavcopy_url
from icarus.agents.data.source import (
    DailyBarSource,
    SourceUnavailableError,
    TransientSourceError,
)
from icarus.agents.data.yahoo import YahooDailySource
from icarus.common.schemas import SchemaError
from icarus.common.types import OHLCV, AssetClass, Candle, MarketData

# --------------------------------------------------------------------------------------
# Fixtures shaped like the real payloads (both verified against live endpoints 2026-07-28)
# --------------------------------------------------------------------------------------
# 1735703100 = 2025-01-01 03:45 UTC = 09:15 IST — Yahoo stamps a daily bar at the session open.
_TS_A, _TS_B = 1735703100, 1735789500


def _yahoo_payload(*, quote: dict[str, list[Any]] | None = None) -> dict[str, Any]:
    return {
        "chart": {
            "error": None,
            "result": [
                {
                    "meta": {"currency": "INR", "symbol": "RELIANCE.NS"},
                    "timestamp": [_TS_A, _TS_B],
                    "indicators": {
                        "quote": [
                            quote
                            if quote is not None
                            else {
                                "open": [1214.85, 1220.0],
                                "high": [1226.30, 1230.0],
                                "low": [1211.60, 1215.0],
                                "close": [1221.25, 1228.0],
                                "volume": [5892590, 6000000],
                            }
                        ],
                        "adjclose": [{"adjclose": [1221.25, 1228.0]}],
                    },
                }
            ],
        }
    }


_BHAVCOPY_COLUMNS = [
    "TradDt",
    "BizDt",
    "Sgmt",
    "FinInstrmTp",
    "ISIN",
    "TckrSymb",
    "SctySrs",
    "OpnPric",
    "HghPric",
    "LwPric",
    "ClsPric",
    "TtlTradgVol",
]


def _bhavcopy_zip(rows: list[dict[str, str]], columns: list[str] | None = None) -> bytes:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=columns or _BHAVCOPY_COLUMNS)
    writer.writeheader()
    writer.writerows(rows)
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("BhavCopy_NSE_CM_0_0_0_20260724_F_0000.csv", buf.getvalue())
    return out.getvalue()


def _equity_row(**overrides: str) -> dict[str, str]:
    row = {
        "TradDt": "2026-07-24",
        "BizDt": "2026-07-24",
        "Sgmt": "CM",
        "FinInstrmTp": "STK",
        "ISIN": "INE002A01018",
        "TckrSymb": "RELIANCE",
        "SctySrs": "EQ",
        "OpnPric": "1265.00",
        "HghPric": "1283.40",
        "LwPric": "1249.80",
        "ClsPric": "1278.00",
        "TtlTradgVol": "9817000",
    }
    row.update(overrides)
    return row


def _client(handler: object) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)  # type: ignore[arg-type]
    return httpx.AsyncClient(transport=transport)


def _candle(day: str, close: str, *, high: str = "10", low: str = "1") -> Candle:
    return Candle(
        ts=datetime.fromisoformat(f"{day}T03:45:00+00:00"),
        ohlcv=OHLCV(
            open=Decimal("5"),
            high=Decimal(high),
            low=Decimal(low),
            close=Decimal(close),
            volume=Decimal("100"),
        ),
    )


# --------------------------------------------------------------------------------------
# Yahoo source
# --------------------------------------------------------------------------------------
async def test_yahoo_parses_verified_shape() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_yahoo_payload())

    async with _client(handler) as http:
        bars = await YahooDailySource(http).daily_bars(
            "RELIANCE.NS", date(2025, 1, 1), date(2025, 1, 2)
        )

    assert [c.ts.date() for c in bars] == [date(2025, 1, 1), date(2025, 1, 2)]
    assert bars[0].ohlcv.close == Decimal("1221.25")
    # Session-open stamping is what makes the UTC date equal the IST trading date.
    assert bars[0].ts == datetime(2025, 1, 1, 3, 45, tzinfo=UTC)


async def test_yahoo_replay_is_deterministic() -> None:
    """The same payload must always normalize to the identical bars (replay test, 1.1 V)."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=_yahoo_payload())

    async with _client(handler) as http:
        source = YahooDailySource(http)
        first = await source.daily_bars("RELIANCE.NS", date(2025, 1, 1), date(2025, 1, 2))
        second = await source.daily_bars("RELIANCE.NS", date(2025, 1, 1), date(2025, 1, 2))

    assert first == second


async def test_yahoo_renamed_field_raises_schema_error() -> None:
    """Induced schema drift: Yahoo renames 'close' -> 'closePrice'. Never best-effort parse."""
    drifted = _yahoo_payload(
        quote={
            "open": [1214.85, 1220.0],
            "high": [1226.30, 1230.0],
            "low": [1211.60, 1215.0],
            "closePrice": [1221.25, 1228.0],
            "volume": [5892590, 6000000],
        }
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=drifted)

    async with _client(handler) as http:
        with pytest.raises(SchemaError, match="close"):
            await YahooDailySource(http).daily_bars(
                "RELIANCE.NS", date(2025, 1, 1), date(2025, 1, 2)
            )


async def test_yahoo_truncated_series_raises_schema_error() -> None:
    """A quote array shorter than the timestamps would silently misalign every bar."""
    drifted = _yahoo_payload(
        quote={
            "open": [1214.85],
            "high": [1226.30],
            "low": [1211.60],
            "close": [1221.25],
            "volume": [5892590],
        }
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=drifted)

    async with _client(handler) as http:
        with pytest.raises(SchemaError):
            await YahooDailySource(http).daily_bars(
                "RELIANCE.NS", date(2025, 1, 1), date(2025, 1, 2)
            )


async def test_yahoo_null_session_is_skipped_not_filled() -> None:
    """A no-trade session is a hole. Skipping is honest; forward-filling would fabricate a bar."""
    payload = _yahoo_payload(
        quote={
            "open": [1214.85, None],
            "high": [1226.30, None],
            "low": [1211.60, None],
            "close": [1221.25, None],
            "volume": [5892590, None],
        }
    )

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async with _client(handler) as http:
        bars = await YahooDailySource(http).daily_bars(
            "RELIANCE.NS", date(2025, 1, 1), date(2025, 1, 2)
        )

    assert len(bars) == 1


async def test_yahoo_server_error_is_transient_but_404_is_not() -> None:
    def failing(status: int) -> object:
        def handler(_: httpx.Request) -> httpx.Response:
            return httpx.Response(status)

        return handler

    async with _client(failing(503)) as http:
        with pytest.raises(TransientSourceError):
            await YahooDailySource(http).daily_bars("X", date(2025, 1, 1), date(2025, 1, 2))

    async with _client(failing(404)) as http:
        with pytest.raises(SourceUnavailableError):
            await YahooDailySource(http).daily_bars("X", date(2025, 1, 1), date(2025, 1, 2))


# --------------------------------------------------------------------------------------
# NSE bhavcopy source
# --------------------------------------------------------------------------------------
async def test_nse_parses_verified_columns(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == bhavcopy_url(date(2026, 7, 24))
        return httpx.Response(200, content=_bhavcopy_zip([_equity_row()]))

    async with _client(handler) as http:
        source = NseBhavcopySource(http, tmp_path)
        bars = await source.daily_bars("RELIANCE", date(2026, 7, 24), date(2026, 7, 24))

    assert len(bars) == 1
    # Fixed-point strings become exact Decimals — no float ever touches a price.
    assert bars[0].ohlcv.close == Decimal("1278.00")
    assert bars[0].ts == datetime(2026, 7, 24, 3, 45, tzinfo=UTC)


async def test_nse_accepts_yahoo_style_symbol(tmp_path: Path) -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_bhavcopy_zip([_equity_row()]))

    async with _client(handler) as http:
        bars = await NseBhavcopySource(http, tmp_path).daily_bars(
            "RELIANCE.NS", date(2026, 7, 24), date(2026, 7, 24)
        )

    assert len(bars) == 1


async def test_nse_skips_non_equity_rows(tmp_path: Path) -> None:
    rows = [
        _equity_row(),
        _equity_row(TckrSymb="SOMEETF", SctySrs="BE"),
        _equity_row(TckrSymb="SOMEBOND", FinInstrmTp="DEBT"),
    ]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_bhavcopy_zip(rows))

    async with _client(handler) as http:
        source = NseBhavcopySource(http, tmp_path)
        assert await source.daily_bars("SOMEETF", date(2026, 7, 24), date(2026, 7, 24)) == []
        assert await source.daily_bars("RELIANCE", date(2026, 7, 24), date(2026, 7, 24)) != []


async def test_nse_missing_column_raises_schema_error(tmp_path: Path) -> None:
    """Induced drift: NSE drops ClsPric from the layout."""
    columns = [c for c in _BHAVCOPY_COLUMNS if c != "ClsPric"]
    rows = [{k: v for k, v in _equity_row().items() if k != "ClsPric"}]

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=_bhavcopy_zip(rows, columns))

    async with _client(handler) as http:
        with pytest.raises(SchemaError, match="ClsPric"):
            await NseBhavcopySource(http, tmp_path).daily_bars(
                "RELIANCE", date(2026, 7, 24), date(2026, 7, 24)
            )


async def test_nse_missing_day_file_raises_rather_than_leaving_a_hole(tmp_path: Path) -> None:
    """A trading day with no archive file must fail loudly — a silent gap looks like a holiday."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(404)

    async with _client(handler) as http:
        with pytest.raises(SourceUnavailableError, match="2026-07-24"):
            await NseBhavcopySource(http, tmp_path).daily_bars(
                "RELIANCE", date(2026, 7, 24), date(2026, 7, 24)
            )


async def test_nse_day_cache_serves_every_symbol_from_one_download(tmp_path: Path) -> None:
    """One file per session covers all symbols — the second symbol must not re-download."""
    downloads = 0
    rows = [_equity_row(), _equity_row(TckrSymb="TCS", ClsPric="3100.00")]

    def handler(_: httpx.Request) -> httpx.Response:
        nonlocal downloads
        downloads += 1
        return httpx.Response(200, content=_bhavcopy_zip(rows))

    async with _client(handler) as http:
        source = NseBhavcopySource(http, tmp_path)
        await source.daily_bars("RELIANCE", date(2026, 7, 24), date(2026, 7, 24))
        tcs = await source.daily_bars("TCS", date(2026, 7, 24), date(2026, 7, 24))

    assert downloads == 1
    assert tcs[0].ohlcv.close == Decimal("3100.00")


async def test_nse_skips_weekends_and_holidays(tmp_path: Path) -> None:
    """26 Jan 2026 is Republic Day; 24-25 Jan is a weekend. Only the 27th should be fetched."""
    requested: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requested.append(str(request.url))
        return httpx.Response(200, content=_bhavcopy_zip([_equity_row()]))

    async with _client(handler) as http:
        await NseBhavcopySource(http, tmp_path).daily_bars(
            "RELIANCE", date(2026, 1, 24), date(2026, 1, 27)
        )

    assert requested == [bhavcopy_url(date(2026, 1, 27))]


# --------------------------------------------------------------------------------------
# Retry + rate limiter
# --------------------------------------------------------------------------------------
async def test_retry_recovers_after_transient_failures() -> None:
    attempts = 0

    async def flaky() -> str:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise TransientSourceError("connection reset")
        return "ok"

    assert await with_retry(flaky, what="test", base_delay_s=0.0) == "ok"
    assert attempts == 3


async def test_retry_gives_up_after_configured_attempts() -> None:
    attempts = 0

    async def always_failing() -> str:
        nonlocal attempts
        attempts += 1
        raise TransientSourceError("down")

    with pytest.raises(TransientSourceError):
        await with_retry(always_failing, what="test", attempts=3, base_delay_s=0.0)
    assert attempts == 3


async def test_retry_never_retries_schema_error() -> None:
    """Retrying a changed response format just fails three times slower — halt on the first."""
    attempts = 0

    async def drifted() -> str:
        nonlocal attempts
        attempts += 1
        raise SchemaError("field renamed")

    with pytest.raises(SchemaError):
        await with_retry(drifted, what="test", base_delay_s=0.0)
    assert attempts == 1


async def test_rate_limiter_schedules_absolute_slots_without_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each call is scheduled at start + N x interval, not 'interval after the previous returned'.

    Asserted on the requested sleep durations rather than elapsed wall-clock: Windows' timer
    granularity (~16 ms) makes a real-time assertion flaky without proving anything extra.
    """
    delays: list[float] = []
    real_sleep = asyncio.sleep

    async def fake_sleep(delay: float) -> None:
        delays.append(delay)
        await real_sleep(0)

    monkeypatch.setattr(asyncio, "sleep", fake_sleep)

    limiter = RateLimiter(rate_per_s=50.0)  # 20 ms apart
    for _ in range(3):
        await limiter.acquire()

    # First call passes freely; the next two wait until slot 1 (20 ms) and slot 2 (40 ms).
    assert len(delays) == 2
    assert delays[0] == pytest.approx(0.02, abs=0.005)
    assert delays[1] == pytest.approx(0.04, abs=0.005)


async def test_rate_limiter_rejects_nonsense_rate() -> None:
    with pytest.raises(ValueError, match="positive"):
        RateLimiter(rate_per_s=0.0)


# --------------------------------------------------------------------------------------
# Cache
# --------------------------------------------------------------------------------------
class _CountingSource:
    """Minimal DailyBarSource that records how often it was actually asked to fetch."""

    def __init__(self, bars: list[Candle]) -> None:
        self._bars = bars
        self.calls = 0

    @property
    def name(self) -> str:
        return "counting"

    def supports(self, asset_class: AssetClass) -> bool:
        return True

    async def daily_bars(self, symbol: str, frm: date, to: date) -> list[Candle]:
        self.calls += 1
        return [c for c in self._bars if frm <= c.ts.date() <= to]


async def test_cache_second_read_hits_disk_and_preserves_decimals(tmp_path: Path) -> None:
    inner = _CountingSource([_candle("2026-07-20", "1278.00"), _candle("2026-07-21", "1290.55")])
    cache = DailyBarCache(tmp_path)
    source = CachedDailySource(inner, cache)

    first = await source.daily_bars("RELIANCE", date(2026, 7, 20), date(2026, 7, 21))
    second = await source.daily_bars("RELIANCE", date(2026, 7, 20), date(2026, 7, 21))

    assert inner.calls == 1
    assert first == second
    assert second[1].ohlcv.close == Decimal("1290.55")
    assert cache.stats.hits == 1
    assert cache.stats.misses == 1
    assert cache.stats.hit_rate == pytest.approx(0.5)


async def test_cache_hit_rate_is_zero_before_any_lookup(tmp_path: Path) -> None:
    assert DailyBarCache(tmp_path).stats.hit_rate == 0.0


async def test_cache_widening_the_range_refetches_the_union(tmp_path: Path) -> None:
    """Fetching the union keeps the covered window contiguous, so it can never hide a gap."""
    bars = [_candle(f"2026-07-{d:02d}", "100") for d in (20, 21, 22, 23)]
    inner = _CountingSource(bars)
    cache = DailyBarCache(tmp_path)
    source = CachedDailySource(inner, cache)

    await source.daily_bars("RELIANCE", date(2026, 7, 22), date(2026, 7, 23))
    widened = await source.daily_bars("RELIANCE", date(2026, 7, 20), date(2026, 7, 23))

    assert inner.calls == 2
    assert [c.ts.date().day for c in widened] == [20, 21, 22, 23]
    # And the widened range is now cached in full.
    assert await source.daily_bars("RELIANCE", date(2026, 7, 20), date(2026, 7, 23)) == widened
    assert inner.calls == 2


async def test_cache_survives_a_corrupt_file(tmp_path: Path) -> None:
    """A corrupt cache file must be discarded and refetched, never parsed into junk bars."""
    inner = _CountingSource([_candle("2026-07-20", "1278.00")])
    cache = DailyBarCache(tmp_path)
    source = CachedDailySource(inner, cache)
    await source.daily_bars("RELIANCE", date(2026, 7, 20), date(2026, 7, 20))

    corrupt = tmp_path / "counting" / "RELIANCE.json"
    corrupt.write_text("{ this is not json", encoding="utf-8")

    bars = await source.daily_bars("RELIANCE", date(2026, 7, 20), date(2026, 7, 20))
    assert bars[0].ohlcv.close == Decimal("1278.00")
    assert inner.calls == 2


async def test_cache_symbol_with_slash_is_filesystem_safe(tmp_path: Path) -> None:
    inner = _CountingSource([_candle("2026-07-20", "42")])
    source = CachedDailySource(inner, DailyBarCache(tmp_path))
    await source.daily_bars("BTC/USDT", date(2026, 7, 20), date(2026, 7, 20))
    assert (tmp_path / "counting" / "BTC_USDT.json").exists()


async def test_cached_source_applies_retry(tmp_path: Path) -> None:
    class _Flaky(_CountingSource):
        async def daily_bars(self, symbol: str, frm: date, to: date) -> list[Candle]:
            self.calls += 1
            if self.calls < 2:
                raise TransientSourceError("blip")
            return self._bars

    inner = _Flaky([_candle("2026-07-20", "7")])
    source = CachedDailySource(inner, DailyBarCache(tmp_path))
    bars = await source.daily_bars("X", date(2026, 7, 20), date(2026, 7, 20))
    assert inner.calls == 2
    assert len(bars) == 1


# --------------------------------------------------------------------------------------
# Cross-check
# --------------------------------------------------------------------------------------
def test_cross_check_reports_agreement() -> None:
    bars = [_candle("2026-07-20", "100.00"), _candle("2026-07-21", "101.00")]
    report = cross_check("RELIANCE", "yahoo", bars, "nse_bhavcopy", list(bars))
    assert report.fully_aligned
    assert report.agreement_rate == 1.0
    assert report.compared_days == 2


def test_cross_check_flags_a_price_disagreement() -> None:
    a = [_candle("2026-07-20", "100.00"), _candle("2026-07-21", "101.00")]
    b = [_candle("2026-07-20", "100.00"), _candle("2026-07-21", "150.00")]
    report = cross_check("RELIANCE", "yahoo", a, "nse_bhavcopy", b)

    assert not report.clean
    assert [d.field for d in report.disagreements] == ["close"]
    assert report.disagreements[0].day == date(2026, 7, 21)
    assert report.agreement_rate == pytest.approx(0.5)


def test_cross_check_tolerates_sub_tolerance_rounding() -> None:
    a = [_candle("2026-07-20", "1000.00")]
    b = [_candle("2026-07-20", "1000.40")]  # 0.04% — vendor rounding, not a bad price
    assert cross_check("X", "yahoo", a, "nse", b).clean


def test_cross_check_separates_coverage_gaps_from_value_gaps() -> None:
    a = [_candle("2026-07-20", "100.00"), _candle("2026-07-21", "101.00")]
    b = [_candle("2026-07-20", "100.00")]
    report = cross_check("X", "yahoo", a, "nse", b)

    assert report.clean  # values agree everywhere both have data...
    assert not report.fully_aligned  # ...but coverage differs, and that is reported separately
    assert report.only_in_a == (date(2026, 7, 21),)
    assert report.only_in_b == ()


def test_cross_check_ignores_volume_unless_asked() -> None:
    a = [_candle("2026-07-20", "100.00")]
    b_candle = Candle(
        ts=a[0].ts,
        ohlcv=OHLCV(
            open=a[0].ohlcv.open,
            high=a[0].ohlcv.high,
            low=a[0].ohlcv.low,
            close=a[0].ohlcv.close,
            volume=Decimal("999999"),
        ),
    )
    assert cross_check("X", "yahoo", a, "nse", [b_candle]).clean
    assert not cross_check("X", "yahoo", a, "nse", [b_candle], compare_volume=True).clean


# --------------------------------------------------------------------------------------
# The agent
# --------------------------------------------------------------------------------------
class _StubSource:
    """Source returning canned bars per symbol, or raising a canned error."""

    def __init__(
        self, bars: dict[str, list[Candle]], errors: dict[str, Exception] | None = None
    ) -> None:
        self._bars = bars
        self._errors = errors or {}

    @property
    def name(self) -> str:
        return "stub"

    def supports(self, asset_class: AssetClass) -> bool:
        return True

    async def daily_bars(self, symbol: str, frm: date, to: date) -> list[Candle]:
        if symbol in self._errors:
            raise self._errors[symbol]
        return self._bars.get(symbol, [])


def _ctx(halt_after: int) -> RunContext:
    """A kill-line that fires after ``halt_after`` checks, so the agent loop terminates."""
    calls = 0

    async def should_halt() -> bool:
        nonlocal calls
        calls += 1
        return calls > halt_after

    return RunContext(should_halt=should_halt)


def _now_2026_07_24() -> datetime:
    return datetime(2026, 7, 24, 12, 0, tzinfo=UTC)


async def test_agent_publishes_normalized_market_data() -> None:
    bars = [_candle("2026-07-20", "1278.00"), _candle("2026-07-21", "1290.00")]
    published: list[MarketData] = []

    async def publish(msg: MarketData) -> None:
        published.append(msg)

    async def alert(_: str) -> None:
        pytest.fail("no alert expected on the happy path")

    agent = DataIngestionAgent(
        [FeedSpec("RELIANCE", AssetClass.EQUITY)],
        _StubSource({"RELIANCE": bars}),
        publish=publish,
        alert=alert,
        poll_interval_s=0.0,
        now_fn=_now_2026_07_24,
    )
    await agent.run(_ctx(halt_after=2))

    assert [m.symbol for m in published] == ["RELIANCE", "RELIANCE"]
    assert published[0].asset_class is AssetClass.EQUITY
    assert published[0].ohlcv.close == Decimal("1278.00")
    assert published[0].ts == bars[0].ts
    assert published[0].schema_version == MarketData.SCHEMA_VERSION


async def test_agent_publishes_each_bar_only_once() -> None:
    """Re-emitting a bar would double-count it in every downstream metric."""
    bars = [_candle("2026-07-20", "1278.00")]
    published: list[MarketData] = []

    async def publish(msg: MarketData) -> None:
        published.append(msg)

    async def alert(_: str) -> None:
        return None

    agent = DataIngestionAgent(
        [FeedSpec("RELIANCE", AssetClass.EQUITY)],
        _StubSource({"RELIANCE": bars}),
        publish=publish,
        alert=alert,
        poll_interval_s=0.0,
        now_fn=_now_2026_07_24,
    )
    await agent.run(_ctx(halt_after=5))  # several full cycles over the same bar

    assert len(published) == 1


async def test_agent_stops_promptly_when_the_kill_line_is_raised() -> None:
    published: list[MarketData] = []

    async def publish(msg: MarketData) -> None:
        published.append(msg)

    async def alert(_: str) -> None:
        return None

    agent = DataIngestionAgent(
        [FeedSpec("RELIANCE", AssetClass.EQUITY)],
        _StubSource({"RELIANCE": [_candle("2026-07-20", "1")]}),
        publish=publish,
        alert=alert,
        poll_interval_s=0.0,
        now_fn=_now_2026_07_24,
    )
    await agent.run(_ctx(halt_after=0))  # halted before the first poll

    assert published == []


async def test_schema_drift_halts_only_the_affected_feed() -> None:
    """Equity data breaking must not stop the crypto plane (PRD §38)."""
    published: list[MarketData] = []
    alerts: list[str] = []

    async def publish(msg: MarketData) -> None:
        published.append(msg)

    async def alert(msg: str) -> None:
        alerts.append(msg)

    agent = DataIngestionAgent(
        [FeedSpec("RELIANCE", AssetClass.EQUITY), FeedSpec("BTC-USD", AssetClass.CRYPTO)],
        _StubSource(
            {"BTC-USD": [_candle("2026-07-20", "5000000")]},
            errors={"RELIANCE": SchemaError("close renamed")},
        ),
        publish=publish,
        alert=alert,
        poll_interval_s=0.0,
        now_fn=_now_2026_07_24,
    )
    await agent.run(_ctx(halt_after=4))

    assert agent.halted_feeds == frozenset({"equity:RELIANCE"})
    assert [m.symbol for m in published] == ["BTC-USD"]
    assert len(alerts) == 1
    assert "RELIANCE" in alerts[0]


async def test_agent_returns_when_every_feed_has_halted() -> None:
    """With no working inputs there is nothing to do — do not let the supervisor restart-loop."""
    alerts: list[str] = []

    async def publish(_: MarketData) -> None:
        pytest.fail("nothing should publish when every feed is drifted")

    async def alert(msg: str) -> None:
        alerts.append(msg)

    agent = DataIngestionAgent(
        [FeedSpec("A", AssetClass.EQUITY), FeedSpec("B", AssetClass.EQUITY)],
        _StubSource({}, errors={"A": SchemaError("x"), "B": SchemaError("y")}),
        publish=publish,
        alert=alert,
        poll_interval_s=0.0,
        now_fn=_now_2026_07_24,
    )
    # Never halts externally: the agent must terminate on its own.
    await asyncio.wait_for(agent.run(RunContext(should_halt=_never)), timeout=2.0)

    assert len(agent.halted_feeds) == 2
    assert len(alerts) == 2


async def _never() -> bool:
    return False


async def test_agent_withholds_the_in_progress_session() -> None:
    """A partial bar must never be published as final — its close has not happened yet (#12/#13)."""
    published: list[MarketData] = []

    async def publish(msg: MarketData) -> None:
        published.append(msg)

    async def alert(_: str) -> None:
        return None

    # 09:00 UTC on 24 Jul 2026 = 14:30 IST — mid-session, before the 15:30 IST close.
    def mid_session() -> datetime:
        return datetime(2026, 7, 24, 9, 0, tzinfo=UTC)

    agent = DataIngestionAgent(
        [FeedSpec("RELIANCE", AssetClass.EQUITY), FeedSpec("BTC-USD", AssetClass.CRYPTO)],
        _StubSource(
            {
                "RELIANCE": [_candle("2026-07-23", "100"), _candle("2026-07-24", "101")],
                "BTC-USD": [_candle("2026-07-23", "5000"), _candle("2026-07-24", "5100")],
            }
        ),
        publish=publish,
        alert=alert,
        poll_interval_s=0.0,
        now_fn=mid_session,
    )
    # 3 checks = one full cycle: loop top, then one before each of the two feeds.
    await agent.run(_ctx(halt_after=3))

    # Yesterday's bars only; today's are still open for both markets.
    assert [(m.symbol, m.ts.date()) for m in published] == [
        ("RELIANCE", date(2026, 7, 23)),
        ("BTC-USD", date(2026, 7, 23)),
    ]


async def test_agent_publishes_the_equity_bar_once_the_session_closes() -> None:
    """After 15:30 IST the equity bar is final, while the crypto day still has hours to run."""
    published: list[MarketData] = []

    async def publish(msg: MarketData) -> None:
        published.append(msg)

    async def alert(_: str) -> None:
        return None

    # 11:00 UTC = 16:30 IST — after the equity close, still mid-UTC-day for crypto.
    def after_equity_close() -> datetime:
        return datetime(2026, 7, 24, 11, 0, tzinfo=UTC)

    agent = DataIngestionAgent(
        [FeedSpec("RELIANCE", AssetClass.EQUITY), FeedSpec("BTC-USD", AssetClass.CRYPTO)],
        _StubSource(
            {
                "RELIANCE": [_candle("2026-07-24", "101")],
                "BTC-USD": [_candle("2026-07-24", "5100")],
            }
        ),
        publish=publish,
        alert=alert,
        poll_interval_s=0.0,
        now_fn=after_equity_close,
    )
    await agent.run(_ctx(halt_after=3))  # one full cycle over both feeds

    assert [m.symbol for m in published] == ["RELIANCE"]


async def test_agent_rejects_a_feed_its_source_cannot_serve() -> None:
    """NSE bhavcopy is equity-only. Pairing it with a crypto feed must fail loudly at wiring time,
    not return nothing forever while looking healthy."""

    class _EquityOnly(_StubSource):
        def supports(self, asset_class: AssetClass) -> bool:
            return asset_class is AssetClass.EQUITY

    async def publish(_: MarketData) -> None:
        return None

    async def alert(_: str) -> None:
        return None

    with pytest.raises(ValueError, match="crypto:BTC-USD"):
        DataIngestionAgent(
            [FeedSpec("RELIANCE", AssetClass.EQUITY), FeedSpec("BTC-USD", AssetClass.CRYPTO)],
            _EquityOnly({}),
            publish=publish,
            alert=alert,
        )


async def test_agent_requires_at_least_one_feed() -> None:
    async def publish(_: MarketData) -> None:
        return None

    async def alert(_: str) -> None:
        return None

    with pytest.raises(ValueError, match="at least one feed"):
        DataIngestionAgent([], _StubSource({}), publish=publish, alert=alert)


def test_sources_satisfy_the_protocol(tmp_path: Path) -> None:
    """Structural check that both concrete sources really are DailyBarSources."""
    client = httpx.AsyncClient()
    assert isinstance(YahooDailySource(client), DailyBarSource)
    assert isinstance(NseBhavcopySource(client, tmp_path), DailyBarSource)


def test_bhavcopy_url_matches_the_verified_archive_layout() -> None:
    assert bhavcopy_url(date(2026, 7, 24)).endswith(
        "/BhavCopy_NSE_CM_0_0_0_20260724_F_0000.csv.zip"
    )


def test_cache_file_is_written_atomically(tmp_path: Path) -> None:
    """No .tmp file may survive a successful write."""
    cache = DailyBarCache(tmp_path)
    cache.store(
        "s", "SYM", date(2026, 7, 20), date(2026, 7, 20), [_candle("2026-07-20", "1")], None
    )
    assert list((tmp_path / "s").glob("*.tmp")) == []
    stored = json.loads((tmp_path / "s" / "SYM.json").read_text(encoding="utf-8"))
    assert stored["covered_from"] == "2026-07-20"
