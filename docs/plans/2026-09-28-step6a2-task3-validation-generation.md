# Step 6a.2 Task 3 Slice 4D — held-back validation generation

**Status: bounded implementation plan, 2026-09-28.** Follows accepted private validation startup at `c694e4a` and the [Task 3 contracts](2026-09-27-step6a2-task3-contracts.md). This slice implements validation generation and durable result writing behind the exact live validation context. It does not add a combined CLI, draw either reserved stream, create review attestation, enable inference, or evaluate real data.

## Behavior

- Permit `_CountedChunkProvider` only for an active controller-issued calibration or validation context. For validation, require the bound completion lineage and exact frozen calibration-selected floor; retain one provider per context and all existing manifest, claim, resource, deadline, chunk-order and seed guards.
- Permit `_write_phase_result` to stream validation's full frozen cells and 20,000 replicates per cell in manifest order, 256-replicate chunks plus remainder, under its existing fresh two-hour deadline and 2 GiB limit. Keep the result `UNVERIFIED` until independent saved-file verification; all failure/close semantics remain unchanged.
- Derive validation candidate checks for **only** the bound floor, with no search across alternatives. A complete statistical failure is a complete `FAILED` result, never a retry or second floor. Bind that floor into the writer's immutable expected context so the independent verifier can recompute the same one-floor verdict.
- Change no frozen manifest, digest, estimator, seed, topology, threshold, family size, first-passing calibration rule or result schema. Keep direct `_begin_linux_phase("validation", ...)` refusal.

## Tests and hold

Write failing tests first using scripted chunk/event fixtures and a live handoff, with RNG constructors trapped. Prove a complete canonical validation result independently re-verifies; one selected floor only; the writer-bound expected floor matches the handoff; changed floor/lineage, duplicate writer/provider, changed claim/result and late resource/deadline failures refuse without an alternate draw. Preserve native Windows refusal and existing calibration output. Run focused/full unit tests, Ruff, mypy, golden characterization and diff checks; obtain independent review of exact bytes. The combined CLI is a later separately reviewed slice. Neither reserved stream may be drawn until complete-runner review and native Linux resource-envelope proof explicitly approve the first counted calibration invocation.
