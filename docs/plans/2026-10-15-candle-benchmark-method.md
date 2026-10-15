# Candle benchmark method proposal — UNAPPROVED METHOD

**Status:** proposal only; independently review before implementation. This document changes no
runtime, source qualification, threshold, trial count, or run authority. It authorizes no data
evaluation. `DATA_QUALIFIED=false` and `RUN_AUTHORIZED=false` remain controlling.

## Purpose and boundary

Keep the existing strict lane unchanged. `EXACT_OBSERVED_SESSION_CLOSE` continues to require a
raw Nifty event at the official session close whose raw availability is no later than that close
(`icarus/engine/timed_runner.py:872-901`). Exact execution-time matching continues to require an
event-resolved fill and an observed, causally available benchmark event
(`icarus/engine/benchmark_match.py:220-272`). Kite archived candles cannot satisfy either claim
from their OHLC label alone.

Add one optional **descriptive candle lane** for a qualified bundle containing official
daily stock records, start-labelled M15 stock candles, official daily Nifty 50 Price Index closes,
and start-labelled M15 Nifty 50 Price Index candles. The lane reports what the captured candles
support. It never labels a candle value as a raw event, a vendor publication time, an exact
fill-time benchmark price, alpha, Information Ratio, DSR/PBO evidence, Validation evidence, or a
promotion metric.

## Required facts versus declared replay assumptions

Required before any actual run: immutable artifact hashes; Nifty identity and Price Index basis;
official-daily versus captured-M15 roles; UTC start labels and interval duration; complete dated
session calendar; effective security lineage; common adjustment basis; explicit missing and
quarantined rows; applicable subscription/use rights for the intended analysis; and independently qualified coverage. Unknown raw
publisher time and revision history remain `null`, never copied from a retrieval time or derived
timestamp. These unresolved source facts still block `DATA_QUALIFIED` for the current archive.

The optional replay declares two different modeled clocks. A benchmark M15 candle completes at
its `interval_end_ts` for retrospective comparison. Every daily stock input and every daily
management feed at source index `t` shares one
`MODELED_NEXT_SESSION_OPEN` decision-availability timestamp: the declared `open_ts` of source
index `t+1`. These are replay assumptions, not vendor facts or proven conservative publication
bounds. Raw and modeled availability must be different typed fields and report columns.

The modeled daily timestamp governs queued entries, opposite-signal exits and scheduled rebalance
decisions in both the signal and portfolio timed engines. Their source index remains `t`; neither
the daily array nor its calendar identity moves to `t+1`. Execution requires an M15 raw bar start
**strictly later** than modeled availability and must also satisfy existing latency. Therefore a
decision modeled available at a regular 09:15 open cannot execute in the 09:15 candle; its first
regular-grid candidate is 09:30, subject to latency and all existing fill rules. A terminal daily
row without a declared next session has no modeled availability and yields typed no-next-session
unavailability; no date or open is inferred.

Already-active protective stops are independent of a new daily decision. They keep their existing
intrabar path and continue protecting held inventory while a new opposite/rebalance decision is
pending availability.

Retrospective measurement is separate. Once a benchmark candle is complete under the replay
model, its captured range may describe an earlier fill within that interval; this does not require
the candle to have been available at the fill. It must never become a strategy input at that fill.
Unknown raw publication and revision times remain unknown, so this mode provides modeled replay
causality, not original point-in-time certification.

## Minimal runnable vertical

Implement this as three or four cohesive units, not a parallel runner or general schema framework:

1. **Loader and assembly:** add an explicit policy mode, defaulting to
   `EXACT_OBSERVED_SESSION_CLOSE`. In opt-in `DESCRIPTIVE_CANDLE_PROXY`, parse a small parallel
   `BenchmarkCandle` contract, seal its bytes/source identity, and bypass only the strict daily
   projection at `timed_runner.py:871-905`. Build the stock panel without a strict benchmark and
   carry the candle series separately in `AssembledTimedInputs`. There is no automatic fallback.
