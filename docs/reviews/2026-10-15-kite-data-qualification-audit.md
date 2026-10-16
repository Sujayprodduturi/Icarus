# Kite input qualification audit — 2026-10-15

Status: **bounded data QA complete and independently reproduced; source
qualification and strategy execution held**.
This is the D55 offline review, not a strategy trial or performance result.
The collection snapshot and the full 694-name requested denominator are retained.
The plan is [bounded data qualification](../plans/2026-10-15-kite-data-qualification.md).

## Established findings

- The corrected unresolved-name review uses only the 2,962 local daily archives
  from 2011-01-03 through 2022-12-30. All 150 unresolved names occur in that
  archive; 138 occur during 2015–2022. None has an exact current NSE/EQ match
  in the captured Kite master. This establishes retrieval gaps, not delisting
  or rename facts. No name is dropped. Receipt SHA-256:
  `49629df06c261e5effb6a889d59fc19192da3dcabbe83d3c7651227811ba97ec`.
  The earlier receipt scanned metadata after 2022 and is explicitly superseded.
- The initial rejected-candle helper sealed raw bytes but trusted unsealed
  manifest request bounds. Root and independent review rejected its receipt as
  final evidence. The corrected helper seals manifests before parsing, derives
  request identities and checks report interval/date bindings. Its new 326-chunk
  audit finds 446,592 candles, including 10,463 distinct invalid rows: 10,435
  with nonpositive OHLC and 28 with an invalid OHLC envelope. The other 436,129
  rows are only locally schema-valid; they are **not** admitted from quarantine.
  The corrected run took 4.888 seconds and 85,180 KiB peak RSS. Original raw
  archives remain unchanged. Evidence SHA-256:
  `a3bc611230f9df0196a1be479fb4b75c18d35f77a3f0b54b5da4d5e0e7c6a0f0`.
  The original receipts are preserved and superseded. Independent review reran
  the final helper on all 326 chunks: all content fields match the corrected
  receipt, excluding elapsed time/RSS. Root and reviewer separately pass all
  five invented fixture tests. Scoped content-QA review is GO; symbol/token
  lineage and source qualification are not established by this helper.
  Review receipt SHA-256:
  `5068ab46632e24fad1a2e2cd1a3a8435dfc6aab5e8b33a5d0672fe1f281b4fb9`.
- Root independently used direct predicates, rather than the builder helper,
  in an offline UID10002 container to reproduce the saved AARTIDRUGS Apr–Jun
  2015 chunk: 1,500 candles, three nonpositive rows and no envelope violations.
  Both raw and manifest bytes matched the pinned snapshot. This explains the
  rejection in the resumed snapshot; it cannot prove the contents of the first
  failed response that was discarded before quarantine capture existed.
- The simulator currently requires a complete M15 grid and exact equality
  between daily OHLCV and first-open/max-high/min-low/last-close/summed-volume
  (`icarus/engine/timed_simulation.py`, validation before execution). Therefore
  separately valid official daily and vendor intraday records are not yet
  demonstrated to satisfy the current simulator contract.
- The daily benchmark projection requires an observed index event at session
  close, available by that close (`icarus/engine/timed_runner.py`). A candle's
  last value does not establish that event or publication time.

## Fixed paired sample

The fixed symbols are INFY, RELIANCE, HDFCBANK, TCS, AARTIDRUGS and NIFTY50;
dates are 2015-01-09 and 2022-12-30. The offline helper opened 23 historical
response artifacts plus the captured master, checked raw and manifest hashes
against the seal, and emitted counts, timestamps and equality booleans only.
This is not a full-range coverage test or an authoritative calendar certificate.

- On 2022-12-30 all six instruments have one daily row and 25 M15 labels on
  the candidate regular-session grid, 09:15 through 15:15 IST.
- On 2015-01-09 only Nifty has all 25 M15 labels. Four stock chunks are accepted
  but contain no candle for that date; the TCS chunk is quarantined. Every daily
  row exists. Missing M15 is explicit, never reconstructed from daily prices.
- Seven pairs are comparable. Exact equalities are: open 7/7, high 4/7, low 2/7,
  close 0/7 and volume 2/7. Thus none satisfies the current exact-aggregate gate.
  These facts do not identify the cause of every difference or prove current
  adjustment bases. They do establish that the feeds cannot be plugged into
  the current exact-aggregate contract unchanged.

