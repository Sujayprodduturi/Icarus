# Atomic Counted Trial Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development and superpowers:verification-before-completion. Implement the tasks in order. Do not run a real panel, read or rewrite `var/trial_ledger.json`, execute an Alembic migration against the operator database, or start Step 8.

**Goal:** Make every real-data portfolio or signal evaluation a durable lifetime trial before evaluation starts, while committing the signal run's full-span row plus all fold-matched rows as one result batch.

**Architecture:** PostgreSQL becomes the sole authoritative lifetime count after an explicit, separately executed import-and-activation transaction. An immutable reservation transaction inserts the run group and all evaluations before strategy evaluation; a second transaction inserts every result plus one terminal row before any metric-bearing output is released. Caller-supplied run-group UUIDs distinguish an idempotent persistence retry from a new evaluation attempt.

**Tech Stack:** Python 3.12, SQLAlchemy 2.0 Core/ORM, PostgreSQL, Alembic, psycopg, pytest, Ruff, strict mypy.

**Spec:** `docs/plans/2026-08-22-signal-test.md` lines 190-197 and 271-292; `docs/plans/2026-09-26-signal-statistics-design.md` lines 47-49 and 63-73; `AGENTS.md` invariants 18, 22, 24-26.

## Global Constraints

- This plan is the operator-authorized isolated Step 7 infrastructure amendment. It does not claim Step 6b adoption, close M4, approve a statistical method, or authorize Step 8 or real-data evaluation.
- `goal.yaml` remains unchanged with `signal_test.inference_enabled: false`; F48 delivery-fee accounting, source/time eligibility, benchmark matching, Task 3a, and the lockbox remain open.
- Count a reservation, including a HUMAN/operator-authored run, retune, same-strategy rerun, failed run, and process crash after reservation. A rerun receives a fresh `run_group_id` even when every input hash is identical.
- Retrying an uncertain persistence operation must reuse the same caller-supplied `run_group_id`. Same ID plus byte-identical canonical reservation/result returns a recovery-only receipt; it never authorizes evaluation again. Same ID plus different content raises `TrialIdentityConflict`. Any evaluation rerun uses a fresh UUID and is counted again.
- For a signal batch with `N` folds, reserve and later complete exactly `N+1` rows: ordinal 0 is `SIGNAL_FULL`; ordinals 1..N are the ordered `SIGNAL_FOLD` evaluations. Do not merge, deduplicate, or exempt reruns.
- Reservation commit is the pre-start barrier. Datastore unavailable, inactive ledger, corrupt legacy input, identity conflict, or cardinality mismatch must stop before `evaluate_once`, `SignalSimulator.run`, metric-bearing logs/stdout, or artifacts.
- PostgreSQL transactions provide committed-process-crash and concurrent-writer safety. Do not claim protection against storage hardware/OS power-loss beyond PostgreSQL's configured durability.
- Preserve `var/trial_ledger.json` byte-for-byte. Implementation and tests use only temporary synthetic legacy ledgers and an isolated throwaway Postgres database. Actual import/activation is a later explicit operator action.
- The canonical lifetime count is `COUNT(*) FROM trial_evaluations`, including reserved, completed, failed, and abandoned rows. Effective correlated-trial estimation, DSR/PBO, search caps, and promotion policy remain separate tasks.
- One disposable isolated PostgreSQL 16 test container may be started from the already cached `postgres:16` image if no isolated service exists. It contains synthetic rows only, is never the operator database, and requires no pull. No study/data-plane container, new sampled experiment, official stream, broker adapter, lockbox access, raw-data cleanup, or inference-flag edit belongs to this plan.
- Do not commit or push; the parent integrates after independent review.

## File Map

