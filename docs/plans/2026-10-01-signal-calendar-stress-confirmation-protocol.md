# Calendar uncertainty artificial-market stress and confirmation proposal

Date: 2026-10-01. Status: D39/D38-authorized design; hash-specific independent review and primary verification are recorded in the [review record](../reviews/2026-10-01-signal-calendar-stress-protocol-review.md). **No runner build or sampled study is authorized by this document.** Current calculator source `7d5d9f571221ed16baa7dadad8d21b48b0d51618`, SHA256 `ef28eeebb2c807bbbed2c707cd1e20a752d448b537646a7beea0426fe2828ec9`; [completed deterministic build](../reviews/2026-10-01-signal-calendar-subsampling-build.md).

## Purpose in plain English

The signal simulator records each trade's result. The calendar calculator asks how uncertain their average is. Its arithmetic is tested; its reliability is not. We propose invented histories whose true average is known exactly, including trades sharing market shocks and rare large outcomes. A calculator that misses the true answer, refuses most histories or gives mostly unusably wide ranges cannot qualify even for the limited artificial family below.

There are two later stages: a development screen that exposes failures, then an independent confirmation using new histories and the exact same calculator and rules. Both need a built/reviewed runner and separate sampled-study authorization. Neither stage uses real strategies, the lockbox, the old official streams or broker access. Passing would establish evidence only for the specified artificial laws, not a market confidence interval, practical minimum-data floor or strategy verdict.

## Frozen design choices and limitations

- One estimator, existing block rule `b=min{integer:b^3>=n^2}`, alpha1/20, all overlapping calendar slices, complete whole-trade entry attribution. No alternative search, clipping, recentering, winsorization, fitted block length or rerolling refusals.
- Seven dense stationary finite-innovation profiles, each with core n64 and n128 and raw/win/paired-excess metrics:42 main cells. Four effect controls at n128: baseline profile with delta=+1/25 and -1/25, raw and paired targets only. One additional sparse profile at both n values/all three metrics:6 explicit limitation cells. **52 total cells;46 formal qualification cells.** Sparse limitations cannot be pooled away or described as a generally accepted method.
- Complete source footprints and calendar warm-up/completion halos are retained. No sparse representation of required observations to evade a resource cap. These are generated completed-outcome records, not OHLC execution simulation, true exchange fills, actual costs or tax evidence.
- The sparse law satisfies the candidate's stationary finite-memory premises but is knowingly capable of zero-count-slice refusals. It remains an in-model limitation. It is excluded from the restricted dense-family qualification by prior design, not from the report. A dense-family pass cannot close sparse coverage/emission failures or M1-M4. No claim that all stationary finite-memory laws are covered.
- Nonstationarity/universe drift, long memory, infinite variance, unbounded holds/state and selective completion are outside this experiment's finite-law family. Their applicability declarations must refuse when unknown/false; no single-history detector is claimed. A later expanded sensitivity design remains required before broader method acceptance. This proposal does not pretend that this small screen exhausts the earlier design's challenge list.

## Exact law, target and stationary initialization

All innovations are independent across dates and independent families unless explicitly shared. S_t and epsilon_(t,s) are symmetric signs; Q_t is Bernoulli(p_v); optional G_t is Bernoulli(p_g); J_t has the tabled rational atom law. Each date has at most two symbols, identified s1/s2. Filled count C_t=G_t*(1+1{S_(t-1)=+1}); absent G means G=1. When C=1 emit s1, when C=2 emit s1 and s2. All symbols share S, F, V and J; only epsilon differs.

Define F_t=(sum S_(t+k), k=0..H-1)/H and V_t=v0+(v1-v0)*1{some Q_(t-m)..Q_(t-1)=1}. Gross synthetic outcome is kappa+delta-a/3+a*S_(t-1)+gamma*F_t+V_t*epsilon_(t,s)+J_t, with kappa=1/1000. Subtract that declared fixed invented cost exactly once to obtain raw Y. All records are before tax. Synthetic benchmark B_t=c+beta_p*S_(t-1)+beta_f*F_t, with c=3/1000, beta_p=3/500, beta_f=1/100. Paired outcome is Y-B. These benchmark/cost values are invented fixtures, not current Indian-market rates or authenticated benchmark samples.

For dense profiles E[C]=3/2, E[C*S_(t-1)]=1/2. Independent gating multiplies both by p_g. Thus the exact long-run selected-trade targets are:

- raw theta=delta;
- paired theta=delta-c-beta_p/3=delta-1/200;
- win theta=(1/3)*P(Y>0|Sprev=-1)+(2/3)*P(Y>0|Sprev=+1).

