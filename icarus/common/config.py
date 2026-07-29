"""Typed loader for ``goal.yaml`` — the single source of truth (PRD §15 + §39.3).

Fail-fast: a missing or mis-typed key raises at startup, never at trade time (task 0.2 AC).
``extra="forbid"`` means a typo'd key is an error, not a silently-ignored setting.

Some hard safety invariants are asserted **in config** here (not only in code) so a bad
edit to ``goal.yaml`` cannot loosen them — e.g. the crypto leverage ceiling can never exceed
2x (invariant #7 requires config AND code AND execution-time asserts).
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# Reusable constrained scalars.
_Fraction = Annotated[float, Field(ge=0.0, le=1.0)]
_Positive = Annotated[float, Field(gt=0.0)]
_PosInt = Annotated[int, Field(gt=0)]

# Hard ceiling from invariant #7 — the leverage cap NEVER loosens with tier.
CRYPTO_LEVERAGE_ABSOLUTE_CEILING = 2.0


class _Strict(BaseModel):
    """Base: immutable + reject unknown keys (catch typos in goal.yaml)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Objective(_Strict):
    account_currency: str
    target_return_30d: float
    max_drawdown: _Fraction
    min_sharpe: float
    min_sortino: float
    min_calmar: float
    min_profit_factor: float
    min_trades_oos: _PosInt
    min_rr: float
    oos_decay_max: _Fraction
    cost_stress_multiplier: _Positive
    dsr_confidence: _Fraction


class Learning(_Strict):
    reflection_every_trades: _PosInt
    one_change_per_cycle: bool
    invention_enabled: bool
    inventor_model: str
    inventor_model_hard: str
    sentiment_model: str


class Risk(_Strict):
    per_trade_risk_r: _Positive
    new_strategy_size_factor: _Fraction
    kelly_fraction_cap: _Fraction
    daily_loss_limit: _Fraction
    daily_derisk_trigger: _Fraction
    max_drawdown_killswitch: _Fraction
    max_open_positions: _PosInt
    max_portfolio_heat: _Fraction
    max_pairwise_correlation: _Fraction
    consecutive_loss_pause: _PosInt
    canary_min_trades: _PosInt
    canary_min_days: _PosInt
    cost_hurdle_multiplier: _Positive
    crypto_max_leverage_hard: _Positive
    crypto_max_leverage_seed: _Positive

    @model_validator(mode="after")
    def _enforce_leverage_ceiling(self) -> Risk:
        # Invariant #7: hard ceiling never exceeds 2x; seed cap never exceeds the hard cap.
        if self.crypto_max_leverage_hard > CRYPTO_LEVERAGE_ABSOLUTE_CEILING:
            raise ValueError(
                f"crypto_max_leverage_hard={self.crypto_max_leverage_hard} exceeds the absolute "
                f"ceiling {CRYPTO_LEVERAGE_ABSOLUTE_CEILING}x (invariant #7 — never loosens)"
            )
        if self.crypto_max_leverage_seed > self.crypto_max_leverage_hard:
            raise ValueError(
                f"crypto_max_leverage_seed={self.crypto_max_leverage_seed} exceeds hard cap "
                f"{self.crypto_max_leverage_hard}x"
            )
        # De-risk trigger must fire before the daily halt (ladder ordering, §14).
        if self.daily_derisk_trigger >= self.daily_loss_limit:
            raise ValueError(
                "daily_derisk_trigger must be < daily_loss_limit (de-risk before halt, §14)"
            )
        return self


class Compliance(_Strict):
    max_orders_per_sec: _PosInt
    max_orders_per_min: _PosInt
    max_orders_per_day: _PosInt
    white_box_only: bool
    static_ip_required: bool
    limit_orders_only: bool
    algo_id_tagging_required: bool

    @model_validator(mode="after")
    def _enforce_hard_compliance(self) -> Compliance:
        # These are safety invariants, not preferences: LIMIT-only (#5), white-box (§8),
        # algo-tagging (#6). A goal.yaml that turns them off is rejected.
        if not self.limit_orders_only:
            raise ValueError("limit_orders_only must be true (invariant #5 — NSE bars MARKET)")
        if not self.white_box_only:
            raise ValueError("white_box_only must be true (PRD §8 — no black-box strategies)")
        if not self.algo_id_tagging_required:
            raise ValueError("algo_id_tagging_required must be true (invariant #6)")
        # Order-rate governor stays well under the SEBI 10 OPS ceiling.
        if self.max_orders_per_sec > 2:
            raise ValueError("max_orders_per_sec must be <= 2 (PRD §11.5 order-rate governor)")
        return self


