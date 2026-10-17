# Independent daily-data qualification review — 2026-10-17

Status: **GO for the bounded source-QA evidence, reviewed calendar, and narrow action-admission implementation; no overall data-admission or actual-run GO.** Scope is the finite D55/D59 source-QA method for the already frozen 257-session daily bundle. The seven-card runner is already built; this review neither repeats its build nor activates a ledger. Provider questions remain UNSENT.

## Review scope and requirements

Standards: AGENTS.md, OPERATOR.md D55–D60, current docs/STATE.md, and the ranked qualification findings in `2026-10-15-kite-data-qualification-audit.md`. Specification: `docs/plans/2026-10-16-daily-descriptive-pilot.md`, its implementation amendment, the runner runbook and the frozen source inventory. The matt-code-review standards/spec separation and delegation evidence discipline apply.

Required finite boundary: 252 warm-up sessions plus the fixed five decision dates, 2022-12-26–30; all 693 requested labels retained. Raw data QA must use UID10002/network-none, read-only source/code mounts, no credential/SDK/socket access and a dedicated output directory. Decode only the pinned pre-2023 interval. Validate dates before numeric conversion, exact schema/duplicate/null/domain rules, exact decimal raw/cache agreement, complete per-label dispositions and original-basis 20-session eligibility. Actions, PIT identity/class, calendar, availability and source-use remain separate admission predicates; a clean payload comparison cannot establish them.

Actual-study decoding/evaluation remains a separate gate: qualified package, separate authorization and all seven native counted reservations before actual-study price decoding. Data-plane source QA creates no strategy result or trial. Do not edit qualification booleans to manufacture admission.

## Independently reproduced baseline

Read-only PowerShell inspection of the frozen metadata on 2026-10-17 reproduced 257 unique dates, 252 before 2022-12-26 and five decision dates; 257 raw-file entries, 257 cache-file entries and 693 requested records. Source inventory SHA-256 is `191008c1b34c4a9b88285c0758d1725b8dca65555e96d16bbcbd09f313d10a7a`.

The first required date, 2021-12-21, has raw ZIP size 80,517 bytes and cache size 119,424 bytes; fresh hashes match their inventory pins. This is an independent file/count check, not payload qualification. No market payload was decoded by this baseline check. The inventory's calendar-qualified flag remains false and its certificate hash is `4d7902c85909cba50b00dfccd6c0d3b1051225ba547e33bc010b56ad0e683c91`.

## Finite helper-plan decision

**GO for source-QA helper implementation, invented fixtures and the stated confined decode only.** The source reviewer proposes a standalone helper bound to the exact inventory, 257 raw ZIPs, 257 schema-2 caches, requested labels, calendar, goal and existing reviewed `screen.py`. It verifies pins/sizes/hashes before and after, single ZIP member/header/date, duplicate EQ keys and JSON keys, finite numeric domains/OHLC ordering, exact raw-EQ/cache key and six-field agreement, and the five inclusive 20-session screens. Output contains counts/reasons/hashes, not strategy metrics.

Clarifications supplied before execution: prescan every source row's date before numeric conversion or EQ selection; never extract ZIP paths; reject nonfinite/bool numeric values; cover wrong/2023 dates, duplicate keys, malformed/null/domain values, field mismatches and altered pins with invented tests. Existing `screen.py` silently filters invalid/sub-unit rows, so the strict new validator must run first and retain any genuine failure. Its conditional alias screen is not a distinct-security/PIT certificate: retain conditional status and shared alias ownership rather than relabelling the output as final eligibility. No source predicate may be loosened silently to obtain a pass.

## Pending finite review

Source-QA method/evidence and action/PIT/calendar review are recorded below. Rights disposition is owned by the root reviewer and must not be inferred here. No runtime edits, actual strategy evaluation, ledger operation, provider contact, broker access or 2023 price access were performed by this reviewer. Invented tests wrote only the root-authorized dedicated temporary directory and test log.

## Standards finding: unresolved-action lookbacks

