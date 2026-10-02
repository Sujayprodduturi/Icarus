# Does the uncertainty mathematics justify its confidence?

Date: 2026-10-02. Scope: review of retained artificial evidence, exact mathematical calculations and independent reviews. No new stochastic histories, real-market data, held confirmation root or production inference. The failed candidate and frozen protocol remain unchanged.

## Operator explanation

The simulator answers what trades a strategy would have taken and what happened to them. The uncertainty calculation answers how much we can trust the apparent average return or win rate. A 95% range should contain the true underlying answer in at least about 95 out of 100 repeated histories under its stated assumptions. It does not mean a strategy has a 95% chance of making money, nor that its next trade has that chance of winning.

The current calculator is implemented correctly, but its confidence is not reliable at the tested history lengths. Even the simplest artificial market covered the known answer in only 426 of 512 histories, about 83%. All 46 formal cases failed their coverage criteria. This invalidates the calculator's qualification; it does not show that trading strategies failed.

Exact mathematical checks now give a trustworthy reference for the simplest artificial market. They establish its average estimation error and variability. Those are useful checks, but neither correct variance nor a familiar multiplier automatically gives a valid 95% range. A proven conservative rule can give a guarantee under that known model, at the cost of a wider range. For its win rate the simple conservative reference is still wider than the research requirement.

The next design must handle whole shared market periods, random trade counts and rare events explicitly. More artificial repetitions would measure the same short-history problem more precisely; they would not give each history more information. We need a justified method and history-length/resource design before another study.

## Primary mathematical checks

The reviewed exact P1 moments are retained in `var/verification/2026-10-02/calendar-geometry/exact-p1-ratio-moments.json`. The primary independently read their rational bias and variance, used 60-digit Decimal square roots, and checked the bounds below with `confidence_review_primary.py` in that directory. Decimal displays here are explanatory, not outward-rounded executable endpoints.

For the finite-history ratio X, let b=E[X]-theta and v=Var(X), both supplied by the fully specified artificial law. Chebyshev applied to X-E[X] gives P(|X-theta-b|>=sqrt(v/alpha))<=alpha. Thus an oracle range centered at X-b with half-width sqrt(v/alpha) covers that law's theta with probability at least 1-alpha. Without bias correction, applying Markov to (X-theta)^2 gives radius sqrt((v+b^2)/alpha). Neither rule assumes independent trades inside X; the exact ratio moments already incorporate shared inputs and random counts.

| P1 metric | Calendar dates | Bias-corrected Chebyshev 95% full width | Research full-width requirement |
|---|---:|---:|---:|
| raw return | 64 | 0.014913409599 | 0.02 |
| raw return | 128 | 0.010543322790 | 0.02 |
| win probability | 64 | 0.436012308552 | 0.2 |
| win probability | 128 | 0.308659231322 | 0.2 |

These are guarantees for the known P1 law only, not a new strategy-judging method. Its target is already known. To call such a construction an unknown-parameter confidence procedure requires valid moment bounds throughout a declared parameter/model family, with inversion or a uniform bound; knowing moments at one truth does not supply that. Equal-tail control is also separate: Chebyshev's total 5% miss bound does not imply at most 2.5% misses on each side. The independent oracle review supplies the separate one-sided analysis. The win-width failures rule out these particular moment bounds at these lengths, not every possible exact-law method.

The primary also independently computed the exact lower binomial tail as a direct sum of integer combinations, without the production recurrence:

- P(Binomial(512,0.94)<=426)=9.10029427735710865e-18.
- P(Binomial(512,0.95)<=426)=1.18692361132513951e-22.

Under independent whole-history replications and a fixed cell, the baseline failure is therefore far larger than ordinary replication noise would explain if actual coverage were at least 94%. These are diagnostic, post-exposure checks; they do not replace the frozen development decision or certify the exact actual coverage. Computational PRNG independence remains the study's experimental assumption.

