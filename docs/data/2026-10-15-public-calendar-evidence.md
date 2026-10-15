# Public NSE cash-market calendar evidence — bounded first pass

**Retrieved:** 2026-10-15 IST  
**Scope:** public, unauthenticated NSE/NSE Archives material only; no market-price download, credentials, strategy evaluation or lockbox access. This five-minute pass establishes a 2022 candidate source pair and identifies older coverage. It does not certify 2011–2022 completeness.

## Result

`CALENDAR_QUALIFIED=false`. The two official Capital Market Segment circulars below are sufficient to construct a **2022 published holiday-list candidate plus the published 2022 Muhurat schedule**. They are not yet sufficient to prove that every 2022 session boundary, later amendment, emergency closure, outage or other special live session has been found.

## 2022 candidate evidence

| NSE record | Circular date and applicability | Verified content |
|---|---|---|
| [NSE/CMTR/50560, circular 117/2021](https://archives.nseindia.com/content/circulars/CMTR50560.pdf) | 2021-12-10; **Capital Market Segment**; “Trading holidays for the calendar year 2022” | Weekday closures: 2022-01-26, 03-01, 03-18, 04-14, 04-15, 05-03, 08-09, 08-15, 08-31, 10-05, 10-24, 10-26, 11-08. It separately lists weekend holidays 04-10, 05-01, 07-10, 10-02 and 12-25. It says Muhurat trading will occur on 10-24 and that times will follow. |
| [NSE/CMTR/54023, circular 124/2022](https://archives.nseindia.com/content/circulars/CMTR54023.pdf) | 2022-10-11; **Capital Market Segment**; continuation of CMTR/50560 | 2022-10-24: block deal 17:45–18:00; pre-open 18:00–18:08 with random closure in the last minute; normal market 18:15–19:15; call-auction illiquid 18:20–19:05; closing session 19:25–19:35; trade-modification window 18:15–19:45. Trades create settlement obligations. |

The annual circular supplies closures, not a positive assertion that every other weekday used ordinary hours. The Muhurat circular overrides the holiday label for one special live session. The adapter must retain both source records and the override relationship.

## Older coverage identified, not completed

[NSE/CMTR/46623, circular 113/2020](https://archives.nseindia.com/content/circulars/CMTR46623.pdf), dated 2020-12-11 and applicable to the Capital Market Segment, is the official annual holiday circular for 2021. It lists fourteen weekday closures, five weekend holidays and states that 2021-11-04 Muhurat timings would be notified later. This confirms the annual-plus-follow-up document pattern in another year. The bounded search did not verify the corresponding cash-market timing circular, so 2021 is incomplete.

No annual Capital Market Segment circular was verified in this pass for 2011–2020. Search misses are not evidence that the circulars do not exist. No year before 2022 is qualified by this report.

The existing local archive-presence calendar has **zero Saturday/Sunday sessions**, and the scanner at audited source `21978fa` constructs its denominator with `day.weekday() < 5`. The separately reviewed fix at `6b71533` widens future discovery; it does not repair this cached axis. It is therefore structurally unable to discover weekend special sessions. Weekend absence in `var/calendar.json` is not evidence of closure and cannot close the public-circular inventory.

## Source retrieval manifest

| URL | Retrieved | Local byte hash |
|---|---|---|
| `https://archives.nseindia.com/content/circulars/CMTR50560.pdf` | 10/15/2026 13:48:50 | `731a4f0f3b3633e53ff344ffda23dab0277c4a6608f5a6da8874f931c9be4ead` (94485 bytes) |
| `https://archives.nseindia.com/content/circulars/CMTR54023.pdf` | 10/15/2026 13:48:50 | `01e579eac8e2dd4a870a9ebc9f08d60bc26fae28d0d35cf58891bf2a2964e0c7` (70954 bytes) |
| `https://archives.nseindia.com/content/circulars/CMTR46623.pdf` | 10/15/2026 13:48:50 | `3c922e234ad2cbe8320cc34507e281477e0ce273ba9ee39d73da2a49d5629add` (75512 bytes) |

Root subsequently downloaded these three PDFs to ignored `var/kite-qualification/2026-10-15/calendar-evidence/`, verified PDF signatures and extracted their actual segment/reference/date headings. `retrieval-register.json` pins URL, retrieval time, size and SHA-256. These immutable pointers still do not establish complete amendment coverage or qualify a calendar.

## Exact unresolved classes

1. Later holiday amendments or withdrawals after each annual circular.
2. Muhurat timing circulars for every year and any other weekend/special live session, including Union Budget sessions.
3. Contingency drills that were live versus mock-only; emergency closures, delayed opens, early closes, outages and resumptions.
4. Segment applicability: only **Capital Market Segment live trading** counts. F&O, currency, commodity, SLBS and clearing/settlement calendars cannot substitute.
5. Session components and boundaries: pre-open, normal market, call-auction/illiquid, closing session and any security-specific session must remain distinct.
6. A complete amendment chain and deterministic precedence where a special-session circular overrides an annual holiday notice.
7. Immutable bytes, SHA-256, retrieval time and source identity for every admitted circular.
8. Weekend special sessions omitted by the legacy weekday-only archive-presence scan; these require circular authority and an independently widened comparison denominator.

## Next action

The initial PDFs are now captured and hash-pinned. Search NSE's Capital Market circular archive by date and document reference for every 2022 amendment, special live session, outage and resumption. Only after that closed 2022 inventory is independently checked should the same annual-plus-follow-up procedure proceed year by year through 2011. Archive presence may be used as a discrepancy check, never as calendar authority.

No runtime, existing frozen report, source byte, quarantine, adapter rule, benchmark policy or authorization was changed.
