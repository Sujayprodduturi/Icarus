# Extreme-return uncertainty research proposal
Date: 2026-10-01. Status: concrete next design; implementation awaits approval. Scope: pure deterministic known-second-moment reference for independent whole groups, not product adoption or real-market certification.

## Purpose and current position
The signal simulator takes every eligible signal and records the trade or explicit skip. The uncertainty layer must judge how much evidence those outcomes provide. The completed bounded and persistent-dependence references require finite outcome limits. Benchmark excess can be unbounded, and a finite historical maximum cannot supply a genuine limit. This proposal adds a separate mathematical reference for original mean returns without deleting, clipping or reweighting extreme trades.

It does not fix the previously rejected methods or certify their saved samples. It does not combine tails with persistent dependence yet. That combination, real-data eligibility and an accepted product method remain later reviewed work. The simulator is built; trustworthy real-strategy judging remains incomplete.

## Approaches considered
1. **Known-second-moment original-mean reference (recommended).** A justified upper bound on the average squared distance from a fixed center limits uncertainty without requiring a maximum individual outcome. Chebyshev gives a small, auditable benchmark; precision may be poor.
2. **Predeclared clipping with an explicit original-mean bias allowance.** For centered second moment M and clip threshold T, absolute clipping bias is at most M/(4T), from (abs(x)-T)_+ <= x^2/(4T). This can be correct but adds threshold policy and transformed-target bookkeeping. Hoeffding plus this bias is not universally more informative; with only second moments its optimized clipping rate is proportional to n^(-1/4), compared with this benchmark's n^(-1/2) at fixed confidence. It is not selected for this unit.
3. **Fit tail/variance parameters from the observed results or build a robust mean estimator now.** An observed variance is not the trusted bound required here. More sophisticated robust estimators can improve confidence dependence under additional carefully declared conditions, but are outside the smallest reference and need separate review. Neither path certifies real-market assumptions automatically.

