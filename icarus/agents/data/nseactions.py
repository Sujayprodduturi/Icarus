"""NSE corporate actions — the authoritative split/bonus history (task 1.7c, PRD §29.3).

Bhavcopy prices are the raw as-traded prices, so a 1:1 bonus reads as a clean 50% overnight
crash. Back-adjusting needs the exact ratio and the exact ex-date for every name that ever traded,
including names that have since been delisted. This module is where those come from.

**The obvious source is not the source.** Every bhavcopy row carries a previous-close field
(``PrvsClsgPric`` in the post-2024 UDiFF layout, ``PREVCLOSE`` in the legacy one), and it is
tempting to read the adjustment factor straight off it. It does not work — verified 2026-08-07
against both layouts and both RELIANCE bonuses::

    UDIFF  RELIANCE 2024-10-28  prev=2655.70  open=1337.00  close=1334.35   (1:1 bonus ex-date)
    LEGACY RELIANCE 2017-09-07  prev=1645.40  open= 823.00  close= 818.10   (1:1 bonus ex-date)

In both eras the field is the previous session's raw close, carried across the ex-date unadjusted.
``close[t-1] / prevclose[t]`` is therefore always 1.0 and tells us nothing.

**The source that does work** is NSE's own corporate-actions API, queried by date range::

    /api/corporates-corporateActions?index=equities&from_date=DD-MM-YYYY&to_date=DD-MM-YYYY

It returns ``symbol``, ``exDate``, ``series`` and a free-text ``subject`` such as ``'Bonus 1:1'``
or ``'Face Value Split (Sub-Division) - From Rs 10/- Per Share To Rs 5/- Per Share'``. Verified
2026-08-07 back to January 2011 (165 rows in 2011 Q1, 803 in 2017 Q3), covering delisted names
because it is indexed by date rather than by a current-instrument list.

    ⚠️ This supersedes the note in :mod:`icarus.agents.data.corpactions`, which recorded on
    2026-07-29 that this API serves only a rolling ~2-day window. That is true of the *default*
    call with no date range; with ``from_date``/``to_date`` it serves history. The Yahoo path
    remains for crypto and for cross-checking, but NSE is now the primary for equities: Yahoo has
    no split record at all for delisted names like RCOM, which are precisely the names a
    point-in-time universe must price honestly (invariant #14).

**Only capital changes are adjusted for.** Dividends are ignored on purpose — ``goal.yaml`` fixes
``dividend_convention: price_return``, so the ex-dividend drop is a real drop the strategy really
experiences (§29.3). Bonuses and splits are parsed exactly. Anything that moves the price by a
ratio this module cannot compute — demergers, rights, schemes of arrangement — is returned as an
:class:`Unpriceable` action rather than guessed at, and the panel builder quarantines the affected
history rather than trading through a discontinuity it cannot explain (invariant #10).
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING, Any

import httpx

from icarus.agents.data.cache import read_versioned_json, write_atomic_json
from icarus.agents.data.corpactions import Split
from icarus.agents.data.fetch import COURTESY_PER_S, RateLimiter, get_or_raise, with_retry
from icarus.agents.data.source import SourceUnavailableError, TransientSourceError
from icarus.common.logging import get_logger
from icarus.common.schemas import SchemaError

if TYPE_CHECKING:
    from collections.abc import Iterable
    from pathlib import Path

log = get_logger("data.nseactions")

HOME_URL = "https://www.nseindia.com"
ACTIONS_URL = "https://www.nseindia.com/api/corporates-corporateActions"

_CACHE_SCHEMA = 1
_EQUITY_SERIES = "EQ"

# NSE serves this endpoint per date range and gets slower the wider the range, so history is
# fetched a quarter at a time. Quarters also make the cache keys obvious and re-runnable.
_QUARTER_MONTHS = (1, 4, 7, 10)

_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}  # fmt: skip

# NSE's subject lines are free text typed by a human, and fifteen years of them contain
# abbreviations ("Fv Splt Frm Rs 10 To Rs 2"), long-hand ("Bonus Shares In The Ratio Of 1:1") and
# outright typos ("Annual Geneerl Meeting"). Every pattern below was widened to match a real
# string that the first, tighter version put in the `unrecognised` bucket — which is what that
# bucket is for. A missed split is not a missed row: it is a fabricated 80% crash in the panel.

# "Bonus 1:1", "Bonus issue 2:1", "Bonus Shares In The Ratio Of 1:34" — a new for every b held.
_BONUS_WORD = re.compile(r"\bbonus\b", re.IGNORECASE)
_RATIO = re.compile(r"(\d+)\s*:\s*(\d+)")

# NSE writes splits as e.g. "Face Value Split (Sub-Division) From Rs 10 Per Share To Rs 5 Per
# Share", plus abbreviated cousins. Also matches consolidations, where the "to" face value is
# the larger — a reverse split, which the same arithmetic handles with no special case.
_SPLIT_WORD = re.compile(r"\b(split|splt|sub-?\s?division|subdivision|fv)\b", re.IGNORECASE)
_FACE_VALUES = re.compile(
    r"\bfr(?:o)?m\b\s*(?:rs\.?|re\.?|inr)?\s*([\d.]+)\s*/?-?\s*(?:per\s+share)?\s*\bto\b\s*"
    r"(?:rs\.?|re\.?|inr)?\s*([\d.]+)",
    re.IGNORECASE,
)

# Things that move the price by a ratio not stated in the subject line. Listed explicitly so a
# new NSE wording shows up as an unrecognised subject rather than being silently swallowed.
_UNPRICEABLE = re.compile(
    r"\b(demerger|de-merger|scheme\s+of\s+arrangement|arrangement|amalgamation|merger|"
    r"rights?\s+issue|rights\b|spin[\s-]?off|capital\s+reduction|reduction\s+of\s+capital|"
    r"consolidation\s+of|reverse\s+split)\b",
    re.IGNORECASE,
)

# Subjects that never move the price by a ratio. Matched only to keep the "unrecognised" bucket
# meaningful — a dividend is not a data problem and must not be reported as one. Deliberately
# loose on meeting/closure wording because NSE's typos are unbounded and a false "benign" here
# costs nothing: this is consulted only after a ratio search has already come back empty.
# No trailing \b on purpose: NSE's typos are suffix typos ("Meetig", "Divdend", "Arangement"),
# so anchoring the end of the alternative is what put thirty-odd dividends in the unrecognised
# bucket. The leading \b still prevents matching inside an unrelated word.
_BENIGN = re.compile(
    r"\b(div|gene?e?ra?l\s+mee|mee|agm|egm|board\s+mee|"
    r"buy\s*back|buyback|postal\s+ballot|e\s*-?\s*voting|election|interest\s+pay|redemption|"
    r"bond|debenture|closure|record\s+date|annual\s+report|general\s+(corporate\s+)?purpose)",
    re.IGNORECASE,
)


class ActionsUnavailable(SourceUnavailableError):
    """Raised when the corporate-action history cannot be established for a span.

    Its own type because the consequence is specific: with no action history there is no honest
    way to back-adjust, and a backtest on unadjusted prices is not a degraded backtest but a
    meaningless one. Callers halt on this rather than proceeding with an empty split list.
    """


@dataclass(frozen=True, slots=True)
class Unpriceable:
    """A capital change whose ratio this module refuses to guess.

    Carried rather than dropped so the panel builder can quarantine the affected symbol-history.
    A demerger really does reprice the stock; silently treating it as a normal session hands the
    backtest a fabricated gap, and dropping it without trace hands it a fabricated continuity.
    """

    symbol: str
    ex_date: date
    subject: str


@dataclass(frozen=True, slots=True)
class ActionHistory:
    """Every capital change in a span, split into what can be priced and what cannot."""

    frm: date
    to: date
    splits: dict[str, tuple[Split, ...]]
    unpriceable: tuple[Unpriceable, ...]
    unrecognised: tuple[Unpriceable, ...]

    def splits_for(self, symbol: str) -> list[Split]:
        return list(self.splits.get(symbol.removesuffix(".NS").upper(), ()))

    def quarantined(self) -> frozenset[str]:
        """Symbols carrying a repricing event we could not compute a ratio for."""
        return frozenset(a.symbol for a in (*self.unpriceable, *self.unrecognised))


def parse_subject(subject: str) -> Decimal | None:
    """The share multiplier a subject line implies, or ``None`` if it implies no repricing.

    Returns *new shares per old share*, matching :class:`~icarus.agents.data.corpactions.Split`:
    a 1:1 bonus is ``2`` (you end up with two shares where you had one, so the price halves), a
    face-value split from ₹10 to ₹2 is ``5``, a consolidation from ₹1 to ₹10 is ``1/10``.

    Raises :class:`~icarus.common.schemas.SchemaError` for a subject that names a repricing event
    whose ratio it cannot extract — the caller must decide, and the decision must not be "assume
    nothing happened".
    """
    text = subject.strip()
    if not text:
        return None

    is_bonus = _BONUS_WORD.search(text) is not None
    is_split = _SPLIT_WORD.search(text) is not None
    is_unpriceable = _UNPRICEABLE.search(text) is not None

    # A line naming two events at once — "Bonus 1:1" alongside a rights issue — has a combined
    # factor that neither ratio alone describes. Checked before the priceable branches precisely
    # so that the bonus half cannot be applied on its own and quietly leave the rights half out.
    if is_unpriceable and (is_bonus or is_split):
        raise SchemaError(
            f"nse corporate action: combined repricing event, no single ratio applies: {subject!r}"
        )
    if is_unpriceable:
        raise SchemaError(
            f"nse corporate action: repricing event with no stated ratio: {subject!r}"
        )

    # A bonus and a split announced on one ex-date COMPOUND — they are two capital changes that
    # both land the same morning, not an either/or. HINDZINC's 'Bonus - 1:1 And Face Value Split
    # From Rs. 10 To Rs. 2' is 2 x 5 = 10, and returning the bonus alone left an unexplained 4.8x
    # discontinuity in the panel. Found 2026-08-07 by the gap audit in engine/panelbuild.py, which
    # is the only reason it was ever visible: the wrong factor still produces a plausible series.
    factor = Decimal(1)
    if is_bonus:
        factor *= _bonus_ratio(text, subject)
    if is_split:
        factor *= _split_ratio(text, subject)
    return factor if (is_bonus or is_split) else None


def _bonus_ratio(text: str, subject: str) -> Decimal:
    """``a:b`` — a new shares for every b held — as a share multiplier."""
    ratio = _RATIO.search(text)
    if ratio is None:
        raise SchemaError(f"nse corporate action: bonus with no ratio: {subject!r}")
    new, held = Decimal(ratio.group(1)), Decimal(ratio.group(2))
    if held <= 0:
        raise SchemaError(f"nse corporate action: bonus with zero denominator: {subject!r}")
    return (new + held) / held


def _split_ratio(text: str, subject: str) -> Decimal:
    """Face value before / after. A sub-division multiplies the share count by exactly that."""
    found = _FACE_VALUES.search(text)
    if found is None:
        raise SchemaError(f"nse corporate action: split with no face values: {subject!r}")
    before, after = Decimal(found.group(1)), Decimal(found.group(2))
    if before <= 0 or after <= 0:
        raise SchemaError(f"nse corporate action: non-positive face value: {subject!r}")
    return before / after


def parse_ex_date(raw: str) -> date | None:
    """NSE's ``DD-Mon-YYYY`` ex-date. Placeholders such as ``'-'`` become ``None``."""
    text = raw.strip()
    if not text or text == "-":
        return None
    parts = text.split("-")
    if len(parts) != 3:
        return None
    try:
        month = _MONTHS[parts[1][:3].upper()]
        return date(int(parts[2]), month, int(parts[0]))
    except (KeyError, ValueError):
        return None


