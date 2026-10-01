# Persistent-dependence uncertainty research proposal
Date: 2026-10-01. Status: operator D35 approved review and proceeding; narrow implementation complete at `f7c72f5`. See [build evidence](../reviews/2026-10-01-signal-persistent-uncertainty-build.md). Scope: a deterministic pure synthetic-law reference, not product adoption or real-market certification.

## Why this is next
The simulator records trades. The completed independent/fixed-class references judge bounded outcomes when exact independence premises are declared. The failing serial profile instead carries a shock forward recursively: its influence decays but never vanishes at a finite gap. This proposal explicitly accounts for the remaining dependence rather than declaring spaced observations independent.

The frozen calibration cell28 has192 trades in24 equally populated latent-factor groups, rho=.5, with each group containing8 trades. It does not have192 independent market periods. Its original coverage failure remains open. Manifest/source inspection was read-only; no reserved or research draw occurred.

## Options
1. Keep exact-independence references only. Valid but cannot describe recursive influence except by refusing.
2. Add a narrowly declared stationary Gaussian AR(1) reference with an explicit probability-error allowance for approximate independence. Recommended: it matches the mathematical structure of the existing synthetic serial example, permits hand/oracle checks and remains honest about precision/model uncertainty.
3. Fit a dependence rate to market observations and use it as a certified bound, or retune bootstrap/HAC parameters against exposed results. Reject for this unit: observed correlation does not establish the required law or tail bounds. A later empirical model/stress route requires its own pre-registration and review.

## Trusted mathematical source contract
The latent law is F_0~N(0,1), F_t=rho*F_(t-1)+sqrt(1-rho^2)*epsilon_t with independent standard-normal innovations and trusted |rho|<=r<1. The stationary start, innovation law and persistence upper bound are explicit fixture premises, not estimated facts. Unknown, fitted/observed, nonstationary, unsupported or outcome-selected declarations refuse.

Every source group contains all its predeclared trades sharing one latent index t_g. Different groups cannot use the same latent index. Its whole raw/benchmark output vector is a fixed measurable function of F_(t_g) and local-vector noise; local-noise vectors are mutually independent across groups and independent of the whole factor process. Within-group noise may be dependent. Additional shared factors, dependence on factor history/future states, outcome-dependent occupancy or selection invalidate this one-factor transfer. Product-reference group marginals must be the actual group marginals; otherwise expectation preservation would require an additional bias term, outside this proposal.

A typed immutable group-to-latent-index mapping carries the latent-axis identity/provenance. Calendar entry-session gaps and occupied-group ranks are not latent-factor gaps. Preserve skipped latent indices. Complete fixed class partitions cover every group once; classes need not be independent of each other. The caller supplies the partition before outcomes (modulo10 is an illustration, not a tuned universal choice); no optimization against outcomes or favorable intervals.

Retain original source/member/coordinate/count/provenance/individual-support checks. Original trade weights n_g/N and whole paired benchmark cohorts remain intact. Raw/win/excess use their own declared supports. Exact singleton metric groups retain known weighted contributions and disappear only from the random class law; compute active-class gaps after excluding such groups. Empty random classes contribute zero error/radius. All-known output still requires a valid model and complete partition.

## Classwise dependence allowance
For one active class with sorted latent indices t_1<...<t_m, gaps d_i=t_i-t_(i-1)>0, let P_c be its actual latent-vector law and P_c^product the product of its own stationary marginals. Gaussian conditional densities and the Markov factorization give

KL(P_c || P_c^product) = -0.5*sum_i ln(1-rho^(2*d_i)).

Replacing |rho| by the trusted upper bound r enlarges this quantity. Total variation uses the event convention TV(P,Q)=sup_E abs(P(E)-Q(E)). Pinsker gives a conservative class allowance

delta_c=min(1,0.5*sqrt(sum_i -ln(1-r^(2*d_i)))).

A class with one random group has delta_c=0. Exactly r=0 has delta_c=0; tiny positive persistence must not become exact independence through underflow. Adding independent local noise and applying the fixed group-output map cannot increase total variation, so the same bound applies to the full observed group vectors. This compares distributions with matching group marginals and therefore matching weighted expectations.

