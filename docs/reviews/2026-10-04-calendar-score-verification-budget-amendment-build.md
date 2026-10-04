# Operational verification budget amendment build

Approved implementation plan SHA256:791c0a23b43dce002d6ecbeeccf610a679f91ae63f22d6561f6a35fc226c4849. Source/config integration is built; effective workload qualification remains pending source review and three fresh governed runs. All previous12-hour failures remain evidence.

The canonical operational contract has exactly two chained entries. Immutable baseline12h digest:e13f6e229442c07edd5f559c878a2c5a1a176080f1c3d7f963914cc63dbd4434. The14h acknowledgement is explicitly post hoc, authored at actual captured2026-10-04T17:14:00Z and binds the approved proposal plus preserved iteration2 three-run summary. Whole-file pin:8a2225727e08cb7eb848e46ab856eca5649d727c15a101f0ab1bb3d9a1d313bc. The production loader has no CLI/environment override or absent-contract fallback; the private test seam requires an explicit expected digest.

The shared loader caps reads at16385 bytes, checks canonical/exact schema, immutable baseline, whole pin, UTC-aware timestamp, history and actual bound evidence hashes afresh. Its frozen scalar snapshot returns a fresh serialized binding; comparisons use the validated JSON seconds. Source closure includes the contract/proposal/approved plan and referenced benchmark summary. Statistical protocol/stream/worker6h12h/counts/caps/safety factor remain unchanged.

Success envelopes carry operational_resources and readers strictly validate canonical bytes before existing schema comparisons. Index rows are transitively bound through claim_digest; existing preflight rows bind directly. Preflight plans/claims/receipts/terminals/cleanup and verifier fixtures/benchmark artifacts have explicit policy bindings. Preflight and independent benchmark projections retain named legacy/effective development/validation flags. The independent benchmark keeps complete conservative timing and600-second full-set supervision. Units2-3 remain unbuilt; no capability, reservation, experimental draw or phase authority was added.

Failure persistence uses captured original binding or explicit null/resource_contract_error and does not re-enter the loader or source manifest. Secondary failure persistence is attached to the original refusal rather than replacing it. Fixture write/verification and benchmark failure records retain this distinction. Inert candidate/no-overwrite publication remains intact.

TDD logs are retained under var/verification/2026-10-04/calendar-score-verify/. budget-red.log preserves initial absent-API/setup failures; budget-red-contract-present.log records18 absent-loader/API failures after actual contract creation. budget-artifact-red.log records2 meaningful missing binding/failure failures and3 already-refusing corruption cases. budget-failure-red.log records missing captured fixture failure evidence. budget-extra-red.log records huge integer projection OverflowError; bounded integer admission now refuses consistently.

Initial candidate focused GREEN:184 tests passed11.30s (budget-green-5.log), retaining prior SHA/word/rejection/overflow/receipt durability failures. Tests cover malformed/duplicate/noncanonical/unknown/type/history/ack/evidence/whole-pin corruption, fresh policy/evidence changes, exact43200/50400 boundaries and0.70-second oldfalse/newtrue distinction, fully rehashed contradictory artifact bindings, missing policy after guarded root creation and captured binding after drift. Strict mypy includes both source modules AND both test modules: clean (budget-mypy-final.log). Ruff check and format: clean (budget-ruff-final.log).

Initial candidate SHA256 (held by review):

- study source:c2a5055c0ecdfe7f4b0ec9d5c7c55353d80cc22e9e1df2bca6111673b723a8b3
- verifier source:dee76774e67c38075e2ee5f133218977e20f7c2e5e497c3efd14d58a039a1449
- study tests:9bac874930230fba23ccfe417bd80aada987b0e4fe7bc4fe526733a205229570
- verifier tests:7cb1079f4db3c9824fcb5e6f043329c9d0ae6d6b501a234e2829ac5abbed7824

No actual benchmark, broad regression, sampled stream, raw cleanup, commit or push was run by the builder. Root owns ordered review, global checks, all three new full saved verifications and guarded raw-only cleanup. Operational qualification remains pending; inference=false and Task3a/M1-M4/F48 remain OPEN.

## Review remediation and current freeze

Independent review found three blockers in the initial candidate: a rehashed preflight eligible=true was accepted despite failed resource comparisons; direct execute_preflight did not persist policy failure after its root guard; binding/existence errors in verifier failure persistence could replace the original refusal. No benchmark was authorized on that candidate.

budget-review-red.log records11 meaningful failures and1 already-passing open-denial case. The six receipt-corruption cases now carry an explicit expected plan; verification/generation mutations also rebuild consistent measured projections, making the composite-gate checks nonvacuous. Valid receipt intake succeeds, while omitted plan intake refuses.

The receipt reader validates complete scalar schema/types, counts/probe size, exact generation/replay-derived projections and fresh old/new comparisons, then independently computes the composite generation/verifier/RSS/free-space/cap eligibility and requires an exact bool match. Expected count comes from the original supplied plan.

Public execute_preflight retains validation/ancestor guards and then enters a captured-resource try/private-work boundary. Missing/corrupt policy creates durable null/error evidence; later drift retains the original binding. Verifier failure binding extraction, existence lookup and record write are all inside the secondary-error boundary. Regression tests deny exists/open/binding and assert the exact original exception object survives with an evidence-persistence note.

