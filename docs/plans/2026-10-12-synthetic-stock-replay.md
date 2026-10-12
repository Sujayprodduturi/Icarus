# Synthetic stock execution replay and benchmark connection — 2026-10-12

The operator directly requested this build. Under D47's major-milestone cadence,
implement the reviewed bounded unit below without another routine approval pause.
This schedules an isolated invented-data prerequisite of the September timing
design, not adoption of the full M15 strategy/portfolio lane.

## Scope and outcome

One pure `scripts/research/synthetic_execution_replay.py` and focused unit tests.
Replay one long-only, fixed caller-sized hypothetical stock trade; preserve its
daily SignalId and source-session index. Return immutable attempted/filled legs,
quantities, itemized modeled charges, timing precision and explicit refusals.
Connect the trace through a public adapter to the existing `match_benchmark`.
No stock alpha/excess, tax or promotion output. No generic provenance framework,
CLI, I/O, dependencies, sizing/cash/heat engine or strategy-card integration.

Daily engines, matcher policy, goal, cards, calendars and ledgers remain unchanged.
A separate minimal READY_SEALED repair to the research runner is necessary because
the exact prior c520017 full CI failed its duplicate-READY no-payload invariant.
That repair changes no study, statistical protocol, sample, retry or budget. The
old frozen study source remains historical; no fresh qualification is inferred.

## Declared fixture and causal clock

Immutable sessions and exact 15-minute partitions carry chronological UTC bounds,
full-source session indices and checked synthetic source/schema/hash declarations.
Prices are positive finite Decimal, volume finite nonnegative, OHLC consistent.
Coverage of expected sessions/bars/refinement must be checked before any replay;
missing/conflicting/out-of-session refinement refuses, never silently skips.
All windows and each session remain within one IST date so fee dates cannot be
invented across an unresolved midnight. Special windows are synthetic declarations,
not exchange-calendar or vendor certification. Constructor errors reject malformed
types/values; well-typed missing coverage has a typed unavailable outcome.

A daily decision is available at or after its declared session close. Configured
latency determines activation; entry occurs only in the next declared session,
at the first eligible whole-bar open. An activation inside a bar skips that bar,
never creates an invented subbar event. Entry is attempted once. Actual partial
entry quantity becomes original Q; cancel the remainder. No fill is no trade.

Every opening fill requires separately declared opening-liquidity proxy/depth with
availability no later than that open. Its absence/future availability refuses the
opening execution. The proxy is a fixture modeling assumption, not real depth.
Use it, not future whole-bar volume, for opening fill capacity. Keep its event
convention visibly MODEL_OPEN_EVENT; raw FillResult.ts alone proves no exact time.

## Orders, capacity and exits

Reuse existing FillModel adverse gap/slippage/tick, strict resting trade-through,
queue, participation and partial/no-fill rules. One shared per-bar allowance is
bounded by declared opening proxy times configured participation. Intrabar fills
are additionally bounded by whole-bar participation/queue constraints recognized
at bar end. All actual fills consume shared capacity; never shrink a requested
intent to evade queue requirements or the partial-disabled all-or-none rule.

Opening sizing remains causal, but the completed bar must support the candidate
quantity under the unchanged realized-volume participation cap. An inconsistent
candidate produces LIQUIDITY_UNAVAILABLE, never retroactive future-informed resizing.
Retain the refusal/attempt evidence; the unsupported candidate is not a validated
executed leg and cannot consume sale fees or yield a benchmark return. This is
fixture reconciliation after observation, not information available at the open.
The positive causality witness varies future volume between two sufficient values
and gets the same opening quantity; an insufficient realized-volume companion
refuses. Depth proxy and realized traded volume need not themselves be equal.

Protective stop and optional resting target activate at entry fill plus configured
latency. If the entry bar could have crossed either level before activation, halt
this replay with PATH_ORDER_UNAVAILABLE, preserve remaining quantity and invent no
sale. A carried active stop crossed at open can use the modeled opening event.
A non-gap stop or resting target inferred inside M15 remains BAR_RESOLVED over the
whole interval, without an exact event timestamp. Native stop trigger is not a new
client submission: placement latency is already paid. Once triggered, a no-fill
or partial stop stays latched and attempts marketably at later eligible opens,
even after a rebound. Target residual retains its limit. If both active stop and
target are possible inside one unresolved interval, refuse ordering rather than
select an invented sequence. One exit attempt per bar after causal selection.

Time stop counts distinct held declared sessions, entry session included, not M15
bars. Holding session N makes the exit due at its first eligible open; N=1 cannot
exit at entry instant, its timer intent pays entry-plus-latency and rounds forward.
At an open, known active gap/latched protective stop precedes a due timer; the due
timer precedes unknown later intrabar events. This causal ordering is explicit and
does not claim equality with the unchanged daily whole-bar protective-first ladder.

Terminal unsold residual stays open. No forced sale, stale execution or fake charge.
Use a fresh DeliveryFeeContext per trace and existing CostModel: actual modeled
entry and exit charges only, DP once per symbol/IST day over actual sale fragments.
Coarse intrabar recognition is bar end on that same validated IST date. No complete
trade P&L or return is claimed when inventory remains open.

## Actual benchmark connection

Derive matcher Timing from execution branches. Modeled opening events can be
EVENT_RESOLVED only under the explicit causal price/proxy convention. Intrabar
legs are BAR_RESOLVED with event_ts absent, bounds start/end, and coarse price-source
and recognition at bar end. Preserve raw bar labels separately.

For every filled entry, build SyntheticTrade using actual original Q and every
executed exit fragment, then call the real existing matcher, including incomplete
exit quantities. It then returns quantity mismatch/None for residual inventory.
No-entry has a typed no-trade result instead of constructing invalid Q=0. Ordering
refusals cannot become a whole-trade value. Match exact observed benchmark times
and unchanged expected identity under the existing zero-age synthetic policy;
no nearest/asof/interpolation, subset renormalization or fabricated index quotes.
Declared identities/hashes do not authenticate real sources.

## Acceptance and proof

TDD witnesses cover next-session availability/latency, late/missing proxy, missing
refinement, session-count invariance, special windows, strict target touch/queue,
partial-disabled and partial fills, shared capacity, activation and both-hit refusal,
stop residual persistence, gap EVENT versus intrabar BAR precision, same-day and
next-day DP, terminal inventory, missing benchmark legs and an unequal-fragment
exact Fraction hand calculation through the public adapter. Keep daily golden
unchanged. Run focused/related regression, strict mypy and global Ruff/format.
Independent simplicity then engineering review plus root independent arithmetic
checks must pass. Freeze runtime and review bytes before commit. Run meaningful
known-bug source mutations only after commit, restore exact bytes, rerun positives.

No market data, actual trial-ledger activation, new sampled study, cleanup, M4/
statistical adoption, lockbox, inference, broker or live order path is authorized.
Full dual-engine/card integration and authoritative source/calendar matching stay
separate next tasks; this unit must be reported as a preset synthetic trade replay.