**P1, confirmed — do not treat the existing panel quarantine as a complete unresolved-action admission guard.** `icarus/engine/panelbuild.py:513` clears membership only through the event/gap index (`tradable[i, :cut + 1] = False`). An independent invented four-row fixture with an unpriceable Rights event at index 1, constant valid OHLC and initially true membership returns `[false, false, true, true]`. Immediate re-entry is therefore possible while a longer indicator window still crosses the unresolved economic-basis event. This reproduction invokes only `_quarantine` on invented arrays; it performs no strategy evaluation or market decode. The first invocation lacked the required `ActionHistory.frm/to` constructor fields and failed before running; the corrected invocation produced the stated result.

Finite remedy for qualification: bind unresolved events to the actual required lookback interval, retain affected labels with explicit counted reasons, and refuse contaminated indicator windows. Choose and freeze the per-card or shared conservative lookback policy before evaluation; do not fit a factor or silently reclassify action uncertainty as missing history. A new action-specific disposition may require a narrow separately reviewed runner status extension. The finding does not require rebuilding the verified runner or changing its seven-evaluation/ledger boundary.

## Action-method decision and independent reproduction

**GO for the finite common-252-session admission helper and explicit `ACTION_UNRESOLVED_LOOKBACK` reason.** Preserve each original price/liquidity status alongside the action reason and all 693 labels. The settled rule requires 252 strictly post-event prior sessions, excluding the decision day: for event index `e` and decision index `d`, release requires `d - e >= 253`. At 252 the `roc(252)` input still reaches the quarantined event bar. Test both boundaries, multiple events and dated identity transitions on invented fixtures; other qualification gates remain necessary after this guard passes. Bind the reviewed action/PIT evidence hashes into the eventual qualification package. No general framework, broad panel rewrite, inferred factor or rights waiver is needed.

Independent metadata-only read of five exact action caches (`actions_20211001_20211231.json`, then the four 2022 quarter caches under `var/corpactions/`) reproduced **784 requested-label EQ rows, 784 unique full rows, zero exact duplicates** within the required interval. It reproduced the unresolved MOTHERSON demerger (2022-01-14), WOCKPHARMA rights (2022-03-08), PEL demerger (2022-08-30), AARTIIND demerger (2022-10-19) and NMDC demerger (2022-10-27).

Material independent case: the Q4 cache, SHA-256 `657854c81963adaba6993d55629b4d72ace00326ab81dd5848fa79d8c9063c42`, contains EASEMYTRIP Bonus 3:1 plus face-value split 2 to 1, both ex-date 2022-11-21. Those terms imply a combined divisor `(1 + 3) * 2 = 8`, independently of any price comparison. The pinned dated matrix `var/kite-qualification/2026-10-15/dated-identities/output/dated-identity-matrix-2021-2022.json`, fresh SHA-256 `4c85773e03d015ddaf5c06d06d27abbf7e95e0b15f34414b84d2558e873b3ba6`, records `INE07O001018` on November 18/21 and `INE07O001026` on November 22/23. This reproduces the dated evidence, not historical provider-token continuity or exact publication time. The action agent corrected an initially mistyped inventory path/hash; this review relies on the exact cache and matrix bytes above, not that mistaken pin.

## Implementation review corrections

- Source helper: reject duplicate CSV headings and row-width drift before `DictReader` can silently overwrite/omit values. Compare valid raw/cache fields as exact Decimals, not textual spellings (`100.00` and `100` are numerically equal). These were sent as finite corrections before final helper review.
- Source domain: the original proposal requires finite, positive, ordered OHLC. A sub-unit quote can be physically valid source data while failing the unchanged research minimum. **GO for separating source `>0` validation from the research `>=1` screen**, retaining the first failed receipt and explicit research-excluded counts/reasons. The screen's pre-parsed `(close, turnover)` path bypasses its six-field validator; enforce the existing research sanity test before taking that path. This must not admit sub-unit history merely because the decision-day quote later exceeds the goal floor.
- Action helper: initial off-session handling counted the first effective event session as clean. Corrected code maps the ex-date to the first reviewed session at or after it and counts only strictly later prior sessions. It also refuses decision dates absent from the supplied axis. Independent focused rerun: `python -m pytest tests/unit/test_daily_pilot_admission.py -q`, **5 passed in 0.12s**. Final integrated qualification review remains pending while the worker completes binding changes.

