"""Data-QA layer (task 1.1b, PRD §29.3-29.4, invariant #10).

Sits between ingestion and everything else (PRD §28). Its job is to catch data that is *wrong*,
as distinct from data that is merely *missing* — a gap is honest, a bad price is not.

**Bad bars are rejected, never winsorized.** §29.4 permits either. Clamping a suspicious price
back into a believable band invents a price that never traded, and every metric downstream then
treats the invention as fact. Rejecting leaves a hole the day's quality score accounts for.

The verdicts, in increasing severity:

* ``ACCEPT`` — the bar is usable.
* ``REJECT`` — this bar is unusable; drop it and count it against the day's score. The series is
  still trustworthy.
* ``QUARANTINE`` — the *symbol* is untrustworthy, not just this bar. A >50% single-bar move is
  indistinguishable from an unadjusted 1:2 split (§29.3), so trading or backtesting the series
  would be trading an artifact. Stop the symbol and let a human look.

**Why the jump test is relative, not absolute.** "More than ₹50" means nothing across a ₹20 stock
and a ₹80,000 index. The test is against the symbol's *own* recent true range (ATR), and it stays
disabled until ``atr_window`` bars exist — judging a bar against no history would be theatre.

**Staleness has two blast radii** (operator decision, 2026-07-28, reconciling §29.4 with §37):
one symbol quiet while its siblings update is a symbol problem → veto that symbol; most of a
plane's feeds quiet at once means the venue is dead → halt the plane.
"""

from __future__ import annotations

import enum
from collections import deque
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING

from icarus.common.calendar import is_nse_trading_day
from icarus.common.logging import get_logger
from icarus.common.types import AssetClass

if TYPE_CHECKING:
    from collections.abc import Mapping

    from icarus.common.config import DataQuality as DataQualityConfig
    from icarus.common.types import Candle

log = get_logger("data.quality")


class Verdict(enum.StrEnum):
    ACCEPT = "accept"
    REJECT = "reject"
    QUARANTINE = "quarantine"


class Reason(enum.StrEnum):
    """Why a bar was not accepted. Recorded verbatim in the audit log — never collapsed to 'bad'."""

    NON_POSITIVE_PRICE = "non_positive_price"
    INCOHERENT_OHLC = "incoherent_ohlc"
    NEGATIVE_VOLUME = "negative_volume"
    NON_TRADING_DAY = "non_trading_day"
    DUPLICATE_TIMESTAMP = "duplicate_timestamp"
    IMPLAUSIBLE_JUMP = "implausible_jump"
    PROBABLE_CORPORATE_ACTION = "probable_corporate_action"


@dataclass(frozen=True)
class Assessment:
    """One bar's verdict, with the reason when it is not ACCEPT."""

    verdict: Verdict
    reason: Reason | None = None
    detail: str = ""

    @property
    def accepted(self) -> bool:
        return self.verdict is Verdict.ACCEPT


@dataclass
class DayScore:
    """Accepted-vs-seen counts for one session (§29.4: the gate reads this)."""

    accepted: int = 0
    rejected: int = 0

    @property
    def seen(self) -> int:
        return self.accepted + self.rejected

    @property
    def score(self) -> float:
        """Share of bars that survived QA. ``1.0`` when nothing was seen (nothing went wrong)."""
        return self.accepted / self.seen if self.seen else 1.0


@dataclass
class _FeedState:
    """Per-feed memory the checks need: what we have seen and the recent true ranges.

    ``true_ranges`` is a bounded deque: only the ATR window matters and a feed runs for years,
    so the maxlen does the trimming.
    """

    true_ranges: deque[Decimal]
    seen_days: set[date] = field(default_factory=set)
    last_close: Decimal | None = None
    last_session: date | None = None


