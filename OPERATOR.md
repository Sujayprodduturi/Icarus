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

### Explanation style - confirmed 2026-09-30

The operator explicitly preferred the ground-up explanation connecting the signal simulator to the uncertainty calculation, and asked that future sessions use the same tone, language and granularity. This is a standing explanation preference.

- Start with the overall purpose and where the current work sits in the original roadmap. Connect it to what the operator already understands.
- Use plain conversational English, familiar words and concrete trading examples. Assume no statistical or software background; define a necessary technical term immediately.
- Explain what each part does and why it matters before describing implementation. Separate simulating trade outcomes from deciding how much evidence they provide.
- Show the sequence from input to outcome when useful. Use a short comparison table for built/tested/proposed/still-unbuilt parts, not a wall of internal task IDs.
- Distinguish working code, artificial-data checks, real-strategy evidence, independently reviewed proposals and accepted methods. Explain what a test failure invalidates and what it does not.
- Give numbers with their meaning and denominator. Explain shared market conditions, luck and uncertainty with examples before formulas, method names, seeds or commit hashes.
- Be patient, respectful and candid; neither oversimplify away limitations nor overwhelm with jargon. Give enough connected explanation for the operator to follow the reasoning once.
- End with the concrete next action and its purpose. Do not require reading a proposal or looking up references to understand the explanation. Scale length to the question; this preference changes clarity, not a requirement for long answers every time.

## 2b. Never reference a number without saying what it means

*(Operator instruction, 2026-08-11.)*

> "Assume that the references you give — the PRD, the invariants, #23 or something else — I may
> not know exactly what they are about. So clarify that before referencing them."

**A bare `#23` is not communication.** Before using any numbered reference in operator-facing
output, say in one clause what it *is*: "invariant #23 — halt on a slow bleed, not just a fast
loss" rather than "invariant #23".

**The reference prefixes, which exist because they collided:**

| prefix | means | lives in |
|---|---|---|
| `#1`…`#26` | a **safety invariant** | `CLAUDE.md` §0 |
| `F1`…`F23` | a **finding** from the post-backtest audit | `docs/reviews/2026-08-09-post-backtest-audit.md` |
| `D1`, `D2`… | a **decision** by the operator | `OPERATOR.md` §7b |
| `§7`, `§29.3` | a **PRD section** | `PRD.md` |
| `O1`…`O8` | an **operator setup item** | `TASKS.md`, top |
| `1.7c`, `2a` | a **task** | `TASKS.md` / the plan in the audit doc |

**Why this rule exists.** Findings were originally numbered `#1`–`#23`, the same shape as the
invariants. So `#23` meant *"halt on stagnation"* in one paragraph and *"annulled trades are in the
panel"* in the next, and the only way to tell was to already know. Renamed 2026-08-11. The prefixes
fix the ambiguity; **the rule above fixes the actual problem**, which is that the operator should
never have to look a reference up to follow a sentence.

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
  Python's `read_text` converts CRLF→LF on the way *in* (universal newlines), so even
  `write_bytes(text.encode())` rewrites the whole file. **Use the Write/Edit tools, not Python file
  writes.** If a script really is the right tool, it must read *and* write bytes and never touch
  `read_text`.
- ⚠️ **The check for it.** `git diff --ignore-cr-at-eol --quiet <file>` only catches a file whose
  *only* change is line endings; a file with both real edits and a mangled ending passes it. The
  check that actually works compares the two line counts:

  ```sh
  diff <(git diff --numstat) <(git diff --ignore-cr-at-eol --numstat)
  ```

  Any file where they disagree has had its endings rewritten. *(Added 2026-08-13 after task 2b
  turned a 120-line change into a 4,700-line diff across `dsl.py`, `trend.py`, `volume.py` and
  `TASKS.md` — caught before commit, but only by reading `--stat` and thinking it looked wrong.)*

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

**Mutation testing is not a substitute for these two, and I substituted it.** *(2026-08-17.)* Four
tasks — F40, F24, F34, 2g-2 — were committed with 3/3, 4/4, 5/5 and 4/4 mutations caught and
**neither review run**. That felt rigorous enough at the time, which is exactly the problem: they
measure different things. **Mutation testing proves the tests catch the bug I already thought of.
The reviews catch what I did not.** Run late on those four commits, they found a warning character
that would have crashed the whole metric sheet on a cp1252 console (F46), a counter reporting
candidates as trades, a cap documented as a standing bound that is only an entry bound (F45), a new
sweep missing the very vacuity guard the same change added elsewhere, and an 86-line test harness
copy-pasted into a fourth module. Not one of those is reachable by mutating code the tests already
cover. **Choosing my own check in place of the specified one is the same failure as narrowing a
task's scope unilaterally** — the decision was not mine to make.

**Run the mutation check *after* the commit, never before.** *(2026-08-16, task 2f.)* A harness
that restores each file with `git checkout --` will silently delete uncommitted work — it did,
losing hours of `runner.py` and `backtest.py`, recovered only because an earlier `git stash` had
left a dangling commit. Snapshot file contents in memory and write them back; commit first so a
mistake costs nothing. And check line endings **per file, every time**: a multi-line anchor written
with `\n` matches nothing in a CRLF file, and a harness that treats "anchor not found" as anything
other than a failure will report a mutation as caught when it was never applied.

*(Corrected 2026-08-20: this used to say "every file here is CRLF", and that is wrong — which made
it worse than saying nothing, because it invites exactly the assumption that fails silently. There
is no `.gitattributes` and `core.autocrlf` is `false`, so whatever a file was created with is what
it keeps. Today: `TASKS.md`, `README.md` and most of `icarus/` are CRLF; `OPERATOR.md`, `CLAUDE.md`,
`BUILD_MAP.md`, `docs/STATE.md` and the test modules `test_dsl_scale.py` / `test_dsl_library.py`
are LF; the audit file is **mixed**, line by line. The only reliable check is to make the edit and
then run* `diff <(git diff --numstat) <(git diff --ignore-cr-at-eol --numstat)` *— if a file appears
in that output, the edit changed line endings and the diff will be noise.)*

## 5b. Which skills to use, and which to leave alone

*(Operator-approved 2026-08-21, after an audit of the ~90 skills available. The point is not to use
skills because they exist — most of them have nothing to do with this project — but to stop
re-deriving by hand the things a skill already encodes.)*

**Standing, before every code commit** — unchanged from §5 above, restated here so the list is in
one place: `ponytail-review` (or `simplify`), then `code-review`. `security-review` as well on
money-path or safety-critical code. Documentation-only changes are exempt; say so explicitly.

**Adopted, with the reason each one earns its place:**

| skill | when | why this one |
|---|---|---|
| `superpowers:test-driven-development` | any feature or bugfix, **before** writing implementation | The strongest of the set for us. Task 2g-3 was written code-first, and the code review then found the guard could be walked around by wrapping the refused word in `zscore`. Enumerating what must be *refused* before building the refuser is exactly the discipline that finds that. |
| `superpowers:verification-before-completion` | before claiming anything is done, fixed, or passing | Aimed at this project's worst failure: the 2026-08-07 metric sheet was reported, believed, and later voided. Evidence before assertion. |
| `superpowers:brainstorming` | before design work, not before mechanical work | Where the design *is* the deliverable — 3a's signal-test mode, 6a's eight strategies. |
| `superpowers:systematic-debugging` | any wrong number or failing test, before proposing a fix | Our recurring shape is "the wrong version runs perfectly", which rewards finding the cause over guessing at it. |
| `superpowers:receiving-code-review` | on every review finding | Verify the finding against the code before implementing it. All five findings on 2g-3 were verified true — but the one that mattered would have been easy to wave through, and one review finding in this repo's history was wrong about which words were affected. |
| `superpowers:writing-plans` / `executing-plans` | multi-step work with checkpoints | Step 3 and Step 4 of the repair plan. |
| `superpowers:subagent-driven-development` / `dispatching-parallel-agents` | independent work that genuinely parallelises | **Enabled by the operator 2026-08-21**, reversing the earlier standing instruction not to use agents. The test is whether the tasks are actually independent — research alongside implementation, several files audited at once. Not for work with shared state or a sequential dependency. |
| `llm-council` | a real decision with stakes and more than one defensible answer | Precedent: `docs/reviews/council-2026-07-31-prd-phases-0-1-2.md`. Finding F45 (the concentration cap) and the Vibe-Trading build/adopt/hybrid call were both of this kind. |
| `claude-api` | **mandatory** before writing or debugging any LLM-touching code | Phase 3's Strategy-Inventor and the news/sentiment agents. Its own trigger says read it before opening the file, not after. |
| `dataviz` / `artifact-design` | Step 4, the metric sheet | A sheet the operator can actually read beats a JSON dump. Not before Step 4. |
| `update-config`, `schedule` | harness and routine changes | Already used for the monthly Vibe-Trading watch. |

