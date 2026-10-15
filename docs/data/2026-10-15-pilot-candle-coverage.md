# Pilot candle coverage — 2026-10-15

Status: **bounded data-QA complete**. `DATA_QUALIFIED=false` and `RUN_AUTHORIZED=false`. This check does not evaluate a strategy, returns, fills, or P&L.

Independent frozen v2 review is **GO for diagnostics only**; its retained repairs, source-pin checks and ten passing invented tests are recorded in the [final reconciliation review](../reviews/2026-10-15-final-dated-identity-review.md).

## Plan before execution

Freeze the accepted Kite M15 report, sealed content index, captured instrument master/request bindings, 693 requested labels plus the separately reported `NIFTY50` benchmark, reviewed 2021–2022 calendar certificate, and five already frozen NSE daily rows for 2022-12-26 through 2022-12-30. First select the exact accepted chunks and bind their manifest/raw sizes and hashes without decoding candle rows. Then run invented tests for the 25-start-label grid, duplicate/off-grid/missing labels, quarantined-chunk exclusion, deterministic mapping, unresolved-label retention, and whole-chunk refusal on any 2023+ timestamp. Only after those tests pass, scan the selected chunks in a UID-10002, network-disabled, read-only container with explicit mounts, dropped capabilities, `no-new-privileges`, at most 1 GiB RAM and two CPUs. Report expected, observed, unique, duplicate, off-grid and missing counts per label/date, with `NIFTY50` separate from the stock screen. Any paired daily/M15 source relations are descriptive diagnostics with unknown common basis; no tolerance, alias substitution, BE substitution, prices, returns, fills or strategies are emitted.

## Result

The fixed denominator is 694 labels: all 693 retained stock labels plus `NIFTY50` as a separate benchmark. Exact captured mappings selected 544 unique `ACCEPTED` chunks (543 stocks plus the benchmark); 150 retained stock labels remain `UNRESOLVED_MAPPING`. There were no selected quarantined chunks in these five dates. No alias, current-symbol, or BE-series substitution was made.

Each accepted chunk had the complete expected grid of 25 start labels on each of the five normal sessions. Across the full 694-by-5 grid, the counts are:

| Measure | Count |
|---|---:|
| Label/date cells | 3,470 |
| Accepted cells | 2,720 |
| Unresolved-mapping cells | 750 |
| Expected M15 rows | 86,750 |
| Observed rows | 68,000 |
| Unique rows | 68,000 |
| Duplicate rows | 0 |
| Off-grid rows | 0 |
| Requested-grid gaps | 18,750 |

All 18,750 requested-grid gaps arise from the 150 unresolved labels across five dates and 25 requested starts. This denominator preserves every requested label; it does not assert that historically inactive or absent labels required physical bars. The accepted chunks contribute no missing, duplicate, or off-grid rows. `NIFTY50` has 25 observed and unique rows on each date, with zero duplicate, off-grid, or missing rows; it is not counted as a stock-screen member. The machine-readable result retains per-label/per-date expected, observed, unique, duplicate, off-grid, missing, and source-status fields.

Joining the frozen coverage statuses to the separate, already frozen `CONDITIONAL_PRICE_LIQUIDITY_SCREEN` shows that 19 of the 150 unresolved labels pass that price/liquidity screen on at least one of the five dates: `ADANITRANS`, `AMARAJABAT`, `GMRINFRA`, `GUJGASLTD`, `HDFC`, `HFCL`, `IBREALEST`, `IBULHSGFIN`, `IDFC`, `IIFLWAM`, `L&TFH`, `LTIM`, `MCDOWELL-N`, `MOREPENLAB`, `PEL`, `PVR`, `TATAMOTORS`, `TV18BRDCST`, and `ZOMATO`. Their daily counts are 16, 16, 17, 16, and 17 from 2022-12-26 through 2022-12-30. “Material” here means conditional on the existing price/liquidity rules only; it does not establish final point-in-time eligibility or identity.

## Paired-source diagnostics

Exact-name pairing against the five frozen NSE daily rows produced 2,695 stock/date relation cells (539 labels times five dates). The preserved v1 exact-equality artifact reports true counts of 1,915 open, 1,433 high, 1,390 low, 88 close, and 0 volume; no cell satisfies all five equality predicates.

