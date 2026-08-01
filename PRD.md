# Project Icarus — Product Requirements Document (PRD)
### A multi-agent, self-learning, fully-autonomous trading system for the Indian market

**Audience:** Claude Code (implementation agent) · **Operator:** Sujay · **Backend:** Python · **PRD compiled:** 23 June 2026 · **Version: 2.0 (hardened)**
**Companion files:** `CLAUDE.md` (engineering conventions + safety invariants), `TASKS.md` (phase-by-phase build checklist with acceptance criteria)

---

> ## 🔁 v2.0 — read this before building
> Sections 1–26 (Part I) are the original architecture and remain correct. **Part II (§27–§39) is the v2 hardening layer and is authoritative where it extends or supersedes Part I.** It closes the expensive-to-retrofit gaps found in two adversarial reviews (quant/backtest-rigor and agentic/autonomy/ops): LIMIT-order **fill modeling**, **point-in-time/survivorship** data integrity, **corporate-action** handling, **next-bar** execution (no look-ahead), **overfitting-at-scale** accounting, **benchmark/edge-vs-beta**, a concrete **trade-quality** definition, **crypto-derivative economics** (funding/roll/expiry), the **strategy lifecycle + capital allocation across strategies**, **crash recovery + exactly-once orders**, **kill-switch independence**, **resilience/observability**, the **daily-auth autonomy** model, and the **decision-rights ladder**. Where a number changes, the consolidated **`goal.yaml` v2 block in §39** wins over §15.

---

> ## ⚠️ Read this first — scope, risk, and how to use this PRD
>
> **This is a specification, not running code.** It is opinionated on purpose. `MUST` = a hard constraint that protects real money or legal standing — never silently weaken it. `SHOULD` = a strong default you may revisit with reason. Every number in a config block is a **starting value the operator tunes**, not a law of physics.
>
> **This is not financial advice.** Icarus is an engineering system. Most retail algorithmic traders lose money; self-modifying strategies are *especially* prone to overfitting and silent decay. The honest expectation, stated plainly so it shapes the design: **even a well-built version of this is more likely to slowly lose money than to compound.** The design's job is to make losses *small, legible, and survivable* while giving a rare real edge a chance to prove itself on evidence. **Treat the seed capital as tuition.**
>
> **The tax and regulatory positions here are research-grade, current as of June 2026, and some are explicitly contested (see §6, §9, Appendix B).** Confirm them with a CA and re-check SEBI/exchange circulars before scaling real money. Where this PRD updates the original blueprint with newer facts, those updates win.
>
> **Build order is mandatory.** Build Phases 0 → 1 → 2 → 3 in sequence. **Stop at the end of Phase 1 and produce a metric sheet for one hand-written strategy before any live order path is enabled.** No code path may place a live order until Phase 2, and the operator must review Phase-1 evidence first. See `TASKS.md`.

---

