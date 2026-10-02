# Artificial calendar runner: independent mathematical review

Date: 2026-10-02. Reviewer: independent Astra mathematical reviewer, medium effort.

## Verdict and scope

APPROVE the frozen laws, compact evaluator, exact statistical criteria, and the dated predraw resource amendment within this mathematical scope. The amendment changes operational budgets before experimental outcomes; it does not relax statistical acceptance or select successful outcomes. This is not approval of market eligibility, finite-sample subsampling validity for arbitrary markets, or every engineering guard in the runner. Fresh exact-source preflight and the separate engineering review remain required before sampling.

No RNG, sampled experimental paths, market data, reserved streams, broker access, source modifications, or product threshold changes were used in this review. Deterministic invented patterns and exact arithmetic were used. Only this review document was written.

## Verified SHA256 snapshots

- Original protocol: `4d5d1749c799d124129ced0e3def82af91ca6f61fcccdcca7fe7a0f8fd044255` (previous independent protocol review).
- Amendment: `06ab50ce55fc0b6eb225f7959d7202ad8afc11835bc0c9bf5f367bd51bba9d7c`.
- `signal_calendar_laws.py`: `811070fa4247a10c5aad612829a6b3f20421f04793a77a3b44017e7ee18b6ba4`.
- `signal_calendar_compact.py`: `e18e49a7d8cdf8d3c975a08c6b4267bb37d3d0ca42a25f9c793f5ad29d442969`.
- `signal_calendar_statistics.py`: `136a0b8425f2012f6e2bd0f2153481a235a13636654a5c3339c1e4e79c67e288`.
- Runner observed during final review: `9773041cc145ab08229f45f402be5f8da825b4567d561b35912504639be2831b`. Runner was still changing; this records a snapshot, not a full final engineering approval. Targeted inspection covered decimal encoding, word mapping, and projection formula.

## Independent deterministic evidence

Ran the compact and statistics unit modules together: **32 passed in 3.08 seconds**. Compact equivalence tests compare complete semantic summaries against the unchanged reference across all 18 path families and four deterministic shapes (72 comparisons), plus malformed inputs, zero counts/slices, strict zero-win handling, degenerate quantiles, and frozen resource limits. Read the compact integer-unit, prefix-sum, exact-ratio, quantile-rank, endpoint, and refusal implementation.

Independently reproduced 480 cutoff cases: N=1..40, six distinct frozen thresholds, both directions, using direct binomial coefficients and power sums rather than the production streamed recurrence. All matched. Also reproduced the fixed N=32768 cutoffs below. Public validation now rejects Boolean denominators and float thresholds even after a cache-equivalent valid call; this closes the earlier cache validation finding.

For development counts (R,A,C,Tlo,Thi,P,D)=(512,512,490,11,11,512,0), emission passes the point criterion while its certified bound fails and reports zero. This correctly preserves separate development point and simultaneous-bound decisions.

## Exact inference contract

For p=a/d, c=d-a, let T_j=choose(N,j)*a^j*c^(N-j), D=d^N. A lower CP bound is at least p exactly when 5600*sum(j=k..N,T_j)<=D; an upper CP bound is at most p exactly when 5600*sum(j=0..k,T_j)<=D. The implemented integral neighboring-term recurrences are exact and assert zero division remainder. Impossible lower/upper cutoffs remain N+1/-1. N=0 remains unassessable.

At N=32768: emission requires 32504; joint coverage 30638; precision 29684; detection 26473; either tail permits at most 1029. Conditional coverage with A=32768 requires 30955. Conditional coverage given the random arithmetic count is binomial under independent identically distributed replicate pairs; endogenous within-path signal counts do not invalidate that replicate-level statement.

The reported lower bound equals p on exact threshold success and zero otherwise; the upper equals p on success and one otherwise. Each is pointwise outward from its numerical CP endpoint. Therefore it is a valid conservative one-sided bound with the same error guarantee. They must remain explicitly labeled `CONSERVATIVE_THRESHOLD_BOUND`, not numerical CP endpoints. Union bounding 280 statements at eta=1/5600 gives total error at most 0.05 without independence across cells. This applies separately to each reported phase; development point acceptance is not a simultaneous confidence claim.

