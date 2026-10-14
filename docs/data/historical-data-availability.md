# Historical market-data availability — public evidence

**As of:** 2026-10-14  
**Scope:** public, first-party pages only. No vendor contact, account, subscription, payment, sample or raw-data download, broker call, price inspection, strategy evaluation, trial-ledger use, or lockbox access occurred.

## Decision

Software construction can continue against invented canonical bundles, but no reviewed source is qualified for an actual market-data run.

NSE Data & Analytics' Historical Order & Trade product is the strongest availability lead. NSE publicly says that the Capital Market product contains order- and trade-level information together with index values. Its published layout describes all-tick cash-equity trades and all-tick `CASH` index records containing transaction date, `HH:MM:SS` transaction time, and a Nifty 50 index value. This establishes that a relevant official product class is advertised. It does not establish that NSE will supply the exact Icarus package.

Qualification still requires written answers and a representative metadata/schema package covering the exact dates, instruments, semantics and permitted use below. Until then the correct status is `RELEVANT_PRODUCT_ADVERTISED_PACKAGE_UNQUALIFIED`. The public lead does not establish that the exact required package exists. Passing the local software preflight would authenticate supplied bytes and contracts; it could not prove facts the supplier has not confirmed. No source-data files were obtained or evaluated.

## Public-source findings

### NSE Data & Analytics — Historical Order & Trade, Capital Market and Index

- [Paid EOD / Historical Data product page](https://www.nseindia.com/static/market-data/eod-historical-data-subscription), rechecked 2026-10-14. The page states that historical Order & Trade data is available for the Capital Market segment and that the segment covers order/trade information along with index value. Delivery is described as an online platform; exact requirements are handled through NSE Data & Analytics.
- [Historical Order & Trade layout v1.12](https://nsearchives.nseindia.com/web/sites/default/files/inline-files/Hist_Order_data_layout_1.12.pdf), rechecked 2026-10-14. Section 1.2 describes cash-market trade records for every trade. Section 1.3 describes Equity Market Index Data for every trade, with `CASH`, transaction date, transaction time and Nifty 50 index value fields.
- [NSE Data Sharing & Usage Policy](https://www.nseindia.com/static/market-data/nse-data-policy), rechecked 2026-10-14. It requires a relevant agreement governing intended use and how market data is received, handled and disseminated. The public product page does not publish an exact price for the required historical bundle.
- [NSE Indices data subscription](https://www.nseindia.com/static/nse-indices/index-data-subscription), rechecked 2026-10-14. It advertises historical index products and confirms that index data and related rights are licensed separately. It does not publicly specify the needed intraday history or solve the stock-universe requirement.

**Unconfirmed:** exact 2015-01-01 through 2022-12-31 availability; coverage of every required cash equity and delisted name; historical security masters and identifier changes; corporate actions and adjustment semantics; pre-open/auction records; timezone; transaction-time versus publication/availability-time meaning; corrections and revisions; Nifty 50 `PRICE_INDEX` identity; complete regular and special-session evidence; file-level provenance/hashes; re-download; internal archival, derived-bar, backup and reproducibility rights; and exact price.

### TrueData

[TrueData's support answer](https://feedback.truedata.in/topic/38617-best-plan-for-historical-data-for-nifty-fn), an approximately 2021 answer rechecked 2026-10-14, says NSE **futures contract-wise** one-minute data was available from June 2015 and tick data from 2018-11-10. That answer concerns derivatives, not NSE cash equities plus the official Nifty 50 price index. It does not confirm the Icarus package, its current coverage or its licence.

### Global Datafeeds

[GDFL's current Historical API availability page](https://globaldatafeeds.in/global-datafeeds-apis/global-datafeeds-apis/introduction/type-of-data-available/), rechecked 2026-10-14, advertises NSE cash history but lists 15-, 20- and 30-minute backfill as six calendar months; tick as one week; and daily data since 2010. [Its API pricing page](https://globaldatafeeds.in/global-datafeeds-apis/global-datafeeds-apis/pricing-sales/api-pricing/) says pricing is tailored to requirements rather than publishing an exact price. The public API offering therefore cannot establish the requested 2015–2022 M15 history. No public evidence reviewed here confirms a separate offline archive with delisted-name completeness, official price-index identity, availability timestamps, special-session authority or the required archival rights.

## Local inventory boundary

A filename-only inventory outside `var/verification` found no local raw file named as M15, intraday, tick, Nifty or NSE-index data. It found the canonical contract and data-ingestion source modules only. No raw values were opened.

The existing `var/panel.npz` daily cache is also unsuitable for exact-time benchmark proof. It uses a shared daily axis and legacy Yahoo-derived benchmark data; original benchmark event and availability timestamps and observed-versus-carried state are unavailable. It may support compatibility checks, never authoritative intraday Nifty matching.

## Unsent vendor-requirements draft

The following text is a preparation aid only. It has not been sent and does not authorize contact, purchase or data access.

**To:** `marketdata@nse.co.in`  
**Subject:** `Historical NSE cash equities and Nifty 50 data, 2015–2022: coverage, licence and quote`

> We are assessing a historical-data package for internal quantitative research and reproducible simulation. Please confirm in writing whether you can supply the following as one source-identified package:
>
> 1. NSE Capital Market executed trades for every available cash-equity instrument from 2015-01-01 through 2022-12-31, at tick resolution or sufficient to derive exact 15-minute OHLCV bars.
> 2. Official Nifty 50 **price-index** observations, not TRI, futures or a constituent reconstruction, over the identical interval, with original event timestamps.
> 3. Historical security masters covering listed and delisted instruments, ISINs, symbol/name changes, listing/delisting dates and series/status changes, sufficient to build a point-in-time universe without survivorship bias.
> 4. Corporate actions and the supplied price/volume adjustment basis, including revision history.
> 5. Pre-open/auction trade or volume records needed to model opening liquidity causally.
> 6. Authoritative regular, holiday and special-session schedules, including Muhurat or other exceptional sessions, with source circular/version identifiers.
> 7. Exact timezone, timestamp precision, event-time and publication/availability-time semantics for every record type; correction, cancellation, duplicate and revision rules; stable record/file identifiers; and observed versus synthesised status.
> 8. A coverage matrix by date, record type and instrument, including known gaps, plus a metadata-only sample manifest/schema and file hashes. Please state whether every requested date and delisted name is present rather than describing general product availability.
> 9. Licence terms permitting internal local archival, parsing, derivation of M15 bars, reproducible reruns, backups and long-term retention of audit/provenance records, with no redistribution. Please state any restrictions on derived data and Nifty index use.
> 10. Delivery format, immutable file/revision identity, re-download policy, total size, lead time and an itemised quote for this exact package.

Any response must be reviewed and pinned outside the delivered bundle before price parsing. An advertisement, self-declared manifest hash, or successful software test does not qualify real inputs.

