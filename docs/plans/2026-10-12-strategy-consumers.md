# Strategy consumers: opposite exit and scheduled rebalance

**Status:** implementation plan under operator decision D47. This plan authorizes artificial
mechanics work only. F48 delivery-fee accounting is built first; then this work may proceed without
another routine approval pause. Real market data, the lockbox, actual trial-ledger activation,
inference, brokers and live orders remain outside scope.

## Outcome

Add the two missing consumers without changing any existing strategy's behavior:

1. a close-bar exit condition that is latched and first attempts a marketable LIMIT on the next
   source session; and
2. a whole-source, 63-session rebalance schedule that retains qualifying incumbents and trades
   membership changes on the next source session.

Both SignalSimulator and PortfolioSimulator use the same decision/fill contract. Existing stops,
targets, trailing stops, time stops and end-of-span behavior stay byte-for-byte/behaviorally
unchanged unless a new card opts into a new consumer.

## Exact cards to materialize

`strategies/donchian_55_20.yaml` (`donchian_55_20@1`): daily `nse_liquid`; entry
`donchian_breakout_up(n=55,basis=close)`; no `rank_by`; exits are
`stop_loss_atr(atr_mult=3.0,atr_period=14)` then
`opposite_signal(event=donchian_breakout_down(n=20,basis=close))`; `risk_r=0.005`,
`equal_weight`. The 3x ATR(14) stop is a project-owned pre-registration choice consistent with
the existing momentum cards, not a literature optimum. If more candidates fire than four slots,
the existing symbol-order fallback and ambiguity counter remain the declared behavior.

`strategies/defensive_low_vol_252_q63.yaml` (`defensive_low_vol_252_q63@1`): daily `nse_liquid`;
entry `xs_bottom_n(expr=realized_vol(n=252),n=30,min_symbols=31)`; rank new admissions by
`negate(series=realized_vol(n=252))`; rebalance every 63 whole-source sessions anchored at source
index 0; exit `stop_loss_atr(atr_mult=3.0,atr_period=14)`; `risk_r=0.005`, `equal_weight`.
This is an Icarus equal-stop-risk, at-most-four-holding adaptation using a 30-name candidate
cohort. It is not the NSE index's inverse-volatility weighted 30-stock portfolio.

Any later parameter, universe, rank, stop, schedule or tie-policy change is a new version and a
new counted trial. Neither new YAML is evaluated on market data in this task.

## Frozen behavior

- Donchian comparisons are strict and fresh-crossing events: close newly above the prior 55-session
  high enters; close newly below the prior 20-session low latches an exit. A close decision at `t`
  cannot use any `t+1` OHLCV and cannot fill on `t`; its first execution bar is `t+1`.
- `opposite_signal` is evaluated once over the complete development panel, then sliced with folds.
  Its 20-session history never restarts at a fold boundary. `primitives_used()` and
  `longest_lookback()` include the nested exit event.
- A close-triggered exit stores its own decision timestamp and full-source index. It must not reuse
  the entry decision timestamp used by resting protective orders. Once latched, a later false
  event does not cancel it.
- On every execution bar, the existing protective/time/final ladder wins. If it emits an intent,
  filled, partial or unfilled, the pending opposite/rebalance exit gets no second attempt on that
  symbol/bar: two FillModel calls could spend the same participation budget twice. A still-open
  pending remainder retries only on a later bar; it remains protected until flat. Costs attach
  only to real fill fragments.
- The low-vol schedule is computed before any fold slice. Source indices `252, 315, 378, ...` are
  the candidate decision grid; 252 is the first grid point at which a 252-return volatility can
  be known. A fold beginning elsewhere takes the next member of this grid; it never resets 63.
- Each scheduled decision needs at least 31 finite, point-in-time tradable scores and exactly 30
  selected names. Existing average-rank ties may return fewer or more than 30; either result is an
  explicit `CARDINALITY_MISMATCH` refusal. A thin/non-finite cohort is `COHORT_UNAVAILABLE`.
- A refused rebalance records a typed event and leaves the book unchanged. It never interprets an
  unavailable cohort as an empty target and liquidates incumbents. The grid does not slide after a
  refusal.
- A valid rebalance retains incumbents still in the 30-name target with no sale, repurchase or
  quarterly resize. Removed incumbents receive pending next-bar exits. Lowest volatility ranks
  new admissions; actual freed slots, heat, cash, concentration, whole shares and fill capacity
  still decide what can enter.
- New rebalance admissions are one-shot next-bar attempts. Exit no-fills/partials cannot create a
  free slot. A stop-out between grids has no cooldown timer but cannot re-enter between grids; it
  may re-enter at the next valid grid if still selected. A symbol with a pending exit is not
  simultaneously re-admitted.
- The `t+1` order is: process positions carried into the bar, then fill queued admissions against
  slots actually freed, then apply the existing entry-session protective-stop pass to each new
  position on that same bar. Moving admission later must not create one unprotected holding day;
  no newly entered position receives a second management-exit attempt on the entry bar.
