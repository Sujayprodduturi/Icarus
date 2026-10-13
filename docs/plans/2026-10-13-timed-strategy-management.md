# Timed strategy management — 2026-10-13

The operator approved adding the remaining two strategy consumers after the
shared timed-book milestone. D47 authorizes autonomous reviewed implementation;
this bounded extension changes existing timed methods, not the daily default.
Published prerequisite 186bf64 passed hosted CI (3156 passed, four skipped) and
the native-resource check. All work here uses deterministic invented fixtures.

## Intended behavior

Add evaluated `exit_signals` and source-anchored `rebalance_pulses` keyword inputs
to both `run_time_resolved` methods and the common engine. Reuse existing typed
management/rebalance records and pure cohort/grid helpers where possible. Keep
daily `.run`, goal, cards, risk limits, runner routing and matcher policy unchanged.
Add timed exit causes for opposite-signal and rebalance sales. Expose decision
records separately from execution legs: original daily source index and OPEN label
remain identity coordinates; availability is the declared session CLOSE in UTC.

At DAILY_CLOSE a held position with a declared opposite exit and a true evaluated
exit event queues one sticky management sale. Its first eligible attempt must be
in a later source session, at an M15 open at or after decision availability plus
latency. Zero fills and partial fills retain the pending sale for subsequent opens
and sessions until sold or the run ends. Repeated decisions cannot replace its
origin. Residual inventory remains visible at the terminal boundary, never forced
sold or silently discarded.

At OPEN, active native/gap stops have first priority, followed by due timer exits,
then eligible pending management. One exit attempt per holding/bar; its residual
cannot receive a second intrabar exit in the same bar. Existing protective latency,
ambiguity refusals, stop latch and target strict-through semantics stay intact.
An exit intent uses its own availability, not the original entry decision time.
Management selections consume the same per-symbol opening capacity as other sales
and entries. Opening realized-volume contradiction still invalidates the whole run
and blocks every benchmark result, with provisional diagnostics retained.

## Scheduled low-volatility decisions

The supplied boolean pulses must exactly match the existing whole-source grid,
including longest-lookback and modulo 63 boundaries; a local slice cannot restart
the schedule. Only a pulse at DAILY_CLOSE creates a rebalance decision. Reuse the
existing candidate cohort rule: thirty selected names, at least thirty-one eligible
names with finite rank and entry data, and tradable status at the decision.
An unavailable cohort/cardinality is an explicit non-action event, preserving the
held book; do not turn missingness into an empty target and liquidate it.

A valid target retains incumbents without resizing or fee-producing churn.
Non-target holdings queue sticky next-session rebalance sales. Pending exits are
not resurrected by a later target. Only absent target names form new admissions;
retained candidates receive explicit already-held dispositions. Signal diagnostics
retain independent fixed-notional scope; portfolio admissions use the existing
serialized cash/slot/heat/concentration/risk sizing, not inverse-volatility weights.
At-most-four portfolio holdings remain enforced.

Admissions receive one attempt at the first latency-eligible open of the immediate
next declared session, using actual existing residual holdings and opening sale
proceeds. No waiting for a later intrabar sale to fund the same opening, no
prediction of future sale proceeds, and no later rollover of an unfilled admission.
Partial sales may leave slots occupied; an unrelated free slot can admit normally.
Source-based deterministic rank/fallback and actual filled acquisition/DP fees
remain shared. No blanket suppression when causally known partial sales leave cash.
Rebalance records must show candidates, retained, holdings after the admission
batch, remaining admissions and no-next-session/unavailable outcomes accurately.

## Validation and scope

Opposite columns are mandatory when declared; extra exit columns without that
declaration must not create exits. Shapes/universe/grid/nonbinary/infinite columns
are rejected before fills. Legitimate NaN exit warmup may remain outside an active
holding; a required held-symbol NaN decision fails the timed run with a typed
missing-decision refusal. Low-volatility NaN entry/rank warmup is evaluated by the
cohort rule at pulses, not coerced to false or rejected globally; nonbinary or
infinite entry values remain malformed. Fixed-card entry NaN refusal is unchanged.
Trailing stops, non-daily clocks and non-equity universes remain unsupported.

## Acceptance and evidence

TDD on both public modes proves next-session/CLOSE availability, latency, sticky
partial/no-fill management, repeated-event identity, stop/timer precedence,
terminal residuals and held NaN refusal. Low-volatility cases prove source grid,
31-name cohort/30 candidates, valid retain/drop/add without resizing, unavailable
cohort/no liquidation, cash/slots/ranks, partial-exit residuals, per-symbol shared
capacity, and once-only same-day book DP versus independent signal scopes.
Actual seven cards parse and their evaluated management columns exercise the lane;
this proves mechanics, not profitability or a new sampled strategy evaluation.
Benchmark matching uses actual executed legs and retains whole-run invalidity and
missing-leg refusal. Existing fixed timed tests and daily/golden regressions pass.
Strict mypy, Ruff lint/format, ordinary versus ignore-CR diff counts pass.
Independent simplification then bug review precedes source commit. Every actually
found bug has a postcommit reintroduction witness, with exact byte restoration and
positive recheck. Freeze source/tests before root verification and publication.

No real data/source procurement, actual trial ledger/study, inference, tax/alpha
adoption, lockbox, cleanup, broker or live path is authorized. Source/calendar
certification and real performance remain separate milestones.
