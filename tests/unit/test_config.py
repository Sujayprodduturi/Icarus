"""Tests for the goal.yaml loader (task 0.2): happy path + fail-fast on bad config."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

import pytest
import yaml

from icarus.common.config import ConfigError, GoalConfig, load_goal


def test_loads_repo_goal_yaml(repo_root: Path) -> None:
    cfg = load_goal(repo_root / "goal.yaml")
    assert isinstance(cfg, GoalConfig)
    assert cfg.objective.account_currency == "INR"
    assert cfg.risk.crypto_max_leverage_hard == 2.0
    assert cfg.compliance.limit_orders_only is True
    assert cfg.recovery.startup_state == "RECOVERY"


def test_missing_file_raises() -> None:
    with pytest.raises(ConfigError, match="not found"):
        load_goal("does_not_exist_goal.yaml")


def test_malformed_yaml_raises(tmp_path: Path) -> None:
    bad = tmp_path / "goal.yaml"
    bad.write_text("objective: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigError):
        load_goal(bad)


def _load_dict(tmp_path: Path, data: dict[str, Any]) -> GoalConfig:
    p = tmp_path / "goal.yaml"
    p.write_text(yaml.safe_dump(data), encoding="utf-8")
    return load_goal(p)


def _valid_raw(repo_root: Path) -> dict[str, Any]:
    raw: dict[str, Any] = yaml.safe_load((repo_root / "goal.yaml").read_text(encoding="utf-8"))
    return raw


def test_signal_test_accepts_only_the_pre_registered_d15_shape(
    tmp_path: Path, repo_root: Path
) -> None:
    """A loader without the typed block would accept none of the settings the diagnostic needs."""
    raw = _valid_raw(repo_root)
    raw["signal_test"] = {
        "registered": date(2026, 8, 22),
        "statistics_registered": date(2026, 9, 24),
        "notional_inr": 100_000,
        "one_position_per_symbol": True,
        "apply_costs": True,
        "apply_tax": False,
        "diagnostic_only": True,
        "block_min_sessions": 63,
        "holding_period_block_multiplier": 3,
        "ci_level": 0.95,
        "placebo_permutations": 4_999,
        "rng_seed": 20_260_924,
        "inference_enabled": False,
    }

    cfg = _load_dict(tmp_path, raw)

    assert cfg.signal_test.notional_inr == 100_000
    assert cfg.signal_test.apply_costs is True
    assert cfg.signal_test.apply_tax is False
    assert cfg.signal_test.diagnostic_only is True
    assert cfg.signal_test.block_min_sessions == 63
    assert cfg.signal_test.holding_period_block_multiplier == 3
    assert cfg.signal_test.ci_level == 0.95
    assert cfg.signal_test.placebo_permutations == 4_999
    assert cfg.signal_test.rng_seed == 20_260_924
    assert cfg.signal_test.inference_enabled is False


@pytest.mark.parametrize(
    ("key", "unsafe_value"),
    [
        ("registered", date(2026, 8, 23)),
        ("statistics_registered", date(2026, 9, 25)),
        ("notional_inr", 1_000_000),
        ("one_position_per_symbol", False),
        ("apply_costs", False),
        ("apply_tax", True),
        ("diagnostic_only", False),
        ("block_min_sessions", 64),
        ("holding_period_block_multiplier", 4),
        ("ci_level", 0.90),
        ("placebo_permutations", 5_000),
        ("rng_seed", 1),
        ("inference_enabled", True),
    ],
)
def test_signal_test_pre_registered_contract_cannot_be_changed(
    tmp_path: Path, repo_root: Path, key: str, unsafe_value: object
) -> None:
    """Every mutation would change the result or let a diagnostic masquerade as a gate."""
    raw = _valid_raw(repo_root)
    raw["signal_test"] = {
        "registered": date(2026, 8, 22),
        "statistics_registered": date(2026, 9, 24),
        "notional_inr": 100_000,
        "one_position_per_symbol": True,
        "apply_costs": True,
        "apply_tax": False,
        "diagnostic_only": True,
        "block_min_sessions": 63,
        "holding_period_block_multiplier": 3,
        "ci_level": 0.95,
        "placebo_permutations": 4_999,
        "rng_seed": 20_260_924,
        "inference_enabled": False,
    }
    raw["signal_test"][key] = unsafe_value

    with pytest.raises(ConfigError, match=key):
        _load_dict(tmp_path, raw)


def test_missing_key_fails_fast(tmp_path: Path, repo_root: Path) -> None:
    raw = _valid_raw(repo_root)
    del raw["risk"]  # drop a whole required block
    with pytest.raises(ConfigError):
        _load_dict(tmp_path, raw)


def test_typo_key_rejected(tmp_path: Path, repo_root: Path) -> None:
    raw = _valid_raw(repo_root)
    raw["risk"]["per_trade_risk_rr"] = 0.005  # typo'd key (extra=forbid)
    with pytest.raises(ConfigError):
        _load_dict(tmp_path, raw)


def test_leverage_ceiling_cannot_loosen(tmp_path: Path, repo_root: Path) -> None:
    # Invariant #7: a goal.yaml trying to raise the crypto ceiling above 2x is rejected.
    raw = _valid_raw(repo_root)
    raw["risk"]["crypto_max_leverage_hard"] = 5.0
    with pytest.raises(ConfigError, match="ceiling"):
        _load_dict(tmp_path, raw)


def test_limit_orders_only_cannot_be_disabled(tmp_path: Path, repo_root: Path) -> None:
    raw = _valid_raw(repo_root)
    raw["compliance"]["limit_orders_only"] = False
    with pytest.raises(ConfigError, match="limit_orders_only"):
        _load_dict(tmp_path, raw)


def test_crypto_options_cannot_be_enabled(tmp_path: Path, repo_root: Path) -> None:
    raw = _valid_raw(repo_root)
    raw["crypto"]["options_enabled"] = True
    with pytest.raises(ConfigError, match="options_enabled"):
        _load_dict(tmp_path, raw)


def test_derisk_must_precede_daily_halt(tmp_path: Path, repo_root: Path) -> None:
    raw = _valid_raw(repo_root)
    raw["risk"]["daily_derisk_trigger"] = 0.05  # above the 0.03 halt -> invalid ladder
    with pytest.raises(ConfigError, match="daily_derisk_trigger"):
        _load_dict(tmp_path, raw)


def test_recovery_startup_state_enforced(tmp_path: Path, repo_root: Path) -> None:
    raw = _valid_raw(repo_root)
    raw["recovery"]["startup_state"] = "TRADING"
    with pytest.raises(ConfigError, match="RECOVERY"):
        _load_dict(tmp_path, raw)


# --------------------------------------------------------------------------------------
# The pre-registered stop gate (2026-08-01) and the data split.
#
# These exist because an LLM council found the Phase-1 gate specified a deliverable ("produce a
# metric sheet and pause") rather than a threshold — it was the only task with no acceptance
# criteria and it could not be failed. The tests below guard the two ways that fix could be
# silently undone: re-dating the commitment, and overlapping the lockbox into training data.
# --------------------------------------------------------------------------------------
def test_stop_gate_cannot_be_redated(tmp_path: Path, repo_root: Path) -> None:
    """Moving the pre-registration date forward is how a lowered bar would be laundered: the
    numbers get edited after a metric sheet exists and the date is updated to match."""
    raw = _valid_raw(repo_root)
    raw["stop_gate"]["pre_registered_on"] = date(2027, 1, 1)
    with pytest.raises(ConfigError, match="pre_registered_on"):
        _load_dict(tmp_path, raw)


def test_stop_gate_trade_tiers_must_be_ordered(tmp_path: Path, repo_root: Path) -> None:
    """NEEDS_MORE_DATA is the band *below* PROMOTE. Inverting them would make a 30-trade result
    promotable — the exact small-sample promotion the tiers exist to prevent."""
    raw = _valid_raw(repo_root)
    raw["stop_gate"]["trade_count_needs_more_data"] = 200  # above the 100 promote threshold
    with pytest.raises(ConfigError, match="trade_count_needs_more_data"):
        _load_dict(tmp_path, raw)


def test_gate_metrics_cannot_be_made_gross(tmp_path: Path, repo_root: Path) -> None:
    """Gross-of-cost metrics are a bug (CLAUDE.md §5), not a configuration choice."""
    raw = _valid_raw(repo_root)
    raw["stop_gate"]["net_of_cost_and_tax"] = False
    with pytest.raises(ConfigError, match="net_of_cost_and_tax"):
        _load_dict(tmp_path, raw)


def test_lockbox_may_not_overlap_the_walk_forward_window(tmp_path: Path, repo_root: Path) -> None:
    """An overlap turns the lockbox into training data — the failure the single-use rule exists
    to prevent, and one that leaves no trace in any metric."""
    raw = _valid_raw(repo_root)
    raw["data_split"]["walk_forward_end"] = date(2023, 6, 30)  # past lockbox_start 2023-01-01
    with pytest.raises(ConfigError, match="lockbox_start"):
        _load_dict(tmp_path, raw)


def test_lockbox_is_single_use(tmp_path: Path, repo_root: Path) -> None:
    raw = _valid_raw(repo_root)
    raw["data_split"]["lockbox_uses_allowed"] = 2
    with pytest.raises(ConfigError, match="lockbox_uses_allowed"):
        _load_dict(tmp_path, raw)


# --------------------------------------------------------------------------------------
# Position count vs heat cap — two controls over one quantity
# --------------------------------------------------------------------------------------
def test_full_book_may_not_breach_the_heat_cap(tmp_path: Path, repo_root: Path) -> None:
    """5 slots x 0.5% = 2.5% heat against a 2% cap. The heat cap is the binding control."""
    raw = _valid_raw(repo_root)
    raw["risk"]["max_open_positions"] = 5
    with pytest.raises(ConfigError, match="max_portfolio_heat"):
        _load_dict(tmp_path, raw)


def test_shipped_position_count_exactly_saturates_the_heat_budget() -> None:
    """4 slots x 0.5% = exactly 2%. This is the derivation, asserted so a later edit to either
    number surfaces the interaction rather than silently wasting or breaching the budget."""
    cfg = load_goal(Path(__file__).resolve().parents[2] / "goal.yaml").risk
    assert cfg.max_open_positions * cfg.per_trade_risk_r == pytest.approx(cfg.max_portfolio_heat)


# ------------------------------------------------------------------------------------------
# min_sharpe amendment log (O8, resolved 2026-08-02).
#
# The operator asked that the bar stay changeable in future. Invariant #25 says the gate is not
# renegotiated once results are seen. Both hold if the value is append-only rather than frozen:
# it may move, but a move can never be invisible or backdated.
# ------------------------------------------------------------------------------------------


def test_min_sharpe_matches_the_latest_amendment(repo_root: Path) -> None:
    cfg = load_goal(repo_root / "goal.yaml")
    assert cfg.objective.min_sharpe == 1.0
    assert cfg.objective.min_sharpe_amendments[-1].value == 1.0


def test_editing_min_sharpe_without_logging_it_is_rejected(tmp_path: Path, repo_root: Path) -> None:
    """The failure the log exists to prevent: a value with a provenance that is false."""
    raw = _valid_raw(repo_root)
    raw["objective"]["min_sharpe"] = 0.4
    with pytest.raises(ConfigError, match="edit the log, not just the value"):
        _load_dict(tmp_path, raw)


def test_an_empty_amendment_log_is_rejected(tmp_path: Path, repo_root: Path) -> None:
    raw = _valid_raw(repo_root)
    raw["objective"]["min_sharpe_amendments"] = []
    with pytest.raises(ConfigError, match="traceable to a dated decision"):
        _load_dict(tmp_path, raw)


# --------------------------------------------------------------------------------------
# A safety limit must not be editable into not being one (task 2e, finding F36).
#
# Invariant #4 says hard risk limits cannot be overridden by any strategy or by the learning loop.
# They could not — and a one-line edit to goal.yaml could. A review demonstrated it by loading six
# mutated configs cleanly; only the crypto leverage ceiling refused, because it alone had an
# assert. These tests are that demonstration, kept.
# --------------------------------------------------------------------------------------

_LOOSENINGS = [
    # The first pass bounded three rungs of the ladder and stopped. These five were found by
    # the review of that pass, each loading cleanly at a value that switched the control off.
    ("risk", "kelly_fraction_cap", 1.00, "full Kelly, against CLAUDE.md 'never exceed half'"),
    ("risk", "new_strategy_size_factor", 1.00, "the canary period is disabled"),
    ("risk", "per_trade_risk_r", 0.25, "50x the per-trade risk the PRD sets"),
    ("risk", "max_portfolio_heat", 1.00, "the whole account may be at risk at once"),
    ("risk", "stagnation_check_after_trades", 1_000_000, "invariant #23 never fires"),
    ("tax", "operator_slab_rate", 0.0001, "business income becomes effectively untaxed"),
    ("tax", "cess_rate", 0.0, "the statutory 4% cess disappears"),
    ("risk", "max_drawdown_killswitch", 1.00, "disables the -10% operator-only stop"),
    ("risk", "daily_loss_limit", 1.00, "disables the daily halt"),
    ("risk", "daily_derisk_trigger", 0.99, "de-risk never fires"),
    ("tax", "vda_flat_rate", 0.0, "the mandated VDA stress becomes tax-free"),
    ("tax", "stcg_rate", 0.0, "short-term gains become untaxed"),
    ("tax", "ltcg_rate", 0.0, "long-term gains become untaxed"),
    ("stop_gate", "require_sharpe_lower_bound_above", -5.0, "the gate accepts anything"),
    ("stop_gate", "max_pbo", 1.00, "overfitting is never rejected"),
]


@pytest.mark.parametrize(
    ("section", "key", "loosened", "effect"), _LOOSENINGS, ids=[k for _, k, _, _ in _LOOSENINGS]
)
def test_a_safety_limit_cannot_be_loosened_by_editing_the_file(
    tmp_path: Path, repo_root: Path, section: str, key: str, loosened: float, effect: str
) -> None:
    raw = _valid_raw(repo_root)
    raw[section][key] = loosened
    with pytest.raises(ConfigError):
        _load_dict(tmp_path, raw)


@pytest.mark.parametrize(
    ("section", "key", "stricter"),
    [
        ("risk", "max_drawdown_killswitch", 0.05),
        ("risk", "daily_loss_limit", 0.02),
        ("tax", "vda_flat_rate", 0.40),
        ("tax", "stcg_rate", 0.25),
    ],
)
def test_a_stricter_setting_is_still_allowed(
    tmp_path: Path, repo_root: Path, section: str, key: str, stricter: float
) -> None:
    """The bound is one-sided on purpose. Halting sooner, or assuming a harsher tax than the
    statute, are both things an operator may legitimately want; only loosening is forbidden."""
    raw = _valid_raw(repo_root)
    raw[section][key] = stricter
    assert _load_dict(tmp_path, raw) is not None


def test_zero_does_not_count_as_a_strict_kill_switch(tmp_path: Path, repo_root: Path) -> None:
    """Zero passes an upper bound and means "never halt", which is the loosest setting there is."""
    raw = _valid_raw(repo_root)
    raw["risk"]["max_drawdown_killswitch"] = 0.0
    with pytest.raises(ConfigError, match="must be > 0"):
        _load_dict(tmp_path, raw)


@pytest.mark.parametrize(
    ("key", "loosened"),
    [("require_sharpe_lower_bound_above", -5.0), ("max_pbo", 1.0)],
)
def test_a_signed_amendment_does_not_buy_a_looser_gate(
    tmp_path: Path, repo_root: Path, key: str, loosened: float
) -> None:
    """The log alone was not enough, which the review of the first pass showed.

    Provenance makes a change *visible*; it does not make it *permitted*. Append a properly signed
    amendment — dated later, ``results_existed: true``, ``acknowledged_post_hoc: true`` — and the
    log is perfectly happy, because that is what it is for. The gate's own header says it is not
    renegotiated once results are seen, and results have existed since 2026-08-07, so these two
    carry a bound as well: the log records movement *within* what is defensible.
    """
    raw = _valid_raw(repo_root)
    raw["stop_gate"][key] = loosened
    raw["stop_gate"][f"{key}_amendments"].append(
        {
            "value": loosened,
            "set_on": date(2026, 9, 1),
            "results_existed": True,
            "acknowledged_post_hoc": True,
            "reason": "a signed, dated, entirely honest attempt to lower the bar",
        }
    )
    with pytest.raises(ConfigError):
        _load_dict(tmp_path, raw)


def test_a_signed_amendment_can_still_tighten_the_gate(tmp_path: Path, repo_root: Path) -> None:
    """The bound is one-sided, so the log keeps its purpose: raising the bar is always allowed."""
    raw = _valid_raw(repo_root)
    raw["stop_gate"]["require_sharpe_lower_bound_above"] = 0.5
    raw["stop_gate"]["require_sharpe_lower_bound_above_amendments"].append(
        {
            "value": 0.5,
            "set_on": date(2026, 9, 1),
            "results_existed": True,
            "acknowledged_post_hoc": True,
            "reason": "tightening after the first metric sheet",
        }
    )
    assert _load_dict(tmp_path, raw) is not None


def test_the_gate_thresholds_that_are_judgement_carry_an_amendment_log(repo_root: Path) -> None:
    """The block asserted an immutable `pre_registered_on` while the numbers under it stayed
    freely editable — a provenance the file could not actually vouch for. The two judgement
    thresholds now trace to dated entries; the rest have an external authority and are bounded."""
    gate = load_goal(repo_root / "goal.yaml").stop_gate
    assert gate.require_sharpe_lower_bound_above_amendments[-1].value == (
        gate.require_sharpe_lower_bound_above
    )
    assert gate.max_pbo_amendments[-1].value == gate.max_pbo
    assert not any(a.results_existed for a in gate.max_pbo_amendments), (
        "the gate was pre-registered before any backtest; an entry claiming otherwise is a story"
    )


# --------------------------------------------------------------------------------------
# Config that promised something it did not do (task 2e, findings F11/F37)
# --------------------------------------------------------------------------------------


def test_the_quality_score_keys_are_gone(tmp_path: Path, repo_root: Path) -> None:
    """`min_quality_score` and `rank_select_top_k` named a scorer that has never existed.

    Deleted rather than marked NOT ENFORCED: a marker preserves a promise, and there was no
    promise — only a name. `extra="forbid"` means reinstating one without its code now fails loudly.
    """
    raw = _valid_raw(repo_root)
    raw["trade_quality"]["min_quality_score"] = 0.6
    with pytest.raises(ConfigError):
        _load_dict(tmp_path, raw)


def test_there_is_only_one_lockbox_allowance(tmp_path: Path, repo_root: Path) -> None:
    """`overfitting.lockbox_eval_budget: 50` contradicted `data_split.lockbox_uses_allowed: 1`,
    which the loader hard-asserts because invariant #26 says the lockbox is consumed exactly once.
    Neither was wired, so whoever wired one would have picked the plausible-sounding name."""
    cfg = load_goal(repo_root / "goal.yaml")
    assert cfg.data_split.lockbox_uses_allowed == 1
    raw = _valid_raw(repo_root)
    raw["overfitting"]["lockbox_eval_budget"] = 50
    with pytest.raises(ConfigError):
        _load_dict(tmp_path, raw)


def test_the_stale_position_threshold_carries_the_same_log(repo_root: Path) -> None:
    """Added 2026-08-14 (task 2c). The first draft of that field simply sat inside the ``backtest``
    block, borrowing the ``registered: 2026-08-05`` date the loader pins — a provenance five
    sessions older than the field. The argument for it, that neither direction of the threshold
    flatters a result, was disproved by the task's own test: writing a dead holding off sooner
    frees a slot sooner, and in a book discarding 94-99.99% of its signals for want of a slot that
    changes which later signals are taken."""
    cfg = load_goal(repo_root / "goal.yaml")
    log = cfg.backtest.stale_position_sessions_amendments
    assert log[-1].value == cfg.backtest.stale_position_sessions
    assert log[-1].acknowledged_post_hoc, "introduced after results existed; it must be signed"


def test_editing_the_stale_position_threshold_without_logging_it_is_rejected(
    tmp_path: Path, repo_root: Path
) -> None:
    """The mechanism has to bite on the new field too, not just on the one it was written for."""
    raw = _valid_raw(repo_root)
    raw["backtest"]["stale_position_sessions"] = 3
    with pytest.raises(ConfigError, match="edit the log, not just the value"):
        _load_dict(tmp_path, raw)


def test_amendments_must_be_chronological(tmp_path: Path, repo_root: Path) -> None:
    """Out-of-order entries would let a later decision be filed as if it came first."""
    raw = _valid_raw(repo_root)
    raw["objective"]["min_sharpe_amendments"] = list(
        reversed(raw["objective"]["min_sharpe_amendments"])
    )
    with pytest.raises(ConfigError, match="strictly increasing date order"):
        _load_dict(tmp_path, raw)


def test_two_amendments_on_the_same_day_are_rejected(tmp_path: Path, repo_root: Path) -> None:
    """Sorted is not enough: equal dates have no order, so ``history[-1]`` becomes whichever the
    operator happened to list last, and the same pair validates against two different live values.
    That is the append-only guarantee quietly failing rather than refusing."""
    raw = _valid_raw(repo_root)
    log = raw["objective"]["min_sharpe_amendments"]
    log[-1]["set_on"] = log[-2]["set_on"]
    with pytest.raises(ConfigError, match="strictly increasing date order"):
        _load_dict(tmp_path, raw)


def test_lowering_the_bar_after_results_must_be_signed(tmp_path: Path, repo_root: Path) -> None:
    """The rationalisation guard: allowed, but only with the admission written down."""
    raw = _valid_raw(repo_root)
    raw["objective"]["min_sharpe"] = 0.5
    raw["objective"]["min_sharpe_amendments"].append(
        {
            "value": 0.5,
            "set_on": date(2027, 1, 1),
            "results_existed": True,
            "reason": "the metric sheet came back at 0.6 and that is nearly good enough",
        }
    )
    with pytest.raises(ConfigError, match="must be signed, not slipped in"):
        _load_dict(tmp_path, raw)


def test_a_signed_post_hoc_change_is_permitted(tmp_path: Path, repo_root: Path) -> None:
    """It is the operator's call to make. The log's job is to make it undeniable, not to veto it."""
    raw = _valid_raw(repo_root)
    raw["objective"]["min_sharpe"] = 0.5
    raw["objective"]["min_sharpe_amendments"].append(
        {
            "value": 0.5,
            "set_on": date(2027, 1, 1),
            "results_existed": True,
            "acknowledged_post_hoc": True,
            "reason": "operator override with full knowledge that results were already seen",
        }
    )
    cfg = _load_dict(tmp_path, raw)
    assert cfg.objective.min_sharpe == 0.5
    assert cfg.objective.min_sharpe_amendments[-1].acknowledged_post_hoc is True
