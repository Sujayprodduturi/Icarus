# Post-backtest audit — what Icarus actually measured, and what is wrong with it

> **Date:** 2026-08-09 · **Trigger:** operator pause after the first end-to-end backtest (2026-08-07).
> **Status:** findings only. **No code was changed.** Nothing here is fixed yet.
> **Companion:** `TASKS.md` §1.7 findings (a)–(x) records the bugs found *during* the build.
> This document records the bugs found *by looking at the result*.

> ### ⚠️ How to read the numbers in this file
>
> Findings here are **`F1`…`F23`**. Safety invariants in `CLAUDE.md` §0 are **`#1`…`#26`**.
> **They are different things and they overlap in range.**
>
> They were originally both written as bare `#N`, which made `#23` mean *"halt on stagnation"*
> (invariant) in one paragraph and *"annulled trades are in the panel"* (finding) in the next.
> Renamed 2026-08-11 so a reference can only mean one thing.
>
> Anywhere in this project: **`F` = a finding in this file · `#` = a safety invariant in
> `CLAUDE.md` · `D` = a decision in `OPERATOR.md` §7b · `§` = a PRD section.**
> Spell out what a reference *means* the first time it appears in any conversation — a bare
> number is not an explanation.

The run that prompted this: 2,962 sessions × 693 point-in-time symbols, 2011-01-03 → 2022-12-30,
lockbox untouched. Three strategies, all three FAIL the pre-registered gate. Headline numbers are in
`TASKS.md`.

The question this document answers is not "did the strategies work". It is **"was that even a
test of the strategies?"** The answer is largely no.

---

## 0. The one-paragraph version

The backtest measured a **four-position, ₹1-lakh book skimming the top of a signal stream it could
not consume**, using a ranking function that was either broken or not the one the strategy meant.
Between 94% and 99.99% of every strategy's signals were discarded for want of a slot. The "control"
strategy picked its holdings **alphabetically** for its entire out-of-sample life. Both
momentum-ranked strategies ranked by *rupees of price change*, not percentage, which is a
systematic bet on expensive stocks. Under those conditions a Sharpe near zero is not evidence about
the strategies; it is evidence about the harness.

---

## 1. The operator's own point, quantified

> *"When I wanted to backtest a strategy, I wanted the strategy to take/exit a trade whenever it
> wants and holding how many positions as he can but ultimately test the win ratio of the strategy."*

This is a different question from the one the engine answers, and the difference is enormous.

| strategy | signals fired | trades taken | **dropped for no slot** | share taken |
|---|---:|---:|---:|---:|
| baseline_buy_and_hold | 246,281 | 33 | 240,122 | **0.013%** |
| donlevey_sweep_reclaim | 7,301 | 466 | 6,342 | **6.4%** |
| xs_momentum_20 | 20,076 | 355 | 14,019 | **1.8%** |

`xs_momentum_20` is written as *"hold the ten strongest names"*. `risk.max_open_positions` is **4**.
The strategy as written was never once run. What ran was a different strategy — "hold the four
names that a possibly-broken ranker put on top, out of the ten this wanted" — and its win rate is a
statement about that, not about relative strength.

**Two different questions, both legitimate, currently conflated into one number:**

1. **Does the signal have an edge?** — every signal taken, one position per signal, uniform
   notional, no book cap, no heat cap, no competition for slots. This is the win-rate / expectancy
   question. It is *not* a runnable portfolio and must never be quoted as one.
2. **Does a runnable portfolio built from that signal have an edge?** — 4 slots, 2% heat, ₹1L,
   whole shares, real costs. This is what the current engine measures and what the stop gate should
   read.

Right now only (2) exists, and (1) is what tells you whether a strategy is worth building a
portfolio around. **You cannot diagnose (2) without (1).** A strategy that fails (2) but passes (1)
needs a bigger book or better slot arbitration; a strategy that fails both is dead. We currently
cannot tell those apart for any of the three.

---

## 2. Bugs — the measured strategy was not the written strategy

Same class of defect as the exit-rule bug found on 2026-08-08 (`TASKS.md` 1.7(q)). Invariant #25 is
worth nothing while the artefact and the simulated object differ.

### 2.1 🔴 `momentum` is *absolute* price change, not percent — CONFIRMED

`icarus/strategy/library/trend.py:434` — `momentum`: *"Absolute change over n bars."*
`roc` is the percentage version.

`xs_momentum_20.yaml`'s own comment says *"hold the ten strongest names in the universe by
**20-session return**"*. It does not. It holds the ten names whose **rupee** price rose most.

Tradable close prices in this panel: 5th pct ₹66 · median ₹470 · 95th pct ₹3,748. A ₹3,000 stock
rising 5% (+₹150) outranks a ₹300 stock rising 40% (+₹120). **The strategy is a persistent bet on
expensive stocks wearing a momentum label.** That alone could produce the −0.03 Sharpe.

Affects `xs_momentum_20` (entry *and* rank) and `donlevey_sweep_reclaim` (rank) and
`baseline_buy_and_hold` (rank).

### 2.2 🔴 `longest_lookback` ignores `rank_by` and `exit` — CONFIRMED

`icarus/engine/backtest.py:109` — `return max(_integer_literals(strategy.entry), default=0)`.

Consequence for the baseline, verified by running it:

- `entry` is `close > 0` → lookback **0** → warm-up **0**, purge **0**.
- `rank_by` is `momentum(252)`, whose first finite value is at index **252**.
- Fold test windows are ~252 sessions long.

So the rank column was `nan` across essentially the entire out-of-sample window of every fold.
`_rank_of` maps `nan` to `-inf`, all candidates tie, and `_process_entries` falls through to the
tiebreak — `sort(key=lambda s: (-rank, s))` — **which is alphabetical by symbol.**

**The control strategy chose its holdings alphabetically for eight years.** A control that does not
control for anything cannot tell you the machinery works, which was its entire stated purpose.

Secondary effect: purge = 0 for the baseline, so there was no purge between train and test either.

### 2.3 🟠 A position in a symbol that stops printing bars is never closed — CONFIRMED by inspection

`portfolio.py:_process_exits` does `bar = _sim_bar(...)` then `if bar is None: continue` — and this
runs **even when `final=True`**. A symbol with `nan` on the last bar (delisted, suspended, or its
history truncated by the corporate-action quarantine) leaves its position in `book` forever.

That position:
- never becomes a `ClosedTrade` → invisible to win rate, expectancy, profit factor, the tax ledger;
- contributes nothing to realised equity (P&L only flows through `_process_exits`);
- contributes nothing to unrealised equity (`_unrealised` skips non-finite closes).

**The capital simply disappears from the accounting** — neither as a loss nor a gain. **CORRECTED 2026-08-14 (task 2c): the sizing argument below was wrong.** Quarantine blanks *membership*, not price data — of 318,332 tradable symbol-days, zero have a missing close — so it cannot cause this at all. The real cause is delisting and suspension: 96 of 693 symbols stop printing before the panel ends, and 71 times a symbol is tradable one session and dark the next (53 staying dark 60+ sessions, one for 2,840). With at most 4 of ~100 tradable names held at once, the likely damage in a full run is a handful of positions. A correctness bug, not an explanation of the results. The
direction of the bias is almost certainly favourable to us: names that stop trading are
disproportionately the ones that collapsed.

### 2.4 🟠 No cash constraint — the book can spend money it does not have

`_process_entries` checks slots, heat, share rounding and fill. It never checks that the position's
**notional** fits in the account.

Position size is `risk_budget / stop_distance`. With a tight stop that ratio explodes: a 1%-of-price
stop at `risk_r 0.005` gives a notional of 50% of equity, and four of those is **200% of equity** —
2× leverage in a *delivery* segment where it is not possible at all.

It did not bite in this run because the stops were wide (baseline's 50% stop → 1% notional; the
2–3× ATR stops → roughly 10%). It will bite the moment we use tighter stops or intraday bars, where
ATR is much smaller relative to price. **The heat cap governs risk, not capital deployed. Nothing
governs capital deployed.**

### 2.5 🟡 Declared-but-inert configuration

Parses, validates, is enforced nowhere:

| where | key | status |
|---|---|---|
| `dsl.py:492` | `sizing.weighting`, `sizing.vol_target_pct` | documented as "declarations only" — all three strategies declare `equal_weight`, which does nothing |
| `goal.yaml` | `trade_quality.min_quality_score` | unused |
| `goal.yaml` | `trade_quality.rank_select_top_k` | unused |
| `goal.yaml` | `trade_quality.max_trades_per_day_per_strategy` | unused |
| `goal.yaml` | `trade_quality.min_holding_bars` | unused |
| `goal.yaml` | `risk.max_pairwise_correlation` | unused — the book may hold 4 names from one sector |
| `goal.yaml` | `allocation.*` | unused |

Not all of these are bugs — some are honestly deferred. The problem is that a reader of `goal.yaml`
cannot tell which. A config key that looks enforced and is not is how a safety limit quietly stops
existing.

---

## 3. Why the verdict is not yet conclusive