Strict zero is not a win. Compute win truth before sampling by exact rational enumeration over Sprev, K~Binomial(H,1/2), V's two states with high probability 1-(1-p_v)^m, epsilon's two signs, and J's atoms. F=(2K-H)/H. Collapse equal/zero-probability states; do not approximate truth by a very large simulation. This target is E[A]/E[C], not E[A/C] or the expected finite-history ratio. The gate's independence preserves the selected targets but not the chance of emitting a range.

Generate innovation indices directly over [-W,n-1+H], W=max(m,1), with complete per-trade source_sessions=[t-W,...,t+H], decision=t-1, entry=t, one exit=t+H and recognition=t+H. Core is [0,...,n-1], authorized source axis includes the entire halo. No zero-start recursion, burn-in truncation or terminal forced close. At decision time no future sign is used to select entry/count. Future signs affect completed outcomes only. Expected core IDs derive independently from the generated entry schedule before outcomes; no missing/halo-selected core record. No halo entrant is needed for this completed-outcome law, and that choice must be declared.

Each profile is bounded and finite dependent over a fixed innovation span, and thus has finite moments; stationarity follows from the shift-equivariant law on IID innovations. The runner build must also prove positive long-run variance for **each profile/target**, not assume it from individual outcome variance: exact finite-state covariance enumeration or an independent innovation variance bound is required before model declarations are stamped. Degenerate targets stay refusal controls, not silently replaced cells. Derivations and finite-precision generator equivalence must be independently checked before any draws.

## Exact profile manifest

Every profile uses delta=0 unless the effect-control row says otherwise. A dash means J=0. Low/high volatility equal means constant volatility (Q may still be generated by the fixed implementation contract). Fractions are exact.

| ID / challenge | a | gamma | H | m | v0,v1 | p_v | J law | p_g |
|---|---:|---:|---:|---:|---|---:|---|---:|
| P1 baseline shared shock | 0 | 1/100 | 1 | 1 | 1/100,1/100 | 1/8 | - | 1 |
| P2 endogenous counts/outcomes | 1/100 | 1/100 | 1 | 1 | 1/100,1/100 | 1/8 | - | 1 |
| P3 finite persistence/overlap | 1/100 | 1/25 | 8 | 1 | 1/100,1/100 | 1/8 | - | 1 |
| P4 clustered volatility | 1/100 | 1/100 | 1 | 4 | 1/500,1/25 | 1/8 | - | 1 |
| P5 rare positive magnitude | 1/100 | 1/100 | 1 | 1 | 1/100,1/100 | 1/8 | +8/25 with1/512; -1/100 with1/16;0 otherwise | 1 |
| P6 rare negative magnitude | 1/100 | 1/100 | 1 | 1 | 1/100,1/100 | 1/8 | negative of P5 | 1 |
| P7 long holds/persistent volatility | 1/100 | 1/25 | 32 | 8 | 1/500,1/25 | 1/8 | - | 1 |
| L1 quiet sessions/bursts, limitation | 1/100 | 1/100 | 1 | 1 | 1/100,1/100 | 1/8 | - | 1/50 |
| E+/E- correct-effect controls | P1 | P1 | P1 | P1 | P1 | P1 | P1 | P1 |

P5 mean J=(8/25)/512-(1/100)/16=0; residual atom probability479/512. P6 has mean zero too. E+ sets delta=1/25, E- delta=-1/25; the paired targets become7/200 and -9/200. Effects are deliberately large invented controls, not realistic expected profit. Correct-direction detection compares raw/paired endpoints to zero; both positive and negative true targets have their specified direction. Null raw P1 is zero; paired P1 is -1/200, so truth coverage and paired positive declarations are reported distinctly.

For L1, any particular b-window is empty with probability(49/50)^b, so arithmetic emission is at most1-(49/50)^b. n128 gives b26 and upper emission about0.409; n64 gives b16 and upper about0.276. This known limitation exists without drawing a single history. Reporting a conditional coverage number from its survivors cannot erase it.

## Deterministic resource feasibility, current Windows PC

Maximum K=2. Full support, not expected occupancy, controls budgets. Rows<=Kn. `_source` total footprint bound is Kn*(W+H+5). Expanded bound is K*(W+H+6)*b*(n-b+1), because each complete source tuple has W+H+1 dates and one exit. At n64 b16,q49; at n128 b26,q103. Worst P7 gives rows256, total11520, expanded246376, inside4096/65536/262144. n64 worst expanded72128. Largest source tuple41 dates fits4096; technical ceilings are unchanged.

Dense two-stock n512 even with W=H=1 requires459776 expanded items and cannot qualify under this implementation. P7 n192 would exceed the cap. Retain these as deterministic resource-refusal controls, not sampled calibration cells. The study cannot identify a useful large-sample market floor from these short histories. A future resource redesign requires its own review/build; do not pre-authorize it here.

