# Daily pilot build review — 2026-10-16

Scope: working tree based on `eb014f44cbec8195fdabf83d754e12712cd2aac3`, new daily-pilot runtime/CLI/tests plus narrowly extended trial-ledger geometry. Standards: AGENTS.md, OPERATOR.md, and the documented safety invariants. Spec: the reviewed daily descriptive pilot and implementation plans. Review is read-only except this report; no actual price payload, actual ledger, provider contact or network operation is used.

## Simplicity

No actionable complexity reduction identified in the first runtime inspection. Existing DSL, signal simulator and guarded runner are reused; the narrow ledger kind avoids fake folds and a second trial ledger.

## Standards — initial working-code findings

- **P1, `icarus/engine/daily_pilot.py:168` and `run_actual_daily_pilot`:** admission accepts caller-set qualification/source-use booleans and syntactically valid hashes without checking pinned evidence or binding its hashes to authorization. The fixture test constructs an alleged actual admission by replacing invented flags. The eventual actual interface must load and validate externally pinned evidence before ledger access; no self-certifying bypass.
- **P1, `DailyPilotPayload.__post_init__` and `run_actual_daily_pilot`:** decoder results are internally consistent but not compared with the admission passed to the runner. A different payload/admission can therefore be evaluated while reporting the first admission's dispositions. Compare exact session/label/disposition identity and eligibility masks before evaluation, after the complete reservation barrier; failure must fail the reserved set without publishing results.

## Spec — initial working-code findings

- **P1, `DailyPilotAdmission.__post_init__`:** count, uniqueness and endpoint checks do not pin the exact original 693 labels or reviewed 257-session calendar. Arbitrary synthetic labels and interior dates satisfy actual admission. Bind metadata to reviewed full-inventory/calendar identities; invented proof may retain its explicitly artificial axis.
- **P2, `_result_payload`:** count/value aggregates do not preserve individual executed-versus-marked fragment quantities, price-source/recognition dates and estimated charges, and skip reasons (including terminal `NO_NEXT_BAR`) are discarded. Emit the finite per-fragment and skip evidence required by the reviewed model without calling marked residuals executed sales or after-tax results.
- **P2, `tools/run_daily_pilot.py`:** current CLI exposes only invented proof/default-held status. The implementation plan promises a qualified, externally authorized actual-input route. Build the fail-closed route with injected invented contract tests; do not run actual source admission/evaluation during this build.

These are initial WIP findings sent directly to the builder/root, not a final disposition. Await frozen fixes and independent invented-test reproduction.

## Finite postcommit fault plan (not executed)

Run only after root confirms a source commit and freezes the implementation. Before any mutation: record committed revision plus SHA-256 and exact bytes of each runtime file; require source hashes to match the frozen review. Each mutant is a single surgical source-byte edit with a new unique `PYTHONPYCACHEPREFIX` and unique pytest temporary directory. Run only its named focused falsification test, capture the assertion/guard failure (not an unrelated import/setup failure), and restore bytes in `finally`. Re-hash every protected source after each restoration; run the retained focused positive gate at the end. No mutation, actual-source read or actual-ledger write has occurred in this review.

| Fault | Required focused falsification |
|---|---|
| Omit one frozen card/hash comparison | catalogue tamper test must reject wrong hash or altered seven-card identity before any reservation/decode |
| Accept 692 labels or replace an original label | evidence loader/admission inventory-identity negative test must fail before ledger |
| Skip source-manifest/qualification authorization binding | bound-evidence mismatch test must fail before ledger |
| Move shared decoder before complete reservation set | event-order test must observe no decode when reservation seven fails; earlier six stay counted failed |
| Pass full 257-row panel/columns to simulator | `test_indicators_use_257_rows_but_simulator_receives_only_five` must assert wrong simulator rows/source indices |
| Trust substituted decoded dispositions/membership | payload-mismatch and fixed-income tradability negative tests must fail reserved set before any evaluation |
| Drop canonical terminal skip detail | terminal-day signal report test must fail missing `NO_NEXT_BAR` disposition; no 2023 input is added |
| Count `STALE_MARK` as executed exit | mixed executed/marked report test must fail executed count, separate marked fragments/charges and dates |
| Fill benchmark/alpha or promotion | `test_inventory_and_invented_proof_run_exactly_seven_without_alpha` and report-field assertions must fail |
| Publish after a failed evaluation or overwrite old report | failure terminalization/no-output test or `test_atomic_publication_never_overwrites` must fail |

Exact names for new negative tests will be pinned from the frozen builder tests before execution; do not mutate a predicate without a retained test that proves its consequence. Existing simulator next-bar/strict-through mathematics are reused and are not re-mutated here.

## Ledger corrective final read

