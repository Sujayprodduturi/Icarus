# Signal trial ledger plan review — 2026-10-08

This tracked record consolidates the two read-only reviews of
[`2026-10-08-signal-trial-ledger-plan.md`](../plans/2026-10-08-signal-trial-ledger-plan.md).
No code, database, evaluation or actual ledger was run or read by either review.

Copied source records:

- `var/verification/2026-10-08/trial-ledger/review/plan-review.md` — SHA-256 `8442FD9D3EB98F4B40C012DB93E82F1BE9E097F4A73868C95356AFDFE28514A8`
- `var/verification/2026-10-08/trial-ledger/review/amended-plan-review.md` — SHA-256 `FE286D2CFB328A71F57BF6334B5580A25887FEAC9D14729208C1D45BD1E86AAE`

## Initial ordered review — NO-GO

2026-10-08 — Ordered ponytail simplicity then engineering correctness review; source-only, no evaluation/database launch/actual-ledger access.

Verdict: NO-GO for runtime build until the following bounded plan corrections; PostgreSQL direction and isolated Step 7 scope are appropriate.

Simplicity: five concrete append-only tables need no framework; :172 duplicates the UNIQUE(run_group_id, ordinal) index already at :168 — omit the redundant index (net: -1 declaration).

P1 — plan :18, :92–96, :203, :223: define persistence retry as never authorizing another evaluation; an existing pending/crashed reservation receipt cannot be reused to start work. Test retry after lost reservation acknowledgement and after crash; retain its count, halt/recover receipt, and use a fresh UUID for any evaluation rerun.

P1 — plan :193: SELECT FOR UPDATE cannot lock a missing batch. Specify conflict-aware insert followed by locked reread/digest comparison; prove same-ID/conflicting-ID reservation/finalization races with independent PostgreSQL processes, including commit acknowledgement loss.

P1 — plan :172/:189: a direct transaction inserting one result without a terminal currently can commit. Add deferred end-of-transaction result consistency: every newly inserted result belongs to a COMPLETED batch containing exactly all reserved results; a result-free pending reservation remains valid. Prove direct-SQL subset rejection.

P1 — plan :203–205/:217 and runner.py :315–320: CLI finalization cannot prevent the existing per-fold trades/Sharpe log before commit. Suppress/defer metric-bearing core logs for the bridge and capture logger/stdout/artifacts on complete() failure; no result may escape.

P1 — plan :205 and runner.py :258/:346–347: deprecation text leaves default library JSON writes available. Add the bounded ledger != None refusal before evaluate_once; retain ledger=None for explicit synthetic fixtures/canonical CLI, and characterize the remaining low-level bypass rather than claiming a real-data API exists.

P2 — plan :200 and runner.py :722: valid schema-1 history predates oos_sharpe_after_tax. Support the documented earlier row shape, retaining absence/null provenance without fabricating an after-tax number; temporary old/new fixtures must import without lost counts.

P2 — plan :172: UPDATE/DELETE triggers do not reject TRUNCATE. Add a BEFORE TRUNCATE statement refusal or explicitly restricted/tested ledger-role privileges; do not claim unrestricted database append-only protection.

P2 — plan :24/:189–194: permit one disposable synthetic PostgreSQL test container if no isolated service exists; no study/data-plane launch. Otherwise the mandatory real-PG crash/concurrency proof is blocked by the plan itself.

P2 — plan :156/:168: pin fold_index-to-ordinal mapping, uniqueness, full-span containment, exact source-index/date/reset identity geometry; add malformed/duplicate/omitted-fold tests. SIGNAL_FULL/FOLD Sharpe fields stay null; no portfolio metric fabrication.

P2 — plan :169/:200: NUMERIC(24,12) can silently round a higher-precision Decimal while its digest binds the original. Specify canonical finite precision/range conversion or reject nonrepresentable values; preserve legacy evidence explicitly. Include both changed scripts in strict mypy (:214).

Scope remains held: no Step 6b adoption, Step 8 runner, real data, inference change, production migration, or actual legacy-ledger read; activation/import is a separately reviewed operator action.

## Amended-plan re-review — GO for the isolated synthetic build

2026-10-08 — Fast bounded re-review of amended signal-trial-ledger plan against plan-review.md; no code edits or execution.

GO for the isolated synthetic infrastructure build; all identified plan blockers are concretely corrected, subject to the specified implementation proofs.

Plan :169/:200–203 now separates NEW_EVALUATION from RECOVERY_ONLY, halts unknown commit acknowledgement, handles missing-row races with conflict-aware insertion, and requires independent-process PostgreSQL/crash proofs.

Plan :181/:199 now rejects direct partial-result commits through deferred result consistency, preserves result-free pending reservations, rejects TRUNCATE, and removes the duplicate unique-key index.

Plan :213–216 now captures all metric-bearing output failure paths, removes the pre-commit fold metric log, rejects legacy non-None writers before evaluation, and accurately states the unsupported low-level real-data API boundary.

Plan :178/:210–212 preserves early missing-after-tax history and exact original payloads, uses exact bounded NUMERIC round trips, and tests explicit fold geometry/null signal Sharpe rather than fabricated portfolio metrics.

Plan :24/:225 permits only disposable synthetic PostgreSQL testing and includes scripts in strict typing; actual import/activation, actual-ledger reads, Step 8, real data, inference, and statistical adoption remain held.

Acceptance still requires demonstrating commit-acknowledgement loss also during completion: no output before durable terminal recovery and no re-evaluation; this follows :169/:213 and is an implementation verification item, not a new architecture requirement.

## Durable disposition

The amended review authorizes only the isolated synthetic infrastructure build and its specified proofs. As of this checkpoint that build is **IN PROGRESS**; this document makes no completion, test, migration or current GitHub-workflow claim. Scheduling Step 7 before later real-data work does not close Step 6b, M4, or adopt a statistical method.
