# Task 3a Step 4 — signal identity and outcome records

**Status:** Approved Task-3a slice, design pinned 2026-09-25 before code. Diagnostic data contracts only; no simulator, portfolio behavior change, real-data evaluation, trial-ledger write, or live order path. See [the Task-3a build plan](2026-08-22-signal-test.md) and operator decisions D15–D19 in `OPERATOR.md`.

## Plain-English job

Give every emitted entry signal one stable identity and exactly one eventual outcome: a completed trade or an explicit skip. A completed trade may close in several pieces. Keep the actual fill prices and assumed stale marks distinct, so a later report cannot turn an estimate into a claimed execution. These records are the common vocabulary for the future signal simulator and the observational portfolio discard ledger; they do not run either simulator.

## Contract

- `SignalId` is immutable and contains strategy ID, the positive integer `StrategyCandidate.version`, symbol, canonical `datetime.UTC` decision timestamp and canonical full-source decision index. Its deterministic UUID is stable across runs and fold views. Run ID, fold ID, mode and notional are **not** part of identity. A fold-local index must never be passed as canonical.
- `SignalSkipped` is immutable and holds the same `SignalId` plus one typed reason: no next bar, untradable, already open, price above notional/zero shares, invalid stop distance, or entry not filled. A partial entry is a trade with its actually filled quantity, not a second skip.
- `SignalExitFragment` holds a positive whole-share quantity, actual exit fill or mark price, price-source UTC time/index, recognition UTC time/index, `ExitReason`, itemized exit `Charges`, and an optional benchmark return observed under a later declared convention. A stale mark is explicitly `STALE_MARK`; recognition may follow the source price. For an actual fill, price and recognition coordinates coincide. Exit fragments are ordered by recognition, not necessarily by price-source index. Every index in every record uses the same canonical full-source coordinate system as `SignalId`.
- `SignalTrade` holds the identity, actual entry UTC time/index/price, filled entry quantity, intended notional, original risk per share, itemized entry `Charges`, and a nonempty immutable tuple of exit fragments. The quantities of all fragments must sum to the filled entry quantity. There is one `SignalTrade` for one signal even when exits are partial.
- Derive deployed capital, gross P&L, itemized total costs, net-before-tax P&L, gross/net return, R-multiple, fill count, marked quantity/value, final recognition index and holding sessions from validated fields. `holding_sessions = final_recognition_index - entry_index + 1`, so an entry-bar exit is one session. Do not store separately editable totals. The entry-charge turnover must equal filled quantity × actual entry price; each exit-charge turnover must equal its fragment quantity × price.
- Benchmark return is quantity-weighted across **all** exit fragments. If any positive-quantity fragment lacks a benchmark observation, whole-trade benchmark return and `pre_tax_alpha` are unavailable (`None`), never zero or a reweighted subset. A supplied observation must be finite; a real observed zero remains zero. Step 4 does **not** choose a Nifty sampling rule: daily bars cannot recover an intrabar benchmark price at a stock stop/target fill. Step 5/6 must pin and label an approximation or suppress the comparison. `pre_tax_alpha` subtracts benchmark return from return after charges but before capital-gains tax; there is deliberately no generic `alpha` field and this diagnostic cannot satisfy the after-tax promotion gate.

## Refusals and chronology

Construction refuses empty identity fields and strategy versions that are not positive whole integers, timestamps without the canonical `datetime.UTC` tag (including naive and arbitrary zero-offset timezone labels), negative or non-whole indices/share counts (`bool` is not an integer here), nonpositive or nonfinite prices/risk, negative or nonfinite charges, turnover mismatch, empty/underfilled/overfilled exits, a same-decision-bar entry, inconsistent time/index order (equal indices require equal timestamps; increasing indices require increasing timestamps), and a purported actual fill whose price-source and recognition coordinates differ. An exit may occur on the entry bar. A stale mark may use a price from an earlier bar, including one earlier than a preceding partial exit's source index, but cannot claim a price or recognition before entry. Missing benchmark data is represented honestly, not rejected as a malformed trade.

## Acceptance tests

1. Stable identity on reconstruction and from full-span/fold contexts when the canonical source index is supplied; changing strategy version, symbol or decision changes it.
2. One signal ID can label either a trade or a skip. Invalid reason and invalid identity fail closed.
3. Partial entry uses filled shares for deployed capital and returns; two unequal partial exits remain one observation with quantity-weighted benchmark return.
4. Entry fee counted once and each exit fee counted separately; costs, R-multiple and `pre_tax_alpha` reconcile by hand.
5. Partial actual exit plus stale residual preserves separate price-source and recognition indices; final-bar mark remains explicitly a mark. Holding sessions use final recognition, not stale-price date.
6. Missing benchmark fragment makes `pre_tax_alpha` unavailable; valid benchmark zero does not. Malformed price, charges, quantities, chronology or UTC tags are refused.
7. Records are frozen/slotted and expose no Sharpe, equity, drawdown or promotion verdict. `signaltest.py` imports neither `portfolio`, `runner` nor `metrics`.
8. The frozen synthetic portfolio characterization and full unit, Ruff and mypy checks remain green; no real panel or lockbox is evaluated.

## What comes next

Step 5 will actually emit these records and prove the `1.0`-signal accounting identity. Step 5b will record and propagate portfolio discards observationally; Step 8 joins only on `SignalId`. Statistical inference and trial persistence remain later gated steps; neither is made ready by these types alone.
