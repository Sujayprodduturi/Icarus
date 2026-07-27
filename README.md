# Project Icarus

A multi-agent, self-learning, fully-autonomous trading system for the Indian market (equities + INR-settled crypto derivatives), built under SEBI rules. **Safety first, edge second.** When unsure, it halts rather than trades.

> **This is not financial advice.** Even a well-built version of this is more likely to slowly lose money than to compound. Treat the seed capital as tuition. See `PRD.md` and `CLAUDE.md` §0.

**Authoritative docs:** `PRD.md` (v2.0 — Part II §27–§39 wins where it extends Part I) · `TASKS.md` (phased checklist) · `CLAUDE.md` (22 safety invariants — never violated) · `BUILD_MAP.md` (decision register).

---

## Current status — Phase 0 (Skeleton & safety rails)

**Goal:** the system authenticates, streams data, and **can place nothing.** No live-order code exists before Phase 2, and the operator reviews the Phase-1 metric sheet before Phase 2 begins.

Build order is mandatory: **0 → 1 → 🛑 stop gate → 2 → 3**. Do not skip ahead.

---

## Developer setup (dev machine)

Requires **Python 3.12** and **[uv](https://docs.astral.sh/uv/)**. Datastores run in Docker.

```bash
uv sync --extra dev          # create .venv + install deps
cp .env.example .env         # fill in as creds become available
docker compose -f deploy/compose.yaml up -d    # Postgres 16 + Valkey 8 (needs Docker Desktop)

uv run ruff check .          # lint
uv run ruff format --check . # format
uv run mypy                  # types (strict)
uv run pytest                # tests
```

The four-command gate (ruff → format → mypy → pytest) is exactly what CI runs and what the Hermes deploy PC must pass before reporting success.

---

## Deployment (Hermes / second PC)

Code moves to the Linux deploy PC via a **private GitHub repo**; secrets never travel (only `.env.example`). The Hermes agent follows **`deploy/HERMES.md`** — a runbook written for an agent, with a verification checklist it must pass. Infra/SPOF runbook: `deploy/infra-notes.md`.

---

## Operator action items (PRD §24) — the system cannot do these for itself

Each item notes the phase it blocks. Phases 0–1 need **no capital and no static IP**.

| # | Item | Blocks |
|---|------|--------|
| **O1** | **Zerodha** Kite Connect ₹500/mo plan active *(done)*; register the deploy host's static IP in `developers.kite.trade`. | Phase 2 (equity live) |
| **O2** | **Upstox** account + API app (free data API); whitelist the host IP; confirm post-31-Mar-2026 order pricing. | Phase 4 failover (data usable earlier) |
| **O3** | **Delta Exchange India** account + API keys + **testnet**; whitelist IP; **disable withdrawals** on the trading key. | Phase 1 crypto sim / Phase 2 crypto live |
| **O4** | **Host + static IP** (AWS Elastic IP *or* ISP static-IP add-on for the home PC); lock inbound to operator SSH; register that one IP with every venue. | Phase 2 |
| **O5** | **Daily-auth approach** — operator one-tap (default) vs TOTP automation (own risk). | Phase 2 |
| **O6** | **CA confirmation** of INR-settled crypto-derivative tax treatment (contested — PRD §6). | Scaling the crypto leg |

**Also:** F&O stays simulation-only until capital genuinely supports ≥1–2 lots. Do not distribute Icarus beyond self + immediate family (PRD §1).

### Open decisions (do not block Phases 0–1)
- **Seed capital** — leaning small; the docs argue ~₹25–30k is the floor that clears equity-delivery costs. Resolve at the Phase-1 stop gate (BUILD_MAP C1).
- **Live hosting** — AWS VM vs home PC + ISP static IP. Decide at Phase 2.

---

## Repository layout

See `PRD.md` §20. Two planes joined by one bridge (the versioned Strategy Registry), crossed only when the numeric Validation gate stamps `PROMOTED`.

- `icarus/orchestrator/` — clock, state machine, supervision, kill-line
- `icarus/bus/` — Valkey Streams (durable: consumer groups, DLQ, backpressure)
- `icarus/agents/` — the 12 domain agents (data, regime, signal, risk, execution, portfolio, news_sentiment, macro, research, validation, compliance, oversight)
- `icarus/brokers/` — `BrokerAdapter` protocol + Zerodha / Upstox / Delta India adapters
- `icarus/strategy/` — DSL, registry, promoted-strategy YAMLs
- `icarus/engine/` — backtest, metrics, cost/tax models, sim (Phase 1)
- `icarus/state/` — Postgres models + Alembic
- `icarus/common/` — schemas, types, logging, secrets
- `tests/` — unit (happy **and** halt paths) + golden backtest regression
