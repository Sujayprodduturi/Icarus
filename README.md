# Project Icarus

**A multi-agent, self-learning, fully-autonomous trading system for the Indian market** (equities + INR-settled crypto derivatives), built under SEBI rules. **Safety first, edge second.** When unsure, it halts rather than trades.

> **This is not financial advice.** Even a well-built version of this is more likely to slowly lose money than to compound. Treat the seed capital as tuition. See `PRD.md` and `CLAUDE.md` §0.

> **For any agent or person reading this repo:** this README is the living front door — it explains *what Icarus is* and *what's built so far*, in plain English. The deep specs are `PRD.md` (the full requirements), `TASKS.md` (the phase-by-phase checklist), `CLAUDE.md` (the 22 safety invariants — never violated), and `BUILD_MAP.md` (decisions). This file is kept up to date as the build progresses.

---

## What Icarus is (plain English)

Icarus is a robot that will eventually trade real money on the stock market by itself, learning and improving as it goes. The single most important design rule is that **the robot must be structurally unable to do dangerous things** — safety is enforced by how the code is built, not by good intentions.

Because bugs here lose money or break the law, the system is built to **fail safe**: on any doubt — a data gap, a disconnect, records that don't match — it **halts and alerts** rather than improvising.

### The core safety idea: two planes, one bridge

Icarus is split into two halves that are walled off from each other:

- **The execution plane** — *fast, dumb, safe.* It only trades strategies that have already been proven. It's the only half that can touch money, and it never improvises.
- **The research plane** — *slow, smart, sandboxed.* This is where new strategies are invented and tested. It has **no access to money and no way to reach a broker** — enforced at the operating-system and network level, not by convention.

The only connection between the two halves is a **versioned list of approved strategies**, and a strategy only gets on that list by passing an automated, numeric quality gate. A bad idea in the research half physically cannot reach real money except by passing that gate. *This separation is the whole point of the design.*

### "Can place nothing" — the guarantee that still holds

Right now the system can log in and read market data, but it **cannot place a single order**. This isn't a setting — every order-placing function in the code raises an error, in one central place, and automated tests prove it. We are building the brakes, seatbelts, and dashboard *before* connecting the engine. No live-order code exists before Phase 2, and a human reviews the evidence at the end of Phase 1 first.

---

## Current build status

**421 automated tests; formatter + type-checker clean.** Phase 0 ✅ complete · Phase 1 🔨 in progress.

**🗓️ Target: code-complete 30 Sep 2026 · live-mode sim Oct 2026 · first real trade Nov 2026.**

### Phase 1 — Data + backtesting + an honest metric sheet (current)

The goal of this phase is to be able to test a strategy on history and get a number we can *believe*, then hand it to a human and stop. Most of the work here is about making the data honest, because a backtest built on flattering data is worse than no backtest — it produces false confidence.

| Piece | What it does (plain English) | Status |
|---|---|---|
| Data ingestion (1.1) | Pulls daily price bars from two independent free sources and cross-checks them against each other | ✅ |
| Data quality gate (1.1b) | Catches data that is *broken* — nonsense prices are rejected (never smoothed over), a frozen feed halts the system rather than trading on stale prices | ✅ |
| Honest history (1.1c) | Catches data that *lies* — see below | ✅ |
| **Cost model (1.5)** | Works out exactly what the government and broker take on every trade, to the paisa | ✅ |
| **Tax model (1.6)** | What's actually left after tax — and it depends on *how* you traded, not just how much you made | ✅ |
| **The pass mark (1.0g)** | The numbers a strategy must hit to be allowed real money — written down *before* we ran anything. See below | ✅ |
| India-only data (1.1d) | Three free feeds that exist nowhere else in the world — see below | ✅ |
| Strategy language (1.4a) | A restricted vocabulary strategies must be written in — 97 words, see below | ✅ |
| SMC + cross-sectional words (1.4b/c) | Market structure, liquidity sweeps, and ranking across the whole universe | ⏳ next |
| Backtester + fill model (1.7, 1.7b) | Replays history honestly: a limit order only fills if the price actually traded *through* it, and today's signal can only trade tomorrow | ⏳ |
| Metrics + overfitting guards (1.8, 1.9) | Scores a strategy, and works out how likely the score is luck | ⏳ |
| Practice runs (1.10) | Two modes: replay old data through the live machinery to catch cheating, then run on real live data to prove the plumbing works | ⏳ |
| Validation gate (1.11) | Runs a strategy through all the checks and issues a verdict with evidence | ⏳ |

