# Finite coloring bound: independent scope review

Date: 2026-10-02. Design-only mathematical assessment. No new draws, seeds, source changes, or confirmation-seal reads.

## Verdict

The proposed coloring Hoeffding ratio bound is valid under the trusted finite-innovation law, but is inadequate for the frozen win precision/coverage criteria at n=64 or 128. Do not implement another qualification screen from this bound. A deterministic finite-window variance and random-count diagnosis is the smallest useful next step.

## Dependency and score proof

Write A_t for the session sum of the metric and C_t for its selected trade count. The population target is theta=E[A_t]/E[C_t], with positive mean count. Thus X_t(theta)=A_t-theta*C_t has mean zero without assuming exogenous or fixed counts. The ratio of expectations is not the expectation of the finite-path ratio.

In the actual frozen law, S enters at t-1 and t..t+H-1; Q enters t-m..t-1; G,J and per-symbol epsilon enter at t. Therefore the entire random input support is contained in [t-W,t+H-1], W=max(m,1). Grouping sessions by residue modulo K=W+H gives mutually independent scores within each group. Different groups need not be independent. The recorded completion/source footprint extends to t+H but the outcome formula uses no innovation there; K=W+H+1 is a valid more conservative choice based on that larger declared footprint.

Suppose the range of each X_t(theta) has length at most R for every candidate theta in the trusted parameter domain. Hoeffding's bounded-variable exponential inequality within each group, followed by Holder across K groups, gives log E exp(lambda*sum_t X_t)<=lambda^2*K*n*R^2/8. Chernoff optimization and the two tails yield P(|sum_t X_t|>x)<=2 exp(-2*x^2/(K*n*R^2)). This derivation is the reviewer's coloring extension; the independent bounded-variable ingredient is [Hoeffding (1963)](https://www.cs.rpi.edu/academics/courses/spring06/random/hoefding.pdf). It does not claim Hoeffding's independent-sum theorem directly applies to adjacent dependent sessions.

Set x=R*sqrt(K*n*log(2/alpha)/2). When total count C is positive, inverting |A-theta*C|<=x yields [A/C-x/C,A/C+x/C], intersected with the known parameter domain if desired. At zero count, return the whole parameter domain for unconditional confidence or explicitly refuse. If refusing, the proved claim is P(emitted AND misses)<=alpha; neither joint coverage >=1-alpha nor conditional coverage >=1-alpha follows without an emission guarantee. Random-count division is valid by inversion of the unconditional score event, not by conditioning on the realized count.

For a raw or paired outcome known to lie in [l,u] and theta in the same interval, a sufficient uniform daily score range is R=2(u-l). Those support endpoints must be trusted deterministic law bounds, never fitted observed extrema. For wins A_t is a success count between zero and C_t<=2 and theta is in [0,1], so X_t lies in [-2theta,2(1-theta)] and R=2 works uniformly. Shared stock shocks are already absorbed in the whole-session score; treating two symbols as independent observations would be invalid.

## Precision obstruction, including clipping

At alpha=1/20 and C<=2n, the untruncated win interval has full width at least sqrt(2*K*log(40)/n). Independently calculated values:

| n | K | Untruncated width floor |
|---:|---:|---:|
| 64 | 2 | 0.48016139565996035 |
| 128 | 2 | 0.3395253789351549 |
| 128 | 3 | 0.4158319665581168 |
| 128 | 9 | 0.7202420934899405 |
| 128 | 40 | 1.518403654770763 |

The phrase best-case full-width floor must say **untruncated**: intersection with [0,1] can shorten intervals near a boundary. That does not rescue these frozen profiles. Every frozen win truth is strictly between 0.2 and 0.8. When the untruncated width exceeds 0.2, a clipped interval of width at most 0.2 must touch 0 or 1, and hence cannot contain any of those truths. Thus precision and coverage events are disjoint for this procedure at the fixed n values. Their probabilities, and their observed fractions, sum to at most one. Required precision 0.90 and joint coverage 0.93 cannot both hold. This is a deterministic adequacy obstruction, not another sampled failure or a claim that every possible confidence method is impossible.

Even the optimistic C=2n width condition for interior coverage requires n>=ceil(2*K*log(40)/0.2^2): 369 for K=2, 554 for K=3, 1660 for K=9, and 7378 for K=40. These are necessary lower floors for this bound, not sufficient sample sizes: endogenous counts are typically lower, precision emission must be frequent, and existing footprint/resource limits still apply. No automatic n increase is warranted.

## Smallest next step

Use existing finite laws and retained development evidence to derive, without draws, the exact finite-n score variance n*gamma_0+2*sum(h=1..min(n-1,K-1),(n-h)*gamma_h), alongside the block-centered score variance and random-count effects. Separate (1) genuine finite-window subsampling geometry, (2) ratio denominator variability, (3) long holding-window overlap, and (4) rare-event absence. Begin with the simplest dense baseline, then one persistent profile. Compare deterministic variance/range adequacy to the fixed precision requirement before proposing one new estimator.

A covariance derivation may inform a new design; a normal approximation or observed variance ratio alone is not a finite-sample confidence proof. Any later candidate must state its assumptions and have a fresh preregistered development/confirmation plan. The failed attempt and its thresholds remain unchanged, and the current confirmation seal remains untouched. Approval here is for this scope conclusion and deterministic diagnosis only, not adoption of the bound or any market-data work.

### Unequal color-class refinement

The builder noted that optimized Holder weights replace K*n by B=(sum_k sqrt(n_k))^2, where n_k is the number of sessions in each nonempty residue class. Choosing Holder exponents proportional to 1/sqrt(n_k) gives the stated exponential coefficient; Cauchy-Schwarz gives B<=K*n. Independently reproduced n=128 values: K=2, B=256 and width floor 0.3395253789351549; K=5, B=639.9411708155669 and floor 0.5368120866876603; K=9, B=1151.7585488933041 and floor 0.7201666106931774; K=40, B=5101.62002695053 and floor 1.5156757924846829. These still exceed 0.2 and leave the clipping-aware impossibility of simultaneous coverage and precision unchanged. Numerical values here describe analytic geometry, not sampled outcomes.

## Review of bounded finite-window diagnosis plan

Reviewed `docs/plans/2026-10-02-calendar-finite-window-diagnosis.md` before implementation on 2026-10-02. APPROVE the pure rational toy diagnostic with the following explicit mathematical contracts incorporated before coding:

- Innovations are independent, centered, and share a finite nonnegative variance sigma^2 across time. With finite rational filter coefficients, gamma(h)=sigma^2*sum_j a_j*a_(j+h), treating absent coefficients as zero. This constructs a positive-semidefinite covariance even for signed coefficients; no need to validate arbitrary supplied covariance sequences.
- For full weights u_t=1 and block indicator v_t, full-root variance is u'Gamma*u/n; centered block-root variance is (v-(b/n)u)'Gamma*(v-(b/n)u)/b; covariance between adjacent centered roots uses the corresponding two weight vectors and the same denominator b. Exact rational outputs require no numerical square roots.
- The iid identity is sigma^2*(1-b/n) for a unit filter, or 1-b/n after normalizing to unit score variance. Do not assert the latter for arbitrary innovation variance.
- Require exact integer geometry 1<=b<=n<=256, nonempty filter length<=64, strict rational coefficient/variance validation and explicit Boolean/float refusal. Adjacent means block starts i and i+1; when b=n there is one block and no adjacent pair, with centered variance exactly zero. Zero variance/all-zero filters are legitimate degenerate toy models.
- The ratio identity is algebraically exact: Y_B/C_B-Y_N/C_N = (S_B-(C_B/C_N)*S_N)/C_B, S=Y-theta*C. Validate positive counts with C_B<=C_N, exact rational totals/theta and appropriate integer count types. It does not require theta to equal a population truth. When count per session is constant, C_B/C_N=b/n; otherwise the replacement is unjustified.

Independent coefficient-vector quadratic/bilinear tests, signed-filter and overlapping-block cases, endpoint geometry and uneven-count examples are appropriate. The plan makes no actual-law covariance claim, Gaussian inference, interval correction, sample-size guarantee, or alteration of the failed study. These boundaries are part of approval. The smallest useful result is exact toy geometry that separates an identity from an explanation requiring further evidence.
