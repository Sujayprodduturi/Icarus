# Signal uncertainty method: bounded research design
Date: 2026-09-30. Source inspected: `e2cba4d`. Status: isolated research build/screen approved by operator D32; no product method adoption or protocol amendment approved.

## 1. Purpose and approved scope
Icarus is in Phase 1, Task 3a Step 6a: establish trustworthy signal uncertainty before strategy evaluation. The operator approved continuing the method design after the [non-reserved failure diagnosis](../reviews/2026-09-30-test-calibration-failure-diagnosis.md). The goal is coverage that survives dependent, discrete and skewed synthetic outcomes while still conveying useful information. A method agreeing with its formula oracle is necessary but not sufficient.

This document recommends **one isolated research candidate**, with the current CR2 method as its reference. It is not a new official statistical protocol. Keep the original estimator, frozen manifest/digest, gates, floor ordering, reserved seeds, counted runner and `inference_enabled: false` unchanged. No real panel, lockbox, broker, Windows platform backend or product inference API is included.

## 2. Alternatives and recommendation
| Approach | Benefit | Failure or cost in this setting | Decision |
|---|---|---|---|
| Bartlett HAC with fixed-bandwidth-fraction critical values | Includes covariance between time blocks and accounts for uncertainty in that covariance estimate | Asymptotic assumptions; rare outcomes, only 24 blocks, uneven counts and regimes can still fail | **One research candidate** |
| Time-block bootstrap/subsampling | Preserves local dependence if sums/counts and paired outcomes move together | Block length and studentization choices; cannot invent unseen rare events; higher compute cost | Keep as fallback design, do not implement now |
| Distribution-free bounded-outcome bounds | Attractive finite-sample guarantee when assumptions hold | Dependence needs its own bound; wins are bounded but Gaussian benchmark excess is not; observed min/max supplies no valid range | No universal replacement |