- Create `icarus/state/trial_ledger.py`: frozen typed contracts, canonical hashing, legacy-v1 validation, PostgreSQL reservation/completion/failure/import service, and typed failures.
- Modify `icarus/state/models.py`: ORM declarations only for the five trial-ledger tables, using unconstrained exact PostgreSQL `NUMERIC` for nullable Sharpe values.
- Create `icarus/state/migrations/versions/20261008_atomic_trial_ledger.py`: tables, checks, indexes, append-only triggers, deferred reservation-cardinality trigger, and terminal/result guards.
- Create `tests/unit/test_trial_ledger.py`: pure contract, canonical fingerprint, validation, and fail-before-evaluation tests.
- Create `tests/integration/test_trial_ledger.py`: real PostgreSQL transaction, concurrency, crash, trigger, import, and idempotency tests using unique UUIDs and no cleanup dependency.
- Create `scripts/migrate_trial_ledger.py`: explicit `--check` or `--apply` legacy import/activation command; `--check` performs no write and `--apply` is never invoked during this build.
- Modify `scripts/run_backtest.py`: bounded portfolio compatibility cutover only; reserve one PostgreSQL row immediately before each `run_walk_forward(..., ledger=None)`, require a newly-created authorization receipt, complete before output, and replace the JSON count read with the canonical database count.
- Modify `icarus/engine/runner.py`: reject every non-`None` legacy JSON ledger before evaluation, remove its post-evaluation JSON append, and keep fold progress logs free of trades, Sharpe, or other outcome metrics until the CLI has committed results.
- Create `tests/unit/test_run_backtest_trial_barrier.py`: proves the portfolio CLI cannot evaluate or release results before durable reservation/completion.
- Do not modify the portfolio simulator, signal simulator, `goal.yaml`, `TASKS.md`, `OPERATOR.md`, `docs/STATE.md`, or the real `var/` ledger in this slice.

## Exact Domain API

`icarus/state/trial_ledger.py` will expose these names and signatures:

```python
type JsonValue = None | bool | int | float | str | list[JsonValue] | dict[str, JsonValue]


class TrialOrigin(StrEnum):
    OPERATOR = "operator"
    INVENTOR = "inventor"


class TrialKind(StrEnum):
    PORTFOLIO = "portfolio"
    SIGNAL_FULL = "signal_full"
    SIGNAL_FOLD = "signal_fold"


class TrialTerminalState(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"


class TrialReservationAuthorization(StrEnum):
    NEW_EVALUATION = "new_evaluation"
    RECOVERY_ONLY = "recovery_only"


@dataclass(frozen=True, slots=True)
class EvaluationReservation:
    ordinal: int
    kind: TrialKind
    fold_index: int | None
    start_index: int | None
    end_index_exclusive: int | None
    start_ts: datetime | None
    end_ts: datetime | None
    reset_identity: str


@dataclass(frozen=True, slots=True)
class TrialBatchReservation:
    run_group_id: UUID
    origin: TrialOrigin
    strategy_name: str
    strategy_version: int
    strategy_sha256: str | None
    panel_sha256: str | None
    config_sha256: str | None
    primitives: tuple[str, ...]
    evaluations: tuple[EvaluationReservation, ...]
    source: Literal["native", "legacy_json_v1"] = "native"


@dataclass(frozen=True, slots=True)
class TrialEvaluationResult:
    ordinal: int
    kind: TrialKind
    oos_sharpe: Decimal | None
    oos_sharpe_after_tax: Decimal | None
    observation_count: int
    payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class TrialBatchReceipt:
    run_group_id: UUID
    reservation_sha256: str
    evaluation_ids: tuple[UUID, ...]
    lifetime_trial_count: int
    newly_created: bool
    authorization: TrialReservationAuthorization


@dataclass(frozen=True, slots=True)
class TrialBatchTerminal:
    run_group_id: UUID
    state: TrialTerminalState
    results_sha256: str | None
    failure_code: str | None


@dataclass(frozen=True, slots=True)
class LegacyPortfolioTrial:
    ordinal: int
    at: datetime
    strategy_name: str
    strategy_version: int
    origin: TrialOrigin
    primitives: tuple[str, ...]
    oos_sharpe: Decimal | None
    oos_sharpe_after_tax: Decimal | None
    after_tax_field_present: bool
    oos_trades: int
    folds: int
    original_payload: dict[str, JsonValue]


@dataclass(frozen=True, slots=True)
class LegacyPortfolioLedger:
    schema: Literal[1]
    sha256: str
    trials: tuple[LegacyPortfolioTrial, ...]


@dataclass(frozen=True, slots=True)
class ActivationReceipt:
    legacy_entry_count: int
    legacy_sha256: str
    lifetime_trial_count: int


class PostgresTrialLedger:
    def __init__(self, engine: Engine) -> None: ...
    def reserve(self, batch: TrialBatchReservation) -> TrialBatchReceipt: ...
    def complete(
        self,
        receipt: TrialBatchReceipt,
        results: tuple[TrialEvaluationResult, ...],
    ) -> TrialBatchTerminal: ...
    def fail(
        self,
        receipt: TrialBatchReceipt,
        *,
        failure_code: str,
    ) -> TrialBatchTerminal: ...
    def lifetime_count(self) -> int: ...
    def import_legacy_and_activate(self, legacy: LegacyPortfolioLedger) -> ActivationReceipt: ...


def read_legacy_portfolio_ledger(path: Path) -> LegacyPortfolioLedger: ...


class TrialLedgerError(RuntimeError): ...


class TrialLedgerUnavailable(TrialLedgerError): ...


class TrialLedgerCorruption(TrialLedgerError): ...


class TrialLedgerNotActivated(TrialLedgerError): ...


class TrialIdentityConflict(TrialLedgerError): ...
```

