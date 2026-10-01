# Persistent-dependence uncertainty reference: build evidence
Date: 2026-10-01. Source: f7c72f5ae51f1dc29dfe53322a44eca83cf9448a. Phase 1 / Task 3a remains in progress. Operator D35 authorized capable sub-agent review and proceeding with justified recommendations.

## What was built
The approved pure stationary Gaussian artificial-model reference is implemented in scripts/research/signal_bounded_uncertainty.py with deterministic tests in tests/unit/test_signal_persistent_uncertainty_research.py. No simulator integration or product adoption occurred.

The capable mathematical reviewer recommended immutable explicit model premises, actual latent coordinates, shared premise-free partition/cohort/endpoint checks, exact powers before directed logarithms, exact conservative residuals and separate class radii. Root checked and adopted these recommendations. A separate implementer was not counted as an independent reviewer.

PersistentModelContract requires declarations for stationary Gaussian start, independent Gaussian innovations, known persistence bound, fixed whole raw/benchmark local map, independent local-vector noise, marginal preservation and fixed geometry. All defaults are UNKNOWN. A complete unique LatentIndex map carries its own axis identity, independent of entry-session coordinates. Groups cannot split a shared latent index. Every group appears exactly once in the fixed partition.

Original counts/trade weights, individual support checks and whole paired benchmark cohorts remain unchanged. Metric-specific singleton groups retain known contributions but are projected out of random gaps and allowances. Even all-known output validates the entire source/model/map/partition. These are conditional mathematical inputs; the code cannot discover or authenticate the law from observations.

## Calculation and numerical refusals
For each active class, exact rational x=r^(2d) and1/(1-x) give an upward logarithmic allowance. Pinsker event-TV allowance is min(1,sqrt(sum(-ln(1-x)))/2). Stationary Gaussian/Markov structure and independent local maps preserve the relevant marginals and expectations. Primary references and the derivation are in the approved proposal; source comments retain as-of provenance.

Class allowances sum upward to D. Residual alpha-Fraction(D_upper) is exact, hence a conservative lower budget; it is not rounded to zero in an ambient Decimal context. Nonpositive residual refuses. Fixed uniform allocation gives each class radius sqrt(Q_c*ln(2K/residual)/2), and these upper radii sum upward. No adjusted KQ shortcut or cross-class independence claim.

Every rational power's combined numerator/denominator resource growth is preflighted before any exponentiation, with a total262144-bit scratch cap. This is a technical cap, not a market floor. A fresh80-digit Decimal context isolates caller settings. Positive tiny persistence stays positive or refuses; exactly zero persistence and singleton classes have exactly zero transfer allowance. K1/r0 reproduces the original independent calculation, including alpha1/3. Endpoints round outward; precision uses full untrimmed width, not favorable outcomes or clipping. Inadequate precision emits no endpoints.

## Verification
- Implementer observed49 missing-API test failures before implementation. Final focused suite175 passed (72 new plus103 prior). Existing earlier test files are unchanged.
- Primary relevant Windows regression573 passed in40.12s. Simulator/accounting/portfolio characterization/research/calibration regressions were included.
- Strict mypy147 sources, Ruff and matching format check passed.
- Primary independently checked four exact Gaussian covariance determinants, including irregular gaps, against exact rational logarithm enclosures with analytic tails. Five pure-model geometries checked class log/TV allowances, original/class Q, exact residuals, class squared radii, upward total radius, normalized widths and outward endpoints. Both exhausted-budget stresses refused.
- Primary scratch initially expected a32-group/r1/3/K4 case to pass: the code correctly refused its exhausted budget. This was an oracle-fixture expectation error, corrected by retaining that case as a refusal witness and checking r1/4 as the valid-budget geometry. No source change was required.
- Independent medium-effort numerical reviewer verified final hashes and separately reproduced the actual24-group example and a heterogeneous irregular example with original Q85/288, class Q19/288 and11/48, conservative radius.750030835877678. Exhaustion and alpha1/3/r0/K1 equivalence also passed.
- Independent reviewer completed the actual ponytail-review skill first (Lean already. Ship), then engineering:code-review. Both approved final code with no blocker. Shared _partition/_aggregate/_finish avoid duplicated validation/arithmetic; original independent and fixed-class radius paths remain intact.
- Default full Windows suite:1854 passed,3 failed,10 skipped in1923.78s. All three failures were the existing audit-ledger parser rejecting the new ranked-list heading. Its F-only namespace also risked ignoring M/P/R rows. Repaired with failing tests first (9 failed/6 passed), then15 passed. Header variants, all current ID namespaces, scope boundaries and nonempty-list checks are covered. Independent reviewer approved the repair. Follow-up excluding unchanged already-tested slow runner and unavailable integration:1568 passed in75.63s. No fresh full-suite green claim is made.

