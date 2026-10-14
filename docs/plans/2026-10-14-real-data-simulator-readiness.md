# Real-data simulator readiness — 2026-10-14

The operator requests continued repairs until the simulator is ready to accept real
data, and asks us to check data availability. This authorizes reviewed software
construction and public provider research. It does not authorize buying data,
contacting vendors, broker access, running strategies on market prices, activating
the actual ledger, consuming the lockbox or adopting a statistical method.

## Outcome

Build a local-only, fail-closed input and execution path using the existing seven
cards and shared timed engine. Prove the complete path with invented file bundles.
Report SOFTWARE_VERIFIED, DATA_QUALIFIED and RUN_AUTHORIZED separately. Never turn
successful invented tests or a self-declared hash into REAL_DATA_READY. Missing
external evidence remains a named blocker while all independent software work
continues. Preserve daily defaults, goal/rates/cards, statistical gates and history.

## Unit 1: immutable input gate

Add typed JSON manifests and external approval/policy inputs, plus a read-only local
loader. A bundle contains independently identified daily-stock, PIT-universe,
corporate-action, M15-stock, Nifty-observation, session-calendar and opening-liquidity
artifacts. For each preserve path, size, SHA256, format/schema/parser version,
vendor, venue, canonical instrument/basis, source revision, retrieval timestamp,
coverage and archival/use evidence. Reject unknown schemas, duplicate identities,
malformed fields, escaped/absolute member paths, symlinks/reparse paths and changed
bytes. Pin the manifest independently outside the bundle; never accept its own
hash or an approval embedded in the upload as source authentication.

The supplied source approval identifies the independently reviewed authority and
licence evidence and pins all artifact/calendar/policy hashes. It is external
operator evidence, not software-created proof of vendor truth. Invented approvals
remain labelled invented and cannot qualify real inputs or authorize a real run.
Provide a metadata-only command that hashes but does not decode price records,
evaluate strategies, reserve trials or connect to databases/network services.

Use immutable bytes captured after preflight and recheck at use to avoid TOCTOU.
Keep resource limits explicit in the supplied policy; do not load unbounded uploads
or multiply full-range M15 objects in every fold. Input errors have typed reasons.

## Unit 2: calendar, observation and replay integration

Define and document a strict canonical local JSON/JSONL schema. Preserve independent
raw event and availability timestamps, record IDs, revisions and observed state;
do not reconstruct those from the old Yahoo daily cache. The benchmark identity is
Nifty 50 PRICE_INDEX, never futures, TRI or a constituent reconstruction. A dated
source-specific matching policy must be independently pinned before price parsing.
Support exact-time matching and, if supplied and approved, latest causally available
observed matching with an explicit maximum age. No unregistered age default, future
nearest, interpolation, silent forward-fill or partial-leg reweighting. M15
intrabar fills remain unresolved intervals and cannot acquire exact point returns.
Move reusable pure matching code to the engine if needed, retaining the research
API/default synthetic policy and old tests. Engine modules cannot import research.

Validate authoritative calendar rows and coverage, including declared regular and
special opens/closes and closed dates. Map source indices to the full daily trading
axis; keep the daily 2011–2022 lane separate from M15 2015–2022. Reject all lockbox
overlap before price decoding. Point-in-time membership, eligibility and adjustment
bases must agree across artifacts. No missing or delisted name is removed to make
a run pass: missing/conflicting refinement is an explicit unavailable result.

Opening liquidity must identify its own earlier-available source or approved
prior-only calculation. A current M15 candle's eventual volume cannot size an
opening intent. Retain whole-batch realized-volume reconciliation and native stop
latency, strict-through/no-fill/partial-fill behavior. Index declared bars by session
once instead of repeatedly scanning full M15 history for every session; prove
unchanged fixed-fixture outputs and test scaling with deterministic invented data.

## Unit 3: guarded timed runner and readiness command

Add an explicit preflight/check/run interface. Default metadata checks never open
a database or execute strategies. Real execution additionally requires fresh
external run authorization bound to the data, source policy, goal, cards and runner
hashes, and the activated Postgres trial ledger. Reserve every inspected strategy,
mode and capital evaluation atomically BEFORE loading price payloads or evaluating
DSL columns; release diagnostics only after durable verified terminal persistence.
Recovery-only receipts, failed reservation, lost acknowledgement or conflicting
identity cannot authorize a second evaluation. Reuse the existing ledger types and
barrier; do not activate or import actual history during this build.

Preserve whole-source lockbox rejection, configured walk-forward geometry/seams,
source-zero rebalances, once-evaluated daily columns and independent/reset books.
Price parsing and DSL evaluation happen behind the reservation barrier. Full input
identity includes raw bundle, approval, policy, goal, strategy and runner hashes.
No resume/retry redraw or result reuse across changed input identity. Reports retain
every card and explicit empty/unavailable outcomes, costs, residual holdings,
benchmark coverage/refusal and original execution times. Pre-tax diagnostics are
labelled; after-tax promotion/alpha/inference remain unavailable rather than inferred
from benchmark excess. Do not advertise this descriptive runner as Validation-ready.

Prove all seven cards in signal and both seed/edge portfolio capital modes using
invented local files and a disposable/fake ledger plus existing real-Postgres
integration tests where appropriate. Exercise genuine entry, exit and rebalance
events, complete partial benchmark arithmetic, missing/refused inputs, authorization
and persistence failures. No actual-ledger activation or market-data study.

## Completion evidence

TDD per unit; independent plan and source review; root reproduced values; strict
mypy/Ruff/format/daily golden and targeted related tests; ordered simplicity then
bug review before source commits. Reintroduce every actually found bug after its
commit, restore exact bytes in finally and rerun positives. Update authoritative
status/handover before publication. Use one writer on shared files and one heavier
foreground gate at a time. Continue through all three units without routine
operator-approval pauses; stop for external facts or money/safety choices we cannot
legitimately supply. A supplier's advertised data product is availability evidence,
not confirmed coverage, licence, authenticated input or permission to run it.
