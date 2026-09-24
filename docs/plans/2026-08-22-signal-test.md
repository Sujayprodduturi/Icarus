# Task 3a — the signal test: plan

**Written 2026-08-22, before any code; corrected 2026-09-24 after independent Astra review and operator approval.** Decisions in `OPERATOR.md` §7b D15. The corrections below supersede the original Step-0 trial exemption, transfer-coefficient claim, and overstrong placebo/uncertainty claims. No real-data run has occurred in Task 3a. Steps 0–1 were subsequently implemented on 2026-09-24; the signal-only mode remains unbuilt. Findings below come
from six agents run in parallel — an integration researcher, a statistician, a prior-art
researcher, a test designer, an architect, and a strategist. Where two of them reached the same
conclusion by different routes, that is noted, because independent convergence is the strongest
evidence available here.

**Reference key:** `#N` = safety invariant (`CLAUDE.md` §0). `FN` = audit finding
(`docs/reviews/2026-08-09-post-backtest-audit.md`). `DN` = operator decision (`OPERATOR.md` §7b).
`§N` = a section of the named document.

---

## 1. What this builds, in one paragraph

A second backtest mode. The existing **portfolio test** simulates a real 4-slot book and answers
*"is this runnable?"*. The new **signal test** removes the book entirely — every signal taken,
uniform ₹1,00,000, no slots, no heat cap, no cash constraint — and answers *"is there an edge at
all?"*. D1 mandated both from the start; only the first was ever built, which is why the
2026-08-07 run discarded 94–99.99% of every strategy's signals for want of a slot and could not
distinguish a bad idea from a good idea in the wrong book.

---

## 2. The finding that changes the deliverable

**Measured on our own panel, 2011–2022: a random entry on a random tradable name pays
+1.505% mean return over a 20-day hold, with a 54.6% win rate.**

| horizon | random raw mean | random raw win rate | random *alpha* mean | random alpha median | random alpha win rate |
|---|---|---|---|---|---|
| 5d | +0.265% | 51.2% | +0.030% | −0.166% | 48.1% |
| **20d** | **+1.505%** | **54.6%** | **+0.444%** | **−0.132%** | **49.3%** |
| 60d | +4.471% | 57.6% | +1.124% | −0.349% | 49.0% |

So a signal test reporting *"54.6% win rate, +1.5% mean return per trade"* has measured **nothing
whatsoever** — that is what a coin flip pays on this universe over these years. NSE rose for most
of the development window, and long-only drift reads as edge to any test whose null is zero.

**Consequence: a null is not a nice-to-have on the report, it is the report.** Three agents
reached this independently — the strategist from the drift argument, the prior-art researcher from
`Vibe-Trading/agent/src/factors/bench_runner_strict.py` (which benchmarks a candidate against a
shuffled copy of itself, citing a 9-month A-share audit where every factor passed a raw test at
some setting and **1 of 12** survived the random control), and the statistician by measuring it.

### 2b. And the confidence interval would have been a fabrication

Average pairwise correlation of daily returns across tradable names in our panel: **ρ̄ ≈ 0.27**,
measured two independent ways that agree (session-grouped intraclass correlation 0.256–0.283;
direct off-diagonal mean 0.30, ranging 0.157 in 2017 to 0.434 in 2011 and 0.393 in 2020). It is
not outlier-driven — winsorising at 1% moves it to 0.27–0.29 — and it is the same on a
strategy-selected subset (0.241–0.358), so it is not an artefact of using the whole universe.

Trades opened on the same day are therefore **not independent observations**. On a worked example
(top-20 20-day momentum, 2011–2022, 9,180 trades over 459 entry days, median 80 positions open at
once):

| | naive IID | block-clustered (honest) |
|---|---|---|
| 95% CI on mean return | [+1.767%, +2.287%] | **[+0.703%, +3.350%]** |
| t-statistic | **15.28** | **3.10** |
| effective sample size | 9,180 | **377** |

**A t of 15.3 is really 3.1. Nine thousand trades are really 377.** Across profiles the naive
interval understates the standard error by **1.3× to 7.3×**.

The obvious fix — clustering by entry date — **is not sufficient**, and this is the single most
important measurement of the six reports. It fixes the cross-sectional problem completely and
then fails just as badly as naive when entries cluster in *time*, which is what a trend follower
does by construction:

