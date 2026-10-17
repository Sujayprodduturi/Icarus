# Daily pilot corporate-action, identity, and calendar QA — 2026-10-17

## Disposition

The bounded metadata prerequisites for the NSE-only daily pilot are reproducible for **257 sessions from 2021-12-21 through 2022-12-30** and **all 693 requested stock labels**. The pure preparer, source-binding wrapper, and one exact-whitelist transient composition have passed scoped review. The transient run composed the 257×693 panel in memory and emitted no NPZ or study result. This does not qualify the data or authorize a run: the evidence-bound qualification document does not exist yet, explicit source-use authorization remains open, and actual-study authorization is a separate later gate.

The machine-readable record is `var/daily-descriptive-pilot/2026-10-17/action-qa/qa-summary.json`. Its selected-source manifest is `var/daily-descriptive-pilot/2026-10-17/action-qa/source-manifest.json`, SHA-256 `b67a2566a7df9455b4709210be69037040aebce04028ee4f1264566ba9c8e5d6`.

The transient composition receipt is `var/verification/2026-10-17/daily-action-composition/composition-receipt.json`, SHA-256 `0917d707f27413a618a3e2249a7991bcc2ef97321ba99b17a196e3c0c0bb5430`. It records 693 labels × 257 sessions, 150,215 observed and 27,886 explicit-absent cells, all 185 PIT overrides, 31 priceable action rows/29 cuts, zero pilot-date priceable actions, five known unresolved-action quarantines, zero requested-subunit exclusions, and a 7,302,141-byte in-memory panel. All 623 staged files were unchanged; every UID, network, mount, capability, resource, environment, and Docker-socket confinement check is true. Peak memory was unavailable and is recorded as null rather than inferred.

## Corporate-action result

The five pinned NSE quarterly caches contain **784 unique requested-label EQ action rows** on **497 labels** in scope. The existing official parser classifies **31 exact split/bonus rows on 27 symbols and 29 symbol-date cuts**, **748 benign price-return rows**, **5 unpriceable rows**, and **0 unrecognised rows**. Same-date events compound: BAJAJFINSV 2022-09-13 is `5×2=10`; EASEMYTRIP 2022-11-21 is `4×2=8`.

The admissible adjustment is the existing raw-NSE method: determine membership on raw values first; divide pre-ex OHLC by the cumulative exact later share multiplier and multiply volume; leave dividends raw under the frozen price-return convention. It does not use or assume a vendor adjustment factor. Rights and demergers have no admissible factor here.

None of the 31 requested-label priceable rows falls on the pilot decision/execution dates 2022-12-26 through 2022-12-30. The latest is SFL factor 2 on 2022-12-21, followed by BLS factor 2 on 2022-12-08 and EASEMYTRIP factors 4 and 2 on 2022-11-21. Every exact adjustment is therefore warm-up-only for this bounded run; no in-holding split/share-quantity or fee-timing model is needed for these five dates.

The unresolved rows are MOTHERSON demerger 2022-01-14, WOCKPHARMA rights 2022-03-08, PEL demerger 2022-08-30, AARTIIND demerger 2022-10-19, and NMDC demerger 2022-10-27. Their strictly post-event prior-session counts on the five decision dates are respectively `233..237`, `198..202`, `79..83`, `45..49`, and `40..44`. All remain inside the frozen common 252-session prerequisite.

The runner now derives `ACTION_UNRESOLVED_LOOKBACK` rather than reusing `MISSING_WINDOW`. It retains all 693 labels, binds the original source-screen status separately, maps an off-session event to the first source session on or after the ex-date, and releases only when 252 later source sessions have completed before the decision. The existing event-day-only panel quarantine was insufficient because it allowed immediate re-entry.

## Point-in-time identity result

