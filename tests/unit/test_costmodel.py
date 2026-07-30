"""Tests for the cost model (task 1.5, PRD §7).

The centrepiece is a **hand-computed contract note** checked line by line. Every other test here
guards one specific way a cost model goes quietly wrong — GST landing on a tax it must not touch,
a brokerage cap that never binds, a rate that silently reverts to its pre-April-2026 value. A cost
model that is wrong in our favour makes losing strategies look profitable, which is the single
most expensive class of bug in this repo (CLAUDE.md §5).
"""

from __future__ import annotations

from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from icarus.common.config import ConfigError, Costs, SegmentSchedules, load_goal
from icarus.common.types import AssetClass, OrderSide
from icarus.engine.costmodel import CostModel, Segment, clears_hurdle, segment_for


@pytest.fixture
def costs(repo_root: Path) -> Costs:
    return load_goal(repo_root / "goal.yaml").costs


@pytest.fixture
def model(costs: Costs) -> CostModel:
    return CostModel(costs)


# --------------------------------------------------------------------------------------
# The hand-computed contract note — buy 10 @ Rs 1,000, sell 10 @ Rs 1,100, delivery
# --------------------------------------------------------------------------------------
def test_delivery_buy_matches_hand_computed_contract_note(model: CostModel) -> None:
    """Turnover Rs 10,000. Every line worked out by hand from the goal.yaml schedule."""
    c = model.charges(Segment.EQUITY_DELIVERY, OrderSide.BUY, Decimal(1000), Decimal(10))

    assert c.brokerage == Decimal(0)  # Rs 0 delivery brokerage
    assert c.stt == Decimal("10.0")  # 0.1% x 10,000
    assert c.exchange_txn == Decimal("0.307")  # 0.00307% x 10,000
    assert c.sebi_fee == Decimal("0.01")  # Rs 10/crore x 10,000
    assert c.gst == Decimal("0.05706")  # 18% x (0 + 0.307 + 0.01)
    assert c.stamp_duty == Decimal("1.5")  # 0.015% x 10,000, buy side
    assert c.dp_charge == Decimal(0)  # nothing leaves the demat on a buy
    assert c.total == Decimal("11.87406")


def test_delivery_sell_matches_hand_computed_contract_note(model: CostModel) -> None:
    """Turnover Rs 11,000. Note the DP charge alone is larger than every other line combined."""
    c = model.charges(Segment.EQUITY_DELIVERY, OrderSide.SELL, Decimal(1100), Decimal(10))

    assert c.brokerage == Decimal(0)
    assert c.stt == Decimal("11.0")  # 0.1% sell side too, unlike intraday
    assert c.exchange_txn == Decimal("0.3377")
    assert c.sebi_fee == Decimal("0.011")
    assert c.gst == Decimal("0.062766")  # 18% x (0.3377 + 0.011)
    assert c.stamp_duty == Decimal(0)  # buy side only
    assert c.dp_charge == Decimal("15.34")
    assert c.total == Decimal("26.751466")

    assert c.dp_charge > c.total - c.dp_charge  # one flat fee outweighs every other line combined


def test_round_trip_sums_both_sides(model: CostModel) -> None:
    rt = model.round_trip(Segment.EQUITY_DELIVERY, Decimal(1000), Decimal(1100), Decimal(10))
    assert rt.total == Decimal("38.625526")
    # Cost as a share of the money actually put at work: ~0.386% on a Rs 10,000 position.
    assert rt.as_fraction_of_entry == Decimal("38.625526") / Decimal(10000)


# --------------------------------------------------------------------------------------
# The rules that are easy to get subtly wrong
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize("segment", list(Segment))
@pytest.mark.parametrize("side", list(OrderSide))
def test_gst_never_touches_stt_stamp_or_dp(
    model: CostModel, costs: Costs, segment: Segment, side: OrderSide
) -> None:
    """GST is levied on services only. Applying it to STT/stamp (taxes) or DP (already
    GST-inclusive at Rs 15.34) would overstate cost and, worse, double-tax the DP line."""
    c = model.charges(segment, side, Decimal(500), Decimal(20))
    expected = Decimal(str(costs.gst_rate)) * (c.brokerage + c.exchange_txn + c.sebi_fee)
    assert c.gst == expected


@pytest.mark.parametrize("segment", list(Segment))
def test_stamp_duty_is_buy_side_only(model: CostModel, segment: Segment) -> None:
    buy = model.charges(segment, OrderSide.BUY, Decimal(500), Decimal(20))
    sell = model.charges(segment, OrderSide.SELL, Decimal(500), Decimal(20))
    assert buy.stamp_duty > 0
    assert sell.stamp_duty == Decimal(0)