## Bounded calendar — GO

Independently read the four saved primary PDFs with the bundled `pypdf`: CMTR46623, CMTR50050, CMTR50560 and CMTR54023. All four fresh byte hashes match the certificate's observation pins. The 49 observations comprise 37 annual closures and 12 special-session components; the closure-table split is **27 weekday and 10 weekend rows**. The historical-calendar narrative's 28/9 split is a documentation typo; certificate data and primary PDFs agree on 27/10.

Independently applying weekday baseline minus official closures plus the explicitly overriding Muhurat sessions reproduces exactly the 257 inventory dates from 2021-12-21 through 2022-12-30. In-scope 2022-10-24 has the source-supported six separate components, with normal trading 18:15–19:15 and explicit precedence over annual closure row 11. The February 2021 outage and earlier-history gaps fall outside this required interval. No specific unresolved calendar issue remains for this bounded daily model. The unchanged certificate's `calendar_qualified:false` denotes its earlier evidence-only state; a later reviewed admission may bind that same immutable certificate and this scoped review. This does not qualify all 2011–2022 history or exact intraday publication times.

## Final source-QA evidence — scoped GO

Reviewed helper SHA-256 `bda4fd02f1ca33a8ecbc3bd3efae2ca54b4f43d85b503f1b2283f8444080c635` resolves the CSV, Decimal and research-floor corrections. It invokes the original pinned `validate_cache` before eligibility screening, preserving the existing research minimum. The first failed receipt remains retained; no real quote was repaired and no research threshold was reduced.

Freshly hashed v2 receipt `var/daily-descriptive-pilot/2026-10-17/source-qa/evidence/source-qa-v2.json`: 899,561 bytes, SHA-256 `1d3a3628dd586ed3984760dc67955166f5f53b30968b5e90d0af9a2d4fe2481b`. Independently summing its per-session records reproduces 257 aligned sessions, 576,443 raw rows and 453,808 raw EQ/cache/Decimal-aligned rows, zero issues. It records 330 positive sub-unit rows in each source as research-sanity exclusions, and 525 identical before/after source/control states. This reviewer inspected implementation, reran invented tests and reconciled the receipt, without duplicating the complete market-payload scan.

All five dates independently reconcile to 693 unique labels. Counts in order below-close / below-turnover / fixed-income / conditional-qualifies / missing-window are: December 26 and 27 `15/335/1/235/107`; December 28 `14/341/1/230/107`; December 29 `15/342/1/228/107`; December 30 `15/342/1/229/106`. These are source-screen counts before final action/PIT admission, not strategy selections or returns. Both `data_qualified` and `run_authorized` remain false.

## Narrow action contract — scoped GO

The qualification loader now requires exact action-manifest and PIT-identity pins plus the exact five unresolved-action records, derives effective statuses itself from retained original screen statuses, and binds/emits both status sets. The exact qualification keyset refuses old documents lacking the new provenance. Source manifest bytes independently hash to `b67a2566a7df9455b4709210be69037040aebce04028ee4f1264566ba9c8e5d6`. Invented runs remain separate; all 693 labels and seven reservations before actual-study decode remain enforced. An explicit legacy-document regression was requested in addition to the reviewed keyset check.

Independent combined check: admission helper, daily pilot and source-QA unit modules, **46 passed in 15.64s**. Log: `var/verification/2026-10-17/daily-qualification-review-tests.txt`. Earlier runs failed in pytest setup because the sandbox temp directory was unavailable, then because the explicit temp parent did not yet exist; neither reached affected test assertions. Creating the authorized parent and rerunning outside that temp limitation produced the reported pass.

Standards: one confirmed historical quarantine limitation, addressed for this pilot by the new admission guard; implementation review corrections resolved. Specification: no remaining scoped implementation finding. Overall qualification still needs the concrete final panel/action/PIT composition and root's separate source-use disposition; no booleans or test passes grant actual-run authority.

