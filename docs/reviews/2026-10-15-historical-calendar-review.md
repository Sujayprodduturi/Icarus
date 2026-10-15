# Independent review: historical NSE cash-market calendar evidence, 2011-2022

**Review date:** 2026-10-15 IST
**Disposition:** **QUALIFICATION MISSING - do not admit to runtime yet.**
**Scope:** read-only review of the 29 sealed NSE Capital Market PDFs and manifest in `var/calendar-reconciliation/2026-10-15/`, plus the reconciliation memo. No broker, credential, price, strategy, trial-ledger, lockbox, or live path was accessed.

## What survived adversarial checking

1. **The sealed bytes are intact.** All 29 local PDFs match the manifest's byte count and SHA-256 exactly; the manifest total recomputes to 4,436,601 bytes. All files open without encryption. Twenty-eight yield substantive text; CMTR42403 is image-only and was checked against its rendered page.
2. **The annual inventory and counts are correct.** The 12 notices cover calendar years 2011-2022. Their tables sum to **172 weekday holiday rows and 56 weekend holiday rows**. Within each annual notice, the dates are unique. The apparent duplicated `08,2022` in CMTR50560 is a PDF text-extraction line-wrap artifact in the single 8 November 2022 row, not a second holiday.
3. **The special-session inventory is arithmetically coherent.** The 29 PDFs comprise 12 annual notices, 12 final Muhurat notices, two superseded Muhurat notices retained for amendment provenance, one Gold-ETF-only Dhanteras notice, and two Saturday Union Budget notices. These categories are mutually accounted for.
4. **The two amendment chains are applied correctly.** CMTR22083 explicitly partially modifies CMTR22027 and changes the 2012 normal close from 16:30 to 17:00 and closing session from 16:40-16:50 to 17:10-17:20 while restating the other fields. CMTR42483 explicitly partially modifies CMTR42403; the original rendered page shows illiquid auction 18:15-19:15, closing 19:20-19:30, and modification cutoff 19:40, while the revision changes those to 18:20-19:05, 19:25-19:35, and 19:45. The unchanged 18:15-19:15 normal market remains valid.
5. **Scope boundaries are correct.** CMTR22063 says only its 14 named Gold ETF securities could trade on Sunday 11 November 2012; it cannot be represented as a market-wide open day. CMTR28939 and CMTR43290 explicitly establish full Capital Market sessions on Saturday 28 February 2015 and Saturday 1 February 2020. Mock, clearing-only, DR-location-only, other-segment, and security-specific pre-open notices do not create whole-market sessions.

## Ranked findings

### P0 - Runtime admission still lacks a positive ordinary-session authority

Annual holiday notices prove closures; they do not prove that every unlisted weekday was a normal session or define its tradable boundaries. A typed calendar needs an effective-dated baseline source for the cash-segment normal market, including the January 2010 opening-time change and the 18 October 2010 pre-open introduction, followed by later changes that affect the 2011-2022 span. The official NSE 17 December 2009 press release establishes a 09:00 market open from 4 January 2010, and NSE's 2011 market report records the 09:00-09:15 pre-open from 18 October 2010, but the reviewed packet does not yet contain a pinned source establishing the resulting normal continuous-session open and close for the full span. Do not fill this gap from present-day timings or convention.

### P0 - The bounded exception inventory is incomplete

The memo correctly refuses impossible proof that no outage ever occurred, but qualification still requires a bounded incident search and typed exceptions. At minimum, classify the known **24 February 2021 NSE cash-market outage and extended close to 17:00**, with authoritative interruption, reopening, and revised-close sources. Also classify the named 2011-2013 `Sun Outage - Capital Market Segment` packages from their contents: planned communications impairment is not automatically a market closure. Search and record a finite set of official channels/subject families for 2011-2022 (holiday/amendment, special live/Muhurat/Budget, outage/resumption/extended hours, and market-wide DR timing changes), and record `NOT_IDENTIFIED_IN_BOUNDED_REVIEW` where nothing is found. This is a practical completeness claim, not a claim that every possible historical outage has been disproved.

