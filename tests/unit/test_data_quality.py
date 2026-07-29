"""Task 1.1b — Data-QA layer: every reject rule, both staleness blast radii, and the agent wiring.

The load-bearing acceptance criterion is "a bad tick never trips a stop". In Phase 1 there is no
stop to trip, so the equivalent proof is that a bad bar never reaches the bus at all.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal

import pytest

from icarus.agents.base import RunContext
from icarus.agents.data.agent import DataIngestionAgent, FeedSpec
from icarus.agents.data.quality import DataQualityGate, Reason, Verdict
from icarus.common.config import DataQuality
from icarus.common.types import OHLCV, AssetClass, Candle, MarketData

# 2026-07-20..24 is Mon-Fri, none of them NSE holidays; 25-26 is the weekend.
_MON, _TUE, _WED, _THU, _FRI = (date(2026, 7, d) for d in (20, 21, 22, 23, 24))
_SAT = date(2026, 7, 25)


def _cfg(**overrides: float | int) -> DataQuality:
    base: dict[str, float | int] = {
        "atr_window": 3,
        "max_bar_move_atr": 8.0,
        "max_single_bar_move": 0.5,
        "min_day_score": 0.98,
        "stale_sessions_symbol_veto": 2,
        "stale_plane_halt_ratio": 0.5,
    }
    base.update(overrides)
    return DataQuality(**base)


def _bar(
    day: date,
    close: str,
    *,
    open_: str | None = None,
    high: str | None = None,
    low: str | None = None,
    volume: str = "1000",
) -> Candle:
    c = Decimal(close)
    return Candle(
        ts=datetime.combine(day, datetime.min.time(), tzinfo=UTC).replace(hour=3, minute=45),
        ohlcv=OHLCV(
            open=Decimal(open_) if open_ is not None else c,
            high=Decimal(high) if high is not None else c,
            low=Decimal(low) if low is not None else c,
            close=c,
            volume=Decimal(volume),
        ),
    )


def _assess(gate: DataQualityGate, candle: Candle, feed: str = "equity:X") -> Verdict:
    return gate.assess(feed, AssetClass.EQUITY, candle).verdict


# --------------------------------------------------------------------------------------
# Structural rules — wrong regardless of history
# --------------------------------------------------------------------------------------
def test_accepts_a_normal_bar() -> None:
    gate = DataQualityGate(_cfg())
    assert _assess(gate, _bar(_MON, "100", high="102", low="99")) is Verdict.ACCEPT


def test_rejects_non_positive_price() -> None:
    gate = DataQualityGate(_cfg())
    bad = _bar(_MON, "0", high="0", low="0")
    result = gate.assess("equity:X", AssetClass.EQUITY, bad)
    assert result.verdict is Verdict.REJECT
    assert result.reason is Reason.NON_POSITIVE_PRICE


def test_rejects_high_below_low() -> None:
    gate = DataQualityGate(_cfg())
    result = gate.assess("equity:X", AssetClass.EQUITY, _bar(_MON, "100", high="90", low="110"))
    assert result.reason is Reason.INCOHERENT_OHLC


def test_rejects_close_outside_the_bar_range() -> None:
    gate = DataQualityGate(_cfg())
    result = gate.assess(
        "equity:X", AssetClass.EQUITY, _bar(_MON, "150", high="110", low="90", open_="100")
    )
    assert result.reason is Reason.INCOHERENT_OHLC


def test_rejects_negative_volume() -> None:
    gate = DataQualityGate(_cfg())
    result = gate.assess(
        "equity:X", AssetClass.EQUITY, _bar(_MON, "100", high="101", low="99", volume="-5")
    )
    assert result.reason is Reason.NEGATIVE_VOLUME


def test_rejects_an_equity_bar_on_a_closed_day() -> None:
    """A Saturday bar is fabricated — the calendar already knows the market was shut (§29.4)."""
    gate = DataQualityGate(_cfg())
    result = gate.assess("equity:X", AssetClass.EQUITY, _bar(_SAT, "100"))
    assert result.reason is Reason.NON_TRADING_DAY


def test_accepts_a_crypto_bar_on_a_weekend() -> None:
    """Crypto is 24/7, so the NSE calendar must not be applied to it."""
    gate = DataQualityGate(_cfg())
    assert gate.assess("crypto:BTC", AssetClass.CRYPTO, _bar(_SAT, "100")).accepted


def test_rejects_a_duplicate_session() -> None:
    gate = DataQualityGate(_cfg())
    assert _assess(gate, _bar(_MON, "100")) is Verdict.ACCEPT
    result = gate.assess("equity:X", AssetClass.EQUITY, _bar(_MON, "100"))
    assert result.reason is Reason.DUPLICATE_TIMESTAMP


# --------------------------------------------------------------------------------------
# History-relative rules
# --------------------------------------------------------------------------------------
def test_quarantines_a_probable_unadjusted_corporate_action() -> None:
    """A 1:2 split looks exactly like a 50% crash — the whole series becomes untrustworthy."""
    gate = DataQualityGate(_cfg())
    assert _assess(gate, _bar(_MON, "100")) is Verdict.ACCEPT
    result = gate.assess("equity:X", AssetClass.EQUITY, _bar(_TUE, "49"))

    assert result.verdict is Verdict.QUARANTINE
    assert result.reason is Reason.PROBABLE_CORPORATE_ACTION


def test_jump_test_is_silent_until_there_is_enough_history() -> None:
    """Judging a bar against no history would be theatre — the rule waits for atr_window bars."""
    gate = DataQualityGate(_cfg(atr_window=5))
    assert _assess(gate, _bar(_MON, "100", high="101", low="99")) is Verdict.ACCEPT
    # A wild excursion, but under the 50% close move, and no ATR baseline exists yet.
    assert _assess(gate, _bar(_TUE, "110", high="180", low="109")) is Verdict.ACCEPT


def test_rejects_an_implausible_spike_once_the_baseline_exists() -> None:
    """The bad-tick rule: a spike far outside the symbol's own range never reaches the bus."""
    gate = DataQualityGate(_cfg(atr_window=3))
    for day, close in ((_MON, "100"), (_TUE, "101"), (_WED, "102")):
        assert _assess(gate, _bar(day, close, high=str(int(close) + 1), low=str(int(close) - 1)))

    # ATR is ~2, so the limit is ~16. A high of 130 against a 102 close is an excursion of 28.
    result = gate.assess("equity:X", AssetClass.EQUITY, _bar(_THU, "108", high="130", low="107"))
    assert result.verdict is Verdict.REJECT
    assert result.reason is Reason.IMPLAUSIBLE_JUMP


