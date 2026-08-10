# OPERATOR.md — how Sujay wants Icarus built

> **Read this at the start of every session, before `TASKS.md`.**
> `CLAUDE.md` says what the code must never do. **This file says how the operator wants to work.**
> Chat context is compacted and lost; this file is not. If a preference only exists in a
> conversation, it does not exist.
>
> **Owned by the operator.** The agent proposes additions; the operator confirms. Every entry is
> dated. Nothing is deleted — superseded entries are struck through and dated, so a preference
> that changed is visible as a change rather than a silent rewrite.
>
> 🚧 **DRAFT, 2026-08-09 — awaiting operator review.** Everything below is reconstructed from
> memory files and past conversation. **Correct anything that is wrong or missing.**

---

## 1. The working loop — non-negotiable

**Explain → approve → build → summarise.** In that order, every time.

1. **Before building anything**, explain in plain English what it is, why it is needed, and what it
   will change. No jargon; if a term is unavoidable, define it on the spot.
2. **Wait for approval.** Do not start because the plan seems obvious.
3. **Build it.**
4. **Afterwards, summarise what was actually done** — including anything that turned out different
   from the plan.

**Ask when unsure.** A question is cheaper than a wrong build. This is explicitly wanted, not
tolerated.

*(Restated by the operator 2026-08-09 after noticing it had been lost to context compaction.)*

## 2. Teaching style

- Ground-up. Assume no prior knowledge of the technique being used, and none of the jargon.
- Explain **why**, not just what. A number without its reasoning is not an explanation.
- Plain English in operator-facing output. Reserve precision for the code and its comments.

## 3. Honesty and reporting

- **Never overstate a result.** Losses, halts and refusals get the same prominence as gains
  (`CLAUDE.md` §8).
