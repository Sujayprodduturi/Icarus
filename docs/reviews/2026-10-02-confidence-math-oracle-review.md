# Confidence mathematics: exact P1 moment oracle

Date: 2026-10-02. Read-only mathematical assessment; no new histories, seeds, confirmation-seal reads, estimator/source changes or adoption.

## Assumptions and confidence meaning

Use only the frozen artificial P1 law, complete n-session paths with n=64 or128, and the exact selected-trade raw mean T or strict-win fraction T. P1 has C_t in {1,2}, so the full-path ratio is always defined. Its targets are raw theta=0 and win theta=1/4. Let beta=E[T]-theta and v=Var(T), using the independently verified exact finite-ratio moments, including endogenous counts and shared shocks. These are population oracle quantities, not estimated sample variance or estimated bias.

The moment source is `var/verification/2026-10-02/calendar-geometry/exact-p1-ratio-moments.json`, SHA256 `f1b91af2cf34b582322e00f6a4a04a5ef50260f48097f2437d332830e480a5ab`. The exact finite-count derivation and independent checks are in the P1 appendix of `2026-10-02-calendar-geometry-math-review.md`. The arithmetic below consumes its exact rational strings, not rounded displays.

A frequentist 95% confidence statement means that at least 95% of intervals constructed from repeated complete paths under that same law contain its fixed target. It is not a posterior 95% probability for the target after observing one path, a 95% chance of profit on the next trade, or a guarantee that 95% of realized trades win. Raw-return mean and win probability are different targets. Pointwise validity under this known law does not imply uniform validity across unknown market laws. Since this oracle already specifies the target and moments, its role is a mathematical calibration baseline, not an operational inference method for an unknown market target.

## Finite-sample bounds and proof

Put X=T-beta-theta. Then E[X]=0 and E[X^2]=v exactly. Markov applied to X^2 gives P(|X|>r)<=v/r^2. Hence I_C(T)=[T-beta-sqrt(20v), T-beta+sqrt(20v)] has coverage at least 19/20, without a Gaussian approximation, asymptotics, or independence among trades inside a path.

