# Seven-strategy daily pilot runner

This runner checks whether the seven fixed strategy cards can work through a small, consistently accounted daily simulation. The invented-price proof is available; actual-market-data use remains held for source qualification, source-use disposition and separate run authorization. Provider questions remain **UNSENT**.

## What it does

- Reads 257 source sessions, from 2021-12-21 through 2022-12-30. The first 252 sessions prepare indicators; they cannot open positions.
- Makes decisions only on 2022-12-26–30. A decision waits for a later bar to execute; the final day's new intent has no next bar. No January 2023 data is appended.
- Runs exactly seven `SignalSimulator` evaluations, with no portfolio evaluations: buy-and-hold control, low volatility, Donchian breakout, sweep/reclaim, uptrend pullback, short momentum and longer momentum. The control is not a separate discovery of a profitable strategy.
- Accounts for all 693 requested stock labels on each decision date, including exclusions and missing histories. `LIQUIDBEES` stays counted as fixed-income-ineligible; there is no blanket ETF exclusion.
- Reports modeled daily execution. A price touching a limit does not guarantee a fill; daily bars cannot establish exact intraday execution times.

Amounts are modeled net of transaction charges **before account capital-gains tax**. Executed exits and terminal `STALE_MARK` estimates are separate: a final estimated value is not an executed sale. Nifty/benchmark return and alpha are unavailable (`null`), inference is unavailable, and promotion is false. Five decision days cannot establish that a strategy is good or profitable.

## Commands available now

Run from PowerShell in `C:\ICARUS` using the existing environment:

```powershell
Set-Location C:\ICARUS
.venv\Scripts\python.exe -m tools.run_daily_pilot
```

The default command prints the held actual-run status. It does not decode market prices or use the trial ledger.

```powershell
.venv\Scripts\python.exe -m tools.run_daily_pilot --invented-proof var/daily-pilot-invented-example.json
```

The proof runs all seven cards on deterministic invented prices and writes one JSON report, without broker credentials, network calls or PostgreSQL. Choose a new output filename each time: existing output is never overwritten. This output is software evidence, not market-performance evidence.

Focused software checks:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_daily_pilot.py tests/unit/test_trial_ledger.py tests/unit/test_timed_runner.py -q
```

PostgreSQL integration tests additionally require an explicitly supplied disposable test DSN; never point them at the operator's ledger.

## Inputs required before actual mode

The actual CLI requires `--actual`, `--qualification PATH`, `--authorization PATH`, `--panel PATH`, `--activated-ledger-dsn DSN` and `--output PATH`. Optional `--source-inventory PATH` and `--requested-labels PATH` default to the reviewed local control documents. Those controls must match their pinned hashes. Supplying flags or editing a JSON boolean does not establish permission or qualify a source.

`load_actual_admission()` requires exactly these qualification JSON fields, with no extra keys. The following is a **schema illustration**, not an accepted qualification document; placeholders must come from independently reviewed evidence:

```json
{
  "schema_version": 1,
  "status": "QUALIFIED_FOR_DAILY_DESCRIPTIVE_PILOT",
  "data_qualified": true,
  "source_use_authorized": true,
  "calendar_qualified": true,
  "actions_qualified": true,
  "point_in_time_qualified": true,
  "source_inventory_sha256": "<reviewed source inventory hash>",
  "requested_labels_sha256": "<reviewed original label-file hash>",
  "calendar_sha256": "<reviewed calendar hash>",
  "panel_sha256": "<qualified decoded-panel hash>",
  "panel_file_sha256": "<qualified panel-file hash>",
  "goal_sha256": "<current goal.yaml hash>",
  "cards_sha256": "<fixed seven-card catalogue digest>",
  "label_dispositions": ["<693 objects, described below>"]
}
```

Each disposition is an object with `label` and `pilot_statuses`, in the original 693-label order. `pilot_statuses` contains five strings, one per decision day: `ELIGIBLE`, `BELOW_CLOSE`, `BELOW_TURNOVER`, `MISSING_WINDOW` or `CLASS_INELIGIBLE_FIXED_INCOME`. `LIQUIDBEES` requires the last status on all five days. Calendar, corporate actions, dated stock identities, source use, prices and missing-window decisions must be supported by the qualification review.

The separate authorization JSON requires exactly `schema_version: 1`, `authorization_id`, UTC `issued_at`/`expires_at`, `actual_ledger_activated: true`, `invented: false`, and these seven lowercase SHA-256 bindings: `bundle_sha256`, `approval_sha256`, `policy_sha256`, `qualification_sha256`, `goal_sha256`, `cards_sha256`, `runner_sha256`. It must be current and externally authorized. The bundle binds the qualified panel file; qualification, goal, cards and runner bind the reviewed artifacts. Changes to relevant code or dependencies invalidate the runner binding.

Actual mode completes applicability checks before ledger access, then reserves seven native descriptive-pilot trials before decoding prices. Reservations are sequential transactions, not one transaction across seven cards. An interrupted reservation set remains counted and fails closed. Completed terminal records remain immutable if later report publication fails; no partial operator report is published. Ledger activation/migration is a separate approved operation, not something this command silently performs.

## Evidence and remaining work

**Software COMPLETE at source `e33cbcb45a7dc95765d404f82decad75b454006a`; independent reviewers give GO with no unresolved software finding.** Root verified **334 distinct targeted tests**: 70 ledger, 132 engine regressions, 69 simulator characterization, 44 compatibility and 19 pilot cases. Fresh restored-source static checks pass strict mypy for 198 source files, global Ruff lint and formatting for 479 files; receipt `var/verification/2026-10-16/daily-pilot-root-restored-static.txt`. The four related test receipts are `var/verification/2026-10-16/daily-pilot-root-ledger.txt`, `daily-pilot-root-engine.txt`, `daily-pilot-root-simcore.txt` and `daily-pilot-root-compat.txt`.

An extracted clean committed checkout without local `var` artifacts also passed all 19 pilot tests and the all-seven invented CLI proof. All 11 postcommit faults were caught; all 212 protected files were restored exactly and a fresh 19-test pilot run passed. See the [verification receipt](../reviews/2026-10-16-daily-pilot-verification.md) for evidence paths and hashes. Source-head hosted CI `38894139184` and resource run `38894139181` were still in progress at the last read; their PASS is not claimed.

Next: qualify and bind actual daily inputs and resolve source-use evidence before obtaining a separate actual-run authorization. Actual data admission and execution remain held. No actual market prices were evaluated, no actual trial ledger was activated or written, no provider was contacted, and no real-money or 2023+ lockbox run was performed by this build. Provider questions remain **UNSENT**.