**We wrote down the pass mark before we ran anything (1.0g).** This one is worth explaining, because it's the change we're most glad we made. The plan used to say: *"produce a metric sheet and give it to the operator."* That sounds responsible, and it is completely empty — it says what to **produce**, not what would count as **failing**. We had it reviewed by a panel of five AI advisors with deliberately different outlooks, and all five independently said the same thing: that's not a gate, it's a ceremony. You cannot fail it.

Why it matters is human, not technical. Imagine the result comes back mediocre. A voice says: *"well, that threshold was arbitrary anyway… and this stretch of history was unusual… and it's positive, which is something… let's just go live small and see."* That reasoning isn't stupid. It's just unfalsifiable — you'd have used it at any number. So the numbers are now fixed in the config file, dated, and **the code refuses to start if you change the date to make an edit look like it was always there**. If every strategy fails, the answer is to change what we feed it — better data, a different kind of strategy — and never to lower the bar.

**The pass mark now has its final number, and a way to change it honestly (O8).** The Sharpe ratio a strategy must hit was set to **1.0** on 2 Aug 2026 — before any backtest existed. A lower bar of 0.70 was proposed and rejected, for a reason worth recording: a *separate* rule already requires the result to be statistically distinguishable from zero, and over the three-year minimum test window that alone demands roughly 0.95. So 0.70 would have been a dial connected to nothing — a bar that cannot fail anything, which is exactly the flaw the review panel found last time.

The operator also asked that the number stay changeable in future, and that's a fair ask — a threshold you can never revisit is its own kind of trap. The resolution: it's changeable, but **never quietly**. Every change is a dated, reasoned entry in an append-only log, the code refuses to start if the live number doesn't match the newest entry, and any change made *after* results exist must explicitly tick a box saying so. That doesn't block you from lowering the bar after a disappointing result — it's your call — it just makes it impossible to do so unnoticed. Which is the part that actually protects us: a threshold must never be able to pretend it was always there.

**A restricted language for writing strategies (1.4a).** A strategy could just be Python code — but then three things become impossible: you couldn't read it at a glance, the compliance checks couldn't verify it's explainable, and the strategy-inventing agent we build later could write *anything*, including something that quietly ignores a risk limit. So strategies are written in a fixed vocabulary of **97 allowed words** — like a form with dropdowns instead of a blank page. If a word isn't in the list, it cannot be said.

The interesting part isn't what the language accepts, it's what it **refuses**:

- An unknown word is rejected, never ignored. A typo'd setting is rejected too — otherwise the strategy silently runs a different rule than the one written down.
- A setting outside its allowed range is **rejected, not quietly corrected** to the nearest legal value. Correcting it would run a strategy nobody wrote and report the result under its name.
- Words that only make sense on minute-by-minute data **refuse to run** on daily data rather than approximating themselves.
- Words that need a data feed we haven't built yet **refuse** rather than returning a harmless-looking default. This is the most dangerous case of all: a news filter that quietly answers "nothing to worry about" produces a backtest showing profit that depended on a filter *which was never actually running* — and it looks like a great result.
- A strategy asking to risk more than the config allows is rejected, not shrunk. Silently shrinking it would teach the future strategy-inventing agent that asking for too much is free.
- A strategy with **no stop-loss** is rejected outright. A take-profit and a time limit leave the downside open.

