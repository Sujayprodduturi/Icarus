# Practical signal uncertainty: calendar ratio subsampling

Date: 2026-10-01. Status: independently reviewed research candidate, approved for operator presentation; implementation remains a separate milestone decision. The operator approved the practical-method DESIGN direction after the [evidence policy](2026-10-01-signal-real-evidence-policy.md). No implementation, experiment, adoption or real-data run is authorized. Phase1 Task3a Step6 remains open.

## Purpose

The simulator records the trades a strategy would take. This candidate asks how its average trade outcome changes across stretches of market time, keeping all stocks together. It preserves whole trades and variable trade counts. It can ultimately report insufficient evidence; it cannot turn a market-model assumption into a proven fact.

## Decision and alternatives

Assess nonstudentized, overlapping calendar-block subsampling of the original trade mean. Nonstudentized means no separately estimated standard error is needed for each slice. This is an outcome-series estimator on one fixed run, not fresh strategy replay, symbol-selection placebo or a new artificial-law guarantee.

| Alternative | Main benefit | Why not the first candidate |
|---|---|---|
| Calendar ratio subsampling | Adjacent time and simultaneous stocks stay together; random counts represented; deterministic slices | Requires a stable dependent-data model and a limiting distribution; sparse slices can prevent inference |
| HAC delta-method interval | Uses a long-run variance estimate for the same ratio | Adds variance/kernel/bandwidth estimation; previous variance corrections already failed some profiles |
| Moving/stationary block bootstrap | Resamples dependent stretches | Adds draws and tuning; stitching raw paths changes strategy state, while outcome resampling still needs assumptions |
| Fresh replay per slice | Recreates execution within a slice | Resets/warm-up/open positions change trades and target; a separate later design |

No failed CR2/fixed-b candidate is adopted or rehabilitated. This candidate has not been calibrated.

## Calendar and accounting contract

Pin the n-session daily analysis core before seeing outcomes. Retain every session, including no-entry sessions. Intraday execution coordinates remain distinct from the daily calendar index. The initial research interface uses invented records only, not a market panel or product simulator adapter.

Assign each original filled trade once to its actual entry session t. Aggregate partial exits before attribution. For each target, retain A_t=sum of its whole-trade outcomes and C_t=filled-entry count, plus trade IDs and complete decision/entry/exit/source/recognition footprints. All stocks use the same calendar axis. Skips and expected missing signal inputs are separate diagnostics, not zero-return trades. Duplicate IDs, nonfinite outcomes or incompatible axes refuse the component.

The full statistic is m_n=sum(A_t)/sum(C_t). This is exactly the original equal-per-trade mean, not the mean of session means or block means. For raw return use the original model-cost, before-tax trade return; for win probability use the count of strictly positive raw returns as A_t; for paired excess use direct whole-trade excess. Each metric has separate applicability and refusal status. No portfolio Sharpe/equity curve or promotion verdict is introduced.

Every selected trade retains its complete outcome even when exits lie beyond a slice's entry-date core. The footprint halo records those required events; halo-only entrants do not enter the slice numerator/count. If any required halo crosses the lockbox or another unauthorized source period, refuse inference rather than load it or shrink the cohort. No return truncation, artificial closure, exclusion of long trades, clipping or boundary re-entry. Adjacent slices and their halos overlap; they are not independent samples.

Raw descriptive arithmetic may retain labelled stale marks, as current code does. Realized-return inference is unavailable with unresolved stale marks or terminally forced outcomes; alternatively a separately reviewed mark-inclusive target would be required. Exact paired excess needs complete certified entry/every-exit benchmark matches for every filled trade. Missing benchmark blocks that target, not raw arithmetic. No matched-subset inference.

Startup-flat state, finite-horizon END_OF_DATA exits, unavailable completion halos and changing point-in-time universes are genuine applicability issues. Do not drop affected trades to create a favorable stationary cohort. The first candidate has no real-source adapter or solution for those boundaries. Fold-matched runs retain their own reset identity; do not pool folds or reset the simulator at subsampling seams.

## Population target and conditional justification

