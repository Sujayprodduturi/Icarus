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

### "Can place nothing" — the Phase-0 guarantee

Right now the system can log in and read market data, but it **cannot place a single order**. This isn't a setting — every order-placing function in the code raises an error, in one central place, and automated tests prove it. We are building the brakes, seatbelts, and dashboard *before* connecting the engine. No live-order code exists before Phase 2, and a human reviews the evidence at the end of Phase 1 first.

---

## Current build status

**Phase 0 — Skeleton & safety rails.** Goal: the system authenticates, streams data, and can place nothing. **In progress (14 of 18 pieces done).** Everything below is built, tested, and green (79 automated tests; formatter + type-checker clean).

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
| Broker adapters (0.7–0.9) | Read-only connectors for Zerodha, Delta India, Upstox (writes raise) | ⏳ in progress |
| Daily-auth agent (0.11) | Logs in each morning; only enters TRADING on success, else stays safe and alerts | ⏳ todo |
| Phase-0 exit + Hermes handoff (18) | A scan proving no order path exists; deployment runbook for the second PC | ⏳ todo |

**Later phases** (not started): Phase 1 = data + backtesting + honest metric sheet → **STOP for human review** → Phase 2 = first live trading (tiny, real money) → Phase 3 = the self-learning loop → Phase 4 = hardening → Phase 5 = scaling.

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

**Open decisions** (don't block Phases 0–1): seed capital amount (resolve at the Phase-1 review) and live hosting (cloud vs home PC, decide at Phase 2).

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
├── engine/         # backtesting, cost/tax models, metrics, simulation (Phase 1)
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
