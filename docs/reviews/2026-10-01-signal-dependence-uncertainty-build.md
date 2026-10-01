# Dependence-aware bounded uncertainty build - 2026-10-01

D34-approved isolated research implementation is complete at source `5db62aeaa1942c0c848f0eec95bf5a04cc656e06`, independently reviewed and verified on the current Windows PC. This is not an accepted product method, a real-strategy result or a whole-runner attestation. Task3a remains incomplete; inference stays disabled.

## What was built and why
The signal simulator records trade outcomes. The approved research extension measures uncertainty when a predeclared partition has jointly independent group vectors within each class, while allowing dependence between classes. Unknown premises refuse; inadequate requested precision returns insufficient evidence without interval endpoints. Synthetic-only source, complete pairing, individual support, fixed geometry and conservative arithmetic remain required.

`estimate_dependence` accepts immutable `IndependentClass` and `DependenceContract` values with explicit `WithinClassIndependence.JOINT_FIXTURE_DECLARED`. Omitted assumptions default to UNKNOWN; pairwise-only and observed declarations refuse. Class IDs and group mappings must be nonempty, unique and cover the full cohort exactly, including structurally known cases. Fixture identity/provenance are checked. The original globally independent `estimate` route retains its API, outputs and global-independence requirement. The new route does not invent a globally independent SourceContract.

`DependenceResult.calculation` uses the existing result types and original Q/weight/range diagnostics; the wrapper separately records original_q, active_classes, penalized_q, penalized_range_effective_groups and class provenance. Insufficient results do not expose interval endpoints. Both routes share validation and numerical arithmetic in scripts/research/signal_bounded_uncertainty.py. New tests are tests/unit/test_signal_dependence_uncertainty_research.py; the earlier bounded tests were not changed.

## Mathematics and limits
Original trade weights are w_g=n_g/N. For d_g=w_g*(b_g-a_g), Q=sum(d_g^2), active K counts classes containing non-singleton declared metric support. Exact K*Q enters radius sqrt(K*Q*ln(2/alpha)/2), followed by conservative Decimal rounding. Original Q and weight concentration remain visible separately from K*Q and penalized concentration. Singleton groups retain known weighted contributions; observed constants do not certify singleton support.

Within each class, Hoeffding bounds the exponential moment. Holder with equal exponent K permits arbitrary dependence between classes, producing the KQ penalty. K=1 recovers the independent method. Precision uses untrimmed width relative to declared total support; favorable clipping or observed outcomes cannot rescue inadequate evidence. The guarantee is unconditional under the declared premises, not nominal conditional-on-emission coverage. The target is the fixed-cohort weighted expectation, not future-regime performance.

