# Independent final dated-identity review — 2026-10-15

## Verdict

**Final verdict: GO for the versioned v3 accounting receipt and recovered raw metadata as bounded evidence.** The initial NO-GO and its concrete finding are preserved below; the re-review closes that finding. This does not qualify an actual strategy input bundle: `DATA_QUALIFIED=false` and actual-study `RUN_AUTHORIZED=false` remain required.

I applied the two-axis `matt-code-review` method to the final reconciliation helper, downloader, conflict summarizer, four scoped test modules, the reconciliation report, acquisition receipt, final matrix and compact conflict receipt. This extends the earlier review, which explicitly excluded the full raw recovery. No vendor questions were sent; the operator's D58 instruction remains binding.

## Standards

### [P2] Final matrix inherits stale aggregate counters

`var/kite-qualification/2026-10-15/dated-identities/reconcile_raw_identities.py:151-155` adds current `counts.observations`, `observations_with_isin` and `conflicts` but retains the original matrix's unqualified `counts.dated_observations` and `isin_conflicts`. The frozen final matrix consequently declares both 1,421,549 and 1,426,541 observation counts, and both zero and 1,447 conflict counts. A metadata consumer choosing the original field names can silently report stale coverage or no discrepancies.

Preserve the original frozen bytes, produce a corrected version with explicit baseline/current scopes, and distinguish CA/raw semantic differences from contradictory same-date raw rows. Add a reconcile-level invented fixture checking inherited counters after a new observation and a semantic difference; the present extractor tests do not exercise this integration behavior. This is an accounting defect in the receipt, not evidence that raw archive contents or the source-date join are wrong.

The scoped helper tests pass **22/22** independently. My first invocation used the read-only input as the working directory and four fixture tests failed because they create temporary files there. Repeating with `/tmp` as the working directory and `/input` on `PYTHONPATH` passed all tests; evidence remained read-only throughout.

## Specification

No additional source-join or scope violation was found. Raw extraction checks the date of every CSV row, accepts the explicitly tested two-digit legacy year, validates each full-run ZIP against its receipt before parsing, limits emitted fields to date/symbol/series/ISIN, and rejects contradictory same-date raw identities. Candidate aliases remain discovery associations, not continuous identity proof or historical Kite token routing. No source price or turnover values were interpreted or emitted during this review.

The report correctly distinguishes a daily trade-date ISIN from the opaque effective-date semantics of the later corporate-action association. In a conflicting matrix cell, the original `isin` value remains present and the raw value is separately retained in `conflicts`; downstream admission must inspect that explicit discrepancy rather than treating the scalar `isin` as a resolved authority. No continuous identity is selected or forward-filled.

The report's original alias totals are correctly attached to the original frozen matrix. The final version must also expose its own totals: **4,985** overlap assignments and **1,421,556** unique source observations, comprising `SKSMICRO` 1,300, `IBVENTURES` 1,288 and `STRTECH` 2,397 overlap assignments. The three candidate-symbol owner groups are the only shared groups; I independently recounted them and checked there were no duplicate observation keys within an individual requested-name record. These are source-observation counts, not unique security identities or eligible stocks.

## Independently reproduced evidence

- Acquisition v2: 668,046 bytes, SHA-256 `469e2a090f322efc546e16f430ca152720c09524360001051a1107dbccda2ce0`; 2,726 distinct requested dates, all 2012–2022, 2,726 saved/reused, zero failures, and 176,787,200 raw bytes summed directly from the rows. This verifies receipt consistency, not a second complete archive hash scan.
- Final matrix: 110,936,278 bytes, SHA-256 `a821903f82ff1dcc452cb05129a2bb2bfe7a6f7c15708e924b426d605ec83412`. Directly recounting the records reproduces 693 requested labels, 1,426,541 assignments, 1,326,175 non-null ISIN cells, and 1,447 labelled differences. All records retain continuity `UNPROVEN` and historical token identity `UNKNOWN`.
- Compact difference receipt: 527,090 bytes, SHA-256 `c3713752f9d1a184aba021a0d065ef47b24f7058b3dd250d55db51c2751a3cf5`. Every one of its 1,447 rows exactly matches the matrix's requested name, date, symbol and both ISIN values; it contains 123 symbols and 134 symbol/ISIN-pair groups.
- Three independently opened raw ZIPs match their acquisition SHA and the compact receipt's raw ISIN: ONGC on 2012-01-06, `INE213A01029` versus CA association `INE213A01011`; KSCL on 2018-09-17, `INE455I01029` versus `INE455I01011`; CANFINHOME on 2022-12-08, `INE477A01020` versus `INE477A01012`. These confirm the preserved differences, without inferring why the identifiers differ.
- Each of the five declared pilot dates, 2022-12-26 through 2022-12-30, directly recounts to 597 present requested labels with an exact-date ISIN and 96 absent. This is presence metadata, not price/liquidity eligibility or a complete universe.

