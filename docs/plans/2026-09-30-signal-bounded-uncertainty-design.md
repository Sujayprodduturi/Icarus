# Next uncertainty research: explicit assumptions and bounded independent groups

Date: 2026-09-30. Inspected source: ada6a7d5c6dab32bf18cb016147bfe856b3056e8.
Status: concrete next research proposal; independent mathematical/governance reviews completed after the clarifications recorded below. No implementation, new stochastic screen, product method, protocol amendment or data floor approved.

## Operator purpose and current position

The signal simulator records what happened to every strategy signal. Uncertainty mathematics must then tell us how much those outcomes establish. The previous synthetic screen rejected both the original method and the fixed-b candidate as general methods: serial raw coverage was913/1024 and rare-magnitude raw839/1024 for the new candidate's intended95% ranges. Those are failures of uncertainty estimation, not results for real strategies.

The operator asked to continue with the next steps after that result. D26 permits autonomous bounded planning/review and GitHub sync. This document completes the next concrete design investigation. Building this changed assumption contract still follows the explain/approve/build loop in OPERATOR section1. The next unit is deliberately a research benchmark and insufficiency checker, not a claim to finish all of Task3a.

## Why this direction

An observed sample can miss rare outcomes. Resampling that sample cannot introduce an outcome absent from it: if every observed win indicator equals1, resampled indicators remain1. More covariance terms also do not supply information about unseen extremes. This deterministic observation is not a blanket claim that every bootstrap construction fails, but it rules out relying on ordinary resampling alone as a rare-event repair.

A finite-sample bound offers a useful reference when both independence and externally justified outcome limits hold. It does not estimate the range from the sample, rely on normally shaped outcomes, or shrink to zero merely because the sample variance happens to be zero. When those assumptions cannot be justified, it must refuse that guarantee. Adjacent time blocks, L=max(63,3H), low observed autocorrelation, a large number of trades or a frozen caller flag do not prove independence.

| Approach | What it would provide | Remaining limitation | Next decision |
|---|---|---|---|
| Bounded independent-group Hoeffding benchmark | Explicit finite-sample mean guarantee under stated conditions; exposes how many independent groups the chosen precision needs | Often wide; independently certified groups and hard support limits are essential | Recommended smallest next research unit |
| Temporal paired block bootstrap/studentization | Could preserve local time dependence and original sum/count weighting | Needs separate dependence/length/coverage design; observed samples can omit rare extremes; more computation | Keep for a separately reviewed dependence-method investigation |
| Another asymptotic covariance/critical-value adjustment | Cheap reuse of prior mechanics | Prior evidence does not repair rare events or establish assumptions | Do not tune the rejected candidate on exposed samples |

