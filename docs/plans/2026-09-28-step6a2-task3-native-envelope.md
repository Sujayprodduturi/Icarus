# Step 6a.2 Task 3 — native full-size resource proof

**Status: bounded proof specification; not executed.** This is a separate hold point after the exact whole-runner review. It does not authorize or perform an official calibration/validation draw.

## Boundary

- Use a fresh child process on a bare Linux host that passes `_verify_native_linux_environment`: init/systemd as PID 1, no WSL or container. Scratch evidence must reside on ext4, xfs or btrfs. Use real `_NativeLinuxOps`, file and directory fsync, secure descriptor operations and the unchanged 2 GiB `RLIMIT_AS` and monotonic 7,200-second deadline per phase.
- Work only in a disposable scratch repository and scratch evidence directory, never the production CLI or official `docs/reviews/step6a2/<manifest_sha>` evidence paths. Trap `SeedSequence` for both reserved master seeds; a trap firing fails the proof. Use no real market data, broker path or product inference.
- Run a non-reserved generation surrogate through the real `_CountedChunkProvider`, event builder, writer, saved-file verifier and completion. A test-only provider subclass calls the real constructor, then replaces `_phase_seed` with a distinct test seed before any draw. Preserve the frozen manifest topology and limits: 45 calibration cells × 10,000 replicates and 37 validation cells × 20,000 replicates, in 256-replicate chunks, all three metrics and parity records. This measures generation time and simultaneous provider/writer memory; label its result as surrogate evidence, never an official calibration result.
- Separately exercise a scripted high-size serialization and independent parse/verification overlap with real native I/O, candidate completion and same-process handoff. Include the largest encoded chunk and result extent; do not substitute a tiny fixture for the memory peak. If a surrogate calibration fails statistically and cannot hand off, exercise validation with a separate test-only verified fixture and disclose that boundary. Any omitted stage needs a conservative measured bound.

## Required evidence

Record OS/host and filesystem facts, exact reviewed code commit, test-only input construction, address-space limit readback, per-phase wall time and peak RSS/VMS, maximum chunk/result bytes, verification projected bytes, and success/failure of fsync and close. The proof passes only if both complete phases and the largest serialization/verification overlap finish within each unchanged limit with no reserved RNG or official artifact. OOM, deadline expiry, unsupported host/filesystem, or unverified close is a blocker. Preserve the raw test log and review it independently before the first official claim.

The first official calibration draw remains a separate decision after this proof, exact-commit whole-runner review, and the required attestation are all complete. The held-back validation stream is reached only by a verified successful calibration in the same process.