2. **Panel and shared decision availability:** descriptive mode sets `Panel.benchmark=None`.
   Before evaluating any DSL column, inspect the card's existing primitive inventory and refuse
   `benchmark_return`, `index_above_ma`, `relative_strength`, `beta_to`, `correlation_to`, and any
   future `require_benchmark` consumer. None of the current seven cards uses those five current
   primitives. Add `decision_available_ts: datetime | None` to each `Session`, or an equally small
   immutable helper keyed one-to-one by session index. In descriptive mode the assembler derives
   it only from the next declared `Session.open_ts`. In strict mode the optional value/helper is
   absent and `run_timed` follows its existing `session.close_ts` path, preserving fixture hashes
   and timing. One shared accessor supplies entries, opposite exits and rebalance decisions, so
   the signal and portfolio wrappers cannot diverge. Never replace `Session.close_ts`, shift the
   daily axis, or retime a source row.
3. **Evaluation:** `CataloguePayload.from_assembled` builds either the existing
   `ObservationIndex` or the new candle index. `_trade_benchmark` dispatches by the pinned mode,
   reusing `TimedTrade`, `Timing`, source seals, executed quantities and existing cost allocation.
4. **Report/CLI and identity:** the existing guarded timed runner and report gain the explicit
   mode and typed interval fields. Seal the availability model identifier and every derived
   per-session timestamp into the fixture digest, matching-policy hash and qualification bounds
   before price decode. Exact-default fixture hashes and timings remain unchanged. Reservations
   still occur before shared price decode. No second runner exists.

Do not widen `NiftyObservation`, whose meaning is an exact observation. Add a small parallel
`BenchmarkCandle` contract beside it: record/revision/source identity, interval start/end, OHLC as
exact positive fractions, `raw_available_ts: datetime | None`,
`modeled_available_ts: datetime`, and availability basis
`MODELED_INTERVAL_END` or `MODELED_NEXT_SESSION_OPEN`. Make the benchmark role a closed,
mode-discriminated schema version; do not disguise M15 candles as exact observations. Reuse
`Session`, `Timing`, `SourceDeclaration`, `FixtureIdentity`, source-pair seals, and timed trade
fragments. Add a separate candle matcher in
`icarus/engine/benchmark_match.py`; leave `match_benchmark()` and its default exact policy intact.

Daily official Nifty closes remain provenance-bearing report inputs only in this first slice;
unsupported open/high/low/volume remain unavailable. Descriptive mode sets `Panel.benchmark=None`
and does not create a shifted or modeled daily benchmark view for the DSL.
The M15 matcher selects exactly one qualified Nifty candle whose half-open interval contains each
executed stock leg's event time, or the identical interval when the stock leg is bar-resolved.
Missing, duplicate, overlapping, identity-incompatible, quarantined, wrong-session, or
non-covering candles refuse the whole trade comparison. A stock interval spanning more than one
benchmark interval is unavailable; it is not approximated.

## Return output

For original quantity `Q`, exit quantities `q_i`, entry benchmark candle `[L_e,H_e]`, and exit
candles `[L_i,H_i]`, report the captured-candle price-return interval:

`lower = sum((q_i/Q) * (L_i/H_e - 1))`

`upper = sum((q_i/Q) * (H_i/L_e - 1))`

Require positive finite OHLC prices, ordered OHLC envelopes, finite ordered return endpoints and
`sum(q_i)=Q`; negative and zero returns are valid. Preserve exact fractions through calculation.
Also report every matched candle ID, interval, modeled availability basis, and refusal. Never emit
the midpoint or call either bound an exact return. Because Kite says intraday capture can omit
ticks, these are bounds over the **captured candle records**, not rigorous bounds on all prices
that traded in the market. Lost ticks cannot be repaired or bounded from OHLC alone.

For this first slice, accept only a fully closed, single-entry `TimedTrade`. Let `P_e` be the one
executed entry price and `Q` its actual `original_quantity`. Stock return is
`fully_allocated_realised_net_pnl_before_tax / (P_e * Q)`. The numerator reuses the existing trade
calculation and includes every allocated entry and exit charge exactly once. Never use intended
quantity, R-multiple or account equity. Multi-entry, open inventory, reinvestment and portfolio
compounding are unsupported. Benchmark weights describe liquidation fractions of one fixed
initial benchmark holding at the stock trade's exit schedule; they do not compound.

