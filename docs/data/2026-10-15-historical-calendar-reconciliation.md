# Historical NSE cash-market calendar reconciliation - 2011-2022

**As of:** 2026-10-15 IST
**Scope:** public, unauthenticated NSE/NSE Archives circular metadata and sealed circular PDFs only. No price data, broker path, credential, strategy, lockbox or live-order access occurred.

## Result

`CALENDAR_QUALIFIED=false`.

This pass establishes the annual Capital Market holiday notice for every year from 2011 through 2022, the corresponding Muhurat session notice for every year, two amendment chains, two Saturday Union Budget sessions, and one additional Sunday security-limited live session. It is a substantial candidate inventory, not yet the canonical session calendar. Annual notices enumerate closures and weekend holidays; they do not positively assert ordinary hours for every remaining weekday. The legacy weekday-only calendar remains non-authoritative.

## Evidence method and precedence

The public NSE circular archive API was queried separately for each calendar year and the complete subject list for `NSE/CMTR/*` was reviewed, rather than treating search-engine misses as absence. Candidate PDFs were then retrieved from `nsearchives.nseindia.com`, checked as Capital Market Segment notices, and hash-pinned in `var/calendar-reconciliation/2026-10-15/manifest.json` (29 PDFs, 4,436,601 bytes).

Typed observations use this precedence:

1. A later circular that says `partial modification`, `revised`, or equivalent overrides only the fields it changes in the cited predecessor.
2. A special live-session circular overrides the annual holiday label for the named date, instruments and session components only.
3. A security-limited session never implies that the whole cash market traded.
4. Mock trading, clearing-only notices, F&O/currency/commodity/SLBS notices and DR-location changes without different market hours do not create calendar sessions.
5. Absence of a circular subject or price archive row is not evidence of closure or ordinary hours.

## Annual closure source inventory

Each source below is page 1 unless stated otherwise. `weekday/weekend` counts refer to the two tables in the circular, not inferred sessions.