def test_dp_charge_only_on_delivery_sell(model: CostModel) -> None:
    """Rs 15.34 is charged per scrip when shares leave the demat account — delivery sells only."""
    assert model.charges(
        Segment.EQUITY_DELIVERY, OrderSide.SELL, Decimal(500), Decimal(20)
    ).dp_charge == Decimal("15.34")
    for segment in (Segment.EQUITY_INTRADAY, Segment.EQUITY_FUTURES, Segment.EQUITY_OPTIONS):
        for side in OrderSide:
            assert model.charges(segment, side, Decimal(500), Decimal(20)).dp_charge == Decimal(0)


def test_dp_charge_is_flat_regardless_of_size(model: CostModel) -> None:
    """The heart of the seed-capital problem: this line does not scale with position size."""
    small = model.charges(Segment.EQUITY_DELIVERY, OrderSide.SELL, Decimal(100), Decimal(20))
    large = model.charges(Segment.EQUITY_DELIVERY, OrderSide.SELL, Decimal(10000), Decimal(200))
    assert small.dp_charge == large.dp_charge == Decimal("15.34")


def test_intraday_brokerage_takes_the_lower_of_percent_and_cap(model: CostModel) -> None:
    """0.03% or Rs 20/order, whichever is LOWER. A cap that never binds is a common bug."""
    # Small: 0.03% of Rs 10,000 = Rs 3, under the cap.
    small = model.charges(Segment.EQUITY_INTRADAY, OrderSide.BUY, Decimal(1000), Decimal(10))
    assert small.brokerage == Decimal("3.0")
    # Large: 0.03% of Rs 10,00,000 = Rs 300, so the Rs 20 cap binds.
    large = model.charges(Segment.EQUITY_INTRADAY, OrderSide.BUY, Decimal(1000), Decimal(1000))
    assert large.brokerage == Decimal("20.0")


def test_options_brokerage_is_flat_whatever_the_turnover(model: CostModel) -> None:
    cheap = model.charges(Segment.EQUITY_OPTIONS, OrderSide.BUY, Decimal(5), Decimal(75))
    rich = model.charges(Segment.EQUITY_OPTIONS, OrderSide.BUY, Decimal(500), Decimal(750))
    assert cheap.brokerage == rich.brokerage == Decimal("20.0")


def test_delivery_brokerage_is_zero_both_sides(model: CostModel) -> None:
    """Zero brokerage is what makes delivery the only viable seed-tier equity path (§7.1)."""
    for side in OrderSide:
        c = model.charges(Segment.EQUITY_DELIVERY, side, Decimal(1000), Decimal(10))
        assert c.brokerage == Decimal(0)


def test_intraday_stt_is_sell_side_only(model: CostModel) -> None:
    buy = model.charges(Segment.EQUITY_INTRADAY, OrderSide.BUY, Decimal(1000), Decimal(10))
    sell = model.charges(Segment.EQUITY_INTRADAY, OrderSide.SELL, Decimal(1000), Decimal(10))
    assert buy.stt == Decimal(0)
    assert sell.stt == Decimal("2.5")  # 0.025% x 10,000


def test_post_april_2026_stt_rates_have_not_reverted(model: CostModel) -> None:
    """Regression guard on the two rates the PRD flags as RAISED on 1 Apr 2026. An old blog post
    or a stale broker page would quietly restore the pre-hike numbers and flatter every F&O sim."""
    futures = model.charges(Segment.EQUITY_FUTURES, OrderSide.SELL, Decimal(1000), Decimal(100))
    assert futures.stt == Decimal("50.0")  # 0.05% x 1,00,000 — was 0.02% before Apr 2026

    options = model.charges(Segment.EQUITY_OPTIONS, OrderSide.SELL, Decimal(100), Decimal(100))
    assert options.stt == Decimal("15.0")  # 0.15% x premium 10,000 — was 0.10% before Apr 2026


def test_exchange_txn_uses_the_all_in_ipft_inclusive_rate(model: CostModel) -> None:
    """0.00307% all-in. Reverting to the raw 0.00297% would understate cost unless IPFT is added
    back separately — the double-count trap PRD Appendix B calls out."""
    c = model.charges(Segment.EQUITY_DELIVERY, OrderSide.BUY, Decimal(100000), Decimal(1))
    assert c.exchange_txn == Decimal("3.07")


