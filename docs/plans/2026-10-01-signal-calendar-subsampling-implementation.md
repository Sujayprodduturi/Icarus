# Calendar uncertainty deterministic implementation

Date: 2026-10-01. Operator approved implementation after the [reviewed design](2026-10-01-signal-calendar-subsampling-design.md); D40 records the scope. No stochastic experiment or product adoption.

## Scope and contract

One pure module `scripts/research/signal_calendar_uncertainty.py`, one new deterministic test file. No existing estimator/API modifications, product import/integration, panel adapter, persistence, broker, RNG, dependencies or configuration changes. Source and model declarations are synthetic premises, never authenticated market certificates.

Frozen typed records hold identity/symbol, decision/entry, complete exit/source/recognition footprint, original return, optional complete synthetic paired excess, and stale/terminal provenance. A source pins the complete canonical core, authorized halo bounds, reset identity, cohort completeness/geometry, synthetic scope and before-tax model-cost accounting. A target-specific model declares stationarity, mixing/moment/CLT premises and deterministic lookback/completion/shift-equivariance bounds. A request fixes nominal alpha1/20 and supplies an explicit research absolute-width requirement; unknown premises/precision are refusals. No product minimum-data floor is introduced.

All original core-entry records count once; partial exits already aggregated. Reconcile rows against independently declared expected core identities so omitted observations are detectable. Halo-only entrants do not count but must have valid identities/footprints; their target-specific benchmark eligibility does not veto core-only paired inference. Missing outcomes/IDs, duplicates, malformed/gapped axis, out-of-bound footprint, stale or forced terminal outcomes, accounting mismatch and incompatible model declarations refuse affected inference. Missing benchmark blocks paired excess rather than raw. Complete declared metadata never authorizes a real run.

Outcome-selected premises mean changing the study core, block rule, target, precision policy or cohort after inspecting outcomes. They do not prohibit market-dependent signal counts or dependence between returns and counts, which the stationary joint-process model explicitly permits. Independent mathematical plan review approved this contract before implementation.

## Arithmetic

1. Convert supported finite numeric inputs to bounded Fractions before aggregation; preguard Decimal coefficient/exponent and integer/Fraction size. Refuse booleans and nonfinite data. Bound rows/sessions/allocation with technical limits, not market floors.
2. Aggregate exact session sums/counts including empty sessions; exact full sum/count mean and every overlapping scheduled slice. Integer binary search for minimal b with b^3>=n^2. No fitted choice or retry.
3. Refuse the entire component if any scheduled slice has zero count; never discard or zero-fill it. Keep explicit zero-slice diagnostics. Degenerate roots or collapsed selected quantile spread refuse, including a rare boundary spike whose central empirical quantiles are identical.
4. Rank exact slice deviations. At95%, inverse-CDF ranks ceil(q/40)-1 and ceil(39q/40)-1. Roots are dependent, not independent evidence counts.
5. Certify a Decimal bracket for sqrt(b/n) by rational squared comparisons. Use sign-aware exact products for m-max(d_hi*s_lo,d_hi*s_hi) and m-min(d_lo*s_lo,d_lo*s_hi); round endpoints outward under a fresh local context. Numeric failure returns refusal, not a misleading range.
6. Compare conservative mathematical and actual displayed span with requested absolute precision. Insufficient evidence preserves candidate calculation/provenance with separately named fields, never an eligible-market interval. All result states are permanently synthetic research, asymptotic candidate uncalibrated, market-ineligible; no p-values, strategy verdict or finite-sample guarantee.

## Test-first and completion sequence

- Write behavioral tests and observe red before implementation: reviewed8-session example; uneven counts, empty dates, complete boundary-crossing trade/halo entrants; exact b/quantiles; paired and win targets; zero slices; malformed IDs/axes/footprints; unknown/outcome-selected premises; stale/terminal/cost/tax mismatch; nonfinite/oversized inputs; degenerate roots; insufficient precision; hostile ambient Decimal context and same-sign quantiles.
- Implement and run focused tests, Ruff/format and strict mypy. Primary independently checks actual API arithmetic and protected source/config bytes. Reuse narrow numeric conventions if natural; do not inherit old model-eligibility or unconditional-coverage labels.
- Independent mathematical review; then actual ponytail/simplicity review followed by engineering code review. Fix verified findings, rerun affected checks; run relevant simulator/portfolio characterization and research regression on the current Windows PC. Disclose any excluded slow/platform/datastore tests; no unchanged full-suite claim.
- Commit source only after checks/reviews; run bounded defect probes after commit, snapshot/restore exact bytes, then rerun focused regression. Update state/handover/audit/task/approval/build evidence, commit and push. User-owned AGENTS.md stays untracked.

Next milestone after this build is a separately preregistered stress/confirmation protocol, not real strategy evaluation. Task3a, M1-M4 and existing source/accounting/Windows official-calibration prerequisites remain open; inference stays false.


## Completion record
D40-authorized deterministic implementation complete at source7d5d9f5. See [build evidence](../reviews/2026-10-01-signal-calendar-subsampling-build.md) for exact hashes, red/green findings,583 relevant regressions, independent reviews and334 restored research tests. No sampled experiment or adopted method.