## Table of contents
1. Product vision, goals, and non-goals
2. Operator profile & operating model
3. The three findings (re-verified June 2026)
4. Locked decisions (requirements recap)
5. What Icarus trades (by capital tier)
6. Tax-aware design (decides what's worth trading)
7. Cost model (concrete current rates)
8. Regulatory compliance — SEBI (compliance by design)
9. System architecture — the multi-agent mesh
10. Agent roster & message contracts
11. BrokerAdapter contract + venues
12. The self-learning engine (invention + mutation)
13. The validation gate + metrics battery + overfitting guards
14. Risk guardrails & kill-switches — **the risk decision + rationale**
15. `goal.yaml` — the single source of truth
16. Capital-scaling ladder
17. Data, news & inputs (and TradingView's real role)
18. Hosting & deployment (AWS Mumbai)
19. Security, secrets & audit
20. Project structure & key configs
21. Tech stack (concrete, version-checked)
22. Phased roadmap (deep through Phase 3)
23. Failure modes (devil's advocate)
24. Operator action items (setup before live)
25. Appendix A — research sources & as-of dates
26. Appendix B — facts to re-verify before live

---

## 1. Product vision, goals, and non-goals

**Vision.** A single-operator, fully-autonomous trading system for Indian equities and INR-settled crypto derivatives that *learns* — it both tunes existing strategies and invents new ones — while remaining white-box, low-frequency, SEBI-compliant, and incapable (by construction) of letting an unvetted idea touch real money. Capital scales only on proven live evidence. The operator reviews it once a day.

**Primary goals.**
- **Safety first, edge second.** Every architectural choice favours capital preservation, legibility, and survivability over return.
- **Self-improvement on evidence, never optimism.** New/changed strategies reach live money *only* through an automated numeric validation gate.
- **Autonomy that survives 24h unattended.** Aggressive, layered kill-switches; fail-safe-to-halt defaults.
- **After-cost, after-tax optimization.** At seed capital, costs and taxes — not the market — are the dominant adversary, so they live *inside* the decision and the backtest, not as an afterthought.
- **Regulatory and legal cleanliness.** White-box, low-frequency, self-use, static-IP, properly tagged.

**Non-goals (explicitly out of scope).**
- ❌ No human-in-the-loop trade approval (autonomy is a locked decision).
- ❌ No distribution: Icarus is **self + immediate-family use only**. Selling/renting/sharing it pulls the operator into algo-provider empanelment and (for undisclosed logic) Research-Analyst registration. Do not build multi-tenant features.
- ❌ No black-box strategies. Every promoted strategy MUST be explainable rule-by-rule.
- ❌ No high-frequency anything. The system is architected *under* 10 orders/second by a wide margin.
- ❌ No spot crypto, no USDT-settled crypto derivatives (tax — see §6).
- ❌ No money-movement capability. The system can trade; it can never withdraw or transfer funds.
- ❌ No trading *through* a TradingView account (that capability does not exist — see §17).

---

## 2. Operator profile & operating model

| Attribute | Value | Design implication |
|---|---|---|
| Operators | 1 (Sujay) + permitted immediate family | Single-tenant; no RBAC/multi-user. |
| Oversight cadence | **Once per day** | Kill-switches must survive ~24h unattended; crypto plane runs 24/7. |
| Trade approval | **None — fully autonomous** | All gating is automated and numeric. |
| Starting capital | **₹1,000–10,000 (seed tier)** | Costs dominate; cost-hurdle gate + min-notional rules are load-bearing. |
| First live focus | **Equities + crypto in parallel** | Both execution paths built behind one `BrokerAdapter` from Phase 2. |
| Reporting/control | **Telegram bot** | Daily brief + interactive manual kill/rollback. |
| Equity broker | **Zerodha Kite Connect (paid plan + key already provisioned)** | Primary execution venue from Phase 2. |
| Failover broker | **Upstox** (to be provisioned) | Hot failover + free backup data feed. |
| Crypto venue | **Delta Exchange India** (to be provisioned) | INR-settled BTC/ETH derivatives only; testnet for sim. |
| Hosting | **AWS Mumbai (ap-south-1)** VM + Elastic IP (to be provisioned) | Dedicated static IPv4 for broker whitelist. |

**What the operator still needs to set up** (the PRD includes these as steps — see §24): Upstox account + API, Delta Exchange India account + API + testnet, the AWS VM + Elastic IP, static-IP registration with each venue, and a CA conversation about crypto-derivative tax classification before the crypto leg scales.

---

## 3. The three findings (re-verified June 2026)

The operator began from a reference design (a single "Hermes" loop on Railway, with paper-trading as a mode you sit in). Three India-specific facts break or reshape that design. **All three re-verified as of June 2026 and still hold; details sharpened below.**

### Finding 1 — Railway cannot host this; a VM with a dedicated static IPv4 is mandatory.
SEBI's framework (fully mandatory **1 April 2026**) requires API orders to originate from a **static IP registered with the broker**. Railway offers only *shared* static egress IPs even on Pro/Enterprise — a shared-ban risk and a trust problem. **Icarus MUST run on a cloud VM with a dedicated reserved/elastic static IPv4** (§18). *Update:* an AWS **Elastic IP is a dedicated static IPv4**; note that since 2024 **all** public IPv4 addresses cost ~$0.005/hr (~₹350/mo) whether attached or idle — budget it.

### Finding 2 — The crypto tax "exit" exists but is now *contested*, not safe-by-default.
Spot crypto in India is taxed at a flat **30% + cess, 1% TDS, no loss offset, no carry-forward** (§115BBH/§194S) — brutal, usually enough to kill an algo's edge. The blueprint's escape was that **INR-settled crypto derivatives on Delta India are treated as speculative business income** (slab rate, loss offset against speculative income, 4-year carry-forward, no per-trade TDS).
**⚠️ Re-verification result (important):** this favourable treatment is a **common interpretation, NOT settled law.** There is no statute provision, CBDT circular, or case law directly on point; the **CBDT has actively solicited stakeholder feedback specifically on crypto derivatives**, and the **Finance Act 2025 broadened the VDA definition (effective 1 Apr 2026)**, which *increases* the risk the department later reclassifies these as VDAs at 30%. The design still trades **only INR-settled Delta India derivatives** (never spot, never USDT-settled), but §6 flags this as a real, CA-confirm-before-you-scale risk and the `TaxModel` MUST support a "conservative 30%" reclassification scenario for stress-testing.

### Finding 3 — Zerodha primary, Upstox hot failover (operator's locked choice).
On pure cost/testability, research favours Upstox (free data API; has a sandbox). The operator has chosen **Zerodha primary** — sound on different axes: `kiteconnect` is the most mature library + community with a strong reliability record. The design absorbs Zerodha's two tradeoffs rather than wishing them away:
- **₹500/month Kite Connect plan is required** (the free "Personal" tier places orders but gives **no market data**). The `CostModel` amortizes this fixed cost into per-strategy hurdle rates. *(Confirmed current.)*
- **No broker sandbox.** Icarus does not depend on one: the validation gate's **internal simulated-fill engine** (`engine/sim.py`) forward-runs against live Zerodha *data* with modeled fills/slippage, and the **micro-live canary** is the first time real Zerodha orders fire. This makes the canary stage *more* important under Zerodha — keep canary size minimal and reconciliation strict.
Keep **Upstox behind the same `BrokerAdapter`** as hot failover; its free data API doubles as a **zero-cost backup market-data feed** if Zerodha's stream drops. *Update:* the Kite static-IP requirement applies **only to order placement** — data endpoints work from any IP, which is convenient for the failover/data-only path.

---

## 4. Locked decisions (requirements recap)

| # | Decision | Implication |
|---|----------|-------------|
| 1 | Fully autonomous; **no human-in-the-loop** for trades | All gating automated + numeric. |
| 2 | **Multi-agent** architecture; one job per agent | §9. Orchestrator + specialist agents + message bus. |
| 3 | Self-learning may **tune AND invent** strategy logic | §12, inside a hard sandbox + validation gate. |
| 4 | **Simulation retained — as an autonomous promotion gate** | §13. No manual "paper mode." |
| 5 | **Crypto included** | Delta India, INR-settled derivatives only (§6). |
| 6 | **Capital scales** from ₹1k–10k on proven results | Sizing is % of equity; tiers unlock (asset, mode) pairs (§16). |
| 7 | **Once-a-day** operator oversight | Aggressive kill-switches (§14). |
| 8 | Every strategy must satisfy **Sharpe / R:R / quality metrics** | The metrics gate (§13). |
| 9 | **Python backend** | Stack in §21. |
| 10 | Deliverable scope: **build-ready through Phase 3** | Phases 4–5 at requirements level (§22). |

---

## 5. What Icarus trades (by capital tier)

Hard reality of tiny capital: **index F&O is mathematically out of reach** at ₹1k–10k (one Nifty options lot = tens of thousands in margin; one futures lot = lakhs in notional). And at ₹10k, equity cash positions are so small that **per-order costs and statutory charges can exceed any realistic edge.**

| Capital tier | Equities (cash) | Index F&O | Crypto (Delta INR-settled) |
|---|---|---|---|
| **₹1k–10k (seed)** | **Live, but tiny & cost-aware** — only strategies that survive a 1.5× cost-stress test (§13). Few, liquid names; **prefer delivery over intraday** (delivery brokerage = ₹0; intraday = ₹20/order, which dominates at this size). | **Simulation only** (margin-impossible) | **Live, micro size, effective leverage 1× at seed tier** (see §14); 24/7 market = more learning at-bats |
| **₹10k–1L** | Live, broader universe | **Simulation only** until ≥2 lots affordable with risk headroom | Live, conservative leverage (≤2× hard ceiling) |
| **₹1L–5L** | Live, primary engine | **Cautious live** — single lot, defined-risk option spreads, never naked short options | Live |
| **₹5L+** | Full | Live within risk budget | Live |

**Design implication.** The same strategy object runs in `sim` or `live` mode via a flag; the **Capital-Tier policy** (§16) decides which (asset, mode) pairs are eligible at the current equity. **At seed capital, crypto micro-trades are the realistic live learning surface; most equity trades will be (correctly) rejected by the cost-hurdle gate until capital grows; F&O is a simulator the agent learns in but cannot yet act on.** This is expected and correct behaviour — the system simply won't trade what it can't afford to trade profitably.

---

## 6. Tax-aware design (decides what's worth trading)

Tax is not an afterthought; at small capital it decides whether an edge survives. Bake a **`TaxModel`** into scoring so the agent optimizes **after-tax, after-cost** returns, not gross. The `TaxModel` MUST be applied inside backtests *and* inside the live decision.

### 6.1 Equities
Normal capital-gains / business-income treatment depending on classification; STT, exchange charges, GST, stamp duty, SEBI fee, DP charges, and brokerage all apply (concrete rates in §7). At ₹1k–10k these are *brutal* in percentage terms.
- **Intraday equity** = speculative business income (slab rate; losses offset only speculative gains; 4-yr carry-forward). *(Settled law.)*
- **Equity delivery / short-term** = capital gains or business income by classification.
- **Equity/index F&O** = **non-speculative** business income (slab; losses offset any income except salary; **8-yr** carry-forward) — because of the §43(5) "recognised stock exchange" carve-out. *(Settled law.)*

### 6.2 Crypto — the decisive (and contested) distinction

| Product | Tax treatment | Loss offset? | TDS? | Certainty | Verdict |
|---|---|---|---|---|---|
| **Spot** (buy/hold/sell BTC etc.) | Flat **30%** + cess (§115BBH) | **None** | **1%/sell** (§194S) | **Settled law** | **Avoid** — kills the edge |
| **USDT-settled futures** | Treated as VDA → **30%** (conservative majority view) | None | On conversion | **Uncertain, leans 30%** | **Avoid** |
| **INR-settled futures/options (Delta India)** | **Speculative business income → slab rate**; losses offset speculative income, **4-yr** carry-forward; **no per-trade TDS** | **Yes (speculative only)** | **No** | **⚠️ Common interpretation, NOT settled law** | **The crypto path — but confirm with a CA** |

**⚠️ The honest line (updated from the blueprint).** The favourable INR-settled treatment rests on a coherent statutory argument (a derivative isn't itself a VDA under §2(47A); cash settlement isn't a "transfer" of a VDA; crypto exchanges aren't "recognised stock exchanges" so the F&O non-speculative carve-out doesn't apply, leaving it *speculative* business income). **But:** no statute/CBDT/case law is directly on point; exchanges (Delta, CoinDCX) and most CA commentary promote this reading, yet **the CBDT itself has flagged crypto derivatives as an open question**, and the FY25 VDA-definition broadening *raises* reclassification risk. Even under the optimistic reading, crypto INR-settled derivatives are **speculative** business income — one notch *below* equity F&O (4-yr vs 8-yr carry-forward, speculative-only offset).

**Requirements for the `TaxModel`:**
- Default scenario: INR-settled crypto derivatives = speculative business income at a configurable slab rate (operator-set; default to a conservative mid-slab e.g. 30% effective marginal if unsure, so the gate isn't *flattered* by an optimistic low slab).
- **MUST** support a **reclassification stress scenario** (treat crypto-derivative P&L at flat 30% VDA, no offset) used in the cost+tax stress stage of the gate. A strategy that only survives under the optimistic tax reading is flagged.
- Equity intraday = speculative; delivery = per classification; F&O = non-speculative. Spot crypto = 30% (and the system never trades it anyway).
- The **audit log doubles as the tax ledger** (Schedule VDA / ITR-3 inputs); keep clean per-trade records from day one.

> **Operator action (important):** confirm the INR-settled-derivative classification with a CA before the crypto leg scales (§24). Maintain clean per-trade records from day one.

---

## 7. Cost model (concrete current rates — June 2026)

The `CostModel` (`engine/costmodel.py`) MUST compute the full round-trip cost per venue and feed it into both backtests and the live decision. **These rates changed recently — use the post-April-2026 numbers below, not older ones.**

### 7.1 Equity statutory charges & brokerage (Zerodha, NSE)

| Component | Rate (current, June 2026) | Notes |
|---|---|---|
| **STT — delivery** | 0.1% buy + 0.1% sell | Unchanged. |
| **STT — intraday** | 0.025% sell only | Unchanged. |
| **STT — equity futures** | **0.05% sell only** | ⚠️ **Raised 1 Apr 2026** (was 0.02%). |
| **STT — equity options** | **0.15% on premium, sell side** | ⚠️ **Raised 1 Apr 2026** (was 0.10%). |
| **Exchange txn charge (NSE cash)** | 0.00297% (raw) / **0.00307% all-in incl. NSE IPFT** | Decide one convention; don't double-count IPFT. |
| **SEBI turnover fee** | 0.0001% (₹10/crore) both sides | + 18% GST. |
| **GST** | 18% on (brokerage + txn charges + SEBI fee) | Not on STT or stamp duty. |
| **Stamp duty** | delivery 0.015%, intraday 0.003% (buy side only) | Uniform pan-India. |
| **DP charge (delivery sell)** | **₹15.34 per scrip per day** (₹3.5 CDSL + ₹9.5 Zerodha + GST) | Fixed-rupee → punishing on tiny delivery sells. |
| **Brokerage — delivery** | **₹0** | Makes delivery the cheapest equity path at seed tier. |
| **Brokerage — intraday & futures** | 0.03% or **₹20/order**, whichever lower | ₹20 floor dominates tiny positions. |
| **Brokerage — options** | flat **₹20/order** | |
| **Debit-balance penalty** | ₹40/order | Never place orders against insufficient margin. |
| **Kite Connect API** | **₹500/month** fixed | Amortize into per-strategy hurdle. |

### 7.2 Crypto (Delta India)
Trading + data API are free; model **maker/taker fees, funding (perps), and slippage** per contract from the live fee schedule (re-verify at build). No per-trade TDS on INR-settled derivatives (per the interpretation in §6). No STT/stamp/DP.

### 7.3 The cost-hurdle rule (MUST)
A trade is submitted **only if** expected edge (after modeled cost **and** tax) clears the round-trip cost with margin: `expected_net_edge ≥ cost_hurdle_multiplier × round_trip_cost` (default `cost_hurdle_multiplier = 1.5`). At seed tier this will reject most equity intraday trades — correct behaviour. Backtests re-run at **1.5× modeled cost** as a gate stage (§13).

---

## 8. Regulatory compliance — SEBI (compliance by design)

The SEBI "Safer participation of retail investors in algorithmic trading" framework (circular 4 Feb 2025) became **fully mandatory 1 April 2026** and is in force now. Implementation standards are in NSE circular INVG/67858 (5 May 2025) + NSE FAQ (3 Nov 2025). What matters for Icarus (all `MUST`):

- **Self-built algos for personal use are permitted** and may be used by immediate family (self, spouse, dependent children/parents) **only** — never third parties. Icarus is single-operator self-use → inside the allowed lane.
- **10 orders/second per exchange is the design ceiling.** Below it, no *full* per-algo exchange registration is required — but **API orders still require a generic algo-ID from the exchange (via the broker) and MUST be tagged.** Architect Icarus as low-frequency: a global **order-rate governor** (§11) hard-caps submission at **≤2 OPS** (target), well under 10.
- **Order tagging.** Every API order carries the broker/exchange-required algo identifier. For below-threshold self-built algos NSE uses a generic tag scheme (first 12 digits `444444444444`, 13th digit by route). The Execution agent MUST attach the correct tag to every order.
- **Static IP registered with the broker.** Orders originate only from the VM's registered static IP. (Data endpoints are exempt — relevant for failover/data feeds.)
- **OAuth-based auth + 2FA + daily session reset.** Tokens expire daily (Kite `access_token` expires ~6 AM next day, a regulatory requirement). The **daily-auth agent** (§11) re-authenticates cleanly before pre-open and asserts the egress IP equals the registered static IP.
- **No market orders via algo (NSE).** ⚠️ The Execution agent MUST use **LIMIT orders with marketable-limit protection**, never plain MARKET. (IOC/Market also barred in some segments.)
- **White-box only.** Every promoted strategy is explainable rule-by-rule. Black-box undisclosed logic triggers Research-Analyst registration — out of scope and prohibited here.
- **Exchange-side kill switch.** Exchanges can kill a rogue algo by algo-id. This is *in addition to* Icarus's own kill-switch — Zerodha has **no app-level kill switch**, so the manual kill MUST be enforced inside Icarus (§14).
- **Audit trail ≥ 5 years**, append-only (§19).

**The honest line on "AI that rewrites its own strategy":** nothing in the framework blesses or names "an LLM that invents and self-promotes strategies." Icarus stays compliant by staying **white-box, low-frequency, self-use, static-IP, properly tagged.** Self-rewriting happens in *your* code/config; what reaches the exchange is ordinary, explainable, rate-limited LIMIT orders from a registered retail API. Keep it that way.

---

## 9. System architecture — the multi-agent mesh

### 9.1 Two planes (the core safety idea)
- **Execution plane (fast, dumb, safe):** Data → Regime → Signal → Risk → Execution → Portfolio. Trades **only validated, promoted strategies.** Never improvises.
- **Research plane (slow, smart, sandboxed):** News/Sentiment + Macro + Research/Strategy-Inventor → Validation/Backtest gate → Strategy Registry. Invention and learning happen here, **walled off from live capital by the gate, with no broker credentials and no network path to brokers.**

Crossing between planes happens **only** through the **versioned Strategy Registry**, and **only** when the Validation agent stamps a strategy `PROMOTED`. Nothing the Inventor dreams up touches money without passing the gate. *This separation is the architecture's whole point* (§9.4).

### 9.2 Topology

```
                         ┌─────────────────────────────────────────┐
                         │         ORCHESTRATOR (conductor)         │
                         │  owns the tick, the state machine, the   │
                         │  message bus, health, and the kill-line  │
                         └───────────────┬─────────────────────────┘
                                         │  (async message bus: Redis/Valkey Streams or NATS)
   ┌──────────────┬───────────────┬──────┴───────┬───────────────┬────────────────┐
   │              │               │              │               │                │
┌──▼───┐    ┌─────▼─────┐   ┌──────▼─────┐  ┌─────▼──────┐  ┌─────▼─────┐   ┌──────▼──────┐
│DATA  │    │ REGIME    │   │ SIGNAL     │  │ RISK       │  │ EXECUTION │   │ PORTFOLIO   │
│agents│───▶│ agent     │──▶│ agents     │─▶│ agent      │─▶│ agent     │──▶│ agent       │
│(feeds)│   │(classify) │   │(per family)│  │(size, veto)│  │(broker IO)│   │(positions,  │
└──┬───┘    └───────────┘   └─────┬──────┘  └─────┬──────┘  └─────┬─────┘   │ live P&L)   │
   │                              │               │               │         └──────┬──────┘
   │   ┌──────────────────────────┴───────────────┴───────────────┴────────────────┘
   │   │
┌──▼───▼──────┐   ┌──────────────┐   ┌───────────────┐   ┌──────────────┐   ┌──────────────┐
│ NEWS/SENT.  │   │ RESEARCH /   │   │ VALIDATION /  │   │ COMPLIANCE / │   │ OVERSIGHT /  │
│ + MACRO     │   │ STRATEGY-    │   │ BACKTEST      │   │ GUARDRAIL    │   │ REPORTING    │
│ agents      │   │ INVENTOR     │   │ agent (gate)  │   │ agent        │   │ agent (TG)   │
└─────────────┘   └──────┬───────┘   └───────┬───────┘   └──────────────┘   └──────────────┘
                         └──────promote/demote┘
```

### 9.3 Coordination & state
- **Message bus:** Redis/Valkey **Streams** (simple, persistent, ordered) to start; NATS at scale. Every message is logged for audit + replay. *(Use **Valkey** — BSD-licensed Redis fork — or Redis 8 via `redis-py`; see §21 for the licensing note.)*
- **State store:** **Postgres** (positions, trades, strategy registry, hypotheses, metrics, audit) via SQLAlchemy + Alembic. Versioned strategy YAML history in git or object storage.
- **Orchestrator** owns: the master clock/tick; agent supervision + restart; the global state machine; and the **kill-line** every agent honours.

### 9.4 Why multi-agent (vs the single Hermes loop)
Separation of concerns = safety. The agent that *invents* has **no credentials and no path to the broker.** The agent that *places orders* has **no creativity** — it executes only what the gate approved and Risk sized. The agent that enforces *limits* is independent of both. A bug or bad idea in the creative plane cannot, by construction, reach live capital except through a numeric gate.

### 9.5 The Orchestrator state machine & master loop
States: `PRE_OPEN → AUTH → RECOVERY → TRADING → POST_CLOSE → RESEARCH → SLEEP`. (RECOVERY is mandatory before TRADING on every startup — three-way reconcile, default-to-halt; see §35.1 and CLAUDE invariant #16.)

```
PRE_OPEN  → daily auth (§11), reconcile positions, refresh universe, load promoted strategies
RECOVERY  → three-way reconcile (internal ↔ broker positions ↔ broker open orders); any
            unresolved drift ⇒ HALT + page; resume only if clean AND every open position
            has a broker-side protective stop (§35.1)
TRADING   → every tick/bar: Data → Regime → Signal → Risk → Execution → Portfolio
            (Compliance governs throughput; News/Macro feed continuously)
POST_CLOSE→ finalize fills, mark trades closed, update equity & metrics
RESEARCH  → if N trades closed since last cycle: Inventor → Validation gate → registry promote/demote
SLEEP     → idle until next session (the crypto plane stays in TRADING 24/7)
```
The crypto and equity planes run on **independent state machines** (crypto never sleeps; equities follow NSE hours). A single portfolio-level risk view spans both.

---

## 10. Agent roster & message contracts

Each agent is an independent async process/coroutine with a typed input/output contract. Implement as Python classes behind an `Agent` base with `async def handle(msg) -> list[Msg]`; deploy as supervised tasks under the Orchestrator. All messages carry `schema_version`, `ts`, and a correlation id for audit/replay.

**1. Data Ingestion agents** (one per feed: price, OHLCV, depth)
- *Job:* pull market data via broker/exchange WebSocket + REST; normalize to a canonical schema; publish `MarketData`. Retry 3× exp-backoff; on schema drift raise `SchemaError` and signal Orchestrator to halt that feed (fail safe, never silent).
- *Out:* `MarketData{symbol, ts, ohlcv, depth, schema_version}`

**2. News & Sentiment agent**
- *Job:* poll Indian financial news (RSS: Moneycontrol/ET/Mint/Business Standard; NSE/BSE announcements & filings), optional news APIs, and (crypto) funding/sentiment sources. Score relevance + directional sentiment per symbol with a Haiku-class LLM call (batched + prompt-cached, §21).
- *Out:* `SentimentSignal{symbol, score[-1,1], salience, sources[], ts}`
- *Guard:* news **informs** signals and can **veto** entries (e.g. pending result/halt), but never **originates** an order. LLM output is **data, never a command** (prompt-injection safety, §19).

**3. Macro / Context agent**
- *Job:* India macro calendar (RBI, CPI/IIP, budget), India VIX, global cues, USDINR, crypto funding/OI. Publishes a slow-moving `MacroContext`.
- *Out:* `MacroContext{vix, regime_hints, event_blackouts[], ts}`

**4. Regime Detection agent**
- *Job:* classify regime per instrument (trend-up / trend-down / range / high-vol / low-vol) from rolling returns, volatility, and `MacroContext`. Start with a transparent 20-day rolling-return + ATR/vol classifier; upgrade to HMM/Markov later (Phase 5). Regime tags gate which strategy families may fire.
- *Out:* `Regime{symbol, label, confidence, ts}`

**5. Signal Generation agents** (one per strategy *family*)
- *Job:* each instance runs **one promoted strategy** from the registry and emits entry/exit intents when its rules fire in a compatible regime. Pure functions of (MarketData, Regime, Sentiment, params). **No I/O, no order placement.**
- *Out:* `TradeIntent{strategy_id, symbol, side, entry, stop, target, conviction, regime, rationale}`

**6. Risk Management agent** (the veto layer — single most important live-plane agent)
- *Job:* take `TradeIntent`s and decide *whether and how much*. Position sizing (volatility-scaled, capital-tier-aware, fractional-Kelly-capped), per-trade risk cap, portfolio heat, correlation/exposure limits, daily-loss budget, leverage cap, event blackouts, **cost-hurdle check**. Can **shrink or veto** any intent. Owns the per-trade `R` (risk unit).
- *Out:* `SizedOrder{...}` or `Veto{intent, reason}`
- Holds **hard limits no other agent and no learned strategy can override** (§14).

**7. Execution agent** (broker/exchange I/O — the only agent that talks to money)
- *Job:* translate `SizedOrder` → broker call via `BrokerAdapter`; order lifecycle (place/modify/cancel), **LIMIT-by-default with marketable protection (never MARKET)**, bracket/stop attachment, fills, partial-fill handling, idempotency keys, **algo-ID tagging**. Subject to the global order-rate governor.
- *Out:* `OrderResult{...}`, `Fill{...}`
- **MUST be the only component with broker write credentials.**

**8. Portfolio agent**
- *Job:* single source of truth for open positions, realized/unrealized P&L, exposure, equity curve, cash. **Reconciles against broker truth every cycle** (drift → halt + alert). Feeds equity to the Capital-Tier policy and kill-switches.
- *Out:* `PortfolioState{positions[], equity, pnl, drawdown, exposure}`

**9. Research / Strategy-Inventor agent** (the brain of self-learning)
- *Job:* on a cadence (every N closed trades), read recent outcomes + current strategies + regime-tagged performance, then **tune** params or **invent** a new strategy as a typed object from the constrained DSL (§12). Forms explicit falsifiable hypotheses. **One change per cycle.** Never edits live strategies in place — writes *candidates* to the registry for the gate.
- *Out:* `StrategyCandidate{spec, hypothesis, predicted_metric_deltas, parent_version}`

**10. Validation / Backtest agent** (the autonomous gate)
- *Job:* run each candidate through the full pipeline of §13 and emit `PROMOTED` / `REJECTED` / `NEEDS_MORE_DATA` with the full metric sheet. **The only path to live.**
- *Out:* `ValidationVerdict{candidate, status, metrics, evidence}`

**11. Compliance / Guardrail agent** (cross-cutting policy enforcer)
- *Job:* enforce SEBI-shaped rules continuously: order-rate governor (≤2 OPS; under daily/min caps), static-IP assertion, market-hours/blackout windows, instrument eligibility, leverage caps, LIMIT-only assertion, "white-box only" assertion on any promoted strategy. Can globally **HALT** the Execution agent. Independent of strategy logic.
- *Out:* `PolicyDecision`, `HALT` broadcasts

**12. Oversight / Reporting agent** (the once-a-day window)
- *Job:* compile the daily brief (P&L, every trade + rationale, every strategy change with diff + hypothesis, current regime, drawdown vs limits, vetoes/halts, validation activity) and deliver via **Telegram bot**. Exposes the **manual kill switch** and **rollback** commands.
- *Out:* `DailyReport`; responds to operator Telegram commands.

---

## 11. BrokerAdapter contract + venues

### 11.1 The contract (broker-agnostic execution)
```python
class BrokerAdapter(Protocol):
    async def authenticate(self) -> Session                  # OAuth + 2FA + daily token
    async def stream_quotes(self, symbols) -> AsyncIterator[MarketData]
    async def historical(self, symbol, tf, frm, to) -> list[Candle]
    async def place(self, order: SizedOrder) -> OrderResult   # tags algo-ID, LIMIT+protection
    async def modify(self, order_id, **kw) -> OrderResult
    async def cancel(self, order_id) -> OrderResult
    async def positions(self) -> list[Position]
    async def funds(self) -> Funds
    async def kill_switch(self) -> None                       # broker-native where available
# Implementations: ZerodhaAdapter (primary), UpstoxAdapter (failover), DeltaIndiaAdapter (crypto)
```
**Never hard-couple to one broker.** All execution goes through this interface.

### 11.2 Zerodha Kite Connect (primary equities) — verified facts
- Library: **`kiteconnect`** on PyPI (the import is `kiteconnect`; the repo is `pykiteconnect`; *the PyPI name `pykiteconnect` 404s*). Actively maintained (v5.2.0, Apr 2026).
- Plan: **₹500/mo** unlocks WebSocket quotes + historical candles; free "Personal" tier = orders but no data.
- Rate limits: **10 req/s** general & order; **5000 orders/day**; **400 orders/min**; quote **1/s**; historical **3/s**. Max 25 modifications/order. Rejected/invalid orders **count** against limits — validate locally first.
- WebSocket: **3000 instruments/connection, up to 3 connections/key**; binary, modes ltp/quote/full.
- Auth: OAuth → daily `access_token` expiring ~6 AM next day (regulatory). **No officially-sanctioned fully-unattended token flow for retail**; plan for one daily token refresh (operator one-tap or TOTP automation at the operator's own risk). Static IP whitelisted in `developers.kite.trade` (order placement only).

### 11.3 Upstox (failover equities + free backup data feed) — verified facts
- SDK: **`upstox-python-sdk`** (import `upstox_client`), active (v2.27.x, May 2026).
- Data/historical/quote APIs **free**; **order API pricing post-31 Mar 2026 is unpublished** ⚠️ (the ₹10/order promo expired) — treat order pricing as TBD (failover is mainly for data + emergency).
- **Sandbox** exists but currently only for order endpoints (no market-data sandbox).
- Historical: daily/weekly/monthly back to **2000**; intraday (minute/hour) only back to **Jan 2022**. Use as a zero-cost bulk-backtest source so you don't hammer Zerodha's rate-limited historical endpoint.
- Native kill-switch / regulatory controls surfaced; verify the exact mechanism at build (Appendix B).

### 11.4 Delta Exchange India (crypto, INR-settled only) — verified facts
- Offers **INR-settled BTC/ETH futures + European options** (daily/weekly/monthly expiries) + perps.
- **Production base URL `https://api.india.delta.exchange`**; **testnet** `https://cdn-ind.testnet.deltaex.org` (site `testnet.delta.exchange`) for the sim stage.
- Client: official **`delta-rest-client`** (lightly maintained, ~1–2 releases/yr; v1.0.14, Apr 2026). **CCXT** supports it as exchange id **`deltaindia`** (distinct from global `delta`) — verify your pinned CCXT version exposes `ccxt.deltaindia`.
- Auth: HMAC-SHA256 over (method+timestamp+path+query+body); **signature valid only 5 s**; **IP whitelisting required**.
- **Native bracket orders** via `/v2/orders/bracket` (TP + SL, one fills cancels the other); stop-market/stop-limit/reduce-only supported; WebSocket public + private channels.
- **Leverage up to 100–200×** is available — **hard-cap at ≤2× in config + code + execution assert** (§14). The single biggest blow-up risk in the whole system.

### 11.5 Order-rate governor (compliance-critical)
A single global **token-bucket** in front of the Execution agent: hard ceiling **≤2 OPS** (well under SEBI 10 and broker caps), plus per-minute and per-day counters that trip a `HALT` *before* broker limits. Internal caps set conservatively below broker limits (e.g. ≤20/min, ≤200/day at seed tier — tripwires, not targets). **Invalid/rejected orders count** — validate every order locally before sending.

### 11.6 Daily-auth agent (SEBI session reset)
Before each session: perform OAuth + 2FA refresh, **assert egress IP == registered static IP**, then flip to `TRADING`. If auth fails, stay in a safe non-trading state and page the operator via Telegram. Design for a **single daily tap**, not a blocker. (Crypto uses HMAC keys, not daily OAuth, but still asserts IP whitelist.)

---

## 12. The self-learning engine (invention + mutation, safely)

### 12.1 Constrained strategy representation (not free-form code)
Strategies are **typed objects assembled from a vetted primitive library**, never raw Python the agent writes. Define a small **strategy DSL** (`strategy/dsl.py`):
- **Indicators/primitives:** RSI, EMA/SMA cross, ATR, Bollinger, breakout/retest, VWAP, regime filter, volume filter, funding-rate filter (crypto), news-veto, time-of-day filter.
- **Composition grammar:** `entry = AND/OR(conditions)`; `exit = stop | target | trailing | time | opposite-signal`; plus `position_size_r`, `stop_loss`, `regime_whitelist`.
- The Inventor composes/mutates **within this grammar.** Anything expressible is, by construction, white-box, explainable, and backtestable — satisfying SEBI's white-box requirement *and* safety.
- **The agent may NOT introduce a primitive that isn't in the vetted library** without a human adding it to the library first.

> Invention = search over the grammar (add/remove/swap a condition, change a primitive, recombine two parents). Mutation = tune a parameter. Both produce a `StrategyCandidate`; both go through the same gate.

### 12.2 The reflection cycle (every N closed trades; default N=15 at seed, counted per-strategy)
```
1. Pull last 25–50 closed trades + current strategy + regime tags + after-cost/after-tax P&L
2. Score against goal.yaml (§13 metric battery)
3. Diagnose: which regime/condition is bleeding? which is working?
4. Form 1–3 explicit hypotheses, each naming exactly ONE change + a predicted metric delta
5. Pick the highest-confidence hypothesis → emit StrategyCandidate (tune OR new grammar composition)
6. Hand to the Validation gate. NEVER edit a live strategy in place.
7. Log hypothesis + outcome to hypotheses.jsonl (so the agent learns which kinds of changes help)
```
**One-variable-change discipline** is enforced *structurally*: a candidate may differ from its parent in exactly one mutation; extra ideas queue as `pending_hypotheses`. This keeps causality legible and prevents thrashing.

### 12.3 Meta-learning
Persist every hypothesis → verdict → live outcome. Over time the Inventor biases its search toward *classes of change* that have historically passed the gate and improved live results. It compounds **evidence**, never unvalidated bets.

### 12.4 LLM usage (the Inventor & sentiment)
- **Inventor / hypothesis generation:** **Claude Sonnet 4.6** (`claude-sonnet-4-6`) as the cost-balanced default; **Opus 4.8** (`claude-opus-4-8`) for the hardest synthesis. Configurable in `goal.yaml`/env.
- **News sentiment scoring:** **Claude Haiku 4.5** (`claude-haiku-4-5`), using the **Batch API (50% off)** + **prompt caching (90% off reads)** for the fixed scoring rubric/universe.
- The LLM is an **idea/score source feeding the gate, never an executor.** Its outputs are parsed/validated as data; any text resembling an instruction is quoted-and-flagged, never acted on.

---

## 13. The validation gate + metrics battery + overfitting guards

**No strategy — invented or tuned — reaches live capital without clearing this gate.** It runs without the operator and is the autonomous replacement for "manual paper trading."

### 13.1 Promotion pipeline (each stage can reject)
```
StrategyCandidate
   ├─▶ 1. IN-SAMPLE BACKTEST         (fit window; sanity only)
   ├─▶ 2. WALK-FORWARD OUT-OF-SAMPLE (rolling; the real test on unseen data)
   ├─▶ 3. COST + TAX STRESS          (re-run at 1.5× costs + correct tax model + crypto-reclassification scenario)
   ├─▶ 4. OVERFITTING GUARDS         (DSR / multiple-testing correction — §13.3)
   ├─▶ 5. SIM / TESTNET FORWARD-RUN  (live data, simulated fills, min N days & ≥30 trades)
   ├─▶ 6. MICRO-LIVE CANARY          (smallest real size; confirms real fills/slippage)
   └─▶ 7. PROMOTE TO LIVE            (within current capital tier) → Registry: PROMOTED
```
**Demotion runs continuously in reverse:** a live strategy whose rolling metrics decay below the gate is auto-**demoted** (to sim or retired) and rolled back to the last good version.

### 13.2 Metrics battery (all on OUT-OF-SAMPLE data, net of cost + tax)

| Metric | Starting threshold | Why |
|---|---|---|
| **Trade count (OOS)** | ≥ 30 (prefer ≥ 50) | Statistical significance; below this, ignore other numbers. |
| **Sharpe (annualized)** | ≥ 1.0 (prefer ≥ 1.3) | Risk-adjusted return; the headline gate. |
| **Sortino** | ≥ 1.5 | Penalizes downside only. |
| **Calmar (CAGR ÷ maxDD)** | ≥ 1.0 | Return per unit of worst pain. |
| **Max drawdown** | ≤ `goal.max_drawdown` (8–10%) | Hard ceiling; ties to kill-switch. |
| **Profit factor** | ≥ 1.3 | Robustness of edge. |
| **Expectancy / avg R:R** | expectancy > 0 with margin; avg R:R ≥ 1.2 | Gate on **expectancy**, not win-rate alone. |
| **OOS-vs-IS Sharpe decay** | OOS ≥ 0.6 × IS | Catches overfit to the fit window. |
| **Cost-stress survival** | still profitable at 1.5× costs | At tiny capital, costs are the real enemy. |
| **Regime stability** | positive in ≥ 2 of 3 regime buckets; no single trade > 25% of total PnL | Not a one-regime, one-lucky-trade fluke. |

### 13.3 Overfitting guards (non-negotiable — the agent will try *many* strategies)
- **Deflated Sharpe Ratio (DSR)** (Bailey & López de Prado, 2014) on the Sharpe gate, accounting for the **number of (effective) trials**, track length, skew, and kurtosis. Require **DSR confidence > 0.95** rather than raw Sharpe. Because trials are correlated, estimate **effective N** by clustering similar candidates — don't use the raw count.
- **Probability of Backtest Overfitting (PBO)** via CSCV (Bailey et al., 2017) as a secondary check where feasible.
- **Walk-forward, never a single train/test split.** Prefer purged/embargoed CV (López de Prado, AFML Ch. 11–12) to avoid leakage.
- **Held-out final lockbox:** a slice of history used **only** for the final go/no-go, **never** during search — evaluated exactly once.
- **Minimum live canary** before full size — real slippage and fills are the ultimate out-of-sample test.

> **Implementation note (§21):** `mlfinlab` is now paywalled and `pypbo` is AGPL-3.0 + not on PyPI. **Implement DSR/PBO in-house from the published formulas** (cleanest, no license entanglement); use `pypbo`/AFML snippets only as a cross-check reference. Cite the SSRN papers in code comments (Appendix A).

---

## 14. Risk guardrails & kill-switches — the risk decision + rationale

These live in the **Risk** and **Compliance** agents and **cannot be overridden by any strategy or by the learning loop.** Because oversight is once-a-day and the crypto plane runs 24/7, they must be aggressive and layered. **The operator delegated the specific numbers to research-and-decide; below are the decided values and the reasoning.** All are `goal.yaml` starting points and remain operator-tunable.

### 14.1 The decided limits (seed tier)

| Control | Decided value | Rationale (research-backed) |
|---|---|---|
| **Per-trade risk (proven strategy)** | **0.5% of equity** | Upper end of the "tiny/new account" range (practitioner guidance: 0.25–0.5%). At seed capital the binding constraints are the cost-hurdle and the daily/DD brakes, not the per-trade %; lowering to 0.25% mostly slows compounding without materially reducing blow-up risk. *(0.25% is the more-conservative alternative if the operator prefers.)* |
| **Per-trade risk (new strategy, canary)** | **25% of normal → ~0.125% effective** | Unproven (gate-passed but not live-proven) strategies run at quarter size for the canary window. Layered de-risking: proven 0.5%, canary 0.125%. |
| **Sizing method** | **min(¼–½ Kelly, 0.5% risk cap, tier cap, heat cap)** | Fractional Kelly as a *cap-reducer*, never a size-*increaser*. Full Kelly overbets under uncertain, drifting edge estimates (raises ruin risk) — research is unanimous. Volatility/ATR-scaled stop distance sets the unit. |
| **Daily loss limit** | **−3% equity → halt new entries**, manage existing to exit, resume next session | Systematic norm is 2–3% self-imposed (FTMO uses 5%). At 0.5%/trade that's ~6 full-stop losers — room to operate, tight enough to cap a bad day. |
| **Two-tier intraday de-risk** | at **−1.5%** (50% of daily limit) → **halve all sizing**; at −3% → halt | Standard prop circuit-breaker pattern; reacts earlier than a single threshold while preserving operating room. |
| **Max drawdown kill-switch** | **−10% peak-to-trough → full stop, flatten where prudent, operator-only restart** | The catastrophe brake (FTMO total-loss = 10%). ≈ 3 consecutive max-loss days — a coherent ladder above the daily limit. Operator-only restart is *intended* to pause for a human if things are badly wrong. |
| **Crypto leverage** | **Hard ceiling ≤ 2× (never exceeded, asserted in config + code + Execution); seed tier capped at 1× effective** until a strategy clears its canary + 4-week sustained-Sharpe window | Crypto's 100–200× is account-suicide for an autonomous agent (10× = a 10% move liquidates). The hard 2× ceiling **never loosens with tier.** Seed-tier 1× because at seed you're validating the whole machine; leverage adds liquidation risk precisely when the system is least proven. |
| **Max open positions** | **3** | Practical at tiny capital; limits concentration. |
| **Max portfolio heat** | **2%** (sum of open-position risks) | Conservative vs the 6–10% "typical" range; with 3 positions at 0.5% = 1.5% heat. |
| **Correlation cap** | **no new position with > 0.7 pairwise correlation** to an existing one; correlated positions share heat | Five correlated positions ≠ five independent 0.5% risks; correlations spike toward 1 in stress. |
| **Consecutive-loss breaker** | **3 consecutive losses on a strategy → auto-pause + demote to re-validation** | Catches live decay fast; the strategy must re-clear the gate. |
| **New-strategy throttle** | canary size (above) for **≥ 10 live trades AND ≥ 1 week**, monitored vs predicted metrics, before ramping to full tier size | Real slippage/fills are the ultimate OOS test. |
| **Cost-hurdle** | submit only if `expected_net_edge ≥ 1.5 × round_trip_cost` (after cost **and** tax) | At seed tier this correctly rejects most equity intraday trades. |
| **Order-rate governor** | **≤ 2 OPS**, internal caps ≤ 20/min & ≤ 200/day | Well under SEBI 10 OPS and broker caps; an autonomous self-rewriting agent should never fire fast. |
| **Event blackouts** | no new entries around known high-impact events/results/illiquid windows/the daily auth gap | Avoids predictable adverse selection. |
| **Reconciliation** | every cycle, Portfolio reconciles internal vs broker truth; any drift → **halt + alert** | Protects against silent partial-fill/disconnect bugs. |
| **Manual kill switch** | one Telegram command flattens + freezes everything (enforced inside Icarus; Zerodha has no app-level kill) | Upstox native kill is a secondary backstop; exchange-side kill is a tertiary. |

### 14.2 Fail-safe doctrine (MUST)
**Fail to flat/halt, never fail to "keep trading."** On data-feed gap, schema drift, disconnect, heartbeat loss, broker error storm, reconciliation drift, or auth failure → **halt the affected plane and alert.** Use **cancel-on-disconnect** where the venue supports it (Delta does — verify). A freshly-promoted strategy never starts at full size. No single threshold is the only line of defense — the controls above are deliberately overlapping.

---

## 15. `goal.yaml` — the single source of truth

```yaml
objective:
  account_currency: INR
  target_return_30d: 0.05          # success bar (operator-set; aspirational, not a guarantee)
  max_drawdown: 0.08               # strategy-level failure bar used by the gate
  min_sharpe: 1.3
  min_sortino: 1.5
  min_calmar: 1.0
  min_profit_factor: 1.3
  min_trades_oos: 30
  min_rr: 1.2
  oos_decay_max: 0.40              # OOS Sharpe >= 0.6 x IS
  cost_stress_multiplier: 1.5
  dsr_confidence: 0.95

learning:
  reflection_every_trades: 15      # seed: per-strategy — reflect after 15 of a strategy's own closed trades (5 was statistical noise); tunable down later as volume grows
  one_change_per_cycle: true
  invention_enabled: true          # grammar-constrained
  inventor_model: claude-sonnet-4-6
  inventor_model_hard: claude-opus-4-8
  sentiment_model: claude-haiku-4-5

risk:                              # DECIDED VALUES (see §14 for rationale)
  per_trade_risk_r: 0.005          # 0.5% equity at risk per trade (proven strategy), tier-scaled
  new_strategy_size_factor: 0.25   # canary runs at 25% -> ~0.125% effective
  kelly_fraction_cap: 0.5          # never exceed half-Kelly; Kelly only reduces size
  daily_loss_limit: 0.03           # -3% equity -> halt new entries for the day
  daily_derisk_trigger: 0.015      # -1.5% -> halve all sizing
  max_drawdown_killswitch: 0.10    # -10% peak-to-trough -> full stop, operator-only restart
  max_open_positions: 3
  max_portfolio_heat: 0.02
  max_pairwise_correlation: 0.7
  consecutive_loss_pause: 3        # consecutive losses on a strategy -> pause + revalidate
  canary_min_trades: 10
  canary_min_days: 7
  cost_hurdle_multiplier: 1.5
  crypto_max_leverage_hard: 2.0    # HARD ceiling, never loosens with tier
  crypto_max_leverage_seed: 1.0    # seed tier effective cap until proven

compliance:
  max_orders_per_sec: 2
  max_orders_per_min: 20
  max_orders_per_day: 200
  white_box_only: true
  static_ip_required: true
  limit_orders_only: true          # NSE bars market orders via algo
  algo_id_tagging_required: true

tax:
  equity_intraday: speculative_business
  equity_delivery: per_classification
  equity_fno: nonspeculative_business
  crypto_inr_derivatives: speculative_business   # DEFAULT (contested - see §6)
  crypto_reclassification_stress: vda_30_flat    # gate stress scenario
  operator_slab_rate: 0.30         # conservative default; operator sets actual
```

---

## 16. Capital-scaling ladder

Position sizing is always **% of current equity**, never fixed rupees — so adding capital needs no rebuild. The **Capital-Tier policy** reads live equity from the Portfolio agent and unlocks (asset, mode) eligibility per §5. Tier promotion is itself gated:

```
Tier-up criteria (ALL, measured LIVE, not in sim):
  • ≥ 30 live trades at current tier
  • live Sharpe ≥ goal.min_sharpe sustained ≥ 4 weeks
  • max drawdown stayed within limit
  • after-cost, after-tax P&L positive
Then: operator reviews the daily report, adds capital, system unlocks next tier's universe.
```
The operator adds money; the **system never moves itself up a tier** without the live evidence above. **The crypto leverage hard ceiling (2×) never loosens with tier.**

---

## 17. Data, news & inputs (and TradingView's real role)

**Live market data:** Zerodha Kite WebSocket (equities, paid plan); Upstox WebSocket as a free failover feed; Delta India WebSocket (crypto).
**Historical OHLCV (backtests):** Zerodha historical (paid) for parity with live; **Upstox free historical** for bulk research (daily to 2000; intraday only to Jan 2022 — design around that); Delta historical for crypto. **Cache aggressively** to a local store to respect rate limits (Zerodha quote 1/s, historical 3/s).
**News:** RSS (Moneycontrol, ET Markets, Mint, Business Standard), NSE/BSE corporate announcements & filings, optional paid news API. Crypto: exchange announcements, funding rates, basic on-chain (free tiers/public explorers).
**Macro:** RBI calendar, CPI/IIP, India VIX, USDINR, global index futures, crypto funding/OI.
**Sentiment:** LLM-scored headlines, treated strictly as *data*.

**TradingView — be clear-eyed.** TradingView is **not a broker and has no execution API.** Its only sanctioned role is charting + alerts: a Pine Script strategy can emit a **webhook alert** to an endpoint you host, which your Execution agent turns into a broker order. That's a legitimate but **optional, secondary** signal source — routing every trade through a TradingView webhook adds latency and a failure point. **Recommendation:** skip TradingView in the core loop; optionally support a `tradingview_webhook` Signal-agent adapter later. **Do not design around "trading through the TradingView account" — that capability does not exist.**

---

## 18. Hosting & deployment (AWS Mumbai)

**Verdict: a single always-on EC2 VM in `ap-south-1` (Mumbai) with a dedicated Elastic IP.** Not Railway (Finding 1).

| Item | Choice | Notes |
|---|---|---|
| Compute | **EC2 `t4g.small`** (2 vCPU ARM Graviton, 2 GiB) | ~$8.2/mo. 2 GiB gives headroom for Postgres + Valkey + agents. *(Lightsail $7/1 GB is cheaper with a bundled static IP, but 1 GiB is tight for the full stack — use only if RAM is carefully managed.)* |
| Static IP | **Elastic IP** (dedicated static IPv4) | ~$3.65/mo (all public IPv4 are billed since 2024, attached or idle). **This is the IP registered with Zerodha, Upstox, and Delta.** |
| Approx total | **~$12.6/mo (~₹1,200)** | FX ~₹95/USD as of June 2026 (weaker than older assumptions — re-check). |
| State | **Postgres** (on-box or managed) | Never store trading state only on ephemeral disk. |
| Bus | **Valkey** (or Redis 8) Streams | See §21 licensing note. |
| Versioned strategy YAML + audit archives | git repo / object storage | |
| Process mgmt | **systemd** units (Orchestrator + agents), auto-restart | Or a lightweight container per plane. |
| Network | Security group: inbound SSH from operator IP only; all outbound | |
| Persistence | Postgres + **off-box backups** | State loss mid-position is a real-money incident. |

Crypto plane runs 24/7; equity plane sleeps outside NSE hours but the VM stays up (research/backtests run after close).

---

## 19. Security, secrets & audit

- **Secrets:** all broker/exchange keys in a secrets manager (**AWS Secrets Manager** — chosen with AWS hosting — or SOPS-encrypted file / git-ignored `.env` chmod 600). **Never hardcoded, never committed.** The **Execution agent is the only component with order-placement credentials**; data agents use read-only keys where the venue supports scoping.
- **Least privilege:** separate data (read) vs trading (write) keys where possible; crypto keys scoped to trading only, **withdrawals disabled at the exchange.**
- **No money movement, ever:** no withdrawal/transfer capability is wired in. Trading only.
- **Prompt-injection hardening:** LLM/news outputs are **data, not instructions.** A headline, fetched page, or LLM completion can never command an order or change a limit. The only order origin is the Signal→Risk→Execution path on **promoted** strategies. Validate/parse all external text; quote-and-flag anything resembling an instruction.
- **Audit log (append-only):** every market decision, order, fill, veto, halt, strategy diff, hypothesis, and validation verdict written immutably (Postgres + archived), retained **≥ 5 years** (SEBI). This is the debugging trail, the daily-report source, **and the tax/Schedule-VDA ledger.**
- **Auth:** OAuth + 2FA + daily token refresh; static-IP assertion on every order path.
- **Blast radius:** the research plane has **no credentials and no network path** to brokers — enforce at the process/network level (separate OS user, no secret access, firewall egress), not just by convention.

---

## 20. Project structure & key configs

```
icarus/
├── pyproject.toml                 # uv-managed
├── README.md
├── CLAUDE.md                      # engineering conventions + safety invariants (companion file)
├── .env.example                   # never commit real .env
├── goal.yaml                      # the objective + thresholds (§15)
├── deploy/
│   ├── systemd/                   # unit files per agent/plane
│   └── infra-notes.md             # VM + Elastic IP + broker whitelist steps
├── icarus/
│   ├── orchestrator/              # clock, state machine, supervision, kill-line
│   ├── bus/                       # Valkey/Redis Streams wrappers, message schemas
│   ├── agents/
│   │   ├── data/ news_sentiment/ macro/ regime/
│   │   ├── signal/                # runs promoted strategies
│   │   ├── risk/                  # sizing + veto + hard limits
│   │   ├── execution/             # broker IO (ONLY writer)
│   │   ├── portfolio/
│   │   ├── research/              # strategy inventor + reflection
│   │   ├── validation/            # the gate + metrics battery
│   │   ├── compliance/            # rate governor, white-box assert, static-IP, LIMIT-only
│   │   └── oversight/             # daily report + manual kill/rollback (Telegram)
│   ├── brokers/
│   │   ├── base.py                # BrokerAdapter protocol
│   │   ├── zerodha.py             # primary (equities)
│   │   ├── upstox.py              # failover (equities) + free backup data feed
│   │   └── delta_india.py         # crypto, INR-settled only
│   ├── strategy/
│   │   ├── dsl.py                 # grammar + vetted primitive library
│   │   ├── registry.py            # versioned promoted/demoted strategies
│   │   └── library/               # promoted strategy YAMLs (versioned)
│   ├── engine/
│   │   ├── backtest.py            # walk-forward, OOS, lockbox, purge/embargo
│   │   ├── metrics.py             # Sharpe/Sortino/Calmar/PF/expectancy/DSR/PBO
│   │   ├── costmodel.py           # STT/GST/brokerage/DP/slippage per venue (§7)
│   │   ├── taxmodel.py            # equity + crypto (incl. reclassification stress)
│   │   └── sim.py                 # simulated-fill forward-runner
│   ├── state/                     # postgres models + Alembic migrations
│   └── common/                    # schemas, types, logging, secrets
└── tests/                         # unit + a full backtest regression suite (golden)
```

**`strategy.yaml` (a single promoted strategy, versioned):**
```yaml
id: rsi_meanrev_eq_v07
version: 7
parent: 6
asset_class: equity
universe: [liquid_largecap_nse]        # §29.2 BANS the penny/low-price universe
regime_whitelist: [range, low_vol]
entry:
  all:
    - rsi(14) < 28
    - close > vwap * 0.99
    - news_veto == false
exit:
  stop_loss_atr: 1.5
  target_rr: 1.8
  trailing: atr(2.0)
  time_stop_bars: 30
sizing:
  risk_r: 0.005           # tier-scaled at runtime
provenance:
  invented_by: research_agent
  hypothesis: "tighter RSI + VWAP filter cuts false longs in range regime"
  validation: { sharpe_oos: 1.41, sortino: 1.7, maxdd: 0.06, trades: 44, dsr: 0.96 }
  promoted_at: 2026-06-20T...
```

---

## 21. Tech stack (concrete, version-checked June 2026)

- **Language:** **Python 3.12** (recommended over 3.11 to track numpy 2.5 + pandas 3.0 without pins), async-first (`asyncio`). Package mgmt: **`uv`**.
- **Broker SDKs:** **`kiteconnect`** (Zerodha — note the PyPI name is `kiteconnect`, not `pykiteconnect`), **`upstox-python-sdk`** (import `upstox_client`, failover), **`delta-rest-client`** + **`ccxt`** (Delta India; verify `ccxt.deltaindia` in your pinned version).
- **Bus:** **Valkey** (BSD-licensed Redis fork) Streams, or Redis 8, via **`redis-py`** (the client works on both). *Choosing the server is a deliberate licensing decision: Redis 8 is AGPLv3/SSPL; Valkey is BSD-3. Prefer Valkey to avoid copyleft questions.*
- **State:** **Postgres** + **SQLAlchemy 2.x** + **Alembic**.
- **Data/backtest:** **`pandas` 3.x**, **`numpy`** (pin ≤2.4.x if you stay on Python 3.11; 2.5 needs 3.12), **`polars`** (speed), `ccxt`.
- **Metrics:** custom implementations + patterns from **`quantstats`**; **do NOT use `empyrical`** (abandoned since 2020) — use **`empyrical-reloaded`** if you want that API. **Implement DSR/PBO in-house** from the published formulas (Appendix A); `mlfinlab` is paywalled and `pypbo` is AGPL/not-on-PyPI (reference only).
- **LLM:** **Anthropic API** — `claude-sonnet-4-6` (Inventor default), `claude-opus-4-8` (hard synthesis), `claude-haiku-4-5` (sentiment, with Batch + prompt caching). Idea/score source only, never an executor.
- **Process mgmt:** **systemd** (or Docker per plane). **Secrets:** **AWS Secrets Manager** (or SOPS).
- **Alerting/report/control:** **`python-telegram-bot` 22.x** (async; v20+ rewrite — don't copy pre-v20 examples).
- **Testing:** **`pytest`** + a **golden backtest regression** that MUST pass before any deploy.

---

## 22. Phased roadmap (build-ready through Phase 3)

Build in order. **Detailed, checkbox-level tasks with acceptance criteria are in `TASKS.md`.**

**Phase 0 — Skeleton & safety rails (no trading).**
Orchestrator + bus + Postgres + config loading; `BrokerAdapter` protocol; Zerodha + Delta adapters in **read-only**; Compliance agent (rate governor, static-IP assert, market hours, LIMIT-only assertion); audit log; daily-auth agent. **Deliverable:** the system authenticates, streams data, and *can place nothing yet.*

**Phase 1 — Data + sim + metrics.**
Data/Regime/News/Macro agents; CostModel (§7 rates) + TaxModel (incl. reclassification stress); backtest engine (walk-forward, OOS, lockbox, purge/embargo); full metrics battery + DSR/PBO; sim forward-runner on Delta testnet. **Deliverable + STOP GATE:** backtest and sim-forward any DSL strategy and produce an honest metric sheet for **one hand-written strategy**. *No live order path is enabled. Operator reviews Phase-1 evidence before Phase 2.*

**Phase 2 — Live execution plane (one hand-written strategy).**
Risk agent (sizing + all §14 hard limits) + Execution agent (LIMIT-only, algo-tagged, bracket/stop) + Portfolio agent + all kill-switches + Telegram oversight (manual kill). Seed **one** simple, human-authored, gate-passed strategy. Run **micro-live** on equities + crypto in parallel behind the shared `BrokerAdapter`. **Deliverable:** Icarus trades real money, tiny, fully governed and logged — but does **not yet self-modify.**

**Phase 3 — The learning loop.**
Research/Inventor agent + the autonomous promotion gate wired end-to-end (invent/tune → validate → canary → promote/demote → rollback). Strategy registry + versioning + hypothesis meta-learning. **Deliverable:** Icarus improves itself, every change forced through the gate.

**Phase 4 — Oversight + harden (requirements level).**
Full daily-report content, rollback command, reconciliation hardening, Upstox failover drills, chaos tests (kill feeds/agents mid-trade), tax-ledger export. **Deliverable:** safe to leave alone 24h.

**Phase 5 — Scale (requirements level).**
Only on live evidence (§16): widen universe, raise tiers as the operator adds capital, expand the primitive library, upgrade Regime to HMM/Markov. **Leverage cap never loosens.**

---

## 23. Failure modes (devil's advocate)

Honest steelman of what kills systems like this, and where each is handled:
1. **Overfitting / backtest mirage** → DSR + multiple-testing correction + walk-forward + lockbox + live canary (§13).
2. **Costs eat the edge at tiny capital** (the most likely silent killer) → CostModel inside every backtest + 1.5× cost-stress gate + cost-hurdle at decision time (§7, §13).
3. **Leverage blow-up on crypto** → hard 2× cap + seed-tier 1× in config, code, and Execution assert (§14).
4. **Strategy decay** → continuous live re-validation + auto-demotion + rollback (§13).
5. **Regulatory drift** → white-box, low-frequency, static-IP, self-use posture + Compliance agent + operator's periodic check (§8, §24).
6. **Tax misclassification** (now an elevated risk) → flagged loudly; reclassification stress scenario in the gate; clean per-trade ledger; CA confirmation before scaling (§6, §24).
7. **Unattended catastrophe in the 24h gap** → daily-loss halt + two-tier de-risk + drawdown kill + reconciliation + circuit breakers + fail-safe-to-halt (§14).
8. **Self-modifying code reaching money unvetted** (the nightmare of the genre) → research plane has *no credentials and no broker path*; the numeric gate is the only bridge (§9, §13).
9. **Tiny-capital statistical noise** → minimum-trade gates before any metric is believed (§13).
10. **Prompt injection via news/LLM** → all external text is data, never command (§19).

The uncomfortable meta-truth, kept visible: **even a well-built Icarus is more likely to slowly lose money than to compound.** Make losses small, legible, survivable; treat seed capital as tuition.

---

## 24. Operator action items (setup before live)

These are the operator's responsibilities the system cannot do for itself. (Claude Code: surface these in `README.md` and block the relevant phases on them.)

1. **Zerodha:** Kite Connect paid plan (₹500/mo) active *(done)*; register the VM's Elastic IP in the Kite developer console; confirm current order-rate limits.
2. **Provision Upstox** failover app (free data API; confirm post-Mar-2026 order pricing) and whitelist the VM IP.
3. **Provision Delta Exchange India** account + API keys + **testnet** access; whitelist the VM IP; disable withdrawals on the trading key.
4. **Provision the AWS Mumbai VM + Elastic IP**; lock the security group; register that one static IP with all three venues.
5. **Unattended daily OAuth+2FA:** decide the daily token-refresh approach (operator one-tap vs TOTP automation at own risk); the system stays in a safe non-trading state until authenticated.
6. **Confirm crypto-derivative tax classification with a CA** before the crypto leg scales (§6 — this is now a contested area; treat seriously). Keep clean per-trade records from day one.
7. **F&O stays simulation-only** until capital + risk headroom genuinely support ≥1–2 lots.
8. **Do not distribute Icarus** beyond self + immediate family.

---

## 25. Appendix A — research sources & as-of dates

**SEBI / regulatory (as of June 2026):** SEBI circular 4 Feb 2025 (the framework); SEBI circular 30 Sep 2025 (extension to 1 Apr 2026 + glide path); NSE INVG/67858 (5 May 2025, implementation standards: 10 OPS, static IP, OAuth/2FA, tagging, kill switch); NSE FAQ (3 Nov 2025, tech-savvy investor / static-IP / black-box clarifications).
**Costs/taxes:** Zerodha charges page + STT support article (confirms 1 Apr 2026 F&O STT hike: futures 0.05%, options 0.15%); NSE transaction-charge revision (₹2.97/lakh, Oct 2024). Crypto: §115BBH / §194S; Finance Act 2025 VDA-definition broadening (eff. 1 Apr 2026); Delta/CoinDCX help pages (the speculative-income interpretation); Karnani & Co / Pi42 / ClearTax / TradeSteady commentary; CBDT stakeholder-feedback solicitation on crypto derivatives.
**APIs:** Zerodha Kite Connect docs (rate limits, WebSocket caps, static IP, daily token); `kiteconnect` PyPI/GitHub (v5.2.0, Apr 2026); Upstox developer docs (free data API, sandbox, historical depth, ₹10/order promo expiry 31 Mar 2026); `upstox-python-sdk` PyPI (v2.27.x); Delta India docs (INR-settled futures+options, testnet `cdn-ind.testnet.deltaex.org`, base `api.india.delta.exchange`, bracket orders); `delta-rest-client` PyPI (v1.0.14); CCXT `deltaindia`.
**Risk/quant:** the "1% rule" + 0.25–0.5% for small accounts; fractional Kelly (Thorp; half-Kelly ≈ 75% growth at ½ vol); ATR/volatility targeting (Carver, *Systematic Trading*); Van Tharp position sizing & portfolio heat; FTMO daily-loss/total-loss benchmarks (5%/10%). DSR: Bailey & López de Prado, *J. Portfolio Management* 40(5), 2014 (SSRN 2460551). PBO/CSCV: Bailey, Borwein, López de Prado, Zhu, *J. Computational Finance* 20(4), 2017 (SSRN 2326253). Walk-forward / purge-embargo / CPCV: López de Prado, *Advances in Financial Machine Learning* (Wiley 2018), Ch. 11–12. Haircut Sharpe / multiple-testing: Harvey & Liu, "Backtesting" (SSRN 2345489).
**Infra/stack:** AWS VPC pricing (public IPv4 $0.005/hr); EC2 `t4g.small` ap-south-1 (~$8.2/mo); Lightsail tiers; AWS Secrets Manager. Library status (June 2026): `kiteconnect` 5.2.0, `upstox-python-sdk` 2.27.x, `delta-rest-client` 1.0.14, `ccxt` 4.5.x, `quantstats` 0.0.81, `empyrical` abandoned → `empyrical-reloaded`, `polars` 1.41.x, `pandas` 3.x, `numpy` 2.5 (needs 3.12), `uv` 0.11.x, `redis-py` 8.0 / Valkey, SQLAlchemy 2.0.51, Alembic 1.18.x, `python-telegram-bot` 22.x.
**Anthropic models (June 2026):** Opus 4.8 ($5/$25 per M tok), Sonnet 4.6 ($3/$15), Haiku 4.5 ($1/$5); Batch API 50% off; prompt caching ~90% off reads.

## 26. Appendix B — facts to re-verify before live (and known uncertainties)
- **SEBI:** confirm no further amendment after the 1 Apr 2026 mandatory date (check SEBI Legal→Circulars, filter "Algorithmic").
- **Equity costs:** exchange transaction charges change by circular; re-pull NSE/BSE charge circulars rather than hard-coding. Decide NSE-cash convention (0.00297% raw vs 0.00307% all-in incl. IPFT) — don't double-count.
- **Crypto tax:** the INR-settled-derivative "speculative business income" treatment is **common interpretation, not settled law**; CBDT has flagged it as open and the VDA definition broadened in FY25 — **CA confirmation required**; keep the reclassification stress scenario in the gate.
- **Upstox order pricing post-31 Mar 2026** is unpublished — verify before relying on Upstox for live orders.
- **Upstox kill-switch** exact API mechanism — verify on the regulatory-controls page.
- **Delta India** exact per-contract max leverage (100× vs 200×) — confirm on the live contract-specs page (irrelevant operationally since we hard-cap ≤2×, but verify the cap is enforceable per contract).
- **`ccxt.deltaindia`** present in your pinned CCXT version.
- **Kite daily token:** no officially-blessed unattended retail flow — plan for one daily refresh.
- **FX** (₹/USD ~95 in June 2026, moves daily) for any INR cost budgeting.
- **Anthropic model availability/pricing** in your Console/jurisdiction before budgeting LLM spend.

---

# PART II — v2 Hardening (authoritative where it extends Part I)

> These sections close the gaps that are cheap to specify now and very expensive to retrofit once real money flows. All are `MUST` unless marked `SHOULD`. Read §27 (autonomy contract) and §28 (sub-agent mesh) first — they answer "is it truly agentic and autonomous?" — then the pipeline-rigor sections.

---

## 27. Decision-rights / autonomy ladder (the autonomy contract)

Icarus is autonomous in everything that happens *between* operator touch-points. There are exactly four standing operator responsibilities, and they exist because of regulation, money-in, or catastrophe — not because the system needs hand-holding. This table is the contract; the build must enforce it.

| Decision | Who decides | Gate / mechanism |
|---|---|---|
| Generate / mutate / invent a strategy | **System** (Inventor) | DSL-constrained; one change per cycle |
| Validate & promote / demote / retire a strategy | **System** (Validation gate) | Numeric gate (§13, §31); lifecycle state machine (§34) |
| Size / veto / place / cancel a trade | **System** (Risk + Execution) | Hard limits (§14), quality gate (§32), order-rate governor |
| Allocate risk budget across promoted strategies | **System** | Allocation policy (§34.2) |
| Select / refresh the tradable universe | **System** | Universe policy (§29.5) |
| Adapt to regime, halt, de-risk, kill on triggers | **System** | Kill-switches (§14, §36) |
| Roll / close a derivative near expiry | **System** | Expiry buffer (§33) |
| Recover after a crash | **System** | `RECOVERY` state, default-to-halt (§35) |
| **Daily auth (token refresh)** | **Operator** (one tap) *or* system (TOTP, opt-in) | §38 |
| **Add capital / approve a tier-up** | **Operator** | System only *unlocks* a tier after live evidence (§16); it never moves itself up |
| **Restart after a −10% drawdown kill** | **Operator** | Operator-only restart (§14) |
| **Enable a new venue or add a DSL primitive** | **Operator** | Human adds the primitive to the vetted library first (§12.1) |
| **Confirm tax classification** | **Operator + CA** | §6 |
| **Manual kill / rollback** | **Operator** (always available) | §36 (independent of orchestrator) |

**Autonomy doctrine:** the system may do anything in the "System" rows without asking, 24/7, but **every autonomous decision is logged with its rationale** (audit log = the autonomy trail) and **surfaced in the daily brief**. If the system is ever unsure (reconciliation drift, data-quality failure, auth failure, datastore down), the autonomous choice is **halt, not improvise** (§14.2).

---

## 28. Sub-agent decomposition (the mesh, expanded)

The 12 domain agents (§10) are **supervisors**; the real work is done by **task sub-agents** they spawn and supervise. This is what makes the system genuinely multi-agentic rather than a monolith with labels. Hierarchy: **Orchestrator → domain agents → task sub-agents.** Sub-agents are independently restartable, single-responsibility, and communicate via the same typed bus.

| Domain agent | Task sub-agents (one job each) |
|---|---|
| **Data** | one **feed sub-agent per (venue, data-type)** — Zerodha-quotes, Zerodha-depth, Upstox-quotes (backup), Delta-quotes, Delta-funding; plus a **Data-QA sub-agent** (§29.4) and a **Historical-loader sub-agent** (cache, PIT) |
| **News/Sentiment** | one **source sub-agent per feed** (Moneycontrol RSS, ET, Mint, NSE/BSE filings, Delta announcements) + a **scoring sub-agent** (Haiku, batched) + an **injection-filter sub-agent** (quote-and-flag) |
| **Macro** | **Calendar/Sessions sub-agent** (NSE holidays, sessions, expiry registry — §33), **macro-prints sub-agent**, **funding/OI sub-agent** |
| **Regime** | per-instrument **classifier sub-agents** (parallel) |
| **Signal** | one **sub-agent per (promoted strategy, instrument)** — pure functions, massively parallel, the literal "small tasks" decomposition |
| **Risk** | **sizing sub-agent**, **limit-check sub-agent**, **allocation/arbitration sub-agent** (§34.2), **quality-gate sub-agent** (§32) — run as a single serialized critical section (§36.5) |
| **Execution** | per-venue **order-lifecycle sub-agent**, **smart-limit-placement sub-agent** (§32.3), **reconciliation sub-agent** |
| **Portfolio** | **P&L sub-agent**, **equity/heat sub-agent**, **broker-reconcile sub-agent** |
| **Research/Inventor** | **diagnosis sub-agent** (what's bleeding), **hypothesis sub-agent** (LLM), **DSL-mutation sub-agent**, **candidate-sanity sub-agent** (schema/white-box check before the gate) |
| **Validation** | one **sub-agent per gate stage** (in-sample, walk-forward, cost/tax stress, overfitting, sim-forward, canary) — each can reject; run as a pipeline |
| **Compliance** | **rate-governor sub-agent**, **static-IP sub-agent**, **white-box-assert sub-agent**, **calendar/blackout sub-agent** |
| **Oversight** | **daily-report sub-agent**, **alerting sub-agent** (separate process — §36.4), **command sub-agent** (kill/rollback) |

**Supervision:** the Orchestrator supervises domain agents; each domain agent supervises its sub-agents (restart on crash, escalate restart-storms to a plane halt). Heartbeats at both levels (§37).

---

## 29. Data integrity & truth (the #1 backtest-validity cluster)

A backtest is only as honest as its data. These prevent the classic invalidators. **All are MUST and gate Phase 1.**

**29.1 Point-in-time (PIT) universe & no look-ahead.** The backtester selects the universe **as it existed on the simulated date**, never today's list. Archive NSE daily bhavcopy + instrument lists + surveillance (ASM/GSM)/suspension/delisting status as-of each date. A strategy is validated only on instruments it *would have known about and could have traded* on that date.

**29.2 Survivorship-bias control.** Today's historical APIs return only currently-listed names — a survivors-only sample that manufactures fake edges, **worst of all in low-priced names.** Therefore: **the seed-tier equity universe is restricted to liquid, non-surveillance, large/mid-cap (ideally F&O-eligible) names; the low-priced "penny" universe is BANNED** because it cannot be backtested honestly at this budget. Where delisted-name data is obtainable, include it with delisting modeled as a forced exit at a punitive price. (This supersedes the `liquid_lowprice_nse` example universe in §20.)

**29.3 Corporate-action adjustment.** Back-adjust equity series for splits/bonus/rights for **signal computation**; choose one dividend convention (price-return vs total-return) and apply it identically in signal, cost, and tax. Cross-check Zerodha's adjusted series against NSE corporate-action announcements (already ingested). **Data-QA assertion:** any single-bar move beyond a threshold (e.g. |return| > 50%) is flagged as a probable unadjusted action → halt that symbol's backtest/trading rather than trade the artifact.

**29.4 Data-QA layer (new sub-agent, between ingest and everything).** Reject/winsorize bad ticks (price ≤ 0, or > N·ATR from last); detect **stale feed** (same value/timestamp repeating beyond a threshold → treat as gap → halt that plane); enforce the **trading calendar** (no fabricated bars on holidays/half-days; no live trading on a closed market); de-duplicate timestamps; emit a per-day **data-quality score** the gate reads (low-quality window → `NEEDS_MORE_DATA`). Applies to crypto too (exchange downtime, funding-time gaps). A bad tick must never trip a real stop or entry.

**29.5 Timezone & autonomous universe selection.** Store **all timestamps tz-aware in UTC**; convert to IST only at session/calendar boundaries and for the tax day; pin crypto funding/settlement boundaries. The **universe-builder sub-agent** autonomously refreshes the tradable set from transparent filters (min average daily value traded, price band, exclude suspended/T2T/surveillance, min depth) — a white-box, auditable policy (this is part of the system's autonomy, §27).

---

## 30. Backtest & execution realism (stop the paper-only profits)

**30.1 LIMIT-order fill model (the single most important realism fix).** Because execution is LIMIT-only, the dominant error is **assuming you got filled.** Rules (conservative-by-default):
- **Touch ≠ fill.** A resting limit fills only if the bar's price **trades strictly through** it, not merely touches it.
- **Pessimistic queue position.** Assume back-of-queue: require traded volume at your price to exceed resting size ahead of you (proxy: bar volume ≥ `k ×` your size).
- **No favorable cherry-picking / adverse selection.** Count fills that occur because price moved against the subsequent trade direction; the sim may not select only favorable fills.
- **No-fill is a real outcome.** An unfilled entry/exit simply doesn't happen; the engine accounts for the missed trade and any resulting unmanaged exposure.
- Marketable/crossing limits pay spread + modeled slippage. **"touch = fill" is a forbidden assumption (CLAUDE invariant) with a golden test.**

**30.2 Next-bar execution (no same-bar look-ahead).** A signal computed on bar *t*'s close executes **no earlier than bar t+1** (next-bar open or a t+1 limit), unless provably computable intra-bar from already-realized data. Decision-time and execution-time are separate fields and asserted. Leakage test: shifting the series by one bar must degrade metrics.

**30.3 Slippage, latency, partial fills.** Model a fixed conservative **decision→ack→fill latency** (broker round-trip + governor delay) so nothing executes instantaneously; model **partial fills** in the sim (residual exposure + stop math); compute the risk unit **R on the actually-filled quantity**, not the intended.

**30.4 Capacity / liquidity / market impact.** Add a **participation/impact term**: slippage scales with (order size ÷ available depth or median bar volume); reject/penalize trades where size exceeds a small fraction (≤1–5%) of typical depth. Report a **capacity metric**: the notional at which the edge degrades — and require a strategy to be capacitated **for the next tier up**, not just the current one (protects the scaling thesis). Screen out illiquid Delta contracts/expiries.

**30.5 Sim-vs-live calibration loop (`SHOULD`).** After each canary/live window, compare modeled vs realized fills/slippage and **auto-widen the sim's assumptions if live is worse**; surface the gap in the daily brief. The cheap, proportionate version of institutional TCA.

---

## 31. Overfitting at scale (defending an *unbounded* autonomous search)

The original DSR + lockbox + walk-forward defense is correct but is defeated over time by an agent that tries thousands of candidates against finite history. Close it:

**31.1 Lifetime trial ledger.** Persist a global counter of **every candidate ever evaluated** (plus a correlation proxy). Feed the **cumulative effective N** into DSR — never the per-cycle count. Wire in **Harvey–Liu haircut Sharpe (BHY)** as the cumulative multiple-testing adjustment (already cited in Appendix A; now make it a gate input).

**31.2 Lockbox budget + rotation.** Treat the lockbox as a consumable: cap total lockbox evaluations; once exceeded, **no promotion until fresh out-of-sample calendar time accrues** (live trades become the new evidence). **Roll the lockbox forward in time** — newest unseen data periodically becomes the new lockbox; the old lockbox graduates to walk-forward. "Lockbox exhaustion" is a first-class state surfaced in the daily report.

**31.3 Quarantine meta-learning from gate data.** The meta-learner (§12.3) may bias *which* hypotheses to try, but its priors are validated on **live forward outcomes**, never re-scored on the historical lockbox — otherwise it is data-snooping by construction.

**31.4 Small-sample honesty.** Gate on the **lower confidence bound** of Sharpe/expectancy (use the skew/kurtosis already in DSR), not the point estimate. Apply a **shrinkage prior** pulling small-sample Sharpe toward zero (a 30-trade 1.3 Sharpe scores well below a 200-trade 1.3 Sharpe). Make the trade-count floor **scale with effect size** (smaller edge → more trades required). Reframe the canary explicitly as **execution validation, not statistical proof** — statistical confidence comes only from the longer live record (the ≥4-week tier-up gate is the real statistical bar).

**31.5 Benchmark / edge-vs-beta (critical — without it the system cannot tell skill from drift).** Add benchmark-relative metrics to the battery: **alpha vs Nifty (equities) / BTC-hold (crypto), Information Ratio, and beta/R² to the benchmark.** Gate: require **positive alpha after cost/tax** and flag any strategy whose returns are mostly explained by benchmark beta (high R²). The daily brief reports excess-over-benchmark so the operator sees skill, not a leveraged long in a bull tape.

**31.6 Cross-section multiple-testing.** Treat (strategy × symbol) combinations as part of the trial count; require the edge to hold **pooled across the intended universe**, not just on the best symbols.

**31.7 Calendar-span & regime floors.** Add a **minimum OOS calendar span** covering ≥1 stress episode (state the known limitation that intraday history is only ~Jan-2022+, so weight daily/longer-horizon evidence). Require a **minimum trade count per regime bucket** before crediting "regime stability," and assert the regime classifier uses only realized bars (no centered/leaky windows).

---

## 32. Trade-quality doctrine (the operator's #1 ask: few, top-notch trades)

"Top-notch quality, not quantity" is now operationalized, not just asserted.

**32.1 `TradeQualityScore`.** A composite, computed at the Risk agent per intent: after-cost-after-tax **expectancy (in R)** × **R:R** × **conviction** (defined: signal strength × regime-fit × confluence count of confirming conditions) × **liquidity headroom** × **event-clean timing**. Uses the **discounted/lower-bound edge** (§31.4), not the raw backtest mean — this also fixes the cost-hurdle circularity (the hurdle's `expected_net_edge` must use the conservative estimate).

**32.2 Quality gate + anti-overtrading.** The Risk agent **rejects intents below `min_quality_score`** (a quality bar above the mere cost-hurdle). **Rank-and-select:** when multiple intents fire, trade only the **top-K by quality**, never "everything that fires." Enforce **max trades/day per strategy** and a **min holding / cool-down**. The learning loop optimizes **quality (expectancy, in-regime hit-rate, R:R), not trade count.**

**32.3 Execution quality.** Concrete smart-limit policy: post at/inside the touch, reprice after X seconds/bars up to a cap, then cancel — **never chase past the marketable-limit band.** Measure **implementation shortfall** (fill vs decision-mid), fill rate, and time-to-fill per order; feed them back so the gate **penalizes strategies that look good but execute poorly.**

---

## 33. Crypto-derivative economics (get the seed-tier live surface right)

Crypto is the primary live learning surface at seed tier, so its economics must be modeled, not waved at.

- **Funding accrual.** For perps, **accrue funding at every funding timestamp** in backtest, sim, and live net-P&L and in the cost-hurdle. A carry-negative strategy must not look profitable.
- **Futures roll.** Define a roll policy for dated futures (roll N days before expiry; pay modeled roll cost = spread + basis; use roll-adjusted series for signals, realize roll cost in P&L). No naive continuous-contract stitching.
- **Expiry buffer.** Risk rule: **no new entry within `expiry_buffer` of a derivative's expiry; force close/roll** open derivative positions T-minus-X. A per-instrument expiry registry lives in the Calendar sub-agent (§28).
- **Options scoped OUT for now (`MUST`).** The DSL has no Greeks/theta/IV/expiry model, so **trade perps + dated futures only**; **no crypto options** until an options sub-model + DSL primitives exist (a Phase-5 item, human-added). This is a CLAUDE invariant.
- **Contract/strike/expiry selection** rules specified where futures are used (front-month with min liquidity).

---

## 34. Strategy lifecycle + capital allocation across strategies

**34.1 Lifecycle state machine (explicit).**
```
CANDIDATE → VALIDATING → CANARY → PROMOTED(LIVE) → WATCH(decaying) → DEMOTED → RETIRED/ARCHIVED
                  │(reject)                    │(rollback to last-good entry logic)
                  └────────► REJECTED          └──────────────────────────────────
NEEDS_MORE_DATA: re-queued with a TTL; expires if still under-powered (no limbo).
```
Every transition is logged with evidence; the daily brief shows current state per strategy.

**34.2 Capital allocation across concurrently-promoted strategies (was unspecified).** Define a `strategy_budget` policy: **max concurrent live strategies** (3–4 at seed), a per-strategy risk-budget fraction, and arbitration when contention exceeds capacity. Default: **risk-parity-style equal weight across promoted strategies, capped, ties broken by recent live DSR-adjusted performance**; **two strategies above the correlation cap share one budget slot** (extends the §14 correlation rule from positions to strategies). The Risk **allocation sub-agent** arbitrates contended `TradeIntent`s, emitting `Veto{reason: budget_contended}` for losers. Aggregate heat still never exceeds 2%.

**34.3 Demotion with open positions.** On demotion/rollback: **stop new entries immediately; manage existing positions to their already-defined exits under a frozen copy of the demoted version's exit rules** (never the new version's), then retire. Rollback changes *entry* logic for new trades only. (No orphaned positions, no ambiguous exit logic.)

---

## 35. Crash recovery & exactly-once execution (the top real-money risk on one VM)

**35.1 Mandatory `RECOVERY` state before `TRADING` on every startup.**
```
1. Load last-known open positions/orders from Postgres.
2. Pull broker truth: positions(), open orders, today's fills/order history.
3. Three-way reconcile (internal ↔ broker positions ↔ broker open orders); classify each:
   matched / broker-has-internal-missing / internal-has-broker-missing / qty-mismatch.
4. Any unresolved discrepancy ⇒ HALT + flatten-where-prudent + page operator.
   Resume TRADING only if clean AND every open position has a live protective stop at the
   broker (re-arm if missing). Persist a recovery_report to the audit log.
```

**35.2 Exactly-once order protocol (idempotency that actually works).** Kite does **not** honor a client idempotency token, so build it:
- Before any broker call, write an `order_intent{client_order_id, strategy_id, signal_id, bar_ts, …, status=PENDING}` row. `client_order_id` = deterministic **UUID v5 of (strategy_id, signal_id, bar_ts)** so the same signal never yields two keys.
- Put `client_order_id` in the order tag; on restart or bus-redelivery, **scan today's broker order history for that id before sending** — if present, reconcile its fill instead of re-placing.
- Invariant + test (add to CLAUDE §6): "a redelivered `SizedOrder` and a mid-flight crash each result in **exactly one** broker order."

---

## 36. Resilience & failure doctrine (survive 24h unattended on one VM)

**36.1 Datastore-down = halt.** Loss of Postgres or Valkey while a position is open is a **fail-safe-to-halt trigger** (halt affected plane, flatten-where-prudent, page). Tested.

**36.2 Bus durability (Valkey/Redis Streams).** Specify **consumer groups with explicit `XACK`**, a **dead-letter stream** for messages failing 3× (the `SchemaError` path feeds it), a **`MAXLEN ~` cap** per stream, and **backpressure policy: drop-oldest for ephemeral market-data streams; block-or-halt for order/position streams (never silently drop an order).** Recovery replays only unacked **order/position** entries; market-data is not replayed.

**36.3 Backups / RPO.** Postgres WAL archiving (or `pg_dump`) to off-box (S3, same region OK) every 15–30 min + on `POST_CLOSE`; **RPO ≤ cadence.** (≥5-yr SEBI audit retention requires off-box copies anyway.)

**36.4 Kill-switch independence (the kill must outlive the thing it kills).** The **Telegram/alerting bot runs as a separate supervised process** from the orchestrator. `kill` acts **directly via the BrokerAdapter cancel/flatten AND sets a persistent `HALT` flag in Postgres/Valkey** that every plane checks each cycle and at startup — not only a bus broadcast a wedged orchestrator must relay. Add a **watchdog** (separate systemd unit) on the orchestrator heartbeat that, on heartbeat-loss-with-open-positions, fires **cancel-on-disconnect/flatten** and pages. Make **cancel-on-disconnect** at the venue a hard requirement where supported (Delta yes; verify Kite).

**36.5 Concurrency serialization.** The Risk agent processes sizing+commit through a **single critical section** (one in-flight at a time) or an atomic reserve-then-commit on the heat/slot budget in Valkey — so two intents can't each see heat=1.5% and both pass to 3%. Test: "two simultaneous intents that each fit alone but together exceed heat → the second is vetoed."

**36.6 SPOF runbook + NTP + secondary alert.** `deploy/infra-notes.md` runbook for VM loss (relaunch, **reattach the *same* Elastic IP** — never release it, the broker whitelist is keyed to it, restore Postgres, re-auth; RTO target stated). Enable **chrony/NTP** and assert clock sync at startup (Delta's HMAC signature is valid only 5 s; audit/idempotency depend on the clock). Add a **secondary CRITICAL-alert path** (email/SNS) and a fallback HALT mechanism (SSH-able flag file) so control doesn't depend solely on Telegram.

---

## 37. Observability & SLOs (the system watches itself between daily reviews)

Quantify the health surface (into `goal.yaml` + §9.3):
- **Heartbeats:** every agent/sub-agent beats every `heartbeat_interval_s` (e.g. 5s); `heartbeat_miss_threshold` misses (e.g. 3) = dead → restart; restart-storm → halt plane.
- **Data-staleness SLO per venue:** equities tick > `data_staleness_equity_s` (e.g. 10s, market hours) = stale → veto new entries on that symbol; crypto > `data_staleness_crypto_s` (e.g. 30s).
- **Alert ladder:** WARN → log + daily report; CRITICAL → immediate Telegram (+ secondary path). Any `HALT` pages immediately.
- **Daily brief gains a "system health" section** (heartbeats, staleness, data-quality score, reconciliation status, lockbox-budget status, LLM spend, allocation state).

---

## 38. Daily-auth autonomy (honest about the one touch-point)

- **Plane decoupling (MUST):** an **equity (Kite) auth failure halts ONLY the equity plane**; the **24/7 crypto plane (HMAC-keyed, no daily OAuth) continues independently.** The shared state machine must not let equity-auth wedge crypto. Tested.
- **Retry/backoff:** retry OAuth across the pre-open window; if still failing, emit an explicit **"equity-disabled-today"** line in the daily brief. A single successful token covers the whole equity session (valid until ~6 AM next day).
- **Mode flag `daily_auth_mode: one_tap | totp_auto`.** Honest default = **`one_tap`**: a pre-generated login URL pushed to Telegram at a fixed pre-open time for a single tap. **`totp_auto`** (scripted TOTP) is an explicitly **operator-owned, at-own-risk** module behind the flag — never the silent default, because automating 2FA is a security/ToS posture the operator must consciously accept.

---

## 39. Resource governance, schema evolution & consolidated `goal.yaml` v2

**39.1 Inventor resource governor (autonomy must not become self-DoS or runaway cost).** `goal.yaml` budgets: `max_candidates_per_day`, `max_llm_spend_per_day_inr` (hard stop → skip cycle + log). **Research/backtest work is niced and never preempts the live execution plane** (systemd `CPUWeight`/`MemoryMax`; run heavy backtests in `RESEARCH`/`SLEEP`, pause if the live plane needs the 2 GiB box). **Thrash guard:** no promotion of a variant within `thrash_guard_hours` of demoting its sibling.

**39.2 Schema evolution.** Message schemas live in one versioned module (`common/schemas`). **Additive/minor changes (new optional fields) are back-compatible and must NOT halt;** reserve the hard `SchemaError`-halt for **major** version mismatches. Major bumps require draining the relevant streams on deploy. (Postgres already uses Alembic.)

**39.3 Consolidated `goal.yaml` v2 additions** (merge into §15; these win on conflict):
```yaml
data:
  timezone_storage: UTC
  equity_session: NSE
  point_in_time_universe: true
  survivorship_control: true               # PIT universe; penny/SME universe banned
  corporate_action_adjust: back_adjust     # splits/bonus/rights; dividend convention fixed
  data_quality_gate: true
  min_oos_calendar_span_days: 250           # >= ~1 stress episode; weight daily+ evidence
execution_realism:
  fill_requires_trade_through: true         # touch != fill
  queue_volume_multiple_k: 2.0              # bar vol must exceed k x order size to fill
  next_bar_execution: true                  # no same-bar look-ahead
  latency_ms: 750                           # conservative decision->fill latency
  model_partial_fills: true
  max_participation_of_depth: 0.05          # capacity/impact cap (<=5%)
overfitting:
  lifetime_trial_ledger: true
  cumulative_effective_n: true
  haircut_method: BHY                       # Harvey-Liu multiple-testing
  gate_on_sharpe_lower_bound: true
  small_sample_shrinkage: true
  lockbox_eval_budget: 50
  lockbox_rotation_days: 90
  benchmark_equity: NIFTY50
  benchmark_crypto: BTCINR
  min_alpha_after_cost_tax: 0.0
  max_benchmark_r2: 0.8
trade_quality:
  min_quality_score: 0.6                    # tune on evidence
  rank_select_top_k: 1
  max_trades_per_day_per_strategy: 3
  min_holding_bars: 3
crypto:
  accrue_funding: true
  futures_roll_days_before_expiry: 2
  expiry_buffer_hours: 12
  options_enabled: false                    # no crypto options until DSL supports Greeks
allocation:
  max_concurrent_strategies: 4
  allocation_method: risk_parity_capped
  correlated_strategies_share_slot: true
recovery:
  startup_state: RECOVERY
  three_way_reconcile: true
  halt_on_unresolved: true
  require_broker_side_stop: true
resilience:
  datastore_down_action: halt
  bus_consumer_groups: true
  bus_dead_letter: true
  bus_maxlen_approx: 100000
  backup_interval_min: 20
  cancel_on_disconnect: true
  ntp_required: true
  secondary_alert_channel: email
observability:
  heartbeat_interval_s: 5
  heartbeat_miss_threshold: 3
  data_staleness_equity_s: 10
  data_staleness_crypto_s: 30
auth:
  daily_auth_mode: one_tap                  # one_tap | totp_auto (totp = operator-owned risk)
  equity_auth_failure_isolates_plane: true
learning_budgets:
  max_candidates_per_day: 12
  max_llm_spend_per_day_inr: 200
  research_never_preempts_live: true
  thrash_guard_hours: 24
```

---

## 40. v2 changelog (what Part II added vs Part I)

Agent count is unchanged (12 domain agents) but each is now explicitly decomposed into **task sub-agents** (§28). New first-class requirements: **autonomy/decision-rights ladder** (§27); **PIT/survivorship/corporate-action/data-QA** integrity (§29, supersedes the penny-stock example universe); **LIMIT fill model + next-bar execution + capacity** (§30); **overfitting-at-scale ledger, lockbox rotation, haircut Sharpe, confidence-bound gating, benchmark/alpha** (§31); **trade-quality score + anti-overtrading + execution-quality loop** (§32); **crypto funding/roll/expiry, options scoped out** (§33); **strategy lifecycle + cross-strategy allocation + demotion-with-open-positions** (§34); **RECOVERY state + exactly-once orders** (§35); **datastore/bus/kill-switch/concurrency/SPOF resilience** (§36); **heartbeat/staleness SLOs** (§37); **daily-auth plane decoupling + mode flag** (§38); **resource governor + schema evolution + consolidated `goal.yaml` v2** (§39). Unchanged and protected: deterministic execution plane, numeric gate as the only plane-crossing, costs/tax inside every decision, hard 2× leverage ceiling, the Phase-1 STOP gate.

---

---

# PART III — Post-review amendments (authoritative where they extend Parts I & II)

*Added 2026-08-01. Source: an LLM council review of Phases 0–2 (`docs/reviews/council-2026-07-31-prd-phases-0-1-2.md`), a measured trade-count study (`docs/reviews/trade-count-feasibility.md`), and a strategy-primitive survey (`docs/strategy-research/primitive-catalogue.md`). Every finding below was verified against the repo before being adopted; two of the council's most forceful claims **failed** verification and are recorded as failures in §41.6 rather than quietly dropped.*

## 41. Amendments

### 41.1 The Phase-1 stop gate is pre-registered (supersedes §22's Phase-1 deliverable)

§22 defined the Phase-1 exit as *"produce an honest metric sheet… operator reviews Phase-1 evidence before Phase 2."* That is a **deliverable, not a threshold** — the only gate in the plan with no acceptance criteria, and one that could not be failed. All five council advisors reached this independently.

**Amendment.** The gate's numbers live in `goal.yaml → stop_gate`, fixed **2026-08-01 before any backtest existed**, with the pre-registration date pinned in `common/config.py` so re-dating the block fails at startup. Gating is on the **Sharpe lower confidence bound**, never the point estimate; PBO ≤ 0.50; trade-count tiers 100/30 where `NEEDS_MORE_DATA` may never decay into `PROMOTED`; ≥3y OOS spanning a ≥15% benchmark drawdown; and **both** tax stress scenarios (crypto VDA *and* equity business-income — §6 previously stressed only the crypto reading).

**The governing rule (CLAUDE.md invariant #25):** a failing strategy receives no money, and **the gate is not renegotiated after results are seen.** If every candidate fails, change the *input* — intraday data, a different strategy class, the India-specific feeds — never the bar.

### 41.2 The trial ledger counts human attempts (extends §31)

§31's overfitting ledger counted Inventor-generated candidates. **In Phase 1 the operator is the only searcher**: every hand-authored strategy, re-tuned parameter and re-run is a trial. Counting only machine trials leaves DSR/PBO blind during the exact phase they exist to protect. Now CLAUDE.md invariant #24.

### 41.3 Sim forward-running is split into replay and live modes (supersedes §22 / task 1.10)

The ≥30-trade sim requirement applied a **statistical** threshold to a test whose real jobs are **operational**. Measured trade rates (§41.7) put the cost at 4–20 months of pure waiting.

The three questions are separable:

| Question | Mechanism | Calendar cost |
|---|---|---|
| Does the edge exist? | Walk-forward + single-use lockbox on history | **zero** |
| Is there a look-ahead bug? | **Replay mode** — historical bars through the *live* path, future bars physically absent | **zero** |
| Does the machine work? | **Live mode** — real clock, real data, no broker write | ~3–4 weeks |

A backtest cannot detect its own look-ahead bug, because the bug and the test share one dataset. Replay can, and adds a stronger check: **replay must reproduce the backtester's signals bar-for-bar**, or one of them is cheating. Live-mode acceptance is **event coverage** (one auth cycle, one restart-with-open-position, one reconciliation, one disconnect/reconnect), not trade count.

**And the canary is the real live test.** At 0.125% risk on ₹25k a canary trade risks **₹31**. Four months of simulation to avoid risking ₹31 per trade is a bad exchange of calendar for confidence.

### 41.4 Data split fixed (extends §13, §29)

Walk-forward **2011-01-01 → 2022-12-31**; lockbox **2023-01-01 → open-ended** (882 sessions; verified to contain two ≥15% drawdowns: Sep-24→Mar-25 at 15.8%, Jan-26→Mar-26 at 15.2%). Loader-asserted non-overlapping and single-use. **The price, stated plainly:** all iteration happens on the walk-forward window; a second look at the lockbox makes it training data.

### 41.5 Risk amendments (extend §14)

- **`max_open_positions` 3 → 4.** *Derived, not chosen*: `max_portfolio_heat / per_trade_risk_r` = 2% / 0.5% = 4. The old 3 was stricter than any risk limit required. The loader now asserts `positions × per-trade-risk ≤ heat` so the two controls cannot contradict.
- **Stagnation halt (invariant #23).** Every §14 kill-switch fires on a *fast* loss; nothing fired on a slow compliant bleed — which §23 itself calls the most likely outcome. After 50 closed live trades, if net-of-cost-and-tax P&L ≤ 0 **and** the CI on mean R includes zero → halt, demote, alert.
- **Position quantisation (new task 2.1b).** Equities trade in whole shares and the seed-tier risk model cannot express itself in them: at ₹25k/0.5% the rounding error is 4% at ₹500/share, **36% at ₹2,000**, and above ~₹3,000 the position is **inexpressible**. No lot/rounding logic existed anywhere in the repo. Sizing must round, report the induced risk error, and **veto** rather than silently round. Note this implies an unwritten *price ceiling* to sit alongside §29.2's written floor.

### 41.6 Council claims that failed verification

Recorded because a review that is never wrong is a review that was not thinking.

- **"D3 hides the infrastructure cost."** ✗ `BUILD_MAP.md` §5 already states, unprompted, that ~₹3,000/mo is 10–12% of a ₹25–30k account monthly and that *"the system cannot out-earn its own hosting bill at seed scale."* D3 also *requires* the ₹500 as its own line in the metric sheet. Phases 0–1 cost ₹700–1,200/mo, not ₹3,000.
- **"SEBI algo approval may be per-strategy, forbidding Phase 3."** ✗ §8 already establishes that below the 10 OPS ceiling no full per-algo registration is required — a *generic* algo-ID via the broker suffices, which is why the governor is pinned at ≤2 OPS. Worth re-confirming with Zerodha (O1); not a structural hole.

### 41.7 Measured facts adopted into the spec

- **Trade count is arithmetic, not an emergent property:** `trades/year = max_open_positions × 252 / median_holding_days`. Signals never bind — a 20-symbol universe yields ~50 signals/yr against 18–84 slot-turnovers. Measured: MA(20/50) cross **18/yr**, Donlevey sweep **84/yr**, monthly cross-sectional momentum **36/yr**.
- **Three India-only NSE feeds are free, daily and historical** (verified live 2026-07-31): security-wise delivery qty/% (2011→ via legacy `MTO`, 2019→ via `sec_bhavdata_full`), participant-wise F&O OI/volume split FII/DII/pro/client (2015→), and the daily F&O ban list. New task **1.1d**. These are the only inputs in the primitive catalogue the global quant industry has not mined, because they exist only in India.
- **The DSL carries cross-sectional primitives from the outset** (§12.1 extended), which obliges the backtester to be **universe-parallel rather than symbol-serial** — cross-sectional rank at bar *t* needs every symbol's bar *t*.

### 41.8 Claude Agent SDK: not for the runtime

Evaluated and declined for Icarus's runtime. The money path must be deterministic and replayable for the audit log, and an LLM loop with filesystem/bash capability near broker credentials contradicts invariants #1, #2 and #9. The research plane is the one architecturally safe home (it holds no credentials by invariant #1), but the Inventor's actual job — structured input → one `StrategyCandidate` + hypothesis — is a few **Messages API** calls with a JSON schema and needs no shell. In a system whose founding principle is capability minimalism, **extra capability is a cost, not a feature.** Revisit at Phase 3+ if multi-step diagnosis outgrows single calls.

---

*End of PRD v2.1. See `CLAUDE.md` for engineering conventions + safety invariants and `TASKS.md` for the phase-by-phase build checklist with acceptance criteria.*
