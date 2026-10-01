# Dependence-aware bounded uncertainty: next research proposal
Date: 2026-10-01. Status: concrete proposal for independent review and operator approval; no implementation or stochastic evaluation authorized by this document.

## Purpose in the roadmap
The signal simulator records trades and skips. The completed bounded helper measures uncertainty when its groups are independent. The next narrow step is to handle an explicitly known pattern of dependence without counting related observations as independent evidence. Task 3a, product inference and real-strategy judgment remain incomplete.

## Options and recommendation
1. Merge every connected set of dependent groups into one independent unit. Simple and valid when distinct components are jointly independent, but a chain of neighboring influences merges the entire history and normally leaves insufficient evidence.
2. Partition groups into fixed classes, each containing mutually independent group outcomes; allow arbitrary dependence across classes. Use the bounded-sum concentration penalty below. Recommended as the smallest conservative extension of the existing helper.
3. Estimate correlations or a mixing rate from observed outcomes and adopt a bootstrap/HAC/Markov bound. This would require a different reviewed model and validation experiment; a fitted correlation does not certify the assumptions. Do not add it in this unit.

## Required assumptions and source contract
Keep the synthetic-only immutable source/member/count/support/provenance checks. Add a fixed disjoint partition of every group into exactly one nonempty class. Class IDs and group IDs must be unique and exactly cover the declared cohort. Within every class, all group outcome vectors must be jointly independent, not merely pairwise uncorrelated or pairwise independent. Dependence between classes is unrestricted. A group vector includes the entire raw/benchmark paired cohort, so deterministic win/excess transforms preserve the same contract.

The class partition, individual hard support, cohort, metric, alpha and requested precision are supplied before outcomes are examined. Unknown joint-independence premises, outcome-dependent partitions, unsupported source provenance or real-data scope refuse. Label the premise explicitly as fixture-declared within-class joint independence; do not relabel the original SourceContract as globally independent. Existing independent API behavior remains unchanged.

For a fixture X_t=(U_t+U_(t-1))/2 with independent binary shocks U, odd and even t form two classes: every same-class outcome uses disjoint shocks. Adjacent classes may share shocks. Arbitrary shared market factors, long-lived regimes or overlapping strategy history can invalidate this construction. In a future real cohort, calendar spacing, a non-significant correlation test, a maximum holding period or a stop-loss does not establish these premises. This research unit provides no market independence certifier.

Pairwise-independent triples U,V,U xor V illustrate why a pairwise declaration is inadequate. Tests must distinguish the missing joint-independence contract; the helper cannot infer an undisclosed false premise from one sample.

## Formula and proof
Use original trade weights w_g=n_g/N, group means Z_g and metric support [a_g,b_g]. Let d_g=w_g*(b_g-a_g), Q=sum(d_g^2), A=sum(w_g*a_g), B=sum(w_g*b_g). Remove only structurally singleton groups from the random sum; their known weighted contributions stay in the mean and A/B. K is the number of classes containing at least one non-singleton metric support. It depends on declared metric support, never realized sample variance.

For each active class c, S_c=sum(g in c) w_g*(Z_g-E Z_g) and Q_c=sum(g in c) d_g^2. Bounded independent-sum Hoeffding gives E exp(s*S_c) <= exp(s^2*Q_c/8). Generalized Holder with equal exponents K gives

E exp(lambda*sum S_c) <= product_c [E exp(K*lambda*S_c)]^(1/K) <= exp(K*lambda^2*Q/8).

Chernoff optimization and the two-tail union bound imply P(abs(mean-theta)>=h) <= 2*exp(-2*h^2/(K*Q)), so h=sqrt(K*Q*ln(2/alpha)/2). K=1 recovers the existing independent formula. All singleton supports give the existing exact structural result; no observed-constant shortcut is permitted.

