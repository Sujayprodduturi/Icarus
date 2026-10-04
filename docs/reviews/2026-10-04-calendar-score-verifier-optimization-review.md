# Calendar-score verifier optimization: independent plan review

Date: 2026-10-04. Approved plan SHA-256: `6b3f07957092dc70540dda253aa6fab1675b377d3682a278fd36fcf81874b217`, freshly checked from disk.

Verdict: APPROVED for the bounded implementation and deterministic comparisons described. No P0/P1/P2 design blocker found. This is not source approval, runtime qualification or sampled-lifecycle authority.

## Independent mathematics

For right-tail masses T_j, the next/current ratio is r_j=(n-j)a/((j+1)(d-a)). These ratios decrease with j. Whenever r_j<1, all omitted mass is at most T_j*r_j/(1-r_j), including the next term. The proposed integer expression is therefore a valid upper bound; the partial sum is a lower bound. Accepted-tail comparison must use the upper bound, while rejection can use a strict lower-bound comparison. Equality is accepted only when proved, otherwise continue to the full exact sum. At or below a nondecreasing region the geometric bound is unavailable and the recurrence must continue without applying it.

The adjacent mass T_(k-1)=T_k*k*(d-a)/((n-k+1)*a) is exact for k>0. Inclusive left tails reflect as P(X<=k)=P(n-X>=n-k), so the failing k+1 neighbor maps to right-tail threshold n-k-1. Boundary states require explicit treatment rather than division by zero.

A separate BigInt check exhaustively compared the proposed geometric bound against exact omitted sums for n=1..16, denominators2..8 and every interior numerator/index: 2,300 applicable remainder bounds passed. The adjacent-mass identity also passed throughout its valid domain. This is independent small-case evidence; registered large-cutoff and equality/fallback tests remain implementation acceptance conditions. The generic exact-Fraction API remains unchanged.

## Engineering and governance

The targeted changes follow the measured costs: cutoff proof, per-stream SHA prefix reuse and prompt child-exit waiting. Prefix state must remain per-stream and copied before adding the counter; hook behavior, rejection consumption, lane ordering and overflow refusal remain exact. Supervisor wait timeouts must preserve recurring and final resource/heartbeat/source/exit checks. No global cache, warm worker or omitted durability cost is approved.

The search is bounded to three batch sizes and declared exact-equivalent combinations. All attempts remain evidence; the selected configuration is only the best tested choice. Final three fresh supervised cold runs use the worst time, and all three must pass. Any mixture containing a failure also fails the stated all-three qualification rule; retaining and investigating such a result is required.

The unchanged ceiling675/1024 seconds, twofold32768-set projection and43200-second limit preserve the failed baseline honestly. Cold initialization, startup, full10 paths/28 outputs, actual receipt durability and final pre-result checks remain inside accounting. The previously disclosed accounting-record exclusion is unchanged. Source manifests must include this plan, and later source review plus independent verification of every retained final path/result is required before raw-only cleanup.

Full sampled authority/integration remains unbuilt; inference stays disabled. No real data, old held study, reserved stream, new experiment key or sampled draw is authorized by this approval.

## Ordered source review of the candidate freeze

Fresh filesystem hashes confirm verifier `acfb5e41e0649e10e242e1cb8102322789a0664a6546f8602e3b79dad580b110`, tests `bcd8111562068d56518f8b9f801e1238e9f7e0a9cd943045305ca1434b33b0e3`, and study `eb7f12dd6bc7982a0e05d952ab749de21537ca79744220fb25448cea7d2ad8e3`.

The ponytail simplicity pass found localized changes with no unused helper or unnecessary framework. The subsequent engineering/math pass found no blocker: `prove_cutoff_pair` validates bounded exact inputs, reflects inclusive lower tails correctly, retains the generic exact fallback outside decreasing-ratio geometry, uses an upper bound for accepted mass and a strict lower bound for its neighbor, and continues through exact equality when necessary. The 32-bit alpha numerator/denominator limit is a safe explicit refusal for the new helper; the generic exact-tail API is unchanged.

Per-stream SHA prefix state is copied before counter updates; buffered lanes survive prefix changes and custom digest hooks bypass the native fast path. Overflow is checked before generation/consumption. The new supervisor wait handles TimeoutExpired by resampling and retains final resource/heartbeat/exit checks. The study change only adds the reviewed plan to the source closure. Tests cover finite exact-tail comparisons, equality/reflection/fallback, registered visited-term counts51/8/61, partial lanes, prefix mutation, custom seams and timeout resampling.

Candidate source inspection passes. Final benchmark approval remains pending selection of the batch size and confirmation of its exact hash after the primary's serial diagnostic matrix. No performance qualification is inferred from source inspection.

## Selected source approval

Selected verifier SHA-256 `4eb95c7eb70afb65fa702130f472aed04292761031472c3e843df9e1e4a5416b` is freshly confirmed. Replacing only `BATCH = 4096` with its prior8192 value in memory exactly reproduces the reviewed candidate hash `acfb5e41...580b110`; no other source change occurred. Tests/study/plan hashes remain exactly those recorded above. The smaller batch remains within reviewed memory/word bounds.

The reviewer inspected `verifier-optimization/configuration-search.json` and independently recomputed its bounded-prefix medians from all45 retained measurements:2048=0.2510438s,4096=0.2508278s,8192=0.2516175s. Every measurement records exact28-result equality. The difference between batch sizes is negligible and provides no broad speedup claim. The two retained final comparison rounds show no alternative improvement; the declared stop rule is satisfied. These are in-memory diagnostics, explicitly not cold runtime qualification.

Verdict: APPROVED exact selected source for the three fresh supervised full10 cold benchmarks in `verifier-optimized-final-1`, `verifier-optimized-final-2`, and `verifier-optimized-final-3`, after required foreground regression/static checks pass. All three must pass the unchanged gate, with worst time reported. Every saved path/result still requires independent verification and dual receipt checks before raw cleanup. No sampled-phase authority follows.

## Iteration 1: all saved results accepted, all cold gates failed

Reviewer independently replayed every saved path in `verifier-optimized-final-1`, `-2`, and `-3` using the retained scalar SHA/naive integer oracle, with no project mathematical imports. Each run passed all10 byte histories,28 metric totals/truths/supports/endpoints/flags,1388952 word counts, summary/receipt/source/terminal and timing checks. Exclusive fsynced reviewer verification receipts were written to all three roots. Own oracle runtimes were1.9450853s,1.9398674s and1.9438828s; ending RSS remained below23MiB (not a peak claim).

All three bind payload `816a0ae0a31c0cf97bf3fd1aa309b063551951305b4dfaac78370db22759afc2`, index `9950e72afb3a7bc9e1927ca4868b8c34024098a639f436374e7b1b63a5203d66`, fixture terminal `b84d5c6ee246293e11e7b72448b5ac4255e30271f88d0180de30af32e0d99950`, and source manifest `78865861b9182865774c7ee197d5476129d3832a24811eff05c9c02ce4684adb`. Source closure matched before and after each replay.

Qualification remains FAILED: conservative times approximately0.7395501/0.7392889/0.7421762s project48,467.1554/48,450.0374/48,639.2594s, all above43,200s. The improved child-only times do not override full-boundary failure. Preserve all three failures and investigate the remaining startup/provenance costs without dropping their checks or amending the threshold. Reviewer permits raw-only cleanup of each exact231492-byte payload after the primary verification and identity/hash-bound cleanup protocol complete; no reviewer cleanup was performed.
