# Post-backtest audit — what Icarus actually measured, and what is wrong with it

> **Date:** 2026-08-09 · **Trigger:** operator pause after the first end-to-end backtest (2026-08-07).
> **Status:** findings only. **No code was changed.** Nothing here is fixed yet.
> **Companion:** `TASKS.md` §1.7 findings (a)–(x) records the bugs found *during* the build.
> This document records the bugs found *by looking at the result*.

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

**The capital simply disappears from the accounting** — neither as a loss nor a gain. Quarantine
already removes 10.1% of tradable symbol-days, so this path is very likely live in the results. The
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

Status: `OPEN` · `DECIDED` (approach agreed, not built) · `IN TASKS.md` · `DONE` · `WON'T FIX`

| # | Finding | Status | Why it ranks here |
|---|---|---|---|
| 1 | §2.1 `momentum` is absolute, not percent | **DECIDED** 2026-08-10 — `OPERATOR.md` §7c (D6): delete the name, add `scale_free`, make xs-words refuse rupee inputs | Silently changes what two strategies mean; invalidates existing numbers |
| 2 | §1 unconstrained "signal test" mode | **DECIDED** 2026-08-10 (D1, D2) — two modes, gross+net side by side | The operator's actual question is currently unanswerable |
| 3 | §2.2 `longest_lookback` ignores `rank_by`/`exit` | OPEN | The control was broken; every warm-up guarantee is weaker than believed |
| 4 | §2.3 orphaned positions | OPEN | Money vanishes from the ledger, biased in our favour |
| 5 | §3.1 + §3.4 cost attribution + per-trade log | **DECIDED** 2026-08-10 (D2) | Cannot distinguish "no edge" from "edge eaten by costs" |
| 6 | §2.4 no cash constraint | OPEN | Latent; becomes severe with tighter stops or intraday |
| 7 | §4.3 wire the India feeds into the panel | OPEN | Largest unexploited asset already paid for |
| 8 | §4.2 intraday data | **DECIDED** 2026-08-10 (D3, D4) — 15-min, daily owns membership | The method's own timeframe; invariant #25's prescribed response |
| 9 | §4.1 shorts | **DEFERRED** 2026-08-10 (D5) — `OPERATOR.md` §7c, with its reopening trigger | Half of the thesis, but gated on a working long-only system |
| 10 | §3.2 alpha/beta/R² vs Nifty | OPEN | Invariant #21; gate is incomplete without it |
| 11 | §2.5 inert config | OPEN | Decide: enforce or delete. Never leave it ambiguous |
| 12 | §3.5 DSR/PBO (task 1.9) | OPEN | Correct order — only meaningful once a candidate passes |
| 13 | §3.3 withdraw the invalid Nifty CAGR comparison in `TASKS.md` | OPEN | A wrong number is currently written down as a headline |
| 14 | §4.4 universe is ~98 names, not 600–900 | OPEN | Not a bug — but the scope choice was made on a wrong number |
| 15 | §4.5 ₹1L + whole shares filters the universe | **DECIDED** 2026-08-10 (D8, D9) — ₹10L edge run + ₹1L seed run; gate reads seed; `NEEDS_MORE_CAPITAL` verdict | Conflates "does it work" with "does it work on ₹1L" |
| 16 | §3.6 folds differ per strategy | OPEN | Cross-strategy comparison is not like-for-like |
| 17 | §3.7 regime breakdown + cost stress (1.8) | OPEN | Already-specified work, never run |
| 18 | walk-forward split for intraday | **DECIDED** 2026-08-10 (D7) — two separately-pinned splits, `lockbox_start` unmoved | `data_split` is deliberately pinned; moving it needs a dated amendment |
| 19 | §6b.1 data-QA gate never applied to the panel | OPEN | Built and tested; no bad tick has ever been rejected from the panel |
| 20 | §6b.2 two-source cross-check never applied to the panel | OPEN | The panel is single-source and unverified, contrary to what `TASKS.md` claims |
| 21 | §6b.3 `tests/golden/` empty — task 1.12 does not exist | **BLOCKS NOTHING YET, SEQUENCED** — capture *after* Step 1, never before | The definition of done in `CLAUDE.md` §6 references a test that has never existed |
| 22 | §6b.4 no lag operator, no series arithmetic in the DSL | OPEN | 12-1 momentum and any two-series expression are inexpressible |
| 7b | §6b.5 India-feed **history has never been downloaded** | OPEN | Finding #7 needs a backfill of 3 report types × 11 years before any wiring |

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

