# Task 3 execution ledger - 2026-09-27

Plan: `docs/plans/2026-09-26-step6a2-task3-counted-gate.md`; parent protocol remains unchanged.

## Authorization and baseline

- User authorized continued planning, implementation, scouting and independent review with role-appropriate models. D23 remains the scoped process boundary; no broker, real-data or inference change is authorized.
- Start: `dev` at `6c5bc77`, 47 ahead of locally recorded origin/dev; only user-owned AGENTS.md untracked. Preserve it.
- Model routing: Sol High for detailed planning/building, Terra High for platform scouting, Astra Medium for architecture and independent safety decisions.
- Fresh baseline: `uv run --frozen --no-sync pytest tests/unit/test_signalcalibration.py tests/unit/test_signalcalibration_task2.py tests/unit/test_portfolio_characterization.py -q` -> 62 passed in 45.15s.
- Frozen manifest SHA256: `0ffd312b3a3bfd03d465bc1ce5d655bff2055861a99d1cf4c17287b4a450e3e5`.
- Estimator SHA256: `7d4a9a4064ef64b12a503e923d1fe04575bae6341933c101b32f666744b03d3a`.

## Preflight interface review

| Slices | Shared contract | Ruling/status |
|---|---|---|
| 1 and 3 | Stable claim, result/seal paths, phase identity | Exact schemas and validation evidence allowance required before code |
| 2 and 3 | Per-replicate partitions, counts, CP checks, selected floor | One canonical count derivation and independent verification; no summary boolean authority |
| 1 and 4 | Resource proof and private draw context | Platform refusal must happen before attempt claim and RNG construction |
| All | Protected harness and immutable manifest | No unprotected helper code or silent manifest edits |
| 1 | Refusal tests before implementation | No reserved-seed construction in tests |
| 2 | Candidate eligibility before observations | Manifest masks/family sizes unchanged |
| 3 | Completion only after reread/verification | Failed evidence cannot acquire a completion seal |
| 4 | CLI cannot bypass provenance/resource/evidence | No seed/count/floor/resume override |

Ruling: native Windows counted invocations refuse before claim/RNG; deterministic/fixture work remains supported. Astra accepted this as within the existing fail-if-unsupported scope. Linux local-filesystem backend must prove secure handles, directory fsync and resource controls before draws. Hard RLIMIT_AS at 2 GiB is an additional conservative address-space cap, not renamed RSS; retain peak-RSS checks and the 2-hour elapsed cutoff including verification. No operating-system changes are authorized by this ruling.

Initial status (superseded by entries below): exact contract drafting and review in progress; implementation not started. Frozen phase streams remain unopened.

## Slice 1A authorization

Astra Medium approved a bounded code slice while the full contract finishes review: private strict canonical JSON parsing, metric event-ID partition validation, and pure CP/count/check recomputation against frozen inputs. This does not approve the full phase-result verifier, attestation, artifact I/O, context, counted RNG, CLI or validation unlock. Scripted tests only. Sol High implements only the protected harness and a new Task-3 unit-test module; reviews and commits remain orchestrator-owned.

Stable metric partition inputs: declared replicate range, metric, emitted/refusal/coverage/lower/upper/joint IDs. Enforce integer-not-bool, exact keys, known refusal reasons, complete/disjoint sorted ranges and correct emitted/generated denominators. Counted streams stay closed.

## Full plan review

Astra Medium approved the clarified Task-3 plan/contracts for bounded implementation after schema, one-floor validation, streaming timestamp, resource-seal, base-count and parity-scale corrections. The original three plan blockers are closed. Parent spot-checked the clean-tree contradiction, result-schema literal, future timestamp streaming conflict, validation floor restriction and required parity scale. Native Windows refuses counted work; Linux capability remains an acceptance test. Exact-runner approval before any frozen draw is still mandatory.

## Slice 1A implementation and independent review

