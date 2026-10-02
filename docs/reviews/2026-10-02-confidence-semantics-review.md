# Adversarial confidence-semantics review

Date: 2026-10-02. Independent Astra review of the frozen protocol, statistics module, geometry mathematics, primary confidence summary and retained failed development. No new histories, confirmation-seal reads, source/config edits or market data. This file is the only review output changed.

## Assessment

No new implementation or mathematical contradiction found. The current interval candidate remains rejected under its frozen synthetic protocol. Neither exact moments nor correct implementation restore its nominal 95% coverage. The confidence vocabulary is defensible only with the distinctions below.

| Quantity | What it means | What it does not establish |
|---|---|---|
| Nominal 95% interval | Intended repeated coverage of one fixed target under a stated law | A verified finite-history guarantee, probability of future profit, or strategy success |
| Frozen qualification floors | Joint coverage .93, coverage conditional on arithmetic emission .94, emission .99, precision .90, tails .035 each; effect detection .80 | Coverage .95, even after a hypothetical pass |
| Simultaneous confidence at least 95% | Correctness of the 280 formal one-sided rate bounds, under IID whole-history replication | Simultaneous coverage of trading intervals, all reported diagnostics, all future candidates, or market validity |
| Exact P1 ratio moments | Bias and variance under the completely specified artificial law | Endpoint distribution, quantile accuracy, selected-output coverage or uniform validity over unknown market laws |

## Multiplicity and conditioning

The formal family is exactly 42 main cells times six statements plus four effect cells times seven: 280. Eta=1/5600 gives 280*eta=.05. Sharing paths across metrics and families does not invalidate the union bound; independence between those 280 statements is unnecessary. IID replication is required across whole histories within each cell. Overlapping block roots are not independent replication trials. Computational seed separation remains an experimental assumption, not a mathematical proof of IID draws.

Conditioning on the observed arithmetic count A is legitimate: IID replicate categories imply C given A is binomial with the law's coverage conditional on arithmetic emission. A=0 is unavailable, correctly not a passing criterion. The statistics module's threshold-valued bounds are conservative test-inversion bounds, not numerical Clopper-Pearson endpoints. Its development decision uses point rates; confirmation would use the exact threshold inversions.

Independently counted the retained terminal: 280 formal statements but 316 statements across all reported cells. The extra 36 belong to sparse limitation diagnostics and are outside the advertised 95% formal family. Existing formal flags/protocol distinguish these correctly; future summaries must not describe all 52 cells or every displayed bound as one 95% simultaneous guarantee. Nor does this allocation cover repeated candidate searches or both stages jointly.

## Precision selection is a material limitation

P is a subset of A, but there is no frozen C-intersection-P counter or criterion. C/A is not coverage conditional on a precision-ready result. A law with A/R=1, P/R=.90 and C/R=.94 can satisfy every coverage/precision floor while concentrating all .06 misses in P: precision-ready coverage is then .84/.90=.93333. Splitting those misses .03 per tail also satisfies the two tail floors. These figures describe underlying rates, not a claim about finite-sample acceptance probability.

This is observable in the already failed development. An independent streaming recount of saved endpoints, using exact rational truth comparisons and lossless Decimal decoding without production counters, found:

| Cell | Covered arithmetic / arithmetic | Covered precision-ready / precision-ready |
|---|---:|---:|
| P3 n64 win | 339/512 | 25/81 |
| P3 n128 win | 390/512 | 58/119 |
| P2 n128 win | 420/512 | 370/457 |
| P7 n128 win | 401/512 | 313/415 |

These are descriptive, post-exposure diagnostics. They establish neither a new calibrated test nor population coverage values. The missing selected-coverage guarantee is a limitation of the frozen research design, not grounds to edit its decision after seeing outcomes. It becomes an actionable defect if a report claims that the protocol guarantees coverage among usable precision-ready outputs. A future design must explicitly choose whether its confidence claim concerns all arithmetic outputs or the outputs actually exposed for decisions, and allocate any additional rate tests prospectively.

## Failure, exact mathematics and next direction

The completed development failed, so confirmation remains ineligible and undrawn. All 46 formal cells failed their coverage criteria; the baseline P1 n128 raw covered 426/512. That is a protocol rejection, not a formal proof that every cell's population coverage is below its floor. The primary's separately calculated tiny fixed-cell binomial tails at .94 and .95 are coherent diagnostic evidence under IID replication; the post-exposure labeling is appropriate. They neither estimate the true coverage exactly nor qualify a replacement method.

The primary confidence summary correctly separates Chebyshev/Markov guarantees under known exact law moments from an unknown-parameter confidence procedure. A bias correction or variance match alone does not prove interval coverage, and total two-sided error control does not supply equal-tail control. The geometry identities explain finite-window mechanisms without certifying the empirical quantiles. No claim of 95% market confidence follows from this review.

Next justified unit: one bounded mathematical proposal for the joint behavior of the estimation error, reported endpoints, arithmetic emission and precision selection. Use a tractable baseline exact-law calculation or rigorously bounded integration to assess endpoint coverage and tail allocation, or derive valid uniform bounds over an explicitly declared model class. Require a credible history-length/resource design before another sampled screen. Additional isolated moment identities or a multiplier fitted to these saved failures would not resolve the confidence question. Any revised candidate must acknowledge the exposed development, freeze a new protocol and preserve independent confirmation; strategy selection and market-assumption validation remain separate work.

## Evidence identities and scope

- Frozen protocol SHA256: `4d5d1749c799d124129ced0e3def82af91ca6f61fcccdcca7fe7a0f8fd044255`.
- Statistics module reviewed: `scripts/research/signal_calendar_statistics.py`, SHA256 `136a0b8425f2012f6e2bd0f2153481a235a13636654a5c3339c1e4e79c67e288`.
- Retained development terminal independently hashed after recount: `b9931a44708292e2f7826dc46bb6c0f1d4261bdae769083d1f60fde72dbf89ef`, in `var/research/calendar_ratio/2026-10-02-development/`.
- Read current `2026-10-02-calendar-geometry-math-review.md` and `2026-10-02-confidence-mathematics-review.md`; the latter's confidence semantics and diagnostic-binomial wording are approved with the explicit limitations above.

This is an adversarial research interpretation review, not method adoption, a rerun of the full suite, a market eligibility decision or Task3a completion. Existing failure, inference-disabled state and real-data boundary remain unchanged.