Let Z_t=(A_t,C_t) be the complete calendar outcome/count process. Under a stationary model with positive lambda=E[C_t], the proposed population target is theta=E[A_t]/lambda: the long-run selected-trade mean for that strategy/process. This differs from E[A_t/C_t], E[sum A/sum C] at a fixed finite horizon, and a forecast of the next market regime. Market-dependent entry counts are allowed jointly with returns; they are not conditioned away.

Set W_t=A_t-theta*C_t. With a joint law giving a law of large numbers for C_t and a nondegenerate sqrt(n) central limit theorem for W_t, sqrt(n)*(m_n-theta) has limiting variance sigma_W^2/lambda^2. The positive-variance normal limit is continuous, supporting the subsampling quantile argument. This follows from the exact identity sqrt(n)*(m_n-theta)=[n^(-1/2)sum W_t]/[n^(-1)sum C_t]. It is a project ratio derivation, not a theorem asserting that Icarus trades meet the premises.

An assessable sufficient model is strict stationarity, strong mixing, finite (2+delta) moments of A_t and C_t for some delta>0, summable mixing coefficients raised to delta/(2+delta), and positive finite long-run variance of W_t. Strong mixing means dependence between sufficiently separated histories decays in a specified probabilistic sense. It is a population assumption, not a certificate supplied by sample autocorrelation. Moment/mixing/variance conditions remain explicit; bounded win indicators do not remove count/dependence assumptions.

For a synchronous stationary full-stock market process, a deterministic finite lookback/state footprint W and forward completion footprint H with a shift-equivariant map can transmit mixing to Z with a lag allowance W+H. One-position-per-symbol state and unbounded holds are not automatically finite-memory. Observed maximum holding duration is not a population bound. Without a finite footprint or separately justified stability/mixing argument, applicability remains unknown. Complete outcome records alone are insufficient.