- Sol High built only private canonical JSON parsing, frozen event-count records, strict metric-ID partitions and CP summary recomputation in the protected script, plus deterministic tests. Initial red: 37 missing-helper failures; focused green: 40 passed after review fixes.
- Terra High ran simplicity review first (lean, no changes requested), then correctness/security review. It found unnormalised Unicode/recursion failures; the builder reproduced those plus Python's oversized-integer ValueError and added narrow normalisation. Final independent verdict: APPROVE Slice 1A only, no remaining blocking finding. Reviewer inspected code but did not rerun tests.
- Parent independently reproduced the denominator witness with SciPy: 9,000 covered / 9,500 emitted gives conditional CP lower 0.938148997904319; the same 9,000 / 10,000 generated gives joint lower 0.8881687832767389. The conditional check passes 0.93 while the joint check fails.
- Broad checks exposed a historical audit-document schema regression (missing ranked table). Added ten actual design findings with DECIDED statuses; implementation remains pending. Audit tests: 6 passed. No test was weakened.
- Global Ruff check/format and mypy passed for 137 files; tracked numstat matches ignore-CR numstat. Final frozen-diff unit run: 1,350 passed in 85.32 seconds, exit 0. Post-commit mutation results are recorded below.
- The initial unrestricted pytest invocation produced no output for more than three minutes and was stopped; no all-tests/integration pass is claimed. A unit run overlapping red-test edits is superseded by the final frozen-diff run.

## Accepted commit and post-commit probes

Slice 1A is committed at `5a6e721`. After commit, three isolated subprocesses replaced exception handlers in the imported module's in-memory source only: Unicode encoding, oversized-integer decoding and recursion decoding. Each mutation produced exactly 1 failed / 39 passed tests, exit 1. The probe harness asserted the mutation anchor existed and all source bytes remained unchanged; harness SHA256 stayed `505bdf752a62c776bc25bec2db5da91655295936069713710d44e59950296481`. No working-tree restoration or git checkout was used. These are parser regression checks, not evidence of the unbuilt full verifier.

## Next: Slice 1B pure complete-result verifier

Sol High scouted the next bounded increment: strict envelope/provenance, all-cell chunk topology, base-event wrapper, parity validation, recomputed summaries and first-passing floor. No I/O, Git ancestry, resource enforcement, CLI or RNG. The wrapper must require parity and forbid BELOW_CALIBRATED_BLOCKS / BELOW_CALIBRATED_DF in base event partitions.

Before code, pin the expected-context input carrying the independently verified calibration floor (required for validation, absent for calibration), ordered cell metric arrays, runtime-source binding and the limits of deterministic refusal-control proof. Never infer the validation floor from the validation artifact itself. Initially the typed-context clarification lacked a new Astra verdict because the follow-up hit the agent service thread limit. On continuation a fresh Astra Medium reviewer approved the clarification; exact constraints are now recorded in the contracts. Root pinned immutable canonical-byte record storage and Linux runtime literals as routine representation choices. Existing full-plan approval and Slice 1A approval stand; this is not exact-runner or draw approval.

Slice 1B tests must cover production-shaped complete calibration and one-floor validation fixtures, nested-key/provenance forgery, reordered or missing cells/chunks, forged CP summaries, missing/mismatched parity, forbidden floor refusals, non-first calibration selection and extra validation candidates. Reduced fixtures may test private helpers only; the public verifier must traverse the full frozen manifest.

## Slice 1B continuation — medium effort only

D26 authorizes continued work to major milestones, medium-effort delegation/reviews and GitHub pushes. Fresh Astra Medium approved the expected-context clarification; Sol Medium implemented and Terra Medium independently reviewed. `dev` was pushed through `5878ad7`, then through contract/decision commit `a733c6a`; the remote full SHA matched local HEAD after the initial push.

The frozen first review candidate passed 83 focused tests independently in 45.61 seconds; before/after hashes matched (script `1c429dbbf5030c52c16d37778e3505985a1268d78d53da18379316b80d01e44f`, tests `37f288b3a232fb2f40f47ff5f0d4beff1b8bcca49b8de9433a287d0f9eeb6877`). Global Ruff/format/mypy also passed. These checks are superseded by final verification after review fixes below.

Simplicity review found no unnecessary abstraction. Correctness/security review found sample variance using a dimensionless tolerance and huge-integer float conversion escaping as OverflowError. Parent confirmed the latter independently and added an unhashable context-phase refusal case. Earlier protocol checks also caught max-versus-additive tolerance and identically forged interval bounds; regression tests cover those and overflowed scale. Fixes remain within strict evidence verification, with no frozen-threshold change. Final Terra Medium review APPROVES Slice 1B only, with no remaining actionable finding. Root verified the reviewed Git blobs: harness `c769cc101957fd860f082398e9e33466803261cd`, tests `e97cea6a5705f14b2446dad2a4a802eb5ecae86c`. Final focused suite: 87 passed; global Ruff/format/mypy passed (137 files). Final parent full-unit run: 1,397 passed in 123.86 seconds, exit 0, including portfolio characterization. Global static checks passed on final bytes. Per-file diff numstat matched ignore-CR numstat. Post-commit mutation results follow below. No artifact I/O, trusted production-context construction, resource enforcement, RNG, CLI, seal or validation unlock was added; unsaved-trigger completeness remains an orchestration obligation.