def test_options_charges_are_levied_on_premium_not_notional(model: CostModel) -> None:
    """Passing the premium as price is the documented contract; turnover must follow it."""
    c = model.charges(Segment.EQUITY_OPTIONS, OrderSide.SELL, Decimal(50), Decimal(100))
    assert c.turnover == Decimal(5000)
    assert c.stt == Decimal("7.5")  # 0.15% x 5,000


# --------------------------------------------------------------------------------------
# Breakeven — the seed-capital reality check
# --------------------------------------------------------------------------------------
def test_breakeven_move_is_a_true_fixed_point(model: CostModel) -> None:
    """Selling at exactly the breakeven price must net zero, to the paisa."""
    price, qty = Decimal(500), Decimal(20)
    move = model.breakeven_move(Segment.EQUITY_DELIVERY, price, qty)
    exit_price = price * (1 + move)
    gross = (exit_price - price) * qty
    cost = model.round_trip(Segment.EQUITY_DELIVERY, price, exit_price, qty).total
    assert abs(gross - cost) < Decimal("0.0001")


def test_breakeven_punishes_small_positions(model: CostModel) -> None:
    """The C1 cold-start problem, quantified: identical strategy, identical percentage costs,
    but the flat Rs 15.34 DP charge makes a small delivery position far harder to clear."""
    tiny = model.breakeven_move(Segment.EQUITY_DELIVERY, Decimal(100), Decimal(20))  # Rs 2,000
    large = model.breakeven_move(Segment.EQUITY_DELIVERY, Decimal(100), Decimal(500))  # Rs 50,000

    assert tiny > Decimal("0.009")  # needs a ~1% move just to break even
    assert large < Decimal("0.0026")  # under a third of a percent
    assert tiny > large * 3


def test_intraday_breakeven_has_no_dp_cliff(model: CostModel) -> None:
    """Intraday carries no DP charge, so its breakeven barely moves with size — a useful contrast
    that confirms the delivery cliff really is the DP line and not something else."""
    tiny = model.breakeven_move(Segment.EQUITY_INTRADAY, Decimal(100), Decimal(20))
    large = model.breakeven_move(Segment.EQUITY_INTRADAY, Decimal(100), Decimal(500))
    assert abs(tiny - large) < Decimal("0.0005")


# --------------------------------------------------------------------------------------
# Cost stress (§13) + the hurdle rule (§7.3)
# --------------------------------------------------------------------------------------
def test_stress_multiplier_scales_every_line(costs: Costs) -> None:
    base = CostModel(costs)
    stressed = CostModel(costs, stress_multiplier=Decimal("1.5"))
    args = (Segment.EQUITY_DELIVERY, OrderSide.SELL, Decimal(1000), Decimal(10))
    assert stressed.charges(*args).total == base.charges(*args).total * Decimal("1.5")
    assert stressed.charges(*args).dp_charge == Decimal("15.34") * Decimal("1.5")


def test_stress_multiplier_leaves_turnover_alone(costs: Costs) -> None:
    """Turnover is a fact about the trade, not a cost — stressing it would corrupt every ratio."""
    stressed = CostModel(costs, stress_multiplier=2)
    assert stressed.charges(
        Segment.EQUITY_DELIVERY, OrderSide.BUY, Decimal(1000), Decimal(10)
    ).turnover == Decimal(10000)


def test_hurdle_requires_edge_to_clear_cost_with_margin() -> None:
    cost = Decimal(100)
    assert clears_hurdle(Decimal(150), cost, 1.5) is True  # exactly at the boundary
    assert clears_hurdle(Decimal("149.99"), cost, 1.5) is False
    assert clears_hurdle(Decimal(120), cost, 1.5) is False  # profitable but not enough


def test_the_kite_subscription_is_not_a_trading_cost(model: CostModel, costs: Costs) -> None:
    """Operator decision 2026-07-30: the Rs 500/mo API fee is a capital investment in the business,
    not a cost of a trade. PRD §7.1 suggests amortizing it into the hurdle, so this test exists to
    stop someone re-adding it from the PRD without re-opening the decision.

    Strategy metrics are therefore *before* infrastructure cost — the Rs 500 is reported as its own
    line (BUILD_MAP §5), never netted into strategy P&L.
    """
    assert "subscription_monthly_inr" not in type(costs).model_fields
    charged = model.charges(Segment.EQUITY_DELIVERY, OrderSide.BUY, Decimal(1000), Decimal(10))
    assert charged.total < Decimal(20)  # nowhere near a Rs 500/mo fee in any amortised form


