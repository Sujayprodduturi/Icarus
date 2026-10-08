# Atomic trial-ledger build review - 2026-10-08

SCOPED PASS for the isolated Step 7 infrastructure build at source commit `c132478`. Actual operator ledger import/activation and real-data evaluation remain held. This does not close Step 6b, M4 or method adoption.

Every evaluation reserves a permanent counted attempt before work. Failed or abandoned attempts retain their count; identical persistence retries recover without reauthorizing evaluation. Results become visible only after verified atomic completion. PostgreSQL is the sole post-activation authority; legacy JSON helpers remain fixture-only.

The independent reviewer completed simplicity then engineering review and issued GO. Parent independently reran the actual PostgreSQL tests, inspected input bindings and reproduced the Windows startup defect. Eleven postcommit source mutations were detected by behavioral tests; exact bytes were restored and checked. The restored final suite passed 54 tests, including 20 real-PostgreSQL tests and four golden/metric-sheet checks, in 12.04 seconds. Strict mypy passed 197 sources; global Ruff lint, 373-file format check and diff check passed.

The earlier broad snapshot had 2,852 passed, 14 skipped and one startup diagnostic failure. Parent reproduced the empty closed Windows pipe error, obtained independent review for a poll-only fix, and passed 16 affected startup/main tests. A genuinely Linux-specific partial-message case remains locally skipped. No fresh full-suite PASS is claimed. Hosted checks will independently test the pushed final snapshot.

Bounded supporting changes: CI now explicitly provides the disposable PostgreSQL DSN so the new integration cases run; Alembic escapes ConfigParser percent characters; build_panel's existing generic return annotation was corrected without running data assembly. The diagnostic fix grants no evaluation/resume authority. Decimal documentation now names the implemented raw exponent bound.

The disposable PostgreSQL container was removed after verification. Existing study artifacts, actual legacy ledger, market data, goal thresholds, calculator and strategy YAMLs were not changed. Strategy breadth remains a reviewed proposal: five families/six specifications, no new performance evidence.

Next: close fees/taxes, strict-through next-bar matching, benchmark/data timing and applicability/refusal dependencies, then immutable rule cards. Donchian opposite exits and scheduled low-volatility rebalancing need explicit support. HFT remains outside the PRD. D41 requires separate authorization before real-data evaluation; lockbox and broker/live paths remain held.

[Compact proof](2026-10-08-trial-ledger-build-proof.json).

## Independent final source review

2026-10-08 — Ordered ponytail simplicity then engineering review of current Step 7 runtime, SQL migration/models/env, CLI/import command, tests/CI, and bounded startup diagnostic change.
GO for isolated synthetic infrastructure integration/commit and the already prepared postcommit verification; no actionable implementation blocker remains. This is not authorization for operator activation/import or real-data evaluation.
Simplicity: five explicit append-only tables and one concrete synchronous service remain appropriate; no unnecessary framework or duplicate ordinal index is present.
Reservation is native-only, committed before evaluation, uses conflict-aware insertion and locked reread, and returns NEW_EVALUATION only for a newly acknowledged row; identical retries are RECOVERY_ONLY and permanent counts include pending/failed/crashed work.
Completion locks the batch and atomically inserts all results plus terminal; retry verifies exact persisted kinds/ordinals/payloads/digests/Decimals. Deferred SQL constraints reject omitted evaluations or partial results, with result-free pending batches permitted; UPDATE/DELETE/TRUNCATE are guarded.
The actual main bridge is tested for reserve outage, recovery-only refusal, completion outage, fresh identical reruns, evaluation failure, and all three input-load mutations. Core fold logs are outcome-free and database/evaluation error tracebacks are sanitized.
Real PostgreSQL tests now cover committed ACK loss for reserve/complete, independent-process same/distinct identity and finalization races, committed crash/precommit kill, mixed historical import/idempotency, planted import rollback, and direct malformed-result transactions.
Exact signal fold indices and UTC dates are ordered/nonoverlapping/contained; reset identities and source fingerprints are bound; signal Sharpe fields remain null. Early missing-after-tax history retains its absence and original payload rather than a fabricated value.
Decimal plan wording will align with implemented finite <=128-digit and abs(raw exponent)<=128 bound, with exact NUMERIC round-trip verification; this changes documentation only, not numeric behavior or thresholds.
Poll-only BrokenPipeError handling classifies an empty closed Windows hint as MISSING; receive/parsing failures retain INVALID and all ERROR/no-authority/no-resume semantics remain unchanged. CI now supplies the isolated test DSN; build_panel's tuple typing change is annotation-only.
Evidence inspected: build/red-green.md records 20 real-PG acceptance tests, 48 ledger tests, 156 affected regressions, and the broad 2852-pass/14-skip run with one now-addressed startup diagnostic failure; the broad run was not repeated.
Parent independently reports final 50 focused tests PASS/12.38s, explicit mypy PASS/197 sources, and global lint/format PASS/197 files. Reviewer performed source/evidence inspection, not a concurrent heavy test run.
Parent subsequently completed eleven-defect detection and exact restoration, followed by 54 passing restored tests. No actual legacy read/import, production migration, real panel, inference enablement, broker path, or study was performed by this reviewer.
