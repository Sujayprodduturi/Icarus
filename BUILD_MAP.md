# Project Icarus — Build Map & Doc Review

> Companion reference to `PRD.md`, `TASKS.md`, `CLAUDE.md`. Reviewed & compiled 24 Jul 2026.
> A one-file map of what Claude Code is about to build, the operating cost of running it, and the open decisions.

**Verdict:** The docs are genuinely excellent — top ~5% of solo trading specs — and **build-ready**. But *build-ready ≠ profitable*. There is one issue (C1) that could quietly stall the self-learning premise, and a short fix list below. Current direction: **equity-delivery-first** (crypto deferred).

---

## 1. Architecture — two planes, one bridge

**ORCHESTRATOR (conductor)** — owns the tick, the state machine `PRE_OPEN → AUTH → RECOVERY → TRADING → POST_CLOSE → RESEARCH → SLEEP`, the message bus (Valkey Streams), health/heartbeats, and the global kill-line. Equity and crypto run on independent state machines (crypto never sleeps — deferred for now).

### Execution plane — *fast · dumb · safe* (trades only promoted strategies)

| # | Agent | Job | Broker creds |
|---|---|---|---|
| 1 | **Data Ingestion** | WebSocket + REST feeds → canonical `MarketData`; schema drift → halt feed | read-only |
| 2 | **Regime Detection** | trend / range / high-vol classifier; gates which strategy families may fire | — |
| 3 | **Signal Generation** | runs promoted strategies; pure functions → `TradeIntent`. No I/O, no orders | — |
| 4 | **Risk Management** | sizes / vetoes; holds the hard limits no strategy can override | — |
| 5 | **Execution** | the **only** component that talks to money — LIMIT+protection, algo-tagged | **WRITE** |
| 6 | **Portfolio** | source of truth for positions/P&L; reconciles vs broker every cycle | read-only |

### Research plane — *slow · smart · sandboxed* (NO broker creds, NO network path to any broker)

| # | Agent | Job |
|---|---|---|
| 7 | **News / Sentiment** | LLM-scored headlines & filings; **data only**, can veto but never originate an order |
| 8 | **Macro / Context** | RBI calendar, VIX, USDINR, funding/OI → slow `MacroContext` |
| 9 | **Research / Inventor** | the brain — invents/tunes strategies within the DSL; one change per cycle |
| 10 | **Validation / Gate** | 7-stage numeric gate; the **only** path a strategy reaches live capital |

### Cross-cutting

| # | Agent | Job |
|---|---|---|
| 11 | **Compliance / Guardrail** | order-rate governor (≤2 OPS) · static-IP assert · LIMIT-only assert · white-box assert · can globally HALT Execution |
| 12 | **Oversight / Reporting** | Telegram daily brief · manual `kill` + `rollback` · runs as a **separate process** so the kill outlives the orchestrator |

**The bridge:** the two planes cross **only** through the versioned **Strategy Registry**, and **only** when the Validation gate stamps a strategy `PROMOTED`. A bug or bad idea in the research plane cannot, by construction, reach live money except through the numeric gate.

---

## 2. The sub-agent mesh — each agent is a supervisor

| Domain agent | Task sub-agents (one job each, independently restartable) |
|---|---|
| **Data** | one feed sub-agent per (venue, data-type) · **Data-QA** (bad-tick/stale/calendar) · Historical-loader (PIT cache) |
| **Regime** | per-instrument classifier sub-agents (parallel) |
| **Signal** | one sub-agent per (promoted strategy × instrument) — pure functions, massively parallel |
| **Risk** | sizing · limit-check · allocation/arbitration · **quality-gate** — run as one serialized critical section |
| **Execution** | per-venue order-lifecycle · smart-limit-placement · reconciliation |
| **Portfolio** | P&L · equity/heat · broker-reconcile |
| **News/Sentiment** | one source sub-agent per feed · Haiku scoring (batched) · injection-filter (quote-and-flag) |
| **Macro** | Calendar/Sessions (NSE holidays + expiry registry) · macro-prints · funding/OI |
| **Inventor** | diagnosis · hypothesis (LLM) · DSL-mutation · candidate-sanity (white-box check) |
| **Validation** | one sub-agent per gate stage (in-sample → walk-forward → cost/tax → overfitting → sim → canary), pipeline |
| **Compliance** | rate-governor · static-IP · white-box-assert · calendar/blackout |
| **Oversight** | daily-report · **alerting (separate process)** · command (kill/rollback) |

---

## 3. How strategies & trades flow

### Flow A — how a strategy is born and reaches live money (the self-learning loop)

```
Inventor (every N closed trades, one change)
  → StrategyCandidate (typed DSL object, white-box)
  → 7-stage gate: in-sample → walk-forward OOS → cost/tax stress → DSR/overfitting → sim → micro-live canary → promote
  → Strategy Registry (versioned, PROMOTED)
  → Signal agent picks it up, goes live
```