def test_a_rejected_bar_does_not_poison_the_baseline() -> None:
    """Only accepted bars update history — otherwise one bad tick widens the band for the next."""
    gate = DataQualityGate(_cfg(atr_window=3))
    for day, close in ((_MON, "100"), (_TUE, "101"), (_WED, "102")):
        gate.assess("equity:X", AssetClass.EQUITY, _bar(day, close, high=close, low=close))
    gate.assess("equity:X", AssetClass.EQUITY, _bar(_THU, "108", high="130", low="107"))
    # The next genuine spike is still measured against the clean baseline, so it is still caught.
    result = gate.assess("equity:X", AssetClass.EQUITY, _bar(_FRI, "108", high="131", low="107"))
    assert result.reason is Reason.IMPLAUSIBLE_JUMP


# --------------------------------------------------------------------------------------
# Day score
# --------------------------------------------------------------------------------------
def test_day_score_counts_accepted_over_seen() -> None:
    gate = DataQualityGate(_cfg())
    gate.assess("equity:X", AssetClass.EQUITY, _bar(_MON, "100"))
    gate.assess("equity:X", AssetClass.EQUITY, _bar(_MON, "100"))  # duplicate -> rejected

    score = gate.day_score("equity:X", _MON)
    assert (score.accepted, score.rejected, score.seen) == (1, 1, 2)
    assert score.score == pytest.approx(0.5)


def test_clean_days_are_not_reported_as_low_quality() -> None:
    gate = DataQualityGate(_cfg())
    gate.assess("equity:X", AssetClass.EQUITY, _bar(_MON, "100"))
    assert gate.low_quality_days() == ()


def test_low_quality_day_is_surfaced_for_the_gate() -> None:
    """A low-scoring window becomes NEEDS_MORE_DATA at the validation gate (§29.4)."""
    gate = DataQualityGate(_cfg())
    gate.assess("equity:X", AssetClass.EQUITY, _bar(_MON, "100"))
    gate.assess("equity:X", AssetClass.EQUITY, _bar(_MON, "100"))

    low = gate.low_quality_days()
    assert len(low) == 1
    feed, session, score = low[0]
    assert (feed, session) == ("equity:X", _MON)
    assert score == pytest.approx(0.5)


def test_unseen_day_scores_one() -> None:
    """Nothing seen means nothing went wrong — an empty window must not read as bad data."""
    assert DataQualityGate(_cfg()).day_score("equity:X", _MON).score == 1.0


# --------------------------------------------------------------------------------------
# Staleness — the two blast radii
# --------------------------------------------------------------------------------------
def test_symbol_is_not_stale_after_a_single_missed_session() -> None:
    gate = DataQualityGate(_cfg(stale_sessions_symbol_veto=2))
    gate.assess("equity:X", AssetClass.EQUITY, _bar(_MON, "100"))
    assert gate.stale_feeds({"equity:X": AssetClass.EQUITY}, _TUE) == frozenset()