| profile | naive IID | cluster by entry date | block-cluster |
|---|---|---|---|
| H=20, 20 trades/day, uniform | 0.63 | 0.94 | 0.99 |
| H=20, 10/day, **bursty** | 0.29 | **0.57** | **0.93** |
| H=60, 20/day, **bursty** | 0.17 | **0.43** | **0.95** |

*(actual coverage of a nominal 95% interval, calibrated by Monte Carlo against synthetic trade
bags built from the real panel)*

An estimator that is correct only when the strategy is well-behaved is not an estimator.

---

## 3. Deltas against D15 — what the agents found that D15 did not settle

D15's five answers all survive. These are gaps and conflicts on top of them.

| # | finding | who found it | resolution |
|---|---|---|---|
| **Δ1** | **The two modes are not comparable as specified.** The portfolio test's out-of-sample window opens in **2014** (`goal.yaml:157`, `min_train_years: 3.0` from 2011); D15(e) spans 2011–2022. A quarter of the signal-test span is absent from the portfolio test, and those are the thin years — 43 tradable names in 2013 against 230 in 2022. Every cross-mode number would be confounded by period. This is F16/F31 in new clothes, which F40 already fixed once *inside* the portfolio test. | strategist | Report **two windows**: the full span for the edge question, and the portfolio test's exact window as the only one used for any cross-mode comparison. No change to D15. |
| **Δ2** | **Cost drag would be understated 4–10×.** A signal-test trade is ₹1,00,000; a portfolio-test trade at ₹1L equity and 0.5% risk is ~₹10,000. The flat `dp_charge_inr: 15.34` is 0.015% of the first and ~0.15% of the second. Flattering direction, on exactly the question D2 exists to answer. | strategist | Not a reason to change the notional — ₹1L ≈ the *edge run's* typical position (0.005 × ₹10L ÷ a 5% stop = ₹1L). Report cost drag **twice**: at ₹1L, and restated at the portfolio test's median position size. |
| **Δ3** | **D15 never settled fills or tradability.** Does the signal test apply trade-through, the queue multiple, the participation cap, and `panel.tradable`? | strategist, test designer | **Settled by the invariants, not by preference — see §4 D-a.** |
| **Δ4** | **Signals are currently dropped silently in three places.** A signal on the last bar (`portfolio.py:302`, `if t < last`), a signal on an untradable session (`portfolio.py:552`, filtered inside a list comprehension before any counter), and a signal that is neither 0.0 nor 1.0 (`== 1.0`, so `0.5` and `nan` read as "no"). In a mode whose output is a *fraction of signals*, a silently shrinking denominator is the failure. | test designer, researcher | Every one becomes a **counted** skip reason. The conservation identity `signals == trades + skips` is a P0 test. |
| **Δ5** | **`summarise([], [])` does not raise — it returns `max_drawdown = 0.0`, `cagr = 0.0`, `exposure = 0.0`.** Real numbers, not `nan`; only Sharpe is `nan`. A signal result routed through the normal metrics path would print "max drawdown 0.0%", which reads as the best possible result rather than a missing one. | researcher, **verified directly** | The result type is **structurally separate**, with no field a drawdown could be silently zero in. Four independent locks — §5. |
| **Δ6** | **`RunResult.skipped` is `dict[Skipped, int]` — counts only.** There is no per-signal record of what was discarded, so "the signals we couldn't take were the good ones" is not computable and "good idea, wrong book" stays an inference rather than a number. | strategist | Add a **per-signal discard ledger** (symbol, decision bar, reason). Scope addition, and the thing that makes the whole exercise deliver a sentence instead of a hint. |
| **Δ7** | **There is no golden regression to protect the extraction.** `tests/golden/` is empty, yet the design moves money-path code. | architect, **verified directly** | **Step 0**: deterministic synthetic characterization before anything moves; compare exact outputs after extraction. A real-panel rerun is a counted trial, never an unlogged shortcut. The full golden backtest remains Step 5a. |
| **Δ8** | **A proposed transfer coefficient is undefined here.** It requires comparable constrained and unconstrained information-ratio series, while D15 forbids equity-curve metrics for the signal test. A ratio of trade-level returns is not that coefficient. | Astra review, 2026-09-24 | **Do not print `TC_observed` or its 0.3–0.8 band.** Compare matched-window signal attrition, costs, and returns by reason instead. Revisit only if a defensible common estimand is specified. |
| **Δ9** | **`Metrics.win_rate` is a naming trap.** `quantstats` and `ffn` ship a `win_rate` meaning *fraction of positive periods*; `vectorbt`, `backtrader` and `pyfolio` ship one meaning *fraction of positive trades*. Ours is per-trade. | prior-art | Rename to `win_rate_per_trade`. Costs nothing now. |
| **Δ10** | **Raw trade count can overstate independent evidence.** One hundred clustered trades may represent far fewer independent observations. | statistician | Report effective sample size and uncertainty in the signal diagnostic. Any new promotion or stagnation threshold is a separate dated gate amendment, not part of Task 3a. See §4 D-f. |
| **Δ11** | **Every result-inspecting evaluation consumes trial budget.** A historical count of 12 was observed while drafting; re-read the live ledger before reporting a count. Future signal and portfolio evaluations must not be silently exempted. | strategist, test designer; corrected by Astra review | Preserve the existing append-only trial rule. Record each capital-row result with its provenance; estimate effective correlated trials in the scheduled multiple-testing task before strategy registration. See §4 D-e. |