**Standing, from 2026-08-22 — parallel agents in distinct roles are the default, not the last
resort.** Operator instruction, strengthening the 2026-08-21 enablement in the table above: *"use
sub-agents and skills as and when required and as frequently as possible. Addressing each issue
with multiple angles solves it in a better way and parallelising work improves productivity. A
developer, tester, reviewer, strategist, researcher, designer, etc."* Two things follow.

- **The angles are the point, not the throughput.** Several agents reading the *same* code under
  *different* mandates is not duplicated work — it is the multi-angle coverage the operator is
  asking for. A researcher mapping integration seams and an architect proposing a layout will read
  the same files and return genuinely different things.
- **The bar for dispatching is not "is this too big for me" but "are these angles independent".**
  If they are, they run at the same time. Sequential dependency or shared file state remains the
  reason not to; nothing else is, and "I could just do it myself" is not a reason.

*Precedent:* task 3a's design opened with **four concurrent agents** — integration-seam researcher,
statistician on the cross-sectional confidence-interval problem, prior-art researcher on how
event-study and factor-analysis libraries already solve this, and test designer — before a line of
implementation was written.

**Deliberately not used, and why — so this is a decision rather than an oversight:**

- **`superpowers:using-git-worktrees`** — this session works in place, and §4's git rule is `dev`
  plus commit every change. A worktree adds isolation we do not want here.
- **`superpowers:using-superpowers`** instructs invoking a skill before *any* response, including
  clarifying questions. That contradicts §1, which wants questions asked early and cheaply.
  **§1 wins.**
- **The `obsidian-second-brain` suite** (~40 skills) — there is no vault. **`impeccable`, `design`,
  `design-flow`** — Icarus has no user interface. **Semrush, Canva, Gamma, Lovable, Prospecting,
  `last30days`, `x-pulse`, `research`, `claude-in-chrome`, `init`** — marketing, vault or
  web-research tooling with no bearing on a trading engine.

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

### 2026-08-17 — F40, before Step 3

| # | decision | who |
|---|---|---|
| D10 | **Drop the per-strategy purge; one fixed `seam_sessions` for every strategy** (finding F40). Purging protects a *fitted* model from label overlap; nothing here is fitted per fold and no state crosses train→test, so it protected nothing — while its per-strategy width made the control and the strategy run over different periods, which invariant #21 cannot tolerate. **Value unchanged at 5**; structure only. The textbook embargo stays unbuilt, and `goal.yaml` marks it mandatory before any per-fold fitting in Phase 2. Full reasoning in §7c. | operator, on the agent's researched recommendation |

### 2026-08-17 — F34, before 3b

| # | decision | who |
|---|---|---|
| D11 | **`max_position_pct_of_equity: 0.25`** — no single name may exceed a quarter of the account by value (finding F34). Risk sizing bounds the loss *if the stop holds*; this bounds what is exposed when it does not, which overnight it often does not. Operator proposed 0.50; the gap arithmetic argued it down — at 0.50 a 20% lower circuit is a 10% account loss, which is `max_drawdown_killswitch` itself. It **reduces** the position rather than refusing it, unlike the cash gate. Code refuses any value above 0.50 whatever the config says. | operator, on the agent's recommendation after the arithmetic |

### 2026-08-20 — F45 and F23, before 3b

| # | decision | who |
|---|---|---|
| D12 | **The concentration cap gets a standing ceiling and a mark-to-market denominator** (finding F45). Two separate faults, one decision. **(a) Entry bound stays `0.25`; add `max_position_pct_standing: 0.40`.** When a position's mark-to-market weight crosses 0.40 it is trimmed back to 0.25 — not to 0.40, because sitting on the trigger re-fires on every subsequent up-day and pays costs and tax each time; trimming to the entry bound gives hysteresis. The band is deliberate slack: a winner runs 60% past the entry bound before anything touches it, because cross-sectional momentum earns in the right tail and trimming at 0.25 would sell every winner the moment it won. 0.40 comes from D11's own arithmetic, not from taste — a 20% lower circuit at weight *w* costs the account `0.20 × w`, so 0.50 *is* `max_drawdown_killswitch` (which is why code already refuses above it) and 0.40 is 8%, leaving headroom for the rest of the book, which is rarely flat on a day one name limits down. **(b) Measure the cap against mark-to-market equity, not the realised book.** Today `equity` is cash plus *cost basis*, so a book down 20% unrealised still permits the same rupee concentration — the cap loosens exactly when the account can least absorb a loss, the same optimistic-direction failure as every other finding in this audit. **Accepted costs, both named rather than discovered later:** every trim pays exit charges and crystallises a capital gain, usually short-term, and that drag must run through `CostModel`/`TaxModel` like any other exit so it lands in the net column instead of vanishing; and a mark-to-market denominator *tightens* the cap during a drawdown, which will refuse entries a mean-reversion strategy wants — the correct direction for a bound whose job is survival. Both numbers live in `goal.yaml`; code refuses a standing ceiling above 0.50 exactly as it already does the entry bound. **Implemented at 3b, not before.** | agent's recommendation, operator delegated and pre-approved 2026-08-20 |
| ~~D13~~ | ~~**F23 (annulled prints) ships as a bounded known-events list, not a complete one.**~~ **SUPERSEDED 2026-08-21 by D14 — taken on a false premise.** The decision rested on "NSE annulled those trades", which the agent asserted from finding F23 without sourcing it. NSE **denied** the annulment. Struck rather than deleted, per this log's own rule: a decision that was made deserves to stay visible, including the reason it did not survive | operator, 2026-08-20 |

### 2026-08-21 — F23 reopened and closed