[Kiefer and Vogelsang, revised 2005](https://kiefer.economics.cornell.edu/newasym2.pdf), equations 5-6, section 4.3 and Table I, provide kernel/bandwidth-dependent asymptotic critical values. Their functional-CLT assumptions and strong-dependence caveat do not prove finite-sample validity here. [Politis and Romano's stationary bootstrap](https://users.ssc.wisc.edu/~behansen/718/Politis%20Romano.pdf) supplies a temporal resampling approach, not a guarantee for this nonstationary/sparse trade process. [Ibragimov and Muller](https://www.princeton.edu/~umueller/tstat.pdf) require approximately independent, Gaussian group estimates; simply merging a few blocks cannot certify those conditions. Sources checked 2026-09-30.

## 3. Completed design probe, not candidate selection
A throwaway comparison on this Windows PC used non-reserved seed **2026093011**, four cells (28, 1, 30, 34), 2,048 replicates each, three paired metrics, and five fixed comparators: original CR2; CR2 with adjacent pairs/quartets merged; Bartlett lag-2/lag-4 score covariance with heuristic `t(G-1)` critical values. Roster and addresses were written before draws. The heuristic covariance uses `G/(G-1)`; **it is not fixed-b inference** and none of these comparators is adopted. The probe did not evaluate the proposed fixed-b candidate.

Completed 8,192 replicates and 122,880 metric comparisons in **25.531 seconds**, exit 0. Dense-kernel quadratic forms matched lag-sum formulas on eight replicates per cell/metric; kernel eigenvalues were nonnegative to tolerance.

| Cell/metric | Original CR2 | Merge four blocks | Lag-4 HAC with ordinary t |
|---|---:|---:|---:|
| 28 serial, raw coverage | 1,622 / 2,048 | 1,849 / 2,048 | 1,690 / 2,048 |
| 1 independent rare-win, win coverage | 1,891 / 2,048 | 1,941 / 2,045 | 1,822 / 2,048 |
| 30 rare magnitude, raw coverage | 1,731 / 2,048 | 1,739 / 2,048 | 1,697 / 2,048 |
| 34 regime control, median win width | 0.308168 | 0.721388 | 0.540478 |

These are exploratory fractions and widths, not full frozen-gate judgments. Coarsening changes the original method's geometry and loses independent blocks. Its apparent improvement does not repair rare-magnitude behavior. The ordinary-t HAC comparator can worsen rare-win coverage, so adding covariance terms alone is not a sufficient design.

Ignored retained files: `var/verification/2026-09-30/method-design/{probe.py,preregister.json,result.json,probe.log,attempt1-error.log,attempt-ledger.jsonl}`.
- Corrected probe SHA-256: `634fa89a9ec8ac1f22fe943c6bfac061097c86d2c7083fb0182de1daab077eaa`.
- Preregistration SHA-256: `c80fe55e04a94dcb4381b54e0191aa875015e6ff1c0009b62cc1f04dae1a2d1e`.
- Result SHA-256: `599c25122ae6d33f7ab2fb008ef364cd22656438cd957c355cf275e8d6ec90ef`.
- Completed log SHA-256: `0ac748feb8c3c4f9747d1163dd48d823f6f2d9415391543fe257bf0526bd3cbd`.

The first attempt failed during its first replicate because the scratch script used an incorrect excess attribute name; ten raw/win comparator evaluations had been computed internally, no complete replicate/result was published. That attempt is retained. Correction changed only the attribute mapping, not methods/seed; the same research stream was rerun. An elapsed-time transcription error in the local attempt ledger has an append-only correction; `result.json` is authoritative. These are research attempts, not a real-strategy trial or a claim on an official stream. Prior diagnostic outcomes informed this design: a new seed does not make the design itself blind or confirmation evidence.

## 4. Exact candidate to investigate
Working research name: `calendar-block-bartlett-fixed-b-v1-dev`. This is chronological **trading-session block** time, not elapsed wall-clock calendar time. No product method/version is assigned.

Inputs: a complete canonical source-session/fold span, immutable study origin, original entry-session coordinates/holdings, unique paired trade observations, and the declared geometry. No DGP cell/family, true correlation, true target, seed or outcome-favourability flag reaches the estimator. Targets exist only in the evaluator.

Retain `L = max(63,3H)` and original origin/block IDs for input geometry; do not replace them with the coarsening probe. Fold geometry includes the first through last blocks intersecting that declared source span, including empty observed trading blocks and partial edge blocks. Empty sessions are not missing prices; weekends/holidays do not become fictitious sessions. Missing or ambiguous canonical source observations refuse. Blocks 0 and 10 must remain ten blocks apart. Do not strip empty prefix/suffix blocks or infer source-span endpoints from first/last trade. Dynamic H/L is recorded as observable geometry and assumption stress; it supplies no independence certificate.

For the synthetic screen, fix analysis-entry-window endpoints before drawing: a fixed profile spans source indices 0 through len(entry_counts)*geometry.l - 1; a dynamic profile spans 0 through parameters.source_span - 1. Compute candidate grid endpoints from those declared indices and each replicate's recorded L/origin. Any synthetic holding completion beyond that entry window is labelled completion-only source extension and does not add empty HAC blocks or change b. This is an explicit synthetic analysis convention, not permission for a real trade to use unavailable exit prices. A future real adapter must use its pinned full-source/fold span and certify all exits independently. Never derive window bounds from first/last realized entry or outcome-selected exit.

For each metric with N valid trade observations:
- `m = sum(y_i)/N` (trade-weighted, never an equal-weight mean of occupied-block means).
- Across the G original grid blocks, retain counts `n_g`, sums `Y_g`, and scores `S_g = Y_g - n_g*m`; observed empty blocks have count/sum/score zero.
- Require N >= 2, at least two occupied blocks, G >= 8; cap scratch input grid at 4,096 blocks and refuse rather than compress or allocate more. These are research bounds, not accepted data floors.
- Set `M = floor(G/4)`, `b = M/G`, and Bartlett weights `w_h = 1-h/M` for 1 <= h < M.
- `V = [sum_g S_g^2 + 2*sum_(h=1..M-1) w_h*sum_(g=h..G-1) S_g*S_(g-h)]/N^2`.
- Use no CR2 leverage correction, G/(G-1) multiplier, prewhitening, shrinkage, automatic bandwidth choice, negative-variance clipping or borrowing of another metric's variance.
- Use Table I's **97.5th percentile** cubic for two-sided 95% bounds: `c(b)=1.9600+2.9694*b+0.4160*b^2-0.5324*b^3`. For G=24, M=6, b=.25, `c=2.72003125`. This is a fitted asymptotic approximation, not an exact finite-sample quantile. Refuse outside its cited fit domain b in [.02,1].
- Research interval: `m +/- c(b)*sqrt(V)`. Refuse non-finite arithmetic or V <= 0. Store untrimmed endpoints; win-rate display may intersect [0,1], but coverage uses untrimmed endpoints and widths report both forms.

Each filled trade is aggregated across partial exits before input. Win is strictly-positive raw net return. Raw/benchmark/excess remain paired at identical identities and weights. Preserve component-specific refusals and whole-cohort certified matching requirements for any future real excess return; synthetic paired benchmark values here are not real match certificates. No intervals for medians/quantiles, Sharpe, portfolio equity or promotion states.

Unequal or outcome-dependent trade counts can violate the paper's homogeneous derivative/partial-sum assumptions even with this score formula. Regime changes and sparse grids likewise may violate assumptions. Their stress profiles stay in the experiment and failures remain visible; do not filter them using latent parameters or call the design universally robust.

## 5. Smallest next implementation unit: isolated research comparison harness
Proposed tracked scope: `scripts/research/signal_method_probe.py`, pure research helpers/types and focused research tests, plus a dated research protocol/evaluation ledger and summary. No imports from these files into `icarus` or the counted runner; no package/dependency update. Exact file layout and execution plan follow operator review of this spec.

One method and one reference only: candidate above versus original CR2 on identical outcomes. Freeze all source hashes, method coefficients/formula, roster, RNG-address rules, environment versions and run count before first evaluation. Use non-reserved development seed **2026093012**; it has not been drawn in this work. Hard-refuse both old reserved seeds and any official output location.

First screen: all **45 calibration profiles x 1,024 replicates x three metrics**, including support/dynamic/unequal/burst/overlap/regime cases. Generate via unchanged pure equations with original 256-row component addressing; this is a prefix development sample, not the full phase. Emit every generated/emitted/refused count and reason, each tail, joint coverage, interval widths, bias, and per-cell pairing. No global averaging to hide failures, no winning method per cell, no floor selection, no official PASSED/FAILED schema or completion authority.

Declare descriptive family accounting now: for the 45-profile comparison use alpha=.05/(2 methods*45 profiles*3 metrics*5 rate checks)=.05/1350. For the three Gaussian informativeness profiles use the same five rate checks with alpha=.05/90. Widths/bias/correct-direction sensitivity are descriptive measurements, not additional accepted hypotheses or a product power gate. Gaussian controls use IDs 100001/100002/100003 for means 0/+.01/-.01, PCG64 SeedSequence(2026093012,spawn_key=(control_id,0,chunk_id)), four 256-row chunks of 192 normal values in declared block/trade order, scaled by .02 and shifted by the control mean. Constant benchmark requires no RNG component. No control ID collides with the original profiles; targets and control labels remain evaluator-only.

Reuse production CP primitives for descriptive rate uncertainty; distinguish point fractions from adjusted bounds. Do not call the fixed-10,000 summary verifier with a 1,024 count. The old absolute-emission cutoff cannot be satisfied by this screen and is reported **not evaluated**, not passed. Screen completion and formula checks are the only harness acceptance, not statistical-method acceptance.

Predeclare informativeness controls independent of coverage profiles: 24 blocks x eight independent Gaussian raw outcomes per block, sigma .02, means 0/+.01/-.01, constant benchmark .002, and wins derived from signed raw values. Each control has 1,024 reps and separately addressed streams. Known truths (including Gaussian win probabilities) reach only evaluation. Record both tails and correct-sign zero exclusion, raw/excess widths and win widths, plus emission. Publish these measurements without setting a product power/width threshold after seeing them. Any later acceptance limit must be specified and independently reviewed before its confirmation draw. Inject two deliberately vacuous stub candidates into deterministic harness tests: one always returns unbounded raw/excess intervals, the other always returns the full [0,1] win interval for every nonempty informativeness control. Reject the first for non-finite endpoints; flag the second as candidate-level NON_INFORMATIVE when every emitted win interval across those controls has clipped width exactly 1. An occasional legitimate clipped [0,1] interval is retained and counted, not individually rejected. This predeclared negative control supplies no product width/power acceptance limit; high coverage alone never authorizes adoption.

Windows scratch envelope: one foreground process, 300-second wall-clock supervisor deadline, scratch output only, bounded 256-row cache and <=4,096-block grid. No claim of Linux resource/durability equivalence; never change system settings or create an official claim. If a configured development run errors/times out, record it as an attempted evaluation, retain partial evidence, and stop; a repair/rerun is explicit research history, never a restored untouched stream.

## 6. Acceptance and review before running the screen
Unit/failure tests and an independent mathematical oracle must cover:
1. Small hand-computed scores and Bartlett quadratic form vs independently built dense kernel; matched polynomial coefficients, kernel endpoint at h=M, b/domain boundaries and G=24 critical value.
2. Unequal counts retain the trade-weighted mean; empty grid/gap sentinel distinguishes IDs 0/10 from 0/1; original fold origin and edge blocks do not move with first trade.
3. Permutation of row order/within-session order leaves values unchanged. Same-block date movement is invariant only if holdings and span remain fixed; changes in H/L are not falsely asserted invariant.
4. Zero variance, empty/one-occupied/too-small-grid, non-finite/overflow, invalid axes, duplicate IDs, missing synthetic benchmark or mismatched pairings refuse with stable component-specific reasons. Real-data inputs and any attempt to treat synthetic paired numbers as a real match certificate are rejected.
5. Estimator cannot access true DGP labels/targets or RNG; target-swap changes evaluation only. Protected source/config remain identical; both reserved-seed and official-path traps fire before RNG/write.
6. Research ledger records author, candidate version, protocol/source hashes, every initial run and repair, addressed prefix and its evaluation exposure. Interrupted output is explicitly incomplete, no credential/network/broker/real Panel import occurs.
7. Deterministic infinite-width/full-win-range sentinel is rejected as non-informative by harness audit; statistical method quality remains unproven even when formula tests pass.
Run focused tests, Ruff/mypy for the new scope, existing estimator/parity/simulator regression as appropriate, then independent numerical/safety review. Existing golden synthetic characterization must remain unchanged.

## 7. Decision boundaries after the screen
If gross undercoverage/tail imbalance or uninformative widths persist, report rejection of this development candidate and propose the next method design; no parameter rescue on the same data disguised as validation. If promising, require a new dated full development/confirmation design, with predetermined width/power criteria, full failure families and held-back research-stream ownership. The pilot does not authorize that later experiment.

Any future official replacement requires an explicit versioned design/protocol decision (method/geometry/schema/integrity/trial exposure/stream ownership), while retaining this original frozen protocol and its untouched reserved streams as history. No automatic reuse of the old one-shot seeds, no silent manifest overwrite and no weakened promotion/statistical threshold.

Windows official startup remains independently blocked by address-space-limit equivalence and durable claim/directory ordering. Statistical research is useful now but does not close those platform gaps. Step 6b and later benchmark/trial-ledger/real-data work remain gated as recorded in STATE.

## 8. Review record
Independent safety/governance reviewer (readiness_review, medium effort) approved this proposal for operator review after verifying four retained hashes, every displayed count/width and partitions, source/time identity, temporal/pairing/history boundaries and primary coefficient/domain definitions. Its non-vacuity clarification is incorporated above. Independent numerical reviewer (runner_review, medium effort) approved this as a research proposal, verifying primary coefficients/critical value, trade-weighted normalization, hand-built dense/lag equality, hashes and count partitions. Its source-span, descriptive-family and control-address clarifications are incorporated above; these explicit synthetic conventions still require implementation-plan tests. No screen or method adoption is approved by either reviewer. Operator approval requested is for this concrete isolated research scope; it supplies no official draw, method adoption, inference enablement or live authorization.

Operator D32 explicitly approved building the uncertainty mathematics on 2026-09-30 after the plain-English roadmap explanation. The isolated implementation plan is 2026-09-30-signal-method-research-implementation.md. The older review-stage wording above is dated history; D32 approves the bounded research implementation and Windows screen, with all official/product boundaries retained.
