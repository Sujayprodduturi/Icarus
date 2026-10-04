# Calendar-score v2 protocol independent review

Date: 2026-10-04. Reviewer: focused independent agent. Initial verdict: REVISE BEFORE BUILD; STOP before study draws.
Reviewed plan SHA256: `69d9b716334711f50f71023da40840f67430b6ad33aceba1d4abc76e55e0ac4a`.
Scope: AGENTS.md, OPERATOR D41-D44, current HANDOVER/STATE, the protocol, laws/score/evidence source and old statistics/runner interfaces. No study PRNG, held roots, market files, secrets or official streams were accessed. Only this review file was written.

## Findings

1. **P1 — Excess support centering is ambiguous and its literal replacement is wrong.** The instruction to replace `a` by `a-BENCHMARK_PREVIOUS` must apply only to the variable coefficient, not the `-a/3` centering term. Freeze center `delta-a/3-BENCHMARK_CONSTANT`, radius `abs(a-BP)+abs(gamma-BF)+max(v_low,v_high)`, then add jump extrema. Actual P1 excess support is [-19/1000,13/1000]; replacing the centering shifts it +1/500 and excludes legal outcomes.
2. **P1 — Exact stream framing is not frozen.** Specify identity byte serialization, root inclusion, counter width/start/overflow, SHA digest word order, and rejection threshold. Distinct semantic tuples must have distinct encodings. Fixed independent test vectors must precede any draw. A version name and big-endian words alone do not identify a reproducible stream.
3. **P1 — Preflight must measure production generation cost.** Constructed-atom replay plus disk speed does not measure billions of SHA words, rejection mapping and packing. Benchmark the full production generator using a separately named deterministic test domain and fixed non-study inputs, with no counted study phase/seed. Include generation, replay, endpoint evaluation, bounded canonical serialization, fsync policy and verification projections under the twofold margin. Failure leaves the experiment undrawn.
4. **P2 — The 512-path development screen has poor conservative operating power.** At exp(-5), a directional cell passes <=5 misses with probability0.8648514260; joint coverage passes with probability0.8585971128. No healthy familywide lower bound follows by a union bound. Do not use an independence product across dependent metrics as actual whole-study power. Resolve before draws. Primary's proposed8192 development amendment has a conservative union rejection bound0.03160225269 using the calculator's rational bound, before any data.

## Independent numerical and exact checks

Nine formal families produce25 formal metrics,9 joint cells and4 detection cells:25*3+9+4=88 statements and eta=1/1760. L1 contributes3 diagnostic metrics; total28 per set of10 histories. Original512 development gives5120 paths/14336 metric evaluations;32768 validation gives327680 paths/917504 evaluations. Proposed8192 development gives81920 paths/229376 evaluations.

Exact support widths (raw,win,excess): P1/E+/E-=(1/25,1,4/125); P2/L1=(3/50,1,7/250); P3/P4=(3/25,1,11/125); P5/P6=(39/100,1,179/500); P7=(9/50,1,37/250). E families omit win formally. All dense families satisfy the exact margin-adjusted eligibility inequality; smallest eligibility ratio is P7 raw~1.01135802469. L1 remains ineligible for formal selected-output guarantees despite sufficient nominal span.

Payload lengths in profile order P1,P2,P3,P4,P5,P6,P7,L1,E+,E- are2050,2050,16393,8197,32770,32770,131112,2050,2050,2050 bytes. Total231492 bytes/set. Original development payload118523904 bytes; proposed8192 development1896382464 bytes; validation7585529856 bytes (7.0645751953125GiB). These exclude metadata, results and audit overhead; explicit bounded overhead remains a pre-draw gate.

At N32768 the exact acceptance cutoffs are coverage/joint>=31258, directional misses<=270, effect detection>=29668. Independently summed integer binomial numerators at rational p=19/20,1/100,9/10: multiplying each accepted-tail numerator by1760 is <=d^N, while the adjacent less favorable count is >d^N. Independent SciPy tails at accepted/adjacent counts are respectively(.000520192879,.000570224649),(.000549043610,.000675239888),(.000536893556,.000573531048). Equality and impossible cutoffs must be preserved in implementation.

The calculator's rational tail ceiling is1/sum(j=0..10,5^j/j!)=~.006831506312973183. With proposed development N8192, worst-case single-criterion failure probabilities are coverage1.96675e-106, directional.00062595198795, joint.00003385036580,effect1.23548e-116. Bonferroni rejection bound is.03160225269; hence assumed-model screen pass probability>=.9683977473. This is a conservative operating calculation, not an empirical prediction or real-data claim.

Lifecycle/resource design is otherwise directionally sound: append-only claims, all-path replay, source binding, independent approval before targeted cleanup, Windows durability limitations, explicit no-retry and no saved-PASS authority. Implementation must concretize schemas/size caps, fsync cadence, source-manifest closure, validation-root sealing, live authority binding, and failure receipts; no gate can rely on unchecked filename/status text. Scope remains artificial-only with inference disabled and Task3a/M1-M4/F48 open.

## Pre-draw amendment review

The primary amended the protocol before draws: development8192 histories/family,3GiB cap and21600s worker deadline; exact excess centering; SHA framing/counter/rejection; deterministic test-domain full-generator performance measurement; combined per-path metadata bound8192 bytes and16MiB phase records. Revised snapshot SHA256 `60e995227fdc6d208a357131ca42257fdc5689e09dd60d4daafafeda86796fe3` resolves findings1-4 subject to final atom-sign and strict detection definitions requested below. No evidence has been sampled to choose these changes.

Recomputed projected bounded phase sizes are2584248320 bytes development and10286661632 bytes validation, including fixed metadata allowance. Independently recomputed conservative validation rejection union bound is0.05925777717418133 (tail failure0.0011847360462192323 per directional cell; joint failure0.000002330540357745397 per family; cover/effect numerical tails underflow). Thus assumed-model whole-validation pass probability is approximately at least94.0742%; the numerical operating calculation does not replace exact decision arithmetic.

Requested final small clarifications: S/epsilon signs map uniform(2)==0 to+1 and1 to-1; Q/G apply p_volatility/p_gate; J uses listed cumulative half-open atom intervals. Detection means precision-ready AND lower>0 for positive effects or upper<0 for negative effects; endpoint zero is not detection. These make reproducibility and sign boundaries explicit.

## Final verdict

**APPROVED FOR DETERMINISTIC IMPLEMENTATION**, final protocol SHA256 `130569a78811e9ad4f9dcdb915410b3c350e137a78bc70974eb81ac4daf13b71`. Final bytes explicitly settle all atom mappings and strict detection boundaries and add the conservative operating calculations; the four initial findings are closed by pre-draw amendments. No remaining protocol blocker to this bounded build was found. This review does not approve an unbuilt runner or authorize bypassing exact-source, measured feasibility, complete verification, validation authority or cleanup gates. Study draws remain stopped until those gates pass; no sampled work occurred in this review. Prior initial verdicts above are retained as history.

Implementation review must still verify fail-safe resource monitoring of worker and verifier, heartbeat independence from heavy loops, bounded canonical schemas and all-path metadata, concrete fsync cadence and failure persistence, no-follow/exclusive file behavior, validation seed sealing and same-session authority, and source closure through cleanup. A failure in any of those gates retains evidence and leaves qualification false. Measured preflight must honestly reject infeasible generation/verification budgets; today's arithmetic establishes only storage/count feasibility and model-assumed statistical operating power.
