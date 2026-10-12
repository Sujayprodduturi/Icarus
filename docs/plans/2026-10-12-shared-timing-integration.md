# Shared strategy and portfolio timing integration — 2026-10-12

The operator's “Go ahead” schedules the next integration milestone under D47's
standing autonomous cadence. Independently review this concrete contract, then
build and prove it on deterministic invented data. The prerequisite a21dde7 passed
full hosted CI (3101 passed/four skipped) and its native-resource check. This build
is not real-data authorization, a statistical study or full seven-card readiness.

## Public behavior and scope

Add explicit `run_time_resolved` methods to EXISTING SignalSimulator and
PortfolioSimulator. Both use one incremental engine event loop. Actual M15 fills
drive their inventory, overlap, exits and, for portfolio mode, shared cash, slots,
heat and subsequent sizing. Never decorate completed daily trades with timestamps
or finance entries from precomputed future trade histories. Existing `.run`, its
daily records, runner/default routing and golden result remain unchanged.

First support ordinary daily entry/rank columns, equal_weight sizing, fixed
stop_loss_atr/stop_loss_pct, fixed optional take_profit_r/take_profit_pct and held
session time_stop. This covers the control, Donlevey, uptrend pullback, xs20 and
xs252 cards. Reject trailing_stop_atr, opposite_signal and any rebalance BEFORE
fills with explicit unsupported status. Donchian and low-volatility timed consumers
are the next increment; do not call all seven timed-ready or ignore their rules.
Only long cash-equity delivery is supported. No new capital/risk thresholds.

## Source and daily-clock contract

Use engine-owned immutable synthetic SourceDeclaration/Session/OpeningLiquidity/
ReplayBar records and Precision/Timing, extracted from the existing pure helpers.
Preserve their public research imports/identities and matcher monkeypatch hook.
Engine code cannot import scripts/research. Declarations/hashes are checked fixture
bindings, never authentication of vendor, exchange calendar, market depth or data.

Preflight complete immutable refinement for the original Panel symbols and full
source indices, chronological UTC sessions and exact M15 grids. Validate positive
finite consistent OHLC, nonnegative finite volume, expected source/hash/proxy
bindings and one IST date per session/window. Daily panel labels equal declared
session opens. M15 first open/max high/min low/final close/summed volume must match
the normalized Decimal daily OHLCV at the same source index. Missing/conflicting
refinement or aggregation refuses the run with affected symbols/source coordinates;
do not shrink the universe, drop delisted names or fall back to daily execution.
Malformed primitive/schema/type inputs fail construction/preflight.

Daily columns are consumed only at the declared session CLOSE. SignalId retains
the original daily open label and full-source index; decision availability is the
close, separately stored. A queued entry gets one attempt at the first latency-
eligible whole-bar open in the immediately next declared session. No same-session
or later-session rollover. Holding counts increment by distinct observed held
sessions, entry session included, never by M15 bars. N=1 pays entry-plus-latency
and rounds to a later eligible open. Final-close signals have no next-bar outcome.

## Incremental causal execution

Use a common synchronized OPEN / BAR_END / DAILY_CLOSE timeline across symbols.
At OPEN, previously activated latched/gap stops precede due session timers. Only
those actual modeled opening fills can release same-open cash/slots. Ordinary
queued admissions are checked after that opening batch, in deterministic current
rank/fallback order. ALREADY_HELD is assessed at the actual eligible admission
open, consistently in both views; never allow two live hypotheses for one symbol.
The daily default's historical ordering is not claimed identical to this lane.

Opening decisions and quantities use only pre-open book state, current opening
prices and separately declared proxies available by that instant. Stage the full
opening batch sequentially, including its cash/inventory effects, without consulting
future high/low or realized volume to select a different opening book. At BAR_END,
reconcile all opening candidates against realized participation. Any contradiction
invalidates/halt the WHOLE RUN: retain clearly provisional diagnostics and prior
inventory/cash, expose no valid final equity/performance, never retroactively resize,
erase an opening trade, continue from a favorable rollback or redraw the fixture.

Reuse FillModel exclusively for adverse prices/ticks, strict resting trade-through,
queue, participation, partial-disabled and no-fill behavior. A per-symbol/bar
allowance survives every open and end phase, including old exit/new entry; unrelated
symbols do not share one volume budget. Preserve original requested quantities for
queue/all-or-none checks. Partial/no-fill stop triggers remain latched through
rebounds; resting target residuals retain their limit. One exit attempt per holding
per bar, so an opening partial exit does not get another intrabar attempt.

