"""Tests for the tax model (task 1.6, PRD §6).

Three things here matter more than the rest:

* **The financial-year boundary is resolved in IST, not UTC.** A trade closing just after midnight
  IST on 1 April is still 31 March in UTC — filing it in the wrong year moves tax between years and
  silently changes which losses were available to offset it (invariant #22).
* **The VDA stress must actually bite.** Tax lands on winning trades alone, so the effective rate on
  net profit can be multiples of the 30% headline. If a test ever shows VDA behaving like a normal
  30% bucket, the no-set-off rule has been quietly lost — that is the AC for this task.
* **Carry-forward relief and its expiry.** Getting this wrong understates tax (too much relief) or
  overstates it (relief expiring early), and both distort every after-tax metric downstream.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
import yaml

from icarus.common.calendar import IST
from icarus.common.config import ConfigError, load_goal
from icarus.common.config import Tax as TaxConfig
from icarus.engine.costmodel import Segment
from icarus.engine.taxmodel import (
    Bucket,
    RealizedTrade,
    Scenario,
    TaxModel,
    effective_tax_rate,
    financial_year,
)


@pytest.fixture
def tax_cfg(repo_root: Path) -> TaxConfig:
    return load_goal(repo_root / "goal.yaml").tax


@pytest.fixture
def model(tax_cfg: TaxConfig) -> TaxModel:
    return TaxModel(tax_cfg)


def _trade(
    bucket: Bucket, pnl: str, *, year: int = 2026, month: int = 6, day: int = 1
) -> RealizedTrade:
    return RealizedTrade(
        bucket=bucket, pnl=Decimal(pnl), exit_ts=datetime(year, month, day, tzinfo=UTC)
    )


# --------------------------------------------------------------------------------------
# The financial-year boundary — IST, never UTC
# --------------------------------------------------------------------------------------
def test_financial_year_runs_april_to_march() -> None:
    assert financial_year(datetime(2026, 4, 1, tzinfo=UTC)) == 2026  # first day of FY 2026-27
    assert financial_year(datetime(2026, 12, 31, tzinfo=UTC)) == 2026
    assert financial_year(datetime(2027, 3, 31, tzinfo=UTC)) == 2026  # last day of the same FY
    assert financial_year(datetime(2027, 4, 1, tzinfo=UTC)) == 2027  # next FY


def test_financial_year_is_resolved_in_ist_not_utc() -> None:
    """00:30 IST on 1 Apr 2027 is 19:00 UTC on 31 Mar 2027. Reading the UTC date files the trade in
    FY 2026-27 — the wrong year, with a different set of losses available to offset it."""
    just_after_midnight_ist = datetime(2027, 4, 1, 0, 30, tzinfo=IST)
    assert just_after_midnight_ist.astimezone(UTC).date().isoformat() == "2027-03-31"
    assert financial_year(just_after_midnight_ist) == 2027  # April in IST, so FY 2027-28


def test_naive_timestamps_are_refused() -> None:
    with pytest.raises(ValueError, match="tz-aware"):
        financial_year(datetime(2026, 6, 1))
    with pytest.raises(ValueError, match="tz-aware"):
        RealizedTrade(bucket=Bucket.NONSPECULATIVE, pnl=Decimal(1), exit_ts=datetime(2026, 6, 1))


def test_fy_label_uses_the_indian_convention(model: TaxModel) -> None:
    [fy] = model.annual_tax([_trade(Bucket.NONSPECULATIVE, "1000")])
    assert fy.label == "2026-27"


# --------------------------------------------------------------------------------------
# Rates, cess, and the marginal-rate choice
# --------------------------------------------------------------------------------------
def test_business_income_taxed_at_marginal_slab_plus_cess(model: TaxModel) -> None:
    """Rs 10,000 non-speculative profit at a 30% marginal slab + 4% cess = Rs 3,120."""
    [fy] = model.annual_tax([_trade(Bucket.NONSPECULATIVE, "10000")])
    assert fy.tax_before_cess == Decimal("3000.00")
    assert fy.cess == Decimal("120.0000")
    assert fy.total_tax == Decimal("3120.0000")
    assert fy.net_pnl == Decimal("6880.0000")


def test_intraday_is_speculative_but_same_slab_rate(model: TaxModel) -> None:
    """Speculative differs from non-speculative in its *relief rules*, not its rate — both are slab.
    A test asserting a different rate would mean the buckets had been confused."""
    [spec] = model.annual_tax([_trade(Bucket.EQUITY_SPECULATIVE, "10000")])
    [nonspec] = model.annual_tax([_trade(Bucket.NONSPECULATIVE, "10000")])
    assert spec.total_tax == nonspec.total_tax


def test_stcg_is_twenty_percent(model: TaxModel) -> None:
    [fy] = model.annual_tax([_trade(Bucket.STCG, "10000")])
    assert fy.tax_before_cess == Decimal("2000.000")
    assert fy.total_tax == Decimal("2080.00000")


def test_ltcg_is_twelve_point_five_percent_above_the_exemption(model: TaxModel) -> None:
    """Rs 2,00,000 LTCG: the first Rs 1.25L is exempt, 12.5% applies to the remaining Rs 75,000."""
    [fy] = model.annual_tax([_trade(Bucket.LTCG, "200000")])
    [outcome] = fy.buckets
    assert outcome.exempt == Decimal("125000")
    assert outcome.taxable == Decimal("75000")
    assert fy.tax_before_cess == Decimal("9375.000")


def test_ltcg_below_the_exemption_is_free(model: TaxModel) -> None:
    """The seed-scale case: a small account's whole LTCG can sit inside the exemption.

    Real, and exactly why it is config — the exemption is per-taxpayer, so the operator's other
    holdings may already have spent it and a backtest has no way to know.
    """
    [fy] = model.annual_tax([_trade(Bucket.LTCG, "40000")])
    assert fy.total_tax == Decimal(0)
    assert fy.buckets[0].exempt == Decimal("40000")


def test_the_exemption_does_not_recur_within_a_year(model: TaxModel) -> None:
    """Two LTCG trades in one FY share ONE exemption, not one each."""
    [fy] = model.annual_tax(
        [_trade(Bucket.LTCG, "100000", month=5), _trade(Bucket.LTCG, "100000", month=9)]
    )
    assert fy.buckets[0].exempt == Decimal("125000")
    assert fy.buckets[0].taxable == Decimal("75000")


def test_the_exemption_does_recur_across_years(model: TaxModel) -> None:
    years = model.annual_tax(
        [_trade(Bucket.LTCG, "100000", year=2026), _trade(Bucket.LTCG, "100000", year=2027)]
    )
    assert [y.total_tax for y in years] == [Decimal(0), Decimal(0)]


def test_a_losing_year_owes_nothing_not_a_refund(model: TaxModel) -> None:
    [fy] = model.annual_tax([_trade(Bucket.NONSPECULATIVE, "-5000")])
    assert fy.total_tax == Decimal(0)
    assert fy.buckets[0].loss_carried_out == Decimal("5000")


def test_cess_is_levied_on_the_tax_not_on_the_profit(model: TaxModel, tax_cfg: TaxConfig) -> None:
    [fy] = model.annual_tax([_trade(Bucket.NONSPECULATIVE, "10000")])
    assert fy.cess == fy.tax_before_cess * Decimal(str(tax_cfg.cess_rate))


# --------------------------------------------------------------------------------------
# The VDA stress — the acceptance criterion for this task
# --------------------------------------------------------------------------------------
def _crypto_year() -> list[RealizedTrade]:
    """Three winners of 100, two losers of 80. Gross +140 — a modestly profitable strategy."""
    return [
        _trade(Bucket.CRYPTO_SPECULATIVE, "100", month=5),
        _trade(Bucket.CRYPTO_SPECULATIVE, "100", month=6),
        _trade(Bucket.CRYPTO_SPECULATIVE, "100", month=7),
        _trade(Bucket.CRYPTO_SPECULATIVE, "-80", month=8),
        _trade(Bucket.CRYPTO_SPECULATIVE, "-80", month=9),
    ]


def test_default_scenario_taxes_the_net(tax_cfg: TaxConfig) -> None:
    """Optimistic reading — speculative business income, so losses offset gains within the bucket:
    30% of the net 140, plus cess."""
    [fy] = TaxModel(tax_cfg).annual_tax(_crypto_year())
    assert fy.gross_pnl == Decimal(140)
    assert fy.buckets[0].taxable == Decimal(140)
    assert fy.total_tax == Decimal("42") * Decimal("1.04")


def test_reclassification_stress_taxes_the_winners_alone(tax_cfg: TaxConfig) -> None:
    """The trap. Under VDA the losses grant NOTHING, so tax lands on the 300 of winners, not the
    140 of net — and the effective rate on real profit is 66.9%, not 30%."""
    stressed = TaxModel(tax_cfg, scenario=Scenario.CRYPTO_RECLASSIFIED)
    [fy] = stressed.annual_tax(_crypto_year())

    assert fy.buckets[0].bucket is Bucket.CRYPTO_VDA
    assert fy.gross_pnl == Decimal(140)  # the real profit is unchanged...
    assert fy.buckets[0].taxable == Decimal(300)  # ...but the taxable base is the winners alone
    assert fy.total_tax == Decimal("90") * Decimal("1.04")  # 93.60
    assert fy.net_pnl == Decimal("46.40")
    assert effective_tax_rate([fy]) > Decimal("0.66")


def test_the_two_scenarios_differ_materially(tax_cfg: TaxConfig) -> None:
    """The literal task AC: after-tax P&L must differ correctly between default and stress."""
    ledger = _crypto_year()
    default = TaxModel(tax_cfg).annual_tax(ledger)
    stressed = TaxModel(tax_cfg, scenario=Scenario.CRYPTO_RECLASSIFIED).annual_tax(ledger)

    assert stressed[0].total_tax > default[0].total_tax
    assert stressed[0].net_pnl < default[0].net_pnl
    assert stressed[0].gross_pnl == default[0].gross_pnl  # only the tax treatment changed


def test_vda_can_turn_a_profitable_strategy_into_a_losing_one(tax_cfg: TaxConfig) -> None:
    """A high-churn, thin-edge strategy: 10 wins of 100, 9 losses of 100. Gross +100, and under VDA
    it pays 30% on 1,000 of winners — a Rs 100 profit becomes a Rs 212 loss."""
    ledger = [_trade(Bucket.CRYPTO_SPECULATIVE, "100") for _ in range(10)]
    ledger += [_trade(Bucket.CRYPTO_SPECULATIVE, "-100") for _ in range(9)]
    [fy] = TaxModel(tax_cfg, scenario=Scenario.CRYPTO_RECLASSIFIED).annual_tax(ledger)

    assert fy.gross_pnl == Decimal(100)
    assert fy.net_pnl < 0
    assert fy.net_pnl == Decimal(100) - Decimal(300) * Decimal("1.04")


def test_vda_losses_never_carry_forward(tax_cfg: TaxConfig) -> None:
    """A losing VDA year gives the next year nothing — unlike every other bucket."""
    stressed = TaxModel(tax_cfg, scenario=Scenario.CRYPTO_RECLASSIFIED)
    years = stressed.annual_tax(
        [
            _trade(Bucket.CRYPTO_SPECULATIVE, "-10000", year=2026),
            _trade(Bucket.CRYPTO_SPECULATIVE, "10000", year=2027),
        ]
    )
    assert years[0].buckets[0].loss_carried_out == Decimal(0)
    assert years[1].buckets[0].loss_absorbed == Decimal(0)
    assert years[1].total_tax == Decimal("3000") * Decimal("1.04")


def test_the_stress_leaves_equity_buckets_alone(tax_cfg: TaxConfig) -> None:
    """The reclassification risk is crypto-specific — it must not touch equity treatment."""
    ledger = [_trade(Bucket.NONSPECULATIVE, "10000"), _trade(Bucket.STCG, "10000")]
    default = TaxModel(tax_cfg).annual_tax(ledger)
    stressed = TaxModel(tax_cfg, scenario=Scenario.CRYPTO_RECLASSIFIED).annual_tax(ledger)
    assert default[0].total_tax == stressed[0].total_tax


# --------------------------------------------------------------------------------------
# Carry-forward
# --------------------------------------------------------------------------------------
def test_a_prior_year_loss_reduces_this_year_tax(model: TaxModel) -> None:
    years = model.annual_tax(
        [
            _trade(Bucket.NONSPECULATIVE, "-4000", year=2026),
            _trade(Bucket.NONSPECULATIVE, "10000", year=2027),
        ]
    )
    assert years[1].buckets[0].loss_absorbed == Decimal("4000")
    assert years[1].buckets[0].taxable == Decimal("6000")
    assert years[1].tax_before_cess == Decimal("1800.00")


def test_relief_is_capped_by_the_loss_available(model: TaxModel) -> None:
    years = model.annual_tax(
        [
            _trade(Bucket.NONSPECULATIVE, "-2000", year=2026),
            _trade(Bucket.NONSPECULATIVE, "1000", year=2027),
        ]
    )
    assert years[1].buckets[0].taxable == Decimal(0)
    assert years[1].buckets[0].loss_carried_out == Decimal("1000")  # the unused half survives


def test_speculative_losses_expire_after_four_years(model: TaxModel) -> None:
    """4-year window: a FY2026 loss helps through FY2030 and is gone by FY2031."""
    within = model.annual_tax(
        [
            _trade(Bucket.EQUITY_SPECULATIVE, "-5000", year=2026),
            _trade(Bucket.EQUITY_SPECULATIVE, "5000", year=2030),
        ]
    )
    assert within[1].total_tax == Decimal(0)

    beyond = model.annual_tax(
        [
            _trade(Bucket.EQUITY_SPECULATIVE, "-5000", year=2026),
            _trade(Bucket.EQUITY_SPECULATIVE, "5000", year=2031),
        ]
    )
    assert beyond[1].buckets[0].loss_absorbed == Decimal(0)
    assert beyond[1].tax_before_cess == Decimal("1500.00")


def test_nonspeculative_losses_last_eight_years(model: TaxModel) -> None:
    """The asymmetry that makes F&O and delivery-as-business more forgiving than intraday."""
    years = model.annual_tax(
        [
            _trade(Bucket.NONSPECULATIVE, "-5000", year=2026),
            _trade(Bucket.NONSPECULATIVE, "5000", year=2034),
        ]
    )
    assert years[1].total_tax == Decimal(0)  # still inside the 8-year window


def test_losses_expire_on_the_calendar_not_on_activity(model: TaxModel) -> None:
    """A loss must age through years with no trading at all — otherwise a quiet period would
    preserve relief the statute has already extinguished."""
    years = model.annual_tax(
        [
            _trade(Bucket.EQUITY_SPECULATIVE, "-5000", year=2026),
            _trade(Bucket.EQUITY_SPECULATIVE, "5000", year=2032),
        ]
    )
    assert len(years) == 2  # empty years produce no bill...
    assert years[1].buckets[0].loss_absorbed == Decimal(0)  # ...but the loss still expired


def test_oldest_losses_are_spent_first(model: TaxModel) -> None:
    """Spend what is closest to expiring. Consuming the newest first would strand the old loss and
    let it lapse — costing real money, invisibly."""
    years = model.annual_tax(
        [
            _trade(Bucket.EQUITY_SPECULATIVE, "-1000", year=2026),
            _trade(Bucket.EQUITY_SPECULATIVE, "-1000", year=2029),
            _trade(Bucket.EQUITY_SPECULATIVE, "1000", year=2030),  # absorbs the 2026 loss
            _trade(Bucket.EQUITY_SPECULATIVE, "1000", year=2032),  # 2026 would have expired
        ]
    )
    assert years[2].buckets[0].loss_absorbed == Decimal("1000")
    assert years[3].buckets[0].loss_absorbed == Decimal("1000")  # the 2029 loss, still valid
    assert years[3].total_tax == Decimal(0)


# --------------------------------------------------------------------------------------
# The documented simplification: buckets do not offset each other
# --------------------------------------------------------------------------------------
def test_buckets_do_not_offset_each_other_and_that_is_conservative(model: TaxModel) -> None:
    """A loss in one bucket does not shelter a gain in another. Real law would allow some of this,
    so the bill computed here is >= the true one — the safe direction — and the loss is not lost,
    it carries forward inside its own bucket."""
    [fy] = model.annual_tax(
        [_trade(Bucket.NONSPECULATIVE, "10000"), _trade(Bucket.EQUITY_SPECULATIVE, "-10000")]
    )
    assert fy.gross_pnl == Decimal(0)  # flat year overall...
    assert fy.total_tax > 0  # ...yet tax is owed on the profitable bucket
    speculative = next(b for b in fy.buckets if b.bucket is Bucket.EQUITY_SPECULATIVE)
    assert speculative.loss_carried_out == Decimal("10000")  # preserved, not discarded


# --------------------------------------------------------------------------------------
# Bucket classification
# --------------------------------------------------------------------------------------
def test_intraday_and_fno_classification_is_fixed_law(model: TaxModel) -> None:
    assert model.bucket_for(Segment.EQUITY_INTRADAY, holding_days=0) is Bucket.EQUITY_SPECULATIVE
    assert model.bucket_for(Segment.EQUITY_FUTURES, holding_days=0) is Bucket.NONSPECULATIVE
    assert model.bucket_for(Segment.EQUITY_OPTIONS, holding_days=400) is Bucket.NONSPECULATIVE


def test_delivery_as_business_ignores_holding_period(model: TaxModel) -> None:
    """Under the default (business-income) classification there is no STCG/LTCG split at all."""
    assert model.bucket_for(Segment.EQUITY_DELIVERY, holding_days=1) is Bucket.NONSPECULATIVE
    assert model.bucket_for(Segment.EQUITY_DELIVERY, holding_days=500) is Bucket.NONSPECULATIVE


def test_delivery_as_capital_gains_splits_on_holding_period(tax_cfg: TaxConfig) -> None:
    cg = TaxModel(tax_cfg.model_copy(update={"equity_delivery": "capital_gains"}))
    assert cg.bucket_for(Segment.EQUITY_DELIVERY, holding_days=30) is Bucket.STCG
    assert cg.bucket_for(Segment.EQUITY_DELIVERY, holding_days=400) is Bucket.LTCG


def test_business_classification_is_the_costlier_default(tax_cfg: TaxConfig) -> None:
    """The default must not be the cheaper reading. Business income at a 30% slab costs more than
    20% STCG, so defaulting to it means the gate is never flattered by an unconfirmed choice."""
    business = TaxModel(tax_cfg)
    capital = TaxModel(tax_cfg.model_copy(update={"equity_delivery": "capital_gains"}))
    ledger_bucket_business = business.bucket_for(Segment.EQUITY_DELIVERY, holding_days=30)
    ledger_bucket_capital = capital.bucket_for(Segment.EQUITY_DELIVERY, holding_days=30)

    [as_business] = business.annual_tax([_trade(ledger_bucket_business, "10000")])
    [as_capital] = capital.annual_tax([_trade(ledger_bucket_capital, "10000")])
    assert as_business.total_tax > as_capital.total_tax


# --------------------------------------------------------------------------------------
# effective_tax_rate + empty input
# --------------------------------------------------------------------------------------
def test_no_trades_means_no_bill(model: TaxModel) -> None:
    assert model.annual_tax([]) == []
    assert effective_tax_rate([]) == Decimal(0)


def test_effective_rate_is_zero_when_there_was_no_profit(model: TaxModel) -> None:
    years = model.annual_tax([_trade(Bucket.NONSPECULATIVE, "-1000")])
    assert effective_tax_rate(years) == Decimal(0)


def test_effective_rate_exceeds_the_headline_across_a_loss_year(model: TaxModel) -> None:
    """Loss then profit, with the loss expiring first: you pay on the winner having netted zero
    overall. This is the honest reason a strategy's tax drag can beat its nominal rate."""
    years = model.annual_tax(
        [
            _trade(Bucket.EQUITY_SPECULATIVE, "-9000", year=2026),
            _trade(Bucket.EQUITY_SPECULATIVE, "10000", year=2031),  # 4-year window has lapsed
        ]
    )
    assert effective_tax_rate(years) > Decimal("0.30")