def test_symbol_goes_stale_after_the_configured_missed_sessions() -> None:
    gate = DataQualityGate(_cfg(stale_sessions_symbol_veto=2))
    gate.assess("equity:X", AssetClass.EQUITY, _bar(_MON, "100"))
    assert gate.stale_feeds({"equity:X": AssetClass.EQUITY}, _WED) == frozenset({"equity:X"})


def test_equity_staleness_ignores_weekends() -> None:
    """A long weekend must not look like a dead feed every Monday."""
    gate = DataQualityGate(_cfg(stale_sessions_symbol_veto=2))
    gate.assess("equity:X", AssetClass.EQUITY, _bar(_FRI, "100"))
    assert gate.stale_feeds({"equity:X": AssetClass.EQUITY}, date(2026, 7, 27)) == frozenset()


def test_crypto_staleness_counts_calendar_days() -> None:
    """Crypto trades every day, so a missed day IS a missed session — weekends are not an excuse."""
    gate = DataQualityGate(_cfg(stale_sessions_symbol_veto=2))
    gate.assess("crypto:BTC", AssetClass.CRYPTO, _bar(_FRI, "100"))
    assert gate.stale_feeds({"crypto:BTC": AssetClass.CRYPTO}, date(2026, 7, 27)) == frozenset(
        {"crypto:BTC"}
    )


def test_a_feed_that_never_produced_a_bar_is_new_not_stale() -> None:
    gate = DataQualityGate(_cfg())
    assert gate.stale_feeds({"equity:X": AssetClass.EQUITY}, _FRI) == frozenset()


def test_one_stale_symbol_out_of_many_does_not_condemn_the_plane() -> None:
    gate = DataQualityGate(_cfg(stale_plane_halt_ratio=0.5))
    feeds = {f"equity:{s}": AssetClass.EQUITY for s in "ABCD"}
    assert not gate.plane_is_dead(feeds, frozenset({"equity:A"}))


def test_enough_stale_feeds_means_the_venue_is_dead() -> None:
    gate = DataQualityGate(_cfg(stale_plane_halt_ratio=0.5))
    feeds = {f"equity:{s}": AssetClass.EQUITY for s in "ABCD"}
    assert gate.plane_is_dead(feeds, frozenset({"equity:A", "equity:B"}))


def test_plane_with_no_live_feeds_is_not_reported_dead() -> None:
    assert not DataQualityGate(_cfg()).plane_is_dead({}, frozenset())


def test_a_single_feed_going_stale_does_condemn_its_plane() -> None:
    """Deliberate: with one feed there is no evidence separating "this symbol is quiet" from
    "the venue is dead", and 100% of the plane stale means no usable data either way. The narrow
    symbol-veto radius only has meaning once a plane has several feeds to compare."""
    gate = DataQualityGate(_cfg(stale_plane_halt_ratio=0.5))
    assert gate.plane_is_dead({"equity:A": AssetClass.EQUITY}, frozenset({"equity:A"}))


# --------------------------------------------------------------------------------------
# Agent wiring
# --------------------------------------------------------------------------------------
class _FixedSource:
    """Returns canned bars regardless of the requested range."""

    def __init__(self, bars: dict[str, list[Candle]]) -> None:
        self._bars = bars

    @property
    def name(self) -> str:
        return "fixed"

    def supports(self, asset_class: AssetClass) -> bool:
        return True

    @property
    def prices_are_split_adjusted(self) -> bool:
        return False

    async def daily_bars(self, symbol: str, frm: date, to: date) -> list[Candle]:
        return self._bars.get(symbol, [])


def _ctx(halt_after: int) -> RunContext:
    calls = 0

    async def should_halt() -> bool:
        nonlocal calls
        calls += 1
        return calls > halt_after

    return RunContext(should_halt=should_halt)


def _now_next_monday() -> datetime:
    # After the 27th's equity close, so every bar from the 20th-24th counts as final.
    return datetime(2026, 7, 27, 11, 0, tzinfo=UTC)


def _now_after_close(day: date) -> datetime:
    """16:30 IST on ``day`` — past the equity close, so that day's bar is final and nothing is
    yet stale. Keeps a QA test about QA rather than accidentally about staleness."""
    return datetime.combine(day, datetime.min.time(), tzinfo=UTC).replace(hour=11)


