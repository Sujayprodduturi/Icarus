# Daily descriptive pilot proposal — 2026-10-16

**Status:** proposal only under D3/D59. No price byte was decoded, no runtime was built, no trial was reserved, and no actual evaluation is authorized. Implementation waits for independent review and completion of the current missing-history collector unit.

## Purpose and boundary

This is a finite stock-only `DESCRIPTIVE_PILOT` for the fixed 2022-12-26–30 dates. Its first actual diagnostic is exactly **seven SignalSimulator evaluations: one per frozen card in the inventory**. It may reuse existing portfolio mechanics internally (`icarus/engine/portfolio.py:385`) but creates no separate PortfolioSimulator evaluations. It would reuse `SignalSimulator.run` (`icarus/engine/signaltest.py:481`) and the actual Postgres counted-trial guard. It does not use the M15-required timed runner (`icarus/engine/timed_runner.py:551`), replace D21's time-resolved benchmark objective, estimate alpha, add statistics, select a winner, promote a strategy, or enter the 2023 lockbox.

D3 keeps dated NSE daily records authoritative for membership and eligibility. All 693 requested labels remain in every date's denominator with an explicit disposition; no missing name may be dropped. Nifty is separate and absent here, so `benchmark_return` and `pre_tax_alpha` remain `None`. Any card containing a registered `require_benchmark` primitive is refused during applicability preflight, before trial reservation, following the existing primitive registry policy (`icarus/engine/timed_evaluation.py:161`). A refusal is reported without creating a trial or decoding actual-study prices; it cannot silently reduce the seven-card set. The seven frozen cards currently contain no such primitive.

## Exact warm-up inventory

The machine-readable inventory is `var/daily-descriptive-pilot/2026-10-16/warmup-inventory.json`. It pins every card hash and uses the engine's conservative `longest_lookback` rule (`icarus/engine/backtest.py:124`): the largest integer literal across entry, rank and exit.

| Approved card and spec anchor | Longest lookback | First required reviewed session |
|---|---:|---|
| `baseline_buy_and_hold` — `strategies/baseline_buy_and_hold.yaml:40`, `roc(252)` | 252 | 2021-12-21 |
| `defensive_low_vol_252_q63` — `strategies/defensive_low_vol_252_q63.yaml:8`, `realized_vol(252)` | 252 | 2021-12-21 |
| `donchian_55_20` — `strategies/donchian_55_20.yaml:6` | 55 | 2022-10-06 |
| `donlevey_sweep_reclaim` — `strategies/donlevey_sweep_reclaim.yaml:36`, `sma(200)` | 200 | 2022-03-07 |
| `short_term_reversal_uptrend` — `strategies/uptrend_pullback_3.yaml:14`, `sma(200)` | 200 | 2022-03-07 |
| `xs_momentum_20` — `strategies/xs_momentum_20.yaml:30` | 20 | 2022-11-28 |
| `xs_momentum_252_21` — `strategies/xs_momentum_252_skip21.yaml:12`, `roc_skip(252,21)` | 252 | 2021-12-21 |

The reviewed 2021–2022 calendar therefore makes **2021-12-21 through 2022-12-30 (257 sessions)** the required source interval: 252 prior sessions before the first decision plus five pilot sessions. The existing 2022-11-29 start gives 20 rows through 2022-12-26 but only 19 prior sessions; it supports the inclusive 20-session liquidity screen, not even the engine's 20-session strategy warm-up and not all seven cards. The calendar certificate is hash-pinned in the inventory but still says `calendar_qualified=false`; these dates are a derived requirement, not input admission.

## Honest daily execution model

- A decision from daily bar *t* becomes available only after that bar is complete. An entry can be considered no earlier than the next admitted session *t+1*; same-bar fills are forbidden.
- Reuse existing strict-through and conservative daily mechanics. When a daily bar touches both stop and target and order is unknowable, the existing pessimistic resolver chooses the stop (`icarus/engine/simcore.py:287`). A daily bar supplies no exact execution timestamp or intraday path.
- Decisions on 2022-12-26–29 have a next bar inside the bundle. A new 2022-12-30 intent is recorded `NO_NEXT_BAR_WITHIN_PRE_2023_BUNDLE` and cannot open on 2023-01-02.
- These are modeled daily outcomes only. They cannot be relabelled as exact fills, exact-time alpha, or evidence for D21.

