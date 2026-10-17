# Daily pilot source QA — 2026-10-17

**Decision:** the bounded source-payload checks pass for the exact 257-session daily bundle, but
`DATA_QUALIFIED=false` and `RUN_AUTHORIZED=false`. This document records the source-only result.
The later scoped calendar, corporate-action, and point-in-time review is recorded separately in
`docs/data/2026-10-17-daily-actions-identity-qa.md` and
`docs/reviews/2026-10-17-daily-data-qualification-review.md`. Source-use/retention and durable
actual-panel emission remain separate gates. No strategy, return, fill, P&L, metric or trial-ledger
operation occurred.

## Scope and confinement

The selected interval is exactly 2021-12-21 through 2022-12-30: 257 reviewed session dates, 257
raw NSE bhavcopy ZIPs and the corresponding 257 schema-2 day caches. The requested universe is the
pinned set of 693 stock labels; Nifty remains separate and absent from this source screen.

The numeric inspection ran in cached
`python@sha256:a6e34c598f2467ed0e9a8d349809fcd8b5c603269512df273a0bb1784edc11b1`
as UID 10002, with network disabled, a read-only root, all capabilities dropped,
`no-new-privileges`, 1 GiB memory, two CPUs, 64 PIDs and a bounded no-exec tmpfs. Only exact staged
copies of the 257 raw and 257 cache files, the explicitly pinned controls and two read-only helpers
were mounted. The broader cache directory and all 2023+ payloads were absent. Only the new evidence
directory was writable; no home, SDK, credential, broker or Docker-socket mount was present.

Source inventory SHA-256:
`191008c1b34c4a9b88285c0758d1725b8dca65555e96d16bbcbd09f313d10a7a`.
Qualification helper SHA-256:
`bda4fd02f1ca33a8ecbc3bd3efae2ca54b4f43d85b503f1b2283f8444080c635`.
The unchanged approved eligibility helper SHA-256 is
`557d9e3d85b0d44fd98983700688750b0b80fc8a7d2ac925129ab18218684250`.

## Source-payload result

All 257 raw archives had one recognized CSV member, unique headings and complete rows. Every raw
row, including non-EQ series, carried its file's expected date before numeric conversion or EQ
selection. The selected interval contained no 2023 row. Duplicate raw identities, duplicate cache
keys, malformed/null/bool/non-finite values, non-positive prices, negative volume/turnover and OHLC
ordering errors were absent.

The scan counted 576,443 raw rows. Of these, 453,808 were EQ rows; the caches contained exactly
453,808 rows. All 257 raw/cache key sets and all six numeric fields aligned by exact finite Decimal
value. The 330 raw rows with a corresponding 330 cache rows whose OHLC was positive but below INR
1 are valid source records, while the unchanged research sanity rule excludes them. This is a
count of symbol-session rows, not 330 distinct instruments.

The report records 525 source/control states before and after inspection: the 514 payload files,
eight inventory controls, source inventory, `goal.yaml`, and the approved eligibility helper. All
were unchanged. A fresh host-side post-check also rehashed the 514 original payload files:
54,505,829 bytes, zero size or SHA-256 mismatches. As an independent spot check, the root reviewer
reproduced 2022-12-30 as 2,335 raw rows and 1,877 EQ/cache rows with exact six-field alignment; the
full report has the same counts.

## All-label eligibility reproduction

The existing approved screen was reused unchanged: 20 observed sessions ending on and including
each date, current-day close at least INR 30, and average turnover at least INR 500,000,000. Every
row below the existing INR 1 research sanity floor remains excluded before this calculation. Each
date accounts for all 693 requested labels.

| Date | Below close | Below turnover | Fixed income | Conditional | Missing window | Total |
|---|---:|---:|---:|---:|---:|---:|
| 2022-12-26 | 15 | 335 | 1 | 235 | 107 | 693 |
| 2022-12-27 | 15 | 335 | 1 | 235 | 107 | 693 |
| 2022-12-28 | 14 | 341 | 1 | 230 | 107 | 693 |
| 2022-12-29 | 15 | 342 | 1 | 228 | 107 | 693 |
| 2022-12-30 | 15 | 342 | 1 | 229 | 106 | 693 |