**Rejected after checking, so they are decisions rather than oversights:**

- **López de Prado's uniqueness weighting / sequential bootstrap.** Implemented and measured: 5–6%
  precision gain, **zero** coverage gain. It also solves a different problem (ML training-set
  construction, with no variance formula), changes the estimand to a weighted average nobody can
  interpret, and its naive use is actively wrong — in the worked example `N × uniqueness = 120`
  against a measured honest `N_eff` of **377**, over-penalising by 3×. Keep the concurrency series
  as a reported diagnostic (4 lines); skip the weighting.
- **The moving-block and stationary bootstraps.** Measured within **3%** of the closed-form
  block-clustered SE in every profile. Same answer, 100× slower, more machinery to defend.
- **Depending on `alphalens-reloaded`.** Last release and last commit both 2025-06-02; PR #46
  ("Adapt to pandas 3.0.x") open since 2026-04-20 with no maintainer response in 2026; pins
  `pandas<3.0`. Steal its report layout and its `t-stat`/`p-value` instinct; do not take the
  dependency.
- **IC / Rank IC as the primary metric.** Cross-sectional by construction — undefined for the
  Donlevey event-driven direction, and it has no notion of a trade or a holding period. Keep Rank
  IC as a secondary diagnostic for the `xs_*` strategies where it is well defined.
- **Fixed-window CAR as the verdict metric.** Our strategies have rules-based exits, so a fixed
  window measures a strategy nobody wrote — the F1 failure mode through a different door. CAR
  stays a diagnostic overlay.
- **Per-symbol market-model (α, β) regressions.** Brown & Warner (1985): for daily data the
  normal-return model barely matters, because a 1% abnormal return dwarfs any error in a ~0.1%/day
  expected return. Market-adjusted (`R_i − R_Nifty`) is sufficient and adds no second look-ahead
  surface.

---

## 4. Design decisions and remaining approval points

### D-a — fills and tradability *(required by existing invariants)*

**Apply the `FillModel` in full, and keep `panel.tradable` at entry.** This is determined by the
invariants rather than by preference: #12 says a resting LIMIT fills only if price trades strictly
through it and *"the sim may never assume a fill at the limit"*; #14 forbids survivorship, and
`panel.tradable` is the point-in-time universe mask. "Every signal taken" means *no signal refused
for want of a slot, cash or heat* — **not** "no signal refused by the market". The market refusing
you is a real property of the strategy and must stay in.

The selection worry this creates is answered by counting, not by removing: `entry_not_filled` is a
counted skip like every other, so it appears in the attrition table rather than shrinking the
denominator invisibly.

**Not doing:** making the signal test's *exits* consult `panel.tradable`. F47 is open, not decided;
making the new mode's exits check a mask the old mode's exits ignore would make the two modes
disagree about which trades exist — silently, in the direction of fewer losses. The asymmetry is
inherited **deliberately**, said out loud in the exit path's docstring, and pinned by a test.

### D-b — two windows *(recommendation)*

Report the full 2011–2022 span **and** the portfolio test's exact window. Only the second is ever
used for cross-mode comparison. Resolves Δ1 without reopening D15(e).

### D-c — two nulls, not zero *(recommendation)*

Scope addition, justified by §2. Both, because they answer different questions and reporting one
alone misleads in opposite directions:

- **Test A — mean alpha vs the benchmark over the identical holding window.** `alpha_i =
  net_return_i − (bench[exit] / bench[entry] − 1)`. This is #21 ("edge ≠ beta") made operational,
  and it is **also a free precision upgrade** — subtracting the common factor is exactly what was
  inflating the variance. In the worked example it raised effective N from **377 to 933**. Doing
  the honest thing and doing the compliant thing turn out to be the same operation.
- **Test B — a fixed-footprint symbol-selection diagnostic, not a full strategy placebo.** Hold
  observed entry dates and holding windows fixed and replace selected symbols with random names
  tradable on those dates. This tests whether *symbol choice* beat a conditional random comparison;
  it does not preserve the replacement symbols' own stop/target exits or establish that the full
  strategy would have traded them. State the exchangeability assumption, show the reference
  universe and permutation count, and suppress a p-value if the null cannot be defended. A full
  strategy placebo would require rerunning symbol-dependent exits and would change the footprint.

The earlier worked-example contrast between A and B is exploratory, not a validated verdict:
A measures market-adjusted trade returns, while B holds the observed footprint fixed to examine
symbol selection. Neither alone establishes a live edge. Keep the two estimands named and separate.

### D-d — block-clustered confidence intervals *(recommendation)*

Use a block-clustered estimator for trade-return and win-rate uncertainty, with the proposed
`L = max(63, 3 × longest_holding_bars)` as a pre-registered starting rule. Report block count,
effective sample size, method and assumptions. If the span yields too few independent blocks for
a defensible interval, report `INSUFFICIENT_EVIDENCE` instead of a confidence interval or p-value.
Validate coverage across long-hold, clustered, sparse and no-trade fixtures before quoting
uncertainty. Ordinary per-trade binomial intervals assume independence and are not suitable here.

`L`, the minimum usable block count, `ci_level`, `placebo_permutations` and the RNG seed are
result-affecting and must be pre-registered and dated with the notional before real-data evaluation.

### D-e — the trial ledger — **corrected 2026-09-24**

The existing rule counts every real-data evaluation, including hand-authored candidates,
calibration and same-strategy reruns. D15(d) explicitly counts signal tests. Therefore Step 0 may
be uncounted only when it uses synthetic fixtures, not when it reruns the real panel with
`ledger=None`. Record each inspected ₹10L and ₹1L capital-row result with its run/strategy/config
identity; do not silently merge or exempt them. The scheduled multiple-testing task estimates
how correlated evaluations contribute to *effective* trial count. Read the live ledger before
quoting its total. This applies the existing rule; it is not a new gate amendment.

### D-f — effective-N floor — **separate gate decision, not Task 3a**

Keep `objective.min_trades_oos: 100` unchanged during this diagnostic. Report raw trades,
independent blocks and effective sample size side by side. Replacing or supplementing the
promotion gate's raw-trade floor, or changing the stagnation test, requires its own statistical
contract and a dated append-only amendment with post-results acknowledgement. Do not infer an
approved numeric threshold from this plan.

### D-g — the per-signal discard ledger *(recommendation)*

Scope addition per Δ6. Record every refused signal and its reason. Skip records alone cannot
show what the refused trade would have earned. Any refused-set outcome requires a separate,
matched synthetic observation under stated fill and exit assumptions; report unmatched signals
and uncertainty. Even then, a difference is descriptive, not proof that the book constraint
caused it. The bridge may say “possible edge, wrong book,” not mechanically assert it.

---

## 5. Structure

```
                    simcore.py              (shared, mode-agnostic)
                   /          \
        portfolio.py          signaltest.py  (siblings; neither imports the other)
             |                      |
        metrics.py            signalmetrics.py
             \                      /
                    runner.py
```

Siblings do not import each other. A shared dependency both modes read is fine; a dependency from
the *diagnostic* mode onto the *gate* mode is not — a future change to the promotion path would
then silently change the diagnostic, and the entire value of running both is that a disagreement
between them is informative.

**New:** `icarus/engine/simcore.py` (~185 moved lines), `signaltest.py`, `signalmetrics.py`,
`scripts/run_signal_test.py`.
**Modified:** `portfolio.py` (deletions + imports + `__all__`, **no edited behavioural line**),
`runner.py`, `backtest.py`, `common/config.py`, `goal.yaml`.

### The four locks on the forbidden metrics

Absence must be structural, not a policy:

