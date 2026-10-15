# Pilot daily-source provenance — 2026-10-15

**The retained daily cache matches the official raw NSE records for the five pilot dates.** This is a bounded provenance check, not a strategy run or source-pair qualification. `DATA_QUALIFIED=false` and actual-study `RUN_AUTHORIZED=false` remain unchanged.

Independent final review is **GO within this scope**: all ten source hashes, receipt links, result counts and three invented tests were independently verified in the [final reconciliation review](../reviews/2026-10-15-final-dated-identity-review.md).

## Plan and controls

An independent reviewer approved comparing only the already sealed 2022-12-26 through 2022-12-30 raw NSE ZIPs with the five previously frozen daily cache files. All ten file hashes were verified against the earlier acquisition/cache receipts before copying them; a new manifest was frozen before numeric decoding. The helper checks every CSV row's trade date before selecting exact symbol plus EQ series, refuses duplicate source identities, and compares named OPEN/HIGH/LOW/CLOSE/TOTTRDQTY/TOTTRDVAL columns to the cache's declared six-field order using exact decimal arithmetic. Every requested label remains present. No aliases, tolerance, provider-token substitution, price values, returns or strategy results are emitted.

Three invented fixture tests pass, covering exact decimal equality, field mismatch, separate missing-cache/source/both states, wrong/lockbox dates and duplicate source identity. A failing fixture first exposed the original helper's ambiguous missing-both label; the correction and original result are retained. Both tests and actual comparison ran with UID 10002, network disabled, a read-only root and scoped input mount, dropped capabilities, `no-new-privileges`, at most 1 GiB and two CPUs. Only the output directory was writable; no repository/home/SDK/credential/socket mount was provided.

## Result

On **each** of the five dates, all 693 exact requested names are retained: 597 match all six fields exactly, 96 are absent from both exact-name sources, zero have a field mismatch, and zero are present in only one source. These are exact-name source comparisons, not 693 proven distinct security identities or a final eligible universe. INFY separately matches all six fields on all five dates and is included once in those totals.

Together with the independently reproduced INFY M15 mismatch in the [candle coverage check](2026-10-15-pilot-candle-coverage.md), this localizes that mismatch to the relationship between the vendor intraday records and the official daily record. It does not establish whether adjustment, revision or another vendor convention causes it. There is no basis to silently rewrite the official daily cache or loosen the paired-source contract.

## Frozen evidence

- Manifest: `b20a62178b1c4a19fcacf27a762f7369905fd0d493d89de5fe3482c627fc9972`.
- Final result v2: `0c9f0ec0df48a9599b43f74a7353784167723763394f65c42bbfecd4472fe2f6`.
- Final helper: `05e51e215ff1e1ad45a89fac63aaa5ed00dd44dca9a57f8c1c30d3bb8a7b6521`.
- Fixture tests: `1b7de88f0a66c5ba6c523d661774bbcbf2c99b4e1377b3aff85fd36b8507861f`.
- Preserved original result: `a5193b8203c24311b64f3028694378f2897c352a0886403fb9ddd97f4143ee30`; its missing-cache category did not distinguish absence from both sources and is superseded by v2.

All inputs, code and receipts are retained under ignored `var/kite-qualification/2026-10-15/pilot-daily-raw-provenance/`. Original source artifacts, risk settings, mappings, trial ledger and source qualification were not changed. No provider was contacted.
