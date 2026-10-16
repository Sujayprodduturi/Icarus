# Missing-history retrieval routes — 2026-10-16

Status: **all 19 material pilot gaps now have collection candidates; no candidate is admitted as historical identity or qualified data**. `DATA_QUALIFIED=false` and `RUN_AUTHORIZED=false` remain unchanged. No authenticated request, price request, provider outreach, strategy run, lockbox access, or broker write occurred.

## What changed

The 13 modern-symbol candidates prepared on 2026-10-15 remain unchanged. Two exact current-series candidates can already be expressed by the existing collector. Four names that had no prepared route now have dated, explicitly published Kite instrument-token candidates.

| 2022 label | Retrieval candidate | Route kind | 2022-12-30 NSE identity | Pilot relevance | Admission state |
|---|---|---|---|---|---|
| ADANITRANS | `ADANIENSOL` | current exact symbol | EQ, `INE931S01010` | qualifies 5/5 dates | candidate only |
| AMARAJABAT | `ARE&M` | current exact symbol | EQ, `INE885A01032` | qualifies 3/5 dates | candidate only |
| GMRINFRA | `GMRAIRPORT` | current exact symbol | EQ, `INE776C01039` | qualifies 5/5 | candidate only |
| GUJGASLTD | `GUJENERGY` | current exact symbol | EQ, `INE844O01030` | qualifies 5/5 | candidate only |
| HDFC | token `340481` | published legacy Kite token | EQ, `INE001A01036` | qualifies 5/5 | identity unknown; quarantine |
| HFCL | `HFCL-BE`, current token `5620225` | current exact symbol, BE series | EQ, `INE548A01028` | qualifies 5/5 | series history unknown; quarantine |
| IBREALEST | `EMBDL` | current exact symbol | EQ, `INE069I01010` | qualifies 5/5 | candidate only |
| IBULHSGFIN | `SAMMAANCAP` | current exact symbol | EQ, `INE148I01020` | qualifies 5/5 | candidate only |
| IDFC | token `3060993` | published legacy Kite token | EQ, `INE043D01016` | qualifies 5/5 | identity unknown; quarantine |
| IIFLWAM | `360ONE` | current exact symbol | EQ, `INE466L01020`; current ISIN differs | qualifies 2/5 dates | ISIN changed; quarantine |
| L&TFH | `LTF` | current exact symbol | EQ, `INE498L01015` | qualifies 5/5 | candidate only |
| LTIM | `LTM` | current exact symbol | EQ, `INE214T01019` | qualifies 1/5 dates | candidate only |
| MCDOWELL-N | `UNITDSPR` | current exact symbol | EQ, `INE854D01024` | qualifies 5/5 | candidate only |
| MOREPENLAB | `MOREPENLAB-BE`, current token `1266945` | current exact symbol, BE series | EQ, `INE083A01026` | qualifies 3/5 dates | series history unknown; quarantine |
| PEL | token `617473` | published legacy Kite token | EQ, `INE140A01024` | qualifies 5/5 | identity unknown; quarantine |
| PVR | `PVRINOX` | current exact symbol | EQ, `INE191H01014` | qualifies 5/5 | candidate only |
| TATAMOTORS | `TMPV` | current exact symbol | EQ, `INE155A01022` | qualifies 5/5 | candidate only |
| TV18BRDCST | token `3637249` | published legacy Kite token | EQ, `INE886H01027` | qualifies 3/5; below turnover 2/5 | identity unknown; quarantine |
| ZOMATO | `ETERNAL` | current exact symbol | EQ, `INE758T01015` | qualifies 5/5 | candidate only |

“Qualifies” above means only the unchanged conditional close/turnover screen. It is not final point-in-time eligibility. All four legacy-token names are present for every session in each relevant 20-session pilot window; their problem is retrieval, not missing-window eligibility. Missing retrieval cannot justify excluding them.

## The four formerly route-less names

User posts on Kite's provider-hosted historical-data forum contain exact `symbol;instrument_token` pairs for `HDFC;340481`, `IDFC;3060993`, and `PEL;617473` in November 2017. A separate July 2018 forum incident post identifies `TV18BRDCST (3637249)`. These are materially stronger than guessing a successor security from a merger or deriving a Kite token from an NSE exchange token. They are not provider-certified mappings or a retained provider instrument dump, so they support a bounded retrieval attempt and nothing more.