Demotion runs continuously in reverse: a live strategy whose rolling metrics decay is auto-demoted and rolled back to last-good.

### Flow B — how one live trade gets placed (the execution loop, per bar)

```
Data → Regime → Signal (rules fire → TradeIntent)
  → Risk (quality-score · size = min(¼–½ Kelly, 0.5%, tier cap, 2% heat) · cost-hurdle · veto?)
  → Compliance (≤2 OPS · static-IP · LIMIT-only)
  → Execution (LIMIT+protection · algo-tag · exactly-once client_order_id · bracket/stop)
  → Portfolio (reconcile vs broker · audit log)
```

**Guardrails wrapping every trade:** touch ≠ fill in sim · next-bar execution · net of cost + tax · hard 2× crypto leverage ceiling · RECOVERY-before-TRADING on every startup.

**Seed tier (equity-first):** equity delivery is the live surface (₹0 brokerage, no leverage, settled tax) · index F&O = simulation only (margin-impossible) · crypto = deferred until equity proves the machine.

---

## 4. The build sequence (Claude Code follows `TASKS.md` in order)

| Phase | What | Needs capital? |
|---|---|---|
| **0** | Skeleton & safety rails — bus, Postgres, BrokerAdapter, Compliance, kill-line. Authenticates, streams data, **can place nothing**. | No |
| **1** | Data + sim + metrics — CostModel + TaxModel, walk-forward backtester, metrics + DSR, testnet/sim runner. | No |
| 🛑 | **PHASE-1 STOP GATE** — produce a metric sheet for ONE hand-written strategy, hand to operator, **pause**. No live-order code before this review. | — |
| **2** | Live execution — Risk + Execution + Portfolio + all kill-switches + Telegram kill. Micro-live, real money, tiny. Does **not** self-modify yet. | **Yes — first capital + static IP here** |
| **3** | Learning loop — Inventor + gate wired end-to-end. Versioning + hypothesis meta-learning. | Yes |
| **4** | Oversight + harden — full daily report, rollback, reconciliation hardening, chaos tests, tax-ledger export. | Yes |
| **5** | Scale — only on live evidence. Widen universe, raise tiers, expand primitives. **Leverage cap never loosens.** | Yes |

---

## 5. Operating cost — running the machine (separate from brokerage / STT / taxes)

Three buckets: **infrastructure, the data-API subscription, and the LLM/agent calls.** Everything else (Upstox data, news RSS, macro feeds, Telegram) is free.

| Component | For | Monthly cost |
|---|---|---|
| AWS EC2 `t4g.small` | the always-on VM (agents + Postgres + Valkey) | ~$12.3 (~₹1,080) |
| Elastic IP (1 public IPv4) | SEBI-mandated static IP for order placement | ~$3.65 (~₹320) |
| S3 backups + Secrets Manager | off-box backups, key storage (or free with SOPS) | ~₹100–200 |
| **Zerodha Kite Connect** | live WebSocket + historical data (orders free on Personal tier) | **₹500 fixed** |
| **Anthropic API (LLM)** | Inventor (Sonnet/Opus) + sentiment (Haiku, batched+cached) | **~₹500–1,500 realistic** · hard cap ₹6,000 (`max_llm_spend_per_day_inr: 200`) |

- **Realistic all-in, live: ~₹2,500–3,500/month.** Hard ceiling ~₹8,000/mo only if the LLM budget runs flat-out.
- **Phases 0–1 (build/backtest, no live orders): ~₹700–1,200/month** — just Kite ₹500 + a little LLM. The ~₹1,400 AWS layer only switches on at Phase 2, the same moment the seed capital does.

**The hard truth:** this cost is *fixed, independent of your capital or trade size.* At a ₹25–30k seed, ~₹3,000/mo is 10–12% of the whole account every month before a single trade; at ₹2–3k it's economically absurd. **The system cannot out-earn its own hosting bill at seed scale** — the operating cost is part of the tuition, not a profit centre.

### Model routing (control the biggest variable cost)

| Task | Model | Why |
|---|---|---|
| Sentiment scoring | **Haiku 4.5** ($1/$5) | high-volume, simple → cheapest, batched + cached |
| Mechanical sub-tasks (candidate-sanity, diagnosis, injection-filter) | **Haiku 4.5** | no deep reasoning needed → cheapest |
| Inventor hypothesis / mutation | **Sonnet 4.6** ($3/$15) default | the reasoning workhorse |
| Hardest strategy synthesis (rare) | **Opus 4.8** ($5/$25) | only when Sonnet isn't enough |
| ~~Fable 5~~ | **skip** | Fable 5 is the *frontier/most-expensive* tier ($10/$50, ~2× Opus) for brutal long-running coding/research — the opposite of Icarus's routine calls. Not needed. |