Even with every bug above fixed, the current metric sheet cannot support "this strategy has no
edge".

### 3.1 🔴 No cost attribution

We report after-cost P&L and the tax bill. We never report **gross P&L, cost, and tax as three
separate lines.**

Rough estimate for `donlevey_sweep_reclaim` (466 trades, ~10% notional per position): ~0.4% round
trip against a total return of 8.8% → **costs plausibly consumed more than the net profit**. If
true, the strategy has a real gross edge that the cost structure eats — which is a *completely*
different problem from "no edge", and calls for a completely different response (fewer, larger,
longer-held trades; not a new strategy).

This is a guess. It should be a column. `costs.dp_charge_inr` alone is a fixed ₹15.34 per delivery
sell — at these position sizes that is a tax on trade frequency, and we are not measuring it.

### 3.2 🟠 No benchmark-relative metrics

Invariant #21 requires gating on **alpha after cost and tax** vs Nifty, and flagging high benchmark
R². `goal.yaml` already carries `benchmark_equity: NIFTY50`, `min_alpha_after_cost_tax: 0.0`,
`max_benchmark_r2: 0.8`. The panel now carries the Nifty 50 series. **Nothing computes alpha, beta
or R².** (Task 1.8b, open.)

### 3.3 🟠 The Nifty comparison already made was not like-for-like

`TASKS.md` currently says *"Nifty 50 over the same span: Sharpe 0.80, 13.1% CAGR"* next to the
baseline's 1.1% CAGR. **The CAGR halves of that comparison are not comparable.** The baseline's
50%-wide stop makes each position ~1% of equity; four positions is ~4% deployed. Its annualised
volatility is **1.47%**. Comparing a 4%-invested book's CAGR to a fully-invested index is
meaningless, and every scale-dependent gate number — `objective.max_drawdown`, `min_calmar`,
`target_return_30d` — is being applied to a book that is nearly all cash.

The *Sharpe* comparison (0.77 vs 0.80) is roughly fair, since Sharpe is leverage-invariant. The
CAGR and drawdown comparisons are not, and should be withdrawn.

### 3.4 🟠 No per-trade output exists

`var/backtest_results.json` contains fold summaries and skip counts. It contains **no trades**.
There is no way to look at a single trade — entry, exit, reason, R, cost — which is precisely what
the operator asked to see and precisely what is needed to tell §3.1 apart from "no edge".

### 3.5 🟡 No overfitting correction yet

DSR, PBO/CSCV and the Harvey–Liu haircut (task 1.9) are unbuilt. The lifetime trial ledger stands at
9. The reported Sharpes carry no multiple-testing correction.

### 3.6 🟡 Folds are not comparable across strategies

`donlevey` gets 7 folds starting 2014-11; the others get 8 starting 2014-01/02, because the purge is
derived per strategy from its own lookback. Correct in isolation, but it means the three OOS records
cover **different periods** and the cross-strategy comparison in the metric sheet is not
like-for-like.

### 3.7 🟡 Regime stability and cost stress not run

Task 1.8 is partial. `objective.cost_stress_multiplier: 1.5` exists and has never been applied.

---

## 4. Structural gaps — what Icarus cannot currently express

These are not bugs. They are the reason invariant #25 says *"change the input, never the bar."*

### 4.1 🔴 Longs only

`_process_entries` always issues `OrderSide.BUY`. There is no `direction` key in the strategy
schema (`_TOP_LEVEL_KEYS` = name, version, timeframe, universe, entry, exit, sizing, rank_by).

The Donlevey research note (`docs/strategy-research/donlevey-liquidity-smc.md`) is explicitly
bidirectional — *"Mirror for shorts"* — and the DSL already carries the full bearish vocabulary:
`bos_down`, `choch_down`, `structure_bearish`, `sweep_and_reclaim_high`, `swept_high`,
`order_block_bear_*`, `ote_bear_*`, `breaker_bear_*`, `mitigation_bear_*`, `rejection_bear_*`,
`liquidity_pool_high`, `inducement_high`, `upthrust`, `failed_break_up`. **All unreachable.**

Note the real-world constraint: NSE cash delivery cannot be shorted. Shorts require intraday (MIS)
or futures — which changes the cost segment, the tax bucket (speculative / non-speculative business,
not capital gains), and the margin model.

### 4.2 🔴 Daily bars only — the method's own timeframe is missing

The Donlevey note states plainly: *"the full method is **intraday** (M5/M15, session liquidity)"*.
What we backtested is the note's explicit "Phase-1 daily distillation", i.e. a deliberately
lossy shadow of the method. Its failure is **weak evidence** about the method.

Roughly 40 of the 223 primitives are intraday-only or degenerate on daily bars: `killzone`,
`silver_bullet`, `power_hour`, `judas_swing`, `session_vwap`, `opening_range_high/low`,
`session_range_high/low`, `daily_open`, `prev_day_*`, `internal_bar_strength`, and the
displacement/FVG family which needs sub-daily resolution to mean what it means.

### 4.3 🔴 The India-only feeds are built but not backtestable

`run_backtest.py:62` calls `parse_strategy(...)` **without `available_feeds`**. The default is
`frozenset()` and feed primitives fail closed. So `delivery_pct`, `delivery_qty`,
`fii_net_index_fut`, `client_net_index_fut` and `in_fno_ban` — the three India-specific feeds that
`TASKS.md` 1.1d calls *"where the catalogue says our edge is most likely, precisely because nobody
outside India has had the data to mine it flat"* — **cannot appear in any backtested strategy.**
The data is fetched and verified against 11 years of files. The panel does not carry it and the
runner does not declare it.

This is the single largest unexploited asset in the repo.

### 4.4 🟠 The universe is ~100 names, not the ~600–900 expected

Median tradable names per session: **98** (min 0, max 248). By year-end 2022 it reaches 230; in 2013
it is 43. The ₹50cr/20-session turnover floor plus the ₹30 penny floor plus the quarantine produce
roughly a **Nifty 100–200 equivalent**, not the broad universe assumed when the scope was chosen.

Consequences: less cross-sectional dispersion for ranking strategies, and a book of 4 out of ~98 is
a far more concentrated bet than 4 out of 900 would be.

### 4.5 🟠 ₹1 lakh + whole shares is itself a filter

`rounds_to_zero` fired **1,822 times** for `xs_momentum_20` — signals discarded purely because
₹500 of risk divided by the stop distance came to less than one share. This biases every result
toward cheap stocks in a way that has nothing to do with the strategy.

The seed-tier question ("can this work on ₹1L?") and the edge question ("does this signal work?")
are being answered by one run. They need separating.

### 4.6 🟡 Only one real hypothesis has been tested

Three strategies: one deliberate control, one machinery-exerciser, one thesis. Concluding anything
about the *approach* from one distilled, daily-bar, long-only, mis-ranked strategy is not warranted.

### 4.7 🟡 Dividends excluded

`universe.dividend_convention: price_return`. Consistent across signal, cost and tax, and the Nifty
50 price index excludes them too — so the comparison is fair. But absolute returns understate a
real holder's outcome by roughly 1–1.5%/yr, which matters for a strategy averaging 331 holding days.

---

## 5. Process finding

**Icarus's engineering record is in the repo; the operator's preferences and decisions are not.**
CLAUDE.md holds the safety invariants. TASKS.md holds the build sequence. Neither holds "explain in
plain English before building, wait for approval, then summarise what was done", or the standing
choices made in conversation. Those live only in chat and are lost at every compaction.

Proposed fix: `OPERATOR.md` at the repo root, read at session start, owned by the operator.

---

## 6. Ranked fix list — THE LIVING CHECKLIST

**This table is the durable record.** Chat is compacted; `TASKS.md` only gets an entry once we
commit to working on something. Between "found" and "scheduled", a finding lives here and nowhere
else. **Update the status column as things move. Never delete a row.**

Status: `OPEN` · `DECIDED` (approach agreed, not built) · `DEFERRED` (with a reopening trigger in
`OPERATOR.md` §7c) · `IN TASKS.md` · `PARTLY DONE` · `DONE` · `CLOSED` (found not to be a defect) ·
`WON'T FIX`

`DEFERRED` and `CLOSED` were both already in use here and neither was on this list until
2026-08-17. The vocabulary is enforced by `tests/unit/test_audit_ledger.py`, which also refuses a
row whose fix is written into the *finding* cell while the *status* cell still reads open — five
rows had drifted that way across tasks 2e and 2f, describing themselves as done and outstanding at
the same time.

