# Calendar geometry: independent mathematical review

Date: 2026-10-02. Verdict: APPROVE within the explicit rational toy-model scope.

Reviewed source SHA256: `5f068bd188d75f869c4b442e1991601271413ca0af2b99e2be3708da9ea06f74` (`scripts/research/signal_calendar_geometry.py`). This review does not adopt a confidence method or change the failed calendar estimator. No sampled paths, seeds, confirmation-seal reads, source edits, or market data were used.

## Formula inspection

For a finite filter a and independent centered innovations with common variance v, gamma(h)=v*sum_j a_j*a_(j+h) is implemented exactly. The finite sum variance n*gamma(0)+2*sum_h(n-h)*gamma(h) correctly truncates at min(n-1,L-1). Full-sum covariance row prefixes include both finite boundaries, so blocks at different positions can have different centered variances.

Centered block weights are block_indicator-(b/n)*full_indicator; quadratic forms divide by b, and the full-root form divides by n. Adjacent uncentered block covariance equals block variance-gamma(0)+gamma(b): their difference is Z_start-Z_(start+b), whose variance is 2*(gamma(0)-gamma(b)). This justifies the implemented adjacent formula including signed autocovariances. For b=n, centered variance is zero and there are no adjacent pairs.

The ratio identity uses observed count weight C_B/C_N and holds for every finite theta, not only a population truth. Signed totals are legitimate. No expectation, normal approximation, confidence interval, or random-count distribution is inferred.

## Independent deterministic computations

Constructed a separate session-by-innovation coefficient matrix, summed its columns for full sums and each centered block, and used innovation-space dot products. This bypasses the production autocovariance and row-prefix implementation. Eight additional cases used (filter length,n,b): (4,13,1), (7,19,8), (19,11,6), (64,3,2), (64,256,255), (3,256,26), (8,31,31), (1,1,1). Coefficients were a_j=(-1)^j*(j+1)/(2j+3), innovation variance 7/11. This covers filter length exceeding the observation window, both geometry maxima, signed rational filters, and full-window degeneracy.

All eight full-root variances, 268 centered-block variances, and 260 adjacent covariances matched exactly. Every checked variance was nonnegative. Separately reproduced:

- Unit iid score, n=64,b=16: every centered variance 3/4; adjacent covariance 11/16.
- Unit iid score, n=128,b=26: every centered variance 51/64; adjacent covariance 631/832.
- Filter (1,-1), unit innovation variance, n=64,b=16: full-root variance 1/32; endpoint centered variances 13/128; all interior centered variances 17/128.
- Ratio totals Y_N=10,Y_B=3,C_N=20,C_B=16,theta=1/5: both identity sides -5/16; observed count weight 4/5.

## Validation and limitations

Read all scalar, shape, geometry and count checks. Independently exercised 11 rejection cases: Boolean geometry, n=257, b>n, filter length 65, denominator beyond the 256-bit input limit, negative innovation variance, float coefficient, Boolean coefficient, zero block count, block count exceeding full count, and Boolean count. All raised GeometryError. An allowed denominator with 256 bits and zero innovation variance at n=b=256 returned exact zero, confirming that legitimate degeneracy is retained.

Exact type checks reject bool and float throughout the public scalar contracts. Geometry requires 1<=b<=n<=256; coefficients require a nonempty tuple of length<=64; counts are positive consistent exact integers; numerators and denominators are bounded at entry. Intermediate rational arithmetic can grow beyond 256 bits, but finite input dimensions and bit bounds keep that growth bounded; the input limit is not misleadingly imposed on correct intermediate results.

The implementation's PSD guarantee follows from its finite independent-innovation construction, not from testing arbitrary covariance data. These exact toy identities may motivate further analysis, but do not establish actual frozen-law covariance, explain all observed undercoverage, or supply a replacement estimator, finite-sample guarantee, or universal data minimum. Reported project tests/static checks are separate from the independent computations above; this review makes no independent claim to have rerun the full project suite.

## Read-only next-proposal consultation: exact frozen-law score moments

