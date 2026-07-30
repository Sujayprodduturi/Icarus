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

**250 automated tests; formatter + type-checker clean.** Phase 0 ✅ complete · Phase 1 🔨 in progress.

### Phase 1 — Data + backtesting + an honest metric sheet (current)

The goal of this phase is to be able to test a strategy on history and get a number we can *believe*, then hand it to a human and stop. Most of the work here is about making the data honest, because a backtest built on flattering data is worse than no backtest — it produces false confidence.

| Piece | What it does (plain English) | Status |
|---|---|---|
| Data ingestion (1.1) | Pulls daily price bars from two independent free sources and cross-checks them against each other | ✅ |
| Data quality gate (1.1b) | Catches data that is *broken* — nonsense prices are rejected (never smoothed over), a frozen feed halts the system rather than trading on stale prices | ✅ |
| Honest history (1.1c) | Catches data that *lies* — see below | ✅ |
| **Cost model (1.5)** | Works out exactly what the government and broker take on every trade, to the paisa | ✅ |
| **Tax model (1.6)** | What's actually left after tax — and it depends on *how* you traded, not just how much you made | ✅ |
| Strategy language (1.4) | A restricted vocabulary strategies must be written in, so they're always human-readable | ⏳ next |
| Backtester + fill model (1.7, 1.7b) | Replays history honestly: a limit order only fills if the price actually traded *through* it, and today's signal can only trade tomorrow | ⏳ |
| Metrics + overfitting guards (1.8, 1.9) | Scores a strategy, and works out how likely the score is luck | ⏳ |
| Validation gate (1.11) | Runs a strategy through all the checks and issues a verdict with evidence | ⏳ |

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
| O3 | **Delta Exchange India** account + keys + **testnet**; **disable withdrawals** | Phase 1 crypto sim / Phase 2 crypto live |
| O4 | **Host + static IP** (cloud Elastic IP or home ISP static IP); register it with every venue | Phase 2 |
| O5 | **Daily-auth approach** — operator one-tap (default) vs TOTP automation (own risk) | Phase 2 |
| O6 | **CA confirmation** of INR-settled crypto-derivative tax treatment (contested — PRD §6) | Scaling crypto |
| O7 | **CA confirmation**: is systematic delivery trading *business income* or *capital gains*? ~10 percentage points of tax either way. Icarus defaults to the costlier reading so results are never flattered | Honesty of the Phase-1 metric sheet; real tax at Phase 2 |

**Open decisions** (don't block Phases 0–1):

- **Seed capital** — now has hard evidence rather than opinion: below ~₹10k the trading costs are structurally larger than the edge, so **~₹25–30k is the floor**. Decide at the Phase-1 review. (`BUILD_MAP.md` §6.1)
- **Live hosting** — cloud VM (~₹1,400/mo) vs home PC + ISP static IP (~₹200–500/mo). Decide at Phase 2.

**Decided since Phase 0:** the Kite ₹500/mo API fee is treated as a **capital investment in the business**, not a per-trade cost — so every strategy number Icarus reports is *before* infrastructure cost, and the ₹500 gets its own line in the daily report rather than being quietly absorbed.

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