# --------------------------------------------------------------------------------------
# Failure paths — these matter most (CLAUDE.md §6)
# --------------------------------------------------------------------------------------
@pytest.mark.parametrize(("price", "quantity"), [(0, 10), (-1, 10), (1000, 0), (1000, -5)])
def test_non_positive_inputs_raise(model: CostModel, price: int, quantity: int) -> None:
    with pytest.raises(ValueError, match="must be positive"):
        model.charges(Segment.EQUITY_DELIVERY, OrderSide.BUY, Decimal(price), Decimal(quantity))


@pytest.mark.parametrize("bad", [0, -1, Decimal("-0.5")])
def test_non_positive_stress_multiplier_raises(costs: Costs, bad: object) -> None:
    with pytest.raises(ValueError, match="stress_multiplier must be positive"):
        CostModel(costs, stress_multiplier=bad)  # type: ignore[arg-type]


def test_crypto_raises_rather_than_guessing_a_fee(model: CostModel) -> None:
    """Delta's schedule is unverified and crypto is deferred (D1). An invented-but-plausible fee
    would produce a crypto backtest that looks trustworthy and is not."""
    with pytest.raises(NotImplementedError, match=r"1\.5b"):
        segment_for(AssetClass.CRYPTO, intraday=False)


def test_equity_maps_to_delivery_or_intraday(model: CostModel) -> None:
    assert segment_for(AssetClass.EQUITY, intraday=False) is Segment.EQUITY_DELIVERY
    assert segment_for(AssetClass.EQUITY, intraday=True) is Segment.EQUITY_INTRADAY


# --------------------------------------------------------------------------------------
# Config guards
# --------------------------------------------------------------------------------------
def _load_with_costs(tmp_path: Path, repo_root: Path, mutate: Any) -> None:
    raw: dict[str, Any] = yaml.safe_load((repo_root / "goal.yaml").read_text(encoding="utf-8"))
    mutate(raw["costs"])
    p = tmp_path / "goal.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    load_goal(p)


def test_segment_names_stay_in_step_with_the_enum() -> None:
    """The config field names and the Segment enum are two lists of the same four things. If they
    drift, a schedule silently becomes unreachable — this is what lets the config drop its own
    hand-written presence check and rely on pydantic instead."""
    assert set(SegmentSchedules.model_fields) == {s.value for s in Segment}


def test_percentage_brokerage_without_a_cap_is_rejected(tmp_path: Path, repo_root: Path) -> None:
    """min(pct x turnover, 0) is always 0 — free trading, silently. Must fail at startup."""

    def mutate(costs: dict[str, Any]) -> None:
        costs["segments"]["equity_intraday"]["brokerage_cap_inr"] = 0.0

    with pytest.raises(ConfigError, match="brokerage_cap_inr"):
        _load_with_costs(tmp_path, repo_root, mutate)


def test_missing_segment_schedule_is_rejected(tmp_path: Path, repo_root: Path) -> None:
    def mutate(costs: dict[str, Any]) -> None:
        del costs["segments"]["equity_futures"]

    with pytest.raises(ConfigError, match="equity_futures"):
        _load_with_costs(tmp_path, repo_root, mutate)


def test_unknown_segment_schedule_is_rejected(tmp_path: Path, repo_root: Path) -> None:
    """A typo'd segment name would otherwise sit in config doing nothing, while the real segment
    silently falls back to whatever else is present."""

    def mutate(costs: dict[str, Any]) -> None:
        costs["segments"]["equity_delivry"] = costs["segments"]["equity_delivery"]

    with pytest.raises(ConfigError, match="equity_delivry"):
        _load_with_costs(tmp_path, repo_root, mutate)


def test_rates_survive_the_yaml_float_round_trip(model: CostModel, costs: Costs) -> None:
    """YAML gives us floats, and 0.00015 as a float is really 0.000149999...; converting via
    ``str`` recovers the intended decimal. Without it every charge carries a tail of binary noise
    and no figure can ever be reconciled exactly against a contract note."""
    stamp_pct = costs.segments.equity_delivery.stamp_buy_pct
    assert Decimal(stamp_pct) != Decimal("0.00015")  # the float really is lossy
    assert Decimal(str(stamp_pct)) == Decimal("0.00015")  # str() recovers it

    c = model.charges(Segment.EQUITY_DELIVERY, OrderSide.BUY, Decimal(1000), Decimal(10))
    assert c.stamp_duty == Decimal("1.5")
    # Exact to 5 dp with nothing beyond it — a float-derived rate would leave a long binary tail.
    assert c.stamp_duty == c.stamp_duty.quantize(Decimal("0.00001"))
