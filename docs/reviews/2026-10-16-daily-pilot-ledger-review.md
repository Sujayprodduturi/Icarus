# Daily descriptive pilot ledger integration review

Scope: read-only review of the current atomic trial-ledger migration, ORM models, ledger service and PostgreSQL integration tests. No database, runtime, price or broker path was touched.

## Disposition

**GO for one new forward migration, with two direct-SQL guards.** Add `TrialKind.DESCRIPTIVE_PILOT = "descriptive_pilot"` as one native evaluation at ordinal `0`, `fold_index=NULL`, exact non-null span and reset `daily_descriptive_pilot_v1`. Keep the seven cards as seven sequential one-evaluation reservations; `lifetime_count()` already counts `trial_evaluations`, so this adds exactly seven trials without a transaction redesign.

## Existing invariants and exact migration surface

| Existing invariant | Current enforcement | Required change |
|---|---|---|
| Persisted kinds | `ck_trial_evaluation_kind` | Drop/recreate under the same name with only `'descriptive_pilot'` added. Mirror it in `TrialEvaluation.__table_args__`. Do not edit `20261008_atomic_trial_ledger.py`. |
| Native evidence hashes | `ck_trial_batch_native_hashes`; canonical reservation hash binds every evaluation field | No SQL or hashing change. The new kind/reset/span flow through the existing canonical hash. |
| Activation before reservation | `trial_batch_requires_activation` | No change. |
| Append-only history | row UPDATE/DELETE and statement TRUNCATE triggers on all five tables | No change. |
| Count/cardinality | deferred `trial_batch_cardinality`; `lifetime_count()` counts evaluation rows | Retain. It supplies atomic exact-cardinality and makes each descriptive singleton count once. |
| Ordinal/fold basics | `ck_trial_evaluation_ordinal`, `ck_trial_evaluation_fold`, unique batch/ordinal, `trial_evaluation_insert_guard` | Extend the insert guard: descriptive requires native source, expected count `1`, ordinal `0`, null fold, non-null span and exact reset; portfolio remains exactly one ordinal-zero `walk_forward_portfolio_v1`; `signal_full` remains ordinal zero with expected count at least `2`; folds remain later ordinals with their existing reset. |
| Non-portfolio Sharpe prohibition | `TrialEvaluationResult.__post_init__` only | Extend `trial_result_insert_guard` to select the evaluation kind and reject either Sharpe field unless kind is `portfolio`; retain its after-terminal rejection. This makes direct SQL match the existing Python invariant. |
| Results and terminal atomicity | `trial_terminal_guard` plus deferred `trial_result_consistency` | No change. |

The insert-guard geometry is necessary. The current `test_direct_batch_with_omitted_fold_cannot_commit` declares three evaluations and inserts two, so it proves only deferred cardinality. Today direct SQL can declare one evaluation, insert one `signal_full`, and commit. A focused `expected_evaluations=1` negative case must prove that old no-fold shape is still refused after the new singleton alternative is added.

## Required PostgreSQL cases

1. A valid activated native descriptive singleton commits, persists the exact kind/reset/span, retries as recovery-only, and increments the lifetime count by one.
2. Direct SQL refuses descriptive wrong reset, null span, nonzero ordinal, non-null fold, non-native source, expected count other than one, or a mixed second evaluation; the whole transaction rolls back.
3. Direct SQL refuses a one-row `signal_full` batch and still accepts the existing full-plus-fold and one-row portfolio geometries.
4. Direct SQL refuses Sharpe on both `signal_full` and `descriptive_pilot`; portfolio Sharpe remains allowed. Python tests retain the same prohibition.
5. Existing activation, native-hash, append-only UPDATE/DELETE/TRUNCATE, completion cardinality, failure terminal and retry/hash-conflict tests remain green.

## Downgrade contract

The new migration's downgrade must query for `trial_evaluations.kind='descriptive_pilot'` and raise **before any DDL** when one exists. That preserves the row and the expanded schema. When none exists, restore the previous kind constraint and prior trigger functions in place; do not drop tables or history. Test both paths. This is distinct from the 20261008 migration's later downgrade-to-base refusal, which still rejects destruction of any activated ledger.

The Python geometry remains unchanged for ordinary signal full-plus-fold batches and portfolio batches, including fold containment and ordering. The new SQL checks should enforce the kind/cardinality/reset boundary needed against direct insertion; they need not redesign reservation transactions or duplicate the existing Python fold-time algorithm.