Current GREEN:197 focused tests passed12.29s (budget-review-green.log). After adding a known-valid eligible input assertion, all13 affected regressions pass1.09s (budget-review-affected-green.log). Four source/test strict mypy and no-cache Ruff/format pass (budget-review-mypy-final.log, budget-review-ruff-final.log).

Current source/test SHA256:

- study source:78fa9ea1041df6eddbe0f4f48cb61daacee4c2937d3aa45fe914f12b9c1269ed
- verifier source:40f40acd5096f69b52e7694317c67c2fd6213b543f02f7514d174385e569cb02
- study tests:5a1d3c0d0e6375904ba7c35ec562b31ef3ccedf5b99935c63de3ef7e8e8caa75
- verifier tests:a81aec072d1ab356c0554033d46d6d1b5ffc18c490747c3232ec19fa1b945bd4

Contract whole/base pins and frozen statistical protocol remain unchanged. Ordered source review, root global checks and new three-run qualification remain pending.

## Final supervisor boundary remediation

A further review found supervised preflight's exception branch still had process polling/termination, failure existence lookup and captured binding construction outside protected secondary-error boundaries. budget-supervisor-red.log records4 meaningful exists/binding/poll/kill failures replacing the original refusal.

Process polling/termination now has its own protected attempt; failure adds a termination note to the original exception. The entire following evidence branch, including existence/binding/payload/write, has a separate protected attempt. Thus cleanup failure does not prevent an evidence attempt. Tests assert exact original exception identity, absence of success and durable ERROR after polling/termination denial. No production source is mutated by these regressions.

Final focused GREEN:201 passed12.24s (budget-supervisor-green.log). Four-file strict mypy, no-cache Ruff and format are clean (budget-supervisor-mypy.log, budget-supervisor-ruff.log).

Final freeze superseding the source/test values above:

- study source:abd6f6cb7ff92802eebd1efa696b3a38bcb0080ff2c7f11009f2e970f4255231
- study tests:2be94e1913dea4f1cf82d1b18004eaa6ef6a9ad99be11dc853c82c6cba60c0c3
- verifier source remains40f40acd5096f69b52e7694317c67c2fd6213b543f02f7514d174385e569cb02
- verifier tests remaina81aec072d1ab356c0554033d46d6d1b5ffc18c490747c3232ec19fa1b945bd4

Contract/protocol remain unchanged. No benchmark/global regression/cleanup/commit/push was run by the builder; root owns remaining review and qualification.

## Root qualification and retained failure

Final approved source has517 related calendar/portfolio/synthetic-characterization/audit tests passing22.62s; strict170-source icarus/scripts-research/tests mypy and global no-cache Ruff/321-file formatting pass. Initial cached formatter panic is preserved in format-budget-final.log; no-cache succeeds. Configured156-source mypy also passes. Broader all-scripts176-source check separately reports pre-existing unchanged scripts/build_panel.py:118 missing tuple parameters, retained in mypy-budget-all-approved.log; no all-scripts-clean claim.

Three fresh declared cold runs cost0.7734873999870615/0.7692184000043198/0.7578426999971271s; effective verdicts false/false/true. Overall FAILED at worst50691.27024555206 seconds versus50400, with all legacy43200 validation verdicts false. The added fresh resource/provenance checks are measured, never excluded. No favorable minimum or automatic larger budget.

[Compact evidence](2026-10-04-calendar-score-verification-budget-amendment-benchmarks.json) retains ALL3 claims/runtime/source/resource bindings, full28 results, index, terminal, automated and primary/reviewer receipts, cleanup intents and absence receipts. Both independent scalar oracles reproduce all231492 bytes/1388952 words. Exact raw-only D44 cleanup complete after both receipts; no raw replay remains. One combined command was initially rejected because automatic approval had not seen reviewer receipts; separately inspected reviewer receipts, primary verification and explicit guarded cleanup resolved the objection. Source freeze held throughout.

Remote refresh:375d813 CI37219846934 and f3550cf CI37219178283/native non-reserved surrogate37219178314 SUCCESS; these are predecessor-source results, not current uncommitted-source CI or official-stream attestation. New operational contract changes resources only. Unit1 runtime gate and R3 remain FAILED/OPEN, Units2-3 UNBUILT, Task3a/M1-M4/F48 OPEN and inference=false. Further optimization requires a reviewed plan and fresh tests/benchmarks.

## Commit and post-commit verification

Implementation/evidence commitfc84af333fa0ba2c63c95818702a03ad8756671b pushed; HEAD=origin/dev confirmed. Three deliberate semantic defects (ignored whole-contract pin, retroactively upgraded legacy budget result, accepted contradictory receipt eligibility) were caught. Exclusive snapshots and finally restoration reproduce exact reviewed studyabd6f6cb/verifier40f40acd hashes. Fresh517 related regressions pass23.07s after restoration. No source fix remains uncommitted. Documentation-only provenance follow-up is exempt from another source mutation cycle. Current commit CI is not assumed.
