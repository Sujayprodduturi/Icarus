"""Synthetic characterization of the portfolio simulator before Task-3a extraction.

This is deliberately not the golden backtest: it uses no repository panel, lockbox, or trial
ledger.  Its one job is to make the Step-1 extraction prove that the current money-path behaviour
did not move.  The fixture reaches a stopped trade, a partial entry, an end-of-data exit, a refused
entry, a repeated signal while already held, and itemised costs in six synthetic sessions.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC
from decimal import Decimal
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
from tests.unit.simharness import REALISM

from icarus.common.config import Costs, Risk
from icarus.engine.costmodel import CostModel
from icarus.engine.fills import FillModel
from icarus.engine.portfolio import PortfolioSimulator
from icarus.strategy.dsl import Bars, Panel, parse_strategy
from icarus.strategy.library import default_registry

if TYPE_CHECKING:
    from icarus.engine.costmodel import Charges
    from icarus.engine.portfolio import ClosedTrade, RunResult


_START = np.datetime64("2024-01-01")
_SNAPSHOT = Path(__file__).resolve().parents[1] / "golden" / "portfolio_characterization.json"
_PRE_EXTRACTION_SHA256 = "98e9aa17227371b9762c56b93ff04ce93de3f8f4ccba0f10b8109b5ef5d00164"

_RISK = Risk(
    per_trade_risk_r=0.005,
    new_strategy_size_factor=0.25,
    kelly_fraction_cap=0.5,
    daily_loss_limit=0.03,
    daily_derisk_trigger=0.015,
    max_drawdown_killswitch=0.10,
    max_open_positions=4,
    max_portfolio_heat=0.02,
    max_position_pct_of_equity=0.25,
    max_pairwise_correlation=0.7,
    consecutive_loss_pause=3,
    canary_min_trades=10,
    canary_min_days=7,
    cost_hurdle_multiplier=1.5,
    crypto_max_leverage_hard=2.0,
    crypto_max_leverage_seed=1.0,
    stagnation_check_after_trades=50,
    stagnation_requires_positive_net=True,
    stagnation_ci_level=0.95,
)
_COSTS = Costs.model_validate(
    {
        "gst_rate": 0.18,
        "sebi_turnover_pct": 0.000001,
        "dp_charge_inr": 15.34,
        "segments": {
            "equity_delivery": {
                "brokerage_flat_inr": 0.0,
                "brokerage_pct": 0.0,
                "brokerage_cap_inr": 0.0,
                "stt_buy_pct": 0.001,
                "stt_sell_pct": 0.001,
                "exchange_txn_pct": 0.0000307,
                "stamp_buy_pct": 0.00015,
                "dp_charge_on_sell": True,
            },
            "equity_intraday": {
                "brokerage_flat_inr": 0.0,
                "brokerage_pct": 0.0003,
                "brokerage_cap_inr": 20.0,
                "stt_buy_pct": 0.0,
                "stt_sell_pct": 0.00025,
                "exchange_txn_pct": 0.0000307,
                "stamp_buy_pct": 0.00003,
                "dp_charge_on_sell": False,
            },
            "equity_futures": {
                "brokerage_flat_inr": 0.0,
                "brokerage_pct": 0.0003,
                "brokerage_cap_inr": 20.0,
                "stt_buy_pct": 0.0,
                "stt_sell_pct": 0.0005,
                "exchange_txn_pct": 0.0000183,
                "stamp_buy_pct": 0.00002,
                "dp_charge_on_sell": False,
            },
            "equity_options": {
                "brokerage_flat_inr": 20.0,
                "brokerage_pct": 0.0,
                "brokerage_cap_inr": 0.0,
                "stt_buy_pct": 0.0,
                "stt_sell_pct": 0.0015,
                "exchange_txn_pct": 0.0003553,
                "stamp_buy_pct": 0.00003,
                "dp_charge_on_sell": False,
            },
        },
    }
)

_STRATEGY = """
name: portfolio_characterization
version: 1
timeframe: 1d
universe: synthetic
entry: {structure_bullish: {k: 2}}
exit:
  - stop_loss_atr: {atr_mult: 2.0, atr_period: 14}
sizing:
  risk_r: 0.005