class Tax(_Strict):
    equity_intraday: str
    equity_delivery: str
    equity_fno: str
    crypto_inr_derivatives: str
    crypto_reclassification_stress: str
    operator_slab_rate: _Fraction


class Data(_Strict):
    timezone_storage: str
    equity_session: str
    point_in_time_universe: bool
    survivorship_control: bool
    corporate_action_adjust: str
    data_quality_gate: bool
    min_oos_calendar_span_days: _PosInt


class DataQuality(_Strict):
    """Thresholds for the Data-QA layer (task 1.1b, PRD §29.3-29.4).

    Config, not constants: a threshold buried in a helper cannot be reviewed, and these decide
    which bars the whole system is allowed to believe (CLAUDE.md §2).
    """

    atr_window: _PosInt
    max_bar_move_atr: _Positive
    max_single_bar_move: _Positive
    min_day_score: _Fraction
    stale_sessions_symbol_veto: _PosInt
    stale_plane_halt_ratio: _Fraction

    @model_validator(mode="after")
    def _thresholds_must_be_meaningful(self) -> DataQuality:
        # A quality gate that accepts everything is not a gate. Catch a well-meaning edit that
        # disables the layer by loosening it to a no-op rather than by turning it off.
        if self.max_single_bar_move >= 1.0:
            raise ValueError(
                "max_single_bar_move must be < 1.0 (a >=100% bar is always worth quarantining)"
            )
        if self.min_day_score == 0:
            raise ValueError("min_day_score must be > 0 (§29.4 — the gate reads this score)")
        return self


class Universe(_Strict):
    """Point-in-time tradable-universe policy (task 1.1c, PRD §29.1-29.3)."""

    min_avg_turnover_inr: _Positive
    turnover_window_sessions: _PosInt
    min_close_inr: _Positive
    dividend_convention: str
    history_years: _PosInt

    @model_validator(mode="after")
    def _enforce_universe_policy(self) -> Universe:
        # §29.3: one convention, applied identically in signal, cost and tax. Anything else means
        # the backtest and the tax model disagree about what a return is.
        if self.dividend_convention not in {"price_return", "total_return"}:
            raise ValueError(
                f"dividend_convention must be price_return or total_return, "
                f"got {self.dividend_convention!r} (§29.3)"
            )
        # The penny ban is an invariant (§29.2), not a preference: low-priced names cannot be
        # backtested honestly at this budget. _Positive already bars 0; this bars a token floor.
        if self.min_close_inr < 10:
            raise ValueError(
                f"min_close_inr={self.min_close_inr} effectively disables the penny-universe ban "
                f"(§29.2)"
            )
        return self


class ExecutionRealism(_Strict):
    fill_requires_trade_through: bool
    queue_volume_multiple_k: _Positive
    next_bar_execution: bool
    latency_ms: _PosInt
    model_partial_fills: bool
    max_participation_of_depth: _Fraction

    @model_validator(mode="after")
    def _enforce_realism_invariants(self) -> ExecutionRealism:
        # Touch != fill (#12) and next-bar execution (#13) are forbidden to disable.
        if not self.fill_requires_trade_through:
            raise ValueError("fill_requires_trade_through must be true (invariant #12)")
        if not self.next_bar_execution:
            raise ValueError("next_bar_execution must be true (invariant #13)")
        return self


class Overfitting(_Strict):
    lifetime_trial_ledger: bool
    cumulative_effective_n: bool
    haircut_method: str
    gate_on_sharpe_lower_bound: bool
    small_sample_shrinkage: bool
    lockbox_eval_budget: _PosInt
    lockbox_rotation_days: _PosInt
    benchmark_equity: str
    benchmark_crypto: str
    min_alpha_after_cost_tax: float
    max_benchmark_r2: _Fraction


