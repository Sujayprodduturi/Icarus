# Finite-sample calendar ratio bound: mathematical assessment

Date: 2026-10-02. Scope: deterministic mathematical consultation about the frozen artificial laws in the [stress protocol](../plans/2026-10-01-signal-calendar-stress-confirmation-protocol.md) and `scripts/research/signal_calendar_laws.py`. This document introduces no adopted estimator, practical minimum-data floor, new draw, confirmation run, threshold amendment or real-data authorization. The exposed development failure remains a failure; this assessment does not repair or reinterpret its evidence.

## What this means in plain English

There is a way to give a mathematically conservative uncertainty range for these particular invented markets. We group calendar dates so that dates in the same group use separate random inputs, then allow the different groups to depend on one another. We also keep quiet dates and account for the fact that the number of trades is random.

However, the resulting win-rate ranges cannot be both narrow enough and correct at the history lengths already specified. This follows from the formula without generating another history. Building and screening this bound as a replacement under the same requirements would therefore add work without a route to qualification. The useful next question is whether the calendar length and complete trade footprints can support a better justified design, rather than whether another run of the same short-history test happens to look better.

## Calendar score and population target

For a fixed target, let C_t be the number of selected completed trades entering calendar date t, and A_t their total target value. For win probability, A_t is the number of strictly positive raw outcomes. For raw or paired return, A_t is the sum of the corresponding trade returns. Retain every core date, including C_t=A_t=0.

Write A=sum_t A_t, C=sum_t C_t, lambda=E[C_t]>0, and theta=E[A_t]/lambda. This is the long-run selected-trade target. It is not E[A_t/C_t] and is not the expected finite-history sample ratio.

For a candidate value v define W_t(v)=A_t-v*C_t. At the true theta, E[W_t(theta)]=0. Counts and outcomes may depend on one another; no independence between A_t and C_t is needed. The whole date vector, including both symbols and their common shocks, is the unit of analysis.

## Exactly which dates can be independent

Let W=max(m,1), with m the volatility memory and H the hold length. In the explicit frozen formula, W_t(v) depends only on innovations indexed from t-W through t+H-1, inclusive. The previous sign and past volatility indicators are in the left part; the forward-sign average ends at t+H-1; gate, jump and per-symbol signs are indexed at t.

The complete recorded footprint is larger: t-W through t+H. The final date is the exit/recognition coordinate, but its innovation is not an input to this particular outcome formula. This distinction is licensed by the frozen law formula, not by a generic claim that exit dates can be discarded.

Consequently K=W+H residue classes of dates give jointly independent daily scores within each class: their actual innovation sets are disjoint, and the underlying innovation families are IID across dates. Classes can depend on one another. Using only the complete declared footprint gives the conservative alternative K=W+H+1. Using the smaller K for a different outcome law would require a new dependency proof.

| Profiles | W | H | K from actual random inputs |
|---|---:|---:|---:|
| P1, P2, P5, P6, L1 | 1 | 1 | 2 |
| P3 | 1 | 8 | 9 |
| P4 | 4 | 1 | 5 |
| P7 | 8 | 32 | 40 |

The effect controls inherit P1's geometry. No independence between stocks is asserted.

## Concentration proof and inversion

For each candidate v, obtain the exact reachable daily support bounds L(v)=min(a-v*c) and U(v)=max(a-v*c), and R(v)=U(v)-L(v). Include the zero-count atom whenever the law permits it. These bounds come from the specified law support, not from observed extrema.

Let class k contain n_k dates and Q_k(v)=n_k*R(v)^2. Within-class Hoeffding bounds, followed by Holder's inequality across classes with positive weights rho_k summing to one, give

```text
E exp(s * sum_t (W_t(v)-E W_t(v)))
    <= exp((s^2/8) * sum_k Q_k(v)/rho_k).
```

Choosing rho_k proportional to sqrt(Q_k) yields V(v)=R(v)^2*B, where B=(sum_k sqrt(n_k))^2 <= K*n. Empty classes can be omitted. If R(v)=0, the score is deterministic and should be handled directly. Chernoff optimization and the two tails then give, at the true target,

```text
P(abs(A-theta*C) >= R(theta)*sqrt(B*log(2/alpha)/2)) <= alpha.
```

