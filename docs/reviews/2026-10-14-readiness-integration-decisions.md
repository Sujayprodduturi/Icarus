# Readiness integration decisions — 2026-10-14

Status: local software mechanics are verified at sources `68b5` plus `eb65474`, with test
head `3dcdcf5` and independent final scoped GO. The corrected outside-sandbox proof reconciles
all 39 semantic mutants and all protected runtime source remains unchanged. No current-source
CI pass is claimed. This is not permission to run strategies on market prices.
`SOFTWARE_VERIFIED=true`, `DATA_QUALIFIED=false` and `RUN_AUTHORIZED=false`.

- Software checks establish structural and causal consistency; they cannot establish
  vendor authority or licence truth. Keep the assembler's data qualification false.
  Actual execution additionally requires a separate, dated, operator-reviewed external
  qualification certificate. Bind its exact digest into run authorization, execution
  identity, trial reservations and reports. The certificate must pin the bundle,
  approval, source policy and required source evidence; invented evidence cannot qualify
  real inputs. Independent contract and implementation source reviews are GO.
- Policy registration precedes qualification; qualification precedes run issuance;
  issuance is no later than now and expiry is later than now. These are external
  attestations, not software proof that historical data was never inspected.
- Registration, qualification, issuance and expiry use strict UTC timestamps, reject
  fractional precision beyond six digits, and follow that chronology.
- The separate calendar cross-date guard requires both the raw UTC calendar date and the
  date after conversion to IST for each open timestamp to equal the declared session date.
  Cross-date equity sessions are unsupported by this contract and refuse rather than being
  silently reassigned.
- Derive reservation geometry from the calendar clock without parsing price records.
  Reserve every strategy/mode/capital attempt before shared price decoding or DSL
  evaluation. Verify the decoded axis agrees with the reserved geometry.
- Closed dates remain in calendar evidence but do not consume trading-session indices.
  Preserve the original full-source trading indices across walk-forward slices.
- Retain all raw intraday Nifty observations for execution matching. Derive the daily
  benchmark projection separately under a pinned `EXACT_OBSERVED_SESSION_CLOSE`
  policy: an observed event at the session close must be available by that daily
  decision. Unsupported benchmark OHLC fields remain unavailable; never substitute
  the opening price for the close. Missing historical observations remain missing.
- Preserve the entire daily axis while accepting only the declared M15 coverage.
  A requested span lacking refinement is explicitly unavailable; later covered folds
  may run independently. Never clip dates or remove names to conceal missing input.
- On an aborted reservation or evaluation, attempt terminalization of every known
  unstarted NEW reservation. Do not overwrite recovered or ambiguously completed
  receipts. Failed persistence retains an explicit reconciliation blocker and releases
  no results; it never authorizes reevaluation.

The loader/barrier builder owns the existing readiness modules and their tests. The
evaluator builder owns the new timed evaluation module, its tests and command-line
launcher. The completed code path passed independent source and corrected post-commit proof
review. Public source availability and the unsent vendor enquiry are recorded in
[historical-data-availability.md](../data/historical-data-availability.md).