1. **A separate type.** `SignalTestResult` is not a `BacktestResult`, contains no `Metrics`, and
   shares no base class.
2. **`slots=True`.** No `__dict__`, so `result.sharpe` raises `AttributeError` and nothing can
   attach one later. (`BacktestResult` is a plain `@dataclass` today — `result.sharpe = 3.0` would
   work on it.)
3. **A module boundary.** `signalmetrics.py` does not import `icarus.engine.metrics`, enforced by
   an AST test.
4. **A type boundary at the gate.** `gate_verdict` is annotated `BacktestResult`; mypy refuses a
   signal result. Plus `NOT_A_GATE` stamped in the JSON and the sheet header, and a separate
   output file (`var/signal_test_results.json`, never merged into `var/backtest_results.json`).

### One extraction, one deliberate duplication

**Extract** the exit ladder (`_exit_intent`, `_trail_stop`, `ExitPlan`, `ExitReason`) to `simcore`.
The exit rules are the one thing that *must* be identical across modes for the comparison to mean
anything — if a fix lands in one ladder and not the other, the gap between the reports silently
becomes "portfolio construction plus whatever drifted". `ExitPlan`'s own docstring records this
failing once already: the simulator honoured one rule out of six and said nothing, and a strategy
declaring a 3R target was simulated as buy-and-hold.

**Duplicate** `_write_off`. Two-thirds of its body is book-specific bookkeeping (pops from the
book, builds a `ClosedTrade`, increments stale counters, returns realised P&L for the equity
accumulator). Sharing it would mean parameterising over four seams to reuse fifteen lines of
arithmetic. Share the genuinely hard pure part — `last_traded_close`, which returns the price *and
the bar index it came from* — and have the duplicate restate the doctrine in its own docstring.

---

## 6. Build order

Test-first throughout: write the acceptance test, watch it fail, implement, watch it pass.

| step | what | depends on |
|---|---|---|
| **0** | ✅ **DONE 2026-09-24, `b54f3cb`.** Synthetic six-session characterization pins entry, gap-stop exit, partial entry fill, end-of-data exit, refused/repeated entries, exact equity path and itemized costs. The current output and SHA-256 are frozen before extraction. No real panel, lockbox or trial ledger was used. A later real-panel evaluation is a counted trial. | — |
| **1** | ✅ **DONE 2026-09-24, `83ff601`.** Shared exit mechanics moved to `simcore.py` without a behavior change; existing `portfolio` exports preserved. Synthetic hash unchanged, 1,014 unit tests, Ruff and mypy passed; independent Astra review completed. | 0 |
| **2** | `signal_test:` config block + loader refusals | — |
| **3** | Lockbox span guards: `development_span`, `assert_span_before_lockbox` | — |
| **4** | `SignalTrade` + `SignalSkipped` | 1 |
| **5** | `SignalSimulator.run()` | 1, 4 |
| **6** | `signalmetrics.py` — block-clustered CI, both nulls, the report statistics | 4 |
| **7** | Trial-ledger `mode` marker | 6 |
| **8** | `run_signal_test()` | 1,2,3,5,6,7 |
| **9** | `scripts/run_signal_test.py` — the sheet, ASCII-only, and the per-trade CSV (pre-delivers 4b) | 8 |

**Waves:** A = {1, 2, 3} · B = {4} · C = {5, 6} · D = {7, 9-skeleton} · E = {8, finish 9}.
Step 1 is one agent, one commit, reviewed against Step 0's synthetic hash and existing tests.
It is the only step that moves a currently-passing money path. A synthetic snapshot is necessary
but not sufficient for confidence: preserve the full failure-path unit suite and independent
review. Do not claim the later golden backtest has been captured.

---

## 7. What to be paranoid about

1. **`decided_at` on the exit intent.** Every exit `Intent` carries `position.decided_at`, **not**
   `entry_ts` and **not** today's `ts`. Dating exits to `entry_ts` was the original bug: it made a
   stop unable to fill on the session the position opened, so a trade that gapped through its stop
   on day one could never be stopped out — always a loss, so suppressing it flattered every
   result. The single easiest thing for a sibling simulator to get wrong.
2. **The return denominator.** `deployed = shares × filled entry price`. Three wrong answers are
   each plausible: `notional_intent` (reintroduces the rounding distortion D15(b) dissolves, as a
   function of share price — a *fake cross-sectional effect*); `bar.open` (a few bps off the
   turnover the charges were computed on); requested rather than filled quantity (reports a return
   on capital never deployed). Assert `deployed == entry_charges.turnover`.