The simpler conservative choice B=K*n is the proper-cover form supported by [Janson's primary preprint, Theorem 2.1](https://api.newton.ac.uk/website/v0/events/preprints/NI02024). The optimized disjoint-class B above is an explicit Holder derivation here; it is not a claim that the cited theorem states that exact refinement. This is a finite-sample lower coverage guarantee, not exact nominal coverage.

Invert the score test over a target domain fixed before seeing outcomes:

```text
I = {v in domain : abs(A-v*C) <= R(v)*sqrt(B*log(2/alpha)/2)}.
```

At the true theta, membership has probability at least 1-alpha. No continuum multiple-testing adjustment is needed for this coverage argument: it concerns membership of one fixed true parameter. R(v) is a difference of extrema of affine support functions, so exact inversion is piecewise. Taking the hull of accepted components preserves coverage and can only widen the result. Substituting the known oracle truth into R and then reporting a data estimator would not be a valid implementation of this inversion.

For a simpler bound, if every trade value lies in [l,u] and the target domain is [l,u], then C_t<=2 implies R(v)<=2*(u-l). For C>0 this gives a symmetric interval around A/C with half-width 2*(u-l)*sqrt(B*log(2/alpha)/2)/C. Exact score support can improve this conservative envelope.

## Random denominator and refusals

Do not condition on observed entry counts and treat the resulting trades as an independent fixed cohort. The concentration event applies to the calendar score with the count inside it. Division by the observed C occurs only when converting that event into a ratio interval.

If C=0, A/C is undefined. A wrapper can refuse, or a separately specified mathematical procedure can return the entire target domain. It cannot invent a zero mean, a zero-width range or conditional coverage for selected survivors. For a wrapper whose only additional refusal is C=0, the unconditional probability of emitting and covering is at least 1-alpha-P(C=0); this does not establish conditional coverage at least 1-alpha. Dense frozen laws have C_t>=1. For L1, P(C=0)=(49/50)^n. Other implementation refusals must also remain visible.

## A deterministic precision obstruction for win probability

For every P1-P7 and L1 win law, R(v)=2 throughout v in [0,1]. When C_t=2, both A_t=0 and A_t=2 have positive probability under the finite atom support. Their scores are -2v and 2-2v. Scores for C_t=0 or 1 lie between these extremes. This is a support statement, not a simulation estimate.

For alpha=1/20, the untruncated ratio interval therefore has full width 4*sqrt(B*log(40)/2)/C. Even the maximum possible C=2n gives the lower bound sqrt(2*log(40))*sum_k sqrt(n_k)/n. At n=128, the actual-input coloring gives:

| Profiles | B | Best possible untruncated full width |
|---|---:|---:|
| P1, P2, P5, P6, L1 | 256 | 0.3395253789 |
| P3 | 1151.7585488933 | 0.7201666107 |
| P4 | 639.9411708156 | 0.5368120867 |
| P7 | 5101.6200269505 | 1.5156757925 |

The frozen win requirement is full width <=0.2. These values already assume the largest possible observed trade count; smaller counts make the range wider. The n=64 geometries are also wider. The conservative complete-footprint coloring cannot improve these bounds.

Clipping to [0,1] can shrink a displayed width near a boundary, so the untruncated width bound must not be asserted for every clipped interval. Nevertheless every frozen win truth lies strictly between 0.2 and 0.8. If an original interval wider than 0.2 clips to width <=0.2, the clipped interval must touch 0 or 1 and cannot contain any of those truths. Thus being precision-ready and covering the truth is impossible for this bound at these lengths, even under that clipping variant. The existing protocol requires unclipped endpoints in any case.

The frozen point requirements precision >=0.90 and joint coverage >=0.93 would require overlap of these events at least 0.83, by the elementary union bound. Their overlap here is empty. Both requirements cannot hold. This is a method-specific obstruction under the specified lengths and widths, not a universal minimum-data floor or a proof that every other finite-sample method must fail.

## Relation to the existing bounded calculator

The existing bounded research helper already uses independently partitioned classes with arbitrary dependence between classes and the active-class penalty on its support sum. Its proper-cover route uses log(2/alpha), not a union penalty log(2K/alpha). The Gaussian-persistence transfer route is a different argument.

That helper's declared fixed-cohort means and weights do not by themselves certify this population ratio with random entry counts. The calendar score, all quiet dates, fixed dependency proof, true support bounds and denominator-safe inversion are additional work. Passing realized trade counts as if they were fixed independent weights would hide the selection problem. Neither helper authenticates market support bounds or a real-data independence declaration.

## Numerical implementation limits and recommendation

A future implementation would need exact rational support and class-count arithmetic, preflight resource limits, outward logarithm/square-root bounds, and outward endpoint inversion. The optimized B contains square roots of class sizes; rounding it downward would weaken the guarantee. Conservative B=K*n avoids those extra radicals at the cost of wider ranges. Narrow intermediate enclosures must never become a falsely narrow reported interval. Zero counts, degenerate support, nonfinite inputs and unsupported laws need explicit behavior.

No new fallback implementation or sampled screen is recommended under the unchanged frozen lengths and requirements: the win obstruction already rules out qualification. Preserve the observed failed method, do not open confirmation and do not relax the requirements to make this bound pass. The next useful design work is a deterministic assessment of history length, dependence span, complete footprint/resource costs and the limits of the current calendar geometry. A different concentration method or resource redesign would need its own mathematical justification and reviewed proposal. None of this establishes real-market eligibility or an accepted data floor.

Independent mathematical cross-check: practical_math agreed on the actual-input coloring, the score-range result, and the precision/coverage obstruction, including the clipping qualification. The primary orchestrator retains responsibility for final acceptance and project state records.
