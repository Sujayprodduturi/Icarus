# Task for Icarus Claude Code — Evaluate HKUDS/Vibe-Trading vs. our build

## Why you're reading this
Sujay found an open-source agentic quant platform that natively supports Indian markets. Before we keep building Icarus blind to it, evaluate it **honestly** and tell us: what to borrow, what to keep as ours, and whether to build / adopt / hybrid. **Do not merge or copy anything yet — produce a written evaluation first.**

## The repo to evaluate
- **HKUDS/Vibe-Trading** — https://github.com/HKUDS/Vibe-Trading (MIT license, ~28k★) · install: `pip install vibe-trading-ai`
- Built by the **Data Intelligence Lab @ University of Hong Kong** (same lab as LightRAG) — legit, not a fork of Qlib / TradingAgents.
- What it ships: **456 alpha factors** (Qlib-158, Kakushadze-101, GTJA-191, academic), **79 finance skills** (8 categories), **~29 agent "swarm" presets** (investment committee, quant desk, risk committee…), **Monte-Carlo backtesting + portfolio optimization**, and **Indian-market connectors: Dhan + Shoonya, NSE/BSE equities + F&O, read-only / paper mode**. Runs as CLI, Web UI, REST API, and an **MCP server**.
- ⚠️ Do NOT confuse with the unrelated clone `hopit-ai/india-trade-cli`. Use the HKUDS one.

## Icarus (what we compare against) — recap
- Autonomous multi-agent trading system: Indian equities, index F&O, crypto.
- Two planes: **fast execution** + **slow research**. Constrained **strategy DSL**. Hard **quant gate** before any strategy goes live: **Sharpe ≥ 1.3, Sortino ≥ 1.5, Calmar ≥ 1.0**. **SEBI-compliant by design.** Brokers: **Zerodha primary, Upstox failover.**

## Your deliverable — a structured evaluation report
1. **Clone + read** it. Start with: the alpha-factor "zoo", the backtesting engine, the Dhan/Shoonya broker connectors, the agent/swarm architecture, and the MCP server interface.
2. **Overlap map** — what Vibe-Trading does that Icarus also does.
3. **Borrow list** — concrete modules we could REUSE to accelerate Icarus (the 456-factor library? the Monte-Carlo backtester? the Indian data/broker plumbing? agent patterns?). Name the actual files/modules and how hard each is to lift.
4. **Our moat** — what Icarus has that Vibe-Trading lacks: the execution plane, the constrained strategy DSL, the Sharpe/Sortino/Calmar gate, Zerodha/Upstox failover, SEBI-compliance design. Be specific.
5. **Recommendation — build / adopt / hybrid.** Give an honest call. Pressure-test this likely-best hybrid: *use Vibe-Trading's research + factor + backtest layer, and keep Icarus's execution plane + quant gate + broker failover on top.* Argue for or against with evidence from the code.
6. **Risks / caveats** — MIT license (fine to reuse), read-only/paper only (live execution is ours to add), Dhan/Shoonya vs our Zerodha/Upstox (how much work to bridge?), code quality, maintenance, dependency weight.
7. **First concrete step** you'd take if we go hybrid.

Flag anything you cannot verify from the actual code. Don't overstate — a clear "keep building Icarus, here's why" is a valid answer if that's what the code shows.