| # | decision | who |
|---|---|---|
| D14 | **F23 is closed as not-a-defect, and D13 is superseded.** The 2012-10-05 flash-crash prints stay in the panel. **NSE never annulled those trades** — Emkay applied, the Relevant Authority **denied** it, Emkay bore ~₹51 crore (more than its own market capitalisation), SAT **remanded** in September 2014 rather than annulling, and the matter ended in 2015 as a private settlement between Emkay and two counterparty brokers: compensation between members, not an exchange annulment. The buyers who filled at those lows kept their gains, which is exactly why the application was refused. **So the prints are legally valid trades and a stop filling against that low models what really happened.** Blanking them would repeat the biased deletion of the tail that the ATR bad-tick detector already attempted and that was reverted for it. There is also nothing else to list: India had **no annulment framework at all** before July 2015 — SEBI created one *because of* this case and made it near-impossible to invoke (30-minute window, 5%-of-value fee) — and no NSE cash-segment annulment is documented anywhere in 2011-2022. **Delivered instead of the registry:** the false claim corrected in `icarus/engine/panelbuild.py`, the audit, `docs/STATE.md` and `TASKS.md`, each with its source and as-of date. **Verification limit, stated rather than glossed:** primary documents (the SAT order text, SEBI's 2015 circular) were not retrieved — 403s — so this rests on consistent secondary reporting from four outlets plus Emkay's own quoted regulatory filing. **The lesson, which cost a scheduled task:** an external fact that schedules work has to be sourced *before* it is scheduled, not after. F23 sat in the plan for eleven days and the operator approved a scope for it, all on a sentence nobody had checked. | operator, on the agent's researched correction |

### 2026-08-22 — task 3a, the signal test, before any code

| # | decision | who |
|---|---|---|
| D15 | **The signal test's five open design questions, all settled before a line was written.** D1 mandated two backtest modes; this is the mode that never got built, and every question below changes the number it produces, so each is fixed and dated *now* rather than discovered during implementation. **(a) One open position per symbol at a time**, re-entry allowed once flat; a repeat entry signal while that symbol is open is **skipped and counted**, not silently dropped. The reason is sample independence, not slot scarcity — a different and better justification than the portfolio test's identical-looking rule. Measured, not assumed: `strategies/baseline_buy_and_hold.yaml` has entry condition `close > 0`, true on **every** tradable bar, so unrestricted overlap would open **318,332** positions across 693 symbols for a strategy that means at most 693. Any trend-follower fires repeatedly during the trend it caught; taking all of them counts one market event as forty independent observations, and every confidence interval computed from that sample is then a lie about how much evidence we hold. **(b) Uniform ₹1,00,000 notional, whole shares, and per-trade return computed on DEPLOYED capital (shares × entry price), not on the ₹1,00,000 intent.** The agent recommended ₹10,00,000 on a measured share-rounding table — at ₹1L, 5.34% of tradable symbol-days cannot deploy more than 98% of the intent and the worst case is 50%, against 0.42% and 9% at ₹10L. The operator chose ₹1L and was right: that objection **dissolves under the deployed-capital denominator**, which makes share-rounding exactly zero distortion to a percentage return, while ₹1L is strictly better on market impact (the participation cap barely binds at ₹10L and never at ₹1L) and matches D8's seed run. Fixed and dated **before** the run per invariant #25 — the pre-registered gate is not renegotiated after results are seen — because a notional that moves the answer is a threshold in everything but name. **(c) Costs applied; capital-gains tax NOT applied; the output labelled "net of cost, before tax" in the file itself.** Indian capital-gains tax is computed per financial year on the aggregate account, netting gains against losses; a signal test has no account and no year end, so there is nothing coherent to net, and a per-trade approximation would be a fabricated number. Invariant #21 — edge is alpha after cost **and** tax — governs the promotion gate, which is the portfolio test. **The signal test is a diagnostic and never a gate**, and that has to be stamped on the artefact, because otherwise the number gets quoted against a bar it was never measured against. **(d) Recorded in the trial ledger with `mode: "signal"` and null Sharpe fields.** Invariant #24 — every evaluation counts, human-originated included — applies: a signal test is a look at the data that influences which strategies we keep, and that is a search. **Sub-decision, taken explicitly because it makes our own bar harder to clear:** signal-test runs **do** inflate the trial count that the deflated-Sharpe correction uses, since they influenced selection and that is precisely what the correction exists to penalise; they are excluded only from the list of candidates carrying a comparable Sharpe. **(e) Single pass over the development window 2011-01-01..2022-12-31; the lockbox is not touched.** A signal test **fits nothing** — it takes every signal as written — so there is no parameter to leak and no need for out-of-sample separation inside it; and invariant #26 consumes the lockbox exactly once, for the final go/no-go, so spending it on a diagnostic would burn it for nothing. **Structural, not negotiable:** built as a **sibling simulator class**, never a config flag on the portfolio simulator, whose caps physically refuse to be disabled (`_MAX_POSITION_PCT_CEILING = 0.50`, the `_Fraction` bounds) and must stay that way. **Named consequence, so nobody reports it as a defect later:** Sharpe, CAGR, drawdown, Calmar, Sortino, volatility and exposure are **absent** from a signal-test result. Every one of them derives from an equity curve, and there is no equity curve without a book. What the mode returns instead is trade-level: win rate, mean and median return per trade with an honest uncertainty band, the return distribution, holding period, and cost drag. | operator, on the agent's five questions; (b) decided against the agent's recommendation |

### 2026-09-24 — task 3a correction and learning scope

| # | decision | who |
|---|---|---|
| D16 | **Proceed with the Task-3a plan only after the Astra corrections.** An uncounted characterization uses synthetic fixtures; every real-data rerun remains a trial. Do not report the proposed transfer coefficient without comparable information-ratio series. A fixed-footprint random-symbol comparison is a symbol-selection diagnostic, not a full strategy placebo. Clustered uncertainty must refuse to claim an interval or p-value when independent blocks or a defensible null are missing. Report effective sample size in Task 3a, but do not silently change the promotion or stagnation gate. The signal mode remains non-promoting and never touches the lockbox. | operator, approving the Astra corrections |
| D17 | **Learning scope includes both strategy entry/exit timing and order-execution timing.** Track the full chain of signal, risk decision, order, fills, close, costs and outcome from multiple angles so Icarus can diagnose and propose improvements. These are different hypotheses and must be evaluated separately. The existing research isolation, trial accounting, numeric validation, registry promotion, hard risk limits and Phase-1 no-live-order rule remain in force; this decision does not authorize autonomous live self-editing before the scheduled phases. | operator, clarifying “timings” and approving the plan |
| D18 | **Task 3a statistical settings are provisional diagnostics, not gate amendments.** For the unrun signal test, use 95% nominal confidence, block length `max(63 sessions, 3 × longest holding period)`, 4,999 symbol-selection permutations and fixed RNG seed `20260924`, with separate 2026-09-24 provenance. Do not pick a minimum usable-block threshold by guesswork: Step 6 must calibrate it on synthetic fixtures and pre-register it before any real-data inferential output. Until then `inference_enabled` stays false. A fixed seed and permutation count do not by themselves validate the placebo null; suppress p-values where it is indefensible. | operator, accepting Astra's recommendation to do what is best |

### 2026-09-25 — task 3a lockbox and comparison contract

| id | decision | owner |
|---|---|---|
| D19 | **Reject any signal-test source panel containing a lockbox date before evaluating a strategy; never quietly clip away the lockbox and continue.** The development view may then select the configured development dates from that already-safe source. For portfolio comparisons, run separate signal simulations over each portfolio fold's exact dates and reset boundary; filtering one continuous development run after the fact is not a matched comparison. Every inspected real-data full-span or fold-matched evaluation, including a rerun, is a separately recorded trial. No real-data run is authorised by this decision; complete the diagnostic and ledger guards first. | operator, approving the two Astra recommendations |
| D20 | **Build Task 3a Step 5 as a synthetic-only signal simulator with explicit missingness provenance.** The caller must label expected warm-up/missing-input NaNs; unlabelled NaNs and invalid signal values fail closed. Daily bars do not define a benchmark price at an intraday stock exit, so benchmark return and pre-tax alpha stay unavailable until a separate sampling rule is reviewed. Reuse fill and exit mechanics; preserve the Phase-1 no-live-order, no-real-evaluation and no-promotion boundaries. | operator, choosing both Step-5 contracts and approving the bounded design on 2026-09-25 |

### 2026-09-26 — time-resolved benchmark direction

| id | decision | owner |
|---|---|---|
| D21 | **Make benchmark-relative signal performance available through a time-resolved stock-and-Nifty route, not a daily-price approximation.** Entry, exit, and execution timing matter both for strategy judgement and future recursive improvement. D20's existing daily-bar refusal remains correct until a separately reviewed and proven sampling rule is built; D21 reopens the work rather than fabricating an alpha now. D3 (daily point-in-time universe authority), D4 (M15 first), D7 (separate 2011–2022 daily and 2015–2022 intraday splits), and Task 3a Step 6's precedence remain unchanged. The hosted Kite MCP is a separate authenticated operator-side connection for interactive inspection, not an Icarus runtime dependency or approved acquisition path; its exposed mutation capabilities must be treated as potentially write-capable until verified, and no mutation tools are to be used. The source-neutral design is `docs/plans/2026-09-26-time-resolved-benchmark-design.md` and requires its own written review before code. | operator, approving the recommended long-run route on 2026-09-26 |
| D22 | **Approve the written time-resolved benchmark design for Step 6 planning.** This approval does not authorise product code, real-data evaluation, a historical-data subscription, or broker integration. The existing daily and M15 windows, missing-refinement refusals, and lockbox/trial gates remain in force. | operator, 2026-09-26 |
| D23 | **For the current Task 3a Step 6 continuation, do not stop for routine document-stage approvals.** Keep planning, building and reviewing within the already approved safety boundary; consult GPT-6 Astra before any major architectural decision, and stop at major milestones or when operator input is genuinely necessary. This is a scoped process authorization, not permission for real-data evaluation, broker integration, live orders, a paid subscription, or a safety-invariant change. Plain-English pre-build explanation and post-build summary still apply. | operator, 2026-09-26 |

### 2026-09-27 — intended host and unresolved setup

| id | decision | owner |
|---|---|---|
| D24 | **Use the current PC as the intended Icarus host.** The operator said "We can have it this pc." Hardware selection does not certify deployment readiness or authorize an OS migration. The current machine is Windows 11; the Linux deployment arrangement, static public IP/CGNAT, continuous uptime and UPS remain to be verified. The operator requested an authentication recommendation and confirmed the CA has not yet been consulted; neither authentication policy nor tax classification was newly approved. Recommendations and evidence are in `docs/plans/2026-09-27-orchestration-roadmap.md`. | operator, 2026-09-27 |

### 2026-09-27 — continuation authorization and host follow-up

| id | decision | owner |
|---|---|---|
| D25 | **Continue planning, implementation, scouting and independent review with task-appropriate models and effort.** The operator confirmed continuous PC/router power with UPS backup can be arranged, but does not know the ISP. This records feasibility, not installed UPS or static-IP readiness. Existing safety boundaries, exact-runner review before frozen synthetic draws, and separate approval for real-data/broker/live work remain unchanged. | operator, 2026-09-27 |

### 2026-09-27 — milestone cadence, medium effort and GitHub sync

| id | decision | owner |
|---|---|---|
| D26 | **Continue autonomously within the approved scope and stop only at major milestones or genuine blockers. Use medium effort for delegated models and reviews, never high effort. Push committed changes to the Icarus GitHub repository.** This changes cadence and model settings, not frozen-stream, real-data, broker or live-trading authorization. | operator, 2026-09-27 |

### 2026-09-27 — plain-language milestone summaries

| id | decision | owner |
|---|---|---|
| D27 | **Use the wait-what style in every milestone summary.** Start with where the work sits in the original roadmap and why it matters. Explain what changed in plain language, what verification establishes and what it does not, and what comes next. Define necessary terms; avoid leading with internal slice names, commit IDs or test counts. Distinguish nested calibration task numbers from the main signal-test steps. | operator, 2026-09-27 |

### 2026-09-28 — usage awareness

| id | decision | owner |
|---|---|---|
| D28 | **Continue the next steps while being mindful of usage limits.** No explicit token budget, reset-credit redemption or reduction in review/safety requirements was requested. D26's medium-effort requirement remains in force. | operator, 2026-09-28 |

### 2026-09-28 — same-process completion authority

| id | decision | owner |
|---|---|---|
| D29 | **Approve the stricter same-process completion approach.** Persisted seal bytes are inert candidate evidence; completion authority is issued privately only after file/directory sync, single-close and final resource/deadline checks succeed under the original two-hour limit. Validation requires that live authority plus fresh complete evidence verification and a passing calibration result. Process loss prevents automatic continuation for that attempt, even with intact files; there is no restart recovery, resume or redraw. This approves implementing the reviewed completion-authority proposal and its exact contract, not an official experiment, attestation, statistical threshold change or live trading. | operator, replying "Go ahead" to the explicit recommendation on 2026-09-28 |

### 2026-09-30 — simulator and tests on the current PC

| id | decision | owner |
|---|---|---|
| D30 | **No separate Linux system is available; run the simulator and other supported tests on the current system, and check the handover/state documents properly.** This confirms D24's current-PC choice and authorizes the existing Windows-compatible synthetic simulator/test lane. It does not request an OS migration, approve consuming a reserved stream, or waive the counted runner's reviewed platform/resource/durability contract. Current documentation must distinguish completed local tests from the separate official-calibration restriction. | operator, direct instruction on 2026-09-30 |

### 2026-09-30 - statistical-method continuation

| id | decision | owner |
|---|---|---|
| D31 | **Continue the statistical-method design and independent review after the non-reserved failure diagnosis.** The operator replied "Okay, go ahead" after the milestone proposing a better interval-method design and preserving thresholds. This authorizes the current design/development investigation; the newly written concrete research candidate still follows section 1's review-before-build loop. No official method/protocol amendment, reserved stream, real-data evaluation, inference enablement or live path is authorized. | operator, direct reply on 2026-09-30 |

### 2026-09-30 - build uncertainty mathematics and explanation preference

| id | decision | owner |
|---|---|---|
| D32 | **Build the uncertainty mathematics and record the plain-English explanation style for future sessions.** After the complete-picture explanation, the operator explicitly asked to proceed with building. This authorizes the concrete isolated research candidate/comparison and supported Windows screen in the reviewed design; section 2 records the requested tone, language and granularity. No accepted product method, frozen protocol amendment, reserved draw, real-data strategy test, inference enablement or live path is approved. | operator, direct instruction on 2026-09-30 |

### 2026-09-30 - bounded uncertainty research build

| id | decision | owner |
|---|---|---|
| D33 | **Build the reviewed bounded independent-group research component and its deterministic tests.** The operator said Yes do it after the concrete proposal explaining justified independence/support, conservative intervals and insufficient-evidence refusals. This authorizes its pure research helper, deterministic verification and reviews; no stochastic screen, product adoption, new data floor, reserved stream, real-data evaluation or live path. | operator, direct reply on2026-09-30 |

### 2026-10-01 - dependence-aware uncertainty research build

| id | decision | owner |
|---|---|---|
| D34 | **Build the reviewed dependence-aware bounded uncertainty extension and deterministic tests.** The operator explicitly said The proposal is approved after the plain-English explanation and independent review of the fixed jointly-independent-class contract. This covers its isolated research implementation, deterministic proof/refusal checks and reviews; no stochastic screen, real-data evaluation, accepted product floor, reserved stream, inference enablement or live path. | operator, direct reply on2026-10-01 |
| D35 | **Review the persistent-dependence proposal with a capable sub-agent and proceed with its justified recommendations.** This approves the isolated pure artificial-model calculator, deterministic tests and independent checks described in the 2026-10-01 proposal. No stochastic screen, real-data evaluation, product adoption, accepted floor, reserved stream, inference enablement or live path. | operator, direct instruction on2026-10-01 |
| D36 | **Implement the reviewed extreme-return moment proposal.** The operator explicitly said Yes implement after the plain-English explanation and independent mathematical/governance reviews. This approves the isolated pure independent-whole-group original-mean second-moment calculator, deterministic tests and reviews. No dependence composition, stochastic screen, real-data evaluation, product adoption, accepted floor, reserved stream, inference enablement or live path. | operator, direct reply on2026-10-01 |

| D37 | **Implement the reviewed combined persistent-market and extreme-return uncertainty proposal.** The operator explicitly said Implement after the plain-English explanation and two independent final design reviews. This approves the isolated class-free Gaussian-factor whole-group moment calculator, narrow shared validation/finishing helpers, deterministic tests and independent reviews. Original all-trade raw/paired-excess mean and conservative arithmetic remain required. No stochastic screen, real-data evaluation, product adoption, accepted floor, reserved stream, inference enablement, lockbox or live path. | operator, direct reply on2026-10-01 |

### 2026-10-01 - milestone cadence reaffirmed

| # | Decision | Decided by |
|---|---|---|
| D38 | **Continue the next tasks and stop to explain only at major milestones, using the established simple, plain-English format.** Reaffirms D23/D26/D27 and section2. Routine preparation/review proceeds within approved scope; this does not authorize real-data runs, method adoption, reserved draws, task-dependency or threshold changes, broker integration or live orders. | operator, direct instruction on2026-10-01 |

### 2026-10-01 - practical uncertainty design direction approved

| # | Decision | Decided by |
|---|---|---|
| D39 | **Approve the recommended practical-method design direction:** prepare a separately preregistered diagnostic uncertainty method with explicit market assumptions, difficult artificial-condition validation and weak-evidence refusals. Approval follows the real-data evidence-policy milestone explanation and covers design/review; no estimator implementation, experiment, adoption, real-data evaluation, reserved draw, accepted floor, task-order change, threshold change, lockbox or live/broker path. Portfolio promotion requirements remain unchanged. | operator, direct Approved reply on2026-10-01 |

### 2026-10-01 - calendar uncertainty implementation approved

| # | Decision | Decided by |
|---|---|---|
| D40 | **Implement the reviewed calendar ratio subsampling calculator and deterministic tests on invented records.** Approval follows the concrete design milestone. Covers isolated research arithmetic, typed refusals, reviews and current-PC verification. No sampled stress/confirmation experiment, product adoption, accepted floor, real-data evaluation, reserved stream, inference enablement, lockbox, task-order or threshold change, broker/live path. | operator, direct yes implement reply on2026-10-01 |

| D41 | **Review and implement the artificial-calendar runner with sub-agents; continue authorized artificial-data checks and research after exact-source, resource and phase gates pass. Stop before running the simulator on real market data.** The operator explicitly asks for the best reviewed solution and no routine implementation stop. This does not authorize broker/live paths, official reserved streams, product adoption, changed statistical thresholds or real-market evaluation. | operator, direct instruction on2026-10-02 |

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

**Built 2026-08-12 (task 2a). What actually shipped, against the plan above:**

- All three parts done as written. Also added `roc_skip(n, skip)` (finding F22 — 12-1 momentum was
  inexpressible) and `requires_lt`, so a parameter *pair* that is individually legal and jointly
  meaningless is refused at parse time rather than returning `nan`.
- The counts in point 2 were estimates; the real numbers are **93 words that had to declare** and
  **131 derived** — an `EVENT` is a yes/no and always comparable, a `LEVEL` is a price and never is,
  so restating that 131 times would have been ceremony and 131 chances to paste the wrong value.
  Of the 93, **29 came out not-comparable.**
- All three strategy files are at **v2** and each carries a paragraph saying what changed, why it is
  a bug fix rather than a post-hoc re-tune (invariant #25), and that **v1's numbers are void rather
  than superseded**.

**The standard of proof, worth reusing: the split test.** A share split changes a symbol's price and
share count and nothing else about the company — so it is exactly the transform that separates the
two classes. Every word claiming to be comparable must come out **unchanged** under it; every word
denying it must **move**. That second direction matters as much as the first: a flag set to `False`
"to be safe" silently removes a word from every ranking, and this is what catches it. The sweep
covers all 76 declared words that can be computed from one symbol's bars, and **14 of 14 deliberate
re-introductions of the bug were caught**. Nothing weaker would have worked here — a unit test of
`momentum` passed, and a unit test of `xs_top_n` passed; the defect lived in the join.

**The code review then found three more of the same shape, all fixed before commit** — worth
recording because two of them were introduced *by this task's own fix*:

- `xs_rank` counted upward from the best (1 = highest) while the simulator fills the book from the
  largest value down, so ranking by it bought the **weakest** candidates. Refused at parse time.
  `rank_by` turns out to be the only position a cross-sectional word can occupy, so this retires
  `xs_rank` (finding F26) — accepted deliberately, because a word that reliably picks the losers is
  worse than a word nobody can reach, and `xs_percentile` does the job correctly.
- A mis-declared `requires_lt` pair raised a bare `KeyError` out of the parser, potentially at the
  first live parse. Now a construction-time refusal like every other `Primitive` check.
- **The rewritten baseline header claimed a ranking the engine does not perform.** `roc(252)` is
  `nan` across the whole one-year test window because the warm-up is computed from `entry` only
  (finding F3), so the control still selects **alphabetically** in every out-of-sample fold. The
  file now says so in full. This is the danger of correcting a file: the fix was right and the
  sentence describing it was not, and only re-reading the diff against the engine caught it.

### The `longest_lookback` fix — built 2026-08-13 (task 2b, findings F3 and F28)

Approved as: widen the scope from `entry` alone to `entry` + `rank_by` + `exit`, and let a word
declare that its history requirement cannot be bounded so a strategy using it is refused. Both
shipped. Two things came out differently and are worth keeping:

- **`psar` is not what I twice said it was.** I first marked it "no finite lead-in works"; the test
  disproved that. I then called it "settles after ~500 sessions"; the test disproved that too. What
  it actually does is **oscillate** — matching full history at 300 sessions of lead-in, missing at
  700, matching again at 900 — because its acceleration factor resets at whichever trend reversal
  falls first in the slice. The flag was renamed from `unbounded_lookback` to `opaque_lookback` to
  say the true thing: nothing in the word tells the engine how much history to grant it. **The
  general lesson is the one from task 2a: measure the property, do not declare it.** A declaration
  is a claim; only a measurement is evidence, and here the measurement was right twice when I was
  not.

- **A bigger finding fell out (F29), left open on purpose.** The lead-in a word is granted is its own
  widest parameter, and for **111 of ~180** words that is too little. Recursive words are the worst:
  given exactly 14 sessions, `rsi(14)` is **32% out** on the first bar of a span and `macd` is **41%
  out**. The count is pinned by a test so it cannot grow quietly. The likely fix is small and
  structural — **the lead-in and the purge are the same number today and should not be.** Reading
  extra history before a span is not leakage (a live strategy would have had it) so a lead-in can be
  generous almost for free; a purge costs folds and should stay tight. Not built, because it moves
  every number and that is an operator call.

### Writing off a dead holding — built 2026-08-14 (task 2c, finding F4)

**Operator decision (2026-08-14):** a position in a symbol that has stopped trading is closed at the
**last price it ever printed**, not at zero, with the count and the gross rupees printed on the
metric sheet. The last print is the optimistic reading — a stock usually stops because something
went wrong — and it was chosen over inventing a haircut nobody derived, on condition the exposure
is visible and can be stress-tested later.

Two things came out differently from the plan and are worth keeping:

- **The threshold got its own amendment log.** It first went into the pre-registered `backtest:`
  block with a comment arguing that neither direction flatters a result. That argument was wrong,
  and the task's own test disproves it: writing a dead holding off sooner frees a slot sooner, and
  in a book discarding 94-99.99% of its signals for want of a slot, that changes which later
  signals are taken. So it is result-affecting and editable — the exact shape invariant #25 covers
  — and sitting inside a block whose `registered: 2026-08-05` the loader pins would have let it
  borrow a provenance five sessions older than itself. It now carries the same append-only dated
  log as `objective.min_sharpe`, and the mechanism was generalised into one shared function so
  there is one implementation rather than two that can drift.

- **The first pass fixed half the bug, and the review found the other half.** The write-off covered
  the case where the symbol prints *no bar*. It did not cover the last bar existing while the
  closing order is capped by participation or refused outright — 4,998 of 5,000 shares in the
  reproduction, orphaned exactly as before. Nothing may now survive the final bar by any route.
  Three more came with it: a dark holding was being marked at **zero** in the equity curve (a fake
  drawdown, then a fake spike, straight into the Sharpe the gate reads); entry charges were
  re-booked in full on every partial exit chunk; and dating the write-off at the session it was
  noticed while pricing it twenty sessions earlier could flip a trade from short- to long-term for
  tax. **The lesson is narrower than "review works": fixing the visible half of a bug can make the
  invisible half look closed.** The test that would have caught it is the one that asks whether
  every share bought ends up in exactly one closed trade, not whether the case I was thinking about
  produces a trade.

### The cash constraint — built 2026-08-15 (task 2d, finding F6)

**Operator decision (2026-08-15):** fix the cash constraint now; leave the concentration cap as a
separate decision. A position the account cannot pay for is **skipped and counted**, never shrunk
to fit.

Why skipped rather than shrunk, since buying what you can afford is what a real account does:
shrinking silently changes the position size the strategy specified, and it erases the one signal
decision D9 exists to read. A strategy that works and is merely too big for the money is
`NEEDS_MORE_CAPITAL` — a different verdict from a bad strategy — and a skip counter says so out
loud where a quiet size-down would not.

**No knob for the leverage ceiling.** Total deployment is capped at 100% of the book and that is
not configurable, because this is the delivery segment: leverage there is not a preference anyone
should be able to set, it is unavailable.

Two things worth keeping:

- **The heat cap looked like it should have caught this and mathematically never could.** Heat is
  `stop_distance x quantity`, and quantity is `risk_budget / stop_distance` — the stop distance
  cancels. Every position contributes exactly `risk_r` to heat however large it is, so four
  positions always total 2.0% against a cap of 2.0%: the cap equals the ceiling and can never bind.
  A guard can be present, correct, and structurally incapable of firing. **Worth asking of every
  other limit in the system: is there an input that makes it unable to bind?**

- **The skip counts were being recorded and printed nowhere.** "94-99.99% of every strategy's
  signals were discarded for want of a slot" — the largest single fact about the first backtest —
  was sitting in the JSON the whole time. It now prints on the sheet. A number that is computed and
  not shown is not much better than one that was never computed.

- **A new guard made an old sloppiness matter.** Candidates beyond the free slots were being
  labelled `no_slot` *before* the loop ran. Harmless while refusals were rare; once the cash gate
  existed, a top-ranked candidate refused for cash left its slot **empty** while a cheaper one
  behind it had already been written off as having no room — the book under-deploying and the skip
  table blaming a slot that stayed open. Slots are now filled by what can actually be taken.
  Worth generalising: *adding a way for something to fail can turn an existing approximation into
  a bug.*

- **And I asserted the consequences of the invariant, not the invariant.** Every test checked a
  refusal here or a cost basis there; none said "cash is never negative", which is the thing the
  change actually establishes and the thing a future refactor would break silently. The engine now
  recomputes committed cash each entry pass and raises if it exceeds the book, and a test hands it
  a book it could not have bought to prove the guard is wired up rather than decorative.

### The LTCG threshold — fixed 2026-08-16 (finding F35), found by a review that was not looking for it

The operator asked for a `code-review` and a `ponytail-audit` before task 2e, as a safety check on
removing config. Neither was aimed at the tax model. The review found that the long-term threshold
was `ltcg_holding_months * 30` = **360 days**, where the statute counts twelve calendar months, so
every delivery trade held 361 to 365 days was mis-bucketed.

**What hid it was a comment.** The line above the constant said the approximation "errs toward STCG
(the higher rate) more often than not" — a confident, absolute, untested claim about direction.
Exactly the `momentum` shape from task 2a: a description asserting the opposite of the code, which
is worse than no description, because it answers the question a reader was about to ask.

**And I did it again in the fix.** My replacement said the old code erred "in our favour, always".
It does not. A *gain* in the band was under-taxed; a *loss* was under-valued, because with no
inter-bucket set-off an LTCG loss shelters future gains at 12.5% where an STCG loss shelters them
at 20% — ₹20,800 worse on a ₹100,000 loss followed by a ₹100,000 gain. Same absolute untested
claim, sign flipped, one commit later. The rule now has a test behind it.

**And I overstated the blast radius, twice, to the operator.** I said the bug sat "on the number
the stop gate reads". It does not: the gate checks Sharpe, trade count and expectancy, all built
from an equity curve that is net of **costs only**. Tax is computed afterwards and printed as an
informational line, and `stop_gate.net_of_cost_and_tax` is asserted `True` by the loader and read
by nothing (finding F38). The tax bug made a reported number wrong; it changed no verdict.

**Two durable lessons:**

- **Run the reviews before the task, not only before the commit.** §5 says run them before
  committing. That would have found nothing here — the working tree was clean. Pointing them at
  existing code, because the operator asked, is what surfaced a money bug in the gate path.
- **A prose claim about direction deserves the same suspicion as a number.** "Errs toward the higher
  rate" is a testable statement, and it was never tested. Where a comment claims a bias, the test
  should pin the bias.

Also worth recording: my first version of the month-end test asserted that 2024-01-31 plus 365 days
was long-term. It lands on 2025-01-30, a day *short* of the anniversary. The code was right and the
test was wrong — which is the argument for writing calendar boundaries as dates rather than offsets.

### Config that lies — task 2e, 2026-08-16 (findings F11, F36, F37)

F11 was written as "inert config: decide enforce or delete". The reviews you asked for before the
task showed it had a **second half nobody had named**, and the second half was the dangerous one.

- **Config that promises enforcement it does not have.** 103 of 194 fields were read by no code.
  Most are honest Phase-2 declarations; nothing distinguished them from the dead ones. Seven whole
  sections now carry a dated `NOT ENFORCED` header. Four keys were deleted rather than marked,
  because a marker preserves a promise and these named things that were never designed:
  `min_quality_score` / `rank_select_top_k` (a per-signal scorer that has never existed) and
  `lockbox_eval_budget` (which contradicted the assert enforcing invariant #26 — two knobs for one
  number, disagreeing, and neither wired). `walk_forward_start` was validated and ignored; it is
  honoured now.

- **Config that looks enforced and can be edited to nothing.** Six safety values loaded cleanly at
  settings that switched them off: the −10% drawdown stop at 1.00, the daily halt at 1.00, the VDA
  stress rate at 0.00, and the gate's own Sharpe bound at −5.0. Invariant #4 says hard limits
  cannot be overridden by any strategy or the learning loop — true of strategies, false of a typo.
  Only the crypto leverage ceiling refused, because it alone had an assert. **The pattern already
  worked once and had simply never been applied to anything else.**

**The general lesson, which is why this is in the file rather than only in the audit:** *"is this
enforced?"* and *"can this be un-enforced?"* are different questions, and asking only the first one
leaves a system that passes every test and can be disarmed by one line. Worth asking of anything
that calls itself a limit.

Two smaller things worth keeping. `sizing.weighting` accepted three schemes and implemented one —
now the other two are **refused rather than validated and ignored**, because a file saying one thing
while the engine does another is the `momentum` failure in another costume. And a test in this repo
had been asserting that an unimplemented scheme *parsed*, which it did, right before the simulator
ignored it.

**The review of this task found I had done half of almost every item**, and that is the pattern
worth naming rather than the individual misses. I bounded three rungs of the kill-switch ladder and
left five more risk values open. I refused `weighting` and left its partner `vol_target_pct`
accepted-and-ignored — both were named in 2e's own acceptance criteria. I bounded the walk-forward
window and not the lockbox window, which is the fold evaluated *once*, where a discrepancy cannot
be corrected by a later run. And I gave the two gate thresholds a provenance log without a bound,
so −5.0 still loaded behind a properly signed amendment — **provenance makes a change visible; it
does not make it permitted**, and those are not the same guarantee.

The common thread: I fixed the instance I was looking at rather than the class it belonged to.
Same shape as task 2c, where the write-off closed the no-bar case and left the unfilled-exit case
open. **When a fix has a natural partner — a sibling field, a second call site, the other half of a
pair — the partner is where the next bug is.**

### The guards that don't guard — task 2f, 2026-08-16 (F29, F30, F38–F44)

You asked for this one to be scoped by looking at the whole system rather than by the findings I
happened to be holding. So it was scoped **mechanically**: a behavioural probe of every config
value and every parameter pair, instead of a reading of the audit. That found more than the audit
had, and the code review afterwards found more still. Seven of the eleven review findings were
real defects in work I had just called done.

**The gate was reading pre-tax numbers under a heading that said AFTER TAX.** F38 was supposed to
fix exactly this, and I pointed `gate_verdict` at the after-tax record and stopped. But
`expectancy_r`, `win_rate` and `trades` are derived from the *trade ledger*, and tax never touches
a trade — so the after-tax expectancy was **identical to the pre-tax one by construction**. Two of
three checks were unchanged. A strategy at +0.03R before tax and negative after 20% STCG would
have passed. The fix invents nothing per-trade (tax is annual, on the aggregate, with set-off
between buckets): the pre-tax check is now **labelled** "before tax", and "P&L after tax > 0" sits
beside it. Strictly harder to pass, which is the only direction the gate may move once results
exist.

**And the tax was being under-charged twice over.** The bill was applied *after* the curve point
was written, so the last financial year's bill — landing on the final index by definition — hit
nothing at all. And it was divided by `starting_equity × compounded index` when each fold resets
the book to `starting_equity`, so a bill worth 40% of the account that earned it was charged as
10% once the strategy had quadrupled. **Both errors flattered the strategy, and both landed on the
number the gate reads.** That is the third time in this sequence a bug has been one-directional
and in the promotable direction; it is worth treating one-directional as a smell in itself.

**I over-applied a rule, which is the same failure as under-applying it.** `requires_lt` refuses a
parameter pair that is individually legal and jointly meaningless. It had one user; I added
fourteen more by scanning for parameter *names* that looked ordered — `fast`/`slow`,
`confirm`/`n`, `slope_n`/`n`. **Nine of the fourteen were wrong.** `stage(n=50, slope_n=63)` is a
quarterly slope on a ten-week moving average; `darvas(n=3, confirm=20)` asks a short high to hold
longer. Both are ordinary things to want, and the parser had started refusing them. The measured
rule is **inversion, not oddity**: refuse a pair only when transposing it makes the word mean the
opposite of its own name. Six qualify. The test now re-measures the sign flip on every run rather
than trusting a list — because the list is exactly what went wrong.

Having just been caught fixing instances instead of classes, I had over-corrected into applying a
class-wide rule without checking the instances. **Both failures come from not looking at the
thing itself.**

**Two process lessons, both learned the hard way in this task:**

- **A guard that looks redundant may be the second half of a pair.** I flagged
  `fill_requires_trade_through` and `next_bar_execution` as inert because flipping them changed
  nothing, and wired the code to read them. But the loader *pins both true* — the flags are config
  restating a guarantee the code makes unconditionally, which is the belt-and-braces shape the
  crypto leverage ceiling already uses. Reading them collapsed two independent guarantees into
  one. Reverted; a test caught it. **"Changing this changes nothing" can mean well-protected, not
  dead.**
- **Never write `git checkout --` into a script that runs against uncommitted work.** My mutation
  harness restored each file with `git checkout --` after testing it, and destroyed several hours
  of uncommitted work in `runner.py` and `backtest.py`. It was recoverable only because an earlier
  `git stash` had left a dangling commit. The harness now snapshots file contents in memory and
  writes them back, and mutation runs happen **after** the commit, never before. Related: every
  file here is CRLF, so a multi-line anchor written with `\n` silently matches nothing — the
  harness normalises, and reports a bad anchor as a failure rather than a pass.

**A definition of done that nobody enforces is not a definition of done.** Checking that 2f had
not added `mypy` errors showed the baseline was never zero: **23 errors**, all stale `type: ignore`
suppressions, in a repo whose `CLAUDE.md` requires it clean. Clearing them exposed **12 real type
errors underneath**, including an `int < str` comparison inside the sweep that validates
`requires_lt` pairs. All 35 are fixed and `mypy` is clean across 119 files for the first time.

**One thing deliberately not settled: F40.** Now that the strategy is evaluated over the whole
span, the purge no longer prevents what it was introduced to prevent — and it never was a leak,
because reading history you would genuinely have had is what a live system does every morning.
What survives is that the gap keeps the in-sample and out-of-sample *trading* periods apart, and
that it will matter in Phase 2 when the Inventor starts fitting per fold. Separately, `goal.yaml`
described an embargo that runs *after* each test window while the code widens the gap *before* it;
the wording now matches the code. The real question — with an anchored window every later fold
trains on every earlier test period, and no gap before the test window changes that — is **yours
to decide**, not mine to settle quietly. Cost of the change as it stands is 5 sessions.

### F40 — the purge that protected nothing, decided 2026-08-17 (D10)

You asked me to be sure before recommending. Here is what "sure" rested on, so you can check it.

**The question.** The gap between the end of training and the start of each test window was
`longest_lookback(strategy) + embargo_sessions` — sized per strategy, up to a full year wide. Was
it doing anything?

**Three checks, all pointing the same way.**

1. **What purging is for.** In the literature it removes training observations whose *labels* are
   formed over a period the test set also covers, so a **fitted model** cannot learn what it will
   be scored on. The embargo does the same for the period just after a test fold. Both assume
   something is being fitted.
2. **Nothing here is fitted per fold.** Strategies are pre-registered with fixed parameters, and
   the in-sample record is *measured*, never optimised against.
3. **No state crosses train→test, checked in code.** `_run_span` builds a fresh simulator with
   fresh equity for each span. Training and test are two independent simulations. There is no Kelly
   or other fitted sizing anywhere in the engine. **There is no channel for a leak to travel** —
   so there is nothing for a gap to cut.

**And the per-strategy sizing was doing real harm.** `longest_lookback` deliberately reads `exit`,
so `time_stop(bars: N)` — a *holding period* — was inflating a backward guard. The result:
`baseline_buy_and_hold` ran 7 folds from ~2015 while `xs_momentum_20` ran 8 from ~2014, and the
sheet printed their Sharpe side by side. **A control measured over a different period from the
strategy it controls for cannot establish alpha**, which is exactly what invariant #21 gates on.

**The decision: one fixed `seam_sessions`, the same for every strategy.** This closes F16 and F31
as well, and makes Step 3c's common-window comparison the default rather than a correction applied
afterwards.

**Two things I deliberately did not do**, because both would have been the wrong kind of freedom:

- **I did not change the number.** 5 was set before any backtest result existed. Changing the
  *structure* is justified by a mechanism; changing the *value* now that three strategies have
  failed would be retuning against results, which invariant #25 exists to stop.
- **I did not build the textbook embargo.** Under an anchored window every later fold trains on
  every earlier test window wholesale, and no gap placed *before* the test window touches that.
  It buys nothing while nothing is fitted. `goal.yaml` carries a `NOT ENFORCED` note saying it
  becomes **mandatory** the day the Inventor starts fitting per fold in Phase 2, together with a
  real purge. That is a trap laid for a future version of me.

**What it costs you.** Every strategy now starts its first fold earlier and gets more
out-of-sample data. That is worth being suspicious of, so state it plainly: **more out-of-sample
data is not a lowered bar.** The gate thresholds are untouched, and a wider sample narrows the
Sharpe confidence interval — which helps a real edge and does nothing for a spurious one. If a
strategy that failed before now passes *only* because of this, that is a finding, not a result,
and I will say so.

### The look-ahead guard that was not guarding — task 2g-1, 2026-08-17 (finding F24)

**What look-ahead is.** A formula that accidentally uses tomorrow's price to decide today's trade.
It is the most dangerous class of backtest bug because it does not crash or look odd — it produces
a *beautiful* result made of trades nobody could have taken.

**How we test for it.** Compute every word in the vocabulary over the full price history. Then chop
the history short and compute it again. The part they overlap must be identical. A word that peeks
at tomorrow gives a different answer for today once tomorrow is removed — so the two runs disagree,
and the disagreement names the culprit. It runs over the whole vocabulary, which is the only way to
catch a peek in a word nobody thought to check by hand.

**Why it was not working.** The test ran on a made-up 120-bar price series where every candle's
high was exactly the body top **plus a fixed 0.5**. So two bars with the same body had *exactly the
same high*. Every structure word in the SMC vocabulary needs a **strictly** higher high to confirm
a swing — a tie is not strictly higher — so no swing ever confirmed. `swing_high` returned "no
value" for the entire series, and so did everything built on it: order blocks, breaks of structure,
liquidity sweeps. The test then compared *no value* against *no value*, found them equal, and
recorded the word as checked. **71 of the 182 words were in that state.**

**Why it mattered now rather than in August.** Until task 2f, each fold was handed a *sliced* panel
— the future was physically absent from the array the vocabulary ever saw, so a peeking word had
nothing to peek at. 2f replaced that with whole-span evaluation, which made **causality the only
thing** standing between a peeking word and every number the engine produces. I leaned on that
guarantee in 2f's own documentation while 39% of it was untested. **The finding did not change; the
stakes did, and nobody re-ranked it — including me.**

**The fix, and the proof it was needed.** The wick is now drawn from a seeded pool (stable per bar
when the series is truncated, so a prefix cannot differ on noise and cry wolf) and the series runs
600 bars instead of 120. Blank words: **71 → 2**. Then the real test — I removed the confirmation
lag from `_confirmed`, so every swing is reported `k` bars before the market could know it, which
is a genuine look-ahead bug in the foundation every structure word stands on:

| | words detecting the planted bug |
|---|---|
| old fixture | **0** |
| new fixture | **37** |

**The guard was not thin, it was blind.** Worth stating plainly: **no real look-ahead bug was found
in the 71.** They all pass genuinely now. The vocabulary was fine; the test was not — which is the
better of the two outcomes, and not the one I would have bet on.

The two that stay blank are `bpr_top` and `bpr_bottom`. A balanced price range needs a bullish and
a bearish gap live *and overlapping* at once, which a random walk essentially never produces. They
now have hand-built fixtures pinning the exact bars and edges, and the sweep names them
individually rather than allowing a count — so a third cannot join them quietly.

### The flags nobody checked, and a cap on one name — task 2g-2, 2026-08-17 (findings F27 and F34)

**Part one: the `scale_free` flags with no verification (F27).**

Recap of why the flag exists. Task 2a found that `momentum` returned a change in **rupees**, so
ranking candidates by it ranked them by *share price* — a ₹2,000 stock moving 1% beats a ₹200 stock
moving 5%. The fix was to label every word in the vocabulary with whether its output is
**scale-free** (a percentage, a ratio, a z-score — comparable across symbols) or
**price-denominated** (rupees — not comparable), and to make `rank_by` refuse a rupee input at
parse time. A **guard test** then proves each label honest: take one symbol, re-denominate it
(multiply price by 7, divide volume by 7 — the same company, quoted differently), and check that
the scale-free words give the *same* answer while the rupee words move.

**What was wrong.** That sweep runs on a single symbol in isolation. Any word needing the whole
market (`needs_panel`), an external feed (`requires_feed`), or intraday bars (`intraday_only`) is
simply skipped — so **17 of the 93 declared flags were never checked at all.** The guard against
"a label that lies" had a hole exactly where the label is hardest to eyeball.

**The fix.** A **panel half** of the sweep: re-denominate one symbol inside a 25-name universe and
demand that symbol's own column be unchanged. That covers the 11 reachable panel words. A coverage
test then asserts the two sweeps **partition** the declared vocabulary — a new panel word cannot
land in neither. The remaining 6 have compute functions that currently *raise* (five wait on
finding F7 to thread the India feeds into `Bars`; one refuses until the sector map is dated per
bar), so they are pinned as unverifiable-by-construction and **will fail the moment somebody
implements them** — forcing the flag to be checked in the same change rather than years later.

**What mutation testing taught here, and it was not what I expected.** The *fixture* was the weak
part, not the assertion. With a mid-priced symbol as the one being split, a planted bug that
compared `close` to an absolute threshold **survived** — a stock at 290 and the same stock at 2,030
are both above almost any threshold you pick, so the bug's output did not change. Splitting the
**cheapest** name in the universe moves it across the whole price range, and the same bug died.
2 of 4 caught → 4 of 4.

**Part two: the concentration cap (F34, decision D11).**

**What was missing.** Task 2d stopped the book spending money it did not have. Nothing stopped it
putting *all* of that money into one name. Risk sizing bounds the loss **if the stop holds** — and
overnight, a stop does not hold: the market reopens wherever it reopens, and `fills.py` already
models this by filling a stop at the worse of trigger and open.

**Why 0.25 and not the 0.50 you proposed.** With a fraction C of the book in one name and an
overnight gap g, the account loses C×g. At C=0.50, a 20% lower circuit — one bad morning, one
name — is a **10% account loss, which is exactly `max_drawdown_killswitch`**: operator-only
restart, from a position nominally "risking 0.5%". At 0.25 the same gap costs 5%. 0.25 is also
**derived rather than picked**: `max_open_positions` is 4, so it is one name's equal share of a
full book, and a test pins the two together so they cannot drift apart silently.

**It shrinks, it does not refuse.** This matters and is easy to get backwards. The cap is the
fourth term in `CLAUDE.md` §4's `min(...)` — it makes the position smaller. The **cash gate**, by
contrast, *skips* the trade. The difference is whether more money would fix it: cash is
scale-dependent, so a skip is real information and feeds the D9 `NEEDS_MORE_CAPITAL` verdict;
concentration is scale-invariant, so there is nothing a bigger account would fix and refusing would
just throw away a tradable signal. It is sized against the **filled** price, not `bar.open`, so
slippage cannot leave it a few basis points over. Code refuses any config value above 0.50 whatever
`goal.yaml` says — the same belt-and-braces shape as the crypto leverage ceiling.

**What it does not do, which the docstrings originally claimed it did.** The cap is checked **at
entry and never again.** A winner drifts straight past it: measured on a name compounding 5× from a
₹1,00,000 book, a position entered at 25% is **61% of the mark-to-market account by bar 58** —
where a 20% circuit is a 12% hit, past the very killswitch the 0.25 was chosen to stay inside. A
second, quieter version of the same gap: the `equity` the cap measures against is the **realised**
book (`starting_equity + realised P&L`), so unrealised losses do not shrink it — with ₹75,000 of
cost basis now worth ₹30,000, a fresh entry may take 45% of what the account is really worth.

Both halves are **finding F45, open, and yours to decide**, because trimming a winner realises
gains, pays brokerage and triggers tax — that is a policy choice, not a bug fix. The docstrings now
say "at entry", and a test pins the drift so it cannot be rediscovered as a surprise.

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
| Host (historical) | ~~operator-supplied Linux/Ubuntu PC (supersedes AWS `t4g.small`)~~ — superseded by D24/D30's current-PC clarification; no OS migration approved | 2026-08-02; superseded 2026-09-30 |
| Host (current) | current Windows PC; no separate Linux system; supported local simulator/tests here; official platform/deployment arrangement unresolved | D24, 2026-09-27; D30, 2026-09-30 |
| Crypto | deferred — equity-delivery first | 2026-08-02 |
| Broker | Zerodha Kite Connect, ₹500/mo, active | O1 |
| Equity delivery tax | capital gains (CA confirmation still open, O7) | 2026-07-31 |
| `objective.min_sharpe` | 1.0 (append-only amendment log in `goal.yaml`) | 2026-08-02 |

## 10. Open operator items

Tracked in full at the top of `TASKS.md`. Currently blocking:

- **O4 - host/deployment details.** D24/D30 select the current Windows PC; supported synthetic simulator/tests run here. No separate Linux system or OS migration is approved. Future live-data/deployment setup needs registered static egress IP, CPU, current OS/version, RAM/disk, always-on operation, UPS, remote access and encryption; these do not block local synthetic testing. Stored timestamps remain UTC tz-aware.
- **F45 — should the concentration cap trim winners?** Blocks nothing today, but has to be settled
  **before 3b**, which is where concentration bites. The cap (D11, 0.25) is checked **at entry
  only**: a name compounding 5× reaches **61% of the book by bar 58**, past the drawdown killswitch
  the 0.25 was chosen to stay inside. Trimming realises gains, pays brokerage and triggers tax, so
  it is a policy choice, not a bug fix. Second half of the same question: the cap is measured
  against **realised** equity, so unrealised losses do not shrink it. Full write-up in §7c.
- **O5 — daily auth**: operator one-tap vs TOTP automation.
- **O7 — CA confirmation** on equity-delivery classification.