The frozen corrective ledger diff passes the independent source review. The original 20261008 migration is unchanged. The new deferred cardinality function preserves native/legacy separation and requires exactly one pilot row with ordinal zero, no fold, non-null span and the exact reset. The `count` negative case declares two rows and actually inserts two, so its rejection proves kind geometry rather than merely missing-row cardinality. Both Sharpe fields are forbidden for every nonportfolio result; portfolio results remain accepted. Activation, append-only, terminal and result-consistency triggers remain unchanged. Downgrade refuses before DDL when a pilot row exists, otherwise restores the prior functions/constraint without deleting history. Root independently ran the combined 70-test ledger gate against disposable PostgreSQL; this review independently inspected code and cases rather than claiming an additional database execution.

## Frozen core final review — scoped GO

All initial WIP findings are resolved in the frozen source. The actual metadata loader pins reviewed source/label controls, while `require_actual()` independently recomputes canonical date/label identity digests and evidence binding. Authorization binds qualification, panel file, goal, cards and the runner dependency closure. Decoded payload identity, pilot membership and full panel digest are checked before evaluation. The CLI rejects expired authorization before opening a ledger engine and rejects wrong panel-file bytes before price decoding. Detailed executed/marked fragment provenance and charges, terminal skip reasons and unavailable benchmark/alpha/promotion fields are retained. The tracked `config/daily_pilot_inventory.json` removes the invented path's dependence on ignored local control files; actual contract tests create only invented temporary metadata/arrays and patch their identity pins.

Independent verification matched all four builder freeze hashes: inventory `ba1086260c2e3709c3a99885df4da9687447ef93f27d2ecbb739a8727a34bb7d`, runtime `46a21d1b23565dc2d560665d70d17bf83dfea8bb29ee552a23979986f9905759`, CLI `3291176168d657f8f4e10ba35204f7cac253431e19876b47c162018bbb2b0fa9`, tests `55a4a616264660ed8bc897063e74a526fabe3d47ec8bd5fc9561cfbf5b6b1f20`. Ran the frozen pilot, timed-runner and trial-ledger unit union independently: **52 passed in 11.93 seconds** (`var/verification/2026-10-16/daily-pilot-independent.txt`). Initial sandbox temporary-directory denial was an environment setup error; the dedicated writable verification temp run passed. No actual-source payload or actual ledger was used.

Standards: zero unresolved findings. Spec: zero unresolved findings. **GO for this software milestone**, conditional on root's remaining global/static/clean-checkout gates and the explicitly postcommit fault/restoration proof. This does not qualify actual source use, source contents or an actual strategy run, and no provider questions were sent.

## Postcommit fault/restoration proof — PASS

After root committed source `e33cbcb45a7dc95765d404f82decad75b454006a` and explicitly authorized the proof, independently planted eleven bounded faults. All were caught by their intended retained assertions: card hash identity; original label identity; runner dependency closure; decode-before-reservation order; warm-up trading; accepting an ineligible panel; hiding terminal skip counts; reporting a stale mark as an executed sale; inventing alpha; overwriting an existing report; and accepting a qualification hash different from authorization. The last case has a retained invented-only local test with baseline PASS, mutant `DID NOT RAISE` failure, and restored PASS. It supplies direct authorization-binding falsification in addition to the closure test.

The eligibility fault deliberately disables both independent `from_panel` semantic-mask and panel-digest guards as one conceptual acceptance fault; disabling only the mask guard is still caught by the digest and would give a misleading regex mismatch rather than prove acceptance. The first receipt classifier expected the literal `AssertionError` for three short pytest traces that instead print `assert 0 > 0`, `assert True is False` and `assert 0 is None`. Those faults failed the intended assertions. Preserved `first-run-summary.json`, corrected the receipt against exact failed test names/assertions, and did not weaken tests or change production behavior.

All **212 protected committed runtime/config/tool/test files** were hash-checked after each restoration, with exact byte restoration in `finally`; protected tracked diff is empty. Every mutant used its own fresh Python cache and temporary directory. Fresh restored pilot gate: **19 passed in 13.99 seconds**. Committed/restored runner closure SHA-256: `2c8301d75839eaa08b9d26e9c3b69853036135d29a77e2a7e20f5128f87ec6d6`.

Evidence directory: `var/verification/2026-10-16/daily-pilot-postcommit/`. Final `summary.json` SHA-256: `c1692b039c92fee8b4980371fb601f95945e6ac62d9159c26671fd079a00bdc0`. Retained scripts: `prove.py` SHA-256 `903c8d3e4915e94f91ea7613e5314d16e2f2f23277a2fd982d4946305d76c84c`; `complete.py` SHA-256 `b5db2f19d1c1b95c9fdad3d951669118aa9cb3d0b13d3d88d160b2b7edec2410`; extra qualification test SHA-256 `ce0a3fa182f9c85c052159c0778fbbcc8929ea263bd658fcd0e76c769b293809`.

Final disposition remains **scoped software GO**: zero unresolved Standards findings; zero unresolved Spec findings. No actual price payload, actual ledger, broker path, provider contact or lockbox data was used. Actual-source qualification and run authorization remain separate held gates.