Primary sources checked 2026-10-01: [Politis, Romano and Wolf (2001), section4 equation16 and Theorem4.1/Remark4.1](https://www3.stat.sinica.edu.tw/statistica/oldpdf/A11n49.pdf) give consecutive-block subsampling under stationarity, mixing and a limiting law; a deterministic block-size sequence b_n must increase with b_n/n tending to zero. [Tewes, Politis and Nordman, section4.2 Theorem5](https://arxiv.org/pdf/1706.07237) supplies a mean-based mixing/CLT result under moment/dependence conditions. Applying it to W and the ratio is the project derivation above. These are pointwise large-sample results, not finite-sample or uniform-over-all-market coverage guarantees.

## Concrete candidate arithmetic

For the initial research design nominate ONE deterministic candidate size b(n)=ceil(n^(2/3)), implemented mathematically as the smallest integer b with b^3>=n^2. This is project-owned tuning chosen before any new screen, not a literature-optimal size, accepted floor or goal.yaml amendment. Require 2<=b<n. It has b increasing and b/n tending to zero, but those properties establish no finite-sample adequacy. Do not choose b after inspecting interval sign, width, coverage or activity. The existing product L=max(63,3*observed H) stays unchanged; it is not this candidate's b.

For each j=1..n-b+1, select all b adjacent Z records and compute m_jb=sum(A)/sum(C). Keep every scheduled slice. With q=n-b+1 roots R_j=sqrt(b)*(m_jb-m_n), construct the empirical CDF using equal slice weights. Roots are dependent; q is not an independent sample size and supplies no degrees of freedom or extra trials.

Use inverse empirical-CDF quantiles Q(p)=sorted_roots[ceil(q*p)-1], tie-inclusive, without interpolating. At the existing nominal 95% level, the candidate interval is [m_n-Q(.975)/sqrt(n), m_n-Q(.025)/sqrt(n)]. Reversed quantile subtraction is deliberate. No symmetric-normal assumption, bias recentering, studentization or finite-b correction is silently added. Raw endpoints remain in the artifact; any later win-probability display intersection with [0,1] is separately labelled and cannot improve coverage by declaration.

If any scheduled slice has zero total count, refuse the entire metric with an explicit zero-count-slice reason; never fill with zero or discard the slice. Under mere stationarity/mixing/positive lambda, this refusal rule is NOT proved to emit with probability tending to one. The literature justifies the underlying asymptotic statistic; the refusal wrapper requires separate emission/joint-coverage validation. Do not claim nominal coverage conditional on emission. Degenerate roots, invalid arithmetic or missing applicability/precision policy likewise withhold an eligible interval. An internal synthetic arithmetic oracle may compute candidate endpoints without conferring product eligibility.

## Hand-worked preservation example

Invented eight-session sums A=(.02,0,-.01,.03,0,.04,-.02,.01), counts C=(2,0,1,3,0,2,1,1). The full mean is .07/10=.007. Empty sessions retain (0,0). Here b=4; five overlapping slice means are .04/6, .02/4, .06/6, .05/6 and .03/4. A trade entered in session4 and closed in session7 remains in the first slice with its whole return; the extra exit sessions supply its halo, not extra entrants.

The root quantiles are Q(.025)=-.004 and Q(.975)=.006. Candidate endpoints are .007-.006/sqrt(8) and .007+.004/sqrt(8), approximately .00487867966 and .00841421356. These verify ratio weighting, slicing and quantile direction only; eight sessions/five slices establish no valid uncertainty or data floor. Removing a boundary trade or averaging the five slice means changes the target and is forbidden.

## Validation design to freeze before implementation/sampled work

First a separately reviewed deterministic implementation plan: immutable calendar/identity validation, exact aggregation, fixed block rule, quantiles/endpoints and typed refusals, invented fixtures only. A small target-specific readiness artifact may explain missing prerequisites, but cannot authenticate assumptions or authorize a study. No general framework, panel adapter, ledger/matcher duplication or product integration.

Before any new stochastic screen, freeze the complete protocol: source/evaluator hashes, target/law derivations, exact profiles/calendar geometries, replication/budgets, seeds and independently held confirmation identities, artifact schemas and stopping/selection rules. Do not use reserved streams or relabel exposed samples as untouched. Preserve all failures and attempts. The previously failed 45 profiles stay history; their trade-vector layouts cannot be relabelled calendar paths without a reviewed adapter/target derivation.

Required coverage challenges: finite-memory persistence/common stock shocks, clustered volatility, rare signed skewed magnitudes, endogenous entry counts coupled to returns, unequal burst counts, long overlapping halos and stationary bounded-state selection. Deliberately out-of-model challenges: nonstationary regime/universe changes, long memory, infinite-variance tails, unbounded state/holds and selective completion. In-model cells need analytically justified theta and sampling target; out-of-model cells are failure/sensitivity evidence, not secretly excluded losses. Observable malformed/missing/out-of-footprint cases test required refusal. Latent model violations are not reliably detectable from one history.

Pin prior numeric criteria for both interval tails, joint coverage/refusal, minimum emission, emitted count, absolute width/informativeness and positive/negative effect detection. Report unconditional emitted-and-covered counts, emitted conditional coverage, every refusal reason, raw endpoint widths and all generated counts. Neither broad ranges nor mass refusal can pass. Confidence bounds for replication rates use independent replicates, never the overlapping roots. Family comparisons/error accounting, calibration-selection policy and untouched confirmation stop-on-failure must be written before draws. Do not silently inherit old CR2 floors or assign guessed practical floors here.

## Consequences, completion and next action

This design handles random counts algebraically and preserves complete trade weighting, synchronous shocks and overlapping outcome paths. It does not solve regime drift, rare unseen events, simulator accounting, source certification or finite-endpoint effects. Those limitations are visible rather than converted into a certainty claim.

Design acceptance requires primary-source theorem premises mapped, formula and preservation example independently checked, statistical and source/governance review approval, D39 recorded and state/handover updated. No code/experiment is complete by this acceptance. Next proposed unit is the isolated deterministic research implementation and tests after the operator milestone decision, followed by a separately frozen screen/confirmation protocol. No method adoption or floor is authorized by building an oracle.

Original Step6b -> Step7 -> Step8 dependencies remain unchanged. Accepted calibration, mandatory atomic counted trials and later source/benchmark/accounting schedule amendment still precede real evaluation. F48, M1-M4, Windows official durability/resource eligibility and datastore limitations remain OPEN; inference_enabled remains false. No broker/live path.
