# Pilot input coverage — 2026-10-15

Status: **conditional data-QA complete; not a strategy evaluation or final universe qualification**. `DATA_QUALIFIED=false` and `RUN_AUTHORIZED=false`.

## Plan before execution

Reproduce the existing point-in-time universe rule for each predeclared date from 2022-12-26 through 2022-12-30 using the 20 observed NSE sessions ending on and including that date. Freeze and hash only the 24 required pre-2023 daily cache files before decoding them. In a UID-10002, network-disabled, read-only container, require a requested label to be present on all 20 sessions, require its current-day close to be at least INR 30, and require the inclusive 20-session average turnover to be at least INR 500,000,000. Report only names, booleans and counts, preserve all 693 requested labels and unknowns, and distinguish current-Kite mapping gaps from unresolved historical identity, alias and instrument-class questions.

## Existing rule reproduced

`PointInTimeUniverse.as_of` and `engine.panelbuild._membership` both include the as-of/current day in the 20-session turnover window. Presence is required in every one of those 20 sessions. The close test uses the current day. Both thresholds use inclusive `>=` comparisons: average turnover at least INR 500,000,000 and close at least INR 30. For 2022-12-26 the window begins 2022-11-29; each later pilot date advances the window by one observed session.

The screen also mirrors the panel reader's fail-closed row validity rules before treating a symbol as present: six numeric fields, all OHLC values at least INR 1, nonnegative volume and turnover, and coherent OHLC ordering. It evaluates each observed symbol separately and does not bridge turnover history across aliases.

## Conditional result

All 693 requested labels remain in every daily result. Counts below are requested-label counts, not proved distinct securities.

| As-of date | Conditional pass | Current-day present mapping gaps | Mapping gaps conditionally passing | Other present mapping gaps: close / turnover / missing-window |
|---|---:|---:|---:|---:|
| 2022-12-26 | 236 | 58 | 16 | 3 / 34 / 5 |
| 2022-12-27 | 236 | 58 | 16 | 3 / 34 / 5 |
| 2022-12-28 | 231 | 58 | 17 | 3 / 33 / 5 |
| 2022-12-29 | 229 | 58 | 16 | 3 / 34 / 5 |
| 2022-12-30 | 230 | 58 | 17 | 3 / 34 / 4 |

Fourteen unresolved current-mapping labels pass the existing price/liquidity rule on all five dates: `ADANITRANS`, `GMRINFRA`, `GUJGASLTD`, `HDFC`, `HFCL`, `IBREALEST`, `IBULHSGFIN`, `IDFC`, `L&TFH`, `MCDOWELL-N`, `PEL`, `PVR`, `TATAMOTORS`, and `ZOMATO`. Five more pass on at least one date: `AMARAJABAT`, `IIFLWAM`, `LTIM`, `MOREPENLAB`, and `TV18BRDCST`. These 19 labels are the material current-mapping-gap priority set for this interval. In particular, `HDFC` remains in the fixed screen on every pilot date, so its retrieval gap is material rather than an issue confined to names the existing rule would reject.

Root intersected this 19-label set with the independently reviewed alias-retrieval packet. Thirteen have prepared modern-name candidates: ADANITRANS, AMARAJABAT, GMRINFRA, GUJGASLTD, IBREALEST, IBULHSGFIN, IIFLWAM, L&TFH, LTIM, MCDOWELL-N, PVR, TATAMOTORS and ZOMATO. Twelve match the current official NSE ISIN; IIFLWAM/360ONE does not. These are retrieval candidates only, with historical provider-token continuity still unknown. Six have no bridge in that prepared packet: HDFC, HFCL, IDFC, MOREPENLAB, PEL and TV18BRDCST. This does not prove their data unavailable or establish delisting; a current-series change or another dated mapping may require separate evidence. No authenticated alias request has been launched.

### Additional current-series metadata leads

The operator-side Kite MCP's read-only `search_instruments` lookup on 2026-10-15 supplies two further candidates: `NSE:HFCL-BE`, token 5620225, ISIN INE548A01028; and `NSE:MOREPENLAB-BE`, token 1266945, ISIN INE083A01026. Both currently have `series=BE` and `instrument_type=EQ`; both ISINs independently match their EQ-series observations in the sealed 2022-12-30 raw NSE metadata. This explains why an exact current NSE/EQ-symbol lookup did not resolve them. It does not prove unchanged provider-token history, make BE and historical EQ interchangeable, or qualify any old candles.

