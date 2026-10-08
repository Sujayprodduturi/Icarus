# Independent active calculator mathematical review

Date: 2026-10-08. Reviewed HEAD `8819514944ea91365e5fa14ea32f772f4bca0913`.

**Verdict: SCOPED PASS. No reproduced P0-P3 defect in the active score formula, its declared synthetic-law application, outward arithmetic, or examined scalar/optimized evaluation paths.** This is not adoption, real-data eligibility, an all-code audit, or independent re-verification of the completed experiment's raw histories. No runtime change is proposed. The old `signal_calendar_uncertainty` estimator is historical; its imported law types are not the active score calculator.

Reproduction: from `C:/ICARUS`, run `.venv/Scripts/python.exe -B var/verification/2026-10-08/calculator-review/math/independent_check.py`. Final run exited 0, measured 1.172 seconds inside the script. Output is `proof.json`, with source hashes, exact values and counts. Inputs are hand-constructed deterministic bytes and exact finite probability sums. No RNG/experimental streams, sealed records, real data, Docker, broker or cleanup was used. Only this review directory was written.

## Derivation checked against the primary theorem

Primary source checked live on 2026-10-08: [Svante Janson, Large deviations for sums of partly dependent random variables, Theorem 2.1, printed page 3](https://api.newton.ac.uk/website/v0/events/preprints/NI02024). The browser returned full text for the 13-page PDF, 1,211 extracted lines, rather than only paper metadata: theorem at extracted lines138-149; proper-cover definitions at64-93; dependency-coloring relation at100-127. The theorem bounds each tail by `exp(-2 r^2 / (chi* sum_t (b_t-a_t)^2))`. Its proper cover consists of subsets with **mutual independence within each subset**; it does not require independence between color classes. This paragraph is a paraphrase, not a quotation.

The remaining derivation is independently checked project mathematics:

1. Define the population target `theta=E[A_t]/E[C_t]`, with stationarity and `E[C_t]>0`. Then `E[W_t]=0` for `W_t=A_t-theta C_t`. For every realized count `0<=C_t<=2` and per-trade value in `[l,u]`, `W_t` belongs to `[2(l-theta),2(u-theta)]`. Thus its range width is `2 Delta`, even when counts depend on outcomes or shared state. The union-bound argument does not assume independent target metrics.
2. With a proper coloring using at most K colors, `chi*<=K`, yielding `P(sum W_t >= r)<=exp(-r^2/(2 K n Delta^2))`, likewise below. For `r=Delta sqrt(10 K n)`, each tail is at most `exp(-5)`.
3. For every C>0, the event `theta` outside `A/C +/- r/C` is exactly the corresponding score-tail event. No replacement of C by its expectation occurs. Code `signal_calendar_score.py:235` implements squared radius `10 K n Delta^2/C^2` exactly. It need not assume that `A/C` is an unbiased estimator. A fully enumerated valid P2/n2 example gives `E[A/C]=-1/400` but `E[A_t]/E[C_t]=0`; this bias does not invalidate score inversion.
4. Six tails for at most three fixed metrics have miss bound `6 exp(-5)`. The implementation uses the conservative exact certificate `E=sum_{j=0}^{10} 5^j/j!=7082479/48384>120`; hence `6/E=0.0409890378778391<0.05`. Its reported joint lower bound `1-6/E=0.9590109621221609` is conservative. Source: score lines 17-18, 146-182. Not simultaneous over many strategies, adaptive choices or every replicate.

Independent elementary check of the constant: partition dates into K classes (empty classes allowed), and let S_j be the centered score sum in class j. Holder's inequality gives `E exp(lambda sum_j S_j) <= product_j (E exp(K lambda S_j))^(1/K)`. Applying the bounded-variable Hoeffding MGF lemma within each independent class yields at most `exp(K lambda^2 sum_t(2 Delta)^2/8)=exp(K n Delta^2 lambda^2/2)`. Markov and optimization at `lambda=r/(K n Delta^2)` give `exp(-r^2/(2 K n Delta^2))`; apply the same argument to -W for the lower tail. Delta=0 is handled by the exact point case instead of dividing by zero. This checks the factor independently of the theorem transcription.

## Synthetic law, counts and support

The law's outcomes at date t depend on innovations only in `[t-W,t+H-1]`, where `W=max(1,memory)`. Residue classes modulo `K=W+H` have disjoint innovation sets. IID innovations therefore provide mutual independence **within** each class. All ten declared K values match this relation, and all stored completion halos remain in payload validation. The last recorded completion coordinate does not enter the exact invented payoff formula; this cannot justify shortening a real strategy's footprint. Sources: design lines 27-35; `signal_calendar_laws.py:33-105`; `signal_calendar_evidence.py:133-214`; `signal_calendar_score_verify.py:243-332`.

Raw support is `delta-a/3 +/- (abs(a)+abs(gamma)+vmax) + jump extrema`. Excess retains the ORIGINAL `-a/3` centering and subtracts the benchmark constant, while its variable coefficients become `a-3/500` and `gamma-1/100`. P1 excess support is exactly `[-19/1000,13/1000]`. The current study and verifier both apply that distinction. Win values use strict `>0`; tie outcomes are not wins. Sources: `signal_calendar_score_study.py:117-156`, verifier lines 336-383; original protocol line 30.

Fresh independent enumeration of **1,088 positive-probability compressed daily states** across all ten laws reconstructs E[A]/E[C] and every win truth; it verifies each per-trade support and daily score support. Counts retain the source-state weighting `P(previous=+1 | selected trade)=2/3`. Each law's raw truth equals delta and excess equals `delta-1/200`. Rare jump atoms are included even if a finite observed history happens to contain none.

**128 exhaustive complete P2/n2 sign histories** and **40 deterministic all-profile/n17 histories** match manually recomputed Fraction totals against optimized replay, scalar replay and independent verifier totals. The 40 cases also reconcile all study/verifier endpoints, coverage, tail flags, precision and direction flags. These are bounded parity checks; they do not exhaust full-length payloads or prove every possible int64 overflow path. Source review finds pre-array integer bounds and arbitrary-precision fallbacks in both evaluator implementations.

## Selection, precision and degenerate cases

For dense histories the asserted daily law guarantees `n<=C<=2n`. Consequently full interval width is at most `2 Delta sqrt(10 K/n)`, whose square is `40 K Delta^2/n`. Pre-data eligibility requires `40 K Delta^2/n <= (requested_width-4*10^-60)^2`. All **25 formal profile/metric combinations** pass the exact inequality independently; observed totals cannot rescue ineligibility. Source: score lines 146-173 and 224-242. P7 raw is a useful limiting value: n=131072, K=40, Delta=9/50, worst width about 0.0198874. P1 win uses n=2048, K=2 and worst width about 0.1976424. These are dates under invented laws, not real-market minimum-data recommendations.

Because eligibility is fixed before outcomes and every valid dense path emits, conditioning on valid arithmetic/precision emission does not select lucky dense paths. In sparse histories only unconditional **emitted-and-miss** control remains; dividing this bound by the probability of emission would be required before any conditional coverage statement. `assess` sets sparse `joint_coverage_lower` and `max_width_squared` to None and never marks sparse precision eligible. Zero C refuses, rather than yielding a zero mean. Study rows preserve the sparse unsupported label, including zero-count paths. Sources: score lines 146-181, 220-225; study lines 528-548; verifier lines 442-470.

The exact isqrt construction rounds radius upward on the fixed 10^-60 grid, by less than one grid step. Each endpoint adds less than another grid step outward; full displayed width excess is less than four steps. **24 independent squared-comparison cases**, including very small/large squares, negative and nonterminating means, and Decimal precision 1, verify enclosure without trusting a floating square root. The known n40/K1/support[0,1]/width1/count40/total40/3 equality case is ineligible before data; its outward display really is wider than 1. For support point 1/3 the exact point is retained as Fraction 1/3 and its decimal enclosure has width exactly 10^-60. Sources: score lines 185-201 and 235-249. Seven explicit invalid-input checks confirm refusal for zero count, dense-count violation, excessive count, aggregate support violation, real scope, observed-only assumptions and differing cohorts.

## Study multiplicity is separate from interval coverage

Within-history interval coverage uses at most six tails. The study independently makes 25*3+9+4=**88** rate statements, assigning `eta=(1/20)/88=1/1760` to each. Bonferroni does not require independence between statements, but each individual binomial assessment still requires its asserted IID repeated-history model. Fresh exact combinatorial sums reproduce **60 small-N cutoff cases**, including impossible cutoffs and equality. A separate SciPy numerical boundary check at N32768 reproduces coverage cutoff31258, directional-tail cutoff270, and detection cutoff29668: each accepted tail is <=1/1760 while its adjacent rejected tail exceeds it. These numerical large-N checks are crosschecks, not exact floating-point proofs. Sources: study lines 110-114 and 177-223; original protocol lines 36-46. No claim of universal familywise control across exposed v2/v3 attempts follows; the replacement protocol correctly discloses this.

## Adversarial limitations and stop conditions

The pure helper verifies aggregate consistency and strict declaration values, not the truth of external assumptions. A deterministic adversarial witness in the proof sets 200 dates to the same fair win/loss bit, declares K=1, and returns all declaration flags as fixture-declared. Both aggregate paths are accepted and width eligible, but **0 of 2 intervals cover the true win rate 1/2**. The actual dependence requires K=200. This is deliberately outside the asserted model, not a calculator defect; it demonstrates why valid-looking aggregates and unchecked labels cannot certify real-market confidence. Similarly, a valid aggregate total cannot establish the per-date cap, original complete cohort, absence of missing data, or per-trade support. Those are explicitly external premises in the module documentation.

Real-data applicability remains held until support, dependence, complete cohort/time/benchmark evidence and count bounds are justified for the actual source, with any selection/adaptive-search scope addressed. The SHA-counter generator is computational pseudorandomness; distinct streams and exact byte mapping are not a mathematical proof of IID (already disclosed in original protocol line 50). Stationarity and genuine bounded support are not established by low sample autocorrelation, observed minima/maxima, the all-PASS study, or these fixtures. Even a fully verified artificial study establishes only the frozen artificial-family claim. Unexpected formal refusals or source-law violations must remain ERROR/incomplete rather than counted as coverage. No existing blocker is closed by this review.

The completed-study JSON was read and hashed for scope and provenance only. Its retained four native verification receipts and development/validation PASS are not newly reproduced raw-study evidence here. No mathematical defect emerged that requires changing active code, widening an allowance, changing the gate or drawing again. Next use of this report is root reproduction and applicability explanation; any extension requires its own explicit premises/proof before implementation.

## Source identities

Full SHA256 map is in `proof.json`. Load-bearing files:

| File | SHA256 |
|---|---|
| signal_calendar_score.py | 7b19acfe21715fe082b13879ea9d3348d769131ab596553baf0c20fd5c600fc7 |
| signal_calendar_score_study.py | eca2cfd8e1ff48178a910b51e54330c78c9f60855d8dd6ef0edff010f56df974 |
| signal_calendar_score_verify.py | 7748f1e560403e9f0d61976186602dfc8907ad1044a67d1b2388c6673d3a1d3c |
| signal_calendar_evidence.py | 5985f3b0f55dc0f89d2632bc9b4378b8fd3c1922029292a91ca52b848d25e234 |
| signal_calendar_laws.py | 811070fa4247a10c5aad612829a6b3f20421f04793a77a3b44017e7ee18b6ba4 |

Review harness note: the first local run compared the full verifier result dictionary to the study's narrower serialized dictionary and stopped on key-set inequality. The harness was corrected to compare every shared serialized field plus the coverage/tail flags separately; source code was unchanged. This was an audit-harness shape error, not a calculator finding. Both final successful runs are deterministic, with no study reuse or sampling.