## Universe and finite input QA

- Preserve all 693 labels and per-date reasons. Validate the requested-label hash, aliases, dated symbol/ISIN/series lineage, and unique EQ record; missing, duplicate, non-EQ, invalid or action-unresolved cells fail or receive an explicit counted reason.
- Re-hash every selected archive/cache file before and after any later decode; bind a new full-interval manifest to exact path, size and SHA-256. The existing 24-file liquidity manifest covers the screen only and cannot certify the 257-session strategy bundle.
- Before numeric conversion, validate archive/CSV schema, one source date per file, reviewed session coverage, no 2023 row, duplicate keys, null/domain rules and complete 2021-12-21–2022-12-30 interval.
- Bind dated corporate-action evidence and the raw-vs-derived convention before using any adjusted series. Membership and original daily eligibility stay point-in-time and must not be recomputed from a later adjusted price basis.
- Reproduce the fixed 20-session eligibility screen for each date and reconcile all four status counts to 693. Keep BANKBEES/NIFTYBEES as counted daily dispositions. Record LIQUIDBEES as `CLASS_INELIGIBLE_FIXED_INCOME`; do not invent a blanket ETF ban.
- Bind the modeled daily availability rule, calendar certificate and its eventual reviewed admission. `calendar_qualified=false`, an unresolved action, or any unaccounted label prevents data qualification.

## Source-use blocker

The NSE research-data list identifies daily OHLC and bhavcopy archives as first-basket research data. That does **not** currently authorize this simulation: the [NSE Terms of Use](https://www.nseindia.com/static/nse-terms-of-use) (updated 2025-10-29) expressly prohibit using website data for simulation and prohibit automated collection. The [Copyright Policy](https://www.nseindia.com/static/nse-copyright) permits unchanged, acknowledged personal/non-commercial/educational downloads, but does not say it overrides that use restriction. The [Data Sharing and Usage Policy](https://www.nseindia.com/static/market-data/nse-data-policy) routes research market-data use through purpose-specific documentation/agreement. No applicable archive-specific exception or agreement is pinned. Therefore `SOURCE_USE_DISPOSITION=UNRESOLVED`, and neither sealed possession nor an NSE-only design clears the actual-run gate. No contact, request, collection, or purchase is proposed or authorized here.

## Ordered gates before any actual run

1. Finish and review the already authorized missing-history collector unit; do not couple this plan to a new acquisition.
2. Independently review this proposal and warm-up inventory, including the 257-session derivation, source-use assessment, all-label policy and daily execution model.
3. Resolve a source choice with an applicable right for simulation. Current NSE website evidence does not supply it. No offline runner/report build begins merely because the collector or software proposal is complete.
4. Under the existing D55 authorization, bounded source-QA may decode the exact pre-2023 daily bundle solely to qualify its full manifest, schema, calendar, actions, PIT identity/class and 693-label counts. This is data-plane QA: no strategy evaluation, trial, or metric-bearing output. Any missing item blocks admission.
5. After the collector, source-use resolution, and independent plan review, an offline build may use invented fixtures to add the seven-SignalSimulator runner/report integration. It must reuse existing engines and the actual ledger barrier; no new statistic or promotion path.
6. Obtain separate actual-run authorization. Applicability/refusal checks run before the ledger. If all seven frozen cards remain supported, atomically reserve the complete seven-card evaluation set in the existing actual trial ledger **before actual-study price decoding or metric-bearing output**; a reservation/decode/report failure remains counted and fail-closed.

Until all six gates pass: `DATA_QUALIFIED=false`, `RUN_AUTHORIZED=false`, no strategy price decode, no trial, and no descriptive result. D55 source-QA decoding remains a separate bounded qualification activity and cannot release a strategy result.