### Slice 1B accepted milestone and fault checks

Committed at `8987ccd`. After commit, 12 isolated in-memory fault probes were detected: additive tolerance changed to max; endpoint recomputation removed; scale-overflow guards removed; sample variance made dimensionless; huge-integer conversion guard removed; phase type guard removed; exact refusal-reason check removed; runtime caps removed; calendar validation removed; floor comparison weakened to Python equality; verified output changed to mutable dict; expected-provenance shape validation removed. Each probe had an asserted mutation anchor and a selected regression test failure (exit 1). No source file was modified; final harness SHA256 remained `7619a5f0b88526e243b2b4911ab860b37d6d2df3cdc6cbf9a349d1c1c0e8849e`.

The first probe launcher hit Windows command-line length limits before applying a mutant; passing the in-memory source through stdin resolved it. This setup failure is not counted as a detected fault. Frozen manifest, digest, estimator and inference setting remain unchanged. Next is Slice 2: review attestation/ancestry, exclusive claims/results, Linux resource and durability enforcement, with no counted draw until whole-runner approval. Seal paths are derived but remain unopened until the later verification boundary.

## Slice 2 — safe experiment startup and recording

Start: `7e1a895` on dev, synchronized with origin/dev, only user-owned AGENTS.md untracked. User authorized continuing Step 6a; medium effort remains mandatory. Fresh Astra Medium approved four bounded increments: strict review/Git provenance; private Linux resource controller; retained-handle exclusive claim/result storage; closed-by-default phase capability. Sol Medium is the sole script/test implementation writer.

Key rulings: compare every tracked working-tree byte to HEAD and use NUL-delimited Git paths; enforce each intervening commit as well as endpoint diff; deadlines cover preflight/subprocess/finalization; never install irreversible hard resource limits in the pytest supervisor; no seal reservation; no production validation context until the later verified calibration trio. Private test seams may inject failures but the production entrypoint exposes no pretend-Linux override. Failed or partial claims are never repaired, removed or replaced.

Windows tests prove refusal order and injected-failure behavior only. Native Linux syscall/filesystem enforcement requires separate actual-kernel tests. Docker Desktop was installed but stopped at the read-only survey; the orchestrator is checking whether isolated Linux tests can run on this PC. This is not counted-host certification or an OS migration. Reserved streams remain unopened.


### Local Docker test-host blocker

Docker Desktop 4.83.0 failed before the Linux engine became available: Windows rejected access/removal of `Docker/run/dockerInference`, then `docker-secrets-engine/engine.sock`. Both original sockets were dated 2026-07-27. After stopping only identified Docker processes started during this investigation and terminating only docker-desktop, the runtime directory was preserved as `C:/Users/sujay/AppData/Local/Docker/run-backup-20260927-0815`. The secrets-engine directory was independently checked to contain only the zero-byte engine.sock and preserved as `C:/Users/sujay/AppData/Local/docker-secrets-engine-backup-20260927`; an attempted individual socket rename failed without moving it. Each host mutation used approved escalation. No factory reset, image/volume deletion, configuration edit or diagnostic upload occurred.

Restart progressed to the second socket failure, then failed again on a newly created inference socket dated today. Thus stale July files alone do not explain the failure; underlying Windows/Docker socket handling remains unresolved. The final failed Docker instance and its WSL distribution were stopped to prevent repeated popups. Native Linux verification is blocked; Windows-capable implementation/testing continues. Related upstream reports describe the same two endpoints, but their proposed causes are not independently established here: https://github.com/docker/desktop-feedback/issues/531 and https://github.com/docker/desktop-feedback/issues/554 (consulted 2026-09-27). Do not represent this recovery attempt as successful or these reports as proof of kernel corruption.

### Existing GitHub Linux CI recovery