| Calendar year | Annual Capital Market source | Published closure observations | Muhurat date named by annual source |
|---|---|---:|---|
| 2011 | [NSE/CMTR/16348](https://nsearchives.nseindia.com/content/circulars/cmtr16348.pdf), 2010-11-22, circular 126 | 14 weekday + 6 weekend | 2011-10-26 |
| 2012 | [NSE/CMTR/19539](https://nsearchives.nseindia.com/content/circulars/CMTR19539.pdf), 2011-12-09, circular 066/2011, pages 1-2 | 15 weekday + 5 weekend | 2012-11-13 |
| 2013 | [NSE/CMTR/22317](https://nsearchives.nseindia.com/content/circulars/CMTR22317.pdf), 2012-12-17, circular 79/2012 | 13 weekday + 6 weekend | 2013-11-03 (Sunday) |
| 2014 | [NSE/CMTR/25326](https://nsearchives.nseindia.com/content/circulars/CMTR25326.pdf), 2013-12-20, circular 99/2013 | 17 weekday + 2 weekend | 2014-10-23 |
| 2015 | [NSE/CMTR/28337](https://nsearchives.nseindia.com/content/circulars/CMTR28337.pdf), 2014-12-12, circular 66/2014 | 15 weekday + 4 weekend | 2015-11-11 |
| 2016 | [NSE/CMTR/31297](https://nsearchives.nseindia.com/content/circulars/CMTR31297.pdf), 2015-12-07, circular 73/2015 | 15 weekday + 4 weekend | 2016-10-30 (Sunday) |
| 2017 | [NSE/CMTR/33746](https://nsearchives.nseindia.com/content/circulars/CMTR33746.pdf), 2016-12-05, circular 64/2016 | 13 weekday + 5 weekend | 2017-10-19 |
| 2018 | [NSE/CMTR/36475](https://nsearchives.nseindia.com/content/circulars/CMTR36475.pdf), 2017-12-12, circular 71/2017 | 16 weekday + 3 weekend | 2018-11-07 |
| 2019 | [NSE/CMTR/39612](https://nsearchives.nseindia.com/content/circulars/CMTR39612.pdf), 2018-12-07, circular 115/2018, pages 1-2 | 15 weekday + 4 weekend | 2019-10-27 (Sunday) |
| 2020 | [NSE/CMTR/42877](https://nsearchives.nseindia.com/content/circulars/CMTR42877.pdf), 2019-12-11, circular 146/2019 | 12 weekday + 7 weekend | 2020-11-14 (Saturday) |
| 2021 | [NSE/CMTR/46623](https://nsearchives.nseindia.com/content/circulars/CMTR46623.pdf), 2020-12-11, circular 113/2020 | 14 weekday + 5 weekend | 2021-11-04 |
| 2022 | [NSE/CMTR/50560](https://nsearchives.nseindia.com/content/circulars/CMTR50560.pdf), 2021-12-10, circular 117/2021, pages 1-2 | 13 weekday + 5 weekend | 2022-10-24 |

These twelve sources contain 172 weekday-closure rows and 56 weekend-holiday rows. The Muhurat date appears inside the holiday list but is explicitly announced as a live session whose timings follow separately.

## Exact special live-session observations

All times below are IST as printed. `normal` is the continuous cash-market session; the source retains other components separately.

| Date | Type and scope | Normal market | Other typed components | Authoritative source and precedence |
|---|---|---|---|---|
| 2011-10-26 | Muhurat, Capital Market | 16:45-18:00 | pre-open 16:30-16:38; block 16:45-17:20; closing 18:10-18:20 | [CMTR19187](https://nsearchives.nseindia.com/content/circulars/CMTR19187.pdf), p1; follows annual CMTR16348 |
| 2012-11-11 (Sun) | Dhanteras; **Gold ETFs only** | 11:00-15:30 | closing 15:40-15:50; page 2 names 14 eligible ETF symbols and separate settlement | [CMTR22063](https://nsearchives.nseindia.com/content/circulars/CMTR22063.pdf), pp1-2; instrument-scoped override only |
| 2012-11-13 | Muhurat, Capital Market | **15:45-17:00** | pre-open 15:30-15:38; block 15:45-16:20; SME auction 15:50-16:20; closing 17:10-17:20 | [CMTR22083](https://nsearchives.nseindia.com/content/circulars/CMTR22083.pdf), p1, partially modifies [CMTR22027](https://nsearchives.nseindia.com/content/circulars/CMTR22027.pdf), p1. The earlier 16:30 normal close and 16:40-16:50 closing session are superseded. |
| 2013-11-03 (Sun) | Muhurat, Capital Market | 18:15-19:30 | pre-open 18:00-18:08; block 18:15-18:50; SME auction 18:20-18:50; illiquid auction 18:30-19:15; closing 19:40-19:50 | [CMTR24773](https://nsearchives.nseindia.com/content/circulars/CMTR24773.pdf), p1 |
| 2014-10-23 | Muhurat, Capital Market | 18:30-19:30 | pre-open 18:15-18:23; block 18:30-19:05; illiquid auction 18:35-19:20; closing 19:40-19:50 | [CMTR27779](https://nsearchives.nseindia.com/content/circulars/CMTR27779.pdf), p1 |
| 2015-02-28 (Sat) | **Union Budget**, full Capital Market live session | 09:15-15:30 | pre-open 09:00-09:08; block 09:15-09:50; six illiquid auctions 09:30-15:30; closing 15:40-16:00 | [CMTR28939](https://nsearchives.nseindia.com/content/circulars/CMTR28939.pdf), p1 |
| 2015-11-11 | Muhurat, Capital Market | 17:45-18:45 | pre-open 17:30-17:38; block 17:45-18:20; illiquid auction 17:50-18:35; closing 18:55-19:05 | [CMTR31047](https://nsearchives.nseindia.com/content/circulars/CMTR31047.pdf), p1 |
| 2016-10-30 (Sun) | Muhurat, Capital Market | 18:30-19:30 | pre-open 18:15-18:23; block 18:30-19:05; illiquid auction 18:35-19:20; closing 19:40-19:50 | [CMTR33424](https://nsearchives.nseindia.com/content/circulars/CMTR33424.pdf), p1 |
| 2017-10-19 | Muhurat, Capital Market | 18:30-19:30 | pre-open 18:15-18:23; block 18:30-19:05; illiquid auction 18:35-19:20; closing 19:40-19:50 | [CMTR35993](https://nsearchives.nseindia.com/content/circulars/CMTR35993.pdf), p1 |
| 2018-11-07 | Muhurat, Capital Market | 17:30-18:30 | block 17:00-17:15; pre-open 17:15-17:23; illiquid auction 17:35-18:20; closing 18:40-18:50 | [CMTR39216](https://nsearchives.nseindia.com/content/circulars/CMTR39216.pdf), p1 |
| 2019-10-27 (Sun) | Muhurat, Capital Market | **18:15-19:15** | block 17:45-18:00; pre-open 18:00-18:08; illiquid auction 18:20-19:05; closing 19:25-19:35; modification cutoff 19:45 | [CMTR42483](https://nsearchives.nseindia.com/content/circulars/CMTR42483.pdf), p1, partially modifies [CMTR42403](https://nsearchives.nseindia.com/content/circulars/CMTR42403.pdf), visually inspected p1. The revised notice changes the original illiquid auction 18:15-19:15, closing 19:20-19:30 and modification cutoff 19:40; revised fields win. |
| 2020-02-01 (Sat) | **Union Budget**, full Capital Market live session | 09:15-15:30 | block windows 08:45-09:00 and 14:05-14:20; pre-open 09:00-09:08; special pre-open 09:00-09:45; illiquid auctions 09:30-15:30; post-close 15:40-16:00; modification cutoff 16:15 | [CMTR43290](https://nsearchives.nseindia.com/content/circulars/CMTR43290.pdf), p1 |
| 2020-11-14 (Sat) | Muhurat, Capital Market | 18:15-19:15 | block 17:45-18:00; pre-open 18:00-18:08; illiquid auction 18:20-19:05; closing 19:25-19:35; modification cutoff 19:45 | [CMTR46230](https://nsearchives.nseindia.com/content/circulars/CMTR46230.pdf), p1 |
| 2021-11-04 | Muhurat, Capital Market | 18:15-19:15 | block 17:45-18:00; pre-open 18:00-18:08; illiquid auction 18:20-19:05; closing 19:25-19:35; modification cutoff 19:45 | [CMTR50050](https://nsearchives.nseindia.com/content/circulars/CMTR50050.pdf), p1 |
| 2022-10-24 | Muhurat, Capital Market | 18:15-19:15 | block 17:45-18:00; pre-open 18:00-18:08; illiquid auction 18:20-19:05; closing 19:25-19:35; modification cutoff 19:45 | [CMTR54023](https://nsearchives.nseindia.com/content/circulars/CMTR54023.pdf), p1 |

Known weekend live observations are therefore seven dates: 2012-11-11, 2013-11-03, 2015-02-28, 2016-10-30, 2019-10-27, 2020-02-01 and 2020-11-14. The 2012 Dhanteras date is restricted to Gold ETFs; the other six are whole-segment special sessions.

## 2022 disposition

The archive API returned 2022 Capital Market Trade circular subjects across the full year. Within that department, the only whole-market holiday/special-time item affecting the 2022 calendar was CMTR54023 Muhurat; the annual source was published in 2021 as CMTR50560. Numerous Saturday notices explicitly say `Mock trading`; they are excluded. CMTR51475, CMTR51546 and CMTR53573 move live trading to the disaster-recovery site on ordinary weekdays and do not state different market hours, so they do not create exceptions. Security-specific pre-open notices do not alter the market-wide session calendar.

This supports a **2022 complete candidate for published annual closures and published market-wide special sessions**, with one important limit: circular-subject review is strong positive evidence, not proof that no intra-day outage occurred without a CMTR circular. No Capital Market holiday amendment or withdrawal was identified in the full 2022 CMTR subject inventory. That is recorded as `NOT_IDENTIFIED_IN_ARCHIVE_METADATA_REVIEW`, never as proof of nonexistence.

## Known limits and next action

- Annual closure rows still need machine-readable transcription with independent row-count/date validation before runtime admission.
- The archive metadata pass identified historical `Sun Outage - Capital Market Segment` notices in 2011-2013, but several are ZIPs and may describe planned infrastructure maintenance rather than a trading outage. They remain unclassified and must not be converted into session observations from title alone.
- Extended live-trading notices and DR-site notices exist in 2011-2022. Most appear to preserve ordinary cash-market hours or extend operational availability; their PDFs need classification only where they change tradable session boundaries.
- Unexpected intra-day interruptions and resumptions may be announced through channels other than annual/Muhurat subjects. A bounded incident search and archive-presence discrepancy check remain necessary; impossible negative proof of every outage is not required.
- 2019 CMTR42403 is image-only in text extraction. Its page 1 was rendered and visually inspected in this pass; CMTR42483's three revised fields are recorded above. Any future automated extractor still needs an image/OCR refusal or explicit manual-observation path rather than treating empty extracted text as an empty circular.

Next, transcribe and independently validate the 2022 annual rows plus CMTR54023 into typed candidate records, compare them against the widened archive-presence axis, then classify the named 2011-2013 Sun Outage packages and the extended-live notices that could change normal-market boundaries. Do not infer ordinary sessions for unresolved dates and do not make the runtime consume this document directly.

## Normal-session baseline and dated exceptions

The baseline is now evidence-backed for this development window. NSE's 2009-12-17 press release states that the cash-market opening moved to 09:00 effective 2010-01-04 and that the normal close remained 15:30. NSE's 2010-11 annual report states that the 15-minute call-auction pre-open launched effective 2010-10-18. It allocates 09:00-09:08 to order entry, four minutes to matching and three minutes to transition. From 2011 onward, the resulting ordinary schedule is therefore:

| Component | Baseline IST | Authority and limit |
|---|---|---|
| pre-open order entry | 09:00-09:08, system-random closure in the last minute | NSE 2010-11 annual report, page 11; applies initially to the eligible index-security set, not every security |
| pre-open match/transition | after order entry through 09:15 | same source; four matching minutes plus three transition minutes |
| normal / odd-lot cash market | 09:15-15:30 | repeated verbatim in CMTR17674 p1, CMTR19202 p1, CMTR20587 p1 and CMTR23346 p1; later full-segment Budget notices CMTR28939 and CMTR43290 retain the same normal hours |

For candidate construction, `09:15-15:30` is the normal cash-market baseline from 2011-01-01 through 2022-12-31 **only on dates established as sessions**. It is not a rule that manufactures a session on every unknown weekday. A dated official live-session, closure, instrument-scoped extension, halt or resumption overrides only its named date/scope/components.

### 2011-2013 Sun Outage classification

The six named notices are not exchange outages. Each says member VSAT connectivity may be affected geographically and explicitly says the Capital Market would **not** close and trading would continue normally. They therefore create `CONNECTIVITY_RISK_NO_SESSION_OVERRIDE` observations, not closed intervals:

| Notice | Risk window printed on page 1 | Calendar classification |
|---|---|---|
| CMTR17048, 2011-02-21 | 2011-03-05..03-19, broadly 11:00-11:35 | no session override |
| CMTR18818, 2011-09-08 | 2011-09-25..10-09, broadly 10:40-11:10 | no session override |
| CMTR20119, 2012-02-27 | 2012-03-04..03-18, broadly 11:00-11:35 | no session override |
| CMTR21635, 2012-09-06 | 2012-09-24..10-08, broadly 10:40-11:10 | no session override |
| CMTR22820, 2013-02-26 | 2013-03-05..03-18; INSAT-3A 11:00-11:35 and INSAT-3E 13:55-14:30 | no session override |
| CMTR24357, 2013-09-04 | 2013-09-24..10-08; INSAT-3E 13:35-14:10 | no session override |

### 2011-2013 extended live trading

These are real tradable extensions, but every one is restricted to the Gold ETFs enumerated in its annexure. The ordinary market remains 09:15-15:30; only the named instruments reopen after an order-cancellation period.

| Date | Event | Instrument-scoped extension | Source |
|---|---|---|---|
| 2011-05-06 | Akshaya Tritiya | Gold ETFs only: cancellation 16:25-16:30; normal market reopens 16:30 and closes 21:00; no second closing session | CMTR17674 pp1-3 |
| 2011-10-24 | Dhanteras | Gold ETFs only: cancellation 16:25-16:30; reopens 16:30 and closes 20:00; no second closing session | CMTR19202 pp1-4 |
| 2012-04-24 | Akshaya Tritiya | Gold ETFs only: cancellation 16:25-16:30; reopens 16:30 and closes 20:00; no second closing session | CMTR20587 pp1-3 |
| 2013-05-13 | Akshaya Tritiya | Gold ETFs only: cancellation 16:25-16:30; reopens 16:30 and closes 19:00; no second closing session | CMTR23346 pp1-3 |

These notices also independently reproduce the ordinary 09:15-15:30 baseline. They must be represented as named-security intervals; applying their late close to unrelated equities would be a scope error.

### 2021-02-24 halt boundary

NSE's published financial-results material confirms that its trading system halted on 2021-02-24 because telecom-link failures made the primary storage network inaccessible and also affected clearing, index and surveillance systems. That establishes a genuine exchange-level exception, unlike the Sun Outage warnings.

SEBI Settlement Order `SO/VV/AS/2023-24/6558`, paragraph 1, supplies the exact sequence from the regulator's investigation and NSE/NCL submissions: all NSE segments halted at **11:40**; a recovery pre-open began at **15:30**; normal trading resumed at **15:45** and was extended through **17:00**. These are admitted as official regulator-attested facts with `source_authority: SEBI_PRIMARY_REGULATOR`, distinct from `NSE_PRIMARY_EXCHANGE`. They are not inferred from price gaps or secondary reporting. The official URL is `https://www.sebi.gov.in/sebi_data/attachdocs/jun-2023/1687944013686.pdf`.

The SEBI host failed DNS resolution in two direct retrieval attempts from this environment, although the official document is publicly indexed and its paragraph was read through the web research surface. Therefore the exact fields are present in the candidate, but the SEBI bytes are **not locally sealed yet**. This is a provenance gap, not a factual ambiguity; admission to runtime still requires the PDF byte hash.

## Typed candidate and complete date axis

Ignored `var/calendar-reconciliation/2026-10-15/calendar-2022-manual.json` contains the 24-row 2022 transcription fixture: 13 annual weekday closure rows, five separately labelled weekend-holiday rows, and six components of the 2022-10-24 Muhurat session. Each record carries ISO date, explicit Capital Market scope, instrument scope, start/end where applicable, circular reference, sealed SHA-256, source page/table-row and `precedence_over`.

Ignored `calendar-2011-2022-candidate.json` is the full candidate. It contains **252 typed source observations**: all 228 annual rows (172 weekday-table rows plus 56 weekend-table rows) and 24 special-session component observations. It also contains one separately typed regulator-attested outage and a resolved **4,383-date** axis from 2011-01-01 through 2022-12-31. Resolution is deterministic: dated scoped special; official annual closure; ordinary weekend closure; otherwise weekday baseline 09:15-15:30. The 2021-02-24 status is `EXCEPTION_WITH_INTRADAY_HALT`. Instrument-limited Gold ETF extensions remain named-security scope and never broaden the whole market.

The validator and full-candidate builder were written test-first under the same ignored directory. Eight tests cover both accepted files, exact 228/172/56 row counts, the 4,383-date axis, invalid dates, reversed or unmarked cross-midnight times, unknown or instrument-mismatched scopes, conflicting duplicates and missing precedence. Fresh result: **8 tests PASS**. The builder independently refuses any annual PDF whose unique in-year date count differs from its published table counts. These helpers and JSON are evidence tooling only and are not imported by Icarus runtime.

The practical next step is independent review of the 252 observations, the special-session scopes, the SEBI paragraph and the rule-resolved axis, then archive-presence discrepancy comparison. The default rule is baseline-in-force-unless-dated-official-override; it does not require proving that no unrecorded outage ever occurred. `CALENDAR_QUALIFIED` remains false until that review and the SEBI byte seal complete.

## Final-review correction candidate (supersedes the earlier candidate counts)

The rebuilt ignored candidate has SHA-256 `db77585a8a39c677381ec1b8ead06751362100a40459f4163f0de55df7e29877`, **315 observations** (228 annual rows and 87 separately typed session components), and 4,383 unique ordered civil dates. Its date axis now has separate `market_wide_status` and `scoped_status` fields. In particular, Gold-ETF-only trading on Sunday 2012-11-11 leaves the market-wide status `CLOSED_WEEKEND_RULE`; it cannot promote the whole Capital Market.

All five Gold ETF notices now carry their exact annexure `SYMBOL:SERIES` lists. The four extensions represent cancellation 16:25-16:30 and extended normal trading separately. The Dhanteras notice represents normal and closing separately. Every old Muhurat and Budget notice now emits each printed pre-open, normal, block, auction, closing/post-close, and trade-modification interval as an individual observation. The revised 2012 and 2019 notices remain the controlling fields; no interval is synthesized from a cutoff alone.

The sealed manifest covers **40 source records: 36 PDFs and 4 ZIPs**, 6,282,617 bytes total. Observation references and hashes are checked against it. The pinned tooling contract is Python 3.12 with `pypdf==6.1.1`, invoked as `uv run --with pypdf==6.1.1 python`. Eleven tests pass, including scope-aware Sunday resolution, exact named instruments, separated extension components, complete/unique date-axis coverage, outage field order, manifest provenance, closure-table counts, invalid dates/times/scopes, duplicate conflicts, and closure precedence.

The non-authoritative `var/calendar.json` archive-presence comparison reads only date strings, never price content. It has 2,962 session dates for 2011-2022 versus 2,972 market-wide candidate dates. The candidate records 11 candidate-only dates and one legacy-only date (`2013-11-14`) verbatim in `archive_presence_discrepancy`; these are review leads, not automatic calendar overrides.

The SEBI observation is bound to a canonical structured-capture hash `dd27d1e0ced4be9afc6362180eefcb1594619ed498f74de493af41c92b46dd78` with official URL, retrieval time, capture method, paragraphs, exact fields, and `raw_pdf_sha256: null`. Paragraph 1 supports the declared 11:40 halt, 15:30 recovery pre-open, 15:45 resumption and 17:00 close. Paragraph 3 says equity-cash trades from 10:06 through 11:43 lacked online risk management. Therefore 11:40 is a conservative modeled exclusion boundary, not a claim about the final equity-cash execution; any intersecting M15 bar must be excluded.

`CALENDAR_QUALIFIED=false`. Remaining external review questions are the 12 archive-presence discrepancies and acceptance of the transparent regulator-derived capture without locally retrieved SEBI PDF bytes. No claim of full qualification is made.

## Bounded 2021-2022 evidence certificate

For the predeclared late-2022 engineering pilot with 2021 warmup, the separate ignored certificate `calendar-2021-2022-evidence-certificate.json` covers exactly 730 civil dates, 37 annual holiday rows (28 weekday-table and nine weekend-table rows), both Muhurat sessions with six components each, and the 2021-02-24 halt/resumption record. Its SHA-256 is `4d7902c85909cba50b00dfccd6c0d3b1051225ba547e33bc010b56ad0e683c91`. It is evidence-only and remains `calendar_qualified: false` pending independent review. The transparent hash-bound SEBI structured capture is an admissible derived-primary record for this review; lack of locally retrieved raw bytes is recorded as a provenance limit, not an automatic rejection rule.

This bounded certificate does not depend on completing the older calendar. The full 2011-2022 candidate is now explicitly incomplete: newly discovered primary/discovery leads identify additional Saturday live sessions on 2012-01-07, 2012-03-03, 2012-04-28, 2012-09-08, 2013-05-11 and 2014-03-22 that are absent from the current observations. They require original notice retrieval and exact component transcription. Therefore the 12 legacy-cache discrepancies are not exhaustive evidence of all missing weekend sessions, and the full-history candidate must not be qualified.

Four weekday discrepancy amendments are positively identified but not yet admitted to the sealed candidate because direct NSE archive DNS retrieval failed in this environment: NSE/CMTR/24977 swaps the 2013 holiday from November 14 to November 15; NSE/CMTR/27792 adds the 2014-10-15 Maharashtra election holiday; NSE/CMTR/40536 adds the 2019-04-29 parliamentary-election holiday; and NSE/MSD/42319 adds the 2019-10-21 Maharashtra election holiday. The 2014-04-24 election-holiday original circular identifier remains unresolved. These findings preserve the annual rows and will be represented as controlling amendment observations once their primary bytes or transparently reviewed primary captures are bound.

## Versioned extension v2: sealed amendments and Saturday sessions

The preceding NSE DNS statement was an artifact of the default restricted network sandbox. An explicitly authorized, unauthenticated `Invoke-WebRequest` GET outside that boundary succeeded on 2026-10-15 at approximately 16:30 UTC. The reviewed base manifest, full candidate, and bounded 2021-2022 certificate were kept byte-for-byte unchanged. The new `manifest-extension-v2.json` independently seals nine NSE PDFs totaling 1,362,191 bytes; its SHA-256 is `2fd250d8235e9e42f29b12548c844de1bfcee7c8a62a6496028a33092332a57b`.

`calendar-extension-v2.json` has SHA-256 `04608a0415eb48dc2a5927de1e7014c265fc4dc41b4175bb56946704a5ec9f27` and binds 27 observations to that manifest. Twenty-two are exact components for five whole-Capital-Market Saturday sessions: 2012-01-07 (CMTR19734), 2012-03-03 (CMTR20063), 2012-04-28 (CMTR20561), 2012-09-08 (CMTR21547), and 2013-05-11 (CMTR23302). The first four each record pre-open, normal 11:15-12:45, block, and closing separately; the 2013 notice additionally records its illiquid and SME auction intervals. All five explicitly override the weekend rule.

Five amendment effects preserve rather than erase the annual history: CMTR24977 reopens 2013-11-14 at normal times and closes 2013-11-15; CMTR27792 closes 2014-10-15; CMTR40536 closes 2019-04-29; MSD42319 closes the Capital Market on 2019-10-21. Each row names its superseded annual source/row. Across base and extension tooling, **15 tests pass**.

Two concrete source gaps remain: the original NSE notice for the 2014-03-22 whole-market live session and the original NSE notice for the 2014-04-24 election closure. CSE primary-exchange attestation supports 2014-03-22 timings (pre-open 11:00-11:08, matching to 11:15, normal 11:15-12:45, closing 12:45-13:05, post-close 13:05-13:15), but those are not admitted as NSE-specific component rows. No exhaustive claim about all historical Saturday sessions is made, and `calendar_qualified` remains false for the full-history composition.