There are now 15 candidate retrieval routes among the 19 priorities: 13 prepared modern names plus these two series candidates. HDFC, IDFC, PEL and TV18BRDCST still have no prepared route; this is not a claim that historical data are unavailable. HDFC's prefix search returned 37 rows across two pages but only 27 distinct IDs: all ten first-page IDs repeat in the second page. The API claims final `has_more=false`, but that overlap leaves exhaustive unique coverage unproved. No exact `NSE:HDFC` appears in the captured rows. The other three searches returned final-page metadata without an exact ID. No substitute such as HDFCBANK or IDFCFIRSTB was selected.

Only identifier, symbol, series, class and pagination fields were retained in the metadata-only receipt, SHA-256 `73d40bed3cdd2d47bd67f904ada3d4cfd2257ebdf7ee32c2be9b459fa21666b5`, under ignored `var/kite-qualification/2026-10-15/current-series-routing/`. The receipt omits price/circuit fields. Icarus did not read or retain connector credentials; no historical-candle requests or broker writes occurred. The hosted connector remains an operator-side inspection tool, not a research-runtime dependency. The independently reviewed 25-symbol retrieval request remains unchanged; the two BE leads have not been added to or launched through it.

The full daily requested-label screen sizes are 236, 236, 231, 229 and 230. No qualifying observed symbol was shared by two requested labels on these five dates, but the result still refuses to emit a distinct-security count: historical lineage and instrument class remain unresolved, and absence of an observed overlap is not proof of distinct identity.

## Evidence and isolation

The 24 copied cache inputs total 3,247,885 bytes and were frozen before numeric decoding. Frozen-manifest SHA-256: `eb52b499bc90477823eab552ca1ed176ad0f7f47c5bcb583588747124d250925`; all 24 hashes matched again afterward. Request-label receipt SHA-256: `a88632590be0f8344e962e0b27179516e977161e113c59e9ef2f5d9748c25fd3`. `goal.yaml` remained unchanged at SHA-256 `c886aca6b198257486d0daefc484f818458e60fa32a5aa861b95d1413282fa0c`.

The implementation sources used to reproduce the rule were pinned as follows: `universe.py` `4dfb986cdc718a65c516d161dc6517f10e0c094c8e4e8a9bb2b0aab3ead06b09`, `panelbuild.py` `0c0b9ec0ddf2bda08b7baf2c8662a907cb586c07119f45b689883107b628d296`, and `nse.py` `437198d8b840a4e4e6072a3b0af8cee1bc973af5f452bc4b4eb91cdd0a04b1b2`.

Four invented tests passed before the real decode, covering inclusive threshold boundaries and current-day inclusion, one missing session out of 20, aliases/shared-symbol refusal, and source-schema/invalid-row failure. The actual screen ran as UID 10002 with network disabled, a read-only root, only explicit input mounts, all capabilities dropped, `no-new-privileges`, a 1 GiB memory ceiling and two CPUs. The result emits names, booleans and counts only; its SHA-256 is `e273f6c96c1cdab0edc685d7b689543b6eeba4503e147c90a0202a4696b46d3b`.

Root independently checked all 24 input hashes before decoding and recomputed HDFC's 20-session presence, inclusive turnover threshold and current close threshold directly from the frozen inputs, without importing the screening helper. All five dates pass, match the receipt's unresolved-mapping result, and retain all 693 requested labels. The separate probe used the same restricted offline container boundary and emitted only booleans/counts.

## Limits

This is a `CONDITIONAL_PRICE_LIQUIDITY_SCREEN`, not a final point-in-time eligible universe. Primary issuer 2022 factsheets prove `BANKBEES` and `NIFTYBEES` are equity ETFs and `LIQUIDBEES` is a fixed-income ETF; their disposition under the existing universe eligibility and cost rules remains open. Alias continuity and the 1,447 raw-trade-date versus opaque corporate-action ISIN associations also remain unresolved. No threshold, universe label, eligibility rule or source record was changed; no strategy, fill, return, P&L, trial-ledger, broker or lockbox evaluation ran.
