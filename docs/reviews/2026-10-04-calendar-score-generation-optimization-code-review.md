# Calendar-score exact-output optimization — code review

Date:2026-10-04. **APPROVED FOR FRESH SUPERVISED DETERMINISTIC MEASUREMENT ONLY.** No P0-P3 blocker found in the reviewed delta. Source SHA256 `58f483289f9175fec4f96153a1e7a377cc8c26e9d61a4a4e35fc8ef67b901f5e`; tests SHA256 `e11f12da2737e4378758264f7a2a2868883233ad9f63f687040c83e848e5915c`. Hashes independently read. Protocol remains unchanged at `130569a78811e9ad4f9dcdb915410b3c350e137a78bc70974eb81ac4daf13b71`.

## Ordered simplicity pass

Applied the retained ponytail-review instructions first. Lean already for this delta: batching, immutable peek/consume state and the scalar fallback each have an active purpose. The small digest helper permits injecting rejected words into the real optimized route, which a custom-source-only test would miss. No speculative sampled lifecycle was added. `net: -0 lines required.`

## Engineering, mathematics and safety pass

Applied the retained engineering code-review instructions second. Reviewed the complete source/test diff against the previously approved supervised preflight, checking all five proposal requirements:

- The six-column mapping uses big-endian unsigned64-bit words and explicit integer NumPy modulus/comparisons. Acceptance limit2^64 is explicitly treated as all-accepted rather than cast; denominator50 is compared against fitting uint64 threshold18446744073709551600. Jump indexes count crossed half-open edges and occupy bits5-6 without overflowing the frozen three-atom law.
- Peek returns immutable bytes and advances only the generated-block cursor; consume alone increments words_consumed. Buffer refill retains unconsumed suffixes; the overflow feasibility test runs before hashing, leaving state unchanged on an unfulfillable request. next_word still consumes exactly one logical word. Prefetch is not counted as an experimental draw.
- A rejected word causes scalar fallback before bulk consumption. Further shifted row/column mappings use the retained suffix and then new words in their original order. Only counter_overflow is caught for residual scalar consumption; unrelated errors propagate. Tests force actual optimized-route rejections at positions2,49148,49154 and a1024-rejection failure, as well as exact uint64 boundary values.
- Batches end after source row0 and each row65536 boundary before callbacks run. Callback refusal therefore leaves the same consumed counter and next word as scalar execution. Exact-type routing keeps custom/subclass WordSource inputs on the scalar route.
- At most8192 dates/49152 words are requested per batch. Word storage is<=393240 bytes plus immutable peek copies; packing masks, output and remainder arrays are bounded by batch size. Including digest-join temporaries remains comfortably below the16MiB limit for the frozen geometries. There is no whole-P7 six-column allocation. This allocation analysis is separate from sampled runtime RSS enforcement.

The evaluator, support/truth/rounding, frozen protocol, supervisor, I/O failure propagation and cleanup behavior are unchanged. Manifest library identity now includes installed NumPy. Experimental CounterStream construction remains an unconditional refusal; no sampled lifecycle or permission route was introduced.

## Independently reproduced evidence

Fresh focused command `python -m pytest tests/unit/test_signal_calendar_score_study_research.py -q -p no:cacheprovider`: **74 passed in7.07s**, exit0. This includes all ten full frozen-profile payload comparisons against the committed previous deterministic hashes, additional identities, actual rejection fallback, ownership/partial lanes, counter exhaustion, callback errors, custom-source isolation and existing durability/supervision refusals.

Separately authored bounded checks rebuilt the SHA prefix and atom map without production scalar mapping for all ten61-date profiles at a distinct fixed test identity; all bytes, consumed counts and the next word matched. Another independent sequential SHA oracle checked69 mixed peek/consume/next_word operations. These checks used deterministic test namespaces only, and did not run governed measurement or experimental draws.

The primary separately reports324 related calendar/synthetic-golden passes,168-source strict mypy, Ruff and168-file format checks; this reviewer did not rerun that broader selection. No performance success is claimed from tests or inspection. Proceed with the exact-source fresh-root supervised full-workload measurement, retain every path until independent all-byte/result verification, and report actual frozen-budget eligibility. Even if feasible, the full sampled worker/verifier/authority/sealing/cleanup lifecycle and real-data applicability remain OPEN.

## Independent verification of optimized saved preflight

Verified `var/verification/2026-10-04/calendar-score-study-preflight-optimized` on2026-10-04. **ALL SAVED-FILE CHECKS PASS; FROZEN PREFLIGHT ELIGIBILITY IS TRUE.** Independent receipt `reviewer-independent-verification.json` was written exclusively, flushed and synced in that root. Source remains `58f483289f9175fec4f96153a1e7a377cc8c26e9d61a4a4e35fc8ef67b901f5e`; manifest `ca9fc3380420a1a50dadfb98a1676e9f9a9e19593a9df52bf75fa164d5f1c0fc`; run receipt `d30d3ca07c3e88d8ddcd09f23e476b26e7a3b65322e876ed744a028e94077c31`.

The independent checker imported no production generator/evidence/score modules. Fresh literal SHA framing/rejection/atom generation matched every saved byte across all10 histories and1388952 consumed words. Independent integer-prefix trade reconstruction, exact finite-binomial strict-win truth enumeration and Fraction/integer-square-root outward rounding reproduced all28 totals/counts/truths/endpoints and flags. Counts remain P1=3055,P2=3089,P3=24480,P4=12298,P5=49158,P6=49224,P7=196653,E+=3093,E-=3066,L1=72. Entire ordered index/result objects also equal the committed pre-optimization baseline.

Payload231492 bytes SHA256 `816a0ae0a31c0cf97bf3fd1aa309b063551951305b4dfaac78370db22759afc2`; index SHA256 `9bb0367747edce09933993a3873ea01cdd04fbf653e327aabbbfc89aa95f9cba`. All listed source hashes, actual frozen protocol, Python/NumPy/psutil versions, canonical claim/manifest/receipt/terminal, ordered offsets/lengths/hashes/word counts, and exact safety-factor projection multiplications were checked. No failure record exists; worker log is empty. Retained bytes were not altered or deleted.

Recorded generation/evaluation/output0.5401904000s and independent-regeneration/replay0.5129779000s per set produce development8850.4795s<21600, validation35401.9181s<43200, development verification8404.6299s<43200 and validation verification33618.5197s<43200. Free disk336690466816 bytes exceeds the fixed reserve plus bounded validation estimate. Parent-observed worker-tree RSS40144896 bytes is below the monitored ceiling. Therefore the recorded true eligibility is consistent with the frozen arithmetic and guards. These are one-full-set projections with the registered twofold margin, not demonstrated sustained32,768-repetition performance or proof of unsampled peak memory.

Separately reconstructed32MiB probe digest `498acf165bdbc19e8d6854e3a9dc52a52a180e277bd27b13f0019f50914cdd05` matches intent/cleanup records; probe absence verified. Raw profile payload remains retained as of this verification. Only the primary may perform the subsequent identity/hash-bound D44 cleanup after recording both independent approvals; this reviewer performed no cleanup.

The optimized deterministic implementation and its measured feasibility checkpoint are accepted for this scope. No experimental namespace was drawn, no statistical qualification exists, and the full sampled worker/verifier/live authority/root sealing/cleanup lifecycle remains OPEN and requires its own review before a study can run.