The following is an independently checked analytic extension for the already declared artificial laws, not implementation approval or adoption of an estimator. No new histories, seeds or source changes were made. Here Y_t means the **session total**, theta is the known selected-trade population mean, and W_t=Y_t-theta*C_t. Set p=p_G, a*=a for raw or a-BENCHMARK_PREVIOUS for paired, and g*=gamma for raw or gamma-BENCHMARK_FORWARD for paired. Write D_t=3/2+S_(t-1)/2, C_t=G_t*D_t, and H for the holding span.

The centered score decomposes exactly into (4*a*/3)*G_t*S_(t-1) + (g*/H)*C_t*sum(i=0..H-1,S_(t+i)) + C_t*J_t + V_t*sum(s=1..C_t,epsilon_(t,s)). This uses the true raw/paired theta; an arbitrary theta would add a count term. J is mean zero in both asymmetric-jump profiles. E[C_t]=3p/2 and E[C_t^2]=5p/2.

Consequently the proposed score covariance is correct:

- gamma_W(0)=p*[16*(a*)^2/9 + 5*(g*)^2/(2H) + (5/2)*E[J^2] + (3/2)*E[V^2]].
- For integer h>=1, gamma_W(h)=p^2*[(9/4)*(g*)^2*(H-h)_+/H^2 + (2*a* g*/H)*1{h<=H}].
- It is zero for h>H; covariance at negative lags is symmetric.

The lagged cross term is the earlier forward shock overlapping the later previous-shock term. The reverse pairing vanishes. For forward-forward products, the random later count's extra S_(t+h-1) factor creates odd sign moments that vanish, leaving the 9/4 overlap coefficient. Conditional centering of J and epsilon kills all cross-time contributions from those noises, even though V is persistent. Zero covariance past H does **not** establish independence past H: volatility can still create dependence in nonlinear functions such as squared scores or wins.

The long-run score variance is gamma_W(0)+p^2*[(9/4)*(g*)^2*(H-1)/H+4*a* g*]. Exact finite-n score variance is n*gamma_W(0)+2*sum(h=1..min(H,n-1),(n-h)*gamma_W(h)). These score formulas must not be called exact variance of the sample trade ratio.

### Independent atom checks and selected exact values

Enumerated all relevant S signs and both gates, with exact probability weights, for H=1,2,3,4, lags 0..H+1, and three (a*,g*,p) settings: (1/7,-2/9,2/5), (-3/11,4/13,1), (0,2/5,1/50). All **54** conditional-score covariance cases matched. Separately enumerated full single-time atoms at H=1,2, including two Q indicators, volatility 1/5 or 3/7, both symbol epsilon signs, and asymmetric mean-zero J with values -2 (probability 1/3) and +1 (2/3). Both exact score means were zero and both variance formulas matched. These invented finite-atom checks test algebra, not sampled operating behavior.

Selected actual-law exact values (gamma_W(0), gamma_W(1), long-run score variance): P1 raw=(1/2500,0,1/2500); P1 paired=(107/500000,0,107/500000); P3 raw=(149/180000,79/160000,251/45000); P7 raw=(141948688427/75497472000000,343/2560000,526042077227/75497472000000); L1 raw=(13/1125000,1/12500000,659/56250000).

### Exact score/count joint moments and approximate ratio implication

The count sequence is iid because C_t uses only the independent pair (G_t,S_(t-1)); sharing those innovations with scores does not change this count-only fact. Therefore Var(C_t)=5p/2-9p^2/4 and its nonzero-lag autocovariances vanish. The proposed cross moments are also correct:

- Cov(W_t,C_t)=2*a* p/3.
- Cov(W_t,C_(t+h))=3*g* p^2/(4H) for 1<=h<=H, zero for h>H.
- Cov(C_t,W_(t+h))=0 for h>=1.

Thus Cov(sum W,sum C)=n*(2*a* p/3)+sum(h=1..min(H,n-1),(n-h)*3*g* p^2/(4H)). Independently checked **162** exact count-count and directional score-count atom cases using the same finite S/G enumerations; all matched.

Expanding E[(sum W)/(sum C)] around mean total count 3pn/2 suggests the second-order term -Cov(sum W,sum C)/(3pn/2)^2. This is a **Taylor approximation**, not exact ratio bias, a confidence guarantee, or a statement conditional on nonzero-count emission. Small or zero count cases particularly resist this approximation. For P1 raw at n=128 the term is exactly -127/4915200, approximately -0.000025838216145833334; the previously proposed decimal -0.0000258374 was slightly inaccurate. No empirical comparison was independently recomputed for this appendix.

