# Project Icarus — Build Map & Doc Review

> Companion reference to `PRD.md`, `TASKS.md`, `CLAUDE.md`. Compiled 24 Jul 2026 · **last updated 30 Jul 2026**.
> A one-file map of what Claude Code is building, the operating cost of running it, and the open decisions.

**Verdict:** The docs are genuinely excellent — top ~5% of solo trading specs — and **build-ready**. But *build-ready ≠ profitable*. There is one issue (C1) that could quietly stall the self-learning premise, and a short fix list below. Current direction: **equity-delivery-first** (crypto deferred).

**Build state (30 Jul 2026):** Phase 0 ✅ complete. Phase 1 in progress — data layer (1.1, 1.1b, 1.1c), CostModel (1.5) and TaxModel (1.6) done. 291 unit tests, ruff + mypy clean. **C1 is now measured, not argued** — see §6.1.

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

| Phase | What | Needs capital? | Status |
|---|---|---|---|
| **0** | Skeleton & safety rails — bus, Postgres, BrokerAdapter, Compliance, kill-line. Authenticates, streams data, **can place nothing**. | No | ✅ complete |
| **1** | Data + sim + metrics — CostModel + TaxModel, walk-forward backtester, metrics + DSR, testnet/sim runner. | No | 🔨 data layer + CostModel done; DSL, TaxModel, backtester, metrics, DSR to go |
| 🛑 | **PHASE-1 STOP GATE** — produce a metric sheet for ONE hand-written strategy, hand to operator, **pause**. No live-order code before this review. | — | ⏳ not reached |
| **2** | Live execution — Risk + Execution + Portfolio + all kill-switches + Telegram kill. Micro-live, real money, tiny. Does **not** self-modify yet. | **Yes — first capital + static IP here** | ⏳ not started |
| **3** | Learning loop — Inventor + gate wired end-to-end. Versioning + hypothesis meta-learning. | Yes | ⏳ not started |
| **4** | Oversight + harden — full daily report, rollback, reconciliation hardening, chaos tests, tax-ledger export. | Yes | ⏳ requirements level |
| **5** | Scale — only on live evidence. Widen universe, raise tiers, expand primitives. **Leverage cap never loosens.** | Yes | ⏳ requirements level |

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

**Accounting decision (Sujay, 30 Jul — D3):** this bucket is **capital investment in the business**, not a cost of a trade. The CostModel therefore does *not* amortize the Kite ₹500 into per-trade cost or the strategy hurdle, which PRD §7.1 had suggested. The reasoning: it is fixed whether or not Icarus ever trades, and charging it against a strategy's edge would make every per-trade figure depend on an assumed monthly trade count.

**The consequence, stated so it cannot get lost:** every strategy metric Icarus reports is **before infrastructure cost**. The cash still leaves the account, so this table is the accounting home for it, and the ₹500 must appear as its own explicit line in the daily Telegram report and in the Phase-1 metric sheet — never netted silently into strategy P&L. A strategy that clears its gate is not the same thing as a month that made money.

**The hard truth (unchanged by the accounting choice):** this cost is *fixed, independent of your capital or trade size.* At a ₹25–30k seed, ~₹3,000/mo is 10–12% of the whole account every month before a single trade; at ₹2–3k it's economically absurd. **The system cannot out-earn its own hosting bill at seed scale** — the operating cost is part of the tuition, not a profit centre. Calling it capital rather than cost changes which ledger it sits in, not whether it has to be paid.

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

## 6. Enhancement register (status as of 30 Jul 2026)

