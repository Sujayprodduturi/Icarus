# Seven-Strategy Daily Pilot Implementation Plan

## Execution checkpoint — 2026-10-16

The offline runner, tracked inventory, guarded actual CLI, descriptive-pilot ledger geometry, migration, and focused unit/integration coverage are implemented. The final test pass exercises the seven-card invented command, complete-set reservation barrier, delayed decode, exact 693 labels and 257 sessions, evidence-bound actual admission, stale authorization, panel-byte binding, output failure, and the SQL downgrade paths. Actual collection, source qualification, authorization, price decoding, trial reservation, and report publication remain held; provider questions remain UNSENT. The invented proof is mechanics-only and cannot admit real data or performance claims.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Every runtime change follows a witnessed RED → minimal GREEN cycle.

**Goal:** Build an invented-data-capable, fail-closed runner for exactly seven daily `SignalSimulator` evaluations over the fixed 2022-12-26–30 pilot, while preserving the 257-session warm-up source and every one of the 693 requested labels.

**Architecture:** Reuse the exact seven-card loader, DSL compiler, `SignalSimulator.run`, cost/fill models, run-authorization bindings, and existing counted Postgres ledger barrier. Applicability and all hash/qualification/source-use checks complete before ledger access; all seven trials reserve before the injected price decoder runs. Columns are computed on 257 sessions, then the simulator receives only the five pilot rows and source indices 252–256, so warm-up signals cannot create positions. Invented proof uses an in-memory fixture and never touches the actual ledger.

**Tech Stack:** Python 3.12, dataclasses, NumPy, existing Icarus DSL/simulator/ledger types, pytest, Ruff, mypy.

**Spec:** `docs/plans/2026-10-16-daily-descriptive-pilot.md`; the safe frozen inventory metadata is shipped as `config/daily_pilot_inventory.json` so the invented proof works from a clean checkout.

## Reviewed ledger shape

The native ledger schema currently rejects a single signal evaluation: `TrialBatchReservation._validate_geometry()` requires every ordinary signal batch to contain `SIGNAL_FULL` plus at least one `SIGNAL_FOLD`. Inventing a fold, recording the pilot as `PORTFOLIO`, or creating a second ledger would falsify the fixed seven-evaluation contract. The root brief authorizes the narrow repair: add `TrialKind.DESCRIPTIVE_PILOT`, represented by exactly one ordinal-zero evaluation with reset identity `daily_descriptive_pilot_v1`. It remains an `EvaluationPlan(mode="signal", capital=None)`; that mode admits either this exact singleton or the unchanged native `SIGNAL_FULL` plus folds shape. Existing portfolio geometry remains unchanged.

`GuardedTimedRunner` remains the reservation barrier. It writes seven per-card transactions sequentially, fails/counts earlier reservations if a later reservation fails, and invokes the shared decoder only after all seven succeed. This is complete-set-before-decode behavior, not a single database transaction spanning seven cards.

## Files and interfaces

