# Source-semantics evidence for the paired daily/M15 adapter

**Evidence date:** 2026-10-15 IST  
**Scope:** public, unauthenticated primary material from Kite/Zerodha, NSE India and NSE Indices only. No authenticated endpoint, order endpoint, credential, bulk market-data download or strategy evaluation was used.

## Decision

**The downloaded 2026 Kite snapshot is not source-qualified.** Public official material is enough to preserve the adapter's separate daily-signal and M15-execution design, start-label interpretation, and strict refusal of an assumed daily/M15 close match. It is not enough to certify the snapshot's effective-dated adjustment basis, historical security lineage, full 2011–2022 regular/special-session calendar, Nifty candle publication times, or durable archival rights. The current strict adapter must therefore refuse these actual inputs. `DATA_QUALIFIED=false`; actual-study `RUN_AUTHORIZED=false`.

Price matching alone cannot qualify a source. Bounded reconciliation can reduce snapshot-specific uncertainty, but a small sample cannot certify full-range basis, lineage, calendar, availability or rights.

## Relationship to the saved evidence packet

This report starts from `var/kite-qualification/2026-10-15/source-evidence/source-evidence.json` (SHA-256 recorded in the qualification audit as `892326ccd446e02b720bcec5b32d346644e08dd9a26cffd129e36d1f6fa55e60`). Its candle schema, timezone, reviewed start-label derivation, Nifty coverage start, price-index identity, mutable-archive warning, prior adjustment warning, official Nifty-close distinction, lineage gap and rights ambiguity are baseline, not new findings. New evidence here is the explicit daily-versus-intraday construction, unsupported daily-open equality as a universal rule, current adjustment scope and reference-date risk, the equity/derivative token distinction, and the finite calendar/clarification work they imply.

## Documented facts

Sources were read on 2026-10-15. A forum statement is treated as a dated vendor statement, not as a specification with revision history.

### 1. Candle record and timestamp semantics

