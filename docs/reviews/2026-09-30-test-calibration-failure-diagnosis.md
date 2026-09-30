# Non-reserved calibration failure diagnosis
Date: 2026-09-30. Source: `8086edbfafb8ec651b16f1c70865bbc7834e0d5d`; protected statistical/generator source unchanged from `cdf127b`. Status: completed diagnostic; no official verdict, floor or implementation approval.

## Finding
The earlier native generated resource proof completed operationally but its test-only calibration was FAILED. A Windows replay now establishes specific statistical witnesses: the candidate intervals miss the known synthetic truth too frequently. All four frozen candidate floors require cell 28, which fails decisively. Raising the existing floor cannot resolve this witness.

This is not a strategy performance result. Inference stays disabled. Neither reserved stream was consumed; no counted context, claim, official artifact or completion authority was created.

## Method and retained evidence
Ran on the current Windows PC with Python 3.12.10, NumPy 2.1.3 and SciPy 1.14.1:
```powershell
uv run python -m var.verification.2026-09-30.calibration-diagnostic.replay
```
The ignored research script calls unchanged `_generate_replicate_core`, `_test_or_rng` and `_uniform_component_draw` using non-reserved seed **2026092911**, the original native generated proof's test seed. The helpers reject both reserved seeds. PCG64/SeedSequence component addresses and original chunk rows are preserved: 256, with a final 16-row chunk. Production metric-event construction self-validates partitions and scalar/batch parity; production Clopper-Pearson summaries recompute the frozen checks.

Completed six selected cells, each with all 10,000 replicates, three metrics: **60,000 replicates / 180,000 metric evaluations**, in 95.875 seconds; process exit 0. Selected before the root replay: serial witness 28, strong block-dependence/rare-win 9, burst 12, rare-magnitude 30, regime-shift control 34, independent rare-win control 1. This is not the complete 45-cell phase.

Local ignored evidence under `var/verification/2026-09-30/calibration-diagnostic/`:
- `replay.py` SHA-256: `5b3d2d19905c7e8045ecdadeaca4a8737c2c98eaf077f2e6e4715746301dc837`
- `result.json` SHA-256: `f191c1270b054478cb73b958eca5d61e46a15588aee7c0d449cc34b8b78ce93b`
- `replay.log` SHA-256: `511eb8470888fe33cd5ca247f765d4d4b8714f4e2940328e7394479abf54a9ce`

Original Linux per-cell artifacts were temporary and not retained by its resource workflow. This replay uses its random-address construction and seed; byte equivalence to an unavailable original phase artifact cannot be claimed. This diagnostic does not test Windows resource/durability equivalence or issue a full counted phase verdict.

## Results
Entries below are coverage successes / emitted intervals. Refusals remain in the joint/emission denominator. A fraction alone is not the gate: production summaries also test multiplicity-adjusted CP bounds, separate tails, emission and joint success.

| Cell | Stress | Raw coverage | Win coverage | Synthetic-excess coverage | Any frozen check fails? |
|---|---|---:|---:|---:|---|
| 28 | Cross-block serial, rho .5, p .5 | 7,910 / 10,000 | 7,871 / 10,000 | 9,379 / 10,000 | Yes, all three metrics |
| 9 | Independent block factor, rho .5, p .05 | 8,536 / 10,000 | 8,178 / 9,820 | 9,428 / 10,000 | Yes, all three metrics |
| 12 | Same-session burst, p .05 | 8,554 / 10,000 | 8,172 / 9,830 | 9,464 / 10,000 | Yes, all three metrics |
| 30 | Bounded rare magnitude, p .05 | 8,337 / 9,998 | 9,079 / 9,992 | 9,137 / 10,000 | Yes, all three metrics |
| 34 | Two-regime p .2/.8 control | 9,992 / 10,000 | 9,991 / 10,000 | 9,998 / 10,000 | No |
| 1 | Independent p .05 control | 9,425 / 10,000 | 9,214 / 9,998 | 9,518 / 10,000 | Raw upper tail; win coverage/tail/joint |

Cell 28 has zero refusals for all metrics. Raw and win coverage CP lower bounds are **0.7752375508831019** and **0.7712366988420098**, below the fixed **0.93** threshold. Raw tail upper bounds are **0.11476853002128506 / 0.11833171481558206**, above **0.04**. Synthetic-excess coverage lower bound **0.9282534045344457** also fails, though its separate tails pass. Emission passes for every selected cell/metric.

At 10,000 emitted intervals, coverage/joint need at least **9,396** successes; each tail permits at most **327** misses. Cell 28 raw misses are 1,028 lower and 1,062 upper. Production `_candidate_support` returns supported=true for cell 28 under all four floors (6 blocks/nu4; 8/6; 12/8; 16/12). Because candidate passage requires every supported cell's checks, this witness excludes every existing candidate for the replayed test seed without needing the other 39 cells. It does not predict an official stream or replace its verdict.

## Cause and limits of diagnosis
Verified source mechanism: `scripts/signal_calibration.py` serial family introduces an AR factor across blocks; `icarus/engine/signalmetrics.py` CR2 variance sums adjusted within-block score squares and has no cross-block covariance terms. This makes omitted serial covariance a strong explanation of cell 28's narrow intervals. The mathematics is implemented as designed; passing parity demonstrates implementation agreement, not valid statistical coverage.

Serial dependence is **not the only failure**: independent cell 1 also fails win coverage/tails. Low win probability, discreteness and skewed rare outcomes require separate diagnosis. The six-cell replay does not isolate those mechanisms causally or justify adopting a particular replacement estimator. Regime cell 34's high coverage is a passing control, not proof of nominal behavior everywhere.

## Next tasks in order
1. Independently review this evidence and develop a bounded **alternative statistical-method design**, covering serial dependence plus rare/discrete/skewed outcomes. Use non-reserved synthetic development only; preserve the rejected method/version and frozen protocol as dated evidence. Do not change thresholds, silently edit the existing manifest, remove failing stress families or select a floor from this diagnostic.
2. Review [Windows capability design](../plans/2026-09-30-windows-calibration-support-design.md). Official support is still blocked by hard address-space-limit equivalence and claim/directory crash durability. Commit-memory limits or successful rereads do not satisfy those requirements. Any platform implementation needs a concrete reviewed design and the operator's required build approval.
3. Only after a separately approved method/protocol and platform satisfy their contracts: exact-source review, test-only evidence, independent attestation and a separate explicit one-shot decision.
4. After valid reviewed calibration and validation, continue Step 6b minimum-data requirements; then remaining trial-ledger/benchmark/source/cost and real-data runner dependencies. No real-data evaluation, lockbox use or live path is enabled.

## Independent review
Independent numerical reviewer (runner_review, medium effort) checked every saved summary against production recomputation, all four floor masks and direct RNG-row/core equality at IDs 0, 255, 256, 9984 and 9999. No blocking defect found. Root inspected the generator, variance formula, counts and frozen thresholds separately. Full source commit and protected SHA-256 values are retained in the ignored source-provenance.json alongside the results; the original research script records its accurate abbreviated source rather than deriving a future HEAD. Documentation-only findings do not amend the canonical whole-runner attestation.

Independent final documentation audit (readiness_review, medium effort) matched all three retained evidence hashes, completed replay log and script scope, and checked STATE/HANDOVER/operator host corrections. No blocker found. This reviewer authored the platform draft; independent platform review was instead supplied by runner_review and root.