class NseCorporateActions:
    """Fetches and caches NSE's corporate-action history, quarter by quarter.

    The endpoint needs a session cookie, which NSE hands out on any page load — hence the
    :meth:`_seed` call before the first request. Requests are rate-limited to the same 2/s
    courtesy limit every source in this codebase holds itself to.
    """

    def __init__(self, client: httpx.AsyncClient, cache_dir: Path) -> None:
        self._client = client
        self._dir = cache_dir
        self._limiter = RateLimiter(COURTESY_PER_S)
        self._seeded = False

    async def history(self, frm: date, to: date) -> ActionHistory:
        """Every capital change with an ex-date in ``[frm, to]``, classified."""
        splits: dict[str, list[Split]] = {}
        unpriceable: list[Unpriceable] = []
        unrecognised: list[Unpriceable] = []
        seen: set[tuple[str, date, str]] = set()

        for q_from, q_to in _quarters(frm, to):
            for row in await self._quarter(q_from, q_to):
                if (row.get("series") or "").strip().upper() != _EQUITY_SERIES:
                    continue
                symbol = (row.get("symbol") or "").strip().upper()
                ex_date = parse_ex_date(row.get("exDate") or "")
                subject = (row.get("subject") or "").strip()
                if not symbol or ex_date is None or not (frm <= ex_date <= to):
                    continue
                # Quarter ranges are inclusive at both ends and NSE occasionally repeats a row
                # across the seam; the same action applied twice would halve a price twice.
                key = (symbol, ex_date, subject)
                if key in seen:
                    continue
                seen.add(key)
                self._classify(symbol, ex_date, subject, splits, unpriceable, unrecognised)

        history = ActionHistory(
            frm=frm,
            to=to,
            splits={s: tuple(sorted(v, key=lambda x: x.ex_date)) for s, v in splits.items()},
            unpriceable=tuple(unpriceable),
            unrecognised=tuple(unrecognised),
        )
        if not history.splits:
            raise ActionsUnavailable(
                f"no priceable corporate actions found in {frm}..{to}. NSE lists hundreds of "
                f"splits and bonuses per year, so an empty result means the feed changed shape, "
                f"not that no company ever split. Refusing to back-adjust against nothing."
            )
        log.info(
            "nse corporate actions loaded",
            frm=str(frm),
            to=str(to),
            symbols_with_splits=len(history.splits),
            splits=sum(len(v) for v in history.splits.values()),
            unpriceable=len(history.unpriceable),
            unrecognised=len(history.unrecognised),
        )
        return history

    @staticmethod
    def _classify(
        symbol: str,
        ex_date: date,
        subject: str,
        splits: dict[str, list[Split]],
        unpriceable: list[Unpriceable],
        unrecognised: list[Unpriceable],
    ) -> None:
        try:
            ratio = parse_subject(subject)
        except SchemaError:
            unpriceable.append(Unpriceable(symbol=symbol, ex_date=ex_date, subject=subject))
            return
        if ratio is not None:
            splits.setdefault(symbol, []).append(Split(ex_date=ex_date, ratio=ratio))
        elif _BENIGN.search(subject) is None:
            # Not a dividend, not a meeting, and not a ratio we could read. It is probably
            # harmless, but "probably" is not a basis for pricing, so it is surfaced.
            unrecognised.append(Unpriceable(symbol=symbol, ex_date=ex_date, subject=subject))

    async def _quarter(self, frm: date, to: date) -> list[dict[str, Any]]:
        path = self._dir / f"actions_{frm:%Y%m%d}_{to:%Y%m%d}.json"
        cached = await asyncio.to_thread(read_versioned_json, path, _CACHE_SCHEMA)
        if cached is not None and isinstance(cached.get("rows"), list):
            rows: list[dict[str, Any]] = cached["rows"]
            return rows

        rows = await with_retry(
            lambda: self._download(frm, to), what=f"nse corporate actions {frm}..{to}"
        )
        if not rows:
            # NEVER cache an empty quarter. NSE lists hundreds of actions per quarter (165 in
            # 2011 Q1 alone), so zero rows means an error envelope or a changed schema, not a
            # quarter in which no company did anything. Cached, it would be served forever: every
            # split in that quarter would go unadjusted, surface as a fabricated 50-80% crash,
            # and be deleted by the panel's quarantine as if it were bad symbol history. The
            # aggregate emptiness check in `history` cannot see it — one bad quarter in 48 passes.
            raise ActionsUnavailable(
                f"nse returned no corporate actions at all for {frm}..{to}. That is not a quiet "
                f"quarter, it is a failed request — refusing to cache it."
            )
        await asyncio.to_thread(write_atomic_json, path, {"schema": _CACHE_SCHEMA, "rows": rows})
        return rows

    async def _download(self, frm: date, to: date) -> list[dict[str, Any]]:
        await self._seed()
        response = await get_or_raise(
            self._client,
            ACTIONS_URL,
            what=f"nse corporate actions {frm}..{to}",
            params={
                "index": "equities",
                "from_date": frm.strftime("%d-%m-%Y"),
                "to_date": to.strftime("%d-%m-%Y"),
            },
            limiter=self._limiter,
        )
        try:
            payload = response.json()
        except ValueError as exc:
            # NSE answers a rate-limited or cookie-less request with an HTML block page and a 200.
            # It must be TransientSourceError, not SchemaError: `with_retry` retries only the
            # former and documents that the latter "propagates immediately to the caller, which
            # halts the feed". Raising SchemaError here — as the first version did, directly
            # contradicting this comment — meant one block page during a 48-quarter fetch aborted
            # the whole panel build with zero retries.
            raise TransientSourceError(
                f"nse corporate actions {frm}..{to}: non-JSON body (probably a block page)"
            ) from exc
        rows = payload if isinstance(payload, list) else payload.get("data", [])
        if not isinstance(rows, list):
            raise SchemaError(
                f"nse corporate actions {frm}..{to}: expected a list, got {type(rows)}"
            )
        return [r for r in rows if isinstance(r, dict)]

    async def _seed(self) -> None:
        """Load the home page once so NSE issues the session cookie its API requires."""
        if self._seeded:
            return
        await self._limiter.acquire()
        try:
            await self._client.get(HOME_URL)
        except httpx.HTTPError as exc:
            # Deliberately NOT setting the flag. Marking the session seeded after a failure meant
            # every later request on this instance skipped seeding and went out cookie-less, so a
            # single failed home-page GET at the start guaranteed the whole fetch failed with no
            # path back. Leaving it false lets the next request try again.
            log.warning("could not seed nse session cookie; will retry", error=str(exc))
            return
        self._seeded = True


def _quarters(frm: date, to: date) -> Iterable[tuple[date, date]]:
    """``[frm, to]`` chopped into calendar quarters, clipped to the requested span."""
    year, month = frm.year, max(m for m in _QUARTER_MONTHS if m <= frm.month)
    while date(year, month, 1) <= to:
        end_month = month + 2
        end = date(year, end_month + 1, 1) if end_month < 12 else date(year + 1, 1, 1)
        yield max(frm, date(year, month, 1)), min(to, end - _ONE_DAY)
        year, month = (year + 1, 1) if month == 10 else (year, month + 3)


_ONE_DAY = date(2000, 1, 2) - date(2000, 1, 1)


__all__ = [
    "ActionHistory",
    "ActionsUnavailable",
    "NseCorporateActions",
    "Unpriceable",
    "parse_ex_date",
    "parse_subject",
]
