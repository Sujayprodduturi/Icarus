# Step 6a.2 Task 3 — bounded saved-result verifier proposal

**Status: operator approved; locally verified implementation, native proof pending.** The [native proof](../reviews/2026-09-29-step6a2-task3-native-resource-proof.md) showed that real test-seed validation could not write its result under the former whole-file verifier budget. The operator approved this bounded repair on 2026-09-29. No official synthetic stream has been drawn.

An independent GPT-6 Astra medium-effort read-only architecture consultation recommended bounded single-file verification after comparing compact encoding and multiple-file publication. A follow-up review of this exact proposal and measured record found no P1/P2 issue; it clarified that reported VMS is the maximum of explicit samples, not a continuous high-water mark.

## Operator-facing change

Keep the existing one-file result and the same statistical calculations. Read and independently check one saved 256-replicate chunk at a time instead of loading the entire result into memory. Apply the same bounded reader both when a phase completes and when validation rechecks calibration. Keep the 2 GiB memory ceiling and one 7,200-second monotonic deadline; a parser or evidence error still halts the phase. Do not change the frozen manifest, seeds, cells, replicates, metrics, targets, candidate floors or acceptance thresholds.

## Contract

1. **Same bytes and authority.** The writer's canonical JSON result bytes and single immutable artifact remain unchanged if tests can establish exact equality. Candidate files remain inert until file and directory fsync, final resource/deadline checks, independently verified saved bytes and successful single-close issue private same-process completion authority. No restart recovery or second draw.
2. **Bound before allocating.** The reader opens the already retained no-follow file descriptor, verifies inode/type/extent, and consumes fixed-size read blocks. It recognizes only the writer's canonical top-level field order and framing. It holds at most one complete chunk, bounded envelope fields, counters and summaries in memory. Derive a maximum encoded chunk and envelope size from the frozen 256-replicate topology and maximum parity representation; refuse an oversized field before allocation. The writer must enforce the same bounds.
3. **Canonical and complete.** For each chunk, use the existing strict JSON decoding rules for duplicate keys, finite numbers and exact types. Re-encode and compare its bytes to enforce canonical form. Reject missing, duplicated, reordered or extra chunks; changed top-level order; malformed UTF-8; unknown fields; malformed escapes/numbers; trailing bytes; missing final LF; and any other representation the current verifier rejects. Check every byte, not only a parsed summary.
4. **Independent recomputation.** Check each saved cell/chunk/metric against the frozen order, range, event partition, refusal reasons and parity records. Build the same six counts per cell/metric and recompute all summaries, CP bounds, verdict and floor from saved events. Saved aggregate rows never become authority. Keep only bounded counters and summaries, not all chunk objects.
5. **Identity across both reads.** Hash the complete first traversal; retain the existing writer-bound expected bytes and provenance checks, retained descriptor identity, final extent/inode checks and independent rehash. Reuse the bounded verifier for validation startup's full calibration recheck. Any changed bytes, path swap, truncation or failed read closes owned handles and withholds authority.
6. **Honest resource model.** Replace the current `current VMS + 32 × whole result bytes + 64 MiB` projection only after the bounded implementation demonstrates its actual maximum live allocation. The new preallocation bound must cover current VMS/RSS, the largest encoded and parsed chunk, canonical re-encoding, parser buffers, all counters and summaries, and the independent rehash. Preserve the exact 2,147,483,648-byte `RLIMIT_AS` readback and 7,200-second deadline. Retain a conservative total file-extent bound derived from frozen topology, plus real measured peaks. Never just lower the multiplier.

## Test-first sequence

1. Pin valid writer output bytes, recomputed counts/floor/verdict and hashes on a small deterministic fixture. Add a validation-startup test that requires a second full evidence pass but no second RNG draw.
2. Add red tests for bounded reads across every byte split and for oversized chunk/envelope refusal before allocation. Add malformed canonical JSON, duplicate keys, nonfinite numbers, extra/truncated/out-of-order chunks and altered terminal fields.
3. Add red tests for changed inode/extent/content during and between passes, read/fsync/close failure, deadline and resource overrun, and proof that no completion or validation authority escapes any failure.
4. Implement one shared bounded reader and switch both completion and validation startup to it. Preserve deterministic writer bytes and old/new valid-fixture results; retire the whole-file parser only when all callers are accounted for.
5. Run Ruff, mypy, full Windows unit suite, exact-commit Ubuntu CI, focused fault probes and independent medium-effort statistical/safety and simplicity review. Confirm the reviewed protected blob hashes match the committed code.
6. Rerun full-size native generated calibration, real test-seed validation after a scripted passing calibration, and scripted maximum-size serialization/verification overlap on bare Linux. Keep test seeds and scratch evidence only. Fix the artifact uploader so logs and reports extract into the flat paths the aggregate checker expects. Require all three reports, raw logs, no fsync/close failures, complete phases, and measured RSS/VMS/time below unchanged limits. Independently inspect the exact logs and report hashes before whole-runner attestation.

The first official calibration attempt remains a separate hold point after this repair, full native proof and exact-commit independent whole-runner approval. An official statistical failure would consume its frozen stream; no test-only surrogate verdict can substitute for that decision.

## Alternatives considered

- **Lossless compact event encoding** could remove repeated dense ID lists but changes saved artifact bytes and verifier schema. Without a proven worst-case size bound, a whole-file parser remains size-dependent; parity-heavy chunks may still exceed the budget. Consider only with separate versioned-format review.
- **Multiple immutable chunk files** would bound reads but adds thousands of secure paths, descriptors, fsyncs, hashes and publication/close states to the already reviewed completion protocol. It is a larger safety surface for this failure.
- **Increasing the memory cap or lowering `32×`** is rejected. Neither demonstrates a safe verifier and the frozen limit remains in force.