The comparable output is the stock return after modeled trading costs and before account-level tax,
beside the gross Nifty Price Index captured-return interval. This asymmetry is explicit and no
fictional index brokerage, tax or fill is charged. Excess is
`[stock_return - benchmark_upper, stock_return - benchmark_lower]`. It is a descriptive interval,
not regression alpha, Information Ratio, or after-tax promotion evidence. PRD section 31.5 requires
positive after-cost-and-tax alpha for promotion; this method does not satisfy that gate.

## Governance and outputs

The lane is opt-in through an externally hashed, dated matching-policy document chosen before
price decoding. It has no default fallback from strict exact mode. Any actual run still requires
the normal qualified-source certificate, fresh run authorization, and the unchanged durable trial
reservation for every human or machine evaluation. Reruns and parameter changes remain new
trials. The lockbox, walk-forward geometry, thresholds, and seven-card identities remain unchanged.

Each per-trade result must state `DESCRIPTIVE_CANDLE_PROXY`, source hashes, policy hash, modeled versus raw
availability, coverage/refusal counts, exact strategy cost basis, tax status, benchmark interval,
and `promotion_eligible=false`. This slice emits no aggregate return, portfolio comparison or
alpha estimate. It may report counts of comparable and unavailable trades without filtering an
aggregate. Daily official Nifty closes never enter strategy calculation in this slice.

Rights remain a qualification fact, not a blanket ban. The 2026-10-15 method review records the
new 9 October Kite staff clarification (forum discussion 16304): personal analysis is allowed,
while permanent raw storage is restricted and the precise archive use still needs clarification.
The later qualification must bind the applicable subscription/contract to the intended use; it
must neither invent permission nor demand a vendor-only certificate when existing terms resolve it.

## Acceptance cases for a later approved build

1. Strict exact fixtures remain byte-for-byte behavior compatible; candle input cannot enter the
   strict projection or exact matcher.
2. A candle-only synthetic bundle passes loader, panel, evaluation and report and reaches one
   actual synthetic `TimedTrade`. Entry benchmark `[100,110]` and equal-quantity exits `[120,130]`
   and `[90,100]` produce exactly `[-1/22,3/20]`. Stock entry 100, equal exits 125 and 95, and
   total allocated charges of 2 per original share produce `2/25`; excess is exactly
   `[-7/100,69/550]`.
3. Retrospective matching may use a completed benchmark candle containing the earlier fill; this
   grants no causal waiver to strategy inputs. For entries, opposite exits and rebalances in both
   timed modes, source row `t` remains row `t`, its modeled availability equals the next declared
   session open, the opening M15 bar is skipped, and the first possible regular-grid execution is
   09:30 subject to latency. Existing protective stops remain active while a decision waits.
4. Missing, duplicate, overlap, quarantine, identity, adjustment-basis, session, quantity and
   multi-interval cases return typed unavailability without a partial comparison.
5. Reports expose no midpoint, exact-point return, alpha, Information Ratio, DSR, PBO, Validation
   or promotion field; mutation tests fail if any is introduced or `promotion_eligible` changes.
6. Positive prices can yield negative/zero interval endpoints. Captured-tick bounds are labelled
   as such; a fixture with an omitted extreme proves the code
   makes no claim about unobserved market prices.
7. A terminal source row without a declared next session cannot create an entry, opposite exit or
   rebalance action. The availability model and timestamps are digest-bound; mutation is caught,
   while strict-default fixture hashes/timing remain unchanged.
8. Preflight still decodes no prices, an actual run still reserves the unchanged trial ledger
   before decode, and absent qualification or authorization still fails before evaluation.

## Decision still required

Approval covers only the synthetic vertical above. Its stopping point is a working descriptive
candle path, followed by qualification of a bounded actual-data window and the existing fresh
actual-run authorization. Exact publisher timestamps are not a prerequisite for this expressly
modeled mode unless a later claim needs them. Dated universe completeness, common action basis,
calendar coverage, applicable rights and explicit missing members remain required; selecting only
surviving retrievable securities is forbidden. A later exact source uses the existing strict lane
and must not silently upgrade results produced by this candle policy.