Proposed parent-enforced research phase limits: one worker, development1800s, confirmation7200s, committed evidence <=2GiB per phase, bounded256MiB write buffer, one replicate in worker memory, intended aggregate working-set ceiling2GiB. Windows measurement/cancellation are research operational limits, **not the unproved official hard address-space/durability contract**. Runner review must make enforced versus monitored controls explicit. Resource preflight must finish before RNG. No timeout extension, parallel heavy workers, weaker limits, unrecorded pilot draws or platform migration to rescue results.

## Measurements and proposed research criteria

Raw/excess requested full width=1/50 (two percentage points of return); win width=1/5 (twenty percentage points of win probability). These are project-owned **research informativeness requirements**, selected before results to reject mostly useless ranges. They are not economic loss limits, market-ready precision or amended goal.yaml thresholds. They can be reconsidered only in an append-only new research version that acknowledges all exposed results.

For every replicate and metric, distinguish A=arithmetic endpoints exist (`CalendarCandidate` or `CalendarInsufficientEvidence`), P=precision-ready (`CalendarCandidate` only), C=A and lower<=truth<=upper, Tlo=A and truth<lower, Thi=A and truth>upper. Then C+Tlo+Thi=A exactly. Refusal contributes zero to these counts; insufficient contributes to A/tails/coverage but not P. Detection D=P and interval excludes zero in the correct effect-control direction. Never count refusal or an infinite/nonfinite interval as covered. Preserve unclipped candidate endpoints. Count all actual reason codes.

Proposed one-sided confirmation criteria for each of42 main cells and4 effect cells:

| Statement | Required bound | Meaning |
|---|---:|---|
| arithmetic emission A/R | lower>=.99 | almost all dense histories produce arithmetic |
| joint coverage C/R | lower>=.93 | refusals cannot inflate coverage |
| lower tail Tlo/R | upper<=.035 | cannot hide misses on one side |
| upper tail Thi/R | upper<=.035 | same for the other side |
| precision-ready P/R | lower>=.90 | broad/insufficient ranges cannot dominate |
| coverage conditional on A: C/A | lower>=.94 | emitted ranges must retain coverage |
| correct-effect detection D/R,4 effect cells only | lower>=.80 | visibly signed invented effects are detectable |

These tolerances are research diagnostics: nominal estimator confidence is95%; a94% criterion is a1-percentage-point screening tolerance, **not proof of95% nominal coverage**. Joint93% and99% emission, plus both tails, guard against selective refusal and lopsided errors;90% precision and80% control detection guard against uninformative success. They do not supersede any previous frozen official criterion. Sparse L1 reports the same measurements and indicative criteria without entering the restricted dense-family pass; its incompatibility with99% emission remains a named failure of broad applicability.

42*6+4*7=280 formal one-sided statements. Allocate family error0.05/280=1/5600 to each, fixed even if a cell fails. Compute conservative exact binomial bounds: L(k,N)=BetaQuantile(eta;k,N-k+1) for k>0, L(0,N)=0; U(k,N)=BetaQuantile(1-eta;k+1,N-k) for k<N, U(N,N)=1. Use A denominator for conditional coverage, refuse a criterion at A=0. Replicates are IID whole histories; same-replicate metric correlations do not invalidate Bonferroni's union bound. Overlapping calendar roots are never replication trials. Numeric beta inversion/rounding needs independent verification against binomial-tail inequalities at the decision boundaries; do not certify an optimistic floating-point crossing.

Primary source for exact binomial tail inversion: [NIST confidence-interval handbook](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm), checked2026-10-01. Bonferroni allocation and all acceptance tolerances here are project-owned design choices, not quantities attributed to that source.

## Two stages, independent streams and stopping

Proposed development R512 per cell, then confirmation R32768 per cell (52*512=26624;52*32768=1703936 metric-cell evaluations). A path feeds all metrics for its profile/n; effect paths feed raw/paired. Thus there are18 path families:8 profiles*2 spans plus2 effects, yielding9216 distinct development paths and589824 confirmation paths. Do not equate metric-cell evaluations with distinct drawn paths. Final runner manifest must state both counts and deterministic path sharing. No trimming the profile list, selecting a passing n, averaging cells or tuning against exposed histories.

**Pre-draw review correction:** the initial R4096 draft had poor confirmation power: even an ideal95%-coverage procedure with A=1 needed3904 covered out of4096 for its conditional criterion, giving only about18.96% chance of passing that single test. Each true2.5% tail passed its<=102-error test only about51.03% of the time. This was a design defect caught before any sampling; no threshold or family allocation was weakened. R16384 still has a loose all-cell rejection bound. At R32768 the fixed cutoffs are A>=32504, C>=30638, P>=29684, D>=26473 and each tail<=1029; conditional coverage at A=32768 needs C>=30955 (recompute exact cutoffs for actual A).

