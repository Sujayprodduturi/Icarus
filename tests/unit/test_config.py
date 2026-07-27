"""Tests for the goal.yaml loader (task 0.2): happy path + fail-fast on bad config."""

from __future__ import annotations

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