UTC-aware timestamps, exact non-Boolean integers, finite JSON numbers, non-empty bounded strings, sorted unique primitives, lowercase 64-character hashes, contiguous ordinals, and signal `N+1` geometry are checked before opening a transaction. Native rows require all three hashes and exact window coordinates. For signal batches, ordinal 0 is the only `SIGNAL_FULL`; each fold has `fold_index == ordinal - 1`; fold indices are unique and contiguous; fold spans are non-empty, strictly ordered, non-overlapping, and contained within the full-span indices and UTC dates; and reset identities are exactly `continuous_full_development_v1` or `fresh_signal_simulator_per_fold_v1`. Portfolio reset identity is exactly `walk_forward_portfolio_v1`. Duplicate, omitted, reordered, or out-of-span folds refuse. Legacy rows explicitly retain unavailable provenance as null and keep their original payload and digest; they never receive invented hashes, dates, or after-tax metrics. Failure codes match `[A-Z][A-Z0-9_]{0,63}` and never contain exception text.

Evaluation UUIDs are derived with UUID v5 from `run_group_id` plus the canonical evaluation body. The reservation SHA-256 is canonical ASCII JSON (`sort_keys=True`, compact separators) over the full batch excluding derived IDs. Signal results must have both Sharpe fields null. Portfolio results retain both pre-tax and after-tax Sharpe, preserving the current F43 correction.

The service catches SQLAlchemy/psycopg availability failures as `TrialLedgerUnavailable`, impossible persisted shapes as `TrialLedgerCorruption`, inactive authority as `TrialLedgerNotActivated`, and reused IDs with different content as `TrialIdentityConflict`. Error text must not contain the DSN or raw database exception. `reserve()` and `complete()` each own their transaction. A newly inserted, acknowledged reservation returns `newly_created=True` and `NEW_EVALUATION`; an existing identical reservation always returns `newly_created=False` and `RECOVERY_ONLY`. Unknown commit acknowledgement halts; retrying the same ID may recover state but cannot start evaluation. A new evaluation attempt requires a new ID and new acknowledged authorization.

## Exact Database Schema and Migration

`20261008_atomic_trial_ledger.py` has `revision = "20261008_trial_ledger"` and `down_revision = "d8847faf5e20"`. It creates:

1. `trial_ledger_activation`: singleton `id SMALLINT PRIMARY KEY CHECK (id=1)`, `legacy_schema INTEGER NOT NULL CHECK (legacy_schema=1)`, `legacy_entry_count INTEGER NOT NULL CHECK (legacy_entry_count>=0)`, `legacy_sha256 CHAR(64) NOT NULL`, `activated_at TIMESTAMPTZ NOT NULL DEFAULT now()`.
2. `trial_batches`: `run_group_id UUID PRIMARY KEY`, `reservation_sha256 CHAR(64) NOT NULL`, `origin VARCHAR(16) NOT NULL CHECK IN ('operator','inventor')`, `source VARCHAR(24) NOT NULL CHECK IN ('native','legacy_json_v1')`, `strategy_name VARCHAR(128) NOT NULL`, `strategy_version INTEGER NOT NULL`, nullable `strategy_sha256/panel_sha256/config_sha256 CHAR(64)`, `primitives JSONB NOT NULL`, `expected_evaluations INTEGER NOT NULL CHECK (>0)`, `reserved_at TIMESTAMPTZ NOT NULL DEFAULT now()`. A CHECK requires all three hashes for `source='native'`.
3. `trial_evaluations`: `evaluation_id UUID PRIMARY KEY`, `run_group_id UUID NOT NULL REFERENCES trial_batches`, `ordinal INTEGER NOT NULL CHECK (ordinal>=0)`, `kind VARCHAR(24) NOT NULL CHECK IN ('portfolio','signal_full','signal_fold')`, nullable `fold_index/start_index/end_index_exclusive INTEGER`, nullable `start_ts/end_ts TIMESTAMPTZ`, `reset_identity VARCHAR(64) NOT NULL`, and `UNIQUE(run_group_id, ordinal)`. CHECK constraints pin full-span ordinal 0/no fold, fold ordinals >=1 with nonnegative fold index, ordered indices, and paired UTC span fields where native provenance exists.
4. `trial_results`: `evaluation_id UUID PRIMARY KEY REFERENCES trial_evaluations`, `result_sha256 CHAR(64) NOT NULL`, nullable `oos_sharpe/oos_sharpe_after_tax NUMERIC` with no precision or scale coercion, `observation_count INTEGER NOT NULL CHECK (>=0)`, `payload JSONB NOT NULL`, `recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()`. Domain validation accepts only finite Decimals with at most 128 significant digits and raw Decimal tuple exponent between -128 and 128, then verifies the database round-trip is exactly equal; nonrepresentable values refuse rather than round.
5. `trial_batch_terminals`: `run_group_id UUID PRIMARY KEY REFERENCES trial_batches`, `state VARCHAR(16) NOT NULL CHECK IN ('completed','failed')`, nullable `results_sha256 CHAR(64)`, nullable `failure_code VARCHAR(64)`, `recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()`, with a CHECK requiring digest only for completed and failure code only for failed.