Read-only inspection found the latest pushed baseline `7e1a895` CI run failed before pytest, on Ruff formatting of Python examples in two September 25 plan documents (run https://github.com/Sujayprodduturi/Icarus/actions/runs/36304765916). Reproduced using the pinned local Ruff 0.16.0 when targeting these Markdown files explicitly. Earlier global-format claims did not establish CI success. Applied only whitespace/layout formatting; root simplicity and correctness review found no semantic changes, and explicit format checks passed. Documentation-only commit `fbf6950` was made to unblock the existing Ubuntu workflow, without changing the workflow, dependencies or statistical contract. The existing CI runs unit and integration tests; its live outcome must be checked, not inferred from local Windows results. Builder will add Linux-only subprocess/syscall fixtures to the Slice 2 tests; until those pass on Linux, platform acceptance remains unproved.

### Slice 2 review in progress

Root completed an early simplicity pass on provenance/resource helpers, then raised correctness fixes: normalize review paths strictly; reject ambiguous stacked mounts; retain/recheck ancestor directory handles; close owned handles on every failure without removing reservations; prove attestation rejection with single mutations of valid fixtures; prove byte checks despite Git assume-unchanged; and exercise the production controller in Linux subprocess tests. These are pending implementation/reverification, not closed findings.

Astra Medium resumed independent review (new reviewer creation hit the service thread limit). Its simplicity pass found no justified cuts in the stable wrappers; these provide deterministic fault injection. Additional correctness blockers: bind the parsed attestation hash to the actual tracked attestation bytes, and reject index-only staged additions that evade both the HEAD tree scan and untracked-file listing. Both were sent to the builder for test-first fixes. The resource review found no additional blocker beyond queued mount/handle issues, but ongoing context guards and final Linux proof remain to be reviewed after code freeze.

Baseline CI outcome: `fbf6950` passed https://github.com/Sujayprodduturi/Icarus/actions/runs/36305873021 on Ubuntu: Ruff lint/format clean, mypy 136 files clean, pytest 1,397 passed and 4 skipped in 141.21 seconds. This is the pre-Slice-2 baseline only. Four integration tests permit skipping when database/migrations are unavailable, and the workflow has no migration step; do not call this evidence that integration behavior passed. New Slice 2 Linux tests are not in this commit and remain unverified.

Integration review found further open blockers before acceptance: a failed active-context check must permanently invalidate the context; compare current file identities to the originally retained identities, not just fd-versus-current-path; reject directly constructed/unissued contexts; provide continuing allocation/current-RSS, peak-RSS, result/verifier projection and deadline guards rather than a startup-only snapshot; register descriptor ownership immediately after opening so fstat/reopen failures cannot leak handles; and prevent double-close after a successful writer close followed by a directory-fsync failure. Root and Astra findings were sent to the sole builder. The earlier attestation-on-disk binding and staged-index checks were independently confirmed repaired, but the full slice is not yet accepted.

### Slice 2 frozen code and pre-push verification

Astra Medium independently approved the final bounded implementation after simplicity then correctness/security review, contingent on root checks and Linux CI. Harness SHA256 `7ca96e4bb1ba48160089d5f676ae0cef01725e45e5c6d9e7c119c3834d9c9b8d`; tests SHA256 `3a785197f5607086aeb10b9ce8330c948dc91acd70e4608d12fc63d8970fdc5d`. Root independently matched both. Review blockers above are repaired: canonical bound identities, frozen context, nested evidence/claim checks, permanent closure, original inode binding, descriptor ownership, ongoing RSS/VMS/allocation/projection guards, actual attestation binding and staged-file refusal. Resource guards must still be wired into every operation by Slice 3; no counted provider exists yet.

Builder focused verification: 149 passed, 3 Windows skips in 75.21 seconds, explicit two-file mypy and Ruff clean. Root fresh full unit verification: 1,459 passed, 3 skipped in 147.42 seconds; global Ruff lint passed, format 179 files clean, mypy 136 files clean. Root documentation formatting and `git diff --check` passed. The three Windows skips cover Linux hard-limit subprocess, Linux secure filesystem behavior, and symlink creation. Native Linux acceptance is pending CI; no completed-runner attestation or frozen draw is authorized. All three frozen manifest/digest/estimator SHA256 values independently match the prior accepted values; `inference_enabled` remains false.

Post-commit verification at `e2eb171`: 18/18 in-memory subprocess fault probes caught the intended broken safeguards, with the exact committed harness SHA256 unchanged afterward. This covers all major repaired review boundaries; no tracked source file was overwritten or restored during mutation testing. The code commit is pushed to origin/dev. Native Linux CI run `36307683127` is in progress; final acceptance remains contingent on its new kernel tests. The [controller review record](2026-09-27-step6a2-task3-controller-review.md) records the frozen hashes, reviewer verdict and boundaries.

### Slice 2 accepted milestone

GitHub Ubuntu CI for exact code `e2eb171fa93f94cd38362559454b1e61bb10d637` passed: https://github.com/Sujayprodduturi/Icarus/actions/runs/36307683127. Pytest: 1,462 passed, four existing integration skips, 144.06 seconds. All three Windows-skipped tests executed on Linux, including the production resource controller in an isolated subprocess and actual secure filesystem syscalls. Ruff lint/format and mypy 136 files passed. Root independently verified committed Git blob bytes equal the reviewed working bytes. Slice 2 is accepted; Task 3 and Step 6a remain incomplete. No production completion attestation or frozen-stream draw occurred.

Next: Slice 3 counted-provider/chunk orchestration, wiring every allocation, chunk, write and failure through this controller; then Slice 4 completion sealing and calibration-to-validation unlock. Whole-runner independent exact-commit approval remains mandatory before the first reserved draw. Docker repair is still unresolved on this PC; it no longer blocks Linux code verification because existing GitHub CI supplied the required tests. Existing integration-skip finding F11 remains open separately.


### Slice 3 implementation breakdown

Continued under the operator's approved scope on 2026-09-27. Independent Astra Medium design review and Sol Medium numerical scouting agree on three independently reviewed increments: 3A shared synthetic equations and authenticated sequential component provider; 3B base metric events and exhaustive parity; 3C canonical streaming result orchestration. The existing durable ledger remains the work record. Service agent limits require reusing the known-medium planner and sole builder; code writes remain serialized.

Failure-writing ruling for 3C: finalize INCOMPLETE only at a known valid append boundary while resources and storage remain usable. Partial write, fsync/storage or exhausted-resource failures may leave invalid reserved bytes; close permanently without repair, retry, replacement or seal. This is consistent with the immutable failed-attempt contract.

3A is now in progress. Its tests use separate fixture-seed/scripted arrays and reserved-seed constructor sentinels. No real counted context, evidence claim, reserved stream, CLI unlock, validation authorization, estimator or frozen manifest change is permitted. Full Task 3 remains incomplete until the later increments and Slice 4 pass independent review.

Root captured a pre-change fixture baseline directly from committed harness `5250d0f`: all 82 calibration/validation cell definitions at replicate IDs 0, 255, 256 and final (328 vectors), using only the separate fixture seed. SHA256 of concatenated sorted compact dataclass JSON is `170e35d2898b98db2b4152e0a2b6fb3b7674438b28a33dc4fd6b3334d3b64cc6`. The refactor must reproduce this exact digest; this supplements shared-core tests with an independent old-code oracle.

3A design review added a one-provider-per-context ownership requirement: constructing another generator during or after the original traversal must refuse before RNG, preventing replay within one claimed attempt. Normal exhaustion preserves the context for later result finalization but releases all provider cache; generation failure closes permanently. Direct reserved-seed RNG helpers without authenticated context are excluded. Allocation projections include Python tuple/scalar overhead as well as NumPy storage.

Forward 3B review clarified that independent scalar evaluation is mandatory for each fixed or triggered audit record, not every ordinary untriggered replicate. Full batch moments detect triggers for every metric/replicate; audited scalar values come from the unchanged production estimator. Effective N must be uncapped, decisions use raw endpoints, nonfinite intermediates must remain visible as triggers, and CR1 needs independent hand-case formula tests. This is design guidance only; 3B is not implemented or accepted.

Root differential check after the shared-core extraction reproduced all 328 baseline vectors and the exact saved SHA256. Early provider review required direct draw callbacks to refuse outside active generation, unexpected StopIteration to invalidate rather than permit retry, and removal of repeated full-manifest JSON parsing from the per-component hot path. Builder implemented those fixes with refusal tests; final independent review and checks are still pending. A further exact component-size/preallocation check is under review. These development checks are not acceptance of the completed runner.

### Slice 3A frozen review and root verification

Astra Medium approved the exact bounded provider after simplicity then correctness review. Harness SHA256 `d4bce154df39bec268e6fa4799a23b17475fb31a1c2e4bc33c0525d5fa93df32`; tests SHA256 `7a5d11c3ed78a97e63bbd5c35da37ce1c4c0b5490ed58c6d57357803ca7849e5`. Root matched both. Exact geometry-derived sizes, one-provider ownership, active draw windows, unexpected StopIteration closure and row isolation now have regression witnesses. All 45-cell topology and nine-family safe-seed traces are tested. No reserved RNG was constructed.

Root fresh full unit suite: 1,481 passed, three Windows skips, 148.98s. Global Ruff lint/format (181 files), project mypy (136 files), explicit harness/test mypy, documentation formatting and whitespace checks passed. Independent 328-vector old-code comparison reproduced the baseline digest exactly. Builder separately verified Task 2: 38 passed; Task 3: 171 passed and three skips. Frozen manifest/digest/estimator SHA256 values remain unchanged; inference remains disabled. Code commit, post-commit fault probes and Linux CI follow; 3B/3C and Slice 4 remain unbuilt.

Provider code `71820d8b1d64a495d3a354a5114910c43a37514a` is pushed to origin/dev. Root verified exact committed blob equality and caught 5/5 in-memory post-commit mutations covering single-provider ownership, exact component widths, row isolation, active draw windows and unexpected StopIteration failure closure. Tracked source bytes remained unchanged. Linux CI is pending; the [provider review](2026-09-27-step6a2-task3-provider-review.md) records the bounded verdict and evidence.

### Slice 3B design accepted; implementation starting

Astra Medium approved the bounded statistical event/parity adapter design. Preserve the public interval API, confidence and win-display clipping while extracting full batch moments and retaining finite-input nonfinite-intermediate failure flags. Counted records use frozen confidence and raw endpoints. Effective N is uncapped. Each metric has independent event/refusal partitions; joint-success IDs equal coverage IDs. Scalar evaluation is required only for fixed/triggered records, with every replicate checked for triggers. Near-zero/t-critical apply only to emitted records; zero-variance refusals always receive the zero trigger. CR1 has its own formula and remains report-only.

The adapter must validate chunk/metric identity against the frozen topology and invoke the existing partition/parity validators before returning, so disagreement halts immediately. No RNG, context issuance, result writer, seal, CLI, new project module or frozen-file changes are included. Sol Medium is again the sole code writer, tests first; root handles records and independent checks. 3A exact-commit Linux CI is still pending at this entry.

Root captured the pre-3B public interval baseline directly from committed `71820d8`: 2,952 cases across all 82 cells, four boundary replicate IDs, three metrics, and confidence levels .90/.95/.99. Only fixture-seed vectors were used. Concatenated compact sorted output JSON SHA256 is `c7f54a16ac1bff74ecad328703ffa141d6927e58ef2bf6e4660ebe9127812451`. The full-moments refactor must preserve these public outputs exactly, including nondefault confidence and win display clipping.

### Slice 3C ownership ruling before implementation

Astra's initial 3C sketch closed the context on success. Root rejected that because Slice 4 must independently reopen through the retained directory handles under the original deadline. Astra corrected and approved a one-way writer-to-reader handoff: finish/fsync result and directory; open read-only relative to the retained directory with no-follow protection; prove the original device/inode; close the writer and transfer read-only descriptor ownership into the still-active context. Writing/finalization is then permanently finished. Claim/directory handles, original identity, resource controller and deadline remain live for Slice 4's independent reopen/hash/parse/verify. The enclosing orchestration closes context after verification/sealing or failure; failed handoffs close all owned descriptors. No pathname recovery, seal or validation authorization is added by this handoff.

Provider failures already close descriptors; their reserved partial bytes are preserved without reopening to fabricate an INCOMPLETE suffix. Adapter/summary failures may finish valid INCOMPLETE JSON only at a proven append boundary with an active context and usable resources/storage. Partial writes, failed fsyncs and expired deadlines preserve bytes and close permanently. These rulings are design only; 3C is not implemented.

### Slice 3A accepted milestone

Exact code `71820d8b1d64a495d3a354a5114910c43a37514a` passed GitHub Ubuntu CI https://github.com/Sujayprodduturi/Icarus/actions/runs/36310199592: 1,484 passed, four pre-existing integration skips, 105.60s; Ruff lint/format and mypy (136 files) passed. Kernel/filesystem tests excluded on Windows executed on Linux. Together with independent review, root unit/static/fixture checks and 5/5 fault probes, this accepts the guarded generator only. F11 integration skips remain open. No completed-runner attestation, official calibration/validation draw, accepted floor or inference unlock exists. 3B is being implemented; 3C has only the reviewed design/ownership ruling above.