### 6b.5 ⚠️ Correction to the size of finding #7

`var/` contains `bhavcopy`, `corpactions` and `calendar`. It contains **no delivery, participants or
F&O-ban data**, and `scripts/` has a backfill script for bhavcopy only.

So finding #7 is bigger than "wire the feeds into the panel". The modules exist and were verified
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

### Step 1 — Make the panel itself trustworthy *(new; promoted to first)*

The panel is the input to everything else. Fixing arithmetic on top of bad numbers is wasted work.

| task | finding | what |
|---|---|---|
| **1.1** | #19 | Apply the data-QA gate (`quality.py`) inside `panelbuild`. Bad ticks **rejected, never winsorized** — clamping invents a price that never traded. Honour `stale_sessions_symbol_veto`. |
| **1.2** | #19 | Rebuild the panel; report exactly what was rejected and what it cost, the same way the quarantine is reported. |

**Deferred here, with the reason recorded:** #20, the two-source cross-check. Yahoo's Indian coverage
for **delisted** names is poor — already established when RCOM returned nothing during the corporate
-actions work. A cross-check would therefore verify survivors only, and a verification that
systematically skips the names most likely to be wrong is worse than none: it would produce a
confidence number that does not mean what it says. Reopens if a source with delisted coverage is
acquired (see §4 option (c), TickData).

### Step 2 — The engine measures the strategy that was written

| task | finding | what |
|---|---|---|
| **2a** | #1, #22 | Delete `momentum`. `roc` = percent, `momentum_abs` = rupees. Add `scale_free: bool` to `Primitive`, set across all 223 words. `xs_*` and `rank_by` **refuse a rupee-denominated input at parse time**. Add `roc_skip(n, skip)` so 12-1 momentum is expressible. Rewrite the three strategy files. **← STOP AND REVIEW** |
| **2b** | #3 | `longest_lookback` reads `rank_by` and `exit`, not only `entry`. |
| **2c** | #4 | A position whose symbol stops printing bars is closed at its last known price with a `DELISTED` reason, not left open forever. |
| **2d** | #6 | Track cash; refuse an entry whose notional does not fit. New skip reason `INSUFFICIENT_CASH`. |
| **2e** | #11 | Every config key either has code enforcing it **or** carries an explicit `# NOT ENFORCED — <reason>, <date>` comment. A reader must never have to guess. Enforce `max_pairwise_correlation`, `min_holding_bars`, `max_trades_per_day_per_strategy`. Make the DSL **reject** `sizing.weighting` values other than `equal_weight` and reject `vol_target_pct` outright until implemented — fail closed. Mark `rank_select_top_k`, `min_quality_score`, `allocation.*` as Phase-3 deferrals in the file itself. |

`roc_skip` rather than a general `lag`: making every SERIES word composable over an arbitrary input
series — instead of implicitly over `close` — is an architectural change, not a Step-2 change. #22
stays open for the general case.

### Step 3 — The engine answers the right question

| task | finding | what |
|---|---|---|
| **3a** | #2 (D1) | **Signal-test mode**: every signal taken, uniform notional, no book cap, no heat cap, no slot competition. Reported separately and never quotable as a portfolio. |
| **3b** | #15 (D8, D9) | Two capital rows on every portfolio test — ₹10,00,000 edge run and ₹1,00,000 seed run. `NEEDS_MORE_CAPITAL` as a third non-promoting verdict. |
| **3c** | #16 | Report each strategy over the **common** OOS window as well as its own, so the cross-strategy comparison is like-for-like. |