**We found a real bug in our own code, and only one kind of test could have caught it.** Nearly every one of these calculations needs a "warm-up" — a 14-day average has no honest value on day 3. Our first version filled in that gap with the next available number so the maths would start sooner. That sounds harmless. It isn't: it *invents a data point that never existed*, which shifts the whole calculation one day early and double-counts the first real reading. Checked against the textbook worked example, our RSI was off by about **3.5 points** — easily enough to change whether a signal fires. No amount of eyeballing would have caught it, because every number looked perfectly reasonable. What caught it was writing the formula a *second* time, independently, straight from the definition, and demanding the two agree.

The other test worth mentioning runs every one of the 97 words twice: once over the full price history, and once over a truncated copy with the last stretch deleted. If any word secretly peeks at future prices, its answers for the *past* change when the future is removed — so the two runs disagree and the test names the culprit. It covers words nobody thought to check by hand, and it fails if that coverage ever quietly shrinks.

**Three free data feeds that only exist in India (1.1d).** Every indicator in every trading book has been tested by thousands of people with better data than us. But NSE publishes three things daily, for free, going back to 2011, that have no Western equivalent — so nobody outside India has mined them. **Delivery percentage**: how much of a day's trading was people actually *buying* shares versus day-traders passing them around — a direct read on conviction. **Participant-wise positioning**: how foreign institutions, domestic institutions, professionals and ordinary retail traders are *each* positioned, separately. And the daily **ban list**. That second one is the interesting one — "smart money versus everyone else" is usually a story people tell about squiggles on a chart; here it's a published number. If Icarus has an edge anywhere, this is where to look first.

Now that it's built, the live data does behave the way the idea predicts. On any given day the foreign institutions and the retail crowd sit on almost exactly opposite sides of the same bet — on 13 July 2015 foreign institutions were net long 289,350 index-futures contracts while retail was net short 290,219; on 28 July 2026 the two had swapped sides. That's not proof of anything profitable yet, but it is the raw material being real rather than theoretical.

**What 11 years of real files taught us that no amount of planning would have.** We didn't write these parsers from the documentation — we ran them over actual archive files spanning 2015 to 2026, and three things turned up that would each have been a silent, expensive bug:

- **The exchange spells its own dates four different ways** (`Jul 28, 2026`, `Mar 03,2021`, `July 02, 2018`, `Mar 20 2020`). Our first version handled the modern spelling perfectly and quietly refused *half of recorded history*. If we'd tested only on recent files, we'd have lost a decade of data and never known why.
- **The exchange's own files sometimes don't add up.** Each file lists four groups of traders plus a total, so we check that the four add up to the total — a good way to notice if the format ever changes. Except NSE's own arithmetic is occasionally off by exactly one contract (11 of 48 files we sampled). The obvious strict check would have shut the feed down on the most recent real trading day. So the check allows a tiny discrepancy, and the size of that allowance is measured from real files rather than guessed.
- **A safety check that looks strong can be weaker than it appears — so we wrote down its actual limits.** That "does it add up" test would *not* catch the columns being shuffled, because the total row shuffles too and the sums still agree. What really protects us is reading columns by name. We documented this in the code rather than letting a future reader assume the check covers more than it does.

**One deliberate design choice on the ban list.** When too many traders crowd into one stock's derivatives, NSE bans new positions in it for a day. That's a legal boundary, not a trading opinion — so the code exposes only "is this banned, yes or no," and deliberately offers no *number* (like "how often has this been banned"). A number is something the learning loop could learn to chase; a boolean is something it can only obey. And if the file can't be read, the system refuses to answer rather than replying "nothing is banned" — because "I don't know what's banned" and "nothing is banned" must never come out as the same sentence.

**Two ways data lies, and what we did about them (1.1c).** First, **survivorship**: if you test on today's list of companies, every company that went bust in between is missing, so your strategy is quietly being graded on winners only. We fixed this by building the tradable list *out of the exchange's own end-of-day files*, so a company that hadn't listed yet simply isn't there, and one that got delisted just stops appearing. Second, **share splits**: when a company splits its shares 1-for-2, the price halves overnight while nothing real changes — but to a strategy that looks like a 50% crash, and it triggers every stop. We rescale old prices so the series is continuous.