Evidence: `var/kite-qualification/2026-10-15/bar-audit/evidence/paired-day-m15-compatibility.json`,
SHA-256 `c1f704c33876096fb1b96ca08f20b8eafd4e8d3b0d072032ecdf0f60b8cbadc4`.
Independent offline rerun reproduced exactly the same bytes. Root separately
recomputed the seven-pair equality counters from the receipt and inspected the
helper's direct comparisons. Review SHA-256:
`c731d9d01876b3b03cb51d17f1aeb83979d3da7a35c90265b0640d5739dc8881`.

## Source evidence and its limits

Checked primary sources on 2026-10-15:

- [Kite historical API documentation](https://kite.trade/docs/connect/v3/historical/)
  defines OHLCV arrays and offset-aware labels. Retain original labels and
  convert to UTC. It does not supply original publication or revision history.
- [Kite staff's candle-formation explanation](https://kite.trade/forum/discussion/9303/last-candle-missing-in-historical-hourly-data)
  supports start labels: the 09:15 hourly candle spans the following hour and
  the 15:15 candle spans the remaining session. A source-specific M15 start/end
  projection still needs a pinned calendar and local grid checks. Modeled
  completion at bar end is a declared derivation, not raw availability evidence.
- [Kite's 2020 adjustment discussion](https://kite.trade/forum/discussion/8979/how-accurate-is-historical-data)
  records then-incomplete adjustment of older intraday history. That dated
  warning does **not** prove the 2026 snapshot remains unadjusted. Current
  daily/intraday price and volume bases require reconciliation before either
  applying or omitting additional corporate-action factors.
- [NSE's index FAQ](https://www.nseindia.com/static/products-services/indices-faqs)
  describes Nifty closing values using constituent closing prices calculated
  from the final half hour. Preserve official daily close separately from a
  final intraday candle; do not infer equality or exact-time availability.
- [Kite's historical coverage discussion](https://kite.trade/forum/discussion/7246/historical-data-availability)
  describes instrument-dependent coverage. The local accepted Nifty M15
  snapshot starts 2015-01-09, leaving the requested earlier sessions unavailable.
- [Kite terms](https://kite.trade/terms/) do not provide sufficiently clear
  evidence here for the proposed durable private archive, backups and
  post-subscription retention. Rights remain unresolved; this audit makes no
  legal permission/prohibition conclusion and sends no vendor message.

Detailed non-price evidence stays under
`var/kite-qualification/2026-10-15/source-evidence/source-evidence.json`.
SHA-256: `892326ccd446e02b720bcec5b32d346644e08dd9a26cffd129e36d1f6fa55e60`.
Local action caches and the archive-presence calendar are useful inputs, but
are not already qualified security lineage, special-session or availability
certificates. Prior completed quantity is a possible registered liquidity
proxy; the current opening candle's eventual volume remains forbidden.

## Source evidence continuation — 2026-10-15

The paired adapter published at `21978fa` passed hosted CI (3,328 tests,
four skips) and its separate resource proof. This verifies software, not
actual source qualification. See the [metadata inventory](../data/2026-10-15-source-evidence-inventory.md)
and [primary-source semantics](../data/2026-10-15-source-semantics-evidence.md).

The bounded local metadata packet retains all 694 requested names. All 50
existing NSE action caches are hash-pinned; 25,133 source rows yield 24,659
unique full rows and 474 exact duplicates with all source occurrences retained.
247 same-symbol/series/date rows are flagged as ambiguous; zero conflicting
versions under the narrower same-subject key does not prove zero ambiguity.
85 of 150 currently unmatched names have dated ISIN-bearing action evidence.
This does not resolve retrieval gaps, continuous lineage or historical tokens.

Root independently passes seven helper tests and reproduces ABAN's nine dated
observations and ISIN directly from source caches. Independent review verifies
all 50 files, the three additional input pins, all requested observations and
mapping dictionaries, calendar metadata and counts. Review receipt SHA-256:
`199556910970d74a72974a6a8e48276e4551219337d367985a6541e2cdb3e356`.
Actual qualification remains NO-GO. Next: dated public security/name-change and
calendar evidence, then concrete action-basis reconciliation; support questions
remain unsent. No actual strategy, trial ledger or lockbox evaluation occurred.
Public evidence continuation also pins the official NSE symbol/company-name CSVs
and three dated calendar PDFs. Only 18 of the 85 unmatched ISIN-bearing names
have a directly matched change event effective inside 2011–2022; those events
do not establish continuous lineage. The weekday-only discovery defect is
corrected at source 6b71533 and its reintroduction is caught; existing cached
axes remain incomplete. See the public reports and weekend build review.

## Ranked fix list

| ID | Finding | Status | Next action |
|---|---|---|---|
| K1 | Rejected raw candles and empty responses | OPEN | Preserve quarantines and explicit gaps; no repair, filtering into accepted coverage or silent promotion. |
| K2 | 150 unmatched historical names | PARTLY DONE | All 19 conditionally material pilot gaps now have retrieval candidates: 13 modern names, two BE-series routes and four dated legacy-token leads. None is recovered or admitted history yet. Retrieval-day provider identity plus current official ISIN and dated NSE lineage is sufficient for unchanged cash equities; per-day old broker-token archives are not a universal gate. Legacy/changed-series candidates require explicit quarantine. Retain all requested names. See [routes](../data/2026-10-16-missing-history-routes.md). |
| K3 | Daily/intraday compatibility | PARTLY DONE; ACTUAL PAIR BLOCKED | Independently reproduced 30-cell diagnosis separates vendor/raw basis differences from daily/intraday capture differences. Kite DAY and first M15 opens coincide in all 30 cells; three stocks differ from official raw while three controls match daily OHLCV. Root independently reproduces INFY. Event-derived factors, vendor rounding and historical share quantities must be reconciled before admission; neither observed ratios nor widened tolerances certify a transform. See [diagnosis](../data/2026-10-16-price-basis-diagnosis.md). |
| K4 | Nifty bar versus exact observation semantics | PARTLY DONE | Descriptive software verified; exact point unavailable. Reviewed candle lane at 1cd3441 retains modeled availability and per-comparison captured-record intervals, with no aggregate alpha or promotion. Keep strict mode unchanged and do not fabricate official close events or exact fill-time points. |
| K5 | Source basis, calendar, rights and availability | PARTLY DONE; ADMISSION BLOCKED | Bounded 2021–2022 calendar evidence is reviewed. As checked 2026-10-16, Kite API terms section 4b restrict database/permanent-copy use, while NSE website terms Use 8/9 restrict simulation/automated collection; NSE's personal-download allowance is not a proved simulation exception. Applicable purpose-specific terms or permission remain unresolved. These are separate source-use questions, not a blanket legal conclusion. Provider questions remain UNSENT. Bind only proved facts and preserve unknown publication/revision semantics. See [review](2026-10-16-data-resolution-review.md) and [daily proposal](../plans/2026-10-16-daily-descriptive-pilot.md). |
| K6 | Concrete bundle and resource qualification | OPEN | Qualify the claimed interval and required warm-up, then its concrete bundle/resources. A bounded pilot need not wait for unrelated older-year calendar gaps; its success would not certify full-history readiness. |
| K7 | Weekday-only archive discovery omitted weekend candidates | PARTLY DONE | Scanner repair and postcommit fault proof pass at 6b71533. Existing cached axis still lacks weekend coverage; reconcile authoritative sessions before a separately bounded rebuild. |
| K8 | Legacy EQ rows do not establish stock instrument class | CLASS EVIDENCE RESOLVED FOR THREE; DISPOSITION OPEN | Reviewed metadata shows BANKBEES/NIFTYBEES below turnover on all five pilot dates; their ETF costs are not a pilot gate. LIQUIDBEES passes the conditional screen but is fixed-income, outside PRD sections 1/29.2's equity scope. Bind a counted CLASS_INELIGIBLE_FIXED_INCOME disposition in the eventual bundle; retain its requested-label record. No blanket equity-ETF exclusion is inferred. See [dated class evidence](../data/2026-10-15-pilot-instrument-classes.md) and [review](2026-10-16-data-resolution-review.md). |

The initial audit led to the approved
[paired-source adapter](../plans/2026-10-15-paired-source-adapter-proposal.md),
which is now implemented and locally verified. Its independently required
shared economic basis and deterministic checks remain admission conditions;
diagnostics do not replace them. The separate descriptive candle benchmark
lane is also implemented, independently reviewed and locally verified at
1cd3441. The next task is concrete source/input qualification, rather than
rebuilding either adapter. See the [pilot candle check](../data/2026-10-15-pilot-candle-coverage.md),
[daily-source provenance](../data/2026-10-15-pilot-daily-source-provenance.md),
and [current identity review](2026-10-15-final-dated-identity-review.md).

No product runtime, risk thresholds, numeric validation gates, trial ledger,
inference or live-order code changes in this unit. The 2023+ price lockbox is
untouched. `DATA_QUALIFIED=false`; actual-study `RUN_AUTHORIZED=false`.

The published prerequisite `3a560e722f5ded6685098c066986df5b162d56ec` has
successful hosted CI `38688431937` and resource proof `38688431887`, freshly
checked on 2026-10-15. Those jobs do not qualify this data or cover a later commit.
