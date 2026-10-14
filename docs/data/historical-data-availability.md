# Historical market-data availability — public evidence

**As of:** 2026-10-14

**Scope:** public, first-party pages only. No vendor contact, account, subscription, payment, sample or raw-data download, broker call, price inspection, strategy evaluation, trial-ledger use, or lockbox access occurred.

## Decision

Software construction can continue against invented canonical bundles, but no reviewed source is qualified for an actual market-data run.

The first qualification candidate is the existing Kite Connect read-only historical path. This is a source-assessment preference, not authorization to authenticate, subscribe, acquire data or run a strategy. NSE Data & Analytics remains an unsent fallback enquiry only for requirements Kite cannot establish; an NSE purchase is not assumed or mandatory, and every backtest does not inherently require tick data.

### Kite-first candidate — assessed 2026-10-14

- [Kite Connect Historical API](https://kite.trade/docs/connect/v3/historical/) advertises several years of candle history at minute, day and `15minute` intervals. Returned records are timestamped OHLCV candles with optional OI, rather than raw ticks with separate original event and availability timestamps.
- [Zerodha's current pricing support page](https://support.zerodha.com/category/trading-and-markets/general-kite/kite-api/articles/historical-data-and-live-market-data-payment-plan) lists historical and live market data in the paid INR500/month/key API plan without a separate data add-on. The repository records an active 500-plan assumption, but no account entitlement or current subscription was verified here.
- The current instrument master is a daily list of instruments available for trading, not a historical point-in-time membership archive. A [July 2025 provider response](https://kite.trade/forum/discussion/comment/50511/) says delisted-instrument history cannot be retrieved; this is a dated limitation report, not a fresh authenticated coverage test.
- `icarus/brokers/zerodha.py` already adapts historical responses into timestamped OHLCV candles. That wrapper is useful plumbing, but it does not establish source coverage, adjustment/revision semantics, exact Nifty price-index identity, original availability time, archival licence, or OS/process separation for credentials and network access.
- Kite candles are not plug-compatible with the canonical exact-point Nifty observation contract. A candle close cannot silently become a raw trade-time observation. Missing event-time evidence remains unavailable unless a separately reviewed converter, source semantics and matching/projection policy justify it.

Qualification must preserve D3's NSE daily point-in-time authority and missing-delisted handling, D7's full daily 2011–2022 and M15 2015–2022 ranges, and D21's isolated ingestion boundary. The hosted Kite MCP is not an approved acquisition path, and the existing wrapper alone is not the required credential-plane security control. The next step is a metadata-only Kite coverage, schema, licence, timestamp and security qualification using no price evaluation. Any missing daily names, delisted history, authoritative calendar/actions/opening liquidity, exact Nifty observations or full-range resources stays explicit and may then justify the unsent NSE fallback request.

NSE Data & Analytics publicly says that its Capital Market Historical Order & Trade product contains order- and trade-level information together with index values. Its published layout describes all-tick cash-equity trades and all-tick `CASH` index records containing transaction date, `HH:MM:SS` transaction time, and a Nifty 50 index value. This establishes that a relevant official product class is advertised. It does not establish that NSE will supply the exact Icarus package.

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

**Subject:** `Historical NSE cash equities and Nifty 50 data, daily 2011-2022 and intraday 2015–2022: coverage, licence and quote`

> We are assessing a historical-data package for internal quantitative research and reproducible simulation. Please confirm in writing whether you can supply the following as one source-identified package:
>
> 1. Daily cash-equity OHLCV history for 2011-01-01 through 2022-12-31, plus NSE Capital Market executed trades for every available cash-equity instrument from 2015-01-01 through 2022-12-31, at tick resolution or sufficient to derive exact 15-minute OHLCV bars. Historical security masters, point-in-time membership, corporate actions and session calendars must cover the full daily interval. Quote the daily archive and intraday archive separately so existing local daily data can be reused if separately qualified.
> 2. Official Nifty 50 **price-index** observations: daily history from 2011-01-01 through 2022-12-31 and intraday history from 2015-01-01 through 2022-12-31, with original event timestamps and availability semantics. Please separate official end-of-day publication from observations actually available at the venue session close; do not substitute TRI, futures or a constituent reconstruction.
> 3. Historical security masters covering listed and delisted instruments, ISINs, symbol/name changes, listing/delisting dates and series/status changes, sufficient to build a point-in-time universe without survivorship bias.
> 4. Corporate actions and the supplied price/volume adjustment basis, including revision history.
> 5. Pre-open/auction trade or volume records needed to model opening liquidity causally.
> 6. Authoritative regular, holiday and special-session schedules, including Muhurat or other exceptional sessions, with source circular/version identifiers.
> 7. Exact timezone, timestamp precision, event-time and publication/availability-time semantics for every record type; correction, cancellation, duplicate and revision rules; stable record/file identifiers; and observed versus synthesised status.
> 8. A coverage matrix by date, record type and instrument, including known gaps, plus a metadata-only sample manifest/schema and file hashes. Please state whether every requested date and delisted name is present rather than describing general product availability.
> 9. Licence terms permitting internal local archival, parsing, derivation of M15 bars, reproducible reruns, backups and long-term retention of audit/provenance records, with no redistribution. Please state any restrictions on derived data and Nifty index use.
> 10. Delivery format, immutable file/revision identity, re-download policy, total size, lead time and an itemised quote for this exact package.

Any response must be reviewed and pinned outside the delivered bundle before price parsing. An advertisement, self-declared manifest hash, or successful software test does not qualify real inputs.