- The current [Kite Historical Candle Data documentation](https://kite.trade/docs/connect/v3/historical/) says the archive is **“up to date as of the time of access”** and defines each record as timestamp, OHLC, volume and optional OI. It does not define original event-publication time, revision identity, adjustment basis, or whether a daily timestamp means session open, close, or publication time.
- A dated Kite staff explanation from April 2019 says a 09:15 15-minute candle covers 09:15:00 through 09:29:59: [15-minute formation](https://kite.trade/forum/discussion/5889/mismatch-in-data). This supports treating M15 labels as interval starts. It does not prove when a historical candle became final or available in 2015–2022.
- A current Kite staff statement says intraday equity data is available from 2015 onward **“subject to instrument availability”**: [July 2026 availability answer](https://kite.trade/forum/discussion/16124/historical-15-minute-ohlc-data-availability-pricing-and-api-limits-for-equity-stocks). This is consistent with the local Nifty M15 start on 2015-01-09, but does not certify every instrument/session or explain the 326 quarantined chunks.

**Adapter consequence:** start-labelled half-open M15 intervals are supportable as a declared projection. Exact historical availability timestamps and full-range completeness are not.

### 2. Daily records are not aggregates of Kite intraday records

- An August 2026 Kite staff response states that daily OHLC comes from post-session exchange bhavcopy, while minute/hourly candles come from live data and may omit ticks: [daily versus intraday construction](https://kite.trade/forum/discussion/16171/historical-data-api-missing-minute-candles-after-15-14). The same response documents a 2026 Closing Auction Session case where intraday records stop at 15:15 while daily data includes the whole trading day. That case evidences source construction; it does not establish 2011–2022 session boundaries.
- NSE Indices says the official [Nifty 50 closing price](https://www.niftyindices.com/resources/index-concepts/faqs) uses the last half-hour weighted-average closing prices of constituents. That is a separately constructed official close, not the last observation in a final 15-minute index candle.
- NSE's current [pre-open specification](https://www.nseindia.com/static/products-services/equity-market-pre-open) says the pre-open equilibrium price is the day's open; if none is discovered, the first normal-market trade is the open. Kite's public material does not say its first captured M15 open must contain that pre-open equilibrium event.

**Adapter consequence:** `daily.close == final_M15.close` is unsupported and must not be required. `daily.open == first_M15.open` is also unsupported as a universal rule for this pair. This does not invalidate an individual row whose opens empirically match; the current strict equality check remains enforced. Actual admission needs a full-range, independently justified and reconciled relationship for the concrete byte set, with provider evidence where public or exchange evidence cannot close the meaning. Because Kite says intraday capture may omit transactions, public evidence alone does not certify exact open, extrema or volume equality. Daily containment of M15 extrema and `sum(M15 volume) <= daily volume` are plausible diagnostics only after a shared adjustment basis is independently established. Until the configured relationships are justified for the actual pair, the adapter refuses rather than relaxing them.

### 3. Corporate-action adjustment is mutable and insufficiently specified

The official vendor statements conflict over time:

- December 2019: [day candles only; split adjustment](https://kite.trade/forum/discussion/6921/historical-data-issue-stock-split-adjustment), with recent intraday adjustments mentioned separately.
- August 2024: daily equity candles are [“adjusted for all corporate actions”](https://kite.trade/forum/discussion/14381/in-historical-data-are-prices-adjusted-for-splits-and-bonus).
- July 2025: [bonuses, splits, rights issues, spin-offs and extraordinary dividends](https://kite.trade/forum/discussion/15358/documentation-of-adjustments-in-historical-data) are listed.
- August 2026: [adjustments occur on the ex-date](https://kite.trade/forum/discussion/16099/split-adjustment-data), demergers wait for a Cost of Acquisition file, and Rights Entitlement instruments are not chart-price adjusted.

The current API documentation does not reconcile these statements or state price/volume factors by interval, effective date, revision history, extraordinary-dividend threshold, or the exact basis of the downloaded bytes.

There is an additional point-in-time problem: the snapshot was retrieved in 2026 but ends in 2022, and Kite describes history as current **at access time**. It may therefore embed adjustments caused by corporate actions after 2022. That is an inference, not a claim that any particular row changed. A raw contemporaneous NSE 2011–2022 series and a 2026-revised Kite series cannot be declared to share an action basis without an event/factor ledger tied to both byte sets. Applying the local action ledger again could double-adjust; applying none could leave daily and M15 on different bases. The phrase “all corporate actions,” followed by the later express reference to extraordinary dividends, also leaves dividend treatment in the captured daily and M15 bytes unresolved. A project-level dividend convention cannot silently replace or duplicate an unknown vendor adjustment.

**Adapter consequence:** do not certify `shared_action_basis`, do not infer relative factors from price matches, and do not pair the downloaded daily/M15 bytes with raw NSE history until effective-dated factors and volume treatment are independently established and reconciled, using provider evidence where the remaining provider-specific semantics cannot otherwise be resolved.

### 4. Instrument tokens do not establish historical equity identity

- Kite staff says instrument tokens are daily identifiers and recommends daily instrument-master imports; for equities they generally persist only until a corporate action: [instrument-token guidance](https://kite.trade/forum/discussion/9301/use-case-of-instrument-token-when-tradingsymbol-and-exchange-can-be-used-for-uniq-selection).
- Another staff response says `exchange:tradingsymbol` remains unique only until a symbol-change corporate action: [historical-store guidance](https://kite.trade/forum/discussion/5783/using-instrument-token-to-store-historic-data-has-issues).
- Token reuse after expiry is explicitly documented for derivatives. Public evidence found here does **not** establish general reuse of cash-equity tokens, so that derivative warning must not be generalized.

**Adapter consequence:** the captured 2026 master proves request-time mapping only. It cannot prove dated identity across 2011–2022 or resolve the 150 unmatched historical names. Require authoritative effective-dated security lineage (at least venue, series, symbol, ISIN, token and validity interval); preserve every unresolved name and gap.

### 5. Regular and special sessions require a dated exchange artifact

- NSE's current [market timings and holidays](https://www.nseindia.com/resources/exchange-communication-holidays) gives the normal equity session as 09:15–15:30 and explicitly notes that Muhurat timings are separately notified.
- NSE's cash-market circular [NSE/CMTR/54023 dated 2022-10-11](https://archives.nseindia.com/content/circulars/CMTR54023.pdf) records a special Muhurat session on 2022-10-24. One circular proves that archive-presence weekdays and a fixed 09:15–15:30 grid are not a complete calendar rule.

**Adapter consequence:** public NSE material can support a calendar only after a complete 2011–2022 manifest of dated normal holidays, Muhurat/special sessions, outages and changed boundaries is assembled and hashed. The current dynamic page plus isolated circulars is insufficient. Do not infer sessions from candle or bhavcopy presence.

### 6. Nifty event and publication semantics remain incomplete

- NSE Indices describes the Nifty close construction, and an [April 2026 press release](https://www.niftyindices.com/Press_Release/ind_prs22042026.pdf) says Nifty 50 was disseminated live every 500 ms before moving to 250 ms on 2026-05-11. These establish a live index stream and a separately calculated official close.
- They do not map Kite historical candle labels to individual NSE index observations, certify which observations were captured in each 2015–2022 candle, identify a historical revision, or attest when each archived candle/daily close became available.

**Adapter consequence:** keep Nifty M15 as interval observations only. Do not turn the final candle into an official daily close or an exact fill-time benchmark point. Treating `bar_start + 15 minutes` as availability would be a separately approved modeled replay rule, not vendor-observed availability; delayed writes or later revisions can still leak. Exact causal benchmark returns remain unavailable pending the separately reviewed interval-benchmark policy.

### 7. Rights for a durable private research archive are unresolved

- Zerodha's current [terms, clause 16.3](https://zerodha.com/terms-and-conditions) permits extraction through officially authorized APIs under a valid subscription.
- Zerodha's support page says Kite data [cannot be displayed on other platforms](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/can-i-use-historical-and-live-data-taken-from-kite-connect-api-on-other-platforms) because of exchange data-vending policy.

Neither page expressly grants or forbids Icarus's proposed durable private local archive, derived M15 artifacts, backups, reproducible reruns, or retention after subscription expiry. No legal conclusion is drawn.

**Adapter consequence:** keep archival/use evidence unqualified. Existing bytes may remain quarantined as evidence, but they must not be admitted to the research bundle on the strength of these pages.

## Finite unresolved evidence requests

### Provider-specific questions

1. For the exact retrieval date and captured byte hashes, identify the adjustment events and effective factors applied separately to daily and M15 price **and volume**, including any post-2022 event that rewrote 2011–2022 rows; state revision timing and exceptions.
2. State whether daily open and first M15 open have any guaranteed relation when pre-open auction prints exist; state the guaranteed cross-source extrema and volume relations, if any, given potentially incomplete live-tick capture.
3. Map the captured provider tokens to effective dates and explain provider-specific token changes. Historical symbol/series/ISIN lineage should also be assembled independently from authoritative NSE records; the provider is not the exclusive source for that lineage.
4. State Nifty historical-candle interval boundaries, observation source, revision behavior and earliest safe availability time for daily and M15 records. A generic timestamp/OHLCV schema is insufficient.
5. Identify the applicable contract or licence text governing local retention, private derived artifacts, backups, reproducible reruns and post-subscription retention. Existing applicable contractual text could close this; a new vendor statement is not inherently required.

### Evidence that can be assembled from public exchange material

1. Build a complete, hashed 2011–2022 NSE cash-market calendar from annual holiday notices plus every special-session, Muhurat, contingency/outage and timing-change circular; independently check it against archive presence without treating presence as authority.
2. Bind the existing NSE corporate-action records to an effective-dated security/ISIN lineage and compare their event set with independently established Kite factors, using provider evidence where unresolved. Public events alone still cannot reveal which revisions were applied inside Kite bytes.
3. Preserve official Nifty close records separately from Kite M15 candles and document Price Index versus Total Return Index identity. This still does not create exact historical publication timestamps.

## Copy-ready Kite support question — UNSENT

> We downloaded Kite Historical API `day` and `15minute` candles in October 2026 for private, offline research covering dates through 2022. We are not asking about orders or strategy results. Could you please point us to authoritative documentation, or answer these source-semantics questions?
>
> 1. Are the returned day and 15-minute price and volume fields adjusted on exactly the same basis? Which actions are applied (split, bonus, rights, spin-off/demerger and ordinary/extraordinary dividend), how is volume transformed, and are pre-2023 rows revised for actions occurring after 2022?
> 2. Is there any guaranteed relationship between bhavcopy daily open/high/low/volume and Historical API 15-minute open/high/low/volume, given that intraday candles are formed from received live data? Please distinguish guaranteed rules from usual observations.
> 3. Does a 15-minute timestamp denote the interval start? When is a completed historical candle safe to treat as available, and can it be revised later? Is any revision or original-publication timestamp exposed?
> 4. Which applicable terms govern retaining these API responses and privately derived research artifacts locally, making backups and reproducible reruns, and retaining them after the subscription ends, without display or redistribution?
>
> No message has been sent from this report.

## Qualification status by adapter field

| Required field or rule | Public evidence result | Strict disposition |
|---|---|---|
| M15 label is interval start | Sufficient as dated vendor semantics | May declare start-labelled intervals; retain modeled completion separately |
| Daily and M15 have separate closing conventions | Sufficient | Preserve both; never force final-M15 close to daily close |
| Daily open equals first M15 open | No universal guarantee; actual full-range relation not yet established | Keep strict check; actual pair refuses until independently justified and reconciled |
| Extrema/volume relationship | Plausible subset relation, but basis and capture guarantees absent | Diagnostic until independently established and reconciled; provider evidence where unresolved |
| Shared action basis | Conflicting/mutable vendor statements | Unknown → refuse |
| Dated security mapping | Current master only | Unknown spans/names → refuse |
| Regular/special calendar | Normal hours plus examples, no complete historical certificate | Unknown sessions → refuse |
| Nifty exact event/availability | Close method and live dissemination known; candle mapping absent | Exact-point use unavailable |
| Private archival rights | API access and no-display rule known; retention/derivation silent | Rights evidence absent → refuse admission |

This evidence changes no threshold, source bytes, quarantine, lineage declaration, adapter rule, benchmark policy, trial ledger or authorization.
