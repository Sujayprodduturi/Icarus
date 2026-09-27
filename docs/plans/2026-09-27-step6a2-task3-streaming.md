# Step 6a.2 Task 3C — streaming orchestration boundary

Design follows the approved counted-gate plan and exact Task 3 contracts. Astra Medium reviewed the architecture and the corrected descriptor-ownership transition; see the execution ledger. Implementation has not started. No reserved draw, seal, validation unlock or counted CLI is authorized.

## Interface and complete path

- Private `_write_phase_result(context, manifest)` derives all phase/cell/chunk identity from the authenticated context and frozen manifest. No seed, floor or cell-subset overrides.
- Instantiate the private provider internally. Verify every yielded chunk against expected manifest order/ranges, including premature exhaustion and extra chunks. Build the three metrics in manifest order through the reviewed self-validating adapter.
- Stream canonical UTF-8 JSON in sorted key order: `attempt`, `chunks`, `phase`, `phase_contract`, `protocol_version`, `provenance`, `runtime`, `schema`, `summary`, `terminal`. Serialize each whole chunk before appending; exactly one document-final LF.
- Recompute counts from validated event partitions; retain only compact per-cell/metric counters. Complete summaries use existing CP helpers, deterministic candidate support and the first-passing rule. A complete statistical failure remains complete `UNVERIFIED` evidence.
- Check additional simultaneously-live provider output, event objects, encoded bytes and summary allocations before work. Release each completed chunk before requesting the next. Guard projected total result size before every append, reserving a conservatively justified bounded closing suffix. Preserve the original deadline and peak-memory sampling.
- Fsync result and retained directory after each complete chunk. Record a safe append boundary only after both succeed. Finalize and fsync the complete suffix before returning immutable expected-verifier metadata.

## Descriptor ownership

Success does not close the full context. Open the finished result read-only relative to the retained directory with no-follow flags; verify original device/inode; close the writer and transfer descriptor ownership through one private one-way transition. Mark writing permanently finished. Retain claim/directory handles, original identity and resource deadline. Slice 4 independently reopens and verifies through those retained handles; the enclosing orchestration closes the context after verification/sealing or failure.

Any failed transition closes every owned descriptor and invalidates the context. No pathname-based recovery, retry, truncation or replacement is introduced.

## Failure path and tests

Caught adapter/summary failures may append a bounded `INCOMPLETE` suffix only at a proven valid JSON boundary with an active context and usable resources/storage. Such summaries must say `INCOMPLETE`, never imply a completed statistical verdict. They cannot receive a seal. Preserve only observed/committed counts; do not invent outcomes for ungenerated cells.

Provider failures already close their descriptors. Preserve their reserved partial bytes without reopening them to append a suffix. Partial write, failed fsync, unusable storage or expired deadline similarly preserves bytes and fails permanently. Cleanup errors cannot become success.

Tests patch private provider/adapter globals, never production arguments, and construct all frozen cell/chunk ranges using scripted event fixtures. Compare successful bytes to canonical serialization and independently pass them through the pure complete-result verifier. Cover complete pass and statistical failure, missing/extra/reordered chunks, safe-boundary INCOMPLETE, already-closed provider failure, allocation/deadline/projection limits, partial writes, file/directory fsync, writer-to-reader identity/ownership failures, duplicate finalization and retained-context verification access. No test constructs either reserved RNG.


Astra's final test clarifications: a newly opened reader must close even if fstat/identity validation fails before ownership transfer; a writer already closed must never be closed twice during later cleanup; deadline expiry during final fsync/handoff must prevent success; failure diagnostic text must fit the bounded suffix budget; native Linux tests must prove the retained result descriptor rejects writes.


Incomplete-summary ruling (Astra Medium and root): use exactly empty cells/candidates, null selected floor, parity false and INCOMPLETE verdict. Committed chunk partitions retain all observed durable counts/ranges. Do not compute partial CP bounds or invent missing outcomes. The exact-contract document now states this explicitly. Test canonical parsing, preservation of committed chunks and rejection by the complete verifier; no seal exists in this slice.
