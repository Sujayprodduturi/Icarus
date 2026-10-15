# Public security-lineage evidence — 2026-10-15

Status: **bounded public-event evidence collected; continuous lineage remains unqualified**. This pass used only two small public NSE security-metadata CSVs and the already frozen local metadata packet. It did not download prices, candles or bulk market history; inspect broker or secret state; access the lockbox; or run a strategy/ledger path.

## Sources and access boundary

NSE's public [All Reports page](https://www.nseindia.com/all-reports) explicitly exposes an old-symbol/company-name history view; its rendered table labels new symbol/name and old symbol/name and says old values can be selected to view history (page lines 801–806 in the 2026-10-15 capture). The exact public archive URLs below existed and returned CSV data. The official terms page was inaccessible to the research tool and the website-policy page timed out; no 403 or other access control was bypassed and no new rights conclusion is made. Existing archive-use rights therefore remain unresolved.

| Official public file | Retrieved UTC | Bytes | Rows | SHA-256 |
|---|---:|---:|---:|---|
| `https://archives.nseindia.com/content/equities/symbolchange.csv` | 2026-10-15 13:45:51.5916275Z | 69,219 | 1,067 | `69c0c5e18cca3350c2e07f7c8c4c1ebbfe38d81c8fa32c51f6ca9ea332e85f17` |
| `https://archives.nseindia.com/content/equities/namechange.csv` | 2026-10-15 13:45:59.1141056Z | 240,291 | 2,329 | `b41026bdec13d5135cf128e75c6cba4e67dd5c9ed3310abaa8412a306ab43534` |

The ignored evidence directory is `var/kite-qualification/2026-10-15/identity-evidence/`. `retrieval-register.json` records URLs, times, hashes and the access-policy checks. An invented-row parser suite passed five tests before the real CSVs were parsed: exact headers, date normalization, explicit blank non-identity fields, and refusals for unknown columns, invalid dates and blank identity keys.

## What the rows establish

The input cohort was the 85 of 150 current-Kite-unmatched requested equities that already had at least one NSE corporate-action row carrying an ISIN. Direct, exact symbol matching against the two public files found:

- 29 names with at least one dated official public event row across **all dates**;
- 20 names in the symbol-change file and 27 in the company-name-change file, with overlap;
- 46 rows across 28 names dated before 2023, spanning 2000-08-02 through 2020-10-29;
- 28 rows across 18 names effective within the actual 2011–2022 study interval;
- 18 rows effective before 2011, which are older anchors rather than evidence of continuous 2011–2022 coverage;
- 56 names with no direct row in either downloaded file; their identity remains unresolved.

The 29 all-date directly observed names are ABAN, ABIRLANUVO, BHARATFIN, CAPF, DALMIABHA, DHANI, DHFL, EVERONN, FCONSUMER, FLEXITUFF, GSKCONS, HEG, HFCL, IDFC, INGVYSYABK, IVRCLINFRA, KWALITY, MINDTREE, MONSANTO, PEL, RCOM, RELINFRA, RNAVAL, SPICEJET, STLTECH, SUDAR, TATACOFFEE, TATASTLBSL and TV18BRDCST. Each receipt retains the original row and source row number. HEG's only direct symbol-change match is effective 2026-09-22, so only 28 of these names have any pre-2023 row. This evidence does not mean 28 names are resolved for the study: only 18 have an event effective inside 2011–2022, and an event is one dated edge rather than a complete interval.

A public row establishes only the stated symbol or company-name change on its effective date. The cached corporate-action ISIN is an association returned in the later-retrieved action archive; unknown revision semantics mean it is not automatically proof that the ISIN was valid on every historical event date. ISIN continuity also does not prove uninterrupted economic identity through a merger, demerger or arrangement.

## What remains candidate-only or unknown

- The event rows are useful edges for a future lineage graph, but they do not establish complete intervals between events, listing/delisting dates, series/status history or Kite token history.
- A post-2022 rename may explain why a historical symbol is absent from the modern master, but cannot reassign pre-2023 candles or tokens without a complete effective chain and matching security evidence.
- The 56 names without a direct file row remain unknown. Absence is not evidence that no change occurred; these current downloads are not certified complete for the study period.
- Even for the 29 direct matches, a chain through mergers, demergers, reused symbols or changed ISINs requires dated circular/security-master evidence. No modern mapping was back-projected.
- These files add neither an authoritative session calendar nor archive/use rights, raw-event availability, corporate-action adjustment basis or source revision history.

Evidence output `public-identity-evidence.json` SHA-256: `7bda5ee2c807b5494b88f431f1b332a0235016b28dea6cb371ea60ba5579cf2b`. It preserves `continuous_lineage=UNKNOWN` and `kite_token_history=UNKNOWN` for every name. This is an evidence observation, not a qualification certificate; `DATA_QUALIFIED=false` and `RUN_AUTHORIZED=false` remain unchanged.

Independent review reproduced the two source hashes, row dates and the all-date/pre-2023/2011–2022 counts. No separate reviewer receipt path was provided. Reproduction uses the ignored helper and test files:

```powershell
cd var/kite-qualification/2026-10-15/identity-evidence
python -m unittest -v test_build_identity_evidence.py
python build_identity_evidence.py --symbol-changes symbolchange.csv --name-changes namechange.csv --metadata-packet ../metadata-packet/metadata-packet.json --out public-identity-evidence.json
Get-FileHash -Algorithm SHA256 symbolchange.csv,namechange.csv,public-identity-evidence.json
```

The executed five-test suite passed. Paths: `var/kite-qualification/2026-10-15/identity-evidence/test_build_identity_evidence.py`, `build_identity_evidence.py`, `public-identity-evidence.json`, and `retrieval-register.json`. Source-evidence verdict: **GO for retaining these dated public event observations; NO-GO for continuous lineage or input qualification**.