The official NSE evidence explains the current-master absences without supplying Kite identity: HDFC Limited amalgamated into HDFC Bank effective 2023-07-01; IDFC's official corporate-action history records a 2024 merger; TV18BRDCST EQ was suspended from 2024-10-16 for amalgamation; and PEL stated its securities would stop trading from its 2025-09-23 merger record date. No successor (`HDFCBANK`, `IDFCFIRSTB`, `NETWORK18`, or PFL) is substituted for the original security.

Kite's own documentation distinguishes `instrument_token`, which Kite issues and the historical API consumes, from the exchange token. Kite also says its live instrument dump contains current-day mappings only and provides no historical-token lookup API. Therefore an archived NSE exchange token cannot be transformed into a historical Kite token. The published Kite pairs above are the valid retrieval leads.

Sources checked 2026-10-16:

- [Kite historical-data thread containing HDFC, IDFC and PEL token pairs](https://kite.trade/forum/discussion/comment/9169/)
- [Kite incident thread explicitly naming TV18BRDCST token 3637249](https://kite.trade/forum/discussion/4424/nifty-50-wrong-data-9-07-2018-03-00-pm)
- [Kite explanation of instrument token versus exchange token](https://kite.trade/forum/discussion/158/instruments-csv-file)
- [Kite statement that historical mappings are absent from the current dump](https://kite.trade/forum/discussion/9563/complete-list-of-instrument-tokens-of-nse-and-bse)
- [Official HDFC amalgamation disclosure](https://nsearchives.nseindia.com/corporate/HDFCLIFE_01072023104844_Merger.pdf)
- [Official NSE IDFC corporate-action history](https://www.nseindia.com/companies-listing/corporate-filings-actions?symbol=IDFC)
- [Official NSE TV18BRDCST suspension circular](https://nsearchives.nseindia.com/content/circulars/CML64466.pdf)
- [Official PEL merger/trading-stop disclosure](https://nsearchives.nseindia.com/corporate/PEL_20092025152926_PEL_SE_intimation_20092025_sd.pdf)

## Collector contract

The existing exact resolver already requires `tradingsymbol`, `instrument_type=EQ`, and `exchange=NSE`, and both current BE rows satisfy that lookup contract. The offline extension adds the missing admission boundary: a new three-line request, its matching provenance, and an explicitly staged hash-pinned evidence file are required, and every BE result is quarantined rather than counted as ordinary coverage. Their current BE series must never be back-projected onto the 2022 EQ rows.

The four legacy tokens need one narrow extension because `_resolve()` accepts current-master symbols only. The offline implementation accepts a separately hashed legacy-token manifest only when the caller supplies its reviewed SHA-256, refuses a route if the token appears anywhere in a newly transported and separately sealed current master, binds the route values and exact `2022-11-29..2022-12-30` bounds into run identity, uses the existing fixed read-only historical endpoint, and marks every resulting chunk `QUARANTINED_IDENTITY_UNPROVED`. Legacy chunks never increment ordinary accepted coverage. It does not add symbol guessing, exchange-token conversion, successor mapping, or an order route.

The BE request is also fail closed: a `-BE` symbol requires the hash-pinned series evidence named by its provenance, the resolved current-master token must equal the pinned candidate token before any historical preflight, and successful chunks are emitted only as `QUARANTINED_SERIES_IDENTITY_UNPROVED`. The collector verifies the local evidence receipt bytes before credentials or transport. The legacy manifest's reviewed hash pins each recorded URL and observation, but no primary forum response-body receipt was retained in this work; that limitation is another reason the four old-token routes remain candidate inventory rather than identity proof.

A successful candle response proves only that the provider returned a structurally valid payload for the requested token and dates. Candles carry no symbol or ISIN. Legacy-token output stays quarantined until either stronger provider identity evidence appears or a separately approved, action-normalized comparison against the full required official daily history supports the mapping and an independent reviewer accepts it. A small plausible price sample cannot certify identity.

## Prepared artifacts and remaining gate

The new ignored packet contains the two exact BE rows, the three-line request, provenance, and four legacy-token candidates. The original 25-symbol alias request and every earlier snapshot remain byte-for-byte untouched. The reviewed offline collector and launcher extension is implemented with invented-response tests; no authenticated or public price request was made.

Any later authenticated collection requires the separate source-use hold to be released and fresh credentials entered only into the collector's hidden interactive prompts. Credentials must not be supplied in chat or written to these artifacts. Existing provider questions remain prepared and UNSENT. Public archive acquisition remains paused pending that disposition.