- Signal mode keeps its existing uniform-notional/no-book-cap purpose; portfolio mode keeps the
  four-position risk book. Both expose the same typed rebalance decisions/refusals and pending-exit
  semantics, while their sizing constraints remain intentionally different.

## Smallest implementation map

1. `icarus/strategy/dsl.py`: add nested `opposite_signal.event`, typed optional `RebalanceRule`,
   exact parser refusals, and traversal of exit primitives. Existing YAML remains compatible.
2. `icarus/strategy/library/oscillators.py`: register `negate(series)` as a scale-free-preserving
   transform whose nested input must itself be scale-free; do not enable inverse-vol weighting.
3. `icarus/engine/simcore.py`: add shared typed pending-management-exit and rebalance-event records,
   plus exit reasons. Keep the existing protective/time/final ladder intact.
4. `icarus/engine/runner.py`: give `evaluate_once` optional validated `source_indices` (defaulting
   to the existing `range(len(panel))`), evaluate nested exit columns and the source-0 grid over
   those full-panel coordinates, and extend `_Columns.slice` so folds receive slices, never
   recomputations.
5. `icarus/engine/portfolio.py` and `icarus/engine/signaltest.py`: execute pending exits after the
   protective ladder; queue scheduled admissions until the next bar; retain partial/no-fill state;
   publish exact event/refusal accounting.
6. Add the two YAMLs. Update `scripts/synthetic_strategy_demo.py` to consume `evaluate_once` so it
   cannot omit new columns/schedules. Expand its exact catalogue guard from five to seven names.
7. Add `tests/unit/test_strategy_consumers.py`; extend the exit-vocabulary completeness test,
   runner source-index tests and synthetic-demo guard only where their public contract changed.

## TDD and acceptance

Write failing public-API tests first, then the smallest implementation. Required proofs:

- Both exact cards parse; unknown rebalance/event keys refuse; `negate(close)` refuses while
  `negate(realized_vol(252))` ranks the lowest volatility first; exit primitives are audited.
- A Donchian exit decided at `t` cannot fill at `t`; changing `t+1` cannot alter the decision at
  `t`; its first fill is `>=t+1`. Event-false/no-volume and partial-fill bars retain the remainder;
  a simultaneous stop/no-fill/partial produces exactly one FillModel call and defers the pending
  exit, proving per-bar participation cannot be spent twice.
- Whole-panel runs with zero-based and offset original coordinates, plus two differently sliced
  folds, produce the same source-0 `252+63k` decisions and full-source identities. A planted
  fold-local reset or hidden `arange(len(slice))` must fail this test.
- Hand-worked 31+ symbol fixtures prove exact bottom-30 membership, ascending admission rank,
  30-from-30 refusal, non-finite refusal, both cutoff-tie cardinalities and no target overflow.
- Incumbent retention creates no turnover; removal exits next bar; only actually freed slots admit
  replacements; no/partial exit preserves slot and risk; stop-out cannot re-enter until the next
  grid, then can; no entry occurs between grid dates. A new admission that crosses its protective
  stop on its entry bar exits on that bar, preserving the existing loss path.
- Portfolio output never exceeds four holdings and labels the 30 names as candidates. Signal mode
  remains uncapped/uniform-notional. Equal-risk behavior remains in force; inverse-vol still
  refuses.
- The unchanged 24-name catalogue fixture reports zero low-vol signals/trades and explicit thin-
  cohort refusals, and names exactly seven cards. A separate 31+ symbol fixture exercises a positive low-vol path;
  Donchian gets its own strict 55/20 positive/exit fixture.
- Existing DSL, exit, portfolio, signal, runner, cost/tax, metric, catalogue, synthetic-demo and
  golden regressions pass; then run strict mypy, Ruff lint and format check. Hosted CI runs the
  full suite once on the final pushed snapshot; local checks exclude completed-study replay and
  other unrelated long raw-coverage jobs. Reintroduce at least the
  same-bar exit, fold-local schedule, invalid-cohort liquidation and dropped-pending-exit defects
  after commit and prove the tests fail; restore exact committed bytes and rerun focused checks.

The implementation proof belongs under `var/verification/2026-10-12/consumers/`; it must record
source/card hashes, focused and broad commands/results, mutation/restoration evidence, and an
independent simplicity-then-engineering review. Documentation-only planning needs no code tests;
`git diff --check` and line-count/scope verification are sufficient now.

## Reviewed opening-capacity amendment - 2026-10-12

Queued open-price admissions must not spend capacity released by later intrabar information.
Before carried exits mutate the book, classify against pre-bar state: unavailable bars, trailing
updates using current close/ATR, non-gap stops and resting targets make execution order unavailable.
A later non-executed STALE_MARK release also refuses admissions. Publish typed
EXECUTION_ORDER_UNAVAILABLE outcomes; consume the admission once, with no delayed retry.
Known open-executable pending/time/final fills and gap stops may release actual capacity. Existing
carried exits remain unchanged. Paired equal-history/open/volume low and trailing-close witnesses,
stale-release refusal and known-open positive companions verify this policy. This is conservative
execution hardening before any market data, not a candidate or statistical-threshold amendment.