**Why tax needed its own model (1.6).** Cost is per-trade: you buy, you pay, done. **Tax is annual and applies to your total** — you can't know the tax on one trade without knowing how the rest of the year went. And Indian law taxes the *manner* of trading, not just the profit: same-day trades, held trades, and F&O all land in different buckets with different rates *and* different rules about whether your losses count for anything. The extreme case is crypto under the "VDA" reading, where losses count for **nothing at all** — tax lands on your winning trades alone. Same crypto ledger, two readings: a **31.2%** effective tax rate under the favourable reading, **66.9%** under VDA. That's why a strategy which only survives the optimistic reading gets flagged rather than promoted.

**What the cost model told us (1.5).** In India there's a flat ₹15.34 fee every time you sell shares you were holding. Flat means it doesn't shrink with your position, so it hurts small accounts specifically. Measured out: at a ₹2,000–3,000 starting pot, a trade has to earn back **1.6–2.4× the amount it was risking** before it makes a single rupee — no strategy survives that. At ₹25,000–30,000 it's about **0.3×**, which is comfortably absorbable. That's why the seed-capital floor is roughly ₹25–30k: not a preference, just where the arithmetic stops fighting us. Full table in `BUILD_MAP.md` §6.1.

### Phase 0 — Skeleton & safety rails ✅ complete (17 of 17)

Goal: the system authenticates, streams data, and can place nothing. **Met.**

| Piece | What it does (plain English) | Status |
|---|---|---|
| Repo + tooling (0.1, 0.1b) | Project setup; auto-formatter, type-checker, test suite, CI gate that runs on every push | ✅ |
| Message types + versioning (0.16b, 0.6) | The shared "official forms" every agent uses; a universal broker plug-shape; the wall that makes all order methods raise | ✅ |
| Rulebook (0.2) | `goal.yaml` holds every risk number; the loader refuses to start if a hard safety limit is loosened | ✅ |
| Message bus (0.3, 0.13) | The durable conveyor belt agents pass messages on; nothing important is silently lost | ✅ |
| Database + audit log (0.4) | Permanent memory (positions, trades, strategies); a **tamper-proof, append-only** audit trail enforced by the database itself | ✅ |
| Logging + secret-scrub (0.12) | Structured logs that automatically redact anything resembling a password or key | ✅ |
| Emergency stop (0.14) | A HALT marker in shared storage + a **separate kill program** so the stop works even if the main program freezes | ✅ |
| Orchestrator (0.5) | The conductor: a strict daily routine (you can only reach TRADING via RECOVERY), plus a supervisor that restarts crashed agents and obeys the kill-line | ✅ |
| Compliance gate (0.10) | The bouncer every order passes: limit-only, correct ID tag, registered IP, market open, speed limit — rejects or halts | ✅ |
| Calendar (0.15) | NSE trading days/hours + crypto 24/7; refuses to guess the market state for an unknown year | ✅ |
| Clock check (0.16) | Halts at startup if the computer's clock disagrees with internet time | ✅ |
| Broker adapters (0.7–0.9) | Read-only connectors for Zerodha, Delta India, Upstox (writes raise) | ✅ |
| Daily-auth agent (0.11) | Logs in each morning; only enters TRADING on success, else stays safe and alerts | ✅ |
| Phase-0 exit + Hermes handoff (18) | A codebase scan proving no order path exists; deploy runbook + systemd for the second PC | ✅ |

**Later phases** (not started): after Phase 1 there's a **🛑 STOP for human review** → Phase 2 = first live trading (tiny, real money) → Phase 3 = the self-learning loop → Phase 4 = hardening → Phase 5 = scaling.

---

## Architecture tour (the pieces, and how they connect)

A price arrives → it's normalized into a standard message → it travels the **bus** → agents react. When (in a future phase) a strategy wants to trade, the order must pass the **compliance** bouncer, and today it also hits the wall that makes every order raise an error. Every decision is written to the tamper-proof **audit log**. The **orchestrator** runs all agents at once, restarts any that crash, and obeys a **HALT flag** that a **separate kill program** can flip — a stop that keeps working even if the orchestrator dies. The **rulebook** (`goal.yaml`) governs every risk number and won't let anyone loosen a hard limit.

