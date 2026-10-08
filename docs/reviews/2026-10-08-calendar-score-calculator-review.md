# Calendar-score calculator review

Date: 2026-10-08. Reviewed source HEAD `8819514944ea91365e5fa14ea32f772f4bca0913`. Active calculator: `scripts/research/signal_calendar_score.py`, SHA256 `7b19acfe21715fe082b13879ea9d3348d769131ab596553baf0c20fd5c600fc7`. The historical rejected estimator is not the reviewed calculator.

## Result in plain English

**Pass for its current invented-data use. No reproduced calculation or refusal defect requires a runtime change.** Two independent reviewers checked mathematics and defensive/integration behavior. The parent inspected their work, reproduced both deterministic harnesses and independently checked key fractions, outward endpoints, refusals and adversarial limitations.

The calculator produces a conservative range for average return, win rate and return above an invented benchmark. It accounts for related dates and variable trade counts. It decides whether a history is long enough before seeing its outcomes, so a lucky narrow result cannot qualify a short history. Invalid inputs and unsupported assumptions refuse; sparse histories retain an unsupported label.

This does not certify a real strategy or the assumptions behind real-market data. A caller can label arbitrary totals as fixture-declared. A concrete shared-bit counterexample falsely declares independent dates and obtains intervals missing the true win rate on both possible paths. That is outside the asserted model, and proves why declarations cannot replace source-bound evidence. The current frozen artificial caller has its own specified laws and independent replay; no production calculator adapter was found.

## Verification

| Check | Fresh result |
|---|---|
| Parent score/geometry/law/portfolio-characterization regressions | 129 passed in 4.05 seconds |
| Boundary reviewer focused score regressions | 52 passed; overlapping tests, not 181 unique tests |
| Boundary deterministic probes; also rerun by parent | 22/22 passed |
| Independent math harness; also rerun by parent | 1,088 daily-law states; 128 small complete histories; 40 scalar/optimized/verifier cases; 24 rounding cases; 60 exact small binomial cutoffs |
| Parent independently authored exact arithmetic/adversarial checks | Passed; width squares 1/16000, 5/128, 1/25000; joint lower 6792175/7082479 |

The three-fixed-metric model guarantee is conservatively at least 95.901%, conditional on genuine model assumptions. It is not a guarantee across searched strategies, repeated studies or unauthenticated market histories. The finite study remains evidence for the frozen invented families only; no additional full raw replay or sampled study was performed in this review. Large binomial cutoff checks use a numerical crosscheck in addition to exact small-case sums, and are not presented as new exact large-case proofs.

The mathematical basis is [Janson's Theorem 2.1](https://api.newton.ac.uk/website/v0/events/preprints/NI02024), with mutual independence within each proper-cover class. The mathematics reviewer retrieved the full primary text live. Parent PDF fetches timed out; parent independently checked the mapping from daily score support width 2 Delta to the implemented radius and tail allocation, and retrieved [publisher metadata and abstract](https://onlinelibrary.wiley.com/doi/10.1002/rsa.20008). Access limitations are recorded rather than treated as a fresh parent full-text check.

## Findings and applicability rules

1. **No active arithmetic/refusal defect reproduced.** Formula, random counts, outward rounding, exact point targets, bounded inputs, duplicate metrics and dense/sparse adequacy behavior passed the checks above. This is a scoped review, not an audit of every runtime or all possible paths.
2. **P2 / existing M4 integration prerequisite remains open:** caller declarations and aggregate checks do not prove complete dates/cohorts, per-trade bounds, stationarity, within-class independence, cost or benchmark provenance. Do not expose this helper as a real-data decision API. Observed extrema, low autocorrelation and a synthetic PASS cannot establish those premises.
3. **P3 optional unit-test coverage improvement:** pin NaN/inf, exact 256-bit acceptance, maximum geometry/count and self-asserted declaration behavior in the permanent unit suite. The review probes pass these cases; this is not a demonstrated code failure.
4. **Practical insufficiency remains possible:** the frozen formal profiles require 2,048 to 131,072 complete calendar positions. These are artificial geometries, not adopted real-market data floors. Positive benchmark excess also requires exact charges/taxes, complete time-resolved matching and trial-search correction outside this calculator.

## Next work

This closes the requested calculator review, not Task3a or overall method adoption. No further calculator calibration run is justified by these findings. Next implement the already scheduled Step7 atomic counted-trial persistence, with a bounded plain-English proposal and reviewer check. Before Step8 real-data evaluation, separately review the applicability/refusal contract and explicit dependency/schedule amendment covering F48 exact delivery-DP fees, approved source/artifact, dual-clock M15 replay and complete benchmark matching. Keep inference disabled and stop before real-data execution. D44 raw cleanup is optional separate guarded work; none occurred here.

No runtime, goal, pinned source/protocol, thresholds, experimental streams, raw evidence, broker or live path changed. Existing v2 ERROR and v3 PASS evidence remain retained. M1-M4/R4/Task3a/F48 remain open for their broader acceptance conditions.

Detailed reviewers: [mathematics](2026-10-08-calendar-score-calculator-review-math.md), [boundaries](2026-10-08-calendar-score-calculator-review-boundary.md). Compact source hashes, reviewer evidence and parent reproductions: [proof](2026-10-08-calendar-score-calculator-review.json).
