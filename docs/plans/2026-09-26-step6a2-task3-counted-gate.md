# Step 6a.2 Task 3 — counted calibration and validation gate

> **For agentic workers:** implement test-first in the slices below. Stop after each independently reviewable slice.

**Status:** clarified implementation plan approved by independent Astra Medium review on 2026-09-27; see the dated approval addendum in `docs/reviews/2026-09-27-step6a2-task3-rereview.md`. No frozen calibration or validation stream has been drawn. This refines Task 3 of [the approved parent plan](2026-09-26-step6a2-calibration-implementation.md) and is governed by the exact [Task 3 contracts](2026-09-27-step6a2-task3-contracts.md). No product inference, real-data evaluation or frozen-stream draw is authorized.

**Goal:** produce one counted, complete and auditable synthetic calibration result and, only after exact byte verification of a passing calibration claim/result/seal trio, one held-back validation result.

**Architecture:** keep all counted implementation in the manifest-protected `scripts/signal_calibration.py`. Build a pure strict result validator first, then provenance and durable I/O without RNG, then counted orchestration, then the calibration-to-validation unlock. Tests use only scripted outcomes, sentinels and the separate fixture seed.

**Tech stack:** Python 3.12, NumPy 2.1.3, SciPy 1.14.1, psutil 6.1.1, pytest, Ruff and mypy.

## Frozen constraints

- Do not edit the frozen manifest, digest, seeds, cells, thresholds, estimator, family sizes, stream mapping, 256-replicate chunks or first-passing rule.
- `goal.yaml signal_test.inference_enabled` remains false. No market data, lockbox, broker, trial-ledger evaluation, promotion or live order path is used.
- Calibration has 10,000 replicates per cell and family size 675; validation has 20,000 and 555. Every generated replicate, refusal and parity trigger is counted once.
- A complete statistical failure is an immutable result. An incomplete/resource/provenance failure is an immutable failed attempt. There is no retry, resume, replacement, next-floor search or scripted override.
- The first counted calibration invocation remains a hold point after implementation, fresh tests and independent review of the exact commit.

## File map

- Modify: `scripts/signal_calibration.py` — pure evidence validator, provenance, Linux safety I/O, private counted provider and CLI.
- Create: `tests/unit/test_signalcalibration_task3.py` — strict schemas, event accounting, ancestry, durability, resource and orchestration refusals.
- Read only: frozen manifest/digest and `icarus/engine/signalmetrics.py`.
- Reviewer creates later: exact Markdown review record plus `docs/reviews/step6a2/<manifest-sha>/task3.review.json`.

No new project-owned module may be imported by the harness. The review-attestation ancestry check freezes all tracked transitive imports without changing the manifest's protected-path set.

### Task 1: Pure evidence and accounting core

**Produces:** `validate_phase_result(manifest, result, expected_provenance) -> VerifiedPhaseResult`; no file I/O, context, CLI or RNG.

- [ ] Write failing tests for every result/claim/seal/attestation missing or extra key, duplicate JSON key, trailing bytes, noncanonical encoding and illegal scalar type.
- [ ] Write failing tests for overlapping, omitted, duplicated and foreign event IDs; incomplete chunks/cells/metrics; false aggregate counts; tampered CP bounds; incomplete parity; non-first floor; and validation floor search.
- [ ] Implement the minimum strict parser and pure recomputation required by the contract. Reuse the existing CP functions, but derive every count and verdict from event partitions rather than trusting the current selection-summary aggregates.
- [ ] Run the focused tests, Ruff and mypy. Review this slice before any context or counted RNG exists.

### Task 2: Provenance, exclusive evidence and platform safety

**Consumes:** the pure validator. **Produces:** a private closed-by-default phase context bound to one exclusive claim/result handle.

- [ ] Write failing tests for invalid review attestation, non-ancestor or merge ancestry, an intervening non-review path, change-then-revert, dirty tracked/untracked paths, reservation collision and wrong/closed phase.
- [ ] Write failure-injection tests for unsupported platform/filesystem, RLIMIT installation/readback, allocation projection, deadline, file/directory fsync, truncated pre-existing artifact, symlink/hard-link/device-inode swap and disk-full writes.
- [ ] Implement Linux-only counted mode exactly as the contract specifies: RLIMIT_AS=2 GiB, separately measured peak RSS, one two-hour monotonic deadline, retained no-follow directory handles, exclusive mode-0600 files and file-plus-directory fsync.
- [ ] Refuse native Windows and every unproved platform before claim, context, cache lookup or RNG. Deterministic preflight and fixture tests remain available there.
- [ ] Permit only the exact current phase paths; for validation additionally permit only the already-verified calibration claim/result/seal trio. Never allow a directory prefix or glob.

### Task 3: Counted generation and immutable result

**Consumes:** authenticated context and existing frozen DGP/evaluator. **Produces:** one unverified or incomplete result at the derived path.

- [ ] Write failing sentinel-provider tests proving reserved phase seeds are unreachable without the active private context and that calibration context cannot draw validation.
- [ ] Process cells in manifest order and chunks of 256 plus the declared remainder. Preserve component stream shapes/order and use the frozen seed derivation internally; never route a frozen seed through a public fixture API.
- [ ] Emit compact chunk event partitions and all fixed/boundary parity records under the exact result schema. Check planned arrays and projected verifier memory before allocation/write; the OS limit and deadline remain active through verification.
- [ ] Close/fsync the result as `UNVERIFIED` or `INCOMPLETE`. Never write `COMPLETE` into result bytes.

### Task 4: Independent verification, seal and validation unlock

- [ ] Reopen the result relative to the retained directory handle, reject non-regular/replaced identities, read/hash those same bytes once, strictly parse, and call the pure validator.
- [ ] Create the exclusive completion seal only for a fully verified complete pass or complete statistical failure. The seal digest binds the exact claim and result bytes.
- [ ] For `validate <calibration-result-path>`, require the argument to equal the result derived from the verified calibration claim. Recompute the full calibration result; unlock only a sealed `PASSED` result with its first-passing floor.
- [ ] Validation tests that one floor once. A complete failure, incomplete evidence, changed target/code, unrelated SHA, omitted cell, duplicate ID, file-identity change or validation observation prevents any alternate draw.

## Verification and hold point

Run `uv run pytest tests/unit/test_signalcalibration_task3.py -q`, then all unit tests, portfolio characterization, Ruff check/format, mypy and `git diff --check`. Failure-path tests must prove refusal occurs before claim/RNG where specified and that post-claim failures never create a seal.

Commit and independently review the exact runner, review attestation, protected blobs, ancestry checks and resource/durability refusals. Record the verdict. Until that review explicitly approves the first counted calibration invocation, leave inference disabled and do not draw either frozen phase stream.