The twelve agents (most still to come) are grouped into the two planes:

- **Execution plane:** Data → Regime → Signal → Risk → **Execution** (the only writer) → Portfolio
- **Research plane:** News/Sentiment, Macro, Strategy-Inventor, Validation (the gate)
- **Cross-cutting:** Compliance (policy enforcer), Oversight (daily report + manual kill)

See `PRD.md` §9–§10 for the full roster and `BUILD_MAP.md` for the one-page map.

---

## Developer setup

Requires **Python 3.12**, **[uv](https://docs.astral.sh/uv/)**, and **Docker Desktop** (for the local Postgres + Valkey).

```bash
uv sync --extra dev                              # create the environment + install deps
cp .env.example .env                             # fill in as creds become available
docker compose -f deploy/compose.yaml up -d      # start Postgres 16 + Valkey 8
export ICARUS_PG_DSN="postgresql+psycopg://icarus:icarus@localhost:5432/icarus"
uv run alembic upgrade head                      # create the database tables

uv run ruff check . && uv run ruff format --check .   # lint + format
uv run mypy                                           # type-check (strict)
uv run pytest                                         # run all tests
```

That four-part gate (lint → format → types → tests) is exactly what CI runs and what the deploy machine must pass before reporting success.

---

## Deployment (the "Hermes" second machine)

Code moves to a separate **Linux** PC via this **private GitHub repo**; **secrets never travel** (only `.env.example`). An agent named Hermes on that machine follows `deploy/HERMES.md` (a runbook written for an agent, with a checklist it must pass). Phases 0–1 need no money and no fixed IP, so the whole thing can be deployed and run through the Phase-1 review without touching the money path.

---

## Operator action items (things the system can't do for itself)

Each blocks the noted phase. Phases 0–1 need **no capital and no static IP**.

| # | Item | Blocks |
|---|------|--------|
| O1 | **Zerodha** Kite Connect plan active; register the deploy host's static IP | Phase 2 (equity live) |
| O2 | **Upstox** account + API app (free data); whitelist the host IP | Phase 4 failover (data usable earlier) |
| O3 | **Delta Exchange India** account + keys + **testnet**; **disable withdrawals** | 🔴 **Phase 1** — the live-mode practice run needs testnet |
| O4 | **Host + static IP** (cloud Elastic IP or home ISP static IP); register it with every venue | 🔴 **Phase 1** — same reason; live market data must come from the registered IP |
| O5 | **Daily-auth approach** — operator one-tap (default) vs TOTP automation (own risk) | Phase 2 — but **decide early**, it changes what gets built |
| O6 | **CA confirmation** of INR-settled crypto-derivative tax treatment (contested — PRD §6) | Scaling crypto |
| O7 | **CA confirmation**: is systematic delivery trading *business income* or *capital gains*? ~10 percentage points of tax either way. Icarus now uses **capital gains** (operator decision) — the *cheaper* reading, and the only assumption in the tax model that errs in our favour, which is exactly why it needs checking | Honesty of the Phase-1 metric sheet; real tax at Phase 2 |
| O8 | **Set the minimum Sharpe** — config says 1.3, and 0.70 was proposed as the realistic floor. Buying and holding the Nifty is about 0.5–0.7, so 0.70 means "beat doing nothing." A bar nobody can clear is a veto, not a bar | 🔴 Must be settled **before the first result exists** |

> **⚠️ O3 and O4 moved from Phase 2 to Phase 1.** They were mislabelled. The live-mode practice run is a Phase-1 task and it needs a testnet account and a registered static IP — so roughly two hours of admin is currently holding up weeks of calendar time.

**Open decisions** (don't block Phases 0–1):

- **Seed capital** — now has hard evidence rather than opinion: below ~₹10k the trading costs are structurally larger than the edge, so **~₹25–30k is the floor**. Decide at the Phase-1 review. (`BUILD_MAP.md` §6.1)
- **Live hosting** — cloud VM (~₹1,400/mo) vs home PC + ISP static IP (~₹200–500/mo). Decide at Phase 2.

**Decided since Phase 0:**

- The Kite ₹500/mo API fee is a **capital investment in the business**, not a per-trade cost — so every strategy number Icarus reports is *before* infrastructure cost, and the ₹500 gets its own line in the daily report rather than being quietly absorbed.
- **Equity delivery is taxed as capital gains**, not business income — Icarus places the trades the operator would have placed personally, and automating your own investing doesn't by itself make it a business. Still needs a CA's sign-off (O7).
- **The pass mark is pre-registered and can't be renegotiated afterwards** (`goal.yaml → stop_gate`). If everything fails, we change the input, not the bar.
- **How long until we know if this works** was measured, not guessed. It turned out a strategy that holds positions for 42 days would take **20 months** to produce enough live evidence to judge — so the practice run was split in two: replaying old history through the live machinery catches cheating instantly and for free, while only the "does the plumbing work" question needs real waiting. That took the first-real-trade date from April 2027 to **November 2026 without relaxing a single standard.** (`BUILD_MAP.md` §6.2)
- **We're not using the Claude Agent SDK for Icarus's runtime.** It's excellent for *building* this, and wrong for *being* it: the trading path has to be deterministic and replayable, and an AI loop with shell access near broker credentials is precisely what the safety rules forbid.

---

## The non-negotiable safety invariants (short list)

Full list in `CLAUDE.md` §0. The load-bearing ones:

1. Research plane has **no broker credentials and no path to a broker.**
2. The Execution agent is the **only** component with order-placement credentials.
3. No strategy reaches live money except through the **numeric validation gate.**
4. **LIMIT orders only — never MARKET.** Every order is algo-tagged, from the registered static IP.
5. Crypto leverage **hard-capped at 2×** (1× at seed) — in config, code, and an execution-time check.
6. **No money-movement capability** is ever wired in. Trading only.
7. **Fail safe, not silent** — on any doubt, halt and alert.
8. **No live order path before Phase 2**, and a human reviews the Phase-1 evidence first.
9. **Halt on going nowhere, not just on losing.** Every other stop-loss reacts to a *fast* loss. After 50 live trades, if we're not actually up after costs and tax, the system stops and says so — because the likeliest way to fail here isn't a crash, it's bleeding away slowly while every safety check passes.
10. **The pass mark doesn't move after we see the score.** It was written down first, and the code refuses to start if the date on it is edited.

---

## Repository layout

```
icarus/
├── orchestrator/   # the conductor: daily-routine state machine, agent supervision, kill-line
├── bus/            # the durable message conveyor belt (Valkey Streams)
├── agents/         # the workers: data, regime, signal, risk, execution, portfolio,
│                   #   news_sentiment, macro, research, validation, compliance, oversight
├── brokers/        # the universal broker plug-shape + Zerodha / Upstox / Delta connectors
├── strategy/       # the strategy language, the approved-strategy registry (future phases)
├── engine/         # costmodel.py (built); tax model, backtester, metrics, simulation to come
├── state/          # the database models + migrations
└── common/         # shared vocabulary: message types, config, logging, clock, calendar, halt flag
deploy/             # docker-compose for Postgres+Valkey, systemd units, the Hermes runbook
tests/              # unit tests (happy AND halt paths) + integration + golden backtest (Phase 1)
```

---

## For contributors and agents

- **Branch flow:** all work goes to `dev`; `main` holds only working code. Merge `dev → main` at working milestones.
- **Every change is committed** — commit messages are the project's running memory (what changed, why, what's next).
- **Quality bar:** each change is run through the `ponytail` skill (simplest thing that works, no over-engineering) and reviewed; the full `/code-review` runs at phase boundaries.
- **Definition of done** (per `CLAUDE.md` §6): tests for the happy path *and* the halt path, formatter/type-checker clean, safety limits proven unexceedable, no secrets committed.
