# Step 6a.2 Task 3 — guarded generation review

**Status: ACCEPTED on 2026-09-27.** Scope is Slice 3A only: shared synthetic equations and the private sequential counted provider. This is not approval to run calibration or validation, and is not a completed-runner attestation.

## Design and review

Astra Medium reviewed the design; Sol Medium is the sole implementation writer; root independently checks the diff and verification. Review order is simplicity, then correctness/security. Simplicity review found no justified removal from the shared core or local provider.

The provider must authenticate its issued context and complete frozen manifest, derive phase/cell/chunk/component addresses internally, reserve one traversal per context, preserve all component shapes/order and equations, release chunk caches, and stop permanently on failure. The public fixture API keeps its separate test seed. No caller can supply a counted seed, floor or cell subset.

## Findings required before acceptance

- Prevent a second provider from replaying a claimed attempt, including after exhaustion.
- Refuse direct component access outside active generation; unexpected StopIteration must fail permanently rather than allow retry.
- Derive exact component sizes before RNG/allocation; positive size alone does not establish the planned memory bound.
- Prove row isolation by actually mutating a returned row, not only comparing unchanged rows.
- Trace counted component order and shapes across all scenario families, including final remainders, with reserved-seed constructor sentinels.

## Independent baseline

Root loaded the previous committed harness from `5250d0f` and generated 328 fixture vectors: all 82 cell definitions at replicates 0, 255, 256 and the final replicate. Only the separate fixture seed was used. Sorted compact dataclass JSON concatenation SHA256: `170e35d2898b98db2b4152e0a2b6fb3b7674438b28a33dc4fd6b3334d3b64cc6`.

The working shared-core extraction reproduced all 328 vectors exactly. Final frozen-code checks, independent approval and CI results will be recorded below. The frozen manifest, detached digest, production estimator and disabled inference setting must remain unchanged.

## Frozen-code review

Astra Medium independently **APPROVED Slice 3A code**, subject to fresh checks on these exact bytes. All findings above were repaired and witnessed by targeted tests. No further simplicity or correctness blocker was reported. This approval does not cover the later event adapter, streaming result writer, sealing, validation unlock or first reserved draw.

- Harness SHA256: `d4bce154df39bec268e6fa4799a23b17475fb31a1c2e4bc33c0525d5fa93df32`.
- Test SHA256: `7a5d11c3ed78a97e63bbd5c35da37ce1c4c0b5490ed58c6d57357803ca7849e5`.
- Builder: Task 2 38 passed (29.64s); Task 3 171 passed, three Windows skips (77.27s); Ruff and explicit two-file mypy clean.
- Root independently matched hashes, reproduced all 328 original fixture vectors, and passed global Ruff lint/format (181 files), project mypy (136 files), explicit two-file mypy and whitespace checks. Normal and ignore-CR numstats agree.
- Root full unit suite, post-commit fault probes and GitHub Linux CI remain pending at this entry.

Test safety: an autouse guard rejects accidental reserved-seed construction. Counted-address spies substitute the separate fixture seed before invoking a real constructor, or return scripted arrays. No production context/evidence claim or actual reserved calibration/validation stream was used.

Root full-unit verification on the frozen code passed: **1,481 passed, three skipped, 148.98 seconds**. The skips are the existing Windows exclusions for Linux/syscall behavior. Root reconfirmed all three protected frozen-file hashes and `inference_enabled: false`. Post-commit probes and Linux CI are still required before final acceptance.

Code committed and pushed as `71820d8b1d64a495d3a354a5114910c43a37514a`. Root compared committed Git blob bytes to reviewed working bytes; both matched exactly. Five post-commit in-memory fault probes caught removal of single-provider ownership, exact component width, row copying, active generation window and unexpected-StopIteration conversion. **5/5 caught; tracked source unchanged.** No real reserved stream was used by these probes. GitHub Linux CI is pending.

## Final acceptance

Exact code `71820d8b1d64a495d3a354a5114910c43a37514a` passed [GitHub Ubuntu CI](https://github.com/Sujayprodduturi/Icarus/actions/runs/36310199592): **1,484 passed, four skipped, 105.60 seconds**; Ruff lint/format and mypy (136 files) passed. The Windows-skipped kernel/filesystem tests ran on Linux. Four pre-existing integration skips remain the separately open F11 finding; this is not proof of passing database integration behavior.

Slice 3A is accepted. Statistical event/parity recording (3B), durable result orchestration (3C), and independent sealing/validation unlock (Slice 4) remain outside this acceptance. Whole-runner approval and both reserved streams remain withheld.
