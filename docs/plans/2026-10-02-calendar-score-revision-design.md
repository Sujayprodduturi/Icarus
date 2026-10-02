# Revised calendar confidence design: guarantee first, usefulness second

Date: 2026-10-02. Proposed research version only. This follows the exposed calendar failure and [confidence review](../reviews/2026-10-02-confidence-mathematics-review.md); it does not amend or revive that candidate or its frozen study. Current authorization covers design/review. No new study, held-confirmation read, real-market inference or adopted data floor.

## Purpose in plain English

The simulator measures all the trades a strategy would have taken. We are building the next part: a defensible range for its underlying average return, win rate and return above a benchmark.

The previous method recycled short sections of the same history. It produced narrow ranges that missed the truth too often. This proposal instead uses a proven worst-case allowance for shared market periods and possible extreme outcomes. The number of trades stays inside the calculation rather than being treated as a fixed independent sample.

The important improvement is that we choose whether a history is long enough **before looking at its results**. A lucky history cannot qualify merely because its measured variability happens to be small. Under the declared dense artificial laws, a sufficiently long fixed history gives useful ranges on every valid path, eliminating the selection problem in which only deceptively narrow ranges are displayed.

This route has a serious limit: the conservative guarantee requires thousands to more than a hundred thousand calendar dates in these invented examples. Those are mathematical requirements for this method, not minimum-data rules for real strategies. The existing experiment cannot test these lengths within its storage cap. Therefore the recommendation is a small deterministic mathematical benchmark, not another sampled study or a claim that the practical strategy judge is solved.

## Options assessed and decision

| Route | Benefit | Unresolved issue | Decision |
|---|---|---|---|
| Rescale or studentize the failed block ranges | May give narrower practical ranges | No proved finite-history tail or selected-output guarantee; unseen rare events remain | Do not fit a correction to exposed results |
| Exact distribution of each complete artificial model | Can provide sharper model-specific answers | Joint endpoints/counts/selection calculation is expensive and does not establish unknown-market validity | Keep as a possible later oracle, not the replacement method |
| Calendar score bound with history eligibility fixed in advance | Finite-history proof; random counts, complete dependence and known rare extremes included | Conservative lengths; trusted support and independence assumptions needed | Select for an isolated deterministic benchmark; sampled feasibility remains blocked |

The selected route is deliberately a correctness reference. It must not be described as a practical market-ready solution. If its resource/data requirements are unacceptable, record insufficiency and investigate a sharper justified method; do not weaken the coverage or width standards.

## Model and original target

For each of n complete calendar dates t, C_t is the number of selected completed trades and A_t is their total target value. Quiet dates are retained. Targets are raw mean, strict-positive win probability and paired synthetic excess mean. Let C=sum C_t, A=sum A_t, and theta=E[A_t]/E[C_t]. Preserve the original trade weighting A/C, not an average of per-date or per-stock averages. The fixed law must be stationary with E[C_t]>0; all decision/completion halos are present.

Each trade target lies in a **trusted, predeclared** interval [l,u], with Delta=u-l. Win targets use [0,1]. No observed minimum/maximum, sample variance, unknown-market declaration or oracle truth may supply the support bound. There are at most two completed entries per date in the artificial laws. The dense family has 1<=C_t<=2 almost surely, so n<=C<=2n on every valid path. L1 does not satisfy the lower bound and remains an explicitly unsupported sparse limitation for useful conditional inference.

A proved partition into at most K jointly independent date classes is required. Dependence between classes and between stocks is allowed. In these frozen artificial formulas the random inputs for date t occupy [t-W,t+H-1], where W=max(1,volatility_memory); residue classes modulo K=W+H have disjoint innovation sets. The recorded exit coordinate t+H is still retained. This shorter stochastic input span is licensed by the exact law formula only, not a general permission to omit a trade's completion footprint. No declaration based merely on sample autocorrelation is accepted.

## Finite-history proof and simultaneous targets

At the true theta, W_t(theta)=A_t-theta*C_t has mean zero. Because theta lies in [l,u], its daily support is contained in [2*(l-theta),2*(u-theta)], whose width is 2*Delta. This remains true for random counts, including zero counts; outcome-count independence is unnecessary.

Janson's proper-cover Hoeffding theorem gives, for r>0,

```text
P(sum W_t(theta) >= r) <= exp(-r^2/(2*K*n*Delta^2)),
P(sum W_t(theta) <= -r) <= exp(-r^2/(2*K*n*Delta^2)).
```

Use the explicit research tail exponent q=5, fixed before any new outcomes. Set

```text
r = Delta*sqrt(2*q*K*n),
I = [A/C-r/C, A/C+r/C], for C>0.
```