class TradeQuality(_Strict):
    min_quality_score: _Fraction
    rank_select_top_k: _PosInt
    max_trades_per_day_per_strategy: _PosInt
    min_holding_bars: _PosInt


class Crypto(_Strict):
    accrue_funding: bool
    futures_roll_days_before_expiry: _PosInt
    expiry_buffer_hours: _PosInt
    options_enabled: bool

    @model_validator(mode="after")
    def _no_crypto_options(self) -> Crypto:
        # Invariant #20: no crypto options until the DSL models Greeks/theta/expiry.
        if self.options_enabled:
            raise ValueError(
                "options_enabled must be false (invariant #20 — no crypto options yet)"
            )
        return self


class Allocation(_Strict):
    max_concurrent_strategies: _PosInt
    allocation_method: str
    correlated_strategies_share_slot: bool


class Recovery(_Strict):
    startup_state: str
    three_way_reconcile: bool
    halt_on_unresolved: bool
    require_broker_side_stop: bool

    @model_validator(mode="after")
    def _recovery_before_trading(self) -> Recovery:
        # Invariant #16: RECOVERY before TRADING on every startup.
        if self.startup_state != "RECOVERY":
            raise ValueError("startup_state must be RECOVERY (invariant #16)")
        return self


class Resilience(_Strict):
    datastore_down_action: str
    bus_consumer_groups: bool
    bus_dead_letter: bool
    bus_maxlen_approx: _PosInt
    backup_interval_min: _PosInt
    cancel_on_disconnect: bool
    ntp_required: bool
    secondary_alert_channel: str

    @model_validator(mode="after")
    def _datastore_down_halts(self) -> Resilience:
        # Invariant #18: datastore-down with an open position is fail-safe-to-halt.
        if self.datastore_down_action != "halt":
            raise ValueError("datastore_down_action must be halt (invariant #18)")
        return self


class Observability(_Strict):
    heartbeat_interval_s: _PosInt
    heartbeat_miss_threshold: _PosInt
    data_staleness_equity_s: _PosInt
    data_staleness_crypto_s: _PosInt


class Auth(_Strict):
    daily_auth_mode: str
    equity_auth_failure_isolates_plane: bool

    @model_validator(mode="after")
    def _valid_auth_mode(self) -> Auth:
        if self.daily_auth_mode not in {"one_tap", "totp_auto"}:
            raise ValueError("daily_auth_mode must be one_tap or totp_auto (§38)")
        return self


class LearningBudgets(_Strict):
    max_candidates_per_day: _PosInt
    max_llm_spend_per_day_inr: _Positive
    research_never_preempts_live: bool
    thrash_guard_hours: _PosInt


class GoalConfig(_Strict):
    """Root config — every top-level block in goal.yaml, all required."""

    objective: Objective
    learning: Learning
    risk: Risk
    compliance: Compliance
    tax: Tax
    data: Data
    data_quality: DataQuality
    universe: Universe
    execution_realism: ExecutionRealism
    overfitting: Overfitting
    trade_quality: TradeQuality
    crypto: Crypto
    allocation: Allocation
    recovery: Recovery
    resilience: Resilience
    observability: Observability
    auth: Auth
    learning_budgets: LearningBudgets


class ConfigError(Exception):
    """Raised when goal.yaml is missing, malformed, or fails validation. Fail-fast at startup."""


def load_goal(path: str | Path = "goal.yaml") -> GoalConfig:
    """Load and validate ``goal.yaml``. Raises :class:`ConfigError` on any problem.

    This is called once at startup; a bad config must stop the process before any agent runs.
    """
    p = Path(path)
    if not p.exists():
        raise ConfigError(f"goal.yaml not found at {p!s}")
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigError(f"goal.yaml is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError("goal.yaml must be a mapping at the top level")
    try:
        return GoalConfig.model_validate(raw)
    except Exception as exc:  # pydantic ValidationError -> ConfigError with detail
        raise ConfigError(f"goal.yaml failed validation:\n{exc}") from exc
