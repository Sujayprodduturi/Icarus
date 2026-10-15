# Dated identity reconciliation — 2026-10-15

Status: **full retained-cache matrix verified and official daily ISIN recovered for the bounded 2012–2022 source list; identity semantics still have explicit conflicts and gaps**. `DATA_QUALIFIED=false` and `RUN_AUTHORIZED=false`. No price, turnover, P&L, strategy, trial-ledger, broker, official-stream or 2023+ lockbox path ran.

## Retained-cache result

The local pre-2023 cache contains 2,962 schema-2 JSON files covering 2011-01-03 through 2022-12-30. Its source parser (`icarus/agents/data/nse.py`) selected legacy `SERIES=EQ` rows and persisted only symbol plus six numeric strings. It did not retain the legacy CSV's `TIMESTAMP` or `ISIN` columns. Each retained row therefore establishes only that the parser emitted an EQ symbol on that exact cache date.

These 2,962 dates are the frozen legacy archive list, not a complete exchange calendar. The separate calendar reconciliation has identified six market-wide weekend sessions absent from this list: 2013-11-03, 2015-02-28, 2016-10-30, 2019-10-27, 2020-02-01 and 2020-11-14. They remain explicit matrix gaps and must be requested separately in any raw recovery; no session is inferred from archive presence or absence here.

The metadata-only helper under ignored `var/kite-qualification/2026-10-15/dated-identities/` scans symbol keys without interpreting or emitting numeric arrays. It retains all 693 requested equities, joins an ISIN only on an exact date + symbol + series match to an existing NSE action observation, treats public symbol-change rows only as dated alias candidates, and retains the captured Kite mapping only as a current snapshot. Continuous identity intervals remain `UNPROVEN`; historical token identity remains `UNKNOWN`.

The full offline run completed in 48.147 seconds inside Docker with UID 10002, network disabled, a read-only root/input mount, only the evidence directory writable, all Linux capabilities dropped and `no-new-privileges`. Thirteen invented-fixture tests passed first. The 96,363,300-byte matrix contains:

- 693/693 requested equities with at least one exact dated symbol observation; none was dropped;
- 1,421,549 requested-name rows containing exact date + observed symbol + EQ observations;
- 7,456 observations with an ISIN from an exact same-date NSE action match;
- zero same-date ISIN conflicts;
- all remaining ISIN cells explicitly missing rather than forward-filled or inferred.

Matrix SHA-256: `4de39c206b47efce6a0af9f366dee506f71207082dc131a3426c7a17f816de00`. Detailed pre/post host manifests cover the same 2,962 files and 308,812,639 bytes; both aggregate to `e2de89d36d2e9d5b5a77783235a3e0fb99929ef370b2cfeea968bbf26c5df31a`. The container compared every opened file to the detailed frozen pre-manifest before inspecting its metadata, and the read-only mount plus matching post-manifest establish unchanged inputs.

Those baseline 1,421,549 rows are not 1,421,549 distinct securities. Candidate aliases intentionally copy the same observed symbol into more than one requested-name row. The preserved baseline receipt counts 1,416,583 unique `(date, observed_symbol, series, ISIN)` source observations and 4,966 overlap rows in three groups: `SKSMICRO` across `BHARATFIN`/`SKSMICRO` (1,294), `IBVENTURES` across `DHANI`/`IBVENTURES` (1,285), and `STRTECH` across `STLTECH`/`STRTECH` (2,387). Baseline receipt SHA-256: `369dcca5ff8c10c2abb9933259a0b690cd71a42bd6403f37de39a122ae0d1a36`. These are explicitly pre-raw-reconciliation counts; current counts appear below. The 693 requested names are not asserted to be 693 distinct historical identities.

## Late-2022 engineering interval

This is presence metadata for planning a test interval, not an accepted point-in-time universe or a survivor filter. On each of 2022-12-26 through 2022-12-30, 597/693 requested equities have an exact EQ observation and 96 are explicitly absent. Of those 597 present names, 58 lack a current Kite retrieval mapping. The same 58 names occur on all five dates and are retained in `late2022-coverage.json`.

Across the 248 observed 2022 sessions, 615/693 names appear at least once, 78 never appear, and 543 appear on every observed session. Seventy-three names appear at least once during 2022 but lack a current Kite mapping. These counts show that current-master gaps affect the proposed late-2022 interval directly; they are not only an early-history issue. Coverage receipt SHA-256: `91c4671ae4afe5cb38068bea0d815ad49e0b80fbe1c32741724f091156db4a70`.