3. **Holding period from timestamps instead of bar indices.** `runner._sessions_held` records this
   exact bug producing an exposure of 1.48 — and warns that anything below ~1.45 would have looked
   plausible and been just as wrong. Worse here: a `STALE_MARK` exit is dated to the last bar the
   symbol printed, up to twenty sessions before it was noticed.
4. **Resampling trades instead of entry sessions in the bootstrap.** Fast, and it reintroduces
   exactly the pseudo-independence the whole design exists to remove. Guard: a test asserting the
   interval **widens** when the same trades are re-clustered onto fewer entry sessions.
5. **Fragmented exits.** The portfolio simulator emits one `ClosedTrade` *per exit fill*. Copying
   that breaks D15(a)'s one-signal-one-observation contract — the trade count inflates and the
   win-rate denominator skews, worst in the thin-liquidity names. Accumulate, emit one
   `SignalTrade`, set `exit_fills`.
6. **Nothing may survive the last bar.** F4's second half: an end-of-data exit the fill model
   refused left 700 of 2,500 shares invisible to the log, the win rate and the tax ledger.
7. **`mean_return_per_trade` is a mean of ratios** and cannot be compounded or annualised. The
   JSON carries `"cannot_be_annualised": true`. Expect it to be annualised anyway at least once.
8. **`notional_inr` at the top of the range.** At ₹1L a share dearer than ₹1L yields zero shares.
   MRF crossed ₹1L in 2023 — outside the development window, so this will not fire today and
   *will* the day someone runs it over live data. `PRICE_ABOVE_NOTIONAL` must exist and be
   counted, not left an unreachable branch.

---

## 8. The report layout

Ordered so a reader cannot reach a number before reaching the reason to doubt it.

- **§0 Provenance** — panel hash, span, session/symbol counts, strategy version, `goal.yaml` hash,
  and the banner: *SIGNAL TEST — NOT A PORTFOLIO RESULT. Net of cost, before tax. Diagnostic, never
  a gate.*
- **§1 Sample and attrition** — signals emitted; trades; **every skip reason with a count**;
  concurrency (mean/median/max open at once) and **effective N with the design effect**. The
  concurrency line is what tells the reader how much to discount §3.
- **§2 Signal shape** — signals per session, clustering in calendar time, holding-period
  distribution split winners/losers, ADV participation at the uniform notional.
- **§3 Edge — gross and net side by side (D2), never one column.** Mean alpha per trade with a
  block-clustered interval only when enough independent blocks exist; mean raw return beside the
  fixed-footprint symbol-selection diagnostic, with its assumptions and limits stated. Show a
  permutation p-value only when its null is defensible. Show win rate, median, expectancy in R,
  and cost drag at ₹1L and the portfolio's median position size. Never replace an unavailable
  interval with a misleading narrow one.
- **§4 Distribution** — return quantiles 5/25/50/75/95, holding-time histogram, the mean−median
  gap, drop-the-best-5-trades sensitivity, and the top/bottom 10 trades named individually so the
  reader can see whether the edge is three prints.
- **§5 Stability** — per-year mean alpha with bands.
- **§6 Bridge to the portfolio test** — compare only the identical time window, signal definition,
  observed attrition, costs and returns by discard reason. `TC_observed` is omitted because a
  comparable unconstrained information-ratio series does not exist. Distinguish supported `NO_EDGE`, `POSSIBLE_EDGE_WRONG_BOOK` and
  `INSUFFICIENT_EVIDENCE`; an interval containing zero is not proof of no edge.
  `NEEDS_MORE_CAPITAL` remains a portfolio-gate verdict, never a promotion verdict from this
  diagnostic.
- **§7 Trial ledger** — the entry that was written, and the lifetime count.

**Deliberately absent:** Sharpe, Sortino, Calmar, CAGR, volatility, max drawdown, exposure and a
transfer coefficient — they require a comparable equity-curve or information-ratio definition
that this signal diagnostic does not have. Also out: profit factor as a headline
(a ratio of sums dominated by the largest few trades, with no interpretable CI), per-symbol P&L
tables (693 symbols guarantees spurious winners), any naive t-statistic, and any compounded
"equity curve" of trade returns.