The versioned v2 artifact also applies the existing adapter predicates with `Decimal(str(value))`: open equality is true in 1,915 cells, M15 extrema are contained by the daily extrema in 1,915, M15 volume equals daily volume in 0, and M15 volume is at most daily volume in 2,139. Under the adapter's two supported volume relations, 0 cells pass the equality-volume form and 1,915 pass the less-than-or-equal form. Close is intentionally independent of the adapter predicates. Common source basis is unknown, so these observations do not establish a tolerance, adjustment basis, qualification, or rejection rule. `ADANIPOWER`, `ALOKINDS`, `INDOSTAR`, and `UNITECH` had accepted M15 chunks but no exact-name NSE relation on all five dates; they were left unmatched.

## Controls and evidence

Ten invented tests passed before and after the bounded v2 decode. They cover exact-grid accounting, duplicate/off-grid/missing accounting, unresolved and quarantined exclusion, schema refusal, whole-chunk lockbox refusal, decimal conversion, independent close, extrema/volume violations, and an end-to-end selection fixture. The fixture retains all requested labels plus the benchmark, accepts only exact NSE/EQ stock bindings and the allowed Nifty index segment, and refuses ambiguous or alias-only mappings. The lockbox test uses the source timezone so `2023-01-01T00:00+05:30` cannot be misclassified by its prior UTC date.

The decode ran as UID 10002 with `--network none`, read-only explicit input/code mounts, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--memory 1g`, and `--cpus 2`. Only the 544 selected raw/manifest pairs and five frozen NSE daily inputs were mounted. Post-decode verification found zero mismatches across all selected chunk pairs. No source input, `goal.yaml`, mapping receipt, frozen reconciliation output, or original archive was changed.

Root independently replayed two pinned chunks and one pinned daily file in a separate restricted container, without importing the helper. All five Nifty grids contain exactly the expected 25 labels. INFY on 2022-12-30 independently reproduces open mismatch, failed extrema containment, unequal volume and M15-volume-at-most-daily; the result agrees with the frozen v2 record. Complete selected-chunk timestamp and numeric/OHLC validation passed before this probe selected the pilot rows. Only booleans and counts were emitted. These facts diagnose a specific source-pair mismatch; they do not identify its adjustment cause.

Key frozen evidence:

- accepted-history report: SHA-256 `43b80fc9e42387b978622676c15ce9c69c564772e006f9627a627bc729f429e0`
- sealed content index: SHA-256 `86aae96d13a4046c4b0f6ba08b6e97e2bcf1b1ca4b2f834b44a767ce089214f0`
- captured instrument master raw bytes: SHA-256 `48adffbfde4a9248ef5541b4273531671e87da3a4b745881125aef02a7bf0d22`
- captured instrument master manifest: SHA-256 `7d8b7c08484d98602331945b8907fb4483e3794fa36f9af6f4d424255df0bff0`
- 693 requested-label receipt: SHA-256 `a88632590be0f8344e962e0b27179516e977161e113c59e9ef2f5d9748c25fd3`
- reviewed calendar certificate: SHA-256 `4d7902c85909cba50b00dfccd6c0d3b1051225ba547e33bc010b56ad0e683c91`
- metadata-only selection: SHA-256 `a870ce61909cdc35bf016be33b35b2441d8ee519d78e4a54261a74c0e6001e9b`
- pre-decode freeze: SHA-256 `ca8140d81013c531909ccbab348551bfd9a5f7dbeb6ba2af6a5f4546f4b3a7b5`
- preserved v1 result: SHA-256 `55078995eae3354e627937c37bdbef8d47bb56241d756d69d39d1961ec90c83f`
- v2 result: SHA-256 `8992ae66bf6ee3b86cde64f3ba82794009f2615d1750c6cec73ba6f636a88a1e`
- v2 helper: SHA-256 `b9591c602197241737b07d15868aab2d212cbdf92c6a7403a2140b5cdc660d03`
- v2 tests: SHA-256 `b0287b9c1e945749ec4b6a2543daf8d0d913a3e13dc173694f4ca639b5abe7eb`
- v2 review freeze: SHA-256 `39df03f93cad6691f61c20995113b3339604d43ef90db2926e6e49531d1914bd`
- conditional-screen input: SHA-256 `e273f6c96c1cdab0edc685d7b689543b6eeba4503e147c90a0202a4696b46d3b`

Evidence directory: `var/kite-qualification/2026-10-15/pilot-candle-coverage/`. This result is a coverage diagnostic only. The unresolved mappings and unknown paired-source basis prevent it from qualifying the complete point-in-time pilot input.
