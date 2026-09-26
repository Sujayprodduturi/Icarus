"""Typed loader for ``goal.yaml`` — the single source of truth (PRD §15 + §39.3).

Fail-fast: a missing or mis-typed key raises at startup, never at trade time (task 0.2 AC).
``extra="forbid"`` means a typo'd key is an error, not a silently-ignored setting.

Some hard safety invariants are asserted **in config** here (not only in code) so a bad
edit to ``goal.yaml`` cannot loosen them — e.g. the crypto leverage ceiling can never exceed
2x (invariant #7 requires config AND code AND execution-time asserts).
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from itertools import pairwise
from pathlib import Path
from typing import Annotated

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

# Reusable constrained scalars.
_Fraction = Annotated[float, Field(ge=0.0, le=1.0)]
_Positive = Annotated[float, Field(gt=0.0)]
_NonNegative = Annotated[float, Field(ge=0.0)]
_PosInt = Annotated[int, Field(gt=0)]

# Hard ceiling from invariant #7 — the leverage cap NEVER loosens with tier.
CRYPTO_LEVERAGE_ABSOLUTE_CEILING = 2.0

# The loosest settings the kill-switch ladder may take. Config may be **stricter** — a smaller
# number halts sooner — and never looser. Same shape as the leverage ceiling above and for the same
# reason: invariant #4 says hard risk limits cannot be overridden by any strategy or by the learning
# loop, and until 2026-08-16 that was true of strategies and false of a one-line edit to goal.yaml.
# A review demonstrated it by loading `max_drawdown_killswitch: 1.00` cleanly (finding F36).
# Values are the ones CLAUDE.md §0 #23 and §4 name, pinned in code so re-dating goal.yaml cannot
# launder a loosened one.
_DAILY_LOSS_LIMIT_CEILING = 0.03  # invariant #23 — -3% halts new entries for the day
_DAILY_DERISK_CEILING = 0.015  # CLAUDE.md §4 — -1.5% halves all sizing
_MAX_DRAWDOWN_KILLSWITCH_CEILING = 0.10  # invariant #23 — -10%, operator-only restart
# The first pass bounded three rungs and left the rest of the block open, which is the same hole
# in a quieter place: each of these also loaded at a value that switched the control off.
_KELLY_FRACTION_CEILING = 0.5  # CLAUDE.md §4 — "min(1/4-1/2 Kelly, ...)"; 1.0 is full Kelly
_CANARY_SIZE_FACTOR_CEILING = 0.25  # CLAUDE.md §4 — canary runs at 25%; 1.0 is no canary
_PER_TRADE_RISK_CEILING = 0.005  # PRD §15 — 0.5% per trade; tiers scale it *down*
_PORTFOLIO_HEAT_CEILING = 0.02  # PRD §15 — 2% of equity at risk across the whole book
_STAGNATION_CHECK_CEILING = 50  # invariant #23 — a larger number defers the halt indefinitely
# Operator decision D11, 2026-08-17 (finding F34). Risk-based sizing bounds the *loss if the stop
# holds*; it says nothing about position **value**, because stop distance cancels out of it. A
# tight stop therefore buys an arbitrarily large position at the same nominal risk — and a stop is
# not a guarantee overnight, where a large share of the NSE move happens. The account-level
# arithmetic is what fixes the ceiling: at 50% of the book in one name, a 20% lower circuit is a
# 10% account loss, which is the `max_drawdown_killswitch` — one name, one morning, operator-only
# restart. So 0.50 is the loosest setting the code will accept, and `goal.yaml` runs at 0.25.
_MAX_POSITION_PCT_CEILING = 0.50

# Statutory rates, as of FY 2026-27 (PRD §7). Config may assume a **harsher** rate than the statute
# — a stress scenario is allowed to overstate the bill — but never a cheaper one, which would
# flatter after-tax P&L. `vda_flat_rate` is the sharpest: it exists only to make the
# reclassification stress bite, and a zero there would make the mandated stress scenario tax-free.
_STCG_RATE_STATUTORY = 0.20
_LTCG_RATE_STATUTORY = 0.125
_VDA_FLAT_RATE_STATUTORY = 0.30
_CESS_RATE_STATUTORY = 0.04  # health & education cess, fixed by statute
# The marginal slab is genuinely personal — an operator in a lower bracket may set a smaller one —
# so this is the lowest *non-zero* slab the regime has rather than the top rate. The old check was
# only `> 0`, under which 0.0001 loaded and made every business-income strategy effectively
# tax-free, which is precisely what the VDA floor above exists to stop, aimed at the equity
# business-income stress the gate requires.
_LOWEST_SLAB_RATE = 0.05

# Statutory LTCG exemption ceiling, s.112A equivalent (verified 2026-07-30, unchanged by Budget
# 2026). Config may set LESS (the operator's other holdings may already consume it) but never more.
_LTCG_EXEMPTION_STATUTORY_CEILING_INR = 125_000.0

# The date the Phase-1 stop gate was fixed, before any backtest existed. Pinned in CODE rather
# than read from config so that re-dating the block in goal.yaml fails at startup instead of
# quietly laundering a lowered bar (LLM council finding, 2026-07-31).
_STOP_GATE_PRE_REGISTERED_ON = date(2026, 8, 1)
LOCKBOX_START = date(2023, 1, 1)
_BACKTEST_REGISTERED_ON = date(2026, 8, 5)
_SIGNAL_TEST_REGISTERED_ON = date(2026, 8, 22)
_SIGNAL_TEST_NOTIONAL_INR = 100_000
_SIGNAL_TEST_STATISTICS_REGISTERED_ON = date(2026, 9, 24)
_SIGNAL_TEST_BLOCK_MIN_SESSIONS = 63
_SIGNAL_TEST_HOLDING_PERIOD_BLOCK_MULTIPLIER = 3
_SIGNAL_TEST_CI_LEVEL = 0.95
_SIGNAL_TEST_PLACEBO_PERMUTATIONS = 4_999
_SIGNAL_TEST_RNG_SEED = 20_260_924


class _Strict(BaseModel):
    """Base: immutable + reject unknown keys (catch typos in goal.yaml)."""

    model_config = ConfigDict(frozen=True, extra="forbid")


class Amendment(_Strict):
    """One dated decision about a number that is allowed to move.

    Written for ``objective.min_sharpe`` and reused since for any threshold that must stay
    live-editable without being able to pretend it was always there (invariant #25).

    O8 was left open specifically so the figure could be settled *before* any metric sheet
    existed, and the operator asked (2026-08-02) that it stay changeable afterwards. Both are
    honoured by making the value append-only rather than frozen: the bar may move, but a move
    leaves a permanent, dated, reasoned record, so a future reader can always tell whether it
    moved before or after the results were known.

    ``acknowledged_post_hoc`` is the one piece of deliberate friction. Lowering a threshold after
    seeing a disappointing result is precisely the rationalisation invariant #25 exists to stop,
    and it is *always* defensible in the moment ("the window was unusual", "it's nearly positive").
    Requiring the operator to write that admission into the file does not prevent the change — it
    prevents the change from being invisible, which is the part that actually causes harm.
    """

    value: float
    set_on: date
    results_existed: bool
    reason: str
    acknowledged_post_hoc: bool = False

    @model_validator(mode="after")
    def _post_hoc_changes_must_be_signed(self) -> Amendment:
        if self.results_existed and not self.acknowledged_post_hoc:
            raise ValueError(
                f"the amendment on {self.set_on} declares results_existed: true but not "
                f"acknowledged_post_hoc: true. Changing a number after seeing a result is allowed, "
                f"but it must be signed, not slipped in (invariant #25)."
            )
        return self


def assert_traceable(live: float, history: Sequence[Amendment], name: str) -> None:
    """The live figure must be the newest recorded decision, and the record must be sane.

    Without this the amendment log would be decorative: someone could edit the value and leave the
    history untouched, which is worse than having no log at all — it would assert a provenance that
    is false.

    One function rather than one per field, because this is the mechanism invariant #25 prescribes
    for *any* threshold that has to stay live-editable, and a rule with two homes is a rule that can
    drift apart.
    """
    if not history:
        raise ValueError(
            f"{name}_amendments is empty — the live {name} must be traceable to a dated decision"
        )
    dates = [entry.set_on for entry in history]
    # Strictly increasing, not merely sorted. Two entries on the same day have no defined order,
    # so `history[-1]` becomes whichever the operator happened to list last and the same file
    # validates against two different live values.
    if any(b <= a for a, b in pairwise(dates)):
        raise ValueError(
            f"{name}_amendments must be in strictly increasing date order, got {dates}"
        )
    if history[-1].value != live:
        raise ValueError(
            f"{name} is {live} but the latest amendment ({history[-1].set_on}) records "
            f"{history[-1].value} — edit the log, not just the value, or the history is a fiction"
        )


class Objective(_Strict):
    account_currency: str
    target_return_30d: float
    max_drawdown: _Fraction
    min_sharpe: float
    min_sharpe_amendments: tuple[Amendment, ...]
    min_sortino: float
    min_calmar: float
    min_profit_factor: float
    min_trades_oos: _PosInt
    min_rr: float
    oos_decay_max: _Fraction
    cost_stress_multiplier: _Positive
    dsr_confidence: _Fraction

    @model_validator(mode="after")
    def _min_sharpe_matches_its_history(self) -> Objective:
        """The live figure must be the most recent recorded decision, and the record must be sane.

        Without this the amendment log would be decorative: someone could edit ``min_sharpe`` and
        leave the history untouched, which is worse than having no log at all — it would assert a
        provenance that is false.
        """
        assert_traceable(self.min_sharpe, self.min_sharpe_amendments, "objective.min_sharpe")
        return self


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
    max_position_pct_of_equity: _Fraction
    """Most of the account one symbol may take **at entry**, by value (finding F34, decision D11).

    Not a duplicate of the heat cap. Heat bounds the loss *if the stop holds*, and stop distance
    cancels out of it — every position is exactly ``risk_r`` of the book however large it is. This
    bounds what is exposed when the stop does **not** hold, which overnight it frequently does not.
    It is the fourth term in the ``min(...)`` CLAUDE.md §4 defines sizing to be, so it reduces a
    position rather than refusing it.

    **"At entry" is load-bearing and was corrected on 2026-08-17 after a code review.** This first
    read "most of the account one symbol may hold", which is a claim about *state* that the code
    does not make: nothing re-checks or trims a position afterwards, so a winner that runs is free
    to drift past the cap. Measured on a name compounding 5x, a position entered at 25% reaches
    **61% of a mark-to-market book by bar 58** — where a 20% lower circuit is a 12% account hit,
    past the `max_drawdown_killswitch` that the 0.25 was chosen to stay inside. Whether a standing
    cap should trim winners is a real trading decision with cost and tax consequences, so it is
    **finding F45**, open, and not settled here. What this field promises is the entry bound."""
    max_pairwise_correlation: _Fraction
    consecutive_loss_pause: _PosInt
    canary_min_trades: _PosInt
    canary_min_days: _PosInt
    cost_hurdle_multiplier: _Positive
    crypto_max_leverage_hard: _Positive
    crypto_max_leverage_seed: _Positive
    stagnation_check_after_trades: _PosInt
    stagnation_requires_positive_net: bool
    stagnation_ci_level: _Fraction

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
        # Each rung of the ladder has a loosest permissible setting, pinned in code. Without these
        # the ordering check below was the *only* constraint, and it is satisfied by
        # `daily_derisk_trigger: 0.99, daily_loss_limit: 1.00` — an ordered ladder with no rungs.
        for name, ceiling in (
            ("daily_loss_limit", _DAILY_LOSS_LIMIT_CEILING),
            ("daily_derisk_trigger", _DAILY_DERISK_CEILING),
            ("max_drawdown_killswitch", _MAX_DRAWDOWN_KILLSWITCH_CEILING),
            ("kelly_fraction_cap", _KELLY_FRACTION_CEILING),
            ("new_strategy_size_factor", _CANARY_SIZE_FACTOR_CEILING),
            ("per_trade_risk_r", _PER_TRADE_RISK_CEILING),
            ("max_portfolio_heat", _PORTFOLIO_HEAT_CEILING),
            ("max_position_pct_of_equity", _MAX_POSITION_PCT_CEILING),
            ("stagnation_check_after_trades", _STAGNATION_CHECK_CEILING),
        ):
            value = getattr(self, name)
            if value > ceiling:
                raise ValueError(
                    f"risk.{name}={value} is looser than the {ceiling} CLAUDE.md §0 fixes for it. "
                    f"A stricter value (smaller, halting sooner) is allowed; a looser one is a "
                    f"kill-switch edited into not being one (invariant #4)."
                )
            if value <= 0:
                raise ValueError(f"risk.{name} must be > 0 — zero disables the halt entirely")
        # De-risk trigger must fire before the daily halt (ladder ordering, §14).
        if self.daily_derisk_trigger >= self.daily_loss_limit:
            raise ValueError(
                "daily_derisk_trigger must be < daily_loss_limit (de-risk before halt, §14)"
            )
        # Position count and heat cap are two controls over the same quantity and can silently
        # disagree. Filling every slot at full per-trade risk must not breach the heat budget.
        implied_heat = self.max_open_positions * self.per_trade_risk_r
        if implied_heat > self.max_portfolio_heat:
            raise ValueError(
                f"max_open_positions={self.max_open_positions} x per_trade_risk_r="
                f"{self.per_trade_risk_r} = {implied_heat:.4f} heat, which exceeds "
                f"max_portfolio_heat={self.max_portfolio_heat} (§14 — the heat cap is the "
                f"binding control; a full book may not breach it)"
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
    """Tax rates + classification policy (task 1.6, PRD §6).

    The classification keys are **settled law**, not preferences, so they are asserted here rather
    than merely typed: a well-meaning edit must not be able to move income into a cheaper bucket
    than the statute allows. ``equity_delivery`` is the one genuine choice (§6.1).
    """

    equity_intraday: str
    equity_delivery: str
    equity_fno: str
    crypto_inr_derivatives: str
    crypto_reclassification_stress: str
    operator_slab_rate: _Fraction
    cess_rate: _Fraction
    stcg_rate: _Fraction
    ltcg_rate: _Fraction
    ltcg_exemption_inr: _NonNegative
    ltcg_holding_months: _PosInt
    vda_flat_rate: _Fraction
    carry_forward_years_speculative: _PosInt
    carry_forward_years_nonspeculative: _PosInt
    carry_forward_years_capital: _PosInt

    @model_validator(mode="after")
    def _classifications_match_the_statute(self) -> Tax:
        settled = {
            "equity_intraday": "speculative_business",
            "equity_fno": "nonspeculative_business",
            "crypto_inr_derivatives": "speculative_business",
            "crypto_reclassification_stress": "vda_30_flat",
        }
        for key, lawful in settled.items():
            if getattr(self, key) != lawful:
                raise ValueError(
                    f"tax.{key} must be {lawful!r} (settled law / PRD §6 — not a tunable); "
                    f"got {getattr(self, key)!r}"
                )
        if self.equity_delivery not in {"nonspeculative_business", "capital_gains"}:
            raise ValueError(
                f"tax.equity_delivery must be 'nonspeculative_business' or 'capital_gains' "
                f"(§6.1 per-classification), got {self.equity_delivery!r}"
            )
        # A zero slab rate would make every business-income strategy look tax-free. §6 requires a
        # conservative default precisely so the gate is not flattered by an optimistic slab.
        if self.operator_slab_rate < _LOWEST_SLAB_RATE:
            raise ValueError(
                f"tax.operator_slab_rate={self.operator_slab_rate} is below the lowest non-zero "
                f"slab ({_LOWEST_SLAB_RATE}). The old check was only '> 0', under which 0.0001 "
                f"loaded and made every business-income strategy effectively tax-free "
                f"(§6: never flatter the gate)."
            )
        # The same reasoning, applied to the three rates it was never applied to. `vda_flat_rate: 0`
        # loaded cleanly until 2026-08-16 and made the mandated VDA reclassification stress
        # tax-free, so a crypto strategy surviving only the optimistic reading would have passed
        # the very scenario built to catch it (finding F36).
        for name, statutory in (
            ("stcg_rate", _STCG_RATE_STATUTORY),
            ("ltcg_rate", _LTCG_RATE_STATUTORY),
            ("vda_flat_rate", _VDA_FLAT_RATE_STATUTORY),
            ("cess_rate", _CESS_RATE_STATUTORY),
        ):
            value = getattr(self, name)
            if value < statutory:
                raise ValueError(
                    f"tax.{name}={value} is below the statutory {statutory}. Assuming a harsher "
                    f"rate is allowed — a stress scenario may overstate the bill — but a cheaper "
                    f"one understates tax on every trade and flatters the gate (§6)."
                )
        if self.ltcg_exemption_inr > _LTCG_EXEMPTION_STATUTORY_CEILING_INR:
            raise ValueError(
                f"tax.ltcg_exemption_inr={self.ltcg_exemption_inr} exceeds the statutory "
                f"Rs {_LTCG_EXEMPTION_STATUTORY_CEILING_INR:,.0f}/year (verified 2026-07-30)"
            )
        return self


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


class SegmentSchedule(_Strict):
    """The charge schedule for one tradable segment (task 1.5, PRD §7.1).

    ``brokerage = brokerage_flat_inr + min(brokerage_pct x turnover, brokerage_cap_inr)`` — one
    formula covering all three real shapes: zero (delivery), lower-of (intraday/futures), and
    flat-per-order (options).
    """

    brokerage_flat_inr: _NonNegative
    brokerage_pct: _NonNegative
    brokerage_cap_inr: _NonNegative
    stt_buy_pct: _NonNegative
    stt_sell_pct: _NonNegative
    exchange_txn_pct: _NonNegative
    stamp_buy_pct: _NonNegative
    dp_charge_on_sell: bool

    @model_validator(mode="after")
    def _percentage_brokerage_needs_a_cap(self) -> SegmentSchedule:
        # A percentage brokerage with a zero cap silently computes to zero brokerage on every
        # trade — free trading is exactly the kind of "wrong in our favour" default that makes a
        # backtest look profitable. Force the cap to be stated.
        if self.brokerage_pct > 0 and self.brokerage_cap_inr <= 0:
            raise ValueError(
                "brokerage_pct > 0 requires brokerage_cap_inr > 0 (the 'or Rs 20/order, whichever "
                "lower' cap); a zero cap would zero out brokerage entirely"
            )
        return self


class SegmentSchedules(_Strict):
    """One schedule per segment. Named fields, not a dict, so pydantic itself enforces that all
    four are present and that a typo'd segment name is an error — no hand-written validator, and
    no import of :mod:`icarus.engine` from ``common`` to check the names against.

    ``test_costmodel`` asserts these field names stay in step with ``costmodel.Segment``.
    """

    equity_delivery: SegmentSchedule
    equity_intraday: SegmentSchedule
    equity_futures: SegmentSchedule
    equity_options: SegmentSchedule


class Costs(_Strict):
    """Statutory + broker charges (task 1.5, PRD §7).

    Charges only. Slippage and fill probability belong to the execution/fill model (§30.1) so
    the two are never double-counted.
    """

    gst_rate: _Fraction
    sebi_turnover_pct: _NonNegative
    dp_charge_inr: _NonNegative
    segments: SegmentSchedules


class ExecutionRealism(_Strict):
    fill_requires_trade_through: bool
    queue_volume_multiple_k: _Positive
    next_bar_execution: bool
    latency_ms: _PosInt
    model_partial_fills: bool
    max_participation_of_depth: _Fraction
    slippage_bps: _Positive
    tick_size_inr: _Positive

    @model_validator(mode="after")
    def _enforce_realism_invariants(self) -> ExecutionRealism:
        # Touch != fill (#12) and next-bar execution (#13) are forbidden to disable.
        if not self.fill_requires_trade_through:
            raise ValueError("fill_requires_trade_through must be true (invariant #12)")
        if not self.next_bar_execution:
            raise ValueError("next_bar_execution must be true (invariant #13)")
        # Zero slippage is the same class of lie as touch-equals-fill: it says a marketable order
        # crosses the spread for free. `_Positive` already excludes zero; this states why.
        if self.slippage_bps <= 0:
            raise ValueError("slippage_bps must be positive — a free spread is not a market")
        return self


class Overfitting(_Strict):
    lifetime_trial_ledger: bool
    cumulative_effective_n: bool
    haircut_method: str
    gate_on_sharpe_lower_bound: bool
    small_sample_shrinkage: bool
    lockbox_rotation_days: _PosInt
    benchmark_equity: str
    benchmark_crypto: str
    min_alpha_after_cost_tax: float
    max_benchmark_r2: _Fraction


class TradeQuality(_Strict):
    """Live-trading throttles for the Risk agent (task 2.1). **Nothing reads them yet.**

    ``min_quality_score`` and ``rank_select_top_k`` were removed on 2026-08-16: they described a
    per-signal quality score that exists nowhere in the codebase and never has (finding F37).
    """

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


class StopGate(_Strict):
    """The pre-registered Phase-1 falsification criteria (operator, 2026-08-01).

    These were fixed **before any backtest existed**, which is the only thing that gives them
    force: a threshold written after seeing results is a rationalisation. The loader asserts the
    pre-registration date has not been quietly moved forward, because silently re-dating this
    block would be the easiest way to launder a lowered bar.
    """

    pre_registered_on: date
    require_sharpe_lower_bound_above: float
    require_sharpe_lower_bound_above_amendments: tuple[Amendment, ...]
    """The date above pins *when* the gate was set; this pins *what it has ever been*.

    Until 2026-08-16 the block asserted an immutable ``pre_registered_on`` while every threshold
    under it stayed freely editable — so ``require_sharpe_lower_bound_above: 0.0 -> -5.0`` loaded
    cleanly and the file still claimed a 2026-08-01 provenance. That is precisely the "assert a
    provenance that is false" failure :func:`assert_traceable` was written to prevent, sitting on
    the gate itself (finding F36). The two thresholds that are judgement rather than statute get
    the same append-only log as ``objective.min_sharpe``; the rest are bounded or derived.
    """

    sharpe_confidence_level: _Fraction
    net_of_cost_and_tax: bool
    max_pbo: _Fraction
    max_pbo_amendments: tuple[Amendment, ...]
    trade_count_promote: _PosInt
    trade_count_needs_more_data: _PosInt
    min_oos_calendar_years: _Positive
    require_benchmark_drawdown_pct: _Fraction
    require_crypto_vda_stress: bool
    require_equity_business_income_stress: bool

    @model_validator(mode="after")
    def _gate_is_coherent(self) -> StopGate:
        if self.pre_registered_on != _STOP_GATE_PRE_REGISTERED_ON:
            raise ValueError(
                f"stop_gate.pre_registered_on must remain {_STOP_GATE_PRE_REGISTERED_ON} — the "
                f"date is the commitment. Got {self.pre_registered_on}. If the gate genuinely "
                f"must change, record why and what was already known when it changed."
            )
        if self.trade_count_needs_more_data >= self.trade_count_promote:
            raise ValueError(
                "stop_gate.trade_count_needs_more_data must be < trade_count_promote "
                "(NEEDS_MORE_DATA is the band below PROMOTE, not above it)"
            )
        if not self.net_of_cost_and_tax:
            raise ValueError(
                "stop_gate.net_of_cost_and_tax cannot be false — gross-only metrics are a bug "
                "(CLAUDE.md §5), not a configuration choice"
            )
        # A bound **and** a log, not one or the other. The log alone was the first attempt, and it
        # is weaker here than it is for `objective.min_sharpe`: that number is editable because the
        # operator asked for it to be (2026-08-02), whereas this block's own header says the gate
        # is not renegotiated once results are seen — and results have existed since 2026-08-07.
        # With only a log, `-5.0` still loads for anyone willing to append a signed amendment.
        # The floor is the weakest defensible gate rather than the current value, so the log still
        # has room to record a genuine tightening.
        if self.require_sharpe_lower_bound_above < 0.0:
            raise ValueError(
                f"stop_gate.require_sharpe_lower_bound_above={self.require_sharpe_lower_bound_above}"
                f" is below zero, which admits a strategy whose confidence interval includes losing"
                f" money. Stricter is allowed; this is not a threshold, it is the absence of one."
            )
        if self.max_pbo > 0.50:
            raise ValueError(
                f"stop_gate.max_pbo={self.max_pbo} exceeds 0.50. Above a half, the "
                f"backtest-best strategy is worse than a coin flip out of sample — the boundary is "
                f"the concept's own, not a tuned number."
            )
        assert_traceable(
            self.require_sharpe_lower_bound_above,
            self.require_sharpe_lower_bound_above_amendments,
            "stop_gate.require_sharpe_lower_bound_above",
        )
        assert_traceable(self.max_pbo, self.max_pbo_amendments, "stop_gate.max_pbo")
        return self


class DataSplit(_Strict):
    """Point-in-time train/validate/lockbox boundaries (operator, 2026-08-01).

    ``lockbox_end: null`` means open-ended — everything at or after ``lockbox_start``.
    """

    walk_forward_start: date
    walk_forward_end: date
    lockbox_start: date
    lockbox_end: date | None
    lockbox_uses_allowed: _PosInt

    @model_validator(mode="after")
    def _windows_do_not_overlap(self) -> DataSplit:
        if self.lockbox_start != LOCKBOX_START:
            raise ValueError(
                f"data_split.lockbox_start must remain {LOCKBOX_START} — moving the fixed boundary "
                f"turns held-out data into development data. Got {self.lockbox_start}."
            )
        # An overlap silently turns the lockbox into training data — the exact failure the
        # single-use rule exists to prevent, and one that leaves no trace in any metric.
        if self.walk_forward_end >= self.lockbox_start:
            raise ValueError(
                f"data_split.walk_forward_end ({self.walk_forward_end}) must be strictly before "
                f"lockbox_start ({self.lockbox_start}) — an overlap contaminates the lockbox"
            )
        if self.walk_forward_start >= self.walk_forward_end:
            raise ValueError("data_split.walk_forward_start must precede walk_forward_end")
        if self.lockbox_end is not None and self.lockbox_end <= self.lockbox_start:
            raise ValueError("data_split.lockbox_end must be after lockbox_start, or null")
        if self.lockbox_uses_allowed != 1:
            raise ValueError(
                "data_split.lockbox_uses_allowed must be 1 (PRD §13: the lockbox is consumed "
                "exactly once; a second look makes it training data)"
            )
        return self


class Backtest(_Strict):
    """Walk-forward window shape (task 1.7, pre-registered 2026-08-05).

    Pre-registered for the same reason the stop gate is, and the reasoning is identical: window
    shape moves results, so choosing it after seeing a number is choosing the number. A three-year
    minimum train window and a one-year test are ordinary choices — the point is that they were
    ordinary choices made *before* anything had been measured.

    Note what is **not** here: the purge gap. It is derived per strategy from that strategy's own
    longest lookback, because a 252-day word leaks 252 days across each seam and a 20-day word
    leaks 20. A single constant would be too small for one and wasteful for the other, and the
    too-small case leaks silently.
    """

    registered: date
    min_train_years: _Positive
    test_window_years: _Positive
    step_years: _Positive
    seam_sessions: _PosInt
    """Sessions left empty between the end of training and the start of each test window.

    Renamed from ``embargo_sessions`` on 2026-08-17 (finding F40) because neither that name nor the
    per-strategy ``purge`` it was added to described what the code does. The textbook embargo sits
    *after* a test window and keeps it out of later folds' training; this gap sits *before* one.
    Calling it a seam says what it is. **The value did not change** — the number here is the one
    that was set before any result existed. See :func:`icarus.engine.backtest.walk_forward_windows`
    for why a fitting-free walk-forward needs no purge at all."""
    starting_equity_inr: _Positive
    stale_position_sessions: _PosInt
    """Sessions a held symbol may print no bar before the position is written off (finding F4).

    **Carries its own amendment log rather than riding on this block's ``registered`` date.** The
    first version of this field simply sat here, with a comment arguing that neither direction
    flatters a result. That argument was wrong, and this task's own test disproves it: writing a
    dead holding off sooner frees a slot sooner, and in a book that discards 94-99.99% of its
    signals for want of one, that changes which later signals are taken and therefore the result.
    So it is result-affecting and editable — exactly the shape invariant #25 covers — and leaving
    it inside a block whose ``registered`` date the loader pins would let it borrow a provenance
    from 2026-08-05 that it does not have.
    """

    stale_position_sessions_amendments: tuple[Amendment, ...]

    @model_validator(mode="after")
    def _registration_holds(self) -> Backtest:
        if self.registered != _BACKTEST_REGISTERED_ON:
            raise ValueError(
                f"backtest.registered must remain {_BACKTEST_REGISTERED_ON} — the date is the "
                f"commitment, exactly as it is for stop_gate. Got {self.registered}."
            )
        if self.step_years > self.test_window_years:
            raise ValueError(
                "backtest.step_years must not exceed test_window_years — a step wider than the "
                "window skips calendar time, and the skipped years are out-of-sample data that "
                "silently never gets tested"
            )
        assert_traceable(
            self.stale_position_sessions,
            self.stale_position_sessions_amendments,
            "backtest.stale_position_sessions",
        )
        return self


class SignalTest(_Strict):
    """D15's pre-registered, non-promoting signal-diagnostic contract.

    The statistical choices are provisional diagnostics fixed before any real-data evaluation;
    they do not change the promotion or stagnation gates. Inferential output remains disabled
    through synthetic-only Step 6a/6b work. Enabling it requires a later dated, separately reviewed
    change after the trial ledger, time matcher, F48 same-day delivery-DP-fee cost correction,
    and source-specific matching rule pass.
    """

    registered: date
    statistics_registered: date
    notional_inr: _PosInt
    one_position_per_symbol: bool
    apply_costs: bool
    apply_tax: bool
    diagnostic_only: bool
    block_min_sessions: _PosInt
    holding_period_block_multiplier: _PosInt
    ci_level: _Fraction
    placebo_permutations: _PosInt
    rng_seed: _PosInt
    inference_enabled: bool

    @model_validator(mode="after")
    def _pre_registered_contract_holds(self) -> SignalTest:
        if self.registered != _SIGNAL_TEST_REGISTERED_ON:
            raise ValueError(
                f"signal_test.registered must remain {_SIGNAL_TEST_REGISTERED_ON} — D15 fixed "
                "the diagnostic before any result existed"
            )
        if self.notional_inr != _SIGNAL_TEST_NOTIONAL_INR:
            raise ValueError(
                f"signal_test.notional_inr must remain {_SIGNAL_TEST_NOTIONAL_INR} — D15(b) fixed "
                "the uniform notional before any result existed"
            )
        if not self.one_position_per_symbol:
            raise ValueError(
                "signal_test.one_position_per_symbol must be true — overlapping entries count one "
                "market event as multiple observations"
            )
        if not self.apply_costs:
            raise ValueError("signal_test.apply_costs must be true — gross-only results are a bug")
        if self.apply_tax:
            raise ValueError(
                "signal_test.apply_tax must be false — D15(c) defines a net-of-cost, before-tax "
                "diagnostic because this mode has no account-level tax ledger"
            )
        if not self.diagnostic_only:
            raise ValueError(
                "signal_test.diagnostic_only must be true — a signal test is never a promotion gate"
            )
        fixed_statistics: tuple[tuple[str, object, object], ...] = (
            (
                "statistics_registered",
                self.statistics_registered,
                _SIGNAL_TEST_STATISTICS_REGISTERED_ON,
            ),
            ("block_min_sessions", self.block_min_sessions, _SIGNAL_TEST_BLOCK_MIN_SESSIONS),
            (
                "holding_period_block_multiplier",
                self.holding_period_block_multiplier,
                _SIGNAL_TEST_HOLDING_PERIOD_BLOCK_MULTIPLIER,
            ),
            ("ci_level", self.ci_level, _SIGNAL_TEST_CI_LEVEL),
            (
                "placebo_permutations",
                self.placebo_permutations,
                _SIGNAL_TEST_PLACEBO_PERMUTATIONS,
            ),
            ("rng_seed", self.rng_seed, _SIGNAL_TEST_RNG_SEED),
        )
        for field_name, actual, expected in fixed_statistics:
            if actual != expected:
                raise ValueError(
                    f"signal_test.{field_name} must remain {expected!s} — provisional diagnostic "
                    "settings were fixed before any real-data evaluation"
                )
        if self.inference_enabled:
            raise ValueError(
                "signal_test.inference_enabled must remain false through synthetic-only Step "
                "6a/6b; a later dated, separately reviewed change also requires the trial ledger, "
                "time matcher, F48 same-day delivery-DP-fee cost correction, and source-specific "
                "matching rule to pass"
            )
        return self


class GoalConfig(_Strict):
    """Root config — every top-level block in goal.yaml, all required."""

    objective: Objective
    stop_gate: StopGate
    data_split: DataSplit
    backtest: Backtest
    signal_test: SignalTest
    learning: Learning
    risk: Risk
    compliance: Compliance
    tax: Tax
    data: Data
    data_quality: DataQuality
    universe: Universe
    costs: Costs
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