The [approved proposal](../plans/2026-10-01-signal-dependence-research-proposal.md) contains the full derivation and [Janson primary theorem](https://api.newton.ac.uk/website/v0/events/preprints/NI02024). The source records theorem/as-of provenance. Existing Fraction/Decimal resource caps remain scratch limits, not product thresholds.

At95% confidence,192 equally weighted unit-range groups produce normalized untrimmed widths about0.19603 forK1,0.27722 forK2 and0.39205 forK4. An illustrative quarter-range request needs119/237/473 groups respectively. Tests show236/472 insufficient and237/473 sufficient forK2/K4. These are examples under trusted premises, not configured trading floors. Increasing trades uniformly inside unchanged groups leaves the width unchanged.

## Verification and independent checks
- Test-first missing-API failures were observed by the implementer before source implementation. Final focused suite: **103 passed** (66 new,37 prior); strict source/test mypy and Ruff passed.
- Primary relevant Windows regression: **501 passed in43.42s**, including dependence/bounded/research uncertainty and method probes, signal simulator/test/metrics/oracle/calibration, portfolio characterization, fills, cost and tax. This is not a full repository-suite claim.
- `uv run mypy icarus tests scripts/research`: **146 source files clean**. `uv run ruff check --no-cache icarus tests scripts/research`: passed. Matching format check:146 already formatted.
- Primary independently enclosed ln(40) with a100-term exact rational atanh series and analytic tail, without using the helper's Decimal ln/sqrt. Six geometries (N,K)=(24,2),(119,1),(192,2),(192,4),(237,2),(473,4) passed exact Q/KQ, squared-radius and outward endpoint/support/precision comparisons.
- Independent numerical reviewer separately reproduced a heterogeneous example: counts1,2 repeated6, support widths1,2, mean1/2, support[0,5/3],Q17/54,K2,KQ17/27, conservative radius about0.66062546315956 at50% confidence. Duplicate-class/pairwise-only refusals and the original global-independence refusal passed. Reviewer approved stable hashes with no numerical blocker.
- Independent simplicity review ran before engineering/governance review, as required. Both approved the final code; shared arithmetic and validation were retained, with no unnecessary framework/dependency. Implementer was not counted as an independent reviewer.

Regression command: `uv run pytest tests/unit/test_signal_dependence_uncertainty_research.py tests/unit/test_signal_bounded_uncertainty_research.py tests/unit/test_signal_uncertainty_research.py tests/unit/test_signal_method_probe_research.py tests/unit/test_signal_simulator.py tests/unit/test_signaltest.py tests/unit/test_signalmetrics.py tests/unit/test_signalmetrics_oracle.py tests/unit/test_signalcalibration_task2.py tests/unit/test_signalcalibration.py tests/unit/test_portfolio_characterization.py tests/unit/test_fills.py tests/unit/test_costmodel.py tests/unit/test_taxmodel.py -q`.

## Exact dependent fixture results
The fixture X_t=(U_t+U_(t-1))/2 has nine independent binary shocks and eight outcomes. Same-parity classes use disjoint latent footprints internally; adjacent classes share shocks. Raw truth is p; strict-positive win truth is1-(1-p)^2. Primary expected probabilities were computed independently before implementation using exact rational log bounds, then compared against emitted endpoints.

All512 latent outcomes were evaluated for each p and metric at two predeclared confidence levels: **6,144 metric/confidence evaluations** total. At50%, every512-case roster emitted512 intervals and refused0. At95%, every roster returned512 insufficient-evidence results with no interval endpoints: normalized untrimmed width1.35810 exceeds the allowed full-support precision1. The separately predeclared50% level has width0.83255; it is a small mathematical test, not a change to the product confidence requirement or evidence of95% emitted coverage.

| Shock probability p | Metric | Target | Exact50% fixture coverage |
|---|---|---|---|
|1/10|raw|1/10|199867743/200000000|
|1/10|win|19/100|965392101/1000000000|
|1/2|raw|1/2|253/256|
|1/2|win|3/4|499/512|
|9/10|raw|9/10|199867743/200000000|
|9/10|win|99/100|999939411/1000000000|

Both implementation tests and primary independent checks matched these six exact probabilities. Enumeration checks the finite fixture, not every possible market process. No RNG, redraw or favorable-emission denominator was used.

## Post-commit guard verification and provenance
No actual implementation defect was found by the final reviews; no claim of reintroducing a discovered bug is made. After committing source5db62ae, primary deliberately omitted the K penalty and then allowed pairwise-only claims. The unequal-weight arithmetic test failed for the first guard mutant; three pairwise/XOR tests failed for the second. Exact original source bytes were restored after each. All103 focused tests passed again in2.15s, and source/test diffHEAD was empty. These are deliberate guard checks, separate from defect-specific mutation evidence.

Source SHA256: `482a74da2e9a9eb0d78d9eeeccebea54653c9912353f33d3d8b3cf6fea1219e8`.
New test SHA256: `5fb49e9a3862caceaff8f85b98bec21d09fd2ac39899235b39ba384fec165ad8`.

Ignored local evidence in var/verification/2026-10-01/dependence-uncertainty/: regression.log, primary-expected-coverage.json, primary_oracle.py, primary-oracle-result.json, primary-oracle.log and guard-mutations.log. Durable conclusions/commands are recorded here; scratch files are not shipped artifacts. Root inspected code, hashes, actual outputs and protected-file diffs before acceptance.

## Remaining work and held boundaries
This does not repair recursive serial cell28, justify finite memory in actual markets, or provide finite bounds for unbounded Gaussian benchmark differences. M1-M4 remain open for general/product use. Next work is a defensible model for persistent market dependence and tails, or an explicit refusal, plus future real-data eligibility before any reviewed validation/adoption.

No stochastic screen/new seed, real-data strategy trial, reserved stream, lockbox, accepted product floor, gate change, inference enablement or broker/live path occurred. Protected estimator/calibration, frozen manifest/digest, goal.yaml and uv.lock are unchanged. Historical platform/integration skips and official Windows resource/durable-claim blockers remain separate and were not rerun here. Synthetic portfolio characterization passed; the separate production golden backtest remains uncaptured.