| # | Finding | Status | Why it ranks here |
|---|---|---|---|
| F1 | §2.1 `momentum` is absolute, not percent | **DONE** 2026-08-12 (task 2a) — word deleted with no alias; `roc` / `momentum_abs` split by unit; `scale_free` declared on all 93 undecidable words and derived for the other 131; `xs_*` and `rank_by` refuse a rupee input at parse time; all three strategy files rewritten to v2. Regression: `tests/unit/test_dsl_scale.py` | Silently changes what two strategies mean; invalidates existing numbers |
| F2 | §1 unconstrained "signal test" mode | **DECIDED** 2026-08-10 (D1, D2) — two modes, gross+net side by side | The operator's actual question is currently unanswerable |
| F3 | §2.2 `longest_lookback` ignores `rank_by`/`exit` | **DONE** 2026-08-13 (task 2b) — reads all three blocks. `baseline_buy_and_hold` goes from a 0-session lead-in to 252 and from 8 folds to 7; the other two were unaffected only because their entry happened to be their widest window. Regression: `tests/unit/test_dsl_lookback.py` | The control was broken; every warm-up guarantee is weaker than believed |
| F4 | §2.3 orphaned positions | **DONE** 2026-08-14 (task 2c) — a holding whose symbol stops printing is written off at its last traded price, on the final bar of a span or after `backtest.stale_position_sessions` (20) dark sessions, under a distinct `STALE_MARK` exit reason. Count and gross value are printed on the metric sheet, because marking at the last print is the optimistic reading and the operator chose visibility over an invented haircut. Regression: `tests/unit/test_portfolio_dark.py`, 18 of 18 mutations caught | Money vanishes from the ledger, biased in our favour |
| F5 | §3.1 + §3.4 cost attribution + per-trade log | **DECIDED** 2026-08-10 (D2) | Cannot distinguish "no edge" from "edge eaten by costs" |
| F6 | §2.4 no cash constraint | **DONE** 2026-08-15 (task 2d) — the book tracks what it has spent and refuses a position it cannot pay for, counted as `insufficient_cash`. Skipped rather than shrunk, so a strategy that fails on capital rather than on edge shows up as `NEEDS_MORE_CAPITAL` (decision D9) instead of quietly becoming a smaller strategy. The whole skip table now prints on the sheet — it was counted from the start and shown nowhere, which is how "94-99.99% of signals discarded" stayed invisible until somebody read the JSON. Regression: `tests/unit/test_portfolio_cash.py` | **Not merely latent, as this row said.** Measured: `ATR/price` bottoms out at 0.003%, so a 2x-ATR stop would size a single position at **7,706% of equity**, and 0.45% of tradable symbol-days would produce one over 100%. The heat cap could never have caught it — stop distance cancels out of heat, so every position uses exactly `risk_r` and four always total 2.0% against a 2.0% cap |
| F7 | §4.3 wire the India feeds into the panel | OPEN | Largest unexploited asset already paid for |
| F8 | §4.2 intraday data | **DECIDED** 2026-08-10 (D3, D4) — 15-min, daily owns membership | The method's own timeframe; invariant #25's prescribed response |
| F9 | §4.1 shorts | **DEFERRED** 2026-08-10 (D5) — `OPERATOR.md` §7c, with its reopening trigger | Half of the thesis, but gated on a working long-only system |
| F10 | §3.2 alpha/beta/R² vs Nifty | OPEN | invariant #21; gate is incomplete without it |
| F11 | §2.5 inert config | **DONE** 2026-08-16 (task 2e) — `min_quality_score` and `rank_select_top_k` deleted (they named a scorer that never existed); `lockbox_eval_budget` deleted (it contradicted the assert that enforces invariant #26); `walk_forward_start` now honoured rather than validated-and-ignored; `inverse_vol_weight` and `rank_weight` refused at parse time instead of accepted and ignored; the seven entirely-unread sections carry a dated `NOT ENFORCED` header. Regression: `tests/unit/test_config.py`, 7 of 7 mutations caught | Decide: enforce or delete. Never leave it ambiguous |
| F12 | §3.5 DSR/PBO (task 1.9) | OPEN | Correct order — only meaningful once a candidate passes |
| F13 | §3.3 withdraw the invalid Nifty CAGR comparison in `TASKS.md` | OPEN | A wrong number is currently written down as a headline |
| F14 | §4.4 universe is ~98 names, not 600–900 | OPEN | Not a bug — but the scope choice was made on a wrong number |
| F15 | §4.5 ₹1L + whole shares filters the universe | **DECIDED** 2026-08-10 (D8, D9) — ₹10L edge run + ₹1L seed run; gate reads seed; `NEEDS_MORE_CAPITAL` verdict | Conflates "does it work" with "does it work on ₹1L" |
| F16 | §3.6 folds differ per strategy | ✅ **DONE 2026-08-17**, as a consequence of F40. The cause was the per-strategy purge; with one fixed seam every strategy produces identical folds. `scripts/run_backtest.py` now *checks* that the spans match and prints a warning header if they ever diverge again, rather than printing a standing caveat | Cross-strategy comparison was not like-for-like |
| F17 | §3.7 regime breakdown + cost stress (1.8) | OPEN | Already-specified work, never run |
| F18 | walk-forward split for intraday | **DECIDED** 2026-08-10 (D7) — two separately-pinned splits, `lockbox_start` unmoved | `data_split` is deliberately pinned; moving it needs a dated amendment |
| F19 | §6b.1 data-QA gate never applied to the panel | **CLOSED** 2026-08-10 — six of seven rules already enforced, impossible, or superseded; the seventh was built, measured, and found to have no job here (§6c) | Turned out to be one rule, and that rule was wrong for this data |
| F23 | **Annulled trades are in the panel.** 32 symbols carry 20%-circuit prints from the Emkay flash crash of 2012-10-05; NSE annulled trades that day. A backtest stop would "fill" against a price that was legally undone | **NEW** 2026-08-10, OPEN | Found while measuring the bad-tick detector. Narrow and real, and it wants a **list of annulled sessions** — not a statistical test, which cannot tell an annulled print from a genuine crash |
| F24 | **The look-ahead sweep passes vacuously for 62 words.** `test_no_primitive_sees_the_future` walks the whole registry, but on its test series 62 of the SMC structure/zone words return all-`nan`, so the prefix comparison holds trivially. They are hand-checked in `test_dsl_structure.py` / `test_dsl_zones.py`, so this is a weaker claim rather than a hole — but the sweep reads as covering them | ✅ **DONE 2026-08-17 (task 2g-1).** The count was **71 of 182** by the time it was fixed, not 62. Cause: the sweep's fixture set every wick to a constant `±0.5`, so equal bodies produced *exactly equal* highs — and every SMC structure word needs a **strictly** higher high to confirm a swing. No swing ever confirmed, so `swing_high` and everything above it returned `nan` for the whole series, and `nan == nan` passed. Fixed by drawing the wick from a seeded pool (stable per bar under truncation, so a prefix cannot differ on noise) and lengthening the series 120→600. Now **2** blank, both `bpr_*`, which need a bullish and bearish gap live and overlapping at once — a random walk essentially never produces one — and both are now covered by hand-built fixtures in `test_dsl_zones.py`; the sweep names them individually so a third cannot join quietly. **The sweep was blind, not merely thin:** with the confirmation lag removed from `_confirmed` so every swing is reported `k` bars early, the old fixture caught it on **0 words** and the new one on **37**. No real look-ahead bug was found in the 71 — they all pass genuinely now. 4 of 4 mutations caught | Found while building the split sweep in task 2a, which hit the same wall. Fix is the same: a bar builder with a genuinely random intrabar range (a fixed `+c` high makes consecutive highs tie, so no swing is ever strictly confirmed) |
| F25 | **`rank_by` and `xs_*` accept a market-wide value.** `benchmark_return`, `advance_decline_ratio`, the three breadth words and — added after the 2a code review — the feed words `fii_net_index_fut`, `client_net_index_fut` and `in_fno_ban` all return one value for the whole universe. Ranking by any of them gives every symbol the same number, so the sort falls through to the symbol name: a degenerate alphabetical ranking that looks like a working ranker | **NEW** 2026-08-12, OPEN | Same family as F1 and cheap to fix, but it needs a second declared flag ("returns one row"), which is out of 2a's scope. No shipped strategy does this today |
| F26 | **`xs_rank` is now unreachable.** 2a refuses it in `rank_by` because it counts upward from the best (1 = highest) while the simulator fills the book from the largest value down — so it bought the *weakest* candidates. But `rank_by` is the only position a `CROSS_SECTIONAL` word can occupy (`_condition` needs an event; no `SeriesParam` in the library accepts the kind), so the refusal retires the word | **NEW** 2026-08-12, OPEN | Deliberate: a word that reliably picks the losers is worse than one nobody can reach, and `xs_percentile` (1.0 = best) does the same job correctly. Reopens if the general series-arithmetic work in F22 gives cross-sectional words somewhere else to live |
| F27 | **17 of the 93 declared `scale_free` flags carry no verification.** The split sweep excludes `needs_panel`, `requires_feed` and `intraday_only` words because they cannot be computed from one symbol's bars, so for those the flag is only checked to be non-`None` | ✅ **DONE 2026-08-17 (task 2g-2).** The single-symbol split sweep skips every `needs_panel`, `requires_feed` and `intraday_only` word, leaving **17 of 93 declared flags with no verification at all** — the same shape as the finding this whole guard exists for, one level up. A **panel half** of the sweep now re-denominates one symbol inside a 25-name universe and demands that symbol's own column be unchanged, covering the 11 reachable panel words. A coverage test asserts the two sweeps **partition** the declared vocabulary, so a new panel word cannot land in neither. The remaining 6 (`delivery_pct`, `delivery_qty`, `in_fno_ban`, `fii_net_index_fut`, `client_net_index_fut`, `xs_sector_neutral`) have compute functions that **raise** — five waiting on F7 to thread feeds into `Bars`, one refusing until the sector map is dated per bar — so they are pinned as unverifiable-by-construction and **will fail the moment somebody implements them**, forcing the flag to be checked in the same change. Also added the reverse claim that matters most for F1: fed a *rupee* input, `xs_percentile`/`xs_rank`/`xs_zscore`/`xs_demean` must **move** — they produce a dimensionless output whatever they are given, so it would be easy to read them as laundering any input into comparability. **Mutation testing found the fixture was the weak part**: with a mid-priced split symbol, a word comparing `close` to an absolute level survived, because a stock at 290 and the same stock at 2,030 are both above almost any threshold. Splitting the *cheapest* name in the universe moves it across the whole price range and catches it. 4 of 4 mutations caught | Raised by the 2a code review. Low severity today — the feed words all `_refuses` until 1.7 — but the panel words are live, and the claim "every flag is proved" is narrower than it reads |
| F28 | **Three words tell the lead-in rule nothing and are granted zero.** `obv` and `ad_line` are running totals from bar one, so no lead-in of any size reproduces them. `psar` is stranger: it does not converge as history grows, it **oscillates** — matching full history at 300 sessions of lead-in, missing at 700, matching again at 900 — because its acceleration factor resets at whichever trend reversal falls first in the slice; and both its parameters are decimals, so the largest-integer rule finds no number in it at all | **DONE** 2026-08-13 (task 2b) — `Primitive.opaque_lookback`, refused at parse time, measured in both directions by the sweep in `test_dsl_lookback.py` | Two earlier drafts described `psar` wrongly (first "never settles", then "settles at ~500"); the measured assertions caught both, which is the argument for measuring rather than declaring |
| F29 | **The lead-in a word gets is its own widest parameter, and for ~111 words that is too little.** Two causes. Recursive words never exactly match: given exactly 14 sessions, `rsi(14)` is **32% out** on the first bar of a span and `macd` is **41% out**, decaying over the following bars. Structure/SMC words come out *blank* rather than wrong, because the swing that would confirm them sits behind the cut | ✅ **DONE 2026-08-16 (task 2f).** Counts were pinned at **112 short-changed and 4 unmeasurable** by `test_how_many_words_are_still_short_changed_is_pinned_not_ignored` — the first draft said 111 because it scored "produced no value at all" as "agrees", which the review caught so it cannot grow quietly. **Measurement then killed the obvious fix**: a Wilder-smoothed word needs roughly 22× its own window before it agrees with full history, and `rsi(200)` needs more sessions than the panel contains, so no lead-in multiplier is both sufficient and affordable. `evaluate_once` removes the approximation instead of tuning it — the strategy is evaluated once over the whole development span and each fold slices the result, which is what a live system has on the morning it starts. Not look-ahead, because every primitive is causal | Affects the start of every fold for every strategy, `donlevey` included. The likely fix is cheap and structural: **the lead-in and the purge are currently the same number and should not be.** A lead-in reads history the strategy would genuinely have had live, so it is not leakage and can be generous almost for free; a purge costs folds and should stay tight. Needs an operator decision because it moves every number |
| F30 | **`embargo_sessions` is reported but never applied.** It is read from `goal.yaml`, stamped onto every `Window`, and printed in the operator metric sheet through `FoldResult.as_json()` — and it never enters the index arithmetic in `walk_forward_windows`. The sheet says `embargo_sessions: 5` for a gap that does not exist | ✅ **DONE 2026-08-16 (task 2f).** `seam = purge + embargo`, applied to both `train_end` and `test_start`. Cost is 5 sessions at the shipped setting. **What the gap is actually for is now written down honestly and is open as F40** — the purge's original justification did not survive `evaluate_once` | Raised by the 2b code review. Pre-existing, but it is the same defect class as F3 and F28 — a guard that reports itself as enforced. Needs a decision on what the embargo should do before it is wired, since turning it on moves every fold boundary again |
| F31 | **The purge is a backward gap now sized partly by a forward number, and the folds it produces are compared as if they matched.** `longest_lookback` correctly reads `exit`, which means `time_stop(bars: N)` — a *holding period* — inflates the *purge*, a backward guard. That is the accepted over-inclusive policy, but the consequence was not written down: `baseline_buy_and_hold` now runs 7 folds from ~2015 while `xs_momentum_20` runs 8 from ~2014, and `scripts/run_backtest.py` prints their Sharpe, CAGR and drawdown side by side with nothing saying the spans differ. **The control is measured over a different period from the strategy it is a control for** | ✅ **DONE 2026-08-17**, as a consequence of F40 — the seam no longer depends on the strategy at all, so `longest_lookback` reading `exit` can no longer inflate a backward guard. **Step 3c's common-window comparison is now the default rather than a correction applied afterwards**, and the sheet asserts the spans match instead of warning that they might not | Raised by the 2b code review. F16 with a sharper edge |
| F32 | **Entry charges were re-booked in full on every partial exit.** `position.entry_charges` is the cost of the *whole* entry and was attached to each `ClosedTrade` as the position drained: a 2,500-share position closing in nine chunks booked Rs 2,673 against Rs 297 actually paid, straight into net P&L, expectancy and the tax ledger | **DONE** 2026-08-14 (task 2c) — pro-rated by filled fraction against a new `OpenPosition.entry_quantity` | Pre-existing and money-path; found by the 2c review because the write-off inherited the field |
| F33 | **A dark holding was marked at zero in the equity curve.** Open P&L is marked at the day's close and a dark day has none, so a position dropped out of equity entirely when its symbol stopped printing and reappeared as realised P&L up to twenty sessions later — two invented daily returns with a genuine peak-to-trough between them, feeding volatility, Sharpe and max-drawdown | **DONE** 2026-08-14 (task 2c) — carried at the last traded price, which is what a broker statement does | Found by the 2c review; the write-off supplied the second half of the artefact, so the fix is what made the symptom visible |
| F34 | **Nothing caps how much of the account one name may take.** The cash constraint added in 2d stops the book deploying more than it has, but a single position may still be 100% of it, leaving nothing for the other three slots — allocation is first-come, first-served by rank | ✅ **DONE 2026-08-17 — operator decision D11: 0.25.** The operator proposed 0.50; the arithmetic argued it down. With C of the book in one name and an overnight gap g, the account loses C×g — and a stop is not a guarantee overnight, which `fills.py` already models by filling a stop at the worse of trigger and open. At C=0.50 a 20% lower circuit is a **10% account loss, exactly `max_drawdown_killswitch`**: one name, one morning, operator-only restart, from a position nominally 'risking 0.5%'. At 0.25 the same gap costs 5%. 0.25 is also **derived rather than picked** — `max_open_positions` is 4, so it is one name's equal share of a full book, and a test pins the two together so they cannot drift apart. It **reduces** the position rather than refusing it (the fourth term in CLAUDE.md §4's `min(...)`), unlike the cash gate which skips: cash is scale-dependent so a skip is the D9 `NEEDS_MORE_CAPITAL` signal, concentration is scale-invariant so there is nothing more money would fix. Sized against the **filled** price, not `bar.open`, so slippage cannot leave it a few bps over. Code refuses any value above 0.50 (`_MAX_POSITION_PCT_CEILING`), the crypto-leverage belt-and-braces shape. Resized entries are counted and printed. 5 of 5 mutations caught | Latent today: the shipped strategies deploy 1-8% per name. Becomes live with tighter stops or intraday bars, the same conditions that made F6 bite |
| F35 | **The long-term capital-gains threshold was 360 days, not twelve months.** `taxmodel.py` computed it as `ltcg_holding_months * 30`. s.2(42A) counts calendar months, and twelve of those are 365 or 366 days — so every delivery trade held **361 to 365 days** was booked mis-bucketed. **Wrong in both directions, which the first write-up of this row got wrong.** A *gain* in the band was under-taxed — 12.5% with the ₹1.25L exemption instead of 20% with none. A *loss* in the band was under-valued: with no inter-bucket set-off an LTCG loss shelters future gains at 12.5% where an STCG loss shelters them at 20%, so a ₹100,000 loss followed by a ₹100,000 STCG gain cost ₹20,800 under the old classification and nothing under this one. Which way a strategy was flattered depends on its win/loss mix in those five days. A fold's test window is about 365 calendar days and the baseline control holds to the end of the fold, so it sits in the band | **DONE** 2026-08-16 — `bucket_for` takes the two dates instead of a day count, because a day count cannot express the rule; calendar arithmetic on IST dates; the anniversary itself reads short-term, one day more conservative than the common reading, flagged for the CA with O7. 6 of 6 mutations caught, plus a seventh the review found surviving (the entry-side IST conversion had no test at all) | Found by the code review run before task 2e. **It did not change any promote/reject verdict — see F38.** **What hid it was the comment above the constant**, which claimed the approximation "errs toward STCG (the higher rate) more often than not" — it erred the other way, always. Same shape as F1: a description asserting the opposite of the code, so nobody checked |
| F36 | ✅ **DONE 2026-08-16 (task 2e).** Ceilings pinned in code for the three kill-switches (the values CLAUDE.md §0 names) and floors for the three statutory tax rates; the two judgement gate thresholds carry `Amendment` logs like `min_sharpe`. Stricter is still allowed in every case; only loosening refuses. **Six safety limits could be edited to nothing and the loader accepted it.** Verified by loading mutated configs: `max_drawdown_killswitch` 0.10→1.00, `daily_loss_limit` 0.03→1.00, `vda_flat_rate` 0.30→0.00, `stcg_rate` 0.20→0.00, `stop_gate.require_sharpe_lower_bound_above` 0.0→−5.0 and `max_pbo` 0.50→1.00 all load cleanly. Only `crypto_max_leverage_hard` refuses, because it alone carries an explicit assert. Invariant #4 says hard limits cannot be overridden by any strategy or the learning loop — they cannot, but a typo can. The stop-gate row is the sharpest: the block pins `pre_registered_on` and asserts the date never moves while every threshold under it stays freely editable, which is the "assert a provenance that is false" failure `assert_traceable` exists to prevent | ✅ **DONE 2026-08-16 (task 2e)** — folded into 2e, which became both halves of F11: inert keys that promise enforcement that does not exist, and enforced-looking limits that can be edited to nothing | The pattern already works once; it was simply never applied to the rest |
| F37 | ✅ **DONE 2026-08-16 (task 2e).** **Two more inert config items, and a third that lies.** `overfitting.lockbox_eval_budget: 50` contradicts `data_split.lockbox_uses_allowed: 1` (invariant #26, consumed exactly once) and neither is wired to anything, so whoever wires `LockboxGuard` picks the more plausible name and gets 50. `data_split.walk_forward_start` is validated and never honoured — windows anchor on the panel's first session, latent only because the two dates currently coincide. And `trade_quality.min_quality_score` / `rank_select_top_k` name a scoring concept that exists nowhere in the codebase | ✅ **DONE 2026-08-16 (task 2e)** | Found by the code review and the ponytail audit run before 2e |
| F38 | **The stop gate does not read after-tax numbers, though the config says it must.** `stop_gate.net_of_cost_and_tax` is asserted `True` by the loader with the message "gross-only metrics are a bug" — and is read by no code. The gate checks Sharpe, trade count and expectancy, all computed by `metrics.py` from an equity curve that is net of **costs only**; tax is computed afterwards over the closed-trade ledger and printed as an informational line. `Metrics`' own docstring claimed "every field is net of cost and tax", which was never true | ✅ **DONE 2026-08-16 (task 2f).** `BacktestResult.oos_after_tax` carries the curve with each year's bill deducted on the session it falls due, and `gate_verdict` reads it. **The first attempt at this fix did not work and the review caught it — see F42**: pointing the gate at the after-tax record changed only the Sharpe check, because expectancy, win rate and trade count come from the trade ledger, which tax never touches | CLAUDE.md §5 requires cost **and tax** inside every backtest, and invariant #21 gates on alpha after cost and tax. Found because F35's write-up claimed the tax bug reached the gate; checking that claim showed nothing does |
| F39 | **`requires_lt` had one user and fifteen candidates.** The mechanism that refuses a parameter *pair* that is individually legal and jointly meaningless shipped in 2b applied to the single word that prompted it (`roc_skip`), while `macd(fast=26, slow=12)` — which computes cleanly and is exactly the negative of the real thing — parsed happily | ✅ **DONE 2026-08-16 (task 2f), then immediately half-reverted, which is the more useful half of the story.** 2f added fourteen declarations by scanning for parameter names that *looked* ordered. **Nine of the fourteen were wrong** and the parser began refusing well-defined configurations: `stage(n=50, slope_n=63)` is a quarterly slope on a ten-week MA, `darvas(n=3, confirm=20)` asks a short high to hold longer, and `vol_percentile` transposed is a coarse percentile — weak, not degenerate. Final list is **six**: `macd`, `macd_signal`, `macd_hist`, `ppo`, `roc_skip` (sign flips on 100% of bars, measured) and `kama` (trend-cleanliness-to-smoothing-speed correlation goes +0.978 → −0.978, so it smooths most exactly where its docstring says least). The test now re-measures the sign flip on every run rather than trusting the list | The membership rule is **inversion, not oddity**: a pair is refused only when transposing it makes the word mean the opposite of its own name. Over-applying a rule is as much a failure to think as under-applying it, and it fails in the direction nobody notices — a strategy that will not parse |
| F40 | **The purge/embargo gap no longer guards what it says it guards, and `goal.yaml` describes an embargo the code does not implement.** The purge's stated justification was "a 200-session average on the first test day is built from training days" — which `evaluate_once` (F29) makes true of *every* test day by construction, and which was never a leak in the first place, because reading history you would genuinely have had is what a live system does. Separately, `goal.yaml` defined `embargo_sessions` as "dropped **after** each test window before training resumes" while the code widens the gap *before* the test window | ✅ **DONE 2026-08-17 — operator decision, taken on evidence rather than taste.** The per-strategy purge is **deleted**; the gap is now one strategy-independent constant, `backtest.seam_sessions`. Verified three ways before deciding: (1) purging exists to stop a *fitted* model learning from observations whose labels overlap the test set (López de Prado, *AFML* ch. 7) — **this engine fits nothing per fold**, strategies are pre-registered with fixed parameters and the in-sample record is measured rather than optimised against; (2) read in code, `_run_span` constructs a fresh `PortfolioSimulator` with fresh equity per span, so **no state at all crosses train→test** and there is no channel for a leak to travel; (3) there is no Kelly or other fitted sizing anywhere in the engine. **The value did not change** — 5 was set before any result existed and was not retuned once results existed (invariant #25); only the structure changed. **This also closes the mechanism behind F16/F31**: every strategy now produces identical folds, so the benchmark is finally measured over the same window as the strategy it controls for. The *textbook* embargo — excluding each earlier test window from later folds' training, which an anchored window swallows whole — is deliberately **not** built, and `goal.yaml` carries a `NOT ENFORCED` note saying it becomes mandatory the day the Inventor fits per fold. 3 of 3 mutations caught | Two real things survive and are now written down: the gap keeps the in-sample and out-of-sample *trading* periods separated so `sharpe_decay` compares distinct stretches, and it is the harness being correct in advance of Phase 2, when the Inventor starts fitting per fold and the leak becomes real. **The question the gap does not answer:** with an anchored window, every later fold trains on every earlier test period, and no gap before the test window changes that. Cost of the 2f change is 5 sessions, not the year a first reading suggested |
| F41 | **The tax bill was converted against an account four times too large, always in the flattering direction.** `_after_tax_curve` scaled a rupee bill by `starting_equity × stitched_index`, but folds each reset the simulated book to `starting_equity`. A ₹40,000 bill earned on a ₹1,00,000 book is 40% of it; once the stitched index reached 4.0 it was charged as 10%. **Tax drag was understated in exact proportion to how well the strategy had compounded** — and it landed on `oos_after_tax`, the record the gate reads | ✅ **DONE 2026-08-16 (task 2f).** `_stitch` now returns the fold-local rupee book alongside the index, and the bill is a share of the account that earned it | Found by the code review of 2f. Same family as F38: a number that is wrong only in the direction that makes a strategy look promotable |
| F42 | **F38 surviving inside its own fix — two of the three "AFTER TAX" gate checks were still pre-tax.** `gate_verdict` was pointed at `oos_after_tax`, but `summarise` derives `expectancy_r`, `win_rate` and `trades` from the *trade ledger*, and tax never touches a trade. So `oos_after_tax.expectancy_r` was **identical** to the pre-tax figure by construction, and a strategy at +0.03R before tax and negative after 20% STCG passed an `expectancy > 0R` check under a heading that said AFTER TAX. Additionally the last financial year's bill was discarded entirely: the deduction was applied *after* the point was emitted, so a bill at the final index — which the last FY's last session always is — hit nothing | ✅ **DONE 2026-08-16 (task 2f).** The bill lands on the session it falls due. Tax cannot honestly be attributed to individual trades (annual, on the aggregate, with set-off), so no per-trade after-tax expectancy is invented: the pre-tax check keeps its pre-registered form and is **labelled** `expectancy > 0R (before tax)`, and `P&L after tax > 0` is added as a check of its own. Strictly harder to pass, which is the only direction the gate may move once results exist (invariant #25) | Found by the code review of 2f, which also caught that the diff's own test enshrined the discarded-bill bug by asserting the final point was unchanged. A green test proves nothing until the bug reintroduced makes it fail |
| F43 | **The trial ledger recorded a different Sharpe from the one the gate judges.** `record_trial` wrote the pre-tax `oos.sharpe`, while the gate moved to `oos_after_tax`. The DSR overfitting correction in task 1.9 reads this ledger, so the correction and the promotion decision it exists to correct would have been computed on two different quantities | ✅ **DONE 2026-08-16 (task 2f).** Both are recorded | Found by the code review of 2f |
| F44 | **The repo did not pass `mypy`, and had not for some time.** `CLAUDE.md` §2 requires it clean and §6 makes it part of the definition of done; the tree carried **23 errors**, all `unused-ignore`. Worse, clearing them revealed **12 real type errors underneath** — the stale suppressions had been masking genuine problems in six test modules, including a `<` comparison between `int` and `str` in the very sweep that checks `requires_lt` pairs | ✅ **DONE 2026-08-16 (task 2f).** All 35 fixed — `_Ohlc` TypedDict for the OHLC fixtures, `npt.NDArray[np.float64]` for a bare `ndarray`, narrowing asserts where a `dict[str, int \| float \| str]` was compared or assigned. **`uv run mypy` is now clean across 119 files** | Found while checking that 2f had not added errors: the baseline was not zero. A definition of done that is not enforced is not a definition of done — the same class as F3, F28 and F30, applied to the toolchain instead of the config |
| F20 | §6b.2 two-source cross-check never applied to the panel | OPEN | The panel is single-source and unverified, contrary to what `TASKS.md` claims |
| F21 | §6b.3 `tests/golden/` empty — task 1.12 does not exist | **BLOCKS NOTHING YET, SEQUENCED** — capture *after* Step 1, never before | The definition of done in `CLAUDE.md` §6 references a test that has never existed |
| F22 | §6b.4 no lag operator, no series arithmetic in the DSL | **PARTLY DONE** 2026-08-12 (task 2a) — `roc_skip(n, skip)` added, so 12-1 momentum is now expressible and Jegadeesh-Titman can be tested as written. The general case (a lag operator, arithmetic between two arbitrary series) is still OPEN | 12-1 momentum and any two-series expression are inexpressible |
| F7b | §6b.5 India-feed **history has never been downloaded** | OPEN | Finding F7 needs a backfill of 3 report types × 11 years before any wiring |

---

## 6b. Found in the completeness sweep, 2026-08-10

Four more, found by looking at the parts the first pass did not open. Two of them are the same
shape as §4.3: **built, tested, and never connected to anything.**

### 6b.1 🔴 The data-QA gate is not applied to the backtest panel

`icarus/agents/data/quality.py` (task 1.1b) — bad-tick rejection at `max_bar_move_atr: 8.0`,
unadjusted-action detection at `max_single_bar_move: 0.5`, `min_day_score: 0.98`,
`stale_sessions_symbol_veto: 2` — is imported by exactly one module: `agents/data/agent.py`, the
**live** ingestion path.

`panelbuild.py` imports `nse`, `calendar`, `logging` and `dsl`. It reads the bhavcopy day-cache raw.
**No bad tick has ever been rejected from the panel every number in this project came from.**

The corporate-action quarantine (±25% residual gap) catches some of the same territory, but it is a
coarser test that only fires around corporate actions. A bad tick on an ordinary day passes straight
through.

### 6b.2 🟠 The two-source cross-check is not applied to the panel either

`icarus/agents/data/crosscheck.py` (task 1.1) is imported by **nothing** outside its own tests.

`TASKS.md` says *"bars arrive from two cross-checked free sources (1.1)"*. That is true of the live
feed design. It is **not** true of the panel: it is single-source NSE bhavcopy, never compared
against Yahoo, never verified.

### 6b.3 🔴 `tests/golden/` is empty — task 1.12 does not exist

`CLAUDE.md` §6 defines a unit of work as done only when *"the **golden backtest regression** still
passes"*. `TASKS.md` §"Definition of done" repeats it. **There is no golden backtest regression.**
The directory was created on 2026-07-27 and has been empty since. That clause has never once been
enforceable.

**This has a direct sequencing consequence.** The Step-1 fixes will move every number in the
project, and there is no regression net to say what *else* moved. But a golden test captured from
today's engine would freeze the bugs into the baseline. So the order must be: **fix Step 1 → then
capture the golden baseline from the corrected engine.** Not before.

### 6b.4 🟠 The DSL has no lag operator and no arithmetic between series

Composite operators are `all` and `any` only — both boolean. There is no `lag`/`shift`, and no way
to subtract, divide or otherwise combine two arbitrary series.

Consequence: **the standard momentum construction is inexpressible.** "12-month return skipping the
most recent month" (Jegadeesh–Titman, and every serious implementation since, because the skip
removes short-term reversal) cannot be written. `roc(252)` alone is the closest available and is a
measurably weaker factor.

`relative_strength` handles benchmark-relative subtraction as a built-in special case, so that
specific need is covered. The general gap stands and it limits which published strategies we can
reproduce faithfully — which matters most for the calibration argument in §6c.

### 6b.5 ⚠️ Correction to the size of finding F7

`var/` contains `bhavcopy`, `corpactions` and `calendar`. It contains **no delivery, participants or
F&O-ban data**, and `scripts/` has a backfill script for bhavcopy only.

So finding F7 is bigger than "wire the feeds into the panel". The modules exist and were verified
against spot-checked live files during 1.1d, but **11 years of history for three separate NSE report
types has never been downloaded.** It needs a backfill first.

## 6c. THE PLAN — everything that happens before the next backtest

Agreed 2026-08-10. Re-ordered after the completeness sweep (§6b) moved two things and promoted a
third to the front.

**The governing constraint:** every backtest run is a trial on the lifetime ledger (invariant #24),
and the multiple-testing correction raises the Sharpe bar in proportion to the count. At 9 trials
the effective bar is ~0.84; at 17 it is ~0.95 *(estimate — task 1.9 computes it exactly)*. **So the
next run has to be right the first time.** Anything that would force a re-run for a reason other
than a new idea belongs before it, not after. That is why the report work (Step 4) and the
benchmark-relative metrics sit *ahead* of the sweep rather than behind it.

**Every finding in §6 is accounted for below** — as a task, or as an explicit deferral with a
reason. Nothing is left merely unmentioned.

*That claim was false between 2026-08-12 and 2026-08-17.* Five findings raised after the plan was
written — F23, F24, F25, F27 and F34 — were never added to any step, so a sentence promising
completeness was doing the opposite: it invited the reader to stop checking. Step 2g now holds four
of them, and F34 is named there as an operator decision. **A plan that asserts its own completeness
has to be re-checked every time a finding is added, or the assertion is worse than none.**

### Step 1 — Make the panel itself trustworthy *(new; promoted to first)*

The panel is the input to everything else. Fixing arithmetic on top of bad numbers is wasted work.

| task | finding | what |
|---|---|---|
| **1.1** | F19 | ✅ **DONE 2026-08-10.** Scope corrected on contact with the code — see below. |
| **1.2** | F19 | Rebuild the panel; report exactly what was rejected and what it cost, the same way the quarantine is reported. |

**1.1 as built, and why it is narrower than it was written.** Checking the gate's seven rules
against `panelbuild` found three already enforced in `_row_values` (and *more* strictly — the panel
refuses sub-₹1 quotes, the gate only non-positive ones), two impossible by construction, and one —
the ≥50% corporate-action test — **actively harmful to port**: it blanks the bar to `nan`, and
`_quarantine` only compares *consecutive present* sessions, so a genuine unexplained repricing
would have become invisible and never truncated anything.

So finding F19 was one missing rule, not a missing layer. What was built:

- `_reject_bad_ticks` — the ATR excursion test, firing only when the overnight move is **inside**
  `MAX_UNEXPLAINED_GAP`, so a bad print and a repricing cannot hide each other.
- **Reordered** to back-adjust → bad ticks → membership → quarantine. Before membership so a
  fabricated print cannot buy a name into the universe; before the quarantine because the gap audit
  cannot tell a bad print from a capital change and deletes everything prior when it guesses wrong.
- Day scores against `min_day_score`, **reported and never acted on** (§29.4 makes that the
  validation gate's call, not the builder's).
- A **differential test** proving `_row_values` and `DataQualityGate` agree on every structural
  rule, with the one deliberate divergence — the sub-₹1 floor — pinned as its own test.
- `goal.yaml` now records, per key, where each `data_quality` threshold is enforced or why it is
  not. `stale_sessions_symbol_veto` turned out to be already implied and stricter: membership
  requires presence in *every* session of the 20-day turnover window.

**What mutation testing found.** The first version had a vectorised pre-filter in front of the
sequential walk. Two of seven mutations **survived** — the band guard and the warm-up guard —
because the pre-filter carried its own copies of both and skipped the symbol before the walk ran.
The two rules that matter most had no single site where breaking them was visible. The pre-filter
went; the walk keeps a running true-range total to stay O(1) per bar. All 7 then caught.

### 🔴 …and then the detector was measured against real prices, and reverted

Built at `5dc68e6`, removed at the next commit, **the same day**. Over 2011–2022 it rejected
**4,053 bars across 480 symbols**. Every one of the 761 that could be diffed against the previous
panel fell into one of three buckets. **None was a data error.**

| what it actually was | count | examples |
|---|---:|---|
| **Real market events** — the close confirmed the move | 383 | DHFL −55% (2018-09-21, IL&FS contagion) · PNB +49% and CANBK +40% (2017-10-25, recapitalisation) · ADANIENT −83% (2015-06-03, demerger) · RCOM · PCJEWELLER · ZEEL |
| **An artefact of the threshold itself** — ATR collapses toward zero on a flat instrument, so 8× almost-nothing is cleared by rounding | 220 | LIQUIDBEES at a pegged ₹1000 · thin names printing an identical price for a fortnight |
| **Real prints at the 20% circuit band** | 158 | 32 symbols on **2012-10-05** — the Emkay erroneous-order flash crash · BRITANNIA · OFSS · NESTLEIND · INFY · ITC |

**The premise was wrong.** Bhavcopy is the exchange's own end-of-day settlement file, not a live
tick feed; it does not carry the random bad prints an ATR test exists to catch. And the failure is
in the worst possible direction: the test deletes the **largest** moves, which are exactly what
sets drawdown and tail risk. Removing DHFL's −55% and ADANIENT's −83% would make every backtest
look *safer* than the market was.

Two mistakes of my own, both worth naming:

1. **I documented one rule and implemented another.** The docstring said a bad tick is "a spike the
   close does not confirm". The code never looked at the close — it only measured the excursion.
   Applying the documented rule to the same data would have kept all 383 real events.
2. **`atr > 0` is not a floor.** On a near-flat instrument the ATR is *positive but negligible*, and
   the threshold becomes noise. It needed a floor relative to price.

Even corrected on both counts, the remaining 158 are real prints of real trades. So the answer is
not a better threshold; it is that this test has no job here. **The revert is verified:** rebuilding
the panel afterwards reproduces the pre-1.1 report field for field, quarantine list included.

**Kept from 1.1** (all of it independently valuable): the differential test proving `_row_values`
and `DataQualityGate` agree on every structural rule; the sub-₹1 divergence pinned as its own test;
the per-key enforcement map in `goal.yaml`; and the analysis of all seven gate rules, recorded in
the `panelbuild` docstring so the detector is not rebuilt from the same false premise.

**Deferred here, with the reason recorded:** F20, the two-source cross-check. Yahoo's Indian coverage
for **delisted** names is poor — already established when RCOM returned nothing during the corporate
-actions work. A cross-check would therefore verify survivors only, and a verification that
systematically skips the names most likely to be wrong is worse than none: it would produce a
confidence number that does not mean what it says. Reopens if a source with delisted coverage is
acquired (see §4 option (c), TickData).

### Step 2 — The engine measures the strategy that was written

| task | finding | what |
|---|---|---|
| **2a** | F1, F22 | ✅ **DONE 2026-08-12.** Delete `momentum`. `roc` = percent, `momentum_abs` = rupees. `scale_free` declared on the 93 words where it is undecidable, derived for the 131 EVENT/LEVEL words. `xs_*` and `rank_by` refuse a rupee-denominated input at parse time. `roc_skip(n, skip)` added. All three strategy files at v2. **The code review of this task then found three more, all fixed here:** `xs_rank` ranked backwards (now refused — F26), a mis-declared `requires_lt` pair raised `KeyError` from the parser (now a construction-time `DslError`), and the baseline's rewritten header claimed a ranking the engine does not yet perform (corrected in the file — it stays alphabetical until F3/step 2b lands). Proved by the **split sweep** — every word claiming comparability must be unchanged when a symbol's price and share count are re-denominated, and every word denying it must move. 11 of 11 mutations caught |
| **2b** | F3, F28 | ✅ **DONE 2026-08-13.** `longest_lookback` reads `entry`, `rank_by` and `exit` instead of `entry` alone. `Primitive.opaque_lookback` refuses `obv`, `ad_line` and `psar`, whose history requirement no parameter expresses. Proved by a **lead-in sweep** that measures, for every computable word, whether a finite history reproduces its full-history values — it disproved two of my own descriptions of `psar` before the flag was worded correctly. 6 of 6 mutations caught. Raised F29: 112 words are still short-changed, which is a separate decision |
| **2c** | F4 | ✅ **DONE 2026-08-14.** Written off at the last traded price under a `STALE_MARK` reason — on the final bar of a span, or after 20 dark sessions, so an ordinary halt is still carried (both directions tested). Not routed through the FillModel: there was no bar and no counterparty, and fabricating one would dress an assumption as a measurement. Exit charges still applied, because the pessimistic reading is that closing costs what closing costs. Count and gross value on the sheet. Also added, from finding F31: the sheet now prints each strategy's fold count and span, since the purge is per-strategy and the table was comparing different periods silently. **The code review then found the fix half done:** an end-of-data exit the fill model caps or refuses left the residual orphaned exactly as before (4,998 of 5,000 shares in the repro), so nothing may now survive the last bar by any route; a dark holding was marked at **zero** in the equity curve, carving a fake drawdown and spike into the Sharpe the gate reads; entry charges were re-booked in full on every partial exit; and dating the write-off at the noticing bar while pricing it twenty sessions earlier could flip the tax bucket. All fixed. 18 of 18 mutations caught |
| **2d** | F6 | ✅ **DONE 2026-08-15.** The book tracks committed cash — cost basis plus entry charges — and refuses any position it cannot pay for, sharing one budget across the day's entries. Skipped and counted, never shrunk: buying what you can afford is what a real account does, but it would silently change the size the strategy specified and erase the signal D9 exists to read. No leverage ceiling knob — this is the delivery segment, where leverage is not a preference but an impossibility. Proved by a **sweep** over stop widths and universe sizes asserting cash is never negative on any bar, rather than by the cases I happened to think of. **The code review then found four more, all fixed:** the sheet's "took N of M" counted *closed trades* against per-signal skips, so a partially-filled entry inflated it several-fold in exactly the thin-liquidity runs the line exists to describe (and `already_held` was being counted as a refusal); committed cash double-counted the entry charge of a half-sold position; the overflow was labelled `no_slot` **before** the loop ran, so a top-ranked candidate refused for cash left its slot empty while a cheaper one behind it was already written off; and the invariant the change establishes — cash never negative — was asserted nowhere, only its consequences. There is now a guard inside the engine and a test that hands it a book it could not have bought. 8 of 8 mutations caught. **Concentration left open by operator decision:** capping total deployment still permits one name at 100% and nothing for the other three slots |
| **2e** | F11, F36, F37 | ✅ **DONE 2026-08-16.** Both halves of F11: config that promises enforcement it does not have, and config that *looks* enforced and can be edited to nothing. Four keys deleted, seven sections marked, `walk_forward_start` honoured, two weighting schemes refused rather than ignored, six safety limits bounded, two gate thresholds given amendment logs. Also the three carry-overs from earlier reviews: same-day amendments now refuse, the money ledger no longer seeds from a raw float, and the tax-model day count became calendar months (F35). **The review of the first pass found I had done half of almost every item**, and all eight are fixed here: `vol_target_pct` was still accepted-and-ignored (its partner `weighting` had been refused, and 2e's own acceptance criteria named both); `lockbox_window` never got the `walk_forward_start` bound that `walk_forward_windows` did, and it is the fold that is evaluated *once*, so a discrepancy there is unrecoverable; the two gate thresholds got provenance but no bound, so −5.0 still loaded behind a properly signed amendment; five more risk values were left unbounded (`kelly_fraction_cap: 1.0` is full Kelly, `new_strategy_size_factor: 1.0` disables the canary, `stagnation_check_after_trades: 1000000` defers invariant #23 forever); two tax rates were left out of the floor loop; the `Sizing` docstring still described the old behaviour; and `ChoiceParam` advertised three schemes then refused two, which in Phase 2 would have had the grammar-constrained Inventor generating unparseable candidates. 15 of 15 mutations caught. **F38 — wiring the gate to after-tax numbers — is deliberately not here**: it changes verdicts and needs an operator decision |
| **2f** | F29, F30, F38–F44 | ✅ **DONE 2026-08-16.** The guards that don't guard, scoped by behavioural probe of every config value and parameter pair rather than by the audit's list. `evaluate_once` replaces the warm-up prefix entirely — measurement killed the alternative, since Wilder words need ~22× their window and `rsi(200)` needs more sessions than the panel holds, so no lead-in is both sufficient and affordable (F29). The embargo enters the seam arithmetic (F30). The stop gate reads after tax (F38). **The code review then found seven real defects in that work**, all fixed here: two of the three "AFTER TAX" checks were still pre-tax because `summarise` derives expectancy and win rate from the trade ledger, which tax never touches (F42); the last financial year's bill was discarded because it was applied after the point was emitted (F42); the bill was divided by the compounded index instead of the fold-local book that earned it, understating drag in proportion to how well the strategy compounded (F41); the trial ledger fed DSR a different Sharpe from the one the gate judges (F43); a tax year with no session on the curve vanished silently; `NO RESULT` was computed and dropped from the gate table; and **nine of the fourteen `requires_lt` declarations were wrong**, refusing well-defined strategies — the rule is inversion, not oddity (F39). Also: a panel containing the lockbox is refused outright, restoring structurally what whole-span evaluation had left resting on causality alone; and the repo did not pass `mypy` — 23 stale suppressions hiding 12 real type errors, now clean across 119 files (F44). The realism flags were investigated, found **not** to be a hole — the loader pins both true, so they are the config half of a belt-and-braces pair — and the wiring was reverted. **F40 (what the purge/embargo gap still buys) is left open for an operator decision.** 11 of 11 mutations caught |

`roc_skip` rather than a general `lag`: making every SERIES word composable over an arbitrary input
series — instead of implicitly over `close` — is an architectural change, not a Step-2 change. F22
stays open for the general case.

### Step 2g — Is the engine measuring what we think it is? *(added 2026-08-17)*

**These five findings were not in this plan at all**, though §6c's preamble claims every finding is
accounted for. Four of them would force a re-run if they surfaced after Step 7, which is exactly
the thing the governing constraint above exists to prevent, so they belong here.

| task | finding | what | why before the run |
|---|---|---|---|
| **2g-1** | F24 | **71 of the 182 swept words never actually get tested for look-ahead.** `test_no_primitive_sees_the_future` runs on a 120-bar series whose wick is a *fixed* `±0.5`, so consecutive highs tie, no swing is ever strictly confirmed, and the SMC structure/zone words return all-`nan` — and `nan == nan` passes. Measured 2026-08-17: 71 vacuous on the current fixture, **2 on a 600-bar series with a randomised intrabar range**. So the words are fine; the fixture is not | **Task 2f raised the stakes on this and nobody re-ranked it.** While each fold was sliced, the future was physically *absent* from the array the DSL saw. `evaluate_once` evaluates over the whole span, so **causality is now the only thing** between a peeking word and every number the engine produces. A 39% hole in the guarantee that change relies on. Cheap: it is a fixture change |
| **2g-2** | F27 | 17 of the 93 declared `scale_free` flags carry no verification — the split sweep excludes `needs_panel`, `requires_feed` and `intraday_only` words | F1 in another costume. A wrongly-declared `scale_free` means `rank_by` silently ranks by share price, which is a wrong result that looks like a real one |
| **2g-3** | F25 | `rank_by` and the `xs_` words accept a market-wide value — `benchmark_return`, `advance_decline_ratio` and the breadth words are identical for every symbol | Ranking a universe by a number that is the same for every symbol is a no-op that reports as a ranking. Affects 3b and 3c directly |
| **2g-4** | F23 | Annulled trades are in the panel: 32 symbols carry 20%-circuit prints from the Emkay flash crash | Bad prices produce bad fills, bad stops and bad P&L. This is a Step-1 item that Step 1 missed |
| **—** | F26 | `xs_rank` unreachable in `rank_by` | **Accepted, not scheduled.** `xs_percentile` does the job correctly and a word that reliably picks the losers is worse than one nobody can reach |

**F34 is an operator decision, not a task.** Nothing caps how much of the account a single name may
take; the 2d cash constraint stops the book overspending but not over-concentrating. It has to be
settled **before 3b**, because the two capital rows are exactly where concentration bites.

### Step 3 — The engine answers the right question

| task | finding | what |
|---|---|---|
| **3a** | F2 (D1) | **Signal-test mode**: every signal taken, uniform notional, no book cap, no heat cap, no slot competition. Reported separately and never quotable as a portfolio. |
| **3b** | F15 (D8, D9) | Two capital rows on every portfolio test — ₹10,00,000 edge run and ₹1,00,000 seed run. `NEEDS_MORE_CAPITAL` as a third non-promoting verdict. |
| **3c** | F16 | Report each strategy over the **common** OOS window as well as its own, so the cross-strategy comparison is like-for-like. |

### Step 4 — The report says enough to act on

Pulled forward from "later" precisely because of the trial-cost constraint above.

| task | finding | what |
|---|---|---|
| **4a** | F5 (D2) | Four columns: **gross · costs · tax · net**. Currently we cannot tell "no edge" from "edge eaten by costs" — which need opposite responses. |
| **4b** | F5 | Per-trade ledger written to CSV. Today not one individual trade is inspectable. |
| **4c** | F10 | Alpha, beta and R² vs Nifty 50 (invariant #21, `max_benchmark_r2: 0.8`). Without it the sweep produces numbers that immediately need another run. |
| **4d** | F13 | Withdraw the invalid Nifty CAGR comparison from `TASKS.md`. A wrong number is currently a headline in the most-read file. |

### Step 5 — Freeze the corrected engine

| task | finding | what |
|---|---|---|
| **5a** | F21 | The golden backtest regression (task 1.12) — **captured from the corrected engine, never before it.** A baseline taken today would freeze the bugs into it. This is the first time `CLAUDE.md` §6's definition of done becomes enforceable. |

### Step 6 — Write the strategies, then pre-register them

| task | what |
|---|---|
| **6a** | Eight strategy files (§6d), each carrying its published source and the reasoning for every parameter. **No parameter tuned on this data** — round numbers from the source, per invariant #25. |
| **6b** | Pre-register all eight with a date **before** any of them runs. |

### Step 7 — Run. ← *the next backtest*

### After the run, in this order

| step | findings | what |
|---|---|---|
| 8 | F8, F18 (D3, D4) | Intraday: 15-minute bars via Kite; daily bhavcopy keeps sole authority over universe membership; a second independently-pinned walk-forward split from 2015, `lockbox_start` unmoved. |
| 9 | F7, F7b | Backfill 11 years of delivery / participants / F&O-ban, then wire them into the panel and declare them in `available_feeds`. |
| 10 | F12, F17 | DSR + PBO with the lifetime effective trial count; regime stability; cost stress at `cost_stress_multiplier: 1.5`. |
| — | F9 (D5) | Shorts — deferred with a trigger, `OPERATOR.md` §7c. |
| — | F14 | Universe is ~98 names, not 600–900. **No action** — not a defect, but the scope was chosen on a wrong number and the metric sheet should say so. |

### 6d. The strategies to be run in Step 7

Chosen so that **a common failure implicates the engine, not the ideas** — and so that the
best-documented of them acts as a calibration instrument. If Donchian disagrees with its own
published record, that is our bug.

| # | strategy | published by | expression | role |
|---|---|---|---|---|
| F0 | Nifty 50 buy-and-hold | — | benchmark series | Reference, fully invested — makes the CAGR comparison valid at last |
| F1 | Donchian 55/20 breakout (Turtle) | Dennis & Eckhardt, public since 1983 | `donchian_breakout_up(55)` | **Primary calibration instrument** |
| F2 | Cross-sectional relative strength | Jegadeesh–Titman 1993 | `xs_top_n(roc_skip(252, 21), 10)` | Most-replicated equity anomaly |
| F3 | Minervini trend template | *Trade Like a Stock Market Wizard* | `trend_template` — already a primitive | Mechanical, widely used on NSE |
| F4 | Weinstein Stage 2 | *Secrets for Profiting…* | `stage_advancing` — already a primitive | Same trend layer Donlevey uses |
| F5 | 52-week-high proximity | George & Hwang 2004 | `pct_off_high(252)` | Closest published cousin of the Donlevey idea |
| F6 | Low-volatility factor | Haugen–Baker; strong on NSE | `xs_bottom_n(realized_vol(252), 10)` | The anomaly that most reliably **survives costs** |
| F7 | Connors RSI-2 | Larry Connors, published rules | `connors_rsi` | **Counter-hypothesis** — if only this works, that is a statement about the regime |
| F8 | Donlevey sweep-reclaim, corrected | ours | `sweep_and_reclaim_low` | The thesis |

**Calibration runs still count as trials** *(decided 2026-08-10)*. They are tagged
`origin: calibration` in the ledger so that a future decision to weight them differently is
possible **with a documented rationale** — but they are counted by default, because an exemption
is exactly the loophole that would hollow out invariant #24.

## 7. What did NOT go wrong

Worth recording, because the list above is long and the foundation is not the problem.

- **The lockbox is intact.** Last fold ends 2022-04-27; the panel stops 2022-12-30;
  `var/lockbox_uses.json` does not exist.
- **The fill model is genuinely conservative** and survived inspection: strict trade-through for
  resting limits, stops filled at the *worse* of trigger and open (so overnight gap risk is real),
  tick rounding away from us, participation cap always applied.
- **Point-in-time membership is decided on raw prices before back-adjustment** — the subtle version
  of the survivorship bug, and it is handled correctly.
- **The panel is built from bhavcopy**, i.e. every symbol that ever traded, not today's listing.
  No survivorship at the universe level.
- **Costs and taxes are computed per fill from actual filled quantity**, never applied to final P&L.
- **The engine found its own bugs** — the residual-gap audit caught compound corporate actions, the
  exposure assertion caught the calendar/session mix-up, the same-bar assertion caught the exit
  dating.
