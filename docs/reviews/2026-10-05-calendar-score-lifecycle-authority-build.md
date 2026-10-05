# Calendar-score Unit2 fixed-fixture lifecycle build

Approved plan: `docs/plans/2026-10-05-calendar-score-lifecycle-authority.md`, SHA256 `f27fa39463eaf8e6e16bc3b4ac805ba402dbae0722b50ee4324ad5c828a05744`.

This build implements only the fixed TEST lifecycle. Experimental reservation, experimental CounterStream access, actual study keys, Unit3 sampling and statistical study authority remain unavailable. `FIXTURE_ACCEPTED` and `study_permission:false` describe control-flow fixture evidence, not a study verdict.

The fixed anchor admits one exclusive attempt directory per case. A partial or failed reservation exhausts that case. A live session can originate only from successful durable reservation; copied objects, mutable identity drift, saved records and caller state assignments cannot issue authority. Every consuming transition rechecks its reservation, current source/resource binding and owned state record.

A trusted reviewer launcher provisions separate coordinator and approval pipes before spawning the coordinator. The reviewer service starts only after reservation. Secrets travel only through the private inherited bootstrap pipe; the coordinator receives no reviewer channel or reviewer secret. The helper independently validates the full reservation before its public fixed TEST key is selected. Authentication binds role, sequence, challenge, session, peer PID/creation time and source binding. The separate approval channel checks exact fresh evidence and both receipt digests. Release is recorded durably once before sending the fixed key.

Writer, primary verifier and reviewer verifier execute in separately supervised, sequential child invocations. Owned exit status, heartbeat thread joining, canonical bounded completion ACK, durable fixture records and final source/resource checks issue local identity-bound tokens. A bounded reader process protects partial ACK reads; the service watchdog covers blocking bootstrap/authenticated reads and peer death. Refusing a swapped child handle shuts down only the saved owned process/channels/monitor. Shutdown errors attach secondary notes without masking the original error.

Finalization rechecks validation evidence, both receipts and exact approval record. Cleanup requires genuine owned primary/reviewer tokens and fresh evidence; it records intent before the immediate bounded raw identity/hash check, deletes only `fixture-payload.bin`, proves absence and records completion. Any cleanup failure terminalizes the session and writes honest error evidence; compact records are retained.

The complete Unit2 extended manifest is retained inside every reservation and bound to `SourceBinding.manifest_digest`. It extends the unchanged study source list with both new modules, this approved plan and the executable test harness module. The harness is a real runtime dependency, so its inclusion is necessary source closure, not a timing qualification. All per-session/runtime/source bindings are fresh; no cache or worker warming was added.

PID creation-time precision is the available psutil timestamp resolution. This is API/process ownership enforcement, not protection against an administrator or malicious code with arbitrary access to Python internals. Directory durability across power loss and secure key erasure are not claimed. The fixed fixture uses P1, n=2048, replicate=0, zero-key TEST payload: 2050 bytes, 12300 consumed words and three metrics. Public control-flow keys 01/02 are separate from that payload identity.

Initial focused GREEN was 50 passed in 114.37s. Final focused/static evidence and retained demo are recorded below after completion. No global regression, full-geometry timing, broker/network call, commit, push or raw cleanup was performed by this builder.

## TDD and failure evidence

Ignored logs are under `var/verification/2026-10-05/calendar-score-lifecycle/`. Meaningful RED evidence includes `publication-red.log` (candidate mutation/invalid transition), `issuer-red.log` (unissued session), `ownership-red.log` (inline verification/foreign child/startup), `reviewer-binding-red.log` (changed rehashed receipt), `final-binding-red.log` (accepted changed final receipt), `process-swapped-red.log` and `owned-cleanup-red.log` (wrong cleanup target/owned process leak), `helper-reservation-red.log` (helper did not independently reject wrong reserved counts), `failure-binding-red.log` (failure written to substituted root), `private-facts-red.log` (public list clear/heartbeat update), and `private-stop-red.log` (public monitor shutdown).

Fresh focused checks cover real separate reviewer/coordinator processes; full valid coordinator-authenticated approval refusal; an actual second authenticated release with fresh sequence; copied genuine release/cleanup tokens; actual coordinator/helper death; partial reservation write; lost heartbeat and duplicate-key ACK; owned reader timeout; primary/ACK error plus shutdown failure; rehashed schema drift; current final receipt checks; complete manifest retention; successful dual-check cleanup; and deletion-error preservation. These are fixed TEST behaviors, not actual-study evidence.

