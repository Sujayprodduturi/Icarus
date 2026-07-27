"""Startup clock-sync assertion (task 0.16, PRD §36.6).

Why this exists: Delta's HMAC order signature is valid only 5s, and exactly-once
idempotency + the audit ledger all depend on a correct wall clock. A skewed clock is a
fail-fast-at-startup condition, never something to trade through.

Design: the skew check is pure and both clocks are injected, so tests are deterministic and
need no network. The default NTP query is a ~12-line stdlib UDP call (no extra dependency).
"""

from __future__ import annotations

import socket
import struct
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from icarus.common.schemas import utc_now

# NTP epoch (1900) to Unix epoch (1970) offset in seconds.
_NTP_UNIX_DELTA = 2_208_988_800
_DEFAULT_NTP_SERVER = "pool.ntp.org"


class ClockSkewError(RuntimeError):
    """Raised when local time differs from NTP truth by more than the allowed skew."""


@dataclass(frozen=True)
class ClockStatus:
    offset_s: float  # local - ntp; positive = local ahead
    max_skew_s: float
    synced: bool


def query_ntp(server: str = _DEFAULT_NTP_SERVER, timeout_s: float = 3.0) -> float:
    """Return the server's Unix time (seconds) via SNTP. Impure; not called in tests."""
    packet = b"\x1b" + 47 * b"\0"  # LI=0, VN=3, Mode=3 (client)
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.settimeout(timeout_s)
        sock.sendto(packet, (server, 123))
        data, _ = sock.recvfrom(48)
    # Transmit timestamp is the last 8 bytes' first 4 (seconds since NTP epoch).
    seconds = struct.unpack("!I", data[40:44])[0]
    return float(seconds - _NTP_UNIX_DELTA)


def check_clock_sync(
    max_skew_s: float,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    ntp_time_fn: Callable[[], float] = query_ntp,
) -> ClockStatus:
    """Compare local time to NTP truth. Pure given the two injected clock functions."""
    offset = now_fn().timestamp() - ntp_time_fn()
    return ClockStatus(offset_s=offset, max_skew_s=max_skew_s, synced=abs(offset) <= max_skew_s)


def assert_clock_synced(
    max_skew_s: float = 1.0,
    *,
    now_fn: Callable[[], datetime] = utc_now,
    ntp_time_fn: Callable[[], float] = query_ntp,
) -> ClockStatus:
    """Fail-fast wrapper: raise :class:`ClockSkewError` if the clock is out of sync."""
    status = check_clock_sync(max_skew_s, now_fn=now_fn, ntp_time_fn=ntp_time_fn)
    if not status.synced:
        raise ClockSkewError(
            f"clock skew {status.offset_s:+.3f}s exceeds {max_skew_s}s (NTP); "
            "halt startup until synced (§36.6)"
        )
    return status
