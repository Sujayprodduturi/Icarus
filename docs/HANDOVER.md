# Icarus handover — 2026-09-30

Read `AGENTS.md`, `OPERATOR.md`, [STATE.md](STATE.md) and this checklist. Current work is Phase 1, Task 3a: make the signal diagnostic trustworthy before evaluating strategy performance.

## Current operator direction

**Use the current Windows PC for the simulator and supported tests. There is no separate Linux system.** D24 already selected this PC; D30 records the 2026-09-30 clarification. No OS migration is approved. A Linux machine is not a prerequisite for the synthetic simulator, fixture tests, deterministic preflight, Ruff or mypy.

## What was verified

At exact source `cdf127b0ea32270056d34e2273f3fefc2929e34f`:

- **Windows:** the existing toy signal simulator ran twice identically. Five signals reconciled to two trades and three skips; both entries executed on the next bar. The simulator/fill/accounting/statistics group passed **268 tests** in 31.51 seconds. The counted-runner safety group completed **301 passed, six platform skips** in 1,618.21 seconds. Preflight, Ruff, formatting and strict mypy passed. See the [local evidence and commands](reviews/2026-09-30-windows-simulator-check.md).
- **GitHub Linux, test-only:** [CI](https://github.com/Sujayprodduturi/Icarus/actions/runs/36680292873) passed **1,644 tests, four existing skips**, Ruff and mypy. [All three native resource proof modes](https://github.com/Sujayprodduturi/Icarus/actions/runs/36680292816) passed the aggregate `WITHIN_FROZEN_LIMITS` check with the unchanged 2 GiB and 7,200-second per-phase limits. The primary and independent reviewer checked raw logs against reports and reproduced the exact-source aggregate verdict; reserved draws, fsync failures and close failures were all zero.
- These are simulator behavior and resource checks. They establish no strategy performance, accepted statistical floor, benchmark alpha or live readiness. `goal.yaml` still disables signal-test inference. No official calibration/validation stream or actual lockbox data was used.

The earlier `81fc971` whole-runner approval and `614fa7a` canonical attestation remain dated history. The successful `cdf127b` runs cover that exact source, not the documentation commit recording this follow-up. No renewed canonical attestation has been issued.

## Latest diagnostic and actual next task

The [non-reserved diagnosis](reviews/2026-09-30-test-calibration-failure-diagnosis.md), using unchanged production helpers at source `8086edb`, completed six selected calibration cells x 10,000 replicates on this PC. Cell 28 raw/win coverage was 7,910 / 10,000 and 7,871 / 10,000; every frozen floor requires this failing cell. Independent rare-win cell 1 also fails. All saved summaries and RNG boundary rows were independently checked. This is a diagnostic rejection witness, not a full 45-cell counted verdict or a reserved outcome.

**Latest completed work / next:** D32 authorized the isolated mathematics build and Windows comparison. The [build/result record](reviews/2026-09-30-signal-method-research-build.md) records exact source `7cbd372`, 48 profiles x1,024 replicates,92.00s parent wall time,397 initial regression tests and41 final research tests plus143-source static checks. The first attempt failed before drawing due to the Windows venv redirector; its evidence is retained, and a direct real-interpreter launch now preserves parent verification and timeout ownership. Candidate serial raw coverage improves802/1024 to913/1024, but rare-magnitude raw remains839/1024. Reject this development candidate; do not adopt it or enable inference. All288 count summaries/1440 rate bounds, protocol/source hashes and ledger were independently checked; individual outcome/width samples were not saved/replayed. The [all-profile CSV](reviews/2026-09-30-signal-method-screen.csv) retains the derived evidence. The [next bounded independent-group proposal](plans/2026-09-30-signal-bounded-uncertainty-design.md) is now concrete and independently numerically/governance reviewed: assumption-explicit Hoeffding research benchmark, precision planning and honest refusals, deterministic fixtures only. Both support-contract and numerical-degeneration findings were incorporated. Await operator review of this narrowed contract before implementation. It does not solve serial dependence, certify real-data independence or set a product data floor. No new stochastic attempt occurred in this design follow-up. No retuning against these exposed samples disguised as validation. Read the [current ranked audit](reviews/2026-09-30-signal-method-audit.md). The Windows official resource/durable-claim blockers remain separate. Both reserved streams, real data, lockbox and product config remain untouched. Follow OPERATOR section2 for the requested explanation style.

## Continue on this PC

1. Check `dev`, live `HEAD`, `origin/dev` and the worktree. Preserve user-owned untracked `AGENTS.md`. Check section 0 of [STATE.md](STATE.md), not older narrative milestones, for the current action.
2. Use the existing synthetic simulator and fixture/test APIs. The completed commands and locally retained logs/results are in the [Windows evidence record](reviews/2026-09-30-windows-simulator-check.md). Re-run checks when code changes or a new failure warrants it; do not repeat an unchanged suite merely because a new session began.
3. Keep outputs labelled synthetic and, for the signal simulator, net of cost before tax. Every emitted signal must have a completed trade or explicit skip. Benchmark alpha stays unavailable when the benchmark is missing. The simulator tests also cover missing-data refusals, touch-versus-fill, partial exits and stale marks.
4. Keep inference disabled. Synthetic fixtures do not substitute for the official statistical experiment or a real-data strategy test. Real-data evaluation remains behind the trial-ledger and source/lockbox guards; it is not authorized by the request to run local tests.

## Separate restriction: official one-shot calibration

The guarded counted runner currently supports **bare native Linux only**, with persistent ext4/xfs/btrfs evidence storage, secure no-follow file handling, real file/directory sync and the frozen resource limits. Windows refuses before claim/RNG. The GitHub job was a test-only proof host, not a designated official evidence host.

There is no such official host available. If the operator later asks to make the official experiment run on this PC, resolve the blockers in the reviewed investigation design, then present a concrete implementation plan and obtain the required platform decision. Do not substitute WSL, Docker, platform monkeypatching or relaxed limits for that design. Local simulator/testing work can continue now.

Before any later official attempt:

1. Finalize and verify the platform, persistent evidence location and intended source. Run fresh exact-source CI/native proof appropriate to the approved contract, independently inspect its raw evidence, and obtain an independently authored whole-runner review and canonical attestation.
2. Write final handover/status updates **before** that reviewed source commit. The attestation permits only its two review-file paths afterward; any other later commit, even documentation, requires renewal. Verify the production parser, commit-by-commit ancestry and protected blobs. Do not weaken this rule to avoid review churn.
3. Present the exact source, platform, evidence location and command scope for the separate explicit decision to consume calibration, including possible same-process held-back validation. A complete FAILED calibration consumes the phase and stops. Interruption can leave reserved bytes without permission to retry. A PASSED calibration can continue only through live same-process completion authority and fresh evidence verification.

## Later tasks and limitations

After valid, reviewed synthetic calibration and validation, Step 6b pins minimum data requirements. Trial-ledger, benchmark/source/cost review and real-data runner work remain later dependencies. No credible strategy performance result or date exists yet.

Six Windows platform skips, four existing Linux integration skips and the unperformed power-loss experiment remain disclosed. The synthetic portfolio characterization passes; the separate production golden backtest remains deliberately uncaptured. Historical failures and measured limits remain in the [native proof plan](plans/2026-09-28-step6a2-task3-native-envelope.md), [measured pass](reviews/2026-09-29-step6a2-task3-bounded-native-pass.md), [earlier whole-runner review](reviews/2026-09-29-step6a2-task3-whole-runner-review.md), and [execution ledger](reviews/2026-09-27-step6a2-task3-progress.md). A test-only statistical FAILED result is not a reserved-stream outcome.
