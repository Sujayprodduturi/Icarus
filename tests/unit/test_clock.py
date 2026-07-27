"""Clock-sync assertion tests (task 0.16). Both clocks injected -> no network, deterministic."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from icarus.common.clock import ClockSkewError, assert_clock_synced, check_clock_sync

# A fixed reference instant.
_REF = datetime(2026, 7, 27, 12, 0, 0, tzinfo=UTC)
_REF_UNIX = _REF.timestamp()


def test_in_sync_passes() -> None:
    status = assert_clock_synced(1.0, now_fn=lambda: _REF, ntp_time_fn=lambda: _REF_UNIX + 0.2)
    assert status.synced
    assert abs(status.offset_s) < 1.0


def test_skew_beyond_limit_raises() -> None:
    with pytest.raises(ClockSkewError, match="skew"):
        assert_clock_synced(1.0, now_fn=lambda: _REF, ntp_time_fn=lambda: _REF_UNIX + 5.0)


def test_negative_skew_also_raises() -> None:
    # Local behind NTP by 5s is just as bad.
    with pytest.raises(ClockSkewError):
        assert_clock_synced(1.0, now_fn=lambda: _REF, ntp_time_fn=lambda: _REF_UNIX - 5.0)


def test_check_reports_offset_without_raising() -> None:
    # NTP 3s ahead of local -> offset (local - ntp) is -3.0.
    status = check_clock_sync(1.0, now_fn=lambda: _REF, ntp_time_fn=lambda: _REF_UNIX + 3.0)
    assert not status.synced
    assert status.offset_s == pytest.approx(-3.0, abs=1e-6)