Indexes are `trial_batches(reserved_at)` and `trial_batch_terminals(state)`; the unique constraint already indexes `trial_evaluations(run_group_id, ordinal)`, so no duplicate index is added. Shared DB triggers reject UPDATE, DELETE, and statement-level TRUNCATE on all five tables. A deferred constraint trigger rejects commit unless every newly inserted batch has exactly `expected_evaluations` rows. An evaluation-insert trigger rejects ordinals outside the owning batch and any insert after a terminal. A result-insert trigger rejects results after a terminal. A deferred result-consistency trigger rejects commit if any newly inserted result lacks one `COMPLETED` terminal or if that completed batch lacks any reserved result; a result-free pending reservation remains valid. A terminal trigger requires exactly the reserved result cardinality for `completed` and zero results for `failed`. Every new batch insert requires the singleton activation row, including legacy import batches inserted later in the same activation transaction.

`downgrade()` first refuses when the activation singleton exists, then drops only these
triggers/functions/tables in reverse dependency order. It therefore works only on an empty,
unactivated test database and cannot destroy activated lifetime history.

## Task 1: Freeze Contracts and Database Invariants

**Files:** Create `tests/unit/test_trial_ledger.py`; create `icarus/state/trial_ledger.py`; modify `icarus/state/models.py`; create the Alembic migration.

- [ ] **Red:** Add contract tests for UTC timestamps, Boolean-as-int refusal, invalid hashes, unsorted/duplicate primitives, invalid span pairs, non-contiguous ordinals, duplicate/omitted/reordered/out-of-span folds, wrong `fold_index == ordinal - 1`, wrong reset identity, missing native provenance, signal-result Sharpe refusal, and exact Decimal accept/refuse boundaries. Add canonical-hash tests proving mapping order does not matter and any field change does.
- [ ] **Run red:** `uv run pytest tests/unit/test_trial_ledger.py -q`; expect import/contract failures because the module does not exist.
- [ ] **Green:** Implement the enums/dataclasses/validation/hash functions exactly as specified, then add the five ORM models and migration SQL. Keep database I/O out of constructors and hashing.
- [ ] **Run green:** `uv run pytest tests/unit/test_trial_ledger.py -q`; expect all contract tests to pass.

## Task 2: Prove Atomic Reservation, Count, Completion, Failure, and Concurrency

**Files:** Modify `icarus/state/trial_ledger.py`; create
`tests/integration/test_trial_ledger_postgres.py`; modify `.github/workflows/ci.yml` to supply the
explicit trial-test DSN from CI's existing ephemeral PostgreSQL service.