For proof sources, [Bartlett notes, Pinsker theorem (PDF page15)](https://www.stat.berkeley.edu/~bartlett/courses/2014fall-cs294stat260/lectures/bandit-lower-bound-notes.pdf) define event-distance TV and its KL/Pinsker inequality; [Guntuboyina notes, pages7-9](https://www.stat.berkeley.edu/~aditya/resources/STAT212aSEP11Lecture3.pdf) provide a sharp-constant proof and data-processing framework. [Lockhart's Gaussian AR notes](https://www.sfu.ca/~lockhart/richard/804/99_3/lectures/07/web.html) describe stationary conditional Gaussian/Markov structure. Primary sources checked2026-10-01. The particular classwise KL identity follows from the explicit conditional-density calculation above; it is not a claim inferred from a sample.

## Overall mean interval and error budget
For original weights w_g=n_g/N and metric supports[a_g,b_g], let Q_c=sum(g in c)[w_g*(b_g-a_g)]^2. For K active classes, D=sum_c delta_c and requested error alpha, refuse if D>=alpha or the residual cannot be enclosed positively. Predeclared equal allocation alpha_c=(alpha-D)/K gives

h_c=sqrt(Q_c*ln(2K/(alpha-D))/2), h=sum_c h_c.

Under the product reference, Hoeffding bounds the class weighted-sum error by alpha_c. Event transfer to the actual class law adds delta_c. A union bound and triangle inequality give actual full-cohort mean coverage at least1-alpha for [mean-h,mean+h], with no cross-class independence requirement. The full target is the original weighted average of group expectations, not a subsample or a promise about a future regime.

Do NOT merely substitute alpha-D into the existing D34 KQ/Holder formula. Total variation controls event probabilities here; it does not supply the exact independent moment bound needed for that shortcut. Even when delta=0, this classwise union construction can be looser than D34. K1/r0 must recover the existing independent result; no claim of universal equality between these methods.

Precision uses the untrimmed full width2h/(B-A), where A/B are original weighted total supports. Wider-than-requested evidence yields no interval endpoints. Original weights, Q/classQ, latent indices/gaps, class delta upper bounds, total error allowance, residual lower budget, class radii and untrimmed/support-intersected endpoints are explicit research diagnostics. No observed variance/range controls the hard bounds or precision. No conditional-on-emission nominal coverage claim.

## Conservative arithmetic and failure behavior
Use exact rational inputs/weights/gaps/r^(2d) and exact1-r^(2d) before conservative log conversion. Enclose class logarithmic sums, delta/radii and total h upward; residual alpha-D and support width downward; final endpoints outward. Refuse numerical collapse, overflow/underflow, unresolved residual, invalid alpha/precision, model/axis/partition mismatch, missing benchmark pairing, support violation or technical-cap excess. Guard power resource growth before allocation; scratch caps are technical implementation limits, not market floors. No silent zero persistence or zero uncertainty for positive non-singleton terms.

## Independently reproduced formula examples
At95% confidence, unit-width support, equal trade weights and fixed modulo10 partition:

| Latent groups | Trades | Persistence upper bound | Total dependence allowance | Normalized full width / result |
|---:|---:|---:|---:|---|
|24|192 (8/group)|.5|.005691824721|2.245471627255: insufficient for precision<=1|
|192|192 (1/group)|.5|.020829557400|.824724309740: meets an illustrative precision1, not .25|
|192|192 (1/group)|.6|.128972277336|error budget exhausted; refuse|

The24-group geometry is cell28's predeclared shape, not a new empirical result. The192-group geometry and .6 stress are hypothetical formula illustrations; .6 is not a frozen manifest parameter. This partition does not rescue cell28, meet a quarter-range request or establish an accepted floor. Primary reproduced these values with80-digit Decimal from exact rational persistence/gaps; independent reviewer reproduced them separately. Scratch evidence: var/verification/2026-10-01/persistent-dependence-design/primary-formula-check.json. No data samples were generated or evaluated.

## Smallest proposed build and deterministic acceptance
Build only a pure synthetic-model geometry/precision calculator and deterministic tests, sharing existing validated cohort and numerical arithmetic where correct. Preserve original independent and D34 APIs; no fake exact-independence contract, source adapter, graph optimization, RNG, new dependency or product imports from research. Exact module/API choice belongs to scoped implementation planning after approval; no duplicate aggregation/endpoint core.

Tests must cover stationary-model/local-map declarations, unknown/fitted persistence and model assumptions, duplicate/wrong latent index/axis, preserving missing gaps, complete class mapping even known supports, unequal trade weights/support, original paired cohort, metric-specific singleton removal, classwise union/radius arithmetic, exhausted/near-zero budgets, numerical extremes/hostile Decimal contexts and outcome-independent precision. Increasing trusted persistence at unchanged geometry cannot narrow the bound. Prove that source entry-session spacing cannot substitute for latent-factor coordinates.

Independent numerical oracles compare class KL to small Gaussian covariance determinants (including irregular gaps), and exact rational logarithm enclosures to conservative allowances/radii/endpoints. Hand fixtures must reproduce r0/K1 independent behavior, the three table entries, positive-persistence underflow refusals and declared95% insufficiency. Do not claim exact Gaussian coverage enumeration: Gaussian outcomes form a continuous infinite space. Any optional finite discrete transfer-proof fixture must state its different law and verify its own TV/marginals exactly; it is not an AR Gaussian coverage result. No stochastic screen is proposed.

Run relevant existing simulator/accounting/portfolio/research regressions, mypy/Ruff and independent numerical plus simplicity/engineering review. Any actual discovered bug gets its required post-commit mutation/restoration check. Keep product/frozen paths unchanged and durable state/handover evidence current.

## Source compatibility, real-data eligibility and remaining work
Read-only inspection of scripts/signal_calibration.py:899-905 confirms the intended stationary Gaussian recursion for the serial family. Fresh trade latents/amplitudes form local noise; intended raw support is[-.015,.015], win[0,1]. Gaussian benchmark differences remain unbounded. This structural comparison does not certify finite-precision PCG/normal draws and rounded recursion as the exact continuous law. No wrapper imports this generator or reclassifies its saved coverage counts.

| Input/evidence | Eligibility under this proposal |
|---|---|
|Explicit pure stationary Gaussian model with fixed local maps and externally justified finite outcome bounds|Conditional mathematical reference only|
|Existing finite-precision synthetic generator/saved serial samples|Not automatically certified as the exact law; original rejection remains|
|Real market history, fitted correlation, finite holding period or broker stop|Unknown premises: refuse; no independence/stationarity/tail certificate|
|Unbounded benchmark excess or raw support estimated from observed extrema|Unsupported support: refuse|

No finite historical sample alone proves these model premises. Later real-data work needs a separately predeclared model/assumption policy and stress/validation design, tail treatment, source/benchmark/cost review and trial-ledger barrier; it may only provide conditional evidence and must expose the limitations. No accepted method/floor, gate amendment, inference enablement, reserved stream, lockbox or broker/live path. M1-M4 and official Windows resource/durability blockers remain open.

## Plain-English explanation for the operator
The simulator can take many trades during one favorable market period. That does not make each trade separate evidence. The completed calculators handle patterns where independence can be justified exactly. This next reference would let influence fade gradually and explicitly charge for the dependence that remains. If that charge is too large, or the assumed market model is unknown, the result is cannot judge yet. First tests check the mathematics using a fully specified artificial model; they do not claim the real market follows that model. Building this would complete another narrow mathematical reference, not finish real-strategy judging.

## Review and next action
Independent medium-effort mathematical and governance/engineering reviewers approved this proposal for operator presentation on2026-10-01, with no blocker. The primary independently reproduced the table and checked the cited primary sources; the source-page label was corrected after review. Approval of the proposed implementation is still pending. Keep evaluator target expectations separate from calculator inputs, and declare each local output map jointly with its benchmark. No code, stochastic experiment or product configuration changed in this proposal session.
