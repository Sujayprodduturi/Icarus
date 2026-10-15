# Pilot instrument classes — 2026-10-15

**The three retained labels are ETF units, not individual company stocks.** Historical primary issuer material establishes the class before the December 2022 pilot; issuer material describing December 2022 corroborates it. This resolves the factual class question for these three labels. It does not itself settle stock-strategy eligibility, applicable transaction costs, or qualification of the whole input bundle. No runtime universe, fees, membership or source files were changed, and no vendor was contacted.

## Historical class and exact identifier evidence

| Requested label | Historical instrument class | Issuer's historical ISIN | Sealed 2022-12-30 NSE raw metadata |
|---|---|---|---|
| BANKBEES | Equity index ETF, tracking the bank index | INF204KB15I9 | Exact same symbol, ISIN and `EQ` series |
| NIFTYBEES | Equity index ETF, tracking the Nifty 50 | INF204KB14I2 | Exact same symbol, ISIN and `EQ` series |
| LIQUIDBEES | Fixed-income/liquid ETF | INF732E01037 | Exact same symbol, ISIN and `EQ` series |

Primary sources inspected on 2026-10-15:

- [Issuer February 2022 BANKBEES factsheet](https://mf.nipponindiaim.com/investorservices/factsheetsdocuments/fundamentals-february-2022/Innerpage/ETF-Bank-BeES.html), details as of 2022-01-31: identifies an equity ETF and index exchange-traded scheme, exchange symbol BANKBEES and ISIN INF204KB15I9.
- [Issuer February 2022 NIFTYBEES factsheet](https://mf.nipponindiaim.com/investorservices/factsheetsdocuments/fundamentals-february-2022/Innerpage/ETF-Nifty-BeES.html), details as of 2022-01-31: identifies an equity ETF and index exchange-traded scheme, exchange symbol NIFTYBEES and ISIN INF204KB14I2.
- [Issuer January 2022 LIQUIDBEES factsheet](https://mf.nipponindiaim.com/investorservices/factsheetsdocuments/fundamentals-january-2022/Innerpage/ETF-Liquid-BeES.html), details as of 2021-12-31: identifies a fixed-income ETF, its NSE symbol LIQUIDBEES and ISIN INF732E01037. The scheme invests in repo/money-market instruments and distributes income through compulsory reinvestment rather than acting as an ordinary company share.
- [Issuer December 2022 presentation](https://mf.nipponindiaim.com/FundsAndPerformance/Presentation/NipponIndia-Nifty-Auto-ETF-Dec-2022.pdf), PDF pages 62–63 (one-based): the abridged report as of 2022-12-31 explicitly lists NIFTYBEES and BANKBEES in the equity-ETF section and LIQUIDBEES in the debt-ETF section. This supplies December historical corroboration. Its actual publication/availability timestamp is unproved, so it is not a source of pre-pilot decision-time knowledge.

I independently matched the identifiers against `raw-identity-samples.json`'s sealed 2022-12-30 observations. That metadata receipt's SHA-256 is `033451f4015d29a506d2798c2128838298a3f6418a608a5b28e9c6177100a7da`; the source ZIP's SHA-256 is `636cb895992d40dfbf92dfe4b634d4e4000be6f218f6075c30631402683e19e7`. This match is exact-date identity evidence, not proof that an identifier was unchanged across every intervening session.

## Consequence for the pilot

`SERIES=EQ` does not distinguish individual stocks from these ETF units. The three labels must remain present in reconciliation records with their proved classes; the existing stock-universe specification must determine their eligibility explicitly. An exclusion on instrument-class grounds must be recorded and counted, rather than presented as a missing symbol or quietly dropped. This report does not introduce a new historical-range requirement or alter the declared pilot interval.

Cost and return semantics remain a separate implementation check if any of these ETFs is admitted. The [issuer's December 2022 LIQUIDBEES presentation](https://mf.nipponindiaim.com/FundsAndPerformance/Presentation/NipponIndia-ETF-Nifty-1D-Rate-Liquid-BeES-Presentation-Dec-2022.pdf), PDF pages 5–8, describes compulsory income reinvestment, additional units credited through its corporate-action calendar and distinct STT treatment. Those issuer statements are evidence that ordinary-stock assumptions cannot simply be reused; they are not a legal rate determination or permission to modify the frozen fee model. No quoted prices, return statistics or performance comparisons were used in this classification.

Published pages were inspected through the web reader. No local binary capture or invented file hash is claimed for the issuer documents. The dated content and exact source URLs above are the retained evidence; the raw NSE metadata has separately sealed local bytes. Current-master labels were not used to infer the historical classes.