- [ ] **Red:** Against an isolated migrated PostgreSQL database, add tests that reservation before activation refuses; one signal reservation inserts exactly `N+1` with exact fold geometry; a committed reservation with no terminal remains counted from a new connection; known failure remains counted; completion inserts all results and terminal atomically; and UPDATE/DELETE/TRUNCATE fail at the database layer.
- [ ] **Red transaction guards:** Use direct SQL to attempt (a) a batch with an omitted fold, (b) one result without a terminal, (c) a partial result set plus `COMPLETED`, (d) results against `FAILED`, and (e) results added after a terminal. Each transaction must fail at commit and leave no partial result rows. A reservation with zero results and no terminal must commit and count.
- [ ] **Red concurrency:** Use independent PostgreSQL processes, not only threads sharing an engine. Concurrent distinct UUIDs each add `N+1`; concurrent identical UUID plus identical body adds only `N+1`, with exactly one `NEW_EVALUATION` receipt and all other receipts `RECOVERY_ONLY`; identical UUID plus changed body refuses. Repeat equivalent checks for completion retries and conflicting result bodies.
- [ ] **Red acknowledgement/crash:** Inject commit-acknowledgement loss after PostgreSQL commits a reservation. A same-ID retry returns the counted recovery receipt and must not call the evaluation probe; a fresh UUID is required to obtain `NEW_EVALUATION`. Separately, a subprocess reserves a synthetic batch, confirms receipt through a pipe, then exits without completion; the parent proves all rows remain counted. A process killed before transaction commit leaves zero rows. Label this as committed-process-crash coverage, not power-loss proof.
- [ ] **Run red:** apply the new migration only to an isolated service or one disposable cached `postgres:16` container with synthetic credentials/data, then run `uv run pytest tests/integration/test_trial_ledger.py -q`; expect missing service behavior. Do not connect to the operator database or pull an image.
- [ ] **Green:** Implement `PostgresTrialLedger`. Reservation uses conflict-aware `INSERT ... ON CONFLICT DO NOTHING`, followed by a locked reread and digest/cardinality comparison; this handles both a newly inserted row and a concurrent winner because `SELECT FOR UPDATE` cannot lock a missing row. Finalization locks the existing batch row, compares canonical digests, and inserts results plus terminal in one transaction. Validate returned cardinality, geometry, IDs, authorization, and exact Decimal round trips before returning. Translate datastore errors to sanitized typed failures.
- [ ] **Run green:** rerun the integration module. No test may query or modify `var/trial_ledger.json`, depend on cleanup of append-only rows, or share fixed UUIDs between runs.

## Task 3: Preserve Legacy Portfolio Trials and Establish One Authority

**Files:** Modify `icarus/state/trial_ledger.py`; create `scripts/migrate_trial_ledger.py`; modify `scripts/run_backtest.py`; create `tests/unit/test_run_backtest_trial_barrier.py`; extend both trial-ledger test modules.

- [ ] **Red legacy validation:** With temporary files, test schema 1 in both legitimate shapes: early rows omit `oos_sharpe_after_tax`, while later rows contain it as null or a value. Preserve the exact original mapping/digest and distinguish absent from explicit null. Require `at`, strategy/version/origin/primitives, pre-tax Sharpe, trade count, and fold count; validate UTC timestamp parsing. Missing file, malformed JSON, wrong schema, missing required keys, unexpected keys, non-list trials, or one bad row refuses before any database write.
- [ ] **Red import:** Import a mixed old/new three-row synthetic legacy ledger and prove canonical count 3, original order/timestamps/payloads/null-or-absence preserved, repeated import adds zero, and changed content at an existing ordinal refuses. The import and singleton activation commit together; any planted mid-import failure leaves neither activation nor rows. Once activated, a different legacy digest or count refuses rather than trying an incremental second import.
- [ ] **Green import:** Derive deterministic legacy run/evaluation UUIDs from namespace `icarus:legacy-trial-ledger:v1:<ordinal>`. Store unavailable hashes/window coordinates as null with `source='legacy_json_v1'`; store the exact original payload and its hash. A missing historical after-tax field stays absent in that payload and maps to database null without fabrication. `scripts/migrate_trial_ledger.py --check --source PATH` validates and prints only schema/count/digest; `--apply` requires `ICARUS_PG_DSN`, calls the one transaction, and prints the activation receipt. Do not add a force/reset path.
- [ ] **Red portfolio bridge:** Test `scripts/run_backtest.py` through injected ledger/panel/strategy dependencies. Reservation failure or a `RECOVERY_ONLY` receipt means `run_walk_forward` is never called. The canonical call uses `ledger=None`, so JSON is not independently appended. Evaluation failure calls `fail()` and emits no result artifact. Capture the runner logger, CLI stdout/stderr, and artifact writer: completion failure must expose no trades, Sharpe, P&L, win rate, or result payload. Two identical operator reruns use fresh UUIDs and add two trials; a same-ID persistence retry adds one but never reauthorizes evaluation.
- [ ] **Green portfolio bridge:** Build one `PORTFOLIO` reservation immediately before each existing `run_walk_forward` call and require `NEW_EVALUATION`; finalize it before appending to `results`, writing artifacts, or calling `_print_sheet`; then report `PostgresTrialLedger.lifetime_count()`. Replace `runner.py`'s existing fold `trades`/`sharpe` log with outcome-free progress fields only. Keep portfolio simulation, result JSON shape, and gate behavior unchanged. Before explicit activation the CLI stops at the ledger barrier; it never falls back to JSON or treats a missing ledger as empty.
- [ ] **Low-level legacy guard:** At the start of `run_walk_forward`, before `evaluate_once`, reject `ledger is not None` with a typed fail-closed error. Remove its internal `record_trial` call. Keep `ledger=None` for explicit synthetic fixtures and the canonical counted CLI. This is a guard against the old writer, not proof that arbitrary library callers cannot bypass the CLI; there is still no supported low-level real-data API in this slice.
- [ ] **Compatibility assertion:** Leave `icarus.engine.runner.read_trials()` and `record_trial()` only to parse/characterize legacy fixtures during this slice, with deprecation text naming PostgreSQL as the post-activation authority. No production entrypoint may call them. A repository search test pins that `scripts/run_backtest.py` contains neither `DEFAULT_TRIAL_LEDGER` nor `read_trials`/`record_trial` and that `run_walk_forward` rejects a non-`None` ledger before the evaluation probe.