"""


def _bars(prices: list[float], *, volumes: list[float] | None = None) -> Bars:
    close = np.array(prices, dtype=np.float64)
    volume = (
        np.full(close.size, 1_000_000.0) if volumes is None else np.array(volumes, dtype=np.float64)
    )
    return Bars(
        ts=np.arange(_START, _START + close.size).astype("datetime64[ns]"),
        open=close.copy(),
        high=close + 1.0,
        low=close - 1.0,
        close=close,
        volume=volume,
    )


def _panel() -> Panel:
    bars = {
        # Full-size entry followed by a gap through the protective stop.
        "AAA": _bars([100.0, 100.0, 100.0, 85.0, 85.0, 85.0]),
        # Entry-bar volume caps the requested 50 shares to a partial fill of 20.
        "BBB": _bars(
            [100.0] * 6,
            volumes=[1_000_000.0, 400.0, 1_000_000.0, 1_000_000.0, 1_000_000.0, 1_000_000.0],
        ),
        # Zero entry-bar volume makes the market refuse the entry.
        "CCC": _bars(
            [100.0] * 6,
            volumes=[1_000_000.0, 0.0, 1_000_000.0, 1_000_000.0, 1_000_000.0, 1_000_000.0],
        ),
    }
    tradable = {symbol: np.ones(6, dtype=np.bool_) for symbol in bars}
    return Panel.build(bars, tradable)


def _column(*fire_at: int) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
    out = np.zeros(6, dtype=np.float64)
    out[list(fire_at)] = 1.0
    return out


def _run() -> RunResult:
    strategy = parse_strategy(
        _STRATEGY,
        registry=default_registry(),
        max_risk_r=_RISK.per_trade_risk_r,
    )
    simulator = PortfolioSimulator(
        risk=_RISK,
        costs=CostModel(_COSTS),
        fills=FillModel(REALISM),
        stale_after_sessions=20,
    )
    return simulator.run(
        strategy,
        _panel(),
        signals={"AAA": _column(0, 1), "BBB": _column(0), "CCC": _column(0)},
        stops={symbol: np.full(6, 10.0) for symbol in ("AAA", "BBB", "CCC")},
        starting_equity=Decimal(100_000),
    )


def _charges(charges: Charges) -> dict[str, str]:
    return {
        "brokerage": str(charges.brokerage),
        "stt": str(charges.stt),
        "exchange_txn": str(charges.exchange_txn),
        "sebi_fee": str(charges.sebi_fee),
        "gst": str(charges.gst),
        "stamp_duty": str(charges.stamp_duty),
        "dp_charge": str(charges.dp_charge),
        "turnover": str(charges.turnover),
        "total": str(charges.total),
    }


def _trade(trade: ClosedTrade) -> dict[str, object]:
    return {
        "symbol": trade.symbol,
        "quantity": trade.quantity,
        "entry_ts": trade.entry_ts.astimezone(UTC).isoformat(),
        "entry_price": str(trade.entry_price),
        "exit_ts": trade.exit_ts.astimezone(UTC).isoformat(),
        "exit_price": str(trade.exit_price),
        "reason": trade.reason.value,
        "entry_charges": _charges(trade.entry_charges),
        "exit_charges": _charges(trade.exit_charges),
        "risk_per_share": str(trade.risk_per_share),
        "gross_pnl": str(trade.gross_pnl),
        "costs": str(trade.costs),
        "net_pnl": str(trade.net_pnl),
        "holding_days": trade.holding_days,
    }


def _observation() -> dict[str, object]:
    result = _run()
    return {
        "trades": [_trade(trade) for trade in result.trades],
        "equity": [[at.astimezone(UTC).isoformat(), str(value)] for at, value in result.equity],
        "skipped": {
            reason.value: count
            for reason, count in sorted(result.skipped.items(), key=lambda item: item[0].value)
        },
        "unfilled_exits": result.unfilled_exits,
        "ambiguous_selection_days": result.ambiguous_selection_days,
        "stale_marks": result.stale_marks,
        "stale_mark_value": str(result.stale_mark_value),
        "concentration_capped": result.concentration_capped,
        "final_equity": str(result.final_equity),
    }


def _canonical(payload: dict[str, object]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def _digest(payload: dict[str, object]) -> str:
    return hashlib.sha256(_canonical(payload).encode("ascii")).hexdigest()


def test_portfolio_simulator_matches_the_pre_extraction_snapshot() -> None:
    """Changing entry, exit, partial-fill, refusal or cost behaviour must change this snapshot."""
    actual = _observation()
    assert _SNAPSHOT.exists(), (
        f"missing characterization snapshot {_SNAPSHOT}; captured payload:\n"
        f"{json.dumps(actual, indent=2, sort_keys=True)}"
    )
    snapshot = json.loads(_SNAPSHOT.read_text(encoding="utf-8"))
    expected = snapshot["observation"]
    expected_hash = snapshot["sha256"]

    assert expected_hash == _PRE_EXTRACTION_SHA256
    assert actual == expected
    assert _digest(actual) == expected_hash
    assert _digest(expected) == expected_hash
