# Step 6a.2 Task 3 Slice 4D — validation generation review

**Status: ACCEPTED (2026-09-28).** Code `11241b8a4d0598ff3e34542985bfc0dd25866fbb` is pushed to `dev`. This review covers private held-back validation generation and durable result writing. It does not authorize the combined counted command, either reserved-stream draw, product inference, real-data evaluation, broker access or live trading.

## What changed

A live validation context created by the accepted calibration handoff can now issue its guarded counted provider and stream a complete validation result. The writer applies only the floor bound by the independently verified calibration result; a failed validation check records a complete statistical `FAILED` verdict without searching another floor. Its result remains `UNVERIFIED` until the existing independent saved-file verifier and completion path run. Original 20,000-replicate validation geometry, 256-replicate chunks, seed derivation, two-hour deadline and 2 GiB ceiling remain unchanged.

The source is `scripts/signal_calibration.py`; focused tests are in `tests/unit/test_signalcalibration_task3.py`; the bounded plan is `docs/plans/2026-09-28-step6a2-task3-validation-generation.md`. No frozen manifest, digest, estimator, threshold, family size or inference setting changed.

## Review and evidence

An independent Astra Medium source review found one P2 test gap: the real provider had not been exercised with an authentic live validation handoff. Tests now provide reviewed-manifest bytes, use the real provider against the live context and trap reserved RNG construction. They cover duplicate provider/writer use, changed completion lineage, changed claim, changed result identity, expired validation deadline and resource overage. The reviewer re-read the amended diff and found the P2 closed with no remaining actionable P1/P2. This was read-only source review, not an official experiment.

- Final Windows unit suite: **1,594 passed, six platform skips** in 725.89s. Focused live-provider bridge: six passed; focused validation writer: two passed; complete Task 3 suite before the final review-driven test additions: 279 passed, six skips. The final full unit suite includes those additions.
- Project-wide Ruff lint/format, mypy on 136 files, explicit script/test mypy and `git diff --check` passed. Ordinary and CRLF-insensitive changed-line counts matched exactly.
- Exact committed Git blobs match the working files. Source SHA-256: `7e1187ee16085b33f403a67c75017d4c7464e9d135004305982db64ffe9d0e60`; test SHA-256: `e6823c5fa81d887ba0378e709a12b7ccb4794d8c6fcd1ef12b77ee2bfbe8be74`.
- [Exact-commit Ubuntu CI](https://github.com/Sujayprodduturi/Icarus/actions/runs/36439913965): **1,600 passed, four existing integration skips** in 703.73s; Ruff, format and strict mypy passed. The job uses an Ubuntu runner with Postgres and Valkey service containers; its existing tests do not certify the later full-size native resource envelope.

## Remaining boundary

The combined CLI has not been implemented; no review attestation for the whole runner or native Linux serialization/resource envelope exists. The four existing integration skips remain open. A complete official calibration run remains forbidden until exact-commit whole-runner review and a separate native resource proof approve it. The next bounded draft is `docs/plans/2026-09-28-step6a2-task3-combined-counted-runner.md`.
