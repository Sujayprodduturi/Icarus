# Windows simulator and verification — 2026-09-30

**Outcome:** the existing synthetic signal simulator works on the current Windows PC. The local simulator/statistics group passed 268 tests; the earlier safety group completed 301 passed with six platform skips. This is fixture behavior verification, not a strategy-performance evaluation or official calibration.

## Source and scope

All reported runs used source `cdf127b0ea32270056d34e2273f3fefc2929e34f`. The local environment reported Windows 11 build 26200 and Python 3.12.10. No production runner, estimator, manifest, goal, dependency or test code changed during this follow-up. Tracked changes are documentation only; the standing pre-commit code-review requirement is exempt for those changes, but independent document and evidence review was performed.

The operator confirmed no separate Linux system and requested simulator/other tests on the current PC. This agrees with D24's host choice and is recorded as D30. No OS migration, platform-guard bypass, reserved draw, broker access, real-data strategy evaluation, actual lockbox access or inference enablement occurred.

## Local execution

From `C:\ICARUS`, the existing toy fixture was run using a locally retained script:

```powershell
uv run python -m var.verification.2026-09-30.run_windows_simulator
```

The script uses `tests.unit.test_signal_simulator._case()`, creates a fresh six-session/three-symbol artificial panel on each run, emits a signal at the first bar for each symbol, repeats BBB at the second bar, and emits AAA again on the last bar. It calls the production `SignalSimulator.run()` with source indices 40..45. Assertions check signal reconciliation, next-bar entries, unavailable benchmark alpha and deterministic repeat output. The second output exactly matched the first. An independent reviewer reproduced both runs without overwriting the saved output.

Fixture SHA-256 (`tests/unit/test_portfolio_characterization.py`): `09e4bf6ffa600de64cffc71150e7dc532cd57d084c06cf51e6d9cbd2a0bfda2d`.

| Check | Observed result |
|---|---|
| Emitted signals | 5 |
| Completed trades | 2 |
| Explicit skips | 3: already open, entry not filled, no next bar |
| Decision / entry indices | 40 / 41 for both trades |
| Repeat execution | Identical |
| Benchmark return / pre-tax alpha | Unavailable for both trades |

Both artificial trades lost money. AAA filled 999 shares on INR 99,949.95 deployed capital, stopped out, and lost INR 15,306.96068239000 after INR 222.06068239000 of modelled costs, before tax. BBB partially filled 20 shares on INR 2,001.00 deployed capital and lost INR 21.78977400000 after INR 19.78977400000 of modelled costs, before tax. These numbers belong to the fabricated fixture and its fixture cost configuration; they say nothing about profitability on market data. No Sharpe, CAGR, portfolio drawdown, calibrated interval, benchmark alpha or promotion verdict was generated. The open F48 delivery-fee accounting finding is not closed by this check.

Local scratch files, deliberately git-ignored under `var/`:

- `var/verification/2026-09-30/run_windows_simulator.py`
- `var/verification/2026-09-30/windows-simulator-result.json`
- `var/verification/2026-09-30/windows-simulator-tests.log`
- `var/verification/2026-09-30/cdf127b-ci.log`
- `var/verification/2026-09-30/cdf127b-native/` (downloaded raw proof logs/reports)

These paths are retained on this PC; they are not files supplied by a fresh clone. The committed test fixtures provide the reproducible simulator behavior checks below.

## Local tests

```powershell
uv run pytest -q tests/unit/test_signal_simulator.py tests/unit/test_signaltest.py tests/unit/test_fills.py tests/unit/test_portfolio_characterization.py tests/unit/test_portfolio_exits.py tests/unit/test_portfolio_discards.py tests/unit/test_signalmetrics.py tests/unit/test_signalmetrics_oracle.py tests/unit/test_signalcalibration_task2.py --durations=8
```

**268 passed in 31.51 seconds**, no skips or failures. This covers simulator happy/refusal paths, every emitted signal accounted for, next-bar entry, resting target strict trade-through, pessimistic stop/target priority, partial fills/exits, explicit missingness, stale marks, synthetic portfolio characterization, discard reconciliation, statistical oracle comparisons and test-seed parity across both frozen phase topologies. The all-cell parity sweep took 29.00 seconds. The synthetic characterization is not the deliberately uncaptured production golden backtest.

The earlier local command, launched in the preceding continuation and collected as complete during this follow-up:

```powershell
uv run pytest -q tests/unit/test_signalcalibration_task3.py tests/unit/test_signalcalibration_envelope.py
```

**301 passed, six skipped in 1,618.21 seconds.** Skips cover one Windows symlink-creation privilege restriction and five tests requiring native Linux resource, secure evidence, completion, descriptor or validation-startup syscalls. Windows startup-refusal tests passed. These skips do not prove equivalent Windows durability or resource enforcement.

`uv run python -m scripts.signal_calibration preflight` passed on the clean committed source, without phase/RNG startup. `uv run ruff check .`, `uv run ruff format --check .` and `uv run mypy` passed (139 typed source files). Static checks also passed after the documentation corrections.

## Exact-source remote evidence, separately labelled

[Linux CI at cdf127b](https://github.com/Sujayprodduturi/Icarus/actions/runs/36680292873): 1,644 passed, four existing integration skips in 1,771.07 seconds; Ruff and mypy clean. [Native test-only resource proof at cdf127b](https://github.com/Sujayprodduturi/Icarus/actions/runs/36680292816): generated, scripted and validation-fallback modes completed successfully. The primary and independent reviewer downloaded all six raw log/report files independently; each final log JSON matched its structured report and no traceback/exception/error marker appeared. Both reproduced the production aggregate checker:

```powershell
uv run python -m scripts.check_signalcalibration_envelope --directory var/verification/2026-09-30/cdf127b-native --expected-commit cdf127b0ea32270056d34e2273f3fefc2929e34f
```

Result: `WITHIN_FROZEN_LIMITS`, `authority: NONE`, `official_streams_drawn: false`. Reports retained the exact 45 x 10,000 calibration and 37 x 20,000 validation topology, 2 GiB address-space limits, 7,200-second phase deadlines, distinct non-reserved test seeds, systemd/non-container/ext4 evidence and zero reserved draws/fsync/close failures. Maximum phase elapsed time was 3,063.55 seconds, peak RSS 143,364,096 bytes, sampled VMS 385,908,736 bytes, and verifier projection 578,052,096 bytes. The generated test calibration FAILED and stopped before validation; the scripted passing calibration exercised the same-process handoff. These outcomes do not predict the reserved experiment's outcomes.

## Remaining restriction

The official counted runner still refuses Windows before claim/RNG, as its reviewed contract requires. No eligible official Linux host exists; GitHub was test-only. No fresh canonical attestation was authored. The prior `81fc971`/`614fa7a` attestation does not cover later handover ancestry. Completed `cdf127b` results are evidence for that source only, not for a later documentation commit. A future official invocation requires finalized source/platform, appropriate exact-source proof, independent attestation and the separate one-shot operator decision. A Windows official-run design requires its own explanation/review; local simulator tests do not silently provide it.

Power-loss testing and existing integration skips remain open. Product inference, real-data evaluation and live order paths remain disabled/unbuilt as recorded in [STATE.md](../STATE.md).