The pinned 99,347,376-byte dated identity matrix, SHA-256 `4c85773e03d015ddaf5c06d06d27abbf7e95e0b15f34414b84d2558e873b3ba6`, covers the full bounded denominator: **178,101 requested label-session cells**, comprising **150,215 observed** and **27,886 explicit absent** cells. Its later corporate-action association conflicts with raw trade-date ISIN in **185** in-scope cells. The build must apply the matrix's bound `raw_isin` conflict sidecar without rewriting the pinned source.

After those 185 overrides, exactly eight raw ISIN transitions remain: BAJAJFINSV, EASEMYTRIP, IPCALAB, JUBLFOOD, SAREGAMA, SCHAEFFLER, TATASTEEL, and VTL. Each transition is on the session after an exact saved split/bonus edge. Across all observed cells there are **zero same-date shared-ISIN label groups**.

The source-QA receipt `var/daily-descriptive-pilot/2026-10-17/source-qa/evidence/source-qa-v2.json`, SHA-256 `1d3a3628dd586ed3984760dc67955166f5f53b30968b5e90d0af9a2d4fe2481b`, reports non-fixed-income conditional counts `235,235,230,228,229`. All **1,157** of those cells join to exactly one dated raw EQ symbol and non-null ISIN in the corrected matrix, with **0 missing links and 0 shared-ISIN collisions**. LIQUIDBEES is the five-cell fixed-income exception; its original `CONDITIONAL_QUALIFIES` status remains recorded before the class disposition.

A final read-only precedence cross-check compared every pilot disposition with exact dated presence over its inclusive 20-session window. All **3,465** label-date cells agree: `MISSING_WINDOW` counts are `107,107,107,107,106`, with **0 mismatches**. The decision-day identity itself is absent in 96 cells per day; another **54** cells across the five dates are present on the decision day but miss an earlier window session. This proves the preparer must keep missing-window precedence ahead of close and turnover reasons rather than treating current-day presence as a complete window.

For the five unpriceable labels, the raw source-screen status on every decision date is `CONDITIONAL_QUALIFIES` for MOTHERSON, PEL, and NMDC, and `BELOW_TURNOVER` for WOCKPHARMA and AARTIIND. The effective action disposition is `ACTION_UNRESOLVED_LOOKBACK` for all five dates. Thus the guard changes admission materially for three labels and preserves an explicit causal reason for the other two.

## Calendar result

The bounded calendar certificate SHA-256 `4d7902c85909cba50b00dfccd6c0d3b1051225ba547e33bc010b56ad0e683c91` independently reproduces **252 warm-up plus 5 decision sessions** and all four saved official source-PDF hashes. The only special session inside the requested interval is 2022-10-24. The older source inventory still says `calendar_qualified=false`; persisting this accepted bounded review in the final qualification is an administrative build step. The reviewed annual decomposition is 27 weekday closures and 10 weekend overlaps; the older narrative's 28/9 wording is a typo and must not be copied.

## Exact remaining blockers

1. No technical action, PIT-identity, bounded-calendar, or transient-composition blocker remains for this 257×693 input. The reviewed path retains every requested label and explicit absence; the existing full panel builder's drop-never-tradable path remains inadmissible for this pilot.
2. Obtain explicit source-use authorization. Until then, `data_qualified=false` remains correct.
3. After source-use authorization, emit and review the evidence-bound qualification contract and write-once panel artifact with raw and effective statuses, panel digest, and bound source-inventory, calendar, action-manifest, and PIT-matrix hashes. Legacy qualification JSON remains rejected.
4. Actual-study authorization remains a separate later gate after data qualification. `run_authorized=false` remains correct; the transient composition did not run a strategy, compute a metric, or activate a ledger.
5. Provider questions remain **UNSENT**; readiness does not authorize contact, and any future contact requires a new explicit instruction.

No additional corporate-action ratio, historical token, current-master alias, 2023 price, network fetch, provider contact, evaluation, metric, ledger, broker, or strategy work is needed for this bounded action/PIT/calendar determination.
