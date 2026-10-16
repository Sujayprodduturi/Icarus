# Daily pilot ledger build review

Scope: uncommitted ledger/model/timed-runner changes and the new `20261016_descriptive_pilot_trial.py` migration, compared with published `eb014f4`. Reviewed against AGENTS.md, OPERATOR.md, the daily-pilot implementation plan and the preceding ledger integration review. No actual prices, operator database, provider communication or broker path was used.

## Standards

The first independent integration invocation was interrupted with no test output because the designated disposable service was no longer available after interruption. It supplies no passing database evidence. Focused offline ledger/timed-runner tests independently passed **32 tests**; an initial restricted-sandbox attempt had two temporary-directory setup errors, resolved by the offline run outside that restriction.

After the root recreated and verified the disposable PostgreSQL service, the independent full integration file passed **24 tests in 11.24 seconds**. Tested hashes: `trial_ledger.py` `b371cf7dce3e932aa897a69ca588b091138a63b907d44311f2acf431cd65399f`; `models.py` `ae1de6abd62917b359da82b648319ae4992b3c2ba4480e4012e7f61994f3c1d9`; `timed_runner.py` `8f1119e2c97fe71df7c97f739295c927a5354445c3e04e7df86f4d72febb9fb6`; new migration `bd38dea5d742ba70108c768a5a7e6b7592ea818b8fe2dda5883a3ddcd48abf23`; integration tests `728a18734b3586bc8ad9dfbca6b622a1330ee1de1c8564a41aec5aef9f665e2f`. This snapshot still predates the Python native-only fix and added retained acceptance tests.

Independent disposable-schema downgrade probes also passed both paths. With one pilot reserved, downgrade to `20261008_trial_ledger` raised the intended refusal and retained the row, current Alembic revision, expanded kind constraint and geometry function. With three ordinary signal evaluations and no pilot, the same one-step downgrade succeeded, retained all three evaluations, and restored the prior kind constraint/cardinality function. Schemas were isolated and removed by the existing fixture; no operator database was used.

## Spec

**Resolved [P2]: native source in the Python descriptive geometry branch.** The initial `TrialBatchReservation._validate_geometry()` accepted a descriptive singleton with `source='legacy_json_v1'`, including missing native hashes and all-null spans. The implementation owner added an explicit native-only guard and retained source/span negative unit tests. Native hashes and contiguous ordinals remain enforced by the preceding existing validation.

The forward migration leaves the old migration unchanged, preserves activation/immutability/result-terminal triggers, and adds the persisted kind plus descriptive batch geometry and direct-SQL non-portfolio Sharpe refusal. Its downgrade checks for pilot history before its first DDL and otherwise restores the prior constraint/functions without dropping tables. These are code observations, awaiting independent database execution.

## Corrective coverage and final verification

After the initial independent review, the root explicitly transferred ledger-only corrective ownership to this reviewer. Subsequent retained-test additions are therefore **corrective-builder verification**, not an independent review of my own additions. Root must independently review that final diff before completion.

Added retained integration cases cover malformed pilot reset/all-null span/ordinal/fold/source/count/native hash; old signal-full-without-fold refusal; signal and pilot records with either forbidden Sharpe field, matching the intended trigger exception; valid pilot persisted geometry/recovery-only retry/count; native portfolio singleton with both allowed Sharpe fields; and both one-step downgrade paths preserving exact evaluation, batch and activation rows. The count-negative case inserts two pilot rows, so it cannot pass merely by observing an omitted-row cardinality failure.

Final corrective gate: **70 tests passed in 14.90 seconds** across unit trial-ledger, unit timed-runner and the full PostgreSQL integration file, using only the designated disposable invented-data service and unique fixture schemas. Ruff lint and formatting pass for all seven scoped Python files; strict mypy passes all seven. `git diff --check` passes; normal/ignore-CR numstats match. No additional runtime behavior change was necessary after the implementation owner's native-only fix; my runtime edit only formats the existing timed-runner exception. No new RED/runtime pair is claimed for tests added around already-correct behavior; postcommit fault checks remain root-owned.

Evidence: `var/verification/2026-10-16/daily-pilot-ledger-green.log`; final frozen source/test manifest `var/verification/2026-10-16/daily-pilot-ledger-hashes.json`. Protected `goal.yaml` remains `c886aca6b198257486d0daefc484f818458e60fa32a5aa861b95d1413282fa0c`; the old migration remains unmodified.

Current disposition: **GO to root's independent final review and postcommit verification**. No remaining ledger-scope code finding. This does not approve actual data admission or strategy evaluation.