# --------------------------------------------------------------------------------------
# Config guards — the settled-law assertions
# --------------------------------------------------------------------------------------
def _load_with_tax(tmp_path: Path, repo_root: Path, mutate: Any) -> None:
    raw: dict[str, Any] = yaml.safe_load((repo_root / "goal.yaml").read_text(encoding="utf-8"))
    mutate(raw["tax"])
    p = tmp_path / "goal.yaml"
    p.write_text(yaml.safe_dump(raw), encoding="utf-8")
    load_goal(p)


@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("equity_intraday", "capital_gains"),
        ("equity_fno", "speculative_business"),
        ("crypto_inr_derivatives", "capital_gains"),
        ("crypto_reclassification_stress", "none"),
    ],
)
def test_settled_law_classifications_cannot_be_edited(
    tmp_path: Path, repo_root: Path, key: str, bad: str
) -> None:
    """These are statute, not tunables. An edit moving income to a cheaper bucket must fail at
    startup rather than quietly reduce every tax figure the system reports."""

    def mutate(tax: dict[str, Any]) -> None:
        tax[key] = bad

    with pytest.raises(ConfigError, match=key):
        _load_with_tax(tmp_path, repo_root, mutate)


def test_delivery_classification_must_be_one_of_the_two_readings(
    tmp_path: Path, repo_root: Path
) -> None:
    def mutate(tax: dict[str, Any]) -> None:
        tax["equity_delivery"] = "per_classification"  # the old placeholder, not a real treatment

    with pytest.raises(ConfigError, match="equity_delivery"):
        _load_with_tax(tmp_path, repo_root, mutate)


def test_zero_slab_rate_is_rejected(tmp_path: Path, repo_root: Path) -> None:
    """A zero slab would make every business-income strategy look tax-free."""

    def mutate(tax: dict[str, Any]) -> None:
        tax["operator_slab_rate"] = 0.0

    with pytest.raises(ConfigError, match="operator_slab_rate"):
        _load_with_tax(tmp_path, repo_root, mutate)


def test_ltcg_exemption_cannot_exceed_the_ceiling(tmp_path: Path, repo_root: Path) -> None:
    def mutate(tax: dict[str, Any]) -> None:
        tax["ltcg_exemption_inr"] = 500000

    with pytest.raises(ConfigError, match="ltcg_exemption_inr"):
        _load_with_tax(tmp_path, repo_root, mutate)


def test_a_reduced_ltcg_exemption_is_allowed(tmp_path: Path, repo_root: Path) -> None:
    """The operator's other holdings may already have consumed it — that must be settable."""

    def mutate(tax: dict[str, Any]) -> None:
        tax["ltcg_exemption_inr"] = 0

    _load_with_tax(tmp_path, repo_root, mutate)  # must not raise