Captured failure metadata uses the original registry, original identifiers, original source/owner binding and fresh UTC. Broken current source/resource loading or caller-mutated session fields cannot redirect or rewrite the failure binding. Failure persistence errors attach notes while the original exception survives. Cleanup errors retain the truthful raw absence/remaining status and halt the live session.

Prior candidate byte hashes (reviewer HOLD; superseded below):

- `scripts/research/signal_calendar_score_lifecycle.py`: `6f096ad7521913e305d81b6a85b04609113a6bc827f6ba98312b1a5dc4396791`
- `scripts/research/signal_calendar_score_lifecycle_service.py`: `a4630691efa21fb87ef69496d3d039de53be13a0a6cd1791584757a8ab581324`
- `tests/unit/test_signal_calendar_score_lifecycle_research.py`: `3e3f4710cdc2825fd735c9d8aa83b620080418a29572fbc67c63db457009838f`

Unchanged existing research source hashes freshly checked: study `8a23e5c93232c9d9c4f1f46cbce10a9f7b3903b0070dd8ac2dfb9d03e5506c5e`; verifier `40f40acd5096f69b52e7694317c67c2fd6213b543f02f7514d174385e569cb02`.

Strict mypy checks all three new source/test files clean (`mypy-final.log`); Ruff no-cache checks clean (`ruff-final.log`). Private runtime supervision owns the error list, real heartbeat timestamp, timer and stop event; public child-handle facts are immutable snapshots/read-only boolean and cannot suppress those guards.

Terminal revocation was proved with two additional real-process REDs: `terminal-channel-red.log` admitted a correctly authenticated release after local failure; `terminal-close-red.log` admitted a raw authenticated release after failure-file persistence was denied. The corrected session terminal guard, fresh helper failure-existence guard and captured coordinator-endpoint closure pass `terminal-close-green.log` (3 tests, 20.86s, including the full fixture lifecycle). Helper termination classification may be the failure-file/watchdog guard or EOF authentication refusal; neither path can release. Failure always attempts closure independently of evidence durability. No caller-mutated endpoint is selected for shutdown.

`empty-issuer-red.log` exposed an unissued empty object's AttributeError masking the issuer refusal. Validation now checks issuance before accessing state, and independent shutdown-error capture preserves that refusal. Public monitor stop access also failed meaningfully in `private-stop-red.log`; only the private captured event can stop the monitor. Close-error notes and the copied/forged-object cases remain part of the focused selection.

## Prior builder handoff

Final focused suite: **60 passed in 138.87s** (`focused-final-freeze.log`). After that run the sole change was Ruff inserting one blank line in a test-local import block; no behavior changed. The final exact-byte strict mypy, Ruff check and Ruff format checks all pass (`mypy-final.log`, `ruff-final.log`, `format-final.log`). Root will supply the exact-final-source broad regression. Constructor parse errors now preserve the original exception, terminalize the reservation and close the transferred owned endpoint; `client-bootstrap-red.log` records the previously live reservation.

The named retained full demo is case `builder-retained-unit2-20261005-a`, registry `var/verification/2026-10-05/calendar-score-lifecycle/attempts/57669f73becc931bcea905be35256ebe0a8f9755ebdae382e72c20ce062d0b19`. `retained-demo.log` confirms `FINAL_VERDICT`. Both `evidence/fixture-payload.bin` and `validation-evidence/fixture-payload.bin` remain, alongside claim/index/report/terminal, primary/reviewer receipts, full source-bound reservation, development/validation phase records, exact reviewer approvals, commitment seal, release-once and final fixture verdict. No cleanup was invoked for this named demo. Its coordinator and reviewer helper have exited; files cannot restore live authority. Root/reviewer must independently inspect before guarded raw-only D44 cleanup.

This was the prior builder source/test freeze; the subsequent reviewer HOLD and correction are recorded below. Independent source review, root saved-file checks, broader checks, commit/postcommit defect checks and repository state documentation remain with the root agent. This build record does not mark actual sampled-study tasks complete or grant experimental access.

Post-demo identity checks (`retained-exit-check.log`) confirm the captured coordinator PID26912 and helper PID6892 are no longer the same live processes. Persisted development/validation writer completion proofs record exit code0; their captured identities and the reviewer-parent identity are also no longer live. The CLI launcher exited0. Top-level coordinator/helper numeric exit codes were not persisted by the harness, so no additional exit-code claim is made.

## Reviewer HOLD correction

The prior candidate's root broad gate passed 610 tests in 167.06s, strict mypy passed 173 files and global Ruff passed. A cached formatter panic was retained; a fresh no-cache format check passed 334 files. Those results belong to the prior candidate and do not qualify the corrected source.

