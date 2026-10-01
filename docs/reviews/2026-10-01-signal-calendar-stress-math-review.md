# Calendar stress protocol: independent mathematical review

Date: 2026-10-01. Reviewer: independent GPT-6 Astra, medium effort. Scope: design only; no RNG, sampled study, calculator/source changes or market data.

Final reviewed draft: `docs/plans/2026-10-01-signal-calendar-stress-confirmation-protocol.md`, independently read and hashed SHA256 `4d5d1749c799d124129ced0e3def82af91ca6f61fcccdcca7fe7a0f8fd044255`.

Initial reviewed draft SHA256 `0044e58b86ed1490c11a402ac358c5f5f3a7e34bfcab720f9f66e747d42cc8ae` is retained below as pre-draw review history.

## Verdict: APPROVE revised bounded design, no sampled-study authorization

The finite-innovation laws, ratio targets, complete-footprint resource accounting, sparse limitation, separate confirmation boundary and binomial error control are mathematically coherent. The initial 4,096-replicate confirmation had a material acceptance-power defect. The revised 32,768-replicate proposal resolves that mathematical study-design finding without lowering any criterion or family allocation. Full-size runtime/artifact feasibility remains unproved and is explicitly required before RNG authorization under unchanged budgets. Approval does not authorize a runner build, sampled study or acceptance of the calculator.

## Exact independent checks

I evaluated the finite atom laws with Python Fraction arithmetic, without importing the generator or using RNG. All main raw targets equal zero and all paired targets equal -1/200. Exact strict-positive win targets:

| Profile | Win target |
|---|---|
| P1 | 1/4 |
| P2 | 7/12 |
| P3 | 121/256 |
| P4 | 9887/24576 |
| P5 | 1143/2048 |
| P6 | 3577/6144 |
| P7 | 74146261351971311/144115188075855872 |
| L1 | 7/12 |

P5/P6 atom probabilities sum to one and their signed means are exactly zero. Independent enumeration also confirmed the paired target accounts for selected benchmark exposure, rather than subtracting an unconditional benchmark mean.

The positive long-run variance premise has a short proof. Condition on all shared S,Q,J,G innovations and leave the independent per-trade epsilon signs random. For raw/paired score sums, conditional variance is sum(C_t V_t^2); hence variance divided by n is at least E[C V^2]>0. Finite dependence establishes existence of the long-run limit. For win scores, the corresponding lower bound is E[C * 1{-V<base<=V}]/4, with base=delta-a/3+a*Sprev+gamma*F+J. Every main/L1 law has a positive-probability straddle event. Exact selected-trade straddle probabilities are P1/P2=1/2, P3=7/16, P4=1695/4096, P5=1501/3072, P6=511/1024, and P7=50815815317021065/72057594037927936. L1 retains P2's selected probability and positive entry intensity. Effect controls omit win, and raw/paired retain the independent-sign variance proof.

Full-support P7 resource totals independently reproduced: n64,b16 gives 128 rows, 5,760 total footprint entries and 72,128 expanded entries; n128,b26 gives 256 rows, 11,520 total and 246,376 expanded. P7 n192,b34 needs 497,352 expanded entries and fails the cap. K2,W1,H1,n512 needs 459,776 and also fails. These are deterministic limits, not sampled failures.

Sparse arithmetic-emission upper bounds are 1-(49/50)^16 = 0.2762022794075042 and 1-(49/50)^26 = 0.408604564816681. The declared sparse-family restriction is honest and must remain in the final report.

Counts check: 52 total metric cells, 46 formal cells, 280 formal one-sided statements, 18 path families and 9,216 development paths. The initial draft had 73,728 confirmation paths; the final R32768 draft correctly requires 589,824 confirmation paths and 1,703,936 metric-cell evaluations. Metric sharing does not undermine Bonferroni; IID whole-path replicates are the relevant units.

## Resolved pre-draw finding: initial confirmation acceptance power

I inverted binomial tails using exact integer sums at each rational criterion and eta=1/5600, not floating-point beta quantiles. At R=4096 the acceptance boundaries are:

| Criterion | Exact integer boundary |
|---|---|
| Emission lower bound >=.99 | at least 4,077 emissions |
| Joint coverage lower bound >=.93 | at least 3,867 emitted-and-covered |
| Each tail upper bound <=.035 | at most 102 tail errors |
| Precision lower bound >=.90 | at least 3,754 precision-ready |
| Conditional coverage lower bound >=.94, when A=4096 | at least 3,904 covered |
| Detection lower bound >=.80 | at least 3,368 correct detections |

An ideal procedure with emission probability one and true coverage .95 has only 0.1895611935564752 probability of satisfying the single conditional-coverage criterion: 3,904/4,096 = .953125, above its true coverage. A true .025 tail satisfies its tail criterion with probability 0.5103188431208971. The .95-coverage procedure satisfies the joint criterion with probability 0.9598737897311417. Thus all-cell qualification probability is at most 18.96% even without assuming independence across cells. Simultaneous qualification is likely substantially harder.

Recommended correction: before sampling, explicitly review a larger confirmation replication budget together with attainable operating characteristics and the frozen resource/time limits, or explicitly accept and prominently disclose this severe false-rejection limitation. Do not quietly relax criteria, family allocation or limits after outcomes. The exact laws and thresholds need not change to recognize the issue.

## Revised R32768: exact independent operating-characteristic check

I repeated threshold inversion with streaming exact integer binomial sums and Fraction probabilities, without RNG, beta-quantile calls or production helpers. The fixed eta remains 1/5600. Final acceptance boundaries are emission >=32504, joint coverage >=30638, precision >=29684, detection >=26473, and each tail <=1029. Conditional coverage when A=32768 requires C>=30955; an actual random A requires its own exact cutoff.

For the hypothetical benchmark with emission and precision probability one, true coverage .95, each tail .025, and correct-effect detection probability .90, exact binomial calculations give the following displayed approximations: joint-criterion rejection 3.248505704089595e-33; conditional-criterion rejection 6.203600586669912e-6; each tail-criterion rejection 3.871209425966438e-13. Effect-detection rejection is negligible at this precision; it was retained as an exact rational in the sum, not replaced by zero.

The union bound across all 46 formal cells and four detection statements is 46*(joint_failure + conditional_failure + 2*tail_failure) + 4*detection_failure, approximately 0.00028536566260194265. Therefore overall qualification probability for that hypothetical benchmark exceeds .9997, without any cross-cell independence assumption. This establishes attainable confirmation behavior for an ideal procedure, not the actual estimator's coverage or runtime. The small development screen still has false-rejection risk; the final draft makes no ideal-power claim for it.

The final draft preserves the original finding, short-history and sparse limitations, all criteria and family allocations. It requires deterministic full-size resource feasibility before RNG, under the unchanged 7,200-second and artifact budgets, with no automatic reduction in R, dropped cells or budget rescue. This remaining engineering prerequisite is correctly a blocker to sampling, not a reason to claim the design was run successfully.

The cited NIST handbook was checked directly: its later exact-binomial interval section supports tail inversion; its earlier Wilson interval section is a different method. The random A denominator is compatible with exact conditional binomial inference because independent replicate pairs imply C conditional on A is binomial. Independence between metrics or cells is not required for Bonferroni.

## Approval limits

This review establishes deterministic target arithmetic and highlights study-design feasibility. It does not verify generator byte mapping, runner correctness, exact-binomial implementation, wall-clock feasibility, Windows cancellation/durability or finite-sample estimator coverage. Those remain later implementation and sampled-study prerequisites. No market eligibility, data floor, promotion, official stream authority or real-data authorization follows.
