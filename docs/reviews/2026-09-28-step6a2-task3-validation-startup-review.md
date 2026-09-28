# Step 6a.2 Task 3 Slice 4C — validation startup review

**Status: ACCEPTED at `c694e4a` (2026-09-28).** This review covers private, same-process validation startup only. It does not authorize a reserved-stream draw, validation generation, the combined CLI, product inference, real-data evaluation, broker access or live trading.

## What changed

A live PASSED calibration completion is consumed once. Validation startup opens a fresh two-hour deadline while retaining the unchanged 2 GiB address-space limit. It independently reopens and checks the calibration claim, result and inert candidate; recomputes the complete result against the original writer-bound expectations; rechecks review ancestry and exact evidence paths; then reserves an inert validation claim and result. The validation context binds the verified first-passing floor and completion lineage. The validation counted provider remains explicitly blocked. A failed startup permanently consumes the authentic attempt; an invalid or copied completion does not consume the original.

The contract clarification is in `docs/plans/2026-09-27-step6a2-task3-contracts.md`, and the bounded plan is `docs/plans/2026-09-28-step6a2-task3-validation-startup.md`. The unrelated audit-ledger status word for the previously accepted 4B finding was corrected to the declared vocabulary after the full suite exposed it.

## Independent review and verification

An independent Astra Medium read-only audit first identified the expired-calibration-deadline handoff problem, then reviewed the implementation. It found and required fixes for post-close deadline and artifact checks, live completion rechecks, the validation-provider RNG reachability, authority revocation during final reader cleanup, and file identity changes during a final hash. The final review found no remaining P1/P2 issue. Root separately reviewed the diff and the Linux scratch test. The pre-commit simplicity pass found no safe cut that justified reopening these ownership boundaries.

- Exact code commit: `c694e4ad9e16c37a0301c47cabed0e43f89cf914`; source SHA-256 `52ff75f3375f6e565dabf5df567d35652517a1f95c5fdeb39e85dc3581a1b5c9`. Committed source and test Git blobs match the reviewed working bytes.
- Final Windows unit suite: **1,586 passed, six platform skips**, 659.19s. The first full run exposed one pre-existing audit status vocabulary failure; the row was corrected, the targeted audit test passed 6/6, and the final full suite passed.
- Exact-commit [Ubuntu CI](https://github.com/Sujayprodduturi/Icarus/actions/runs/36417754332): **1,592 passed, four existing integration skips**, 603.65s; Ruff lint/format and strict mypy passed. The new native scratch-filesystem startup test ran on Linux.
- Local global Ruff check/format, project mypy (136 files), explicit script/test mypy and `git diff --check` passed. Line-ending-aware numstat matched ordinary numstat for every modified file.
- Three post-commit in-memory fault probes were caught: removal of the explicit validation-provider refusal (one guard-specific assertion failure), the final live-completion recheck (one missed revocation), and post-hash identity checks (two missed inode/hardlink changes). Each mutation applied exactly once; tracked file hashes and repository status remained unchanged.

## Limits and next step

The Linux smoke test uses scratch paths and real open-at, no-follow, fsync and descriptor operations. It scripts the statistical verdict, Git proof and resource setup; it does not prove official-run memory headroom or power-loss recovery. CI's four database integration skips remain open as finding F11. No review attestation for the complete counted runner exists, and neither reserved phase stream has been drawn.

Next: separately review and implement the combined counted CLI and validation execution path, then run exact-commit whole-runner safety/statistical review and a native Linux serialization/resource envelope check. Only after explicit whole-runner approval may the first counted calibration invocation be considered. `goal.yaml` inference stays disabled.