Each tail is at most exp(-5). There are at most three target intervals per fixed history. Their six tails have total probability at most 6*exp(-5)<0.05. Thus all three intervals jointly cover their respective true targets with probability greater than 95%, regardless of dependence between metrics. This is a finite-history bound uniform over the declared bounded/independent-class model, not moments known only at one oracle truth. It is not simultaneous over searched strategies or repeated candidate studies.

No transcendental approximation is needed for the proof: sum(j=0..10,5^j/j!)>120 by exact rational arithmetic, hence exp(5)>120. The fixed exponent is a conservative research choice, not a risk threshold or a goal.yaml amendment. A future helper receives it explicitly in a versioned request and rejects unsupported budgets; no hidden configurable weakening.

Endpoints remain untruncated for precision reporting. If Delta=0 and the law is valid, all trade values equal the same target and the range is a point; handle directly. C=0 is not a zero mean: refuse or report the entire predeclared domain with no useful-range claim. Unsupported law/count/support/geometry, missing calendar data or nonfinite arithmetic refuse explicitly. These safety errors are not counted as successful coverage.

## Preventing narrow-range selection from creating false confidence

For dense valid paths C>=n, the full-width bound is

```text
width(I) <= 2*Delta*sqrt(2*q*K/n),
width(I)^2 <= 8*q*K*Delta^2/n = 40*K*Delta^2/n.
```

Let w be the unchanged research width request (raw/paired 1/50, win 1/5). The mathematical eligibility inequality is n*w^2 >= 40*K*Delta^2, checked for every requested metric **before path generation**. A numerical implementation needs the stronger deterministic rounding allowance below. Choose one fixed n per profile using the maximum over its metrics, not a favorable n after results. Under the dense contract and rounding-safe eligibility, all valid paths then produce arithmetic and precision-ready ranges. Consequently conditioning on arithmetic or useful emission does not select histories: both events have probability one. Each metric inherits the guarantee and the whole three-metric report has joint coverage >95%.

### Outward arithmetic must not reintroduce selection

Equality at the mathematical width limit is insufficient for finite Decimal endpoints. The focused review found the exact counterexample n=40,K=1,Delta=1,w=1,C=40,A=40/3: radius1/2 gives endpoints-1/6 and5/6, but any finite Decimal enclosure rounded outward has width greater than1. A data-dependent precision refusal at such boundaries would defeat the probability-one selection proof.

Use a predeclared fixed absolute decimal grid d=10^-60, not a magnitude-dependent significant-digit guarantee. Compute the squared radius exactly as a Fraction; certify its rational upper square-root enclosure on that grid with exact integer square-root comparisons. The radius excess is less than d. Rounding each final endpoint outward onto the same grid adds less than d per side. Thus the final full-width excess over its mathematical value is bounded by4d. Require w>4d and the **exact rational pre-data guard** n*(w-4d)^2 >=40*K*Delta^2. This guarantees the displayed width as well as the mathematical width; the counterexample is rejected before data. The table choices all have positive certified slack and remain unchanged under this stronger guard.

For Delta=0 retain the mathematical point as an exact Fraction rather than falsely claiming a nonterminating rational has a zero-width finite Decimal display. Label its separately rounded display enclosure and include its width in the same pre-data display budget. Bound rational input sizes and dimensions before integer operations; numerical or contract failures outside the specified valid fixture model refuse loudly and are not successful coverage. This contract is a proposed implementation requirement, not an already verified implementation.

When this pre-data condition fails, do not award useful eligibility merely because an observed C or unusually quiet returns yield a narrow interval. The method may report an assumption-conditional mathematical range as descriptive research output, labeled insufficient for decision use. For sparse laws, C can be small or zero and this deterministic eligibility proof fails; neither nonzero-count nor precision-selected conditional coverage is claimed. A future sparse extension requires its own selection-aware proof.

## Deterministic data-adequacy calculation

For raw synthetic laws Delta=2*abs(a)+2*abs(gamma)+2*max(v0,v1)+(max J-min J). For paired excess replace a by a-3/500 and gamma by gamma-1/100 before applying the same formula. This uses the known joint benchmark shocks, not separate empirically estimated benchmark ranges. Level shifts/cost constants cancel from the width. Win Delta=1. Source-law bounds must remain explicit.

The following n is the next power of two meeting all three rational width inequalities. Effect controls use the baseline n for a common comparison. These choices depend on support/geometry only, with no new histories. Displays are illustrative; exact squared inequalities control eligibility.

