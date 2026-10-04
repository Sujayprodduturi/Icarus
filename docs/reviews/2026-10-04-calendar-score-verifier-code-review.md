# Calendar score independent verifier: code review

Date: 2026-10-04. Scope: deterministic Unit 1 only; no sampled lifecycle or study authority.

## Initial freeze reviewed

- Verifier SHA-256: `cb35d26b0254d14c0ea67c84bdac6883e9538e0f0f0ea7f6434053f3ae9af57b`.
- Tests SHA-256: `a2296ecd961369d9a664f3988cfc3fffd035fe0f6e9263a7fcc29f13498095ed`.
- Study SHA-256: `252f496eb5e857e3606a7c8f0f0f6377c71b14f3dd5d21c935a159c19eec4533`.
- Approved plan SHA-256: `c12129e2799e580cb0d4a7541ac304598c8ad953034eabfe2f9cd69b920a8e61`.

Ordered review: ponytail-review simplicity pass, then engineering code-review with independent mathematics and failure-safety inspection.

## Initial findings

- P2, simplicity: `integer_totals` is an unused alternative accumulator, exercised only by its own test. Remove it and retain the real `trade_totals` Python-integer fallback regression.
- P1, receipt integrity: `_verify_fixture` writes the successful verification receipt before its final source-manifest recheck. Source drift at that last check raises while leaving a successful-looking receipt. Likewise, an actual flush/fsync/close failure can occur after valid receipt bytes exist. The existing fault test raises before persistence and does not cover this state. This violates the plan's no-success-receipt-on-error contract. Approval is withheld until receipt publication or ownership-bound rollback closes these failures, with regressions for post-write failures and preservation of preexisting receipts.

## Inspection evidence

The independent verifier reconstructs the literal SHA framing, unbiased rejection mapping, six draws per date and original-a excess support. Integer prefix totals, strict win comparison, finite truth enumeration, outward 60-digit endpoint rounding and cutoff recurrences are independently implemented rather than delegated to the production evaluator. Inspection found no additional mathematical blocker. The mandatory three L1 diagnostic counters are retained and full-phase count checks are distinct from the 10-path/28-metric fixture verdict.

The actual verifier receipt durability, cold truth/cutoff initialization, parent startup and final pre-result source/resource checks are included in benchmark accounting. Excluding persistence of the benchmark's own accounting record and redundant post-result checks is acceptable for this disclosed deterministic verifier timing scope; it grants no sampled-phase approval. Full lifecycle, global attempt authority, sealed reviewer release and sampled execution remain open.

This initial entry records source inspection, not an executed benchmark or saved-file verification. Root-reported broad regression/static results are not substituted for reviewer fault-path checks. A corrected immutable freeze and its targeted evidence will be appended before approval.

## Corrected freeze: approved for supervised deterministic measurement

Fresh reviewer filesystem SHA-256 checks confirm verifier `946d5fdefd663c7d47ba36fa6448f41662bff93bf7b5b0f02982bbd40f8cd4a5` and tests `1cb394062e37ce8ea7e50042bc9a0a62938a39b8ec2d327b5465fce465d8ff0b`. Study and plan hashes remain exactly those above.

P2 is closed: the orphan helper and its isolated test are removed; the genuine prefix/Python-integer fallback test remains. P1 is closed: receipt persistence now targets a bounded, explicitly inert candidate. Only after durable writing, source/resource rechecks and exact candidate size/hash verification does an exclusive hard-link publication create the success filename. Preexisting destinations cannot be overwritten. No fallible checks follow publication, and directory power-loss durability is explicitly unclaimed. Failed candidates are retained as inert evidence; no deletion capability was added.

The reviewer read the actual new fault tests and retained logs in `var/verification/2026-10-04/calendar-score-verify/`. The RED log proves all three actual-bytes-written source/fsync/close cases left a receipt before the fix (3 failed, 1 preservation test passed). The corrected full focused suite reports 57 passed in 4.11 seconds. Targeted strict mypy reports two source files clean; Ruff reports all checks passed. These are inspected execution logs, not reviewer reruns; parent foreground regression work was deliberately not overlapped.

Verdict: no remaining P0/P1/P2 blocker for this exact deterministic Unit 1 source freeze. Approved to run the bounded, supervised full 10-path cold verifier benchmark. Actual saved-file results and runtime feasibility still require separate review; no timing result is assumed here. This approval confers no experimental stream, sampled-phase PASS, attempt authority, validation-root release or raw cleanup approval.

## Independent saved benchmark verification

The reviewer independently checked `var/verification/2026-10-04/calendar-score-verifier-benchmark-final` using a retained bounded standalone oracle, `var/verification/2026-10-04/calendar-score-verify/reviewer_saved_oracle.py`. It imports no project math or production generator: literal scalar SHA/unbiased mapping regenerates every saved byte, naive Python integer date/trade sums reproduce every total, and a separate finite enumeration plus rational/isqrt calculation reproduces all truths, supports, outward endpoints and flags. All 10 paths, 28 metrics, 1,388,952 consumed words and 231,492 payload bytes passed. All summary cells, including three L1 diagnostics, match exactly.

Source-file hashes were checked against the manifest both before and after verification. Canonical record seals, claim/report/index/terminal bindings, published/candidate receipt identity and bytes, measurement bindings and runtime arithmetic passed. The oracle took 1.9445591 seconds; ending process RSS was 22,659,072 bytes (not a peak-memory claim). The retained log and exclusive fsynced `reviewer-independent-verification.json` record the evidence.

- Payload SHA-256: `816a0ae0a31c0cf97bf3fd1aa309b063551951305b4dfaac78370db22759afc2`.
- Index SHA-256: `50e1bd5a58d9383039dd6a4ded48f3ee8889cb4cc486c4c9fbdbd43337a77007`.
- Fixture terminal SHA-256: `a8188e8d9ec9f321e89d393531d558634fd35aedb296a67ec454f16de6e4db71`.
- Source manifest SHA-256: `76962f70b2e8869e6fd9685807761d7edf747c43e2a380250ced3d7ca616b1b2`.

Saved evidence and mathematics are accepted; performance qualification fails. Measured cold verification was 0.8196814 seconds, conservative full-boundary cost 1.2932477 seconds, and doubled validation projection 84,754.2813 seconds (23.54 hours), above 43,200 seconds. The per-set ceiling remains 0.6591796875 seconds. `eligible=false` is correct; no criterion is relaxed and no study draw or sampled lifecycle approval follows.

Reviewer cleanup approval is limited to the new fixture's exact 231,492-byte `fixture-payload.bin` with the payload hash above, after both verification receipts pass and the parent rechecks identity/hash. Retain index, results, terminal, manifests, receipts, oracle/log and cleanup provenance. The reviewer performed no cleanup. Further optimization or a separately reviewed pre-draw operational amendment is required before claiming runtime feasibility; full sampled lifecycle remains open.
