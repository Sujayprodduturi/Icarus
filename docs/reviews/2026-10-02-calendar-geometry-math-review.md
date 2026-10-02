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