Primary sources checked2026-10-01: [Stark, Berkeley: Markov and Chebyshev inequalities](https://www.stat.berkeley.edu/~stark/SticiGui/Text/clt.htm), especially the event inequality in the Chebyshev section; [Catoni, High confidence estimates of the mean of heavy-tailed real random variables](https://arxiv.org/abs/0909.5366), abstract explaining prior-bound requirements and the limitations of the ordinary mean at high confidence. The weighted non-identically-distributed derivation below is project mathematics, not an assertion that Catoni's estimator is implemented.

## Explicit artificial-law contract
For every fixed complete source group g:
- n_g original trades, with all original member IDs and coordinates preserved; N=sum(n_g), w_g=n_g/N.
- Y_g is the average of its selected metric's original trade outcomes. The observation is y_g. Arbitrary dependence within the group is allowed.
- Fixed finite center c_g and finite nonnegative M_g with a trusted law declaration E[(Y_g-c_g)^2] <= M_g. The bound is about the entire group mean, not a cap on individual observed trades.
- A group-law identity and provenance explicitly cover its whole raw/benchmark vector, metric, center and bound. Unknown, observed/fitted, outcome-selected or incompatible declarations refuse. No true mean is provided as an estimator input.
- Whole group vectors are mutually independent by trusted fixture declaration. Different groups need not have the same distribution or mean. Entry-session spacing alone does not establish this premise.

Fixture identity, source/member/count/cohort declarations, fixed geometry, synthetic-only scope and finite observations are checked before arithmetic. Group membership and sample size cannot be selected by outcomes. Missing, duplicated, shifted or additional members refuse. A finite sample cannot authenticate these premises.

For RAW, Y_g averages original raw returns in the supplied metric units; existing simulator outcomes remain labelled net of cost before tax. This helper introduces no new cost/tax or performance claim. For SYNTHETIC_EXCESS, it averages each original paired raw-minus-benchmark outcome; every original benchmark is required. The direct moment declaration must be for that paired group-mean difference. Do not infer independence between strategy and benchmark or subtract moments. No trade-to-group moment converter is included in this unit. Any future converter must permit arbitrary within-group dependence. WIN remains on the existing bounded research path; no automatic method fallback or method selection against observed outcomes.

No fabricated finite supports or reuse of SourceContract with fake raw/benchmark limits. Reuse validated numeric/member/observation conventions and shared premise-free cohort validation only where correct. Exact module/API extraction belongs to the scoped implementation plan; avoid unnecessary restructuring of the completed bounded helper.

## Original-mean calculation and guarantee
Target mu=sum(w_g*E[Y_g]); sample mean ybar=sum(w_g*y_g), equal to the original all-trade arithmetic average. The target is the expected return for this fixed cohort law, not a forecast of an unspecified future regime.

Var(Y_g) <= E[(Y_g-c_g)^2] <= M_g. Under group independence,

V=sum(w_g^2*M_g) >= Var(ybar), h=sqrt(V/alpha).

Chebyshev gives P(abs(ybar-mu)>h) <= alpha, hence original-mean interval [ybar-h,ybar+h] has unconditional coverage at least1-alpha under the declarations. No identical-distribution or normal-shape premise is needed. Centers justify the bounds; their weighted sum is not used as the reported sample mean. Centered second-moment bounds may be conservative compared with actual variances.

The result reports original counts/weights, centers/bounds, exact V, requested alpha, radius upper enclosure, full width upper enclosure and outward endpoints when precision succeeds. Scope remains SYNTHETIC_RESEARCH_ONLY. This is a conservative benchmark, not a claim of optimal interval length.

## Precision and numerical safety
Predeclare a positive desired **absolute full interval width**, in the selected metric's original return units. No support-range normalization, observed extrema/variance, favorable-result clipping or post-result scale selection. Width=2h; compare the conservative upward width to the exact request. If too wide, return insufficiency diagnostics with no endpoints. Precision depends only on fixed geometry, moment bounds and alpha. Equality passes only when proved by conservative arithmetic. No minimum-data floor is accepted by illustrative calculations.

Use exact rational numeric conversion, trade weights and V; fresh isolated directed Decimal arithmetic for square-root enclosures and endpoints. Certify h_upper^2 >= V/alpha by exact rational comparison of the represented endpoint; correct outward if needed or refuse. Do not rely on Decimal.sqrt honoring an arbitrary directed rounding mode. Final endpoints must be no narrower than exact ybar +/- h_upper. Refuse nonfinite inputs, invalid alpha/precision, unknown/infinite/negative moments, invalid cohort, resource excess or inadequate numerical resolution. Technical scratch caps protect allocation and are not market thresholds.

If M_g=0, the law implies Y_g=c_g almost surely; an observed group mean unequal to its declared center is a contract contradiction and refuses. Individual members need not equal c_g: their values may cancel within the group. With V=0 and every group consistent, report the weighted known centers only after the full premise/cohort checks. Positive tiny V must not become zero uncertainty through numerical collapse. For M_g>0, a legitimate observation may exceed sqrt(M_g) from the center; this is not a support violation and must not be discarded. A single observation cannot establish or refute an expectation bound merely by its magnitude.

## Formula checks and exact rare-event witness
These are new hypothetical law checks, not calibration samples or parameters fitted from trading history. At95% confidence, each group declares c=0 and M=.0004 (a bound on average squared return, whose square root is2%):

| Independent groups | Trades | Half-width in return percentage points | Full width in percentage points |
|---:|---:|---:|---:|
|24|192, eight/group|1.825741858351|3.651483716701|
|192|192, one/group|.645497224368|1.290994448736|
|320|320, one/group|.5|1|

The24/192 row illustrates trade-count weighting only. The existing serial cell's groups are dependent; it is **ineligible** for this independent-moment reference and receives no new interval or repaired verdict. The1-percentage-point request is illustrative, not an approved product threshold. Equal groups under these hypothetical bounds need320 groups for that request; eight perfectly correlated trades per group do not multiply independent evidence. Increasing the actual bound widens the interval.

A separate exact artificial law has return10000 with probability1/10000 and0 otherwise. Mean=1, second moment about0=10000. In192 independent draws, probability of seeing only zeros is (9999/10000)^192 = .98098220418648. Thus a quiet sample can miss a large contribution to the true mean. This proves neither a market law nor empirical coverage; it explains why observed quietness cannot replace an externally justified bound. Both rare gains and their sign-reversed rare losses belong in deterministic fixtures.

Primary used exact rational weights/moments and80-digit Decimal for these formula checks, and enumerated a separate two-group finite law with unequal weights to verify the event bound. Locally retained scratch evidence: var/verification/2026-10-01/tail-moment-design/primary-check.json. No RNG or trading data used.

## Proposed deterministic acceptance
- Happy paths: equal/unequal original trade weights, different group laws/centers, direct paired excess, exact original mean, legitimate rare large observations, and centered second moments differing from variance.
- Refusals: real data, unknown/fitted moments or independence, outcome-selected geometry/bounds/precision, incomplete or shifted original cohorts, missing benchmark pairs, unsupported metric, infinite/negative/nonfinite bounds and observations, invalid alpha/precision and numerical/resource limits.
- Zero bounds: correct group-mean cancellation, inconsistent zero-moment group, and validation of all declarations before all-known output. Tiny positive bounds retain positive uncertainty or refuse.
- Directed arithmetic: exact squared-radius oracle, hostile ambient Decimal contexts, numerical extremes, outward endpoints, exact representable precision boundary and untrimmed full-width refusals. At fixed geometry, increasing M cannot narrow the result.
- Independent exact finite-law coverage enumeration includes unequal weights, rare positive/negative outcomes, original mean targets and boundary events. Target expectations stay in the oracle, never estimator inputs. Enumeration demonstrates specified finite examples, not every heavy-tailed law.
- Relevant current Windows simulator/accounting/portfolio/research regression, mypy/Ruff/format checks and independent numerical review. Before code commit run actual simplicity review followed by engineering code review. Discovered defects receive post-commit recurrence checks with exact byte restoration; update state/handover/evidence and push.

## Held boundaries and next sequence
1. Obtain approval for this concrete narrow design, then build/test the independent original-mean moment reference.
2. Separately review composing moment-based events with fixed/persistent dependence. Marginal-preserving event-TV can transfer an unbounded-event probability; TV alone does not bound differences in unbounded means or second moments when marginals differ. No current support-based API is automatically certified for this purpose.
3. Define a predeclared real-market model/assumption and stress/validation policy, plus source/benchmark/cost/trial-ledger guards. Moment bounds cannot be certified from a finite historical panel alone. No stop-loss, holding period or observed maximum supplies a tail certificate.

M1-M4 remain OPEN. No rejected method is adopted, no original saved serial/rare coverage count is changed. No stochastic screen, real-data strategy evaluation, accepted data floor, frozen gate/manifest amendment, official draw, lockbox, inference enablement or live/broker path. Official Windows resource/durability blockers remain separate.

## Operator explanation
We already have the simulator that records trades. We are still building the part that judges how much confidence those trades deserve. A short test may miss a rare large win or loss. This next calculator keeps every trade and allows such large outcomes, but requires a justified bound on their average squared size. A larger bound means a wider uncertainty range. Without the bound, or without justified independence between market groups, it says cannot judge yet. First we prove this using fully specified artificial examples; deciding which assumptions can be defended for real market history remains later work.

## Review status
Independent medium-effort mathematical reviewer tail_design_review and scope/governance reviewer tail_scope_review both read the final written proposal and approved it for operator presentation on2026-10-01, with no blocker. Primary independently reproduced all table rows, the exact rare-event probability and a separate weighted finite-law event check. The governance reviewer correctly noted that fixed/outcome-independent provenance remains a trusted artificial-law premise; inspecting supplied numbers cannot authenticate it. Implementation awaits approval of this concrete design. This session changes proposal/state documentation only. Per OPERATOR section5b, documentation-only changes are exempt from code simplicity/engineering review; the design itself received independent mathematical and governance reviews.
