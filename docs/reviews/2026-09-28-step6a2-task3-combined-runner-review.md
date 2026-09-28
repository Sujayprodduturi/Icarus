# Step 6a.2 Task 3 Slice 4E — combined counted runner review

**Status: Slice 4E ACCEPTED (2026-09-28).** Code `9f7360c37c88181f81af7481643e8f935994ee59` is pushed to `dev`. This slice adds the same-process `run-counted` command. It does not authorize the first official synthetic draw, product inference, real-data evaluation, broker access or live trading.

## What changed

The command refuses non-Linux platforms before reading the manifest or creating evidence. On Linux it starts the calibration deadline, checks the frozen manifest and deterministic preflight, then enters the existing reviewed Git, filesystem and resource guards. It writes and independently completes calibration. A complete statistical `FAILED` result ends the run; a `PASSED` result hands the live completion directly to validation, which rechecks calibration evidence and writes/completes one held-back result at the bound floor. Writer or completion exceptions never trigger another phase. The command prints a final JSON report only after owned contexts close successfully. Complete statistical failure exits zero; operational failure exits one; invalid arguments use argparse exit two. The report contains derived artifact paths and verdicts, not an accepted product threshold.

Source: `scripts/signal_calibration.py`; new command tests: `tests/unit/test_signalcalibration_runner.py`; integrated Task 3 test: `tests/unit/test_signalcalibration_task3.py`. No manifest, seed, floor, threshold, estimator, inference setting, risk limit or broker code changed.

## Review and evidence

Independent Astra Medium read-only review found no production bypass. It requested proof of the full `PASSED`/`PASSED` path, validation failure cleanup, and one provider per entered phase through the actual runner. Those tests were added. Its final re-review found the gap closed and no remaining P1/P2 finding. The integrated test uses authentic fixture context and manifest, the real writer/completion/validation startup, and scripted chunks; it traps reserved RNG construction and asserts exactly one provider per phase.

A separate whole-runner read-only review of exact code commit `9f7360c` found no P1/P2 statistical or safety bypass in the inspected paths. It confirmed protected worktree bytes and frozen manifest hash matched the commit, and traced writer recomputation, independent verification, process-local completion authority and validation's bound-floor recheck. This is not an approval to draw. The reviewer identified the passing Linux CI result, final handover commit identity, independent attestation and native full-size resource proof as remaining hold points. The [resource-proof specification](../plans/2026-09-28-step6a2-task3-native-envelope.md) records the non-reserved surrogate requirements; it has not been executed.

- Final Windows unit suite: **1,612 passed, six platform skips** in 783.93s. Focused combined runner: 17 passed. Focused scripted real-writer handoff: one passed. A real Windows CLI smoke test refused immediately with `counted phases require native Linux`.
- Repository-wide Ruff lint and format, strict mypy on 138 source files, and staged `git diff --check` passed.
- Exact code commit: `9f7360c37c88181f81af7481643e8f935994ee59`; [Ubuntu CI](https://github.com/Sujayprodduturi/Icarus/actions/runs/36448420283) passed 1,618 tests/four existing integration skips in 760.87s, with Ruff lint/format and strict mypy clean. It was not a full-size native resource proof.

## Remaining boundary

No whole-runner exact-commit review attestation or full-size native Linux serialization/resource envelope exists. The first official calibration draw therefore remains locked. CI unit tests exercise native Linux components but do not prove the unchanged 2 GiB/two-hour full-run envelope. Both reserved synthetic streams remain untouched; `signal_test.inference_enabled` remains false. The four existing integration skips remain open.