`LIQUIDBEES` retains its original source-screen status in the receipt and is then counted as
`CLASS_INELIGIBLE_FIXED_INCOME`. `BANKBEES` and `NIFTYBEES` remain ordinary counted dispositions;
both are below turnover on all five dates. `CONDITIONAL_QUALIFIES` is the existing screen's name
and is not a point-in-time identity, corporate-action, strategy or admission certificate.

## Evidence and limits

The immutable result is
`var/daily-descriptive-pilot/2026-10-17/source-qa/evidence/source-qa-v2.json`, 899,561 bytes, SHA-256
`1d3a3628dd586ed3984760dc67955166f5f53b30968b5e90d0af9a2d4fe2481b`. It contains both complete
file-state lists, all 257 per-session counts and every requested label's original and class-adjusted
status on all five dates.

The earlier `source-qa.json` failure receipt is retained. It rejected `ANTGRAPHIC` for being below
INR 1 because the first helper version conflated source validity (finite, positive, ordered OHLC)
with the separate research sanity floor. The reviewed correction did not change or fit any source
value and did not loosen the research screen; it separated the two checks and wrote a new v2
receipt.

Twenty-two source-helper unit tests pass, covering wrong and 2023 dates, all-row date prescan, duplicate
raw identities and CSV headings, duplicate cache keys, malformed/null/bool/non-finite/domain rows,
OHLC ordering, Decimal-equivalent alignment, field mismatch, pin mutation, exact calendar scope,
fixed-income treatment, ordinary ETF retention and continued scanning after a per-date failure.
Strict mypy, Ruff lint and Ruff format checks pass for the helper and its tests.

The immutable source receipt still says `calendar_qualified=false`, as it must: this source-only
packet cannot retrospectively claim the later scoped review. The separate action/identity/calendar
record supplies that review without rewriting this receipt. Source-use remains unresolved, and no
document here authorizes the daily pilot or any other actual evaluation.

## Reviewed composition interface and next confined check

The narrow composition code is `icarus/engine/daily_pilot_prepare.py`. Its
`bind_and_prepare_daily_pilot` entry point rehashes the full 257 raw plus 257 cache bundle and all
selected controls before and after use, validates the source-QA PASS semantics, derives the exact
calendar axis, applies every relevant raw-ISIN conflict override, rebuilds the requested-label
action ledger, checks the pinned `goal.yaml` universe, and calls the pure 693-by-257 preparer. It
does not write an NPZ, qualify data, authorize a run, or evaluate a strategy. Its invented suite
has 15 passing tests, including source mutation, status-reason mismatch, action-control mismatch,
apply-all PIT conflicts, sub-INR-1 physical validity versus research exclusion, residual-gap
refusal, full-axis binding, exact action handling, all-label retention, and write-once round-trip.

The next transient composition-QA invocation must use these exact files and SHA-256 pins:

- source inventory `191008c1b34c4a9b88285c0758d1725b8dca65555e96d16bbcbd09f313d10a7a`
- source QA `1d3a3628dd586ed3984760dc67955166f5f53b30968b5e90d0af9a2d4fe2481b`
- requested labels `a88632590be0f8344e962e0b27179516e977161e113c59e9ef2f5d9748c25fd3`
- calendar `4d7902c85909cba50b00dfccd6c0d3b1051225ba547e33bc010b56ad0e683c91`
- action manifest `b67a2566a7df9455b4709210be69037040aebce04028ee4f1264566ba9c8e5d6`
- PIT matrix `4c85773e03d015ddaf5c06d06d27abbf7e95e0b15f34414b84d2558e873b3ba6`
- `goal.yaml` `c886aca6b198257486d0daefc484f818458e60fa32a5aa861b95d1413282fa0c`
- session-axis digest `061958ca5e9606bc0e5ec79db8b347d7dcaee2bc62924d01475e33821da0956d`
- ordered-label-axis digest `0cb9acc3eeb45ebdbf5443467d326c6f87f038c58957f7a7ff015390f9894790`

Call the binder with repository root plus the paths named by those controls and
`load_goal(root / "goal.yaml").universe`. Under the reviewed transient D55/D61 scope, print only
its verification counts, lineage/action/input-state digests, audit counts, and 693 raw/effective
five-day dispositions. Do not call `publish_prepared_panel_once`, save an NPZ, emit price arrays,
run a signal/simulator, or touch a trial ledger. Run it only in the same UID 10002, network-none,
read-only-source confinement after the final code review. Durable emission then still requires the
source-use disposition, reviewed qualification contract, confined resource/package proof, and
separate actual-run authorization.
