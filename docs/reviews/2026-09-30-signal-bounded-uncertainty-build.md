# Bounded uncertainty research build - 2026-09-30

The D33-approved component is built and independently reviewed at source `5d59925cc0b22bf1d07af6acefcbd3b3110dfbda`. This is a pure synthetic research reference, not an accepted strategy evaluator or whole-runner attestation. Task 3a remains incomplete; inference stays disabled.

## What it does
The simulator records trade outcomes. This helper measures uncertainty only when a fixture explicitly declares independent groups, hard individual-outcome bounds and fixed grouping. Trades within a group may depend on each other. Unknown assumptions, real-data labels, invalid cohorts and support violations refuse. If requested precision needs more independent evidence, the result has no interval endpoints.

Raw outcomes, wins and paired synthetic benchmark differences share the same complete cohort. Benchmark differences require declared bounds for both sides. Constant observations retain uncertainty unless every declared support is an exact singleton. Singleton results use the exact weighted structural value.

The immutable API is scripts/research/signal_bounded_uncertainty.py; deterministic tests are tests/unit/test_signal_bounded_uncertainty_research.py. No dependency or product changes were needed.

## Mathematical contract
For group counts n_g, total N, weights w_g=n_g/N and metric support [a_g,b_g], define A=sum(w_g*a_g), B=sum(w_g*b_g), Q=sum((w_g*(b_g-a_g))^2). Weighted Hoeffding gives radius sqrt(Q*ln(2/alpha)/2). The untrimmed mean interval is intersected with [A,B]. This is unconditional coverage under the declared assumptions, not nominal coverage conditional on data-dependent emission.

Fractions preserve exact inputs, means, support and Q. A fresh local Decimal context isolates ambient precision/traps. The logarithm and square root are conservatively enlarged; endpoints round outward. Precision uses untrimmed width 2*radius/(B-A), determined by declared geometry/support rather than observed mean. Endpoint conversion that exhausts precision or collapses resolution refuses separately.

The theorem follows [Hoeffding's bounded independent-variable result](https://www.cs.rpi.edu/academics/courses/spring06/random/hoefding.pdf); directed arithmetic was checked against the [Python 3.12 Decimal specification](https://docs.python.org/3.12/library/decimal.html). Sources checked 2026-09-30. Independence and support are trusted fixture premises; the helper cannot certify them from market observations or a stop-loss rule.

Technical scratch caps (4,096 groups/observations, 4,096-bit rational components and Decimal adjusted magnitude at most 1,000) protect arithmetic resources. These are not product minimum-data rules. Alpha/precision inputs belong to the caller's fixture specification.

## Reproduced examples
At alpha=0.05 with unit-width support, 192 trades grouped into 24 independent units have normalized untrimmed width about 0.55444; 192 independent units give about 0.19603. For an illustrative requested width of 0.25, 118 equal units return insufficient evidence and 119 give about 0.24899. The number 119 is an example, not a trading threshold.

## Verification and reviews
- Initial test-first run: 28 failures for the missing helper; expanded implementation run: 33 failures before completion. Final focused suite: 37 passed.
- Relevant regression: **435 passed in 38.20s** on this Windows PC. Included bounded/research uncertainty and method probes, signal simulator/test/metrics/oracle/calibration, portfolio characterization, fills, cost and tax tests. This was not a full repository-suite claim.
- `uv run mypy icarus tests scripts/research`: 145 source files clean. `uv run ruff check --no-cache icarus tests scripts/research`: passed. Matching Ruff format check: 145 already formatted.
- Primary independently bracketed ln(40) using exact rational atanh-series terms and an analytic tail bound, without the helper's Decimal ln/sqrt. Five geometries (8, 24, 119, 192 equal groups and 12 unequal groups) passed squared-radius, outward endpoint/support and precision checks. Log bracket width was approximately 7e-98.
- Primary exhaustively evaluated all 256 outcomes of eight independent binary units at each of p=0.1, 0.5 and 0.9: **768 deterministic cases**, 256 emitted and zero refused per distribution. Exact coverage was 19991367/20000000 (0.99956835) for p=0.1/0.9 and 127/128 (0.9921875) for p=0.5. These are finite fixtures, not a general 45-profile acceptance.
- Independent numerical reviewer approved the proof/arithmetic and separately reproduced a radius and refusal paths. Independent ponytail then engineering/governance reviewer approved final source/test hashes. The implementer was not counted as an independent reviewer.

Two actual development defects were fixed through failing tests: omitted assumptions initially defaulted to declared-known, and precision initially depended on observed-mean endpoint rounding. After committing source `5d59925`, each defect was temporarily restored in an exact-byte snapshot. Corresponding regressions failed for both mutants. Original bytes were restored after each, then all 37 focused tests passed in 0.38s; source/test diff was empty. No broadened repeat suite was needed after exact restoration.

Local ignored evidence: var/verification/2026-09-30/bounded-uncertainty/ contains regression logs, independent-design-check.json, independent_oracle.py, independent-oracle-result.json, exhaustive-primary.json and mutations.log. Durable conclusions and commands are recorded here; ignored scratch files are not shipped artifacts.

Source SHA256: `9276f7a08a0aa1c59fdde6327fe1089932e32475b9220f4a733a0ffee8a7f2f9`.
Test SHA256: `015334e2bccdf613e0bc9aaa3a5a78bb4331f3aa0ed98576afdd21795d7443ec`.

Regression invocation: `uv run pytest tests/unit/test_signal_bounded_uncertainty_research.py tests/unit/test_signal_uncertainty_research.py tests/unit/test_signal_method_probe_research.py tests/unit/test_signal_simulator.py tests/unit/test_signaltest.py tests/unit/test_signalmetrics.py tests/unit/test_signalmetrics_oracle.py tests/unit/test_signalcalibration_task2.py tests/unit/test_signalcalibration.py tests/unit/test_portfolio_characterization.py tests/unit/test_fills.py tests/unit/test_costmodel.py tests/unit/test_taxmodel.py -q`.

## Remaining work and boundaries
Earlier general candidates remain rejected: serial raw coverage 913/1024 and rare-magnitude raw coverage 839/1024 did not meet intended 95% coverage. This helper neither fixes serial dependence nor permits inventing finite bounds for unbounded outcomes. Next statistical design must address dependence and establish which real-data assumptions can honestly be justified, with reviewed precision/refusal requirements before evaluation.

No stochastic draw, new seed, real-data strategy evaluation, lockbox use, trial-ledger strategy attempt, official stream, accepted product floor or broker/live path occurred. Protected product estimator/calibration files, goal.yaml, frozen manifest/digest and uv.lock remain unchanged. Historical platform/integration skips and native proof results were not rerun here. Separate production golden backtest remains uncaptured; synthetic portfolio characterization passed. Windows official resource/durable-claim blockers remain open.