- **Turn shiny numbers into tests.** A good result is a hypothesis until something proves it.
- **Lead with the schedule cost, then the workaround.** Do not hide a delay inside good news.
- **Do not pre-emptively quit.** A demanding bar is accepted deliberately; the response to failing
  it is to change the input, never to lower the bar (invariant #25).
- **Write decisions into the repo.** A decision that lives only in chat will be lost.
- If earlier reported numbers are invalidated, **say so plainly and prominently**, and mark the
  superseded figures where they were written down.

## 4. Git

- **Commit every change.** Not at the end of a session — as work completes.
- `dev` for work. `main` only ever holds working code.
- **No session link in commit messages.** Co-author trailer is fine.
- Repo: `Sujayprodduturi/Icarus`.
- ⚠️ **Line endings:** the repo is mixed CRLF/LF with `core.autocrlf=false` and no `.gitattributes`.
  Writing files with Python's `write_text` silently converts CRLF→LF and produces enormous phantom
  diffs. **Use the Write/Edit tools, not Python file writes.** Verify with
  `git diff --ignore-cr-at-eol --quiet <file>` before committing.

## 5. Before committing code

Run both, in this order:
1. **`ponytail` / `simplify`** — strip over-engineering, unrequested abstractions, reinvented stdlib.
2. **`code-review`** — hunt for bugs.

*(2026-08-08: the code review caught that the portfolio simulator honoured one exit rule out of six,
which invalidated an entire published metric sheet. Run it **before** reporting results, not
alongside.)*

**And: a green test is not evidence.** For any test guarding a bug that was actually found,
reintroduce the bug and confirm the test fails. Two tests in this repo have passed while asserting
nothing.

## 6. Strategy direction

- **Matt Donlevey's mechanical SMC / liquidity method is the DNA** of Icarus strategies
  (`docs/strategy-research/donlevey-liquidity-smc.md`). Sweep the liquidity pool, trade the reaction.
- **Everything mechanical.** Exact thresholds, no discretion; the validation gate judges them.
- **Existing public strategies are fair game and preferred as a starting point** *(operator,
  2026-08-09)*. There is no requirement to invent from scratch. Backtest known, published,
  already-proven strategies first; then enhance the ones that survive in the direction of the
  Icarus thesis. Inventing is for after we have a working baseline that clears the bar.
- **Intraday data is approved** *(operator, 2026-08-09)* — the full Donlevey method is M5/M15 and
  the daily distillation is a lossy shadow of it.
- **LLM cost tracking is required** for anything the Inventor does.

## 7. What "backtest" means to the operator

*(Clarified 2026-08-09, after the first run measured something else.)*

> *"I wanted the strategy to take/exit a trade whenever it wants and holding how many positions as
> he can, but ultimately test the win ratio of the strategy."*

Two separate reports are wanted, never conflated:

1. **Signal test** — every signal taken, uniform notional, no book cap, no heat cap, no competition
   for slots. Answers *"does this idea have an edge?"* — win rate, expectancy, R distribution.
   Explicitly **not** a runnable portfolio and must never be quoted as one.
2. **Portfolio test** — the real book: position cap, heat cap, real capital, whole shares, real
   costs. Answers *"is it runnable?"* This is what the stop gate reads.

A strategy that passes (1) and fails (2) has a portfolio-construction problem. One that fails both
is dead. **The first run only produced (2)**, so the two cases were indistinguishable.

## 7b. Decision log — append-only

Dated decisions that are not code and not in `goal.yaml`, so they have nowhere else to live.
**Never edit an entry. Supersede it with a new one and strike the old.**

### 2026-08-10 — after the post-backtest audit (`docs/reviews/2026-08-09-post-backtest-audit.md`)

| # | decision | who |
|---|---|---|
| D1 | **Two backtest modes, always both.** Signal test (every signal, uniform notional, no caps) *and* portfolio test (real book). Never conflated. | operator |
| D2 | **Every report shows gross and net side by side.** Gross P&L, costs, tax, net — four columns, not one. Without this we cannot tell "no edge" from "edge eaten by costs". | operator |
| D3 | **Intraday survivorship: option (a).** Daily bhavcopy remains the sole authority on universe membership and entry eligibility; intraday bars refine *timing only*. A delisted name keeps its place in the universe and simply loses its intraday refinement. Invariant #14 stays intact — Kite cannot serve history for delisted instruments, so any Kite-derived universe would be survivors-only. | operator |
| D4 | **15-minute bars first**, not 1-minute. Matches Donlevey's M15 structural layer, ~15× cheaper to fetch and store. 1-minute stays open for later. | operator |
| D5 | **Long-only for now.** Bidirectional trading is revisited **after the current system is set up and working properly** — see §7c. | operator |
| D6 | **Fix the `momentum` ambiguity systemically, not locally** — see §7c. | agent, on operator instruction to "fix things once and for all" |
| D7 | **Two separately-pinned walk-forward splits** — daily (2011→2022) and intraday (2015→2022), each with its own pinned date and loader assertion. **`lockbox_start` stays 2023-01-01 for both, unmoved.** Rationale: `walk_forward_start` states what data *exists*; it is not a bar that could be lowered to flatter a result, and moving it to 2015 for the daily panel would discard four years of evidence (incl. the 2013 taper tantrum) for no gain. Two splits means nothing is discarded and the one gameable number never moves. **Accepted cost:** an intraday strategy gets ~5 OOS years vs ~9, so wider error bars and a harder gate — printed on the metric sheet, never left implicit. | operator |
| D8 | **Two capital rows on every portfolio test.** *Edge run* at **₹10,00,000** (rounding and flat fees negligible → you see the strategy) and *seed run* at **₹1,00,000** (what is actually tradable on day one). The gap between them *is* the measurement of BUILD_MAP's C1 seed-tier affordability problem, which has never been measured because it was baked into one blended number. Does not apply to the signal test, which has no book. | operator |
| D9 | **The stop gate reads the seed run.** A strategy passing the edge run and failing only the seed run is recorded **`NEEDS_MORE_CAPITAL`** — a third non-promoting verdict, structurally identical to the existing `NEEDS_MORE_DATA` tier. **No threshold moves and no money is released**; a `NEEDS_MORE_CAPITAL` strategy is treated exactly like `REJECTED` except that we revisit it at a larger tier. Flagged as gate-shaped and decided explicitly *after* results existed, per invariant #25. | operator, 2026-08-10 |

## 7c. Deferred by decision — not forgotten

Things consciously postponed. **Each names the condition that reopens it.** A deferral without a
trigger is an abandonment pretending otherwise.

### Bidirectional (short) trading — deferred 2026-08-10 (D5)

**Reopens when:** the long-only system is running end-to-end and has produced at least one strategy
that clears the pre-registered stop gate.

**What is already built and idle:** the DSL carries the complete bearish vocabulary — `bos_down`,
`choch_down`, `structure_bearish`, `sweep_and_reclaim_high`, `swept_high`, `liquidity_pool_high`,
`inducement_high`, `upthrust`, `failed_break_up`, and the `order_block_bear_*`, `ote_bear_*`,
`breaker_bear_*`, `mitigation_bear_*`, `rejection_bear_*` families. None of it is reachable:
`portfolio.py:_process_entries` always issues `OrderSide.BUY` and the strategy schema has no
`direction` key.

**What it will cost when we do it** (recorded now so it is not rediscovered as a surprise):
1. NSE **cash delivery cannot be shorted at all.** Shorts require intraday (MIS) or futures.
2. That changes the **cost segment** — `equity_intraday` or `equity_futures`, not `equity_delivery`.
3. It changes the **tax bucket** — speculative business (s.66) or non-speculative business, *not*
   capital gains. This is the expensive reading: 30% slab instead of 20% STCG.
4. It needs a **margin model**, which does not exist.
5. The Donlevey method is explicitly bidirectional (*"Mirror for shorts"*), so a long-only result
   is weak evidence about the method either way.

### The `momentum` fix — decided 2026-08-10 (D6)

The local fix is to rename one word. The **actual** bug class is: *a DSL word whose name does not
determine its units, used in a cross-sectional comparison.* Ranking rupee-denominated quantities
across symbols is nearly always wrong, and it fails silently — it looks like a working ranker.

**The systemic fix, in three parts:**
1. **Delete the ambiguous name.** No word called `momentum` survives. `roc` is the percentage
   change; `momentum_abs` is the rupee change, named so it cannot be picked by accident. No alias —
   an alias keeps the ambiguity alive in every strategy file already written.
2. **Add `scale_free: bool` to `Primitive`**, beside `intraday_only` / `requires_feed` /
   `intermittent` / `needs_panel`. The docstring already says those flags live there *"precisely so
   that adding a primitive cannot forget them"* — this is the same idea. 82 SERIES words, roughly
   32 of them price-denominated; a bounded one-time job.
3. **Make the cross-sectional words refuse a non-scale-free input.** `xs_top_n`, `xs_bottom_n`,
   `xs_rank`, `xs_zscore`, `xs_percentile`, `xs_sector_neutral` and the `rank_by` block raise at
   parse time rather than ranking rupees against rupees. Same shape as `ExitPlan.of` refusing an
   exit rule it cannot honour: **fail loudly at parse time, never compute something plausible.**

Consequence, accepted: this breaks every existing strategy file that says `momentum`. That is the
point — those files currently mean something other than what they say.

## 8. Pace and posture

- **Ship fast.** Prefer a working, honest, small thing today over a complete thing next month.
- Demanding bars are accepted **on purpose** — do not soften them to make progress look better.
- A slip in the schedule is information. Surface it, do not absorb it.
- Target dates (operator, 2026-08-01): code-complete **30 Sep 2026** · live-mode sim **Oct 2026** ·
  Phase-1 verdict + first real trade **Nov 2026**.

## 9. Infrastructure decisions already made

| decision | value | when |
|---|---|---|
| Local dev | Docker Desktop on Windows | Phase 0 |
| Deploy | Linux host + private GitHub, via Hermes | Phase 0 |
| Host | operator-supplied Linux/Ubuntu PC (supersedes AWS `t4g.small`) | 2026-08-02 |
| Crypto | deferred — equity-delivery first | 2026-08-02 |
| Broker | Zerodha Kite Connect, ₹500/mo, active | O1 |
| Equity delivery tax | capital gains (CA confirmation still open, O7) | 2026-07-31 |
| `objective.min_sharpe` | 1.0 (append-only amendment log in `goal.yaml`) | 2026-08-02 |

## 10. Open operator items

Tracked in full at the top of `TASKS.md`. Currently blocking:

- **O4 — host details.** 🔴 Blocks Phase 1. The one decisive question: **does the line have a static
  public IP, and is it behind CGNAT?** Indian residential broadband usually is, which makes a static
  IP impossible on that line at any price (invariant #6 requires orders to originate from a
  registered static IP). Also needed: CPU arch, Ubuntu version, RAM/disk, always-on with suspend
  disabled, shared or dedicated, UPS, remote access preference, timezone, disk encryption.
- **O5 — daily auth**: operator one-tap vs TOTP automation.
- **O7 — CA confirmation** on equity-delivery classification.
