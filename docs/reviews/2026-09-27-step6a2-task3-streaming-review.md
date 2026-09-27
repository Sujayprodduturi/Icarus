# Step 6a.2 Task 3C — streamed evidence review

**Status: ACCEPTED — independent review, final root checks, 7/7 post-commit probes and exact-commit Linux CI passed.** Code `12e1a8a` is pushed to origin/dev. This review covers calibration result streaming and the retained read-only descriptor handoff only.

Astra Medium reviewed simplicity, correctness and failure-test non-vacuity. Sol Medium was the sole code/test writer; root independently reviewed the implementation and reproduced numerical/verification evidence.

## Behavior and repaired findings

- Canonical ordered chunks stream to the exclusively reserved result; event partitions produce compact counts, CP summaries and first-passing candidate selection. Complete statistical failure remains UNVERIFIED evidence.
- Missing/extra/reordered chunks refuse. Size and offset checks prevent prepopulated or rewound result writes; file and directory checkpoints must both succeed.
- Safe-boundary failures may write canonical INCOMPLETE evidence with empty summary arrays. Saved chunks retain observed outcomes; no partial statistical verdict is invented. Failed storage/resources preserve partial bytes without reopening or repair.
- Allocation checks precede normal and failure serialization. Closing suffix and diagnostics are bounded; original deadline, memory limits and original file identities remain active.
- Successful handoff transfers an authenticated read-only descriptor into the context before the old writer's single close attempt. An uncertain close is never retried; descriptor-reuse tests prove an unrelated handle survives. Claim/directory handles remain for later independent verification.
- Completion timestamps must be valid UTC and cannot precede startup. Repeated finalization fails closed.
- Review repaired weak tests that initially failed on the claim descriptor before opening a reader, or only exercised the first file fsync. Separate witnesses now cover newly opened reader cleanup and a directory fsync failure after a committed chunk.

## Frozen bytes and checks

- Script SHA256 `cef45f9360d49fc3cc9ae4c4150c7f77a2b89ff74a459073d414c7638f2ddb15`.
- Tests SHA256 `6410e7363fba05ceaebd9463553bb2b8bf3722d0c59be51cc8bb13278c21c26f`.
- Astra and root matched these final hashes. Builder: 22 focused passes, one Linux-only skip; final allocation regression passed again after formatting. Ruff and explicit mypy passed.
- Root global Ruff lint/format, mypy (136 project files and explicit script/test), and whitespace checks passed. Previous-candidate full unit suite: 1,525 passed/four Windows skips; the final guard-inclusive full suite passed 1,526 tests/four Windows skips (230.91s), as recorded below.
- Root's 2,952-case old-code interval comparison remained byte-exact with SHA256 `c7f54a16ac1bff74ecad328703ffa141d6927e58ef2bf6e4660ebe9127812451`.

No reserved RNG was constructed. Manifest/digest/estimator remain unchanged; inference stays disabled. Slice 4 sealing, validation unlock, counted CLI and exact-runner first-invocation approval remain outstanding. Native Linux memory/serialization headroom must be proved before an official draw; scripted result sizes do not establish feasibility. Existing F11 database integration skips remain open.


Post-commit root fault probes: 7/7 caught (initial extent, diagnostic bound, handoff close ordering, duplicate handoff, directory checkpoint, startup cleanup and failure-path allocation). Mutations ran only in isolated in-memory copies. Tracked script bytes retained the approved SHA256.


Final root full suite on the formatted guard-inclusive commit: 1,526 passed, four Windows platform skips, 230.91s. Final-commit numerical comparison again reproduced all 2,952 interval outputs and the exact baseline digest. Ruff lint/format, project and explicit mypy, whitespace, committed-byte equality and 7/7 fault checks are clean. Exact Linux CI subsequently passed, as recorded below.


Exact code commit `12e1a8a50d42e81b6673146db4bf78c6a4016861` passed Ubuntu CI: **1,530 passed, four pre-existing integration skips, 194.21s**, with Ruff lint/format and mypy clean. Native Linux resource/filesystem checks and the actual read-only descriptor test executed successfully. Evidence: https://github.com/Sujayprodduturi/Icarus/actions/runs/36313816437. This closes Slice 3C and the bounded Slice 3 milestone. F11 remains open; no official calibration/validation draw, seal or trading inference was enabled.