## Official raw samples

HEAD requests returned HTTP 503, but ordinary unauthenticated GETs succeeded; the earlier report that the source was unavailable was wrong. No access-control workaround was used. Three official NSE ZIPs are sealed:

| Date | ZIP bytes | ZIP SHA-256 | Offline result |
|---|---:|---|---|
| 2011-01-03 | 42,678 | `8efbc8f9bc3ec393b1fe2187e4f17dd7543c36044645a1e43285f4b19ebf195b` | Schema gap: the real header ends at `TIMESTAMP` and contains no `ISIN`; zero identity rows claimed. |
| 2012-01-02 | 52,248 | `32f1779fc6529270ac99b3ccef5f8abeab6f07bb557e7bd2d64a44448b527754` | Header-only probe: `ISIN` present. |
| 2013-01-01 | 55,769 | `d89e7fc9320dcc966586cccd15b419d16cc2fb31cdecc854b0cda18e5214862f` | Header-only probe: `ISIN` present. |
| 2014-01-01 | 50,463 | `07db42624e8c5ef01b006f43620882917aab2c34456417352077e3f75e8f2e58` | Header-only probe: `ISIN` present. |
| 2015-01-01 | 56,642 | `c13be02ec70c85ef029ec1542170e7c335c4cb925aee506c7ccbfcee19f5fc3e` | Header-only probe: `ISIN` present. |
| 2016-01-01 | 58,943 | `8623d28a92924fd6d3432b3e21d307dd501a6f3891006e37d720fda2e436a5d7` | Header-only probe: `ISIN` present. |
| 2017-01-02 | 61,571 | `dfa61bf8767594c0070ea2489a1ead179d4a7288f3e37357399ff5f3bfb40f5d` | 1,692 date/symbol/series/ISIN observations. |
| 2022-12-30 | 87,662 | `636cb895992d40dfbf92dfe4b634d4e4000be6f218f6075c30631402683e19e7` | 2,335 date/symbol/series/ISIN observations. |

The raw parser ran only in the same offline container and emitted no price fields. Its receipt is 313,361 bytes, SHA-256 `033451f4015d29a506d2798c2128838298a3f6418a608a5b28e9c6177100a7da`. The 2011 result proves only that 2011-01-03 lacks ISIN; it is not generalized to other 2011 dates. Each annual first-session probe from 2012 through 2016 contains ISIN, so the prior pre-2017 boundary was unsupported and has been withdrawn. Any source schema gap remains dated rather than “fixed” by carrying later identifiers backward.

The resumable two-worker downloader uses one global governor with at least 0.5 seconds between every request start. Its first 125 completed requests took 62.141 seconds and 8,015,157 bytes: 0.497 seconds and 64.1 KB per completed date. The useful 2012–2022 workload is 2,721 dates, including all six separately established weekend sessions, projecting about 22.5 minutes and 174 MB. This met the approved 60-minute and 1-GiB gate. Acquisition is ordered 2022 then 2021 before older dates so a bounded pilot/warm-up certificate remains possible if the hard deadline ends the larger recovery; every success and failure remains explicit and resumable.

## Full raw reconciliation

The first complete acquisition receipt covers 2,721/2,721 dates, zero failures and 176,564,414 bytes. Its 1,075.422 seconds is the final resumed pass only; it does not claim to include the earlier interrupted pass. Five subsequently verified early Saturday sessions absent from the legacy list—2012-01-07, 2012-03-03, 2012-04-28, 2012-09-08 and 2013-05-11—were then fetched. The final v2 receipt covers 2,726/2,726 dates, zero failures and 176,787,200 bytes; SHA-256 `469e2a090f322efc546e16f430ca152720c09524360001051a1107dbccda2ce0`. Its 3.282-second elapsed field mostly measures reuse verification plus five new GETs, not total acquisition wall time.

The full isolated parser validated each ZIP against its acquisition hash, validated every CSV row date (including a tested legacy two-digit-year format), and retained only EQ date/symbol/series/ISIN metadata matching candidate symbols for the 693 requested names. It added 1,318,719 ISIN-bearing requested-name cells and 4,992 requested-name rows from the separately sourced sessions without emitting price fields. The authoritative corrected v3 matrix is 110,936,534 bytes with SHA-256 `ad44a5fe1b8ab069e50abf5f4fe485d4a6fcbfadecd36b637cbc48bacd6c292d`. It labels every count by scope: baseline requested rows 1,421,549 and baseline action-ISIN conflicts zero; current requested rows 1,426,541, current unique source observations 1,421,556, current alias-overlap excess rows 4,985, current ISIN-bearing requested rows 1,326,175, current semantic-conflict rows 1,447, current same-date raw-internal ISIN conflicts zero, and 693 requested labels retained.