Final source-only rerun after the worker's two additional tests: **22 passed in 0.12s**, log `var/verification/2026-10-17/daily-source-review-final-tests.txt`. The source worker's run-envelope records pinned image, UID10002/network-none/read-only mounts and the retained original failure; this reviewer read it and verified its result/code bindings against the inspected artifacts.

## Finite panel-preparer plan — GO for invented implementation

The existing general `build_panel` drops never-tradable symbols, so it cannot directly satisfy this pilot's 693-row contract. A narrow preparer is necessary: retain all 693 ordered labels across 257 sessions, represent missing cells as NaN/false, use exact dated symbol/ISIN cells bound to corrected raw identity evidence, refuse unproved aliases/shared same-date identities, and compute the existing raw `_membership` before any action adjustment. Keep LIQUIDBEES false for every session, not only the final five. Independently reconcile final-five original screen statuses before applying action reasons.

Reuse the existing adjustment and NPZ interfaces with pinned deduplicated/compounded split/bonus events; unresolved actions require the reviewed clean-lookback guard. An unexplained residual gap must cause explicit refusal rather than relying on the old event-day quarantine. Invented tests must prove no double adjustment, missing-cell preservation, all-label roundtrip, exact dates, provenance refusal and write-once output. The pending packet binds source/action/PIT/calendar/transform and encoded/decoded panel hashes while leaving rights/admission/run flags false. No actual panel emission, simulator call or ledger operation is authorized by this plan review. This closes avoidable software preparation while source-use and actual-run authority remain separate.

### Initial preparer implementation — REVISE

Reviewed frozen preparer `716326009498bb32620a8d779281e28c0f8a16162194a34621a7034996b69e05` and tests `9273566b4280a9c5bfddf7c6a26b5811bd2301a3d79a4249f1c69313366db4de`. Four finite corrections were sent before final acceptance:

1. **P1 Standards:** `_quarantine` returns one latest cut per symbol; checking only that cut against known events can hide earlier unexplained gaps. Independently reproduced with invented 100-to-50 prices at index 100 and a known unpriceable event at index 200: preparation succeeds and reports one allowed quarantine. Inspect every consecutive-present adjusted gap and allow only the exact explicitly unresolved effective event edges.
2. **P2 Spec:** 257 dates plus the last five dates does not establish the fixed full axis. Check the complete reviewed session identity hash, not just length/order/end.
3. **P2 Spec:** comparing admitted booleans cannot distinguish a false `BELOW_CLOSE` from `MISSING_WINDOW`. Reconcile exact source-screen reasons with the fixed raw-window rules, preserving reason precedence.
4. **P1 Spec:** refuse priceable actions during the five pilot sessions. The reviewed concrete sources contain none; an in-holding share/action model must not be implied by accepting them.

The pure preparer correctly labels its pins as unverified caller declarations and actual emission as unsupported. An actual source-binding wrapper remains unimplemented at this checkpoint. It can be built/tested on invented fixtures while actual emission remains held; no claim that only external blockers remain is justified until that software exists.

### Transient composition-QA scope — GO under D55/D61

After rereading the literal current decisions, **a reviewed transient binder/preparer run is already authorized as source QA**. D55 explicitly includes bounded offline adjustment-consistency checks; D61 continues real daily qualification and action/identity/calendar binding. Computing adjusted arrays and membership in memory solely to check composition is data-plane QA, provided no strategy indicator, simulator, metric, ledger or authorization path runs. Output must be limited to counts, pins, dispositions and refusal reasons; never call NPZ publication or emit price arrays.

This resolves the earlier broader implementation hold on all actual invocation: the hold still applies to durable actual-panel emission and actual study. The transient check requires frozen reviewed code, passed invented failure tests, exact pre-2023 input/code mounts, UID10002/network-none/read-only confinement, no credentials/SDK/socket, bounded resources, before/after source hashes, all-693 accounting and retained failures. Source-use resolution remains separate, and no `DATA_QUALIFIED` or `RUN_AUTHORIZED` claim follows.

### Final preparer/binder implementation — scoped GO