**Throttle the Inventor cadence at seed:** the Inventor reflects every `reflection_every_trades` closed trades (locked at 15 at seed) — each cycle spends Sonnet/Opus tokens. At seed with few trades, 5-trade windows are statistical noise, so frequent reflection burns money chasing randomness. **Locked at `reflection_every_trades: 15`** (per-strategy) at seed: cuts Inventor cycles to ~⅓ (LLM saving) and gives a steadier read than a 5-trade window. Note 15 still isn't statistically significant — the gate needs ≥30 OOS trades — so it's a pragmatic middle, tunable down later as trade volume grows.

### Hosting option: home PC instead of the AWS VM

Viable — **especially now that we're equity-first**, because the live plane only needs to run during NSE hours (9:15 AM–3:30 PM IST), not 24/7.

- **Phases 0–1:** a home PC is ideal and **free** — no static IP needed (data endpoints are IP-exempt), no 24/7 requirement. Do all build + backtest here.
- **Phase 2 (live):** the one hard requirement is a **static IP registered with the broker**. Home broadband is usually *dynamic*. Fix: buy a **static-IP add-on from your ISP** (~₹200–500/mo on ACT/Airtel/Jio business plans), register it with Zerodha. That replaces ~₹1,400/mo of AWS with ~₹200–500/mo.
- **Requirements & risks:** the PC needs ~4 GiB+ RAM and Linux (or WSL2); it holds broker **write credentials** → lock it down (disk encryption, dedicated box, not the daily-driver). Mitigate power/internet drops with a UPS + mobile-hotspot failover, and rely on **broker-side protective stops (GTT/bracket)** so an open position is safe even if the PC dies mid-session (the PRD already requires this).
- **Decision timing:** this is a Phase-2 choice, not now. Build on the PC free through Phase 1; decide the live-hosting question at the stop gate.

---

## 6. Enhancement register (status as of 24 Jul 2026)

| ID | Sev | Finding | Status |
|---|---|---|---|
| **C1** | CRITICAL | Seed-tier order math may never produce a placeable trade → system idles, never hits the ≥30 live trades needed to learn/tier-up. Equity at ₹2–3k fails hardest (share-price lumps + ₹15.34 DP charge). | **HELD** — pending seed decision (Claude: ~₹25–30k floor for equity delivery) |
| **H1** | HIGH | Banned `liquid_lowprice_nse` universe still in §20 example strategy.yaml (§29.2 bans it). | ✅ **APPLIED** → `liquid_largecap_nse` |
| **H3** | HIGH | Delta cancel-on-disconnect is load-bearing for the 24/7 crypto plane but only "verify at build". | **HELD** — deferred with crypto; make it a hard Phase-2 gate when crypto is enabled |
| **M1** | MED | §9.5 state-machine diagram omitted RECOVERY (invariant #16 requires it). | ✅ **APPLIED** |
| **M2** | MED | No explicit pytest/CI scaffold task in Phase 0. | ✅ **APPLIED** → TASKS 0.1b |
| **M3** | MED | Reflection cadence (N=5) vs belief threshold (≥30 trades) mismatch → early reflection chases noise. | ✅ **RESOLVED** — `reflection_every_trades` locked at 15 (per-strategy) at seed |
| **M4** | MED | Time-to-first-evidence is months and isn't stated. | Open — set expectation in PRD |
| **M5** | LOW | 2 GiB VM may OOM on walk-forward/CPCV backtests. | Open — benchmark memory in Phase 1 (moot if home PC has more RAM) |
| **D1** | DECISION | Crypto-first was a single point of fragility (contested tax + leverage + only viable seed surface). | ✅ **DECIDED: equity-first**, crypto deferred (revises locked decisions #5/#6) |
| **D2** | DECISION | 12-agent × sub-agent mesh is heavier than ≤2 OPS justifies. | Open — keep plane isolation + single writer; consider leaner Phases 0–2, defer full mesh |

---

## 7. Current decisions & open items

- ✅ **Equity-delivery-first** to prove the machine; crypto stays in the architecture but deferred (Sujay, 24 Jul).
- ⏳ **Seed number — OPEN.** Sujay leaned ₹2–3k; Claude flagged that won't place cost-clearing equity trades (cold-start trap) and recommends **~₹25–30k** as the Phase-2 seed floor. Phases 0–1 need no capital, so this doesn't block the build — resolve it at the Phase-1 stop gate.
- ⏳ **Hosting — OPEN.** AWS VM (~₹1,400/mo) vs home PC + ISP static IP (~₹200–500/mo). Equity-first makes the home PC viable (no 24/7). Decide at Phase 2.
- ⏳ Once seed + hosting are set: apply C1 + H3 + the equity-first rewrite of §2/§5/§22 + locked decisions #5/#6 in one clean pass.

*Docs: `PRD.md` (v2.0, 1079 lines) · `TASKS.md` (phased, incl. 0.1b) · `CLAUDE.md` (22 invariants) · `goal.yaml` (all thresholds). Build map compiled 24 Jul 2026.*
