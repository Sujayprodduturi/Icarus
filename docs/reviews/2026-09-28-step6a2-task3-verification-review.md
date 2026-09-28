# Step 6a.2 Task 3 Slice 4A — independent saved-result verification

**Status: ACCEPTED — code `e406a7b` pushed to origin/dev; independent review, final local checks, three post-commit fault probes and exact-commit Linux CI passed.** This slice verifies saved content only. It creates no seal and grants no validation or trading authority.

Sol Medium was the sole code/test writer. Astra Medium independently matched both frozen hashes and approved simplicity, correctness, ownership and failure-test non-vacuity with no blocking findings. Root independently inspected the diff and reproduced the deadline/descriptor-reuse regressions.

## Behavior and repaired findings

- Successful result writing binds its expected provenance, attempt and runtime into the issued phase context. The verifier accepts only that context and the frozen manifest; callers cannot supply a replacement expectation or result path.
- The verifier reopens the result relative to the retained directory, checks regular-file identity and link count, freezes its size, and checks the memory projection before reading result bytes.
- Bounded positional reads remain under the original deadline. Strict canonical parsing and complete result recomputation precede a second bounded hash and repeated identity, extent and claim checks.
- Success returns immutable verification evidence and closes its new reader while retaining the original context handles. Failure invalidates the context. An uncertain close is attempted once, protecting a reused descriptor.
- Root found that claim rereads also needed a bound: they now read only the original claim length plus a one-byte growth probe.
- Root reproduced a deadline gap during successful reader closure. The repaired verifier checks the original deadline/resources after closing the reader and measures its final snapshot afterward. The regression first failed, then passed.

## Frozen bytes and checks

- Script SHA256: `5538cddeb22c85a85e2adb5aad78ff7e05a810024db2a0e4ff7550036c46c3b2`.
- Tests SHA256: `d69371065e9845ef9f8b192f9a2436ac76cb8f2e9151f340eff252a2b0d64243`.
- Builder reports 17 focused writer/verifier passes; root independently reproduced the post-close deadline and descriptor-reuse tests: 2 passed, 233 deselected, 21.20s.
- Root global Ruff lint/format, project mypy (136 files), explicit script/test mypy and whitespace checks passed.
- First full suite: 1,540 passed, four Windows skips, one test failed solely because its old expected error text did not include the new earlier bounded-claim growth refusal. Production correctly failed closed; the specific test expectation was corrected, and all three tampering variants passed. The source hash is unchanged.

## Remaining boundary

Sealing remains on hold under the [approved Slice 4A plan](../plans/2026-09-28-step6a2-task3-verification.md). Identical seal bytes could survive either successful finalization or a later fsync/deadline failure. A precise commit-point ruling is required before implementing a seal writer or validation unlock. This verifier proves current content, not prior finalization success.

No reserved calibration/validation draw, review attestation, official evidence, estimator or goal change is included. Inference stays disabled. Native Linux resource headroom remains to be proved before any official draw, and the existing database-integration skips remain open.


Final root gate on the corrected tests: **1,541 passed, four Windows platform skips, 299.80s**. Global Ruff lint/format, project mypy (136 files), explicit script/test mypy and whitespace checks passed. Exact commit `e406a7b73f1dded1374e587031ec81999a325abb` is pushed to origin/dev; root compared both committed blobs with the independently reviewed hashes and working bytes successfully.

Post-commit root fault probes caught **3/3** deliberate in-memory changes: disabled writer-binding authentication, bypassed pre-read projection, and disabled second-hash comparison. Production source bytes stayed unchanged at the reviewed hash. Linux CI for the exact code commit is [run 36383980706](https://github.com/Sujayprodduturi/Icarus/actions/runs/36383980706).

Exact-commit Ubuntu CI passed: **1,545 passed, four pre-existing integration skips, 272.63s**, with lint, format and mypy clean. Root retrieved the completed run logs independently. This accepts Slice 4A only; the seal commit-point ruling, sealing, validation authorization and counted CLI remain unfinished. Existing integration-skip finding F11 stays open.