| ID | Sev | Finding | Status |
|---|---|---|---|
| **C1** | CRITICAL | Seed-tier order math may never produce a placeable trade → system idles, never hits the ≥30 live trades needed to learn/tier-up. Equity at ₹2–3k fails hardest (share-price lumps + ₹15.34 DP charge). | ✅ **MEASURED** (1.5, 29 Jul) — confirmed *and bounded*: fatal below ~₹10k, workable at ₹25–30k. See §6.1. Seed number still the operator's call. |
| **H1** | HIGH | Banned `liquid_lowprice_nse` universe still in §20 example strategy.yaml (§29.2 bans it). | ✅ **APPLIED** → `liquid_largecap_nse` |
| **H3** | HIGH | Delta cancel-on-disconnect is load-bearing for the 24/7 crypto plane but only "verify at build". | **HELD** — deferred with crypto; make it a hard Phase-2 gate when crypto is enabled |
| **M1** | MED | §9.5 state-machine diagram omitted RECOVERY (invariant #16 requires it). | ✅ **APPLIED** |
| **M2** | MED | No explicit pytest/CI scaffold task in Phase 0. | ✅ **APPLIED** → TASKS 0.1b |
| **M3** | MED | Reflection cadence (N=5) vs belief threshold (≥30 trades) mismatch → early reflection chases noise. | ✅ **RESOLVED** — `reflection_every_trades` locked at 15 (per-strategy) at seed |
| **M4** | MED | Time-to-first-evidence is months and isn't stated. | ✅ **MEASURED + RESOLVED** (1 Aug) — see §6.2. It was not a documentation gap but a near-design-falsifier: `trades/yr = max_open_positions × 252 / hold_days` gives **18/yr** for an MA cross. Fixed by splitting 1.10 into replay + live modes (statistical vs operational) and by 3→4 slots. Verdict moves Apr-2027 → **Nov-2026** with no standard lowered |
| **M5** | LOW | 2 GiB VM may OOM on walk-forward/CPCV backtests. | Open — benchmark memory in Phase 1. **Now larger:** 1.7 must be universe-parallel for cross-sectional primitives, so peak memory scales with universe size, not one symbol |
| **M6** | MED | `max_open_positions` and `max_portfolio_heat` are two controls over one quantity and can silently disagree (3 proven at 0.5% + 4 canaries at 0.125% is also exactly 2%). | Open — loader now **asserts** `positions × per_trade_risk ≤ heat` so they cannot contradict. Deriving the count from the heat budget is a later refactor |
| **M7** | HIGH | Position sizing is inexpressible in whole shares at seed capital, and no lot/rounding/quantisation logic exists anywhere in the repo (verified 1 Aug). At ₹25k/0.5% risk: 4% rounding error at ₹500/share, **36% at ₹2,000**, **impossible above ~₹3,000**. | Open → **TASKS 2.1b**. Compounds with `min_close_inr: 30`: a floor is written down, the implied ceiling is not |
| **M8** | HIGH | Every kill-switch is drawdown-triggered. Nothing halted a slow, perfectly-compliant bleed — the outcome PRD §23 itself calls most likely. | ✅ **RESOLVED** (1 Aug) — stagnation halt, **invariant #23**. Flatness-triggered, not drawdown-triggered |
| **M9** | HIGH | The DSR/PBO trial ledger counted Inventor candidates but not hand-authored ones. In Phase 1 the operator is the *only* searcher, so the multiple-testing guard was blind exactly where it mattered. | ✅ **RESOLVED** (1 Aug) — **invariant #24**; TASKS 1.9 AC now requires a hand re-run to increment the ledger |
| **D1** | DECISION | Crypto-first was a single point of fragility (contested tax + leverage + only viable seed surface). | ✅ **DECIDED: equity-first**, crypto deferred (revises locked decisions #5/#6) |
| **D2** | DECISION | 12-agent × sub-agent mesh is heavier than ≤2 OPS justifies. | Open — keep plane isolation + single writer; consider leaner Phases 0–2, defer full mesh. **Council (31 Jul) split three ways and did not settle it:** trim to the three boundaries that carry credentials; *or* the shape is fine but is pre-committed to a trade frequency the capital can't afford; *or* marginal cost per agent is one supervised task, so it's cheap optionality. Two of three reviewers held that the binding constraint is operator calendar, not capability |
| **D7** | DECISION | The Phase-1 stop gate had no numbers — a deliverable, not a threshold, and the only task with no AC. | ✅ **DECIDED + PRE-REGISTERED 2026-08-01** — `goal.yaml → stop_gate`, fixed before any backtest existed, date pinned in code. **Invariant #25: the gate is not renegotiated after results are seen.** On a total failure the response is to change the *input*, never lower the bar |
| **D8** | DECISION | Where does the lockbox start, and can held-out history replace a live-clock sim forward-run? | ✅ **DECIDED** (Sujay, 1 Aug) — walk-forward **2011→2022**, lockbox **2023→now** (882 sessions; verified to contain two ≥15% drawdowns). Held-out history answers *"does the edge exist"*; **replay mode** answers *"is there a look-ahead bug"* at zero calendar cost; only *"does the machine work"* needs wall-clock, and that needs event coverage, not 30 trades |
| **D9** | DECISION | `max_open_positions` 3 → 4. | ✅ **DECIDED** (Sujay, 1 Aug) — **derived, not chosen**: heat cap ÷ per-trade risk = 2% ÷ 0.5% = 4. The old 3 was stricter than any risk limit required and cost 33% of the evidence rate for nothing. No limit loosened |
| **D10** | DECISION | Claude Agent SDK for Icarus's runtime? | ✅ **DECIDED: no, not yet** (1 Aug) — the money path must be deterministic and reproducible; an LLM loop with filesystem+bash near broker credentials contradicts invariants #1/#2/#9, and a non-deterministic decision can't be replayed for the audit log. The research plane is the one architecturally safe home (no credentials by invariant #1), but the Inventor's real job — structured input → one `StrategyCandidate` + hypothesis — is a few **Messages API** calls with a JSON schema. It needs no bash. Where capability minimalism is the founding principle, extra capability is a cost. Revisit at Phase 3+ if multi-step diagnosis outgrows single calls |
| **D3** | DECISION | Kite ₹500/mo: amortize into the per-strategy hurdle (PRD §7.1) or treat as capital? | ✅ **DECIDED: capital investment** (Sujay, 30 Jul) — same bucket as the PC. Metrics are *before* infra cost; the ₹500 gets its own reported line, never netted into strategy P&L |
| **D4** | DECISION | NSE cash txn charge: 0.00297% raw vs 0.00307% all-in incl. IPFT (Appendix B: "don't double-count"). | ✅ **RESOLVED, not chosen** (1.5, 29 Jul) — they are the *same total*. NSE circular 27 Feb 2026 (eff. 1 Mar) cut IPFT to ₹0.01/crore and raised txn charges to match. Use all-in **0.00307%**, never add IPFT separately |
| **D5** | DECISION | Dividend adjustment convention (§29.3 requires exactly one, applied in signal + cost + tax). | ✅ **DECIDED: price-return** (Sujay, 29 Jul) — adjust splits/bonus/rights, **not** dividends. The ex-date drop is real and a price strategy eats it. Consequence: Yahoo `adjclose` is banned |
| **D6** | DECISION | Equity delivery: business income or capital gains? (§6.1 "per classification".) Worth ~10pp of tax on every rupee. | ✅ **DECIDED: capital gains** (Sujay, 31 Jul) — Icarus places the delivery trades he would have placed himself; automating your own investment decisions doesn't make it a business. So STCG 20% / LTCG 12.5%, split on holding period. ⚠️ Unlike every other §6 default this is the *cheaper* reading, so **O7** (CA confirmation) stays open — a CA weighs holding period + frequency, not who clicks buy |

---

## 6.1 C1, measured — the seed-capital floor

The CostModel (1.5) turns C1 from an argument into arithmetic. Everything scales with position size **except** the ₹15.34 DP charge on every delivery sell — a flat rupee fee, so it punishes small accounts specifically. On an ₹11,000 delivery sell it alone exceeds every other charge combined.

The honest way to read it is as a fraction of the risk budget **R** — how much of a trade's risk is eaten by cost before it earns anything. At `per_trade_risk_r: 0.005` with a 3% stop (so position = capital × 0.005 ÷ 0.03) and the 1.5× cost hurdle:

| Seed | Position | Breakeven move | Need (1.5× hurdle) | as R | Verdict |
|---|---|---|---|---|---|
| ₹2,000 | ₹333 | 4.83% | 7.24% | **2.41R** | dead on arrival |
| ₹3,000 | ₹500 | 3.29% | 4.94% | **1.65R** | dead on arrival |
| ₹10,000 | ₹1,667 | 1.14% | 1.72% | 0.57R | marginal |
| ₹25,000 | ₹4,167 | 0.59% | 0.89% | **0.30R** | workable |
| ₹30,000 | ₹5,000 | 0.53% | 0.79% | **0.26R** | workable |

**Reading:** at ₹2–3k a trade must clear ~1.6–2.4R in cost *before it earns a rupee* — no strategy survives that, and the system would idle exactly as C1 predicted. At ₹25–30k it is 0.26–0.30R, which a 1.5–2R target absorbs comfortably. Indivisibility compounds the problem at the bottom: a ₹333 position cannot buy even 11 shares of a ₹30 stock, the universe's price floor.

So **C1 is real and bounded**. The ~₹25–30k floor is not a preference — it is where the arithmetic stops being hostile. Reproduce with `CostModel.breakeven_move`.

---

## 6.2 M4, measured — how long until we know anything

*Measured 1 Aug 2026 on real NSE daily bars (19 liquid names, 10.4 years). Full method:
`docs/reviews/trade-count-feasibility.md`.*

| Strategy archetype | Median hold | **Trades/yr** (3 slots) | Time to a 30-trade sim verdict |
|---|---|---|---|
| SMA(20/50) cross | 42 bars | **18** | **20 months** |
| Sweep + reclaim (Donlevey distillation) | 9 bars | **84** | 4.3 months |
| Cross-sectional momentum, monthly | ~21 bars | **36** | 10 months |

**Signals are never the constraint — slots are.** Even 20 symbols generate ~50 signals/year against
18–84 available slot-turnovers; at 500 symbols it is ~1,340. Universe size is irrelevant to trade
count. What decides it is arithmetic:

```
portfolio trades/year = max_open_positions × 252 / median_holding_days
```

Every term is a config value or a strategy property. **This needed no backtester and should have
been computed before the validation machinery was designed** — that is the process lesson, and it
is the reason this section exists rather than a note in the PRD.

**What it changed:**

1. The MA-cross baseline is **barred from live sim and canary** and kept as a backtest-only engine
   control. A 20-month wait to learn that a control strategy has no edge is not a trade worth making.
2. **Task 1.10 split into replay + live modes.** The ≥30-trade rule applied a *statistical*
   threshold to a test whose real jobs are *operational* (look-ahead detection, plumbing). Replay
   does the first at zero calendar cost; live-mode sim does the second in ~3 weeks on event
   coverage. Verdict moves from Apr-2027 to Nov-2026 **without lowering a single standard.**
3. **`max_open_positions` 3 → 4** (D9), lifting every count by 33% within the existing heat cap.
4. The operator's chosen direction survives on *structural* grounds: the sweep clears comfortably
   because it holds 9 days rather than 42 — independent of whether it has any edge.

**And the argument that settled the calendar question:** the canary *is* the live forward test. At
0.125% risk on ₹25k a canary trade risks **₹31**. Spending four months of simulation to avoid
risking ₹31 per trade is a bad trade — real fills, real slippage, real broker behaviour and real
auth gaps are things no modelled fill can tell you.

---

## 7. Current decisions & open items

- ✅ **Equity-delivery-first** to prove the machine; crypto stays in the architecture but deferred (Sujay, 24 Jul).
- ✅ **Kite ₹500/mo = capital investment**, not a trading cost (Sujay, 30 Jul — D3). Strategy metrics are therefore *before* infrastructure cost; the ₹500 must appear as its own line in the daily report and the Phase-1 metric sheet so it is never silently absorbed.
- ✅ **Universe filters** (Sujay, 29 Jul): ₹50cr 20-session average turnover, ₹30 close floor. The price floor is *not* about returns — profit is capital × percent move — it is a crude second liquidity filter, held deliberately low because indivisible shares make a high floor unsizable at seed.
- ✅ **Price-return convention** for corporate actions (Sujay, 29 Jul — D5).
- ⏳ **Seed number — OPEN, now with evidence.** Sujay leaned ₹2–3k; §6.1 shows that costs ~1.65–2.41R at that size, i.e. structurally unable to trade. **₹25–30k** brings it to 0.26–0.30R. Phases 0–1 need no capital, so it still doesn't block the build — decide at the Phase-1 stop gate.
- ⏳ **Hosting — OPEN.** AWS VM (~₹1,400/mo) vs home PC + ISP static IP (~₹200–500/mo). Equity-first makes the home PC viable (no 24/7). Decide at Phase 2.
- ⏳ Once seed + hosting are set: apply H3 + the equity-first rewrite of §2/§5/§22 + locked decisions #5/#6 in one clean pass. (C1 is now discharged by §6.1.)
- ⏳ **Verify before live capital:** re-pull the NSE transaction-charge circular from the primary source. The 1.5 rates rest on a circular summary plus Zerodha's live page (independent and arithmetically consistent) because the NSE PDFs would not extract.
- ✅ **The Phase-1 stop gate is pre-registered** (Sujay, 1 Aug — D7). Numbers fixed *before* any backtest existed and enforced in `goal.yaml → stop_gate`; the pre-registration date is pinned in code so re-dating it fails at startup. **Invariant #25: if every candidate fails, change the input — never the bar.**
- ✅ **Data split fixed** (Sujay, 1 Aug — D8): walk-forward 2011→2022, lockbox 2023→now, single-use, loader-asserted non-overlapping. **The real price:** all iteration happens on the walk-forward window. The lockbox is opened once, at the end. A second look makes it training data and any number from it means nothing.
- ✅ **Three stop-gate strategies** (Sujay, 1 Aug): MA-cross as engine control (backtest only), the Donlevey sweep, and a **reproduction of the 2026 SSRN cross-sectional-momentum claim** (~133% annualised / Sharpe 2.90 OOS on Nifty-50). Sharpe 2.9 from free data in India's 50 most-analysed stocks is ~3× what the best systematic equity funds sustain; survivorship, a 5× bull market, an optimistic cost model and a ±0.6 standard error are each likelier than a discovery. **Reproduce it in our own gate or don't cite it** — a survivorship-free reproduction returning 0.6 is *more* valuable than a pass, because it proves the engine catches what a paper got wrong.
- ⏳ **O8 — `objective.min_sharpe` 1.3 vs 0.70. OPEN, and must be closed before the first metric sheet exists.** 1.3 net of cost and tax on daily-bar retail equity is very demanding; Nifty buy-and-hold is ~0.5–0.7, so 0.70 means "beat doing nothing." The stricter 1.3 stays active until the operator rules. Resolving it *after* seeing a result would violate invariant #25.
- ⏳ **New feed work — TASKS 1.1d.** Delivery %, participant-wise F&O OI (FII/DII/pro/client) and the F&O ban list, all verified free and live 2026-07-31, historical to 2011/2015. The one class of input in the whole primitive catalogue that the global quant industry has *not* mined, because it only exists in India.

*Docs: `PRD.md` (v2.0, 1079 lines) · `TASKS.md` (phased, with progress) · `CLAUDE.md` (22 invariants) · `goal.yaml` (all thresholds + rate schedule). Build map compiled 24 Jul 2026, last updated 30 Jul 2026.*
