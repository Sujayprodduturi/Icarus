# Step 6a.2 Task 3 - independent Astra Medium re-review

Date: 2026-09-27. Scope: documentation and read-only code inspection.

**Verdict: NOT IMPLEMENTATION-READY until the three clarifications below are recorded and re-reviewed.** The revised architecture is within the approved synthetic-only parent scope. This verdict authorizes neither implementation nor a frozen-stream draw.

## Sources inspected

- `AGENTS.md`, `OPERATOR.md` (including the scoped process authorization at line 304), and `docs/STATE.md` (lines 16-19).
- [Revised Task 3 plan](../plans/2026-09-26-step6a2-task3-counted-gate.md), cited below by line.
- [Original plan audit](2026-09-26-step6a2-task3-plan-audit.md), lines 3-7.
- [Approved parent plan](../plans/2026-09-26-step6a2-calibration-implementation.md), especially Random streams, acceptance and parity, and Task 3.
- `scripts/signal_calibration.py`, especially `verify_protected_git_state` at lines 1386-1418; frozen manifest integrity fields.

## Architecture accepted

- Stable manifest/phase claim plus one result JSON plus a completion seal preserves one statistical result per phase. The claim prevents duplicate attempts; the seal attests independently verified bytes. Neither sidecar is a competing result (Task 3 lines 15, 27).
- Separate reviewed-code and invocation commits avoid review-record circularity, provided protected blobs remain identical and intervening commits are restricted to exact review-document paths (line 9).
- Same-handle byte hashing, strict parsing, complete event partitions, independently recomputed bounds and first-passing selection address the earlier evidence-integrity findings (lines 29-31).
- Deterministic eligibility, unchanged family sizes, counted refusals, and no validation floor search retain the parent's statistical contract (lines 19-23).

## Three blocking clarifications

1. **Name the validation evidence allowance.** Line 35 permits only exact artifacts for the current run; validation also needs the already-produced calibration claim/result/seal. Leaving those untracked can fail cleanliness; committing them appears to violate line 9's review-only intervening-commit rule. Explicitly permit the exact, verified calibration trio as validation inputs plus the current validation paths. Do not allow a directory prefix. Existing cleanliness code rejects other untracked files at lines 1396-1405.

2. **Freeze exact evidence and review contracts.** Line 29 requires an exact schema/key set before implementation but currently supplies a field inventory. Record nesting, types, required/forbidden keys and version for result, claim, seal and review attestation. Resolve which SHA names the result's `harness-commit` versus invocation commit. Require reviewed-commit ancestry and an exact review-document allowlist across intervening commits, not only equal protected blobs at the endpoints.

3. **Specify the Windows enforcement and durability contract.** Line 35 does not select the hard-limit mechanism or distinguish its units from peak resident memory. Windows Job Object `ProcessMemoryLimit` limits committed virtual memory, not RSS. Pin the chosen enforcement primitive, its measured quantity, how it combines with `peak_wset` and preallocation checks, and failure-before-draw behavior. Lines 15/27 also need a platform-specific directory-creation durability contract instead of assuming POSIX directory fsync works unchanged. This is a plan-contract blocker, not a finding that Windows cannot implement the safety boundary.

Microsoft primary source, checked 2026-09-27: [JOBOBJECT_EXTENDED_LIMIT_INFORMATION](https://learn.microsoft.com/en-us/windows/win32/api/winnt/ns-winnt-jobobject_extended_limit_information), `ProcessMemoryLimit`. For file metadata flushing: [File Caching](https://learn.microsoft.com/en-us/windows/win32/fileio/file-caching). These establish API semantics; they do not prove the current host can install the required controls.

## Acceptance and authorization remain separate

After the clarified plan passes re-review, implementation must demonstrate resource-control installation, bounded allocation failure, durable reservations and secure file handling using deterministic or test-only fixtures. Fail closed if the platform cannot provide the chosen guarantees. These implementation proofs are still outstanding.

The first counted calibration draw requires independent statistical/safety approval of the exact completed, committed runner and protected hashes. Validation additionally requires complete accepted calibration bytes and the verified claim/result/seal. No cells, seeds, thresholds, estimator, family sizes or first-passing rules change. Inference remains disabled.

No code was changed, tests or calibration streams were run, backtests were evaluated, broker tools were accessed, or commits were made during this review. This file is the only review-owned write; other session documentation is owned by the parent orchestrator.

## 2026-09-27 addendum - clarified plan approved for implementation

**Updated verdict: APPROVED FOR BOUNDED TASK 3 IMPLEMENTATION**, governed by the revised [Task 3 plan](../plans/2026-09-26-step6a2-task3-counted-gate.md) and [exact contracts](../plans/2026-09-27-step6a2-task3-contracts.md). The earlier NOT IMPLEMENTATION-READY verdict remains above as history; the reviewed clarifications close its three blockers.

- Contracts section 7 explicitly permits only the verified calibration trio plus the exact validation paths, without requiring an impermissible intervening result commit.
- Sections 2-6 pin strict claim/result/seal/review schemas, reviewed versus invocation commits and per-commit review-only ancestry. All other tracked imports remain unchanged. One statistical result plus control sidecars preserves the parent architecture.
- Section 8 refuses native Windows counted mode before claim or RNG. Native Linux requires supported local storage, secure handles, file/directory fsync, a hard 2 GiB address-space cap and separate peak-RSS accounting. The address-space cap is conservatively stricter, not falsely equated with RSS. Actual capability and failure behavior still require implementation proof.
- Section 5 preserves the parent's result schema, base-estimator event counts without floor filtering, selected-floor-only validation, append-only timestamp ordering, and post-verification seal measurements. Saved outcome scale permits the frozen parity tolerances. Reviewed orchestration/tests establish exhaustive trigger emission; stored event IDs alone cannot establish that unsaved triggers were not omitted.

Slice 1A was separately approved before this full-plan verdict: private strict canonical parsing, metric event partitions and CP/count/check recomputation against the frozen manifest, using scripted test inputs only. It did not approve a full phase validator or any context, I/O, CLI, RNG or validation unlock.

Proceed test-first in the stated independently reviewed slices. This approval does not assert that the implementation exists, fits the resource budget or passes tests. Resource-incomplete attempts remain possible; no guarantee that a frozen phase fits the budget is made.

**No first draw is approved.** The completed committed runner still needs exact-commit independent statistical/safety approval before calibration; validation additionally requires accepted verified calibration evidence. Inference remains disabled. This addendum changed only this review file; no code, stream, broker access or commit was performed by this reviewer.