### Full-suite orchestration limitation
The default suite initially waited in local Postgres integration setup with no DSN override. Both one-second loopback5432 probes timed out; this does not prove the service absent. A proposed bounded connection retry was independently reviewed but was never applied: the original suite progressed before the stop guard, so that guard refused termination.

Root's shell then incorrectly continued after that failed guard and launched a duplicate test process sharing the log path. Root verified and stopped only that owned duplicate after68.498s, keeping the original suite running. The shared log's progress prefix was corrupted by truncation; the original final terminal summary and child exit1 were preserved and inspected. The wrapper then encountered a CP1252-versus-UTF8 decoding error after saving its result; a decoded copy was inspected without changing raw evidence. No test/product/DSN change occurred, and no clean-prefix or bounded-rerun claim is made. Metadata is retained locally.

## Artificial-model results and their meaning
At95% confidence, unit-width supports and the predeclared illustrative modulo10 partition:

| Geometry | Dependence allowance | Full normalized width | Result |
|---|---:|---:|---|
|24 groups /192 trades (8/group), r=.5|.005691824721047|2.245471627254998|Insufficient for precision<=1|
|192 groups /192 trades, r=.5|.020829557399766|.824724309739820|Meets illustrative precision1, not .25|
|192 groups /192 trades, r=.6|>.05|No endpoints|Exhausted probability budget|

The first geometry matches cell28's declared shape; these are mathematical checks, not new samples or empirical coverage. The hypothetical192-group and .6 examples are not frozen manifest parameters. No partition optimization, accepted minimum-data floor or serial-failure repair.

## Post-commit checks and provenance
After source commit, three mathematical/type mutants were caught: omit dependence charge, accept unknown model premises, and reintroduce the aggregate return-type defect. Two audit-checker mutants were caught: legacy-only heading and F-only finding IDs. Each mutation produced the expected failure; exact bytes were restored after each. Restored focused suite175 passed in2.22s. The earlier aggregate type defect was discovered and fixed before the final static gate; this mutation confirms that mypy detects its recurrence. Audit checker SHA256:ca475eb324bc07c372426ff5f5e067a1abb6156a21d797babefc887b03a0241e.
Source SHA256:77bd29e660ebcfcec9d4eaecf0d4fa218af6e5d1de6736eb9fac0aa91579f139.
New test SHA256:06c773333e0f0bf16c9b0d37b0400a99f017b6bfd64cb75026546849fd7f4a91.
Ignored local evidence: var/verification/2026-10-01/persistent-dependence-build (RED/GREEN, regression/static/full-suite logs, primary_oracle.py, covariance-oracle.json, primary-results.json, verification-notes.json and guard logs). Root inspected actual code, outputs, hashes, diffs and at least one independently reproduced value before acceptance.

## Remaining work
The original serial coverage failure remains open. Exact continuous Gaussian model declarations do not certify finite-precision PCG/normal samples or real-market stationarity/dependence. Unbounded benchmark excess and observed extrema remain unsupported; future tail treatment and real-data model/assumption policy require a separate reviewed design and stress/validation plan. M1-M4 remain open for general/product use.

No stochastic screen, real-data trial, reserved-stream consumption, lockbox access, accepted floor, frozen gate/config amendment, inference enablement or broker/live path. Official Windows hard-resource/durable-claim blockers remain separate. Synthetic portfolio characterization passes; the separate production golden backtest remains uncaptured.
