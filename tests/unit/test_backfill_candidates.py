from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, cast

import pytest

from icarus.agents.data import backfill
from icarus.agents.data.source import SourceUnavailableError, TransientSourceError

if TYPE_CHECKING:
    from icarus.agents.data.nse import NseBhavcopySource


class _FakeBhavcopySource:
    def __init__(
        self,
        *,
        published: set[date] | None = None,
        transient: set[date] | None = None,
    ) -> None:
        self.published = published or set()
        self.transient = transient or set()
        self.requested: list[date] = []

    async def day_rows(self, day: date) -> object:
        self.requested.append(day)
        if day in self.transient:
            raise TransientSourceError(f"transient failure for {day}")
        if day not in self.published:
            raise SourceUnavailableError(f"no archive for {day}")
        return object()


def _as_source(fake: _FakeBhavcopySource) -> NseBhavcopySource:
    return cast("NseBhavcopySource", fake)


@pytest.mark.parametrize("weekend", [date(2022, 10, 22), date(2022, 10, 23)])
async def test_scan_retains_a_published_weekend_session(weekend: date) -> None:
    source = _FakeBhavcopySource(published={weekend})

    result = await backfill.scan(_as_source(source), weekend, weekend)

    assert result.sessions == (weekend,)
    assert result.closures == ()
    assert source.requested == [weekend]


async def test_scan_keeps_an_absent_weekend_as_a_derived_closure() -> None:
    weekend = date(2022, 10, 23)
    source = _FakeBhavcopySource()

    result = await backfill.scan(_as_source(source), weekend, weekend)

    assert result.sessions == ()
    assert result.closures == (weekend,)


async def test_scan_preserves_weekday_session_behavior() -> None:
    weekday = date(2022, 10, 24)
    source = _FakeBhavcopySource(published={weekday})

    result = await backfill.scan(_as_source(source), weekday, weekday)

    assert result.sessions == (weekday,)
    assert result.closures == ()


def test_days_between_is_inclusive_and_reversed_ranges_are_empty() -> None:
    assert backfill.days_between(date(2022, 10, 22), date(2022, 10, 24)) == [
        date(2022, 10, 22),
        date(2022, 10, 23),
        date(2022, 10, 24),
    ]
    assert backfill.days_between(date(2022, 10, 24), date(2022, 10, 22)) == []


async def test_scan_propagates_transient_errors_from_weekend_candidates() -> None:
    weekend = date(2022, 10, 23)
    source = _FakeBhavcopySource(transient={weekend})

    with pytest.raises(TransientSourceError, match="2022-10-23"):
        await backfill.scan(_as_source(source), weekend, weekend)