Primary sources inspected 2026-09-30: [Hoeffding1963](https://www.cs.rpi.edu/academics/courses/spring06/random/hoefding.pdf), Theorem2 for independent bounded sums; [Politis and Romano1994](https://users.ssc.wisc.edu/~behansen/718/Politis%20Romano.pdf), stationary-bootstrap construction and asymptotic scope. The weighted bound below is a project derivation by applying Hoeffding to weighted independent group variables, not a new theorem claimed for arbitrary time series.

## Exact mathematical target and assumptions

For G nonempty externally declared groups, n_g positive integer observations, N=sum n_g, group average X_g and deterministic weight w_g=n_g/N, preserve the original trade-weighted estimate m=sum w_g X_g. Its estimand is theta=sum w_g E[X_g]. Group means need not have identical means or distributions. The guarantee is for this weighted analysis-window expectation, not future market performance or a time-invariant population parameter under regime changes.

Assumptions, all required before output:

1. Group membership and positive group sizes are fixed before observing outcomes, or accompanied by an independently justified conditional model proving the same boundedness and independence after conditioning on the sizes. The initial unit supports the fixed case only. Outcome-driven group widths/holdings/counts, stopping and sample selection are refused.
2. The random group vectors are jointly independent across declared groups. Dependence within a group is allowed. Splitting trades across guessed independent groups is not an acceptable certificate.
3. In this initial contract, each individual trade outcome in group g is almost surely within finite bounds[a_g,b_g], justified outside the observed sample. This implies a_g<=X_g<=b_g for the group mean. A certificate bounding only the group mean is not supported by this first unit. Bounds derived from observed minima/maxima, average holding time or a risk/stop-loss target are rejected. Stops and LIMIT exits do not enforce a price gap or net-return bound by themselves.
4. Full paired cohorts and source geometry are intact. For excess returns, support needs a valid bound for both trade and benchmark, including any relevant costs; paired subtraction alone does not bound a Gaussian benchmark.
5. Group IDs, source span, declared count vector and all values are valid; no silent deletion, regrouping or denominator change. Every observed value must lie within its declared group support; violations refuse rather than clip.

In the initial synthetic implementation, assumptions are explicitly fixture-owned structural declarations, anchored to the fixture/source specification before any observations. They are not inferred from outcomes. No real-data adapter or public product certificate issuer is built. Results must say that assumption declarations are trusted research inputs and the pure math cannot verify probabilistic independence. A fabricated Boolean does not make real data eligible.

## Derivation

Let d_g=w_g*(b_g-a_g) and Q=sum d_g^2. Applying independent bounded-sum Hoeffding in each tail gives

P(|m-theta|>=h) <= 2*exp(-2*h^2/Q).

For a supplied alpha in(0,1), h=sqrt(Q*log(2/alpha)/2). The untrimmed interval is[m-h,m+h]. Intersect it with the externally known support for theta,[A,B]=[sum w_g*a_g,sum w_g*b_g]. This support intersection retains coverage under the declared assumptions; endpoints used for all reports must be recorded alongside the untrimmed ones.

Only when every exact declared a_g==b_g and every observation is consistent is theta structurally known. Different groups can have different singleton values; the result is the weighted[A,A], not one group's value. Machine Q=0 never establishes this condition. This is different from zero observed sample variance with Q>0, where h stays positive. Nonfinite arithmetic, alpha outside(0,1), bad weights/IDs/counts, inconsistent singleton observations or unknown assumptions refuse. Use conservative numerical arithmetic and stable summation; refuse overflow, underflowed/nonpositive Q for non-singleton supports, collapsed positive radius, underflowed weights/support widths, cancellation in B-A, or loss of endpoint resolution rather than manufacturing certainty. The implementation plan must account conservatively for numerical error before describing emitted bounds as guarantees; ordinary nearest-rounded arithmetic is not itself a proof of machine-level coverage.

For heterogeneous support, record B_range=(B-A)^2/Q for Q>0; this is the range-adjusted concentration quantity for the precision bound. For a common support range R, Q=R^2*sum w_g^2. Record the weight-concentration quantity B_weight=1/sum w_g^2. It is a mathematically defined effective count for this bound under the independence assumption, not an empirical measurement of time-series independence. Equal weights give B_weight=G; concentrated counts make it smaller.

## Precision and refusing an unhelpful answer

Before outcome evaluation, the caller's research specification supplies desired normalized full width epsilon in(0,1]. For B>A, use the conservative untrimmed width ratio W=2h/(B-A); it depends on fixed group sizes/support, not observed means or favorable clipping. If W>epsilon, return NEEDS_MORE_INDEPENDENT_EVIDENCE with m, h, W, the requested precision and geometry diagnostics, but no confidence-interval claim for an emitted metric. Do not change epsilon after seeing results or hide such refusals from generated denominators. Other refusals include UNKNOWN_INDEPENDENCE, UNKNOWN_SUPPORT and OUTCOME_DEPENDENT_GEOMETRY.

The common-range requirement is B_weight >=2*log(2/alpha)/epsilon^2. It is a conditional analytical requirement, not the pending product trade/block floor in Step6b. More trades within the same groups can leave B_weight unchanged. With heterogeneous ranges, report Q and required Q <= epsilon^2*(B-A)^2/[2*log(2/alpha)]; do not invent one universal required trade count.

A primary deterministic calculator, with no RNG/data evaluation, reproduced alpha=.05 normalized full widths:

| Equally weighted independent groups | Normalized full width |
|---:|---:|
|24|.554442622|
|48|.392050138|
|96|.277221311|
|119|.248993924|
|192|.196025069|

A quarter-of-support-width request(epsilon=.25) needs at least119 equally weighted independent groups. This is an illustrative precision request for deterministic fixtures, not a product width threshold or claim that119 real trading periods are independent. For wins, support is[0,1], so those normalized widths are also probability widths. Raw-return widths must be multiplied by a separately justified raw support range.

## Smallest implementation proposed for approval

Build only a pure typed research helper and deterministic tests in `scripts/research/signal_bounded_uncertainty.py` and `tests/unit/test_signal_bounded_uncertainty_research.py`. Inputs include immutable synthetic group/source/count contracts, externally declared per-group support, alpha and predeclared desired precision. Return an explicitly research-labelled typed bounded estimate, structurally known result, or refusal/insufficiency record. No existing estimator API changes and no product imports from research.

No new Monte Carlo screen or seed is proposed for this first unit. Use scripted fixtures and exact small Bernoulli enumerations as a mathematical oracle. Enumeration checks every outcome's probability for small independent experiments; it is not a random draw or a real strategy evaluation. Any later stochastic experiment needs its own predeclared roster, addresses/seed, computational envelope, assumptions and width/sensitivity criteria before generation.

Acceptance tests must demonstrate:

- Formula/weight normalization using hand sums and an independently computed oracle; original trade weights, unequal groups, permutation invariance, signed affine support transforms and numerical/overflow refusal.
- Exact exhaustive coverage at nominal confidence for predeclared small independent bounded examples. This proves those fixtures and checks the implementation; the general guarantee depends on the cited inequality/assumptions.
- All-success/no-observed-rare-event cases preserve a positive radius when declared support has positive width. Neither sample range nor sample variance controls that radius.
-192 observations in24 groups differ from192 independent units; concentration reduces B_weight; increasing within-group trade counts equally does not fake new independent information.
- Unknown cross-group dependence, unknown support, outcome-dependent geometry, duplicate/missing IDs or pairing, unsupported Gaussian excess, support violation and invalid precision/alpha refuse before an interval output.
- Precision selection uses untrimmed/support-based widths; clipped favorable endpoints cannot rescue an insufficient fixture. A precision refusal is recorded, never treated as successful coverage/emission.
- Deterministic requested precision=.25 shows24 equal groups insufficient and119 sufficient when other assumptions hold; structurally singleton support differs from identical observed values under nondegenerate support.
- Protected estimator/harness/manifest/digest/goal/lock paths unchanged, no RNG/network/broker/Panel import. Existing synthetic simulator and portfolio characterization regressions pass; mypy/Ruff clean, independent numerical plus ponytail/engineering review, post-commit mutations of actual found defects.

## Expected limits and follow-up

This benchmark does not make the serial cell28 eligible; unknown dependence refuses. It does not make unbounded Gaussian benchmark excess eligible; unknown support refuses. Dynamic outcome-driven grouping cannot be certified by treating its realized H/L as fixed. Existing45 profile results are not reclassified as passing; unsupported/refused cases stay counted and their original failures stay OPEN.

Even a perfect implementation will often report insufficient evidence, particularly for wide-support rare outcomes. That is the intended distinction between weak evidence and broken arithmetic. It is useful as a reference for later methods, not a universal signal-uncertainty replacement. We still need an independently reviewed time-dependence approach and an honest boundedness/tail-assumption contract for future real-data use. No strategy promotion, stagnation policy or minimum-data gate changes here.

## Review and authorization status

User continuation authorizes this design investigation; implementation of this new concrete assumption contract awaits the operator's plain-English review. Independent medium-effort numerical and governance reviewers approved the proposal for operator review subject to two exact clarifications now incorporated: individual-trade support rather than group-mean-only support, and structural singleton checks distinct from floating numerical degeneration. Primary independently reproduced all five displayed widths and the119-group requirement. No data/RNG evaluation or implementation occurred in this design session. Both reviewers subsequently re-read the corrected contract and approved it for operator review/docs-only commit, with no remaining proposal blocker. This is a documentation-only session: existing code suites were not rerun unchanged; deterministic analytical calculations were reproduced and protected code/config diff was empty. All previous research samples remain exposed development evidence; the original reserved streams are untouched and never repurposed. Keep inference disabled and the official Windows resource/durable-claim restrictions unchanged.