### Step 4 — The report says enough to act on

Pulled forward from "later" precisely because of the trial-cost constraint above.

| task | finding | what |
|---|---|---|
| **4a** | #5 (D2) | Four columns: **gross · costs · tax · net**. Currently we cannot tell "no edge" from "edge eaten by costs" — which need opposite responses. |
| **4b** | #5 | Per-trade ledger written to CSV. Today not one individual trade is inspectable. |
| **4c** | #10 | Alpha, beta and R² vs Nifty 50 (invariant #21, `max_benchmark_r2: 0.8`). Without it the sweep produces numbers that immediately need another run. |
| **4d** | #13 | Withdraw the invalid Nifty CAGR comparison from `TASKS.md`. A wrong number is currently a headline in the most-read file. |

### Step 5 — Freeze the corrected engine

| task | finding | what |
|---|---|---|
| **5a** | #21 | The golden backtest regression (task 1.12) — **captured from the corrected engine, never before it.** A baseline taken today would freeze the bugs into it. This is the first time `CLAUDE.md` §6's definition of done becomes enforceable. |

### Step 6 — Write the strategies, then pre-register them

| task | what |
|---|---|
| **6a** | Eight strategy files (§6d), each carrying its published source and the reasoning for every parameter. **No parameter tuned on this data** — round numbers from the source, per invariant #25. |
| **6b** | Pre-register all eight with a date **before** any of them runs. |

### Step 7 — Run. ← *the next backtest*

### After the run, in this order

| step | findings | what |
|---|---|---|
| 8 | #8, #18 (D3, D4) | Intraday: 15-minute bars via Kite; daily bhavcopy keeps sole authority over universe membership; a second independently-pinned walk-forward split from 2015, `lockbox_start` unmoved. |
| 9 | #7, #7b | Backfill 11 years of delivery / participants / F&O-ban, then wire them into the panel and declare them in `available_feeds`. |
| 10 | #12, #17 | DSR + PBO with the lifetime effective trial count; regime stability; cost stress at `cost_stress_multiplier: 1.5`. |
| — | #9 (D5) | Shorts — deferred with a trigger, `OPERATOR.md` §7c. |
| — | #14 | Universe is ~98 names, not 600–900. **No action** — not a defect, but the scope was chosen on a wrong number and the metric sheet should say so. |

### 6d. The strategies to be run in Step 7

Chosen so that **a common failure implicates the engine, not the ideas** — and so that the
best-documented of them acts as a calibration instrument. If Donchian disagrees with its own
published record, that is our bug.

| # | strategy | published by | expression | role |
|---|---|---|---|---|
| 0 | Nifty 50 buy-and-hold | — | benchmark series | Reference, fully invested — makes the CAGR comparison valid at last |
| 1 | Donchian 55/20 breakout (Turtle) | Dennis & Eckhardt, public since 1983 | `donchian_breakout_up(55)` | **Primary calibration instrument** |
| 2 | Cross-sectional relative strength | Jegadeesh–Titman 1993 | `xs_top_n(roc_skip(252, 21), 10)` | Most-replicated equity anomaly |
| 3 | Minervini trend template | *Trade Like a Stock Market Wizard* | `trend_template` — already a primitive | Mechanical, widely used on NSE |
| 4 | Weinstein Stage 2 | *Secrets for Profiting…* | `stage_advancing` — already a primitive | Same trend layer Donlevey uses |
| 5 | 52-week-high proximity | George & Hwang 2004 | `pct_off_high(252)` | Closest published cousin of the Donlevey idea |
| 6 | Low-volatility factor | Haugen–Baker; strong on NSE | `xs_bottom_n(realized_vol(252), 10)` | The anomaly that most reliably **survives costs** |
| 7 | Connors RSI-2 | Larry Connors, published rules | `connors_rsi` | **Counter-hypothesis** — if only this works, that is a statement about the regime |
| 8 | Donlevey sweep-reclaim, corrected | ours | `sweep_and_reclaim_low` | The thesis |

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
