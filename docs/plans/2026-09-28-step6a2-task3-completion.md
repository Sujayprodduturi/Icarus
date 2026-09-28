# Step 6a.2 Task 3 Slice 4B — candidate record and completion authority

**Status:** bounded implementation brief following the operator's 2026-09-28 approval of the same-process authority proposal. Root reviewed and approved this bounded brief before builder dispatch on 2026-09-28. The exact schema and superseding authority rules are in [contracts §§6–8](2026-09-27-step6a2-task3-contracts.md). This is not approval of a counted experiment.

## Scope and minimal API

Keep implementation in `scripts/signal_calibration.py` and tests in the existing Task 3 module. Add private `_complete_phase(context, manifest) -> _PhaseCompletion` and `_require_phase_completion(context, completion) -> _PhaseCompletion`. Reuse Slice 4A verification, bounded I/O, identity checks and resource guards. No new module, persistence framework, extra artifact or public entry point. Do not reuse `_write_immutable_claim` for candidate writing: the candidate path must independently prove relinquish-before-close ownership.

The writer accepts only an active, writing-finished, authenticated context with its writer-issued expected binding. It derives all metadata itself and calls `_verify_finished_phase_result(context, manifest)` freshly inside this operation; there is no caller-supplied verification record, verdict, path, phase override or floor.

Capture the real PID when the controller creates the phase context; completion and authority checks require that original PID still equals the current PID. Add one completion-attempt flag and one completion-object slot to the existing frozen context, updated only through its private lifecycle operations. This is not a registry of attempts.

Mark completion attempted before verification or candidate I/O. Any subsequent issuance call refuses, invalidates/closes that context, and cannot overwrite or regenerate anything. An issued capability is the exact immutable object stored in the context slot; copying or constructing an equal dataclass does not pass. Require its private issuer marker, context identity and canonical bindings, original/current PID, unchanged payload binding, live context and successful lifecycle state. Do not describe this as resistance to arbitrary malicious in-process Python.

The immutable capability contains: issuing context reference, private issuer marker, PID, context/writer-expected bindings, phase, attempt/manifest identity, claim/result digest and original device/inode, result size, candidate digest/size/device/inode, phase verdict/selected floor, and completed total elapsed/peak RSS/UTC snapshot. Its data is never deserialized as authority. Closing the context revokes it. FAILED completion is valid completeness evidence but supplies no validation authorization.

## Ordered implementation

1. Require original PID, active context, bound writer expected, full authenticated manifest and unused completion lifecycle; enter attempted state.
2. Invoke fresh Slice 4A verification. Both complete PASSED and complete FAILED are eligible; incomplete or malformed results fail before candidate reservation.
3. Derive the exact `step6a2-completion-candidate-v2` object from verified data and independent context provenance. Capture explicitly pre-write elapsed/peak/UTC values under the original boundary; UTC must not precede attempt start.
4. Guard construction, canonical serialization, UTF-8 encoding and simultaneous live buffers before allocation, using conservative geometry/field-size bounds rather than a post-allocation length check alone. Candidate uses sorted keys, compact separators and exactly one LF. All schema keys/ranges are validated before reservation.
5. Reserve the existing derived `.seal` name exclusively via the retained directory handle at mode 0600 with existing secure flags. Register descriptor ownership immediately before fallible validation; prove regular file, single link and original identity.
6. Write the complete bounded canonical bytes. A short/zero/invalid write or exception is failure: no continuation, repair or retry. File-fsync then containing-directory-fsync with original deadline/resource checks around each operation.
7. Relinquish writer ownership before its single close attempt. Reopen candidate read-only through the retained directory, prove original identity/extent, bounded-read and compare exact canonical bytes/digest. Retain that reader through the late result rehash in step 8. No by-path fallback.
8. Recheck original claim/result/candidate identities and extents through retained handles/directory. Bounded-rehash the result against the freshly verified digest after candidate I/O; compare exact claim bytes. After result rehash, bounded-reread the candidate again and compare exact bytes, then relinquish and close its reader once. Recheck identities after content checks/closure. Same-inode edits, replacement, growth and shrinkage fail. These are point-in-time integrity checks; the future consumer must verify again.
9. After all operation-owned readers/writers have closed successfully, check the original resources/deadline and capture finite nonnegative completed elapsed/peak and valid UTC. No file I/O or cleanup remains between this final boundary and capability issuance. All capability allocations must already have been guarded.
10. Register/return the immutable capability once. Retain original context handles for a later same-process consumer. No validation starts in this slice.