All independent execution used `python:3.12-slim`, UID 10002, `--network none`, read-only root and scoped evidence mount, dropped capabilities, `no-new-privileges`, 1 GiB/2 CPUs and a 64 MiB bounded tmpfs. No repository-wide mount, home, credentials, SDK, Docker socket, strategy, ledger or 2023+ price data was available. I did not repeat the full 2,726-archive replay or rehash all raw archives; the review combines code inspection, complete compact receipt consistency checks and three source-bound raw examples.

**Initial summary:** Standards: one P2 receipt-accounting finding. Specification: no additional finding. Raw evidence was usable within its declared scope; aggregate-receipt GO awaited correction.

## Versioned correction re-review — finding closed

The worker froze `output/v3-review-freeze.json` at SHA-256 `df2e3d68e3c8c9bc89abdbf93eae7ed501b98aaab70e6e52cc65841edabba704`. I independently checked the corrected helper/test hashes, inspected the new reconcile-level fixture and reran all four scoped modules: **23/23 pass** in the same restricted no-network container.

- `dated-identity-matrix-raw-reconciled-v3.json`: 110,936,534 bytes, SHA-256 `ad44a5fe1b8ab069e50abf5f4fe485d4a6fcbfadecd36b637cbc48bacd6c292d`.
- `alias-overlap-accounting-v3.json`: 605 bytes, SHA-256 `845197b60a0eb85970bd5e6d8b9620a41c4d21c4b386a44bb832eeedc7ec9e17`.
- `raw-vs-ca-conflicts-v3.json`: 527,090 bytes, SHA-256 `5694752d0de598bb4bf51bbe4b7ec424b6f5dc80ec1254e0dcf6506b43b94f31`.

The corrected counts explicitly separate `baseline_requested_row_observations=1421549` and `baseline_action_isin_conflicts=0` from current requested assignments 1,426,541, unique source observations 1,421,556, alias excess 4,985, ISIN-bearing assignments 1,326,175 and semantic difference rows 1,447. `current_raw_same_date_isin_conflicts=0` is a separate measure: the extractor refuses contradictory raw rows rather than silently choosing one. The new fixture verifies that a new observation and one raw/CA semantic difference replace the ambiguous inherited field names.

I compared canonical per-field digests of the original and v3 matrices. Every field except `counts`, `observation_accounting` and the reconciliation timing metadata is identical, including all records, candidate aliases, source pins and preserved differences. The only change within `raw_reconciliation` is `elapsed_seconds`; all archive receipts and other values match. My first comparison deliberately excluded only accounting fields and failed on that timing difference; the narrower inspection established its exact scope. The original matrix remains unchanged at its original SHA. The compact v3 receipts pin the corrected matrix and carry the independently recounted values above.

No further actionable finding remains in this scoped accounting correction. **Final standards: zero open findings; specification: zero additional findings. GO applies only to labelled metadata evidence and coherent accounting.**

## Additional current-series lead review

The metadata-only receipt SHA-256 independently matches `73d40bed3cdd2d47bd67f904ada3d4cfd2257ebdf7ee32c2be9b459fa21666b5`. It supplies `NSE:HFCL-BE`/token 5620225/ISIN INE548A01028 and `NSE:MOREPENLAB-BE`/token 1266945/ISIN INE083A01026. I independently matched both ISINs to the sealed 2022-12-30 raw `HFCL/EQ` and `MOREPENLAB/EQ` observations. These are two additional retrieval candidates, with no inference that current BE and historical EQ are interchangeable or that current tokens retrieve the historical identity.

The count is coherent: 13 prepared modern-name leads plus two distinct BE leads yield 15 candidates among 19 material requested labels. HDFC, IDFC, PEL and TV18BRDCST retain no prepared route. No HDFCBANK, IDFCFIRSTB or other substitute was selected. The original 25-symbol request independently remains unchanged at SHA-256 `037318fe0951f97e3873c1f0f2a4b1222794e5628b6853927a80806cb5099154`; the two BE leads have not been incorporated or launched.

**[P2 / specification precision] HDFC's claimed exhaustive pagination needs qualification.** Its two captured pages contain 10 + 27 = 37 returned rows but only **27 unique instrument IDs**: the ten first-page IDs recur on the second page. The connector declares `has_more=false`, but the overlap means exhaustive coverage of 37 distinct instruments is unproved. No exact `NSE:HDFC` appears in the captured unique rows. The report should state these limits rather than calling the search fully paginated in a way that implies complete unique coverage. This does not establish historical unavailability and does not affect the positive BE leads or the 15-candidate arithmetic. No additional API calls or actual-data decoding were performed for this review.

**Wording finding closed after re-review:** the pilot coverage report now explicitly records 37 returned rows, 27 distinct IDs, ten repeated IDs, `has_more=false` and unproved exhaustive unique coverage. It limits the absence claim to captured rows and keeps all four no-route labels unresolved. The source receipt remains unchanged. **GO for retaining these current-series retrieval leads as metadata only; zero open findings in this addendum.**

## Bounded pilot candle coverage v2 review

**GO for the fixed five-date coverage and conditional relation diagnostic.** `DATA_QUALIFIED=false` and actual-study `RUN_AUTHORIZED=false` remain unchanged. This review did not repeat actual numeric market decoding, evaluate strategies, or make API requests.