For a rare atom occurring with probability 1/512 per date, the exact chance of no such atom in 128 core dates is (511/512)^128, approximately 0.778610421493. Many short histories genuinely contain no example of the important tail. This supports the already observed rare-event diagnosis without generating new data; it does not prove that a generic wider-block multiplier solves it.

## Confidence levels that must stay separate

1. A nominal 95% interval concerns repeated coverage of one fixed target under a specified law. The calendar candidate has an asymptotic justification, not a proved finite-history 95% guarantee.
2. The frozen synthetic qualification accepts simultaneous evidence for specified tolerances: joint coverage at least 93%, arithmetic-emission-conditional coverage at least 94%, emission at least 99%, tails at most 3.5% each and precision at least 90%. Passing those tolerances would not prove coverage at least 95%.
3. The confirmation experiment allocates 1/5600 failure probability to each of 280 one-sided qualification statements: 42*6+4*7=280 and 280/5600=0.05. The union bound remains valid when metrics share a path. This is confidence in the qualification measurements, not the interval's coverage probability and not a market-success probability. The development screen was not confirmation and failed.
4. Arithmetic-emission-conditional coverage is not automatically coverage conditional on a narrow, precision-ready range. For example A/R=1, C/R=.94 and P/R=.90 permit only .84/.90=93.33% coverage among precision-ready outputs: all .10 non-precision outputs can be covered. This is a limitation of the declared claims, not a reason to change the frozen gate after results. Independently decoding saved endpoints as exact fractions, the primary reproduced P3/n128 win: 390/512 arithmetic ranges covered, but only 58/119 precision-ready ranges covered (48.74%). P3/n64 similarly gives 339/512 versus 25/81. These exposed-data diagnostics do not invent a new acceptance criterion; any future report claiming confidence specifically for usable outputs needs a matching selection-aware justification. All strategies/metrics tested or selected later add another selection issue. Strategy search and validation remain separate outstanding work.

Only the 280 formal statements belong to the advertised simultaneous confirmation family. The additional 36 sparse-cell statements are descriptive, so all 316 reported statements must not be labeled jointly certified at 95% by this allocation.

The statistics module's reported threshold-valued bounds are deliberately conservative, coarse bounds, not numerical Clopper-Pearson endpoints. The exact binomial decision boundary and clear labeling preserve their stated role. No new code defect is established by this review.

## Next direction and held boundaries

Require one revised proposal to state the target, law/assumptions, finite-history versus asymptotic claim, random-denominator treatment, complete dependence footprint, treatment of unseen tails, emission/precision selection and confidence allocation. Assess a longer-history geometry/resource design before another sampled study; do not declare a universal minimum history from the P1 example. Any new candidate must acknowledge the exposed failed study, freeze its choices and retain an independent confirmation boundary. Do not fit a multiplier to make the saved histories pass.

The independent [oracle review](2026-10-02-confidence-math-oracle-review.md) and [confidence semantics review](2026-10-02-confidence-semantics-review.md) provide separate mathematical and adversarial checks. Task3a/M1-M4 stay open; inference remains disabled. No production code changed, so the previous 2108-pass/10-skip regression is historical evidence, not a freshly rerun suite.

## Sources checked in this review

- [Stanford EE178/278A lecture 9, Chebyshev theorem](https://stanford.edu/~dntse/classes/ee178_278a_spring14_notes/lecture9.pdf), checked 2026-10-02: finite-variance deviation inequality. The ratio-specific application and width requirements here are project calculations.
- [Politis, Romano and Wolf, On the Asymptotic Theory of Subsampling](https://www3.stat.sinica.edu.tw/statistica/oldpdf/A11n49.pdf), section 4, checked 2026-10-02: increasing block size, vanishing block/history ratio and dependence conditions; no fixed-n coverage guarantee is provided by that limit statement.
- [NIST confidence-interval handbook](https://www.itl.nist.gov/div898/handbook/prc/section2/prc241.htm), checked 2026-10-02: exact binomial confidence limits. The study thresholds, family allocation and coarse reported bounds are project-owned.
