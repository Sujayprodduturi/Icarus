from __future__ import annotations

from datetime import UTC
from decimal import Decimal

import numpy as np
from tests.unit.test_portfolio_characterization import _panel

from icarus.engine.simcore import _last_traded_close, _sim_bar, _ts_at


def test_shared_timestamp_helper_returns_utc_datetime() -> None:
    ts = _ts_at(_panel(), 1)

    assert ts.tzinfo is UTC
    assert ts.isoformat() == "2024-01-02T00:00:00+00:00"


def test_shared_bar_helper_refuses_missing_symbol_session() -> None:
    panel = _panel()
    panel.bars[0].open[1] = np.nan

    assert _sim_bar(panel, 0, 1, _ts_at(panel, 1)) is None


def test_shared_bar_helper_converts_finite_bar_to_decimal() -> None:
    panel = _panel()

    bar = _sim_bar(panel, 0, 1, _ts_at(panel, 1))

    assert bar is not None
    assert bar.open == Decimal("100.0")
    assert bar.volume == Decimal("1000000.0")


def test_shared_last_close_returns_price_and_local_index() -> None:
    panel = _panel()
    panel.bars[0].close[2:] = np.nan

    assert _last_traded_close(panel, 0, 5) == (Decimal("100.0"), 1)
