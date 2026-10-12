# Synthetic capital comparison contract — 2026-10-12

The operator approved continuing after the fee/exit/rebalance milestone. This dated scope
amendment schedules a bounded extension of the existing synthetic demonstration under that
instruction and the standing major-milestone cadence. It does not schedule product Task 3a
Step 8, adopt a statistical method, activate the actual trial ledger, or authorize real data.

## Outcome in plain English

Run every existing card on the same invented prices, once as independent signal observations
and twice as a portfolio: Rs100000 seed capital and Rs1000000 edge capital, as required by D8.
Show how capital and existing limits affect simulated trades. Explain empty or unavailable
results. Do not select winners from invented prices or claim readiness for market inference.

## Fixed behavior

- Extend `scripts/synthetic_strategy_demo.py` and its existing unit tests only. Preserve the
  fixed 24-symbol/600-session fixture, origin260 and all seven cards, goal and engine modules.
- Evaluate causal full-source DSL columns once per card and reuse exactly the same inputs for
  all three evaluations. Preserve next-bar decisions, source identity and rebalance grid.
- Signal notional stays at the configured Rs100000. Each portfolio starts fresh at its named
  capital with identical risk/fill/cost settings; never scale one result to manufacture another.
- Record three distinct synthetic evaluation identities per card before executing that card.
  All21 evaluations belong to isolated synthetic receipts, not the lifetime PostgreSQL ledger.
- Emit two explicit capital rows and two full portfolio result records. Report starting/final
  equity, closed-trade P&L after modeled charges before tax, trades, typed refusals, stale marks,
  unfilled exits and ambiguity. Do not describe final equity as cash or net P&L as after tax.
- Bind goal/card bytes actually parsed, fixed fixture identity/hash and source coordinates.
  Output directories and artifacts remain exclusive; a failed run cannot publish overall success.
- Keep zero-trade cards visible. The24-name fixture cannot satisfy low-volatility's31-name floor;
  it must show the refusal. Existing dedicated positive fixtures remain the separate evidence
  for low-volatility, reversal and Donchian consumers. Do not alter prices to favor any strategy.

## Explicit unavailability and boundaries

Benchmark excess is unavailable without resolved execution times and certified benchmark legs.
Confidence remains unavailable with inference disabled and no adopted market method. Account
tax/promotion metrics are unavailable because this direct simulator demonstration does not
evaluate account taxation or walk-forward promotion. These are reasons for missing measures,
not zero values, failed strategies or waived prerequisites. No edge ranking or winner appears.

This unit is continuous-history artificial capital-sensitivity mechanics, not a fold-matched
comparison. A later fold comparison must use fresh exact fold resets under D19/Step8; cropping
a continuous signal result cannot substitute. Actual-ledger activation, source/time benchmark
matching, method applicability/M4, and D41 real-data approval remain separate held decisions.
Inference stays false; lockbox, broker, live paths and existing artificial-study streams remain
untouched. No acquisition, subscription, new sampled study or project risk/gate amendment.

## Acceptance and verification

Tests first: fail on the missing paired rows/identities, then exercise the real public simulators.
Verify exactly seven cards and21 declared evaluations, correct capital labels, independent book
results, real quantity sensitivity without assuming linear tenfold profits, and preservation of
the fixed fixture. Verify refusal/empty-result labels, unavailable metric reasons, exclusive
output reuse and fail-before-evaluation on inference/catalogue mismatch. Compare at least one
paired book value independently; keep every card present and original source coordinates intact.

Run focused integration/consumer and golden regression checks, strict explicit mypy and global
Ruff lint/format. Independently review simplicity then correctness; freeze source before commit.
Known-bug source variants run only after commit, with exact restoration and a fresh positive
regression. Record root verification and reviewers in durable build proof and update STATE,
HANDOVER, TASKS and the latest audit before ending. Publish once and inspect exact-source CI.

Prior milestone's exact published source6b3303d has full CI38216162648 and native-resource
38216162627 both SUCCESS, freshly verified on2026-10-12. This status does not pre-approve later
source changes. No new hosted PASS is claimed until its own run succeeds.