Entry protection activates at actual entry plus configured latency. A bar crossing
stop/target before activation cannot establish ordering: halt/refuse the whole run
with inventory intact. An active non-gap stop or target inferred from OHLC remains
BAR_RESOLVED, no exact event timestamp. Both possible intrabar levels refuse order.
Opening fills use MODEL_OPEN_EVENT under the explicit proxy convention, not raw
FillResult.ts alone. Intrabar proceeds become available only after BAR_END, never
to earlier opening entries. Do not force terminal sales or stale executed fees.

## Money and result contracts

Signal mode sizes from its intended notional and adverse actual open price; original
Q is actual partial filled Q, with canceled entry remainder. It keeps independent
SignalId fee scopes and visible overlap/no-fill/missing outcomes. It is a diagnostic
exposure view, not a funded portfolio or evidence of risk-gate passage.

Portfolio mode serializes size-plus-commit using existing whole-share risk sizing,
concentration, heat, max-position and actual outlay/cash formulas. Reject strategy
risk_r above the supplied goal Risk.per_trade_risk_r even for handbuilt candidates.
Preserve the existing REALIZED-equity basis: starting equity plus realized net P&L,
allocating original acquisition charges proportionally to closed fragments. Cash
is separate and debits entry price*filledQ plus actual charges immediately; sells
credit actual proceeds less charges. Cash refusal does not resize to affordability.
Concentration may reduce size as already specified. Reassert filled-value, heat,
cash and slot limits after commit. One book-wide fresh DeliveryFeeContext allocates
DP once per symbol/IST day across all trades, unlike independent signal hypotheses.

Extract only bounded scalar sizing/charge-allocation helpers for use by BOTH the
unchanged daily path and timed portfolio path; prove daily parity. No alternate
Kelly, risk, stagnation or accounting framework. Terminal residual shares and their
cost basis remain visible. Valid daily closing equity is cash plus marked holdings;
closed P&L and cash/cost-basis identities reconcile exactly. Invalid runs expose
provisional diagnostics but valid final-equity/performance fields are None.

New immutable timed trade/run records store original SignalId, daily decision/
availability, actual entry Q/charges, execution legs with precision/interval/source
index/recognition/charges, remaining Q and typed completeness/refusal. Enforce
exitQ+remainingQ=originalQ; account for every emitted signal as accepted, discarded
or unavailable. Do not relax the old SignalTrade canonical daily-axis/full-exit
invariants. A thin research `match_timed_trade` adapter derives actual Timing/all
exit legs and original Q and calls the existing matcher; partial inventory or any
unavailable run cannot yield a valid whole-trade benchmark value. No strategy-
provided benchmark scalar, stock excess/alpha, tax, confidence or promotion output.

## Files and ordered proof

Engine timing records, incremental execution and timed simulation own the new lane;
existing simulators only add explicit delegation. Reuse FillModel's actual config
via a read-only accessor, not contradictory duplicated execution settings. Research
helpers import shared primitives/steps without changing policy or public hooks.
Use bounded scalar helpers in simcore or a small accounting module; no callback,
plugin, provenance, registry or multi-entry trade framework. Goal/cards, market
sources, runner/gate/ledger and old study artifacts remain untouched.

TDD steps: shared primitive/execution extraction parity; genuine signal integration;
portfolio accounting and causal opening batches; real timed-trade matcher adapter;
paired public-simulator end-to-end regression. Acceptance witnesses must prove
an earlier M15 exit changes later eligibility/cash/slot admission, future-low/volume
variations cannot alter the opening batch (or invalidate the WHOLE run), tiny-capital
cash/heat/concentration/slot/risk vetoes, shared symbol budget, actual partials,
independent-vs-book DP scopes, session timers, missing refinement without universe
shrink, typed unsupported cards, interval benchmark refusal and exact event Fraction.
Run focused/related tests, daily golden, strict explicit mypy and global Ruff/format.
Independent simplicity then engineering/security/math review and root own arithmetic
must pass. Freeze source/review before commit; known-bug source mutations execute
ONLY postcommit, restore exact bytes and rerun positives. Update durable state/proof.

No real-market data, source procurement, actual-ledger activation, new sampled study,
cleanup, inference/statistical adoption, lockbox, broker or live path is authorized.