Cantelli follows by applying Markov to (X+s)^2 on X>=r and minimizing (v+s^2)/(r+s)^2 over s>=0, whose minimizer is s=v/r. Thus P(X>=r)<=v/(v+r^2), and similarly for -X. Radius sqrt(39v) bounds each tail by 1/40, hence also total miscoverage by 1/20. Radius sqrt(19v) is sufficient for a single 95% one-sided bound, but does not give a two-sided 95% interval merely by using it on both sides. These classical inequalities and distinctions are discussed in the primary research paper [Ion, Klaassen and van den Heuvel (2022)](https://arxiv.org/abs/2208.08813); the direct proofs above establish the claims needed here.

The narrower Chebyshev95 radius alone guarantees each tail only by Cantelli's 1/21 bound, which is larger than the frozen per-tail 0.035 criterion. To prove that criterion as well, use radius sqrt((193/7)*v): Cantelli gives each tail <=7/200=0.035, while Chebyshev gives total miscoverage <=7/193, hence coverage >=186/193 (approximately 96.3731%). This combination is stronger than merely adding the two 0.035 tail bounds. It is a known-law oracle calculation, not a change to the existing frozen candidate.

Bounds are conservative inequalities, not claims that actual error equals the bound. All intervals are centered at T-beta: both P1 biases are negative, so the correction moves their centers upward. An asymmetric interval can allocate different Cantelli tail budgets, but their sum must not exceed the desired total-error budget if the union bound is the sole two-sided proof.

## Independently reproduced widths

Values below are untruncated full widths. Fit decisions were checked by exact rational squared-width comparisons against (1/50)^2 for raw and (1/5)^2 for win. Independently bracketed every square root using integer square root at 10^-18 resolution; displayed values are readability approximations, not inward-rounded implementation endpoints.

| Target | n | Chebyshev95 | Cantelli .025 each | Combined .035 each / >=96.37% coverage | Gaussian 1.96 comparison only |
|---|---:|---:|---:|---:|---:|
| raw | 64 | 0.014913409599 | 0.020825443151 | 0.017510219194 | 0.006536089937 |
| raw | 128 | 0.010543322790 | 0.014722949030 | 0.012379187459 | 0.004620814947 |
| win | 64 | 0.436012308552 | 0.608858053866 | 0.511933306966 | 0.191090819546 |
| win | 128 | 0.308659231322 | 0.431019159790 | 0.362404771417 | 0.135275872531 |

Thus a rigorously valid raw P1 oracle interval meets the frozen 0.02 width at both n values. The combined Chebyshev/Cantelli version also proves the required per-tail cap. The equal-tail .025 Cantelli version narrowly misses raw n=64 but fits n=128. All listed rigorous moment-bound win intervals exceed the 0.2 width cap; the Gaussian comparison fits it at both n values but has no 95% coverage proof from these moments alone.

For example, the combined raw n=64 full width is certified inside [0.017510219193837723,0.017510219193837724]; raw n=128 inside [0.012379187459446388,0.012379187459446389]. Chebyshev95 win n=128 is inside [0.308659231321699018,0.308659231321699019]. Exact bias corrections are those in the moment file: approximately +0.0000513561932771/+0.0000258603512375 for raw n=64/128 and +0.00128390483193/+0.000646508780937 for wins.

Clipping a win interval to [0,1] preserves coverage but can reduce displayed width near boundaries. Therefore an untruncated-width failure is not a universal displayed-width floor. Here theta=1/4 is inside (0.2,0.8): any clipped interval of width <=0.2 coming from one of these intervals with original width >0.2 must touch 0 or1 and cannot cover theta. For these particular constructions, precision and coverage events are disjoint, so the frozen high-precision/high-coverage requirements cannot both hold. This does **not** prove that every other rigorous method for the known P1 law must fail the 0.2 width; exact distributional calculations may be sharper than moment inequalities.

## Scope conclusion

The exact variance and bias are enough to build conservative finite-sample P1 oracle intervals. They are not enough to justify replacing the radius by 1.96*sqrt(v): approximately Gaussian shape and appropriate tail accuracy require separate proof or distributional evaluation. The same warning applies even more strongly to replacing v by an empirical estimate without uncertainty accounting.

This result provides a valid mathematical baseline for raw P1, not qualification of the failed calendar estimator or of all 46 formal cells. The 95% path-level interval guarantee is distinct from the separate simultaneous Monte Carlo confidence bounds on performance rates; it does not automatically pass a finite replicate gate or authorize use of the reserved confirmation. Neither paired returns nor other profiles were certified here. No claim transfers to unknown real-market laws without justified assumptions and a valid estimation procedure. The failed development record and unopened confirmation seal remain unchanged.

### Explicit pointwise and uncorrected-center alternatives

The supplied bias and variance are authenticated only at the specified frozen P1 law and its specified truth. They may change with the unknown parameter in any enlarged model; shifted raw returns and thresholded win probabilities are especially different constructions. A plug-in of these constants is therefore not a proved uniform confidence procedure over an unknown-parameter family. The oracle already knows its target. Raw narrowness here is no qualification of the frozen study or its estimator.

Bias correction is not implicit or free. If the center must remain the uncorrected raw sample mean T, the known-law second moment around truth is E[(T-theta)^2]=v+beta^2. Direct Markov gives the alternative [T-sqrt(20*(v+beta^2)), T+sqrt(20*(v+beta^2))] with coverage at least 95%. This simple proof bounds each individual tail only by 0.05, so it does not establish the frozen 0.035 per-tail caps. It still depends on knowing the exact bias and variance through their second-moment sum.

Independently certified uncorrected raw full widths: n=64 lies in [0.014920481980933970,0.014920481980933971]; n=128 lies in [0.010545859664878981,0.010545859664878982]. Both fit the raw 0.02 cap by exact squared comparison, without removing bias from the center. This remains an illustrative pointwise known-law bound, not a passed frozen gate.