| Profile | K | Raw Delta | Paired Delta | Proposed n | Worst raw full width | Worst win full width |
|---|---:|---:|---:|---:|---:|---:|
| P1 baseline | 2 | .04 | .032 | 2,048 | .007906 | .197642 |
| P2 count selection | 2 | .06 | .028 | 2,048 | .011859 | .197642 |
| P3 overlapping holds | 9 | .12 | .088 | 16,384 | .017788 | .148232 |
| P4 volatility memory | 5 | .12 | .088 | 8,192 | .018750 | .156250 |
| P5/P6 rare opposite tails, each | 2 | .39 | .358 | 32,768 | .019270 | .049411 |
| P7 long hold/memory | 40 | .18 | .148 | 131,072 | .019887 | .110485 |
| E+/E- controls, each | 2 | .04 | .032 | 2,048 | .007906 | not requested |

The known E controls have raw theta=+/-1/25 and paired theta=delta-1/200. Any covering interval of width<=.02 must exclude zero in the correct direction for these controls; therefore their detection probability is at least their coverage probability. This statement uses the actual frozen effect laws, not a re-tuned smaller effect.

The finite source-support allowance protects against the rare atoms even on histories that do not observe one. For an unknown market with no trusted support bound, this protection is not available: refuse the guarantee. It does not justify assuming that real losses are bounded by observed past losses.

## Resource result: the current sampled route does not fit

One dense long-history replicate across these nine families contains 229,376 core dates. At the old development512 this is117,440,512 dates; at confirmation32768 it is7,516,192,768 dates. Counts are scenario comparisons, not a new selected replication plan. Original short-span families/cells remain intact and rejected; this is a different research design with different geometry.

The existing lossless path format stores two hexadecimal characters per date even before halos, result records or JSON overhead. Its confirmation core path strings alone require at least15,032,385,536 bytes (14GiB), exceeding the existing3GiB artifact cap. Therefore the current runner/format cannot honestly authorize this study. Runtime is also unproved. Do not pass these lengths through the old law/build caps or automatically enlarge budgets, reduce replicates, drop difficult profiles, thin evidence, change encoding or reuse the sealed root.

A pure confidence/adequacy helper takes declared n,K,support and validated aggregate totals and is O(1) per metric; it need not construct these billions of dates to check the proof or width. This makes deterministic implementation small and feasible, but does not authenticate totals or prove a future sampled pipeline. Existing complete-footprint checks remain mandatory for any future source adapter. Reusing the fixed-cohort bounded helper by pretending observed trade weights were fixed would be incorrect.

Any later sampled proposal needs a new versioned stream/protocol, target/replication table, full replayable evidence layout, measured full-size runtime/storage preflight and limits on this Windows PC. The old confirmation stays unopened. No alternate replication count or resource budget is chosen here. If no credible evidence-retention design fits, stop at the deterministic reference and leave practical qualification open.

## Next implementation unit and acceptance

Recommendation: implement one isolated pure calendar-score bound and exact pre-data adequacy check, with a synthetic-only trusted-model contract. Reuse outward rational/Decimal arithmetic already present where safe; avoid a new generic inference framework. It accepts no credentials, network, RNG, file IO or broker path. No sampled driver or large-history source adapter is included.

Before build, the focused independent review must verify the score support, dependency coloring, simultaneous tail proof, count/selection handling, exact table and artifact lower bound. Tests should prove finite endpoints rounded outward, point-target behavior, count violations, zero counts, incorrect/unknown assumptions, support violations, metric-budget mismatch and refusal to mark a short history useful despite high observed counts. Independent rational squared-width and finite-atom checks guard the proof; then relevant regressions/mypy/Ruff must pass. Green tests certify implementation of the declared bound, not market assumptions or Task3a completion.

This proposal is post-exposure: its method, q, simultaneous-target scope and larger history choices acknowledge the failed v1 data. It is not preregistration retroactively applied to those paths. No frozen thresholds, reserved streams, real-data authority, cost/tax/benchmark prerequisites or goal settings change. M1-M4 remain open. The operator's request to use fewer sub-agents is respected: primary analysis plus one focused final review.

## Source and primary verification

[Janson, Large deviations for sums of partly dependent random variables, Theorem2.1](https://api.newton.ac.uk/website/v0/events/preprints/NI02024), checked2026-10-02, gives each one-sided proper-cover bound. The calendar-ratio support application, q allocation, selection-proof and proposed geometries are project derivations. Primary retained exact arithmetic in `var/verification/2026-10-02/calendar-geometry/revised_design_arithmetic.py`; it imports only pure existing law declarations and generates no paths. All nine geometry inequalities and the exponential-series proof passed.

Primary separately checked84 exact daily-score support endpoint cases and reproduced the review's finite-Decimal counterexample/its rejection by the strengthened guard. The [single focused independent review](../reviews/2026-10-02-calendar-score-revision-review.md) APPROVES the bounded deterministic proposal after that correction; it independently checks all25 metric inequalities across nine families. This is design approval, not implemented-code verification or sampled authorization.