## Task 4: Verification and Review Handoff

**Files:** No additional runtime files. Parent owns durable status/review documents after independent review.

- [ ] Run focused tests: `uv run pytest tests/unit/test_trial_ledger.py tests/unit/test_migrate_trial_ledger.py tests/unit/test_run_backtest_trial_barrier.py tests/integration/test_trial_ledger_postgres.py -q` against only the isolated migrated database.
- [ ] Run affected regressions: `uv run pytest tests/unit/test_runner.py tests/unit/test_metric_sheet.py tests/unit/test_signaltest.py tests/unit/test_signal_simulator.py tests/unit/test_portfolio_characterization.py -q`.
- [ ] Run the full available unit suite: `uv run pytest tests/unit -q`.
- [ ] Run static checks: `uv run mypy icarus scripts tests`; `uv run ruff check icarus scripts tests`; `uv run ruff format --check icarus scripts tests`; `git diff --check`.
- [ ] Run the existing synthetic portfolio characterization/golden checks only. Do not run `scripts/run_backtest.py` against `var/panel.npz`, a real strategy, official data, or the lockbox.
- [ ] Mutation checks must demonstrate that tests fail when: reservation moves after evaluation; a recovery receipt reauthorizes evaluation; acknowledgement loss starts work; a same-ID conflict is accepted; a rerun is deduplicated by content; one fold is omitted or mis-mapped; one result commits without a terminal; terminal precedes a full result batch; `FAILED` stops counting; TRUNCATE succeeds; activation is bypassed; old missing-after-tax history is refused or fabricated; a fold metric log leaks; or the portfolio CLI falls back to JSON.
- [ ] Independent review must inspect SQL transaction boundaries, deferred PostgreSQL trigger behavior, multi-process races, acknowledgement/crash semantics, sanitized error paths, old/new legacy preservation, exact `N+1` geometry, exact Decimal storage, and captured proof that no metric-bearing logger/stdout/artifact output occurs before result commit.

## Review Decisions Required Before Runtime Edits

1. Approve PostgreSQL as the sole post-activation count and the bounded `scripts/run_backtest.py` bridge. This avoids two lifetime totals without rewriting the portfolio simulator.
2. Approve conservative counting: a committed reservation counts forever even if evaluation never starts, crashes, or fails. This may over-count uncertain starts, but it cannot under-count inspected results.
3. Approve caller-generated `run_group_id` as the retry boundary: same UUID is only a recovery/readback persistence retry and can never reauthorize evaluation; any rerun/re-evaluation gets a fresh UUID and count.
4. Approve null legacy provenance rather than fabricated strategy/panel/config hashes. Activation remains blocked if the legacy JSON is absent or corrupt.
5. Confirm that actual import/activation remains a separate operator action after code and migration review. Until then, no portfolio or signal real-data evaluation is permitted through the new API.

## Explicitly Deferred

Step 8 signal orchestration, actual real-data evaluation, applicability/refusal policy, source and time matching, F48 charge correction, benchmark certificates, placebo evidence, DSR/PBO/effective trial weighting, any trial/search cap, lockbox use, real-market adapters, broker credentials, inference enablement, production migration execution, and reading or modifying the operator's actual legacy ledger.