Frozen preparer SHA-256 `d6dd5608c3416eca8c82a93597295bf95c874080188b4a0b5943010fcce1becf`; tests `4375c1ec41bd0d388e4e04f9bf7a0434aa02ad24b5e02259499ced19e8ea4d88`. Both hashes remained unchanged before/after the independent regression. The four initial findings are resolved: all consecutive-present gaps are checked; complete axis/label digests are required; exact source reasons are derived; pilot-session priceable actions refuse. Positive sub-unit source cells retain observed identity/counts while research arrays contain NaN and membership remains false. They are not misreported as source absence.

The binding wrapper now exists. It verifies all 514 raw/cache file pins plus selected controls/action files before and after, checks the QA receipt's full scope and source/control bindings, binds the caller universe to pinned goal bytes, derives actions and dated identities, validates and applies every relevant raw-ISIN override, and returns an in-memory panel with a byte-verification receipt. Duplicate JSON keys and malformed/aliased conflict overrides refuse. Pending publication retains all 693 raw/effective dispositions and never grants policy admission.

Final review order followed OPERATOR §5/§5b: **ponytail-review simplicity first** (no unnecessary abstraction/dependency deletion identified; lean for the stated scope), then **engineering code-review** with matt-code-review Standards/Spec axes, then the **admission safety-boundary view**. The named `security-review` skill was absent from installed skill roots; the security dimension of engineering code-review covered path containment, pin integrity, parsing, publication, credential/network/ledger boundaries and honest flags. No unavailable skill invocation is claimed.

Safety result: paths resolve inside the selected root; source bindings are checked before use and after preparation; no evaluator, strategy, ledger, network or authorization function is called by the preparer/binder. `source_pins_verified=true` denotes successful byte/derivation verification only, while all data/source-use/run policy flags remain false. Imported engine definitions do not themselves run a strategy. Actual NPZ publication remains held; root may run the bounded transient QA described above.

Independent final regression across preparer, admission, pilot and source-QA modules: **66 passed in 24.34s**, log `var/verification/2026-10-17/daily-preparer-review-final-tests.txt`. Root's commit followed by actual-defect mutation checks and exact restoration remains a separate next verification step; this review does not pre-claim that result or a successful real-source composition check.
### Final resource delta — scoped GO

Final frozen preparer `101e301860ac06212a59a2c147b7f5a7aaadbc23f7a7e897839e7e2e4439fb84`; tests `e35c115640af29e4d586656f2bb0c3dc6dcb4b9f1acc364188f19502e50d6e4f`. Reviewed the final delta: every cache row still receives shape/canonical-symbol validation, while only pinned requested-label rows are retained in memory. Full source-file hashing and source-QA binding remain intact. Earlier hardening rejects duplicate QA state paths and validates requested action rows after filtering out unrequested actions. Independent focused regression: **15 passed in 11.44s**, `var/verification/2026-10-17/daily-preparer-review-delta-tests.txt`. These final hashes supersede D6DD/4375 above. Scoped GO remains limited to preparation software and the previously described transient composition QA; actual study and policy qualification remain held.
### Postcommit defect proof — PASS, exact restoration verified

Root authorized an exclusive mutation window after source commit `c92074d8abd24a784d5af1b7fbb7397aa8e85b49`. The var-only harness verified HEAD and committed source before mutating one anchor at a time, used a distinct fresh bytecode directory for each subprocess, and restored exact in-memory original bytes in per-case and outer finally blocks. No checkout/reset was used.

Ten distinct faults produced substantive focused failures: hidden earlier discontinuity; missing full-axis pin; missing exact source reason; source-observed subunit conflated with invalid research price; pilot-date priceable action admitted; decision day incorrectly counted as clean prior history; source QA minimum changed to one; duplicate CSV heading allowed; text equality substituted for Decimal equality; file-pin verification skipped. Logs and source-before/mutant hashes are retained under `var/verification/2026-10-17/daily-qualification-mutations/`.

The original axis and pilot-action fixtures initially failed by expected-error regex mismatch because secondary checks still refused. Those were not claimed as behavioral escapes. Two stronger var-only fixtures supplied a consistently remapped source axis and a price-consistent split; both passed under restored source, then each failed **DID NOT RAISE** with its single guard disabled. Evidence: `daily-qualification-mutations-strengthened/`, with fixtures `test_qualification_mutation_controls.py` in the same verification date directory. This is ten distinct faults, twelve retained mutant runs, and two green strengthened controls.

