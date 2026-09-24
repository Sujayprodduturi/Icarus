# Trade lineage and bounded self-improvement — draft spec

**Status:** Proposed, not build-ready for Phases 2–3. The operator approved the aim and clarified on 2026-09-24 that “timing” means both strategy entry/exit decisions and order execution timing. This document does not authorize a live-order path or change the Phase-1 task order.

## Problem

Icarus can simulate trade prices, fills, costs and exit reasons, but it cannot yet reliably answer *why this trade happened, what information was known then, what the broker did, and what a different decision would have changed*. A collection of P&L numbers cannot support honest self-improvement. Missing lineage also makes it easy to mistake better fills for a better strategy, or a lucky market period for skill.

## Observable outcomes

1. The operator can trace each signal—traded or skipped—from the strategy version and decision-time inputs through risk checks, orders, fills, close and net outcome.
2. The operator can separate strategy selection and entry/exit timing from execution quality, costs, market drift, regime, capacity and risk vetoes.
3. A proposed improvement states one falsifiable change and a predicted effect, records every evaluation as a trial, and can be followed through rejection, canary, promotion, demotion or rollback.
4. No learned observation or LLM output changes live limits or live strategy code directly.

## Phase-1 slice: measurement, not autonomy

Task 3a records a stable run ID, signal ID, strategy/spec identity, decision bar and timestamp, emitted signal, typed skip reason, entry/exit fills, gross outcome, itemized costs, net-before-tax outcome, holding bars and source-data/config/code provenance. Assert that every emitted signal becomes exactly one completed observation or an explicit skip. The signal diagnostic has no portfolio equity curve and no promotion authority.

The existing portfolio test retains its after-tax account-level gate. Its later metric-sheet work exports trade records and matched-window comparisons, but does not allocate account-level tax to individual diagnostic trades as if that were an observed fact.

## Phase-2 slice: real trade lineage

The durable event chain is: strategy signal → risk decision or veto → order intent → broker acknowledgement → partial/full fills → position changes → close → reconciliation. Each event carries stable correlation, signal, strategy version and order IDs; UTC decision and event times; point-in-time context; rationale; expected versus realized price/cost; and hashes of the data, code and config that produced the decision. Record attempted and rejected actions as well as trades. Audit append and state mutation must be transactionally consistent. A missing link or reconciliation drift halts the affected trading plane.

Execution timing is evaluated separately from the strategy rule: decision-to-send delay, broker round-trip, time to fill, fill probability, price improvement/slippage, partial fills, cancels, adverse selection and opportunity cost of no-fill. Daily bars alone cannot validate intraday timing; collect suitably timestamped live or approved intraday data before claiming improvement.

## Phase-3 slice: bounded self-improvement

The research plane may diagnose performance by strategy version, regime, holding period, entry/exit rule, execution behavior and cost. Each cycle proposes one typed, white-box candidate change with a parent version, hypothesis, predicted metric delta, evidence links and trial ID. A strategy-timing hypothesis and an execution-timing hypothesis are different change classes and are tested separately. Learning from outcomes may prioritize *which hypothesis to test next*; it does not turn a retrospective pattern into a live rule.

Every *strategy* candidate passes the numeric strategy-validation process and versioned registry before any promotion. Execution-policy candidates remain research proposals until their permitted representation, benchmark, uncertainty test and separate validation contract are explicitly approved; the strategy gate alone cannot validate a fill-policy change. Real positions retain the exit rule/version under which they opened. Canary results, demotions and rollbacks are linked to the originating hypothesis. Meta-learning uses forward live outcomes, not repeated looks at the final historical lockbox. The research plane has no broker credentials and no network path to any broker; Risk and Compliance limits remain non-overridable.

## Verification seams

- Replaying one synthetic scenario reproduces the same ordered signal/skip/trade lineage and rejects missing or duplicated IDs.
- Fault injection proves that an audit-write failure, an orphaned fill, or a reconciliation mismatch halts rather than silently discarding evidence.
- A candidate cannot reach promotion without a recorded trial, complete validation evidence and a registry transition; an LLM-generated instruction cannot become an order.

## Out of scope now

No live order code, automatic strategy promotion, broker execution-timing optimization, new risk threshold, revised tax rule or use of the lockbox in Phase 1. This spec does not assume that every observed performance difference is causal.

## Open questions for later approval

- Which approved intraday/quote/depth feeds and timestamp precision will support execution-timing comparisons?
- What exact benchmark and uncertainty test will determine whether an execution-policy change is better after costs, no-fills and adverse selection?
- What retention, access-control and data-minimization policy will apply to detailed live context beyond the existing minimum audit retention?
- Which operator-facing views make the lineage understandable without hiding losses, skips or uncertainty?

Existing commitments: `PRD.md` §§9, 12–13, 19, 27, 31, 35–36; `AGENTS.md` invariants 1–4, 9–10, 15–19, 21–26; `OPERATOR.md` D15–D17. Current code evidence: `icarus/engine/portfolio.py`, `icarus/engine/fills.py`, `icarus/state/models.py`, and `icarus/state/audit.py`. The generic audit writer exists but is not wired into runtime decisions yet.
