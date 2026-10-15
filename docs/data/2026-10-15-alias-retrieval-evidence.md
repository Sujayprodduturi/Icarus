# Alias retrieval evidence — 2026-10-15

Status: **candidate metadata only; not identity proof, universe qualification, or run authorization.**

The full captured symbol-change file was searched on both old and new sides. Across all 693 requested equity labels it yields 159 matching change rows; across all 150 labels lacking an exact current Kite NSE/EQ symbol it yields 85 rows. Within the 58 names observed as EQ on 2022-12-30 but unresolved in the captured Kite master, 35 names match 37 change rows. This replaces the earlier cohort-limited 85-of-150 search as the retrieval-discovery denominator.

All 58 late-2022 names have an exact ISIN in the sealed 2022-12-30 raw sample. The graph yields 24 modern-symbol candidates that also have a captured current Kite NSE/EQ row; the request file contains those 24 plus `NIFTY50`. The official current NSE EQ list gives the same ISIN for 21 of 24. Three current ISINs differ: `AMIORG→ACUTAAS` (`INE00FF01017→INE00FF01025`), `HEG→HEGAM` (`INE545A01016→INE545A01024`), and `IIFLWAM→360ONE` (`INE466L01020→INE466L01038`). These look like security-code changes and remain candidate bridges, not continuity proof.

The broader 150-name graph yields 49 current Kite candidates. Only 24 are pinned to the 2022-12-30 raw cohort, so only those 24 are in the prepared retrieval request. The remaining candidates are retained as discovery evidence and cannot borrow the late-2022 ISIN claim.

Pinned receipts:

- `symbolchange.csv`: 69,219 bytes; SHA-256 `69c0c5e18cca3350c2e07f7c8c4c1ebbfe38d81c8fa32c51f6ca9ea332e85f17`.
- sealed 2022-12-30 raw sample: 87,662 bytes; SHA-256 `636cb895992d40dfbf92dfe4b634d4e4000be6f218f6075c30631402683e19e7`.
- captured Kite master: 687,745 bytes; SHA-256 `48adffbfde4a9248ef5541b4273531671e87da3a4b745881125aef02a7bf0d22`.
- official current NSE `EQUITY_L.csv`, retrieved 2026-10-15: 183,984 bytes; SHA-256 `951c5d376d83ef0ddf8b040f9a52cd8b19388e7a51de8880af9a0b06ea0865a1`.
- generated evidence JSON: SHA-256 recorded in the ignored directory; generated request list: 25 symbols and accepted by the existing provenance validator.

Limitations: current NSE/Kite matches describe today's retrieval surface only. They do not establish historical token identity, continuous legal/security identity, merger or demerger treatment, adjustment behavior, or point-in-time eligibility. Current-master absence is not delisting evidence. No prices were downloaded or inspected, and no authenticated acquisition was started.