Under the hypothetical ideal A=P=1, coverage 0.95, each tail 0.025, and effect detection 0.90, the previously independently checked rejection probabilities are: joint 3.248505704089595e-33, conditional 6.203600586669912e-6, each tail 3.871209425966438e-13, and a negligible detection contribution. The union bound over 46 formal cells and four effect statements is approximately 0.00028536566260194265, hence ideal overall pass probability exceeds 0.9997. This is not a measured calculator operating characteristic. The original R=4096 poor-power finding remains in the protocol history.

## Laws, targets, and compact equivalence

Selected-trade means are exact ratios of stationary joint process expectations, not fixed-count assumptions. All principal profiles have raw truth zero and paired truth -1/200. Effects have raw +/-1/25 and paired +7/200 or -9/200. Strict-positive win truths independently enumerated are P1=1/4, P2=7/12, P3=121/256, P4=9887/24576, P5=1143/2048, P6=3577/6144, P7=74146261351971311/144115188075855872, and L1=7/12.

Conditioning on shared S,Q,J,G leaves independent per-trade epsilon innovations. For raw and paired ratio scores W=A-theta*C, variance per session has lower bound E[C*V^2]>0. For wins the corresponding bound is E[C*1{-V<base<=V}]/4>0. Finite dependence supplies the long-run limit. Exact selected straddle probabilities are respectively 1/2,1/2,7/16,1695/4096,1501/3072,511/1024,50815815317021065/72057594037927936, and 1/2; sparse intensity is positive. Dividing score long-run variance by squared mean count yields the ratio variance. Shared shocks and endogenous counts remain present.

The compact evaluator uses exact common integer units, identical counts, strict wins, exact Fraction deviations, and the reference endpoint routine. It keeps whole-component zero-slice refusal and degenerate-root/quantile refusal. Its validity is restricted to the frozen bounded laws and dimensions; it is not a generic replacement for the validated reference API.

## Geometry and resource arithmetic

For W=max(m,1), H holding span, and b=min integer with b^3>=n^2, maximum rows=2n, total footprint=2n(W+H+5), expanded footprint=2(W+H+6)b(n-b+1). At n=64, b=16 and q=49; at n=128, b=26 and q=103. P7 n=128 has 256 rows, total footprint 11520, and expanded footprint 246376 below 262144. P7 n=192 would require 497352 expanded entries and is ineligible. This prevents silently treating larger n as feasible.

There are 18 path families, 52 metric cells and 46 formal cells. Development is 9216 paths / 26624 metric evaluations; confirmation is 589824 paths / 1703936 evaluations. Sparse emission is bounded above by 1-(49/50)^b: approximately 0.2762022794075042 or 0.408604564816681 for the two b values. The frozen sparse limitation and restricted dense-family qualification remain essential.

## Predraw amendment and remaining limitations

The reviewed amendment preserves original protocol bytes, law families, targets, sample sizes, all 280 statements, eta, acceptance criteria, sparse limitations, and the rule that failed development cannot authorize confirmation. Confirmation alone changes to 10800 seconds and 3 GiB; development remains 1800 seconds and 2 GiB; memory remains 2 GiB and one worker. Original blocked preflights must remain visible. Under the stated absence of experimental outcomes, this changes operational feasibility without statistical outcome selection.

The inspected projection is 4*32768*sum_f(max measured time for family f)+60 seconds and 2*32768*sum_f(max measured serialized bytes for family f)+16 MiB. Weighting family maxima by their fixed known replicate counts is arithmetically appropriate and preserves both margins; no family or outcome is removed. Charging the global worst family to every replicate was a coarser projection, not a statistical requirement. Neither formulation proves a worst-case runtime or artifact bound over every possible path. Representative-pattern timing, machine variation, refusal paths, rejection draws, verification, and reporting overhead can differ. Fresh exact-source preflight plus supervised cancellation remain necessary; this review supplies no Windows hard-resource certificate.

The inspected decimal codec retains coefficient, exponent, and sign, including signed zero, rather than shortening endpoints. The inspected counter maps all four big-endian 64-bit lanes per SHA256 digest and uses rejection before modulo. Uniform atom mapping is exact conditional on uniform words; computational pseudorandom stream independence remains an explicit experimental assumption, not a mathematical IID proof.

Parent-reported fixes to seed/path binding, verified-report provenance, confirmation seed separation, and mid-verification supervision require the separate engineering reviewer and final frozen-source checks. They are not inferred from the mathematical proofs above. Any later source change requires matching this review's scope against the final manifest. No outcome-based restart, automatic budget rescue, market eligibility, product adoption, or real-data run is authorized by this review.