Independent saved-fixture math/provenance checks of case `57669f73...d0b19` passed, but final review held worker/service teardown: their first join/close failure could mask the original failure and skip remaining owned endpoint closure. No earlier raw or compact record was modified by this correction.

`final-shutdown-red.log` demonstrates three meaningful failures (worker write and verify original failures masked by completion close; service original failure masked by first close). The fourth case already passed: actual raw unlink followed by denied completion-receipt persistence. Existing `_shutdown` now captures the original failure and independently attempts stop, explicit thread join and every owned endpoint close. Thread startup is inside the guarded boundary. Worker failures rethrow the original error; service failures retain their existing structured failure conversion. Secondary teardown failures attach notes. `final-shutdown-green.log`: 4 passed in 10.62s.

The added actual post-unlink regression proves validation raw absence, retained development raw, durable cleanup intent and honest `CLEANUP_ERROR/raw_status:absent`, no completion record, original denied-write exception identity and refused same-session retry. It adds no phase or sampling authority.

Corrected candidate hashes: lifecycle `ba67c3e163b4d9fb9a3fd816e2d5a4677046c3b938779820186468024a41bdb3`; service `35a8d68f80c723e309531984e16940f0a6f0587075ea434e97b7919862f559b8`; tests `e74ca719249de89937e3a366c682a23b69794f5bdb08486d0f543df5acc16ca5`. The approved plan hash remains `f27fa39463eaf8e6e16bc3b4ac805ba402dbae0722b50ee4324ad5c828a05744`.

Corrected strict mypy (three files), no-cache Ruff and no-cache formatting checks pass in `mypy-corrected.log`, `ruff-corrected.log` and `format-corrected.log`. Full focused and new retained-demo results follow below after completion.

## Corrected freeze

`focused-corrected.log`: **64 passed in 141.51s**. The exact tested source was not edited afterward. Strict three-file mypy, Ruff and formatting no-cache checks are clean. The targeted and full results belong to the corrected candidate hashes above; root owns fresh broad regression and final independent approval.

New full retained case `builder-retained-unit2-20261005-b` reached `FINAL_VERDICT` (`retained-demo-corrected.log`, launcher exit0). Its registry is `var/verification/2026-10-05/calendar-score-lifecycle/attempts/2b1bce56091f4fd2a185285fdd52dd0d36fcfeb9dd1ae2cfff0649610da11540`. Both 2050-byte raw files and all compact records/receipts remain. The reservation contains the complete corrected extended manifest. No cleanup or retry of either named retained case occurred.

`retained-exit-corrected.log` records both writer exit-code0 proofs, fresh captured-process liveness checks, raw sizes, manifest digest and exact final source/plan hashes. As before, top-level coordinator/helper numeric exit codes are not persisted; captured identities are checked no longer live. The old retained case remains historical evidence at its original path, unchanged.


## Final primary qualification2026-10-05

Corrected exact-source gates:64 focused and614 related tests (181.85s), strict173-file mypy, global no-cache Ruff and334-file formatting pass. Root independently hashed the three approved files, reproduced both complete saved fixtures with its separate literal SHA/naive scalar rational oracle, and checked15 canonical records/25 source hashes. Reviewer independently repeated complete checks and gave ordered GO. Final compact fixture/cleanup proof is `2026-10-05-calendar-score-lifecycle-fixture-checks.json`; earlier HOLD evidence remains unchanged. No source change after freeze, no actual study. Postcommit defect/restoration provenance is recorded separately.


## Postcommit qualification

**Unit2 final code provenance2026-10-05:** Code commit08cbb81d4edc25a79d4a45a96260082814dd59bb independently reviewed and qualified. Three deliberate postcommit defects were caught: forged coordinator approval, repeated key release and copied reviewer cleanup authority. Root and reviewer inspected actual unauthorized-deletion records for the third witness; its expected-error check failed as KeyError rather than AssertionError, and the initial overly strict ignored capture script rejected that classification. Original logs and all four witness records are retained; no source fix or rerun concealed it. Exact approved three-file bytes restored from exclusive snapshots, then fresh298 affected regressions pass153.54s; strict173-file mypy and global no-cache Ruff/334-file formatting pass. Compact postcommit proof: docs/reviews/2026-10-05-calendar-score-lifecycle-postcommit.json. Documentation-only provenance follow-up is exempt from another source mutation cycle. Normal dev push follows; remote current-source CI is not assumed.