async def test_a_bad_bar_never_reaches_the_bus() -> None:
    """The 1.1b acceptance criterion, in Phase-1 terms: QA runs before publish, not after."""
    published: list[MarketData] = []

    async def publish(msg: MarketData) -> None:
        published.append(msg)

    async def alert(_: str) -> None:
        return None

    async def halt_plane(_: str) -> None:
        pytest.fail("one bad bar must not halt the plane")

    bars = [
        _bar(_MON, "100", high="101", low="99"),
        _bar(_TUE, "0", high="0", low="0"),  # structurally impossible
        _bar(_WED, "102", high="103", low="101"),
    ]
    agent = DataIngestionAgent(
        [FeedSpec("X", AssetClass.EQUITY)],
        _FixedSource({"X": bars}),
        publish=publish,
        alert=alert,
        quality=DataQualityGate(_cfg()),
        halt_plane=halt_plane,
        poll_interval_s=0.0,
        now_fn=lambda: _now_after_close(_WED),
    )
    await agent.run(_ctx(halt_after=2))

    assert [m.ts.date() for m in published] == [_MON, _WED]


async def test_quarantine_halts_that_feed_and_pages() -> None:
    published: list[MarketData] = []
    alerts: list[str] = []

    async def publish(msg: MarketData) -> None:
        published.append(msg)

    async def alert(msg: str) -> None:
        alerts.append(msg)

    async def halt_plane(_: str) -> None:
        return None

    bars = [_bar(_MON, "100"), _bar(_TUE, "49")]  # 51% drop -> probable unadjusted split
    agent = DataIngestionAgent(
        [FeedSpec("X", AssetClass.EQUITY)],
        _FixedSource({"X": bars}),
        publish=publish,
        alert=alert,
        quality=DataQualityGate(_cfg()),
        halt_plane=halt_plane,
        poll_interval_s=0.0,
        now_fn=lambda: _now_after_close(_TUE),
    )
    await agent.run(_ctx(halt_after=4))

    assert agent.halted_feeds == frozenset({"equity:X"})
    assert [m.ts.date() for m in published] == [_MON]
    assert any("quarantine" in a for a in alerts)


async def test_a_dead_venue_halts_the_plane() -> None:
    """Every feed stale at once is the venue, not the symbols — halt (operator decision)."""
    alerts: list[str] = []
    halts: list[str] = []

    async def publish(_: MarketData) -> None:
        return None

    async def alert(msg: str) -> None:
        alerts.append(msg)

    async def halt_plane(reason: str) -> None:
        halts.append(reason)

    # Both feeds last produced a bar on the 20th; "now" is the 27th — many sessions later.
    agent = DataIngestionAgent(
        [FeedSpec("A", AssetClass.EQUITY), FeedSpec("B", AssetClass.EQUITY)],
        _FixedSource({"A": [_bar(_MON, "100")], "B": [_bar(_MON, "200")]}),
        publish=publish,
        alert=alert,
        quality=DataQualityGate(_cfg()),
        halt_plane=halt_plane,
        poll_interval_s=0.0,
        now_fn=_now_next_monday,
    )
    await agent.run(_ctx(halt_after=10))

    assert len(halts) == 1
    assert "2/2 feeds stale" in halts[0]
    assert any("plane halted" in a for a in alerts)


async def test_one_stale_symbol_only_vetoes_that_symbol() -> None:
    """The narrow blast radius: the plane keeps running, the quiet symbol gets no new entries."""
    fresh = [_bar(_MON, "100"), _bar(_TUE, "101"), _bar(_WED, "102"), _bar(_THU, "103")]
    fresh.append(_bar(_FRI, "104"))

    async def publish(_: MarketData) -> None:
        return None

    async def alert(_: str) -> None:
        return None

    halts: list[str] = []

    async def halt_plane(reason: str) -> None:
        halts.append(reason)

    # Four feeds; only one is stale, which is under the 0.5 plane-halt ratio.
    agent = DataIngestionAgent(
        [FeedSpec(s, AssetClass.EQUITY) for s in ("A", "B", "C", "D")],
        _FixedSource({"A": [_bar(_MON, "100")], "B": fresh, "C": fresh, "D": fresh}),
        publish=publish,
        alert=alert,
        quality=DataQualityGate(_cfg()),
        halt_plane=halt_plane,
        poll_interval_s=0.0,
        now_fn=_now_next_monday,
    )
    await agent.run(_ctx(halt_after=6))

    assert halts == []
    assert agent.vetoed_feeds == frozenset({"equity:A"})


async def test_quality_gate_without_a_halt_channel_is_refused() -> None:
    """Accepting a gate that can demand a plane halt, with nowhere to send it, is unsafe wiring."""

    async def publish(_: MarketData) -> None:
        return None

    async def alert(_: str) -> None:
        return None

    with pytest.raises(ValueError, match="halt_plane"):
        DataIngestionAgent(
            [FeedSpec("X", AssetClass.EQUITY)],
            _FixedSource({}),
            publish=publish,
            alert=alert,
            quality=DataQualityGate(_cfg()),
        )


def test_config_rejects_a_no_op_quality_gate() -> None:
    """A gate loosened until it accepts everything is not a gate."""
    with pytest.raises(ValueError, match="max_single_bar_move"):
        _cfg(max_single_bar_move=1.5)