### P1 - The evidence is not yet a runnable typed transcription

The prose tables are accurate spot checks, but runtime admission needs one canonical record per observation and independent validation of every annual row. The loader must reject missing provenance, invalid civil dates/day-of-week, duplicate effective keys, overlapping whole-market sessions, ambiguous scope, an amendment without its predecessor, and an image-only source without an explicit manual-observation attestation. The existing missing-bar/data-QA gate may detect consequences of a wrong calendar; it does not establish calendar truth and must not be cited as calendar qualification.

### P1 - Session component semantics need to stay separate

Do not flatten pre-open, normal continuous market, block deal, periodic/illiquid auction, closing/post-close, and trade-modification windows into one interval. `normal_open`/`normal_close` is the tradable continuous-market boundary; the other components need typed names. Instrument-limited sessions require an explicit allow-list (CMTR22063's 14 symbol-series pairs), and the default for securities outside that list is closed.

## Minimum typed record contract

Each immutable observation should carry at least:

```text
schema_version
calendar_date                  # ISO date
timezone                       # Asia/Kolkata; convert to UTC only after local validation
market                         # NSE
segment                        # CAPITAL_MARKET
event_kind                     # ANNUAL_CLOSURE | ORDINARY_BASELINE | SPECIAL_SESSION | OUTAGE | RESUMPTION | AMENDMENT
scope_kind                     # WHOLE_SEGMENT | SYMBOL_SERIES_ALLOWLIST | SESSION_COMPONENT_ONLY
scope_values[]                 # empty only for whole segment; symbol+series for CMTR22063
session_component              # PRE_OPEN | NORMAL | BLOCK | ILLIQUID_AUCTION | CLOSING | MODIFICATION
start_local, end_local          # nullable only where the source does not state a boundary
status                         # OPEN | CLOSED | INTERRUPTED | RESUMED
source_reference               # e.g. NSE/CMTR/22083
source_sha256, source_bytes, source_page
source_publication_date
observation_method             # TEXT_EXTRACTION | MANUAL_VISUAL
supersedes_reference           # nullable
superseded_fields[]            # mandatory for partial amendments
review_status, reviewer, reviewed_at_utc
notes                          # factual limits only
```

Uniqueness should be enforced on `(calendar_date, market, segment, scope_kind, normalized_scope_values, session_component, effective_source_reference)`. Amendment materialization must preserve both the source record and the final effective view. Annual rows should retain printed description and printed weekday, with the loader independently recomputing weekday. A second reviewer should compare every typed date/time/scope field to the pinned page and produce per-source row counts plus a total reconciliation of 172 weekday and 56 weekend rows.

## Smallest qualification path

1. Pin authoritative ordinary-hours source(s) and encode effective-dated baseline intervals for 2011-2022.
2. Transcribe all annual and special-session observations into the contract above; independently double-check every row, not only 2022.
3. Add the 24 February 2021 outage/reopening/17:00 close and classify the 2011-2013 Sun Outage packages plus other bounded market-wide timing exceptions.
4. Run structural checks for hashes, counts, dates/weekdays, duplicates, amendment graph, scope, and non-overlap; compare candidate expected sessions with archive presence as a discrepancy detector.
5. Only then mark the historical calendar qualified. Unknown spans or unresolved incidents remain explicit exclusions, never fabricated normal sessions.

## Reproduction notes

- Hash/size check: Python `hashlib.sha256` over every `evidence/*.pdf`, compared to `manifest.json`.
- PDF check: bundled Python `pypdf` opened every file and extracted all pages; CMTR42403 was verified from `CMTR42403-page1.png` because extraction produced only six characters.
- Count check: annual serial-number tables were independently read and summed by year; all special-session dates, scopes, times, source identities, and amendment wording were compared to the pinned PDFs.