- Create `icarus/engine/daily_pilot.py`: strict inventory/admission parsing; `DailyPilotPayload`; exactly seven plans; applicability preflight; five-session evaluator; result serializer with `benchmark_return=None`, `pre_tax_alpha=None`, `promotion_eligible=False`, and separate executed-exit versus final marked-value fields.
- Create `tools/run_daily_pilot.py`: metadata-only default; `--invented-proof` standalone path; actual path requires external qualification, authorization, activated-ledger DSN, pinned panel path and write-once output. No price loader is imported/called until all seven reservations succeed.
- Create `tests/unit/test_daily_pilot.py`: invented all-seven proof, exact catalogue/inventory hashes, 693-label accounting including `LIQUIDBEES`, applicability-before-ledger, complete-set reservation-before-decode, pilot-only signal suppression, no Jan-2023 bar, null benchmark/alpha, failure terminalization and write-once output.
- Create `var/verification/2026-10-16/daily-pilot/`: RED/GREEN logs, standalone invented report, static-check logs and final SHA-256 manifest.
- Modify `icarus/state/trial_ledger.py`: add the single `DESCRIPTIVE_PILOT` kind and exact one-item/reset geometry without relaxing existing signal or portfolio batches.
- Modify `icarus/state/models.py` and add one Alembic migration under `icarus/state/migrations/versions/`: admit the new persisted kind and narrowly extend the database triggers that enforce batch cardinality, evaluation inserts and result consistency; downgrade restores the prior checks. Migration execution is limited to a new disposable test database supplied by the root.
- Modify `icarus/engine/timed_runner.py`: allow `mode="signal"` to contain either the exact descriptive singleton or the unchanged full-plus-fold shape. Capital remains `None`; reservation, authorization, hash and terminalization behavior stays unchanged.
- Extend `tests/unit/test_trial_ledger.py`, `tests/unit/test_timed_runner.py`, and `tests/integration/test_trial_ledger_postgres.py` with focused geometry, guard and persistence tests. Create `tests/unit/test_daily_pilot.py` for the runner contract.

## Finite acceptance

1. Exact seven frozen cards and hashes; any missing/extra/reordered/benchmark-dependent card aborts before ledger or decode.
2. Exact 257-session axis `2021-12-21..2022-12-30`; decisions are only the final five sessions; 2022-12-30 cannot open a position on a 2023 bar.
3. Exactly 693 requested labels remain accounted for on every pilot date; `LIQUIDBEES` is explicitly `CLASS_INELIGIBLE_FIXED_INCOME`; no hidden subset runs.
4. Actual mode requires qualified calendar/actions/PIT/source-use/full-manifest evidence and external active authorization before ledger access; incomplete applicability creates zero trials and performs zero price decode.
5. Seven native descriptive-pilot reservations complete sequentially before one shared decode. A partial reservation failure fails/counts earlier reservations, calls zero price decoders and publishes no report. Decode/evaluation failures terminalize every applicable reservation. An atomic report-publication failure releases no report and does not rewrite already-completed immutable ledger terminals.
6. Exactly seven `SignalSimulator.run` calls and zero `PortfolioSimulator.run` calls. Reported P&L is modeled net of charges before account capital-gains tax; executed exits and final `STALE_MARK` estimates are distinct.
7. Output states daily modeled execution, `NIFTY=None`, benchmark return/alpha unavailable, inference unavailable and promotion false.
8. Standalone invented command exits zero and emits all seven card names plus the required unavailable labels without network, credentials, Postgres or market-data reads.

## TDD order and mutation predictions

1. RED strict metadata/applicability tests; GREEN parser/preflight only.
2. RED pilot-slice tests proving a warm-up signal cannot enter and terminal-day signal cannot reach 2023; GREEN evaluator using full-column computation followed by a five-row slice.
3. RED exact-one `DESCRIPTIVE_PILOT` reservation, ORM/SQL constraints and guarded signal-plan tests; GREEN the narrow ledger/model/migration/guard geometry.
4. RED integrated event-order and failure tests; GREEN actual runner and write-once report.
5. RED standalone seven-card invented proof; GREEN CLI proof path.

Post-build faults must be killed individually: relax the new one-item/reset ledger geometry; omit the persisted-kind constraint; omit one card/hash check; admit 692 labels; reserve after decode; permit a warm-up entry; append a 2023 next bar; call `PortfolioSimulator`; populate benchmark/alpha; merge marked values into executed exits; publish after terminal failure. Every mutation must restore exact source bytes before the next case.

## Held actual work

This plan authorizes invented-fixture software only. `DATA_QUALIFIED=false`, actual-study `RUN_AUTHORIZED=false`, source-use disposition unresolved, provider questions UNSENT, and no actual price decode, trial reservation, download, broker SDK, strategy result or ledger write is permitted by this build.