I reviewed the final helper, ten invented tests, selection, pre-decode freeze, preserved v1 result, corrected v2 result and updated pilot coverage report. Two initial method/precision issues were repaired before this GO: use the existing adapter's exact decimal/open/extrema/volume predicates while keeping close independent, and describe the fixed 694-label grid's gaps as requested-grid gaps rather than required physical bars for every historically active stock. The worker also added an end-to-end selection fixture after review identified that the original six tests did not cover the promised mapping/denominator behavior.

Independent checks:

- All **10/10 invented tests pass** in UID-10002, network-disabled Docker with read-only code, dropped capabilities, `no-new-privileges`, 1 GiB/2 CPUs and bounded tmpfs. Tests cover the grid, gaps/duplicates/off-grid labels, quarantine predicate, schema/whole-chunk lockbox refusal, exact decimal relations, independent close, extrema/volume failures and exact mapping/retained-label integration.
- All six artifact sizes/hashes in `review-freeze-v2.json` independently match; freeze SHA-256 `39df03f93cad6691f61c20995113b3339604d43ef90db2926e6e49531d1914bd`. The v2 result is pinned at `8992ae66bf6ee3b86cde64f3ba82794009f2615d1750c6cec73ba6f636a88a1e`. The five frozen daily NSE file hashes also independently match, without decoding their price fields.
- Captured original instrument-master SHA-256 `48adffbfde4a9248ef5541b4273531671e87da3a4b745881125aef02a7bf0d22` independently matches. All 544 accepted labels have exactly one captured NSE/EQ binding in the required stock segment or allowed Nifty index segment: zero predicate mismatches. Current modern aliases and BE candidates were not substituted.
- Direct result/selection recount reproduces 694 distinct labels (693 stocks plus one benchmark), 544 accepted chunks, 150 unresolved mappings, 3,470 distinct label/date cells, 2,720 accepted cells, 86,750 requested-grid rows and 68,000 observed rows. Nifty contributes five separate cells, each with 25 observed rows and no missing rows. The stock-grid gap count is 18,750; it must not be read as 18,750 physically required bars in a qualified point-in-time universe.
- The 2,695 relation cells independently recount to 1,915 open-equality, 1,915 extrema-containment, zero equal-volume and 2,139 M15-volume-at-most-daily booleans. Common adjustment basis remains unknown regardless of those counts. The separate conditional price/liquidity screen identifies 19 material unresolved requested labels, not all 150 unresolved labels as necessarily eligible.

The report preserves v1 and labels v2 explicitly. No open actionable finding remains within this bounded diagnostic scope. Runtime qualification, historical routing continuity, point-in-time eligibility and source-basis admission remain separate.

## Five-date daily-source provenance review

**GO for the bounded cache-versus-official-raw provenance diagnostic.** I reviewed the final helper, three invented fixture tests, frozen manifest, v2 result and [source-provenance report](../data/2026-10-15-pilot-daily-source-provenance.md). No actionable finding remains within this scope.

The code stages and verifies all ten input hashes before decoding any source prices; checks every CSV row's exact trade date in a complete first pass; rejects duplicate exact symbol/EQ identities; and compares OPEN/HIGH/LOW/CLOSE/TOTTRDQTY/TOTTRDVAL against the cache's six-field order with exact decimals. Missing cache, missing official source, and missing both are distinct states. The original ambiguous result and helper remain preserved; v2 corrects that label without changing source records.

Independent verification reproduced:

- Manifest `b20a62178b1c4a19fcacf27a762f7369905fd0d493d89de5fe3482c627fc9972`, helper `05e51e215ff1e1ad45a89fac63aaa5ed00dd44dca9a57f8c1c30d3bb8a7b6521`, tests `1b7de88f0a66c5ba6c523d661774bbcbf2c99b4e1377b3aff85fd36b8507861f`, and v2 result `0c9f0ec0df48a9599b43f74a7353784167723763394f65c42bbfecd4472fe2f6` all match their actual bytes.
- All ten actual source file hashes match the frozen manifest. Every raw ZIP hash also matches the earlier raw-acquisition v2 receipt; every daily-cache hash matches the earlier candle-coverage pre-decode freeze. No numeric source replay was required for these checks.
- On each of the five dates, the result independently recounts to 693 distinct requested labels, 597 exact six-field matches, 96 missing from both sources, zero field mismatches and zero one-source-only rows. INFY's six booleans are all true on each date and its requested-name row appears once in the denominator.
- **3/3 invented tests pass independently**, using UID 10002, no network, read-only scoped code, dropped capabilities, `no-new-privileges`, 1 GiB/2 CPUs and bounded tmpfs. This reviewer did not repeat actual numeric data decoding or access broker/API paths.

The result supports the limited claim that the five retained official daily caches faithfully reproduce their sealed official raw records. It does not explain the difference between those daily records and vendor M15 records, certify a common adjustment basis, qualify all history, or authorize a strategy run. `DATA_QUALIFIED=false` and actual-study `RUN_AUTHORIZED=false` remain required.
