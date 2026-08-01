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