The earlier 110,936,278-byte output with SHA-256 `a821903f82ff1dcc452cb05129a2bb2bfe7a6f7c15708e924b426d605ec83412` remains preserved for audit history but is superseded for aggregate accounting: it inherited stale baseline fields named `dated_observations` and `isin_conflicts` beside current fields. The v3 replay changes the accounting labels only and was generated under a new path after an invented reconcile-level regression reproduced that defect.

Current alias accounting is 1,426,541 requested-name rows, 1,421,556 unique source observations and 4,985 overlap rows: `SKSMICRO` across `BHARATFIN`/`SKSMICRO` (1,300), `IBVENTURES` across `DHANI`/`IBVENTURES` (1,288), and `STRTECH` across `STLTECH`/`STRTECH` (2,397). The versioned current-scope receipt SHA-256 is `845197b60a0eb85970bd5e6d8b9620a41c4d21c4b386a44bb832eeedc7ec9e17`. Any later universe construction must deduplicate proven same-date ISIN identity and fail closed on unresolved alias identity.

Those 1,447 differences are between an ISIN on the official daily trade-date row and an ISIN in the later-retrieved corporate-action evidence association. The latter source has unknown effective-date semantics, so the two values are not labelled equally authoritative for a dated identity and neither is selected or carried through time. They span 123 observed symbols and 134 symbol/ISIN-pair groups. The concentration around corporate-action names is consistent with split or replacement associations, but that is an inference rather than proved effective-date semantics. The v3 compact receipt retains requested name, symbol, exact date, both labelled values, daily archive SHA and CA evidence-packet SHA for every row and links to the corrected matrix; its SHA-256 is `5694752d0de598bb4bf51bbe4b7ec424b6f5dc80ec1254e0dcf6506b43b94f31`. The prior receipt SHA-256 `c3713752f9d1a184aba021a0d065ef47b24f7058b3dd250d55db51c2751a3cf5` remains preserved and links to the superseded accounting output.

For each of 2022-12-26 through 2022-12-30, all 597 requested names present on that date now have an exact-date raw ISIN, including all 58 without a current Kite mapping; the 96 absent requested names remain absent rather than invented. The 496-archive 2021–2022 certificate had zero acquisition failures and its reconciled matrix SHA-256 is `4c85773e03d015ddaf5c06d06d27abbf7e95e0b15f34414b84d2558e873b3ba6`; the late-2022 coverage receipt SHA-256 is `7e6f5e5ab5efbb9826b6b1c1b7789fdb5d46c27d36d8fac1ccbc7823783732f`.

The requested labels include `BANKBEES`, `LIQUIDBEES` and `NIFTYBEES`. Primary issuer 2022 factsheets now prove their historical classes: `BANKBEES` and `NIFTYBEES` are equity ETFs, while `LIQUIDBEES` is a fixed-income ETF. All three remain retained. Their disposition under the existing universe eligibility and cost rules is still open; the class evidence does not silently include, exclude, or price them as ordinary stocks.

## Docker startup provenance and critical path

The initial diagnosis that Docker Desktop, its backend and service were absent was incorrect; sandbox-limited process visibility caused that conclusion. Outside-sandbox inspection showed Desktop/backend present and WSL stopped after stale AF_UNIX reparse sockets crashed startup. The root agent preserved the affected socket directories and settings backup, disabled Docker AI, and restarted without reset or deletion. The first coordinated repair exposed another generated stale socket; preserving both current socket parents together produced a healthy Docker server (`29.6.2`). This report records provenance only; no Docker repair was performed by this worker.

Next: reconcile the 1,447 labelled raw-trade-date versus opaque-CA semantic differences and settle the existing-universe eligibility and cost disposition for the three now-classified `*BEES` ETFs before universe qualification. Exact symbol↔ISIN history remains unresolved before 2012 except where an exact source exists; 2011-01-03 specifically lacks ISIN. Current mapping absence still cannot prove delisting, and no historical Kite token may be inferred.