class DataQualityGate:
    """Stateful per-feed bar validator. One instance per ingestion agent.

    Deliberately *not* an async agent: it does no I/O, so it stays a pure function of (config,
    history, bar). That makes every rule directly testable, which matters more here than matching
    the PRD's "sub-agent" wording — it occupies the same position in the pipeline either way.
    """

    def __init__(self, config: DataQualityConfig) -> None:
        self._cfg = config
        self._feeds: dict[str, _FeedState] = {}
        self._scores: dict[tuple[str, date], DayScore] = {}

    # -- assessment ---------------------------------------------------------------------
    def assess(self, feed_key: str, asset_class: AssetClass, candle: Candle) -> Assessment:
        """Judge one bar and fold the outcome into the feed's state and the day's score."""
        state = self._feeds.setdefault(
            feed_key, _FeedState(true_ranges=deque(maxlen=self._cfg.atr_window))
        )
        session = candle.ts.date()
        assessment = self._check(state, asset_class, candle, session)

        score = self._scores.setdefault((feed_key, session), DayScore())
        if assessment.accepted:
            score.accepted += 1
            self._remember(state, candle, session)
        else:
            score.rejected += 1
            log.warning(
                "bar failed data-QA",
                feed=feed_key,
                session=str(session),
                verdict=assessment.verdict,
                reason=assessment.reason,
                detail=assessment.detail,
            )
        return assessment

    def _check(
        self, state: _FeedState, asset_class: AssetClass, candle: Candle, session: date
    ) -> Assessment:
        """Run the rules in order: structural first (unconditional), then history-relative."""
        ohlcv = candle.ohlcv
        prices = (ohlcv.open, ohlcv.high, ohlcv.low, ohlcv.close)

        if any(p <= 0 for p in prices):
            return Assessment(Verdict.REJECT, Reason.NON_POSITIVE_PRICE, f"prices={prices}")
        if ohlcv.volume < 0:
            return Assessment(Verdict.REJECT, Reason.NEGATIVE_VOLUME, f"volume={ohlcv.volume}")
        if ohlcv.high < ohlcv.low or not (
            ohlcv.low <= ohlcv.open <= ohlcv.high and ohlcv.low <= ohlcv.close <= ohlcv.high
        ):
            return Assessment(
                Verdict.REJECT,
                Reason.INCOHERENT_OHLC,
                f"o={ohlcv.open} h={ohlcv.high} l={ohlcv.low} c={ohlcv.close}",
            )
        # Equities only: crypto trades every day, so no calendar can fabricate a crypto bar.
        if asset_class is AssetClass.EQUITY and not is_nse_trading_day(session):
            return Assessment(Verdict.REJECT, Reason.NON_TRADING_DAY, str(session))
        if session in state.seen_days:
            return Assessment(Verdict.REJECT, Reason.DUPLICATE_TIMESTAMP, str(session))

        if state.last_close is None:
            return Assessment(Verdict.ACCEPT)

        # A >=50% bar is far more likely an unadjusted split/bonus than a real move (§29.3).
        # The comparison is inclusive on purpose: a textbook 1:2 split lands on exactly -50.000%,
        # so a strict ">" would miss the single most common corporate action there is.
        move = abs(ohlcv.close - state.last_close) / state.last_close
        if move >= Decimal(str(self._cfg.max_single_bar_move)):
            return Assessment(
                Verdict.QUARANTINE,
                Reason.PROBABLE_CORPORATE_ACTION,
                f"{move:.2%} move vs previous close {state.last_close}",
            )

        # Bad-tick test against the symbol's own volatility — silent until there is enough history.
        atr = self._atr(state)
        if atr is not None and atr > 0:
            excursion = max(abs(ohlcv.high - state.last_close), abs(ohlcv.low - state.last_close))
            limit = atr * Decimal(str(self._cfg.max_bar_move_atr))
            if excursion > limit:
                return Assessment(
                    Verdict.REJECT,
                    Reason.IMPLAUSIBLE_JUMP,
                    f"excursion {excursion} > {self._cfg.max_bar_move_atr}x ATR {atr}",
                )
        return Assessment(Verdict.ACCEPT)

    def _atr(self, state: _FeedState) -> Decimal | None:
        """Average true range over the configured window, or ``None`` until the deque is full."""
        window = self._cfg.atr_window
        if len(state.true_ranges) < window:
            return None
        return sum(state.true_ranges, Decimal(0)) / Decimal(window)

    def _remember(self, state: _FeedState, candle: Candle, session: date) -> None:
        """Fold an accepted bar into the feed's history."""
        ohlcv = candle.ohlcv
        previous = state.last_close
        true_range = (
            ohlcv.high - ohlcv.low
            if previous is None
            else max(
                ohlcv.high - ohlcv.low,
                abs(ohlcv.high - previous),
                abs(ohlcv.low - previous),
            )
        )
        state.true_ranges.append(true_range)
        state.seen_days.add(session)
        state.last_close = ohlcv.close
        state.last_session = session

    # -- staleness ----------------------------------------------------------------------
    def stale_feeds(self, feeds: Mapping[str, AssetClass], today: date) -> frozenset[str]:
        """Feeds with no accepted bar for ``stale_sessions_symbol_veto`` expected sessions.

        A feed that has never produced a bar is not yet stale — it is simply new; the missing-data
        case is covered by the day score, not by a staleness veto.
        """
        stale: set[str] = set()
        for key, asset_class in feeds.items():
            state = self._feeds.get(key)
            if state is None or state.last_session is None:
                continue
            missed = _expected_sessions_between(state.last_session, today, asset_class)
            if missed >= self._cfg.stale_sessions_symbol_veto:
                stale.add(key)
        return frozenset(stale)

    def plane_is_dead(self, feeds: Mapping[str, AssetClass], stale: frozenset[str]) -> bool:
        """True when enough of a plane's feeds are stale that the venue itself is the suspect.

        One quiet symbol is a symbol problem. Most of them quiet at once is a dead connection,
        and continuing to trade the rest on equally stale data is the failure §29.4 forbids.

        Note the single-feed consequence: a one-feed plane whose only feed is stale is always
        "dead" by this rule. That is intended — with nothing to compare against there is no
        evidence distinguishing a quiet symbol from a dead venue, and either way the plane has no
        usable data. The narrow symbol-veto radius only becomes meaningful with several feeds.
        """
        if not feeds:
            return False
        return len(stale & feeds.keys()) / len(feeds) >= self._cfg.stale_plane_halt_ratio

    # -- reporting ----------------------------------------------------------------------
    def day_score(self, feed_key: str, session: date) -> DayScore:
        return self._scores.get((feed_key, session), DayScore())

    def low_quality_days(self) -> tuple[tuple[str, date, float], ...]:
        """Sessions scoring below ``min_day_score`` — the gate turns these into NEEDS_MORE_DATA."""
        return tuple(
            (feed, session, score.score)
            for (feed, session), score in sorted(self._scores.items())
            if score.score < self._cfg.min_day_score
        )


def _expected_sessions_between(last: date, today: date, asset_class: AssetClass) -> int:
    """Sessions that should have produced a bar, strictly after ``last`` and up to ``today``.

    Crypto trades every calendar day, so a missed *day* is a missed session. Equities count only
    NSE trading days — otherwise a long weekend would masquerade as a dead feed every Monday.

    Raises ``CalendarDataMissing`` if a year's holiday list is not loaded: the ingestion agent
    lets that propagate, which crashes the agent into the supervisor and ultimately halts the
    plane. "I don't know whether a bar was due" must never quietly become "none was due" (§28).
    """
    if today <= last:
        return 0
    if asset_class is AssetClass.CRYPTO:
        return (today - last).days
    count = 0
    day = last + timedelta(days=1)
    while day <= today:
        if is_nse_trading_day(day):
            count += 1
        day += timedelta(days=1)
    return count