Recommendation: these proved raw/paired score and count moments can support one bounded deterministic **actual-known-law covariance diagnosis** before proposing a new estimator. Keep win-score moments, random-denominator distribution, centered ratio-block behavior, and finite-sample interval coverage explicitly unresolved. Compute exact finite-window score geometry first; do not turn variance agreement into a width correction, universal data floor, revived confirmation authorization, or market claim. The existing toy module and failed study remain unchanged.

## Exact P1 finite-ratio moment oracle: independent review

Read the parent's scratch `exact_p1_ratio_oracle.py` and `exact-p1-ratio-moments.json` without executing the script that writes its output. VERIFIED the P1 raw and strict-win finite-sample moments. This strengthens the P1 baseline diagnosis beyond the earlier Taylor approximation, while proving no interval coverage statement.

Let B_i=1{S_(i-1)=+1}, C_i=1+B_i, total C=n+sum B_i, and D=sum(i=0..n-2,(1+B_i)*(2B_(i+1)-1)). Conditional on sum B_i=k, distinct bit products have expectation f_j=choose(k,j)/choose(n,j), with f_0=1 and terms beyond available dimension irrelevant/zero. The remaining S_(n-1) is independent of these n count bits. Writing m=n-1, adjacent=m-1 clipped at zero, and disjoint=choose(m,2)-adjacent, the proposed E[D|k] and E[D^2|k] are correct.

Independently expanded Boolean multilinear polynomials with idempotence B_i^2=B_i. Degree coefficients obtained were: single edge (-1,1,2), squared edge (1,3), adjacent edge pair (1,-4,1,6), and disjoint pair (1,-2,-3,4,4). Their expectations against f_j reproduce exactly the supplied formulas. A separate fixed-count combination enumeration verified E[D], E[D^2], and E[C_last^2]=1+3f_1 for every n=1..9 and k=0..n: **54 conditional cases**. This independently tests edge-overlap counting and small-dimension boundaries rather than repeating the supplied sign-enumeration loop.

For raw returns the centered numerator is (D+C_last*S_last+sum selected epsilon)/100. Given the count bits, its conditional mean is D/100 and noise variance is (C_last^2+C)/10000. For strict wins, a trade wins precisely when its forward shared sign and its epsilon are both +1. Given all shared signs, expected wins are one half the count on positive-forward sessions. Subtracting C/4 gives conditional score mean D/4 after integrating the last shared sign, and conditional noise variance (C+D)/8+C_last^2/16. The first term is mean per-trade Bernoulli noise variance; the second is variance from the independent final shared sign. Thus the supplied raw and win second moments are correct, including the shared-last-sign contribution.

Recomputed exact unconditional bias and variance using independently derived polynomial coefficients and exact Binomial(n,1/2) weights. All four rational bias and variance strings in the retained output matched exactly:

| P1 metric | n | Exact-bias decimal display | Standard-deviation display |
|---|---:|---:|---:|
| raw | 64 | -0.00005135619327710654 | 0.0016673698819410995 |
| raw | 128 | -0.00002586035123746633 | 0.0011787793233363879 |
| win | 64 | -0.0012839048319276635 | 0.04874765804743471 |
| win | 128 | -0.0006465087809366583 | 0.034509151155907566 |

Here raw bias is relative to zero and win bias to 1/4. Rational moments are exact; displayed standard deviations use floating-point square roots for readability. P1 count is always positive, so no conditioning-on-emission issue arises for these ratio moments. The oracle does not characterize the selected intervals, their endpoints or block-count dependence, and therefore neither diagnoses the whole cause of undercoverage nor supplies an adopted correction. It does not extend automatically to other profiles, paired returns, sparse counts, or market data. No new stochastic histories, seeds or confirmation reads occurred.

Reviewed scratch oracle SHA256: `191c5670ab631c3183b3ce6c99133d235bb2919544d61a7aeb63ae17198a9331`. Reviewed exact-moment output SHA256: `f1b91af2cf34b582322e00f6a4a04a5ef50260f48097f2437d332830e480a5ab`.