Primary beta/binomial-tail calculations and independent exact-integer binomial sums agree: for the **hypothetical** ideal benchmark A=P=1, coverage.95, both tails.025 and effect detection.90, the all46-cell union rejection bound is below0.000286, so pass probability is at least0.9997. This establishes the proposed confirmation test is not structurally hostile to that ideal benchmark. It predicts neither this calculator's performance nor acceptance of a method barely satisfying a tolerance. Development remains a deliberately small conservative screen; false rejection is possible and no power claim is made for it.

The larger replication proposal is conditional on deterministic full-size runtime/artifact feasibility **before any RNG authorization**. In the later runner build, use fixed invented worst-case records and bounded serialization tests, with an independently checked upper bound for all589824 paths/1703936 evaluations and margin within the unchanged phase limits. Document measured versus projected quantities and enforce the parent deadline/file cap. If that proof is missing or does not fit, the study remains blocked; do not lower R, relax criteria, lengthen deadlines, drop cells, add workers or thin evidence automatically. Any different resource design needs a separately reviewed amendment before draws.

Development is descriptive: every formal-cell point rate must meet its corresponding criterion before confirmation is eligible; compute/report simultaneous bounds too but do not claim confirmation from that screen. Sparse limitation cells do not qualify for a dense-family pass and their report is mandatory. A complete failing screen rejects this protocol's candidate; no confirmation draw. ERROR is an incomplete retained attempt, not a statistical verdict. Confirmation uses all frozen criteria/bounds, same estimator/profiles/widths; any failed cell rejects the restricted-family qualification. Complete all cells for a statistical report even after a failure; safety/resource/I/O/source mismatch stops immediately with retained incomplete status.

Named namespace `icarus/calendar-ratio-research/v1`. Separate development and confirmation identities derive from explicit phase root256-bit seeds, cell/profile/n/replicate identity and fixed generator version. A later independent reviewer chooses and seals the confirmation root after development source/protocol freeze; no held confirmation root is created or consumed now. Protocol/runner must bind seed commitments, byte-to-rational-atom mapping, draw counts and exact rejection-sampling behavior before startup. No global RNG, reserved stream imports, cross-replicate recycling, shared paths across development/confirmation or redraw after refusal. Fresh PRNG seed separation is computational experimental independence, not a proof of mathematical IID or a secret-market holdout.

Every startup is an append-only counted research attempt, separate from real-strategy trial accounting and from the official one-shot runner. Claim attempt before RNG; persist complete terminal state and all errors. A crash/timeout cannot resume/redraw that attempt or label the replacement untouched. Any proposed retry needs a recorded amendment and review of exposed seed/artifact scope before separate approval. Source/protocol changes after viewing outcomes are new exposed versions, never confirmation of the old one. No automatic retry, confirmation continuation from a mere file, or borrowed official completion authority.

## Evidence and later implementation acceptance

Before runner implementation, approve this concrete reviewed scope. Before sampling, independently verify exact runner source, protocol/manifest/target-table hashes, resource preflight, generator-law mapping, numerical binomial boundaries, attempt accounting, phase/draw boundary and Windows cancellation/artifact behavior. Obtain a separate explicit sampled-study decision. No official canonical attestation is claimed by this research design.

Retain manifest and analytic truth derivations; per-path generated innovation/outcome/ID digests with replayable source coordinates/atom inputs; per-metric return sums/counts, endpoints, mathematical/display widths, result/reason, coverage/tails/detection; exact source identities; all startup/terminal/parent limit evidence. Use deterministic canonical rational and Decimal encodings. Save enough to replay selected **and failing** paths independently; summaries alone are insufficient. A verifier must independently recompute aggregation, truth membership and all280 rate bounds from retained records. Archive every earlier ERROR and statistical failure.

Runner tests must establish complete target enumeration, all source events/IDs, next-session decision/entry, strict-win ties, paired target difference, exact block/resource budgets, sparse refusal, finite endpoint/width checks, counter identities, sentinel always-refuse/always-wide/missing-truth/one-sided intervals, malformed declarations/footprints, schema/source mismatch, failed persistence, timeout and prevention of confirmation after failed development. These are invented deterministic checks first; no pilot RNG hidden in tests. Ordered simplicity/engineering and independent mathematics review precede a source commit; post-commit bounded defect checks follow the existing operator convention.

## Present decision and next milestone

This proposal makes a **restricted artificial-family** qualification concrete while exposing known sparse and large-span limitations. It neither closes Task3a/M1-M4/F48 nor supplies a data floor. Original Step6b/7/8 order, source/benchmark/accounting/trial prerequisites, official Windows resource/durability blockers and inference_enabled=false remain unchanged. No config, official manifest/stream, real-data evaluation, lockbox or broker/live path changes.

After independent written review and primary verification, present the calculator-test plan in plain English. The next proposed implementation unit is its isolated synthetic research runner and deterministic tests. Sampled development/confirmation remains a later explicit decision after exact-runner review.