This is a conservative integer-cover bound, not an optimal/fractional coloring or a universal time-series theorem. [Janson, Theorem 2.1 and proper-cover definitions](https://api.newton.ac.uk/website/v0/events/preprints/NI02024) give the partly-dependent bounded-sum framework; the proof above spells out the particular disjoint K-class specialization. [Hoeffding](https://www.cs.rpi.edu/academics/courses/spring06/random/hoefding.pdf) supplies the independent bounded-sum ingredient. Primary sources checked 2026-10-01. No stationarity or equal expectations are required: the target is the fixed-cohort weighted average of expectations, not a promise about a future market regime.

## Precision, arithmetic and refusal
Use existing exact Fraction weights/means/support and conservative local Decimal endpoint arithmetic. Compute exact K*Q before the upper logarithm/square-root bound. Report K, Q, K*Q, original counts/weights, untrimmed/trimmed interval and assumption provenance. Intersect with [A,B] only after computing the untrimmed radius. Precision is W=2*h/(B-A); insufficient precision has diagnostics but no interval endpoints. The guarantee is unconditional under declared premises, not nominal conditional-on-emission coverage.

Report (B-A)^2/(K*Q) as a concentration quantity for this theorem, explicitly not an empirically measured number of independent market periods. Preserve separate weight concentration 1/sum(w_g^2). Empty/partial/duplicate class mapping, invalid alpha/precision, malformed/nonfinite/out-of-support input, missing paired benchmark, unknown support or assumptions, numerical collapse and resource excess all refuse. Existing research scratch caps remain technical caps, not product thresholds.

Primary deterministic arithmetic (alpha=.05, 192 equally weighted unit-range groups):

| Fixed classes K | Normalized untrimmed width |
|---:|---:|
|1|0.196025069|
|2|0.277221311|
|4|0.392050138|
|192|2.716203031|

An illustrative quarter-range width needs at least119 equal groups at K=1,237 at K=2 or473 at K=4. These are formula examples, not accepted floors. Assigning each possibly dependent group its own class is valid without independence between groups, but K=N gives a width exceeding the full support and therefore insufficient evidence for any allowed precision <=1. More trades inside the same groups do not erase dependence.

## Proposed implementation and deterministic acceptance
After operator approval, extend only the isolated research helper (or one small sibling sharing its validated arithmetic) and deterministic tests. Do not add graph optimization, correlation estimation, product adapters or dependencies. Exact API/refactoring choice is implementation planning; do not duplicate the arithmetic/validation core or weaken globally-independent contracts to reuse it.

Acceptance must include K=1 equality with existing outputs; hand/oracle K*Q calculations with unequal counts/support; metric-specific singleton handling; original trade weights and complete raw/win/excess pairing; permutation/class-label invariance; larger declared K never narrows the bound for unchanged active Q; support-only precision; constant observations retain radius; invalid/unknown/outcome-selected contracts refuse; conservative endpoints under numerical extremes; no product/frozen-path changes.

Enumerate every latent-shock outcome for eight X_t=(U_t+U_(t-1))/2 observations (nine binary shocks,512 outcomes) at predeclared p=.1,.5,.9. Verify independence by disjoint latent footprints within each class and calculate exact outcome probabilities. Raw mean target is p; strict raw-positive win target is 1-(1-p)^2. Evaluate each metric against its own target with no benchmark unless a whole paired bounded benchmark construction is separately specified. Count generated/emitted/refused cases and exact coverage; no RNG, hidden redraw or favorable-emission denominator. Use supplied precision=1 for this small coverage fixture; alpha=.05 and K=2 imply untrimmed width about1.358>1, so the eight-observation fixture must report insufficiency rather than manufacture emitted coverage. To exercise nontrivial emitted dependent coverage, predeclare alpha=.5 and precision=1 for the same small fixture (width about.833), label its50% level explicitly; retain the95% insufficiency witness. Larger95% arithmetic fixtures may test formula/precision but must not masquerade as exhaustively enumerated coverage.

Independent numerical plus engineering/governance review, primary reproduced arithmetic, existing simulator/accounting/portfolio regressions, strict mypy/Ruff and actual-defect mutations apply. No new Monte Carlo screen, real strategy trial, reserved stream or lockbox use is proposed. No new production floor, gate or inference flag is changed.

## What stays unresolved
The existing serial failure profile uses recursive factors in scripts/signal_calibration.py:899-905. Its influence does not stop at a fixed finite lag, so odd/even partitioning cannot be asserted independent. Cell28 remains unresolved; a K-class fixture is not its repair. Unbounded Gaussian benchmark differences and rare outcomes with unsupported hard ranges remain ineligible. Original rejected methods/45 profiles are not reclassified. M1-M4 and Windows official-platform blockers stay open. Later work requires a separately justified dependence/tail model or honest refusal, followed by reviewed validation and the later real-data prerequisites.

## Operator-facing explanation
If many trades win because they shared one favorable market episode, they provide less evidence than the same number of unrelated trades. The proposed extension accepts a justified description of those connections and widens the uncertainty range accordingly. Its first tests use artificial cases where the connections are known exactly. It will still say cannot judge when those connections are unknown. This adds one piece needed to judge strategies; it does not yet establish that any real strategy is good.

## Review record
Two independent medium-effort reviewers approved this proposal for operator review with no mathematical or governance blocker. The numerical reviewer reproduced all four192-group widths, both eight-group widths and119/237/473 minimum equal-unit counts; it checked the self-contained Holder argument and metric-specific singleton rule. The governance reviewer verified scope, paired cohort, fixed partitions, refusal/precision separation and explicitly different coverage-fixture confidence levels. Reviewers' direct author-PDF retrieval timed out; primary successfully fetched the full NewtonInstitute preprint linked above and checked proper-cover definitions and Theorem2.1, in addition to independently reproducing the arithmetic. No implementation acceptance, stochastic screen, real-data evaluation or product adoption is claimed. Protected code/config paths have no changes; unchanged test suites were not rerun for this documentation-only proposal.

Approval addendum2026-10-01: operator explicitly stated The proposal is approved (D34). The reviewed contract and deterministic acceptance scope are now authorized for implementation. Prior awaiting-approval wording is dated proposal history, not the current status.
