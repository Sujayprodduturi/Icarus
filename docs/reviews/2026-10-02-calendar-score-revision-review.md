# Focused calendar-score revision review

Date: 2026-10-02. Final verdict: APPROVE the bounded deterministic proposal after the numerical correction recorded below. The initial eligibility finding is retained as review history; its design-level blocker is resolved. No delegation, sampled histories, source changes or confirmation-seal access.

The score support is correct: theta lies in [l,u], so with 0<=C_t<=2, A_t-theta*C_t lies in [2(l-theta),2(u-theta)], including the zero-count case. Its mean is zero at the ratio-of-expectations target without outcome/count independence. Read [Janson Theorem 2.1](https://api.newton.ac.uk/website/v0/events/preprints/NI02024), PDF page 3: independent sets within a proper cover suffice; sets need not be mutually independent. Substituting support width 2*Delta and cover size at most K gives the stated exp(-r^2/(2KnDelta^2)) one-sided bound. Actual artificial innovations justify K=W+H; retaining the complete exit footprint remains necessary for a future adapter.

The q=5, six-tail argument is correct and uniform over the declared bounded/proper-cover model, unlike pointwise known-truth moments. Independently obtained sum(j=0..10,5^j/j!)=7082479/48384>120; hence 6*exp(-5)<290304/7082479<1/20. It covers at most three targets for one fixed history, not strategy search or multiple new studies. The dense almost-sure C>=n contract makes mathematical width eligibility deterministic and removes arithmetic/precision selection only if the implemented numeric contract actually emits on every valid eligible path. Unknown support, sparse counts and unverified independence remain outside that claim.

## Required numerical clarification

The non-strict mathematical test n*w^2>=40KDelta^2 alone does not guarantee finite-Decimal **outward displayed** width<=w. At n=40,K=1,Delta=1,w=1,C=40,A=40/3, equality holds and exact endpoints are -1/6 and5/6. Every outward finite Decimal pair has displayed width greater than1. A path-dependent precision refusal would undermine the probability-one useful-emission premise.

Choose exact rational/algebraic endpoint output, or specify a deterministic pre-data rounding allowance and eligibility margin that covers every bounded valid input. Do not merely test observed endpoints and then claim selected-output coverage from the unconditional bound. The proposed table has strict slack, so its entries need not change. Delta=0 with a nonterminating rational target also needs exact point output or an honest rounded enclosing interval, not an impossible exact Decimal point. Input bit bounds and numerical refusal semantics must be stated as part of the trusted implementation contract.

## Independently reproduced adequacy/resource arithmetic

Required n by (raw,paired,win): P1=(320,1024/5,2000); P2=(720,784/5,2000); P3=(12960,34848/5,9000); P4=(7200,3872,5000); P5/P6=(30420,128164/5,2000); P7=(129600,87616,40000). Every table power of two is correct and minimal for the requested three metrics. E controls deliberately use P1's common n=2048 rather than their smaller two-metric minimum. Raw and paired support widths correctly combine the shared benchmark coefficients before bounding; the jump width is .33 for P5/P6.

All nine families total229376 core dates per replicate; times512 gives117440512; times32768 gives7516192768. Two hex characters/date require at least15032385536 bytes, exactly14GiB, before halo or JSON overhead. This exceeds3GiB and correctly blocks the current sampled evidence format. The effect claim is valid: each true raw/paired effect is farther than .02 from zero, so a covering interval of width<=.02 excludes zero with the correct sign.

After the numerical clarification, the isolated deterministic helper is a reasonable correctness benchmark. It must not authenticate arbitrary aggregate totals, retrofit the old law caps, revive the exposed failed candidate, consume its held confirmation, or imply market validity. Runtime/evidence feasibility and a separately preregistered sampled design remain unresolved; the proposed data lengths are method-specific, not a universal data floor.

## Reviewed correction: numerical blocker resolved at design level

The primary proposes a fixed Decimal grid d=10^-60, an exact integer-square-root rational upper radius bracket no more than d above the true radius, and outward endpoint rounding to that grid. The radius inflation contributes at most2d to full width (also valid if the bounded quantity is aggregate score radius, since C>=1); the two endpoint roundings add less than2d. Thus the displayed full width exceeds the exact width by at most4d. The revised **pre-data** eligibility w>4d and n*(w-4d)^2>=40KDelta^2 proves displayed width<=w on every valid dense path. Integer/rational grid operations must implement this proof without an unbounded-context Decimal rounding assumption.

Independently checked the revised exact rational inequality for all **25 requested metric supports across nine table families**: every proposed n still passes. Keeping a Delta=0 target as an exact Fraction point and separately labeling its outward display enclosure resolves the nonterminating-point issue. This is approval of the planned numeric contract, not a claim that it is implemented or tested yet.

With this correction incorporated, APPROVE the bounded deterministic implementation proposal. No other blocking mathematical finding remains. Subsequent implementation review should reproduce the equality counterexample as a refusal under the revised margin, verify certified radius/grid bounds and retain the selection and unknown-model limitations above.