On every failure, remove/invalidate any completion slot, permanently close the context and close every operation-owned handle once. Relinquish ownership before close; cleanup errors remain visible and never cause descriptor reuse to be closed twice. Candidate bytes can be absent, partial or complete and stay reserved. Late failure cannot make those bytes authoritative. No delete, rename, overwrite, truncation, resume, new attempt or fallback exists.

`_require_phase_completion` validates issuance and bound identity only; it must not imply fresh trio verification or unlock validation. It refuses foreign contexts, altered payloads, copied/unissued objects, closed contexts and PID changes. A future consumer must separately reverify the complete trio and PASSED/non-null first floor. The original completed elapsed snapshot is historical: this helper must not call `context.require_active`, reset/check the calibration deadline, or expire authority merely because that deadline later passes. Check context non-closure and immutable bindings directly without I/O. This slice does not invent the later phase's deadline/consumption policy; fresh trio verification and validation startup need an explicitly budgeted Slice 4C contract.

## Acceptance evidence

Use deterministic scripted fixtures and RNG constructor sentinels, never reserved seeds, claims for an official experiment, or an official review attestation.

- Independent exact expected candidate schema/bytes and capability bindings for PASSED; complete FAILED issues completion but is never represented as validation permission.
- Caller cannot inject saved 4A metadata; tampering after an earlier successful 4A call is rejected by fresh internal verification before reservation.
- Malformed/incomplete result, wrong manifest/context/PID, unfinalized context, missing expected binding and resource/allocation refusal produce no capability.
- Existing candidate refuses without modifying bytes; repeated issuance cannot verify again, rewrite, issue a second object or retain authority after invalidation.
- Short/zero/invalid write and exceptions preserve reserved bytes, invalidate context and issue nothing.
- File fsync and directory fsync failures; writer/reader/context-directory close failures including release-then-raise and descriptor reuse; prove each owned fd is attempted once and cleanup errors surface.
- Deadline/resource failure before/after write, each sync, candidate close, reader close and final checks; specifically a complete candidate survives a late failure with no valid capability.
- Candidate/result/claim same-inode edit, replacement, hard link, changed size and malformed canonical data; prove the intended late check is reached before injection.
- Copied/equal/unissued capability, altered fields, wrong context, PID change, context close, and candidate files loaded into a fresh process/context all refuse authority. Fork/PID behavior uses an isolated Linux child where available.
- Prove order with operation witnesses, not only an exception assertion: sync file then directory, close once, fresh content checks, final boundary, issuance.
- Existing full fixture happy path plus complete FAILED path reuse strict verification; avoid whole-phase repetition per failure parameter.
- Windows scripted failures are unit evidence only. Existing Linux CI must exercise actual exclusive/no-follow mode, relative reopen, fsync and descriptor ownership using isolated scratch evidence, without installing resource limits in the test coordinator.
- Run focused tests and explicit static checks, then root independent review/full regression and exact-commit Linux CI before accepting Slice 4B.

## Holds

No validation execution or consumption API, combined invocation, production CLI, official attestation, frozen-stream RNG, broker or real-data work. Frozen manifest/estimator, statistical thresholds, 2 GiB/two-hour limits and disabled inference remain unchanged. Surviving candidate files cannot authorize validation after process loss. The later combined invocation and its phase-resource handoff require separate review.

### Adjacent ownership regression (root, 2026-09-28)

Root reproduced an existing `_write_immutable_claim` defect against committed source in an in-memory fake filesystem: release-then-raise on writer close caused cleanup to retry a reused descriptor and close an unrelated sentinel. Include only the minimal ownership-order repair (clear writer ownership before its close) and a precise reuse witness in this slice. Candidate finalization remains independently implemented/tested. No broader claim-path refactoring is in scope.