All three mutated source hashes were verified restored: preparer `101e301860ac06212a59a2c147b7f5a7aaadbc23f7a7e897839e7e2e4439fb84`; admission `9448b929d6213f4f1915ec3a6ee5320202cfeb4ddad6cdf659d1d463181de507`; source helper `bda4fd02f1ca33a8ecbc3bd3efae2ca54b4f43d85b503f1b2283f8444080c635`. Prepared tests remained `e35c115640af29e4d586656f2bb0c3dc6dcb4b9f1acc364188f19502e50d6e4f`; no runtime/test/script git diff remained. Both receipts report every protected source restored. Root received MUTATIONS RESTORED before any transient actual-source QA mount.

Final post-restoration fresh-bytecode regression: **66 passed in 26.42s**, log `var/verification/2026-10-17/daily-postmutation-fresh-tests.txt`. Scoped software-review GO; real-source composition outcome and source-use decision remain separately evidenced gates.
### Real-source transient composition receipt — scoped GO

Independently read metadata only and verified receipt SHA-256 `0917d707f27413a618a3e2249a7991bcc2ef97321ba99b17a196e3c0c0bb5430` at `var/verification/2026-10-17/daily-action-composition/composition-receipt.json`. Exit 0, no error/stderr, all fourteen confinement checks true. The before/after stage summaries are exactly equal: 623 files, 157475667 bytes, digest `2f2597ce49c9b1f02abcb9150c2289e28fc73da7ea3243b73cf9fa14d76317c2`. Peak RSS is explicitly unavailable/null; the configured hard memory bound must not be described as measured use.

Independently matched every one of the 3465 raw-status cells to the frozen source-QA receipt and independently derived every effective status using the five unresolved labels plus the narrow LIQUIDBEES class rule. All 693 unique labels remain on each date. Effective counts below are in the order ELIGIBLE / BELOW_CLOSE / BELOW_TURNOVER / MISSING_WINDOW / ACTION_UNRESOLVED_LOOKBACK / CLASS_INELIGIBLE_FIXED_INCOME:

- 2022-12-26: 232 / 15 / 333 / 107 / 5 / 1.
- 2022-12-27: 232 / 15 / 333 / 107 / 5 / 1.
- 2022-12-28: 227 / 14 / 339 / 107 / 5 / 1.
- 2022-12-29: 225 / 15 / 340 / 107 / 5 / 1.
- 2022-12-30: 226 / 15 / 340 / 106 / 5 / 1.

The action guard retains AARTIIND and WOCKPHARMA raw BELOW_TURNOVER reasons and MOTHERSON/NMDC/PEL raw CONDITIONAL_QUALIFIES reasons while counting all five explicitly as action-unresolved. LIQUIDBEES retains its original conditional source status and becomes class-ineligible; BANKBEES/NIFTYBEES remain ordinary BELOW_TURNOVER outcomes. The receipt's raw conditional totals include LIQUIDBEES, explaining the one-count difference from earlier class-adjusted QA summary totals.

The observed/absent identity accounting independently sums to 178101 = 693×257: 150215 observed plus 27886 absent. Receipt evidence reports 526 verified files, 514 source files, 185 exact raw-ISIN overrides, 31 priceable rows/29 cuts, zero priceable pilot-date actions, five known unpriceable quarantines and zero requested research-subunit exclusions. Thus the 330 global source subunit rows did not affect requested panel cells. These are composition-QA facts, not strategy outcomes.

Final scoped verdict: **GO for completed bounded source/action/PIT/calendar composition QA; no remaining observed software composition defect in this fixed bundle.** The policy flags `data_qualified`, `source_use_authorized`, and `run_authorized` are all explicitly false. Source-use resolution and the subsequent authorized durable panel/qualification publication and native seven-card reservation/run sequence remain gates; no NPZ, strategy evaluation, ledger result, inferred permission or actual-study readiness is claimed by this review.
