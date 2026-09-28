# Step 6a.2 Task 3 Slice 4A — independent saved-result verification

Status: Slice 4A accepted on 2026-09-28 at `e406a7b`: independent Astra Medium review, 1,541 local unit passes, 1,545 Linux CI passes, clean static checks and three caught post-commit fault probes. See the [verification record](../reviews/2026-09-28-step6a2-task3-verification-review.md). Usage-aware scope used one medium-effort builder and one reviewer; one stale test expectation required a final broad rerun. Sealing remains explicitly held below.

## Boundary

Build only private independent result verification in `scripts/signal_calibration.py`, with tests in the existing Task 3 test module. No seal writer, validation unlock, counted CLI, reserved RNG, attestation or official experiment. Frozen manifest/estimator/limits and disabled inference remain unchanged.

## Contract

- Bind the immutable writer-issued expected phase context inside the authenticated `_PhaseContext` only after successful writer finalization. Verification must use that binding, never caller-supplied matching runtime/provenance.
- Require active, writing-finished context with that binding; independently check manifest/context identity. Derive paths from the retained context.
- Open the result read-only relative to retained directory handles; verify regular-file status, single link and original device/inode.
- Freeze the initial file size and check the full verifier memory projection before reading. Read exactly that size in bounded pieces with original-deadline checks; reject premature EOF, extra bytes or changed extent. Never chase a growing file.
- Hash and strictly parse those same collected bytes; run the existing complete-result verifier against the writer-bound expected context. PASSED and complete FAILED are valid evidence; INCOMPLETE is refused.
- Independently rehash current bytes in bounded pieces after verification; compare digest, extent and original identity; recheck exact claim bytes and context resource/deadline state.
- Return immutable private evidence bound to the retained context, exact digest/size, statistical verdict and measured verification snapshot. It grants no completion, validation or trading authorization.
- Success closes only the newly opened reader, checks the original deadline/resources again, and retains the authenticated context for later work. The returned timing/peak snapshot includes successful reader closure. Failure invalidates/closes context and newly owned handles; relinquish descriptors before each single close attempt, never retry an uncertain descriptor.

## Tests and acceptance

Use scripted fixtures and RNG sentinels only. Cover independent successful verification, complete statistical failure, unfinalized/missing binding, forged matching caller/result runtime, malformed/incomplete/tampered events, projection refusal before reads, growing/shrinking/same-inode modified or replaced files, bounded-read deadline expiry, post-verification mutation, and close-after-release failure. Reuse existing fixture helpers; avoid a full-phase run per failure parameter. Review simplicity then correctness/security before commit, then in-memory post-commit fault probes and exact-commit Linux CI. Root independently verifies key evidence and updates STATE before finishing.

## Sealing hold discovered during review

Two runs can write identical canonical seal bytes at 7,199 seconds, but finish fsync respectively before and after the 7,200-second deadline. Surviving files alone cannot distinguish successful finalization from the rejected run. Reverification proves current content integrity, not historical completion. Astra corrected its initial suggestion after root challenged this counterexample. The persistent seal contract therefore needs an explicit commit-point ruling before a seal writer or validation unlock is implemented. No extra sidecar, deletion/truncation or threshold change is authorized here.
