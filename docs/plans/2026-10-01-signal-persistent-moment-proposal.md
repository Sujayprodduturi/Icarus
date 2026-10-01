# Combined persistent-market and extreme-return uncertainty proposal

Date: 2026-10-01. Status: independently reviewed design ready for operator presentation; operator D37 approved implementation with Implement; isolated build complete at source3d0dd81. Research only, deterministic tests only. Existing source: d1070d2; independent moment implementation: f0bab2f.

## What this adds, in plain English

We already have separate calculators for two problems: trades can move together because they share market conditions, and a few unusually large outcomes can make an average unreliable. This proposal combines those protections. It keeps every trade in the average and gives a wider uncertainty range when the declared artificial model permits stronger shared movement or larger outcomes. If that range is too wide, the answer is still "not enough evidence".

This is a calculator for explicitly described artificial examples. It does not yet establish that actual market data meets its assumptions or judge a strategy. Real-data assumptions, validation policy and product adoption remain later work.

## Selected approach and alternatives

Use a direct upper bound on the variance of the original weighted average under a declared stationary Gaussian market factor. This avoids the fixed-class event-transfer penalty used by the existing bounded reference. Classwise Chebyshev plus total-variation event transfer is a valid alternative with matching original marginals, but is much wider in the checked examples: about38.59 and16.90 percentage points for the first two geometries below. At192 groups and persistence0.6 its event-transfer allowance exhausts alpha. The direct covariance theorem is a different valid proof, not a relaxed confidence target. Do not transfer unbounded moments through total variation.

## Required contract

The source retains complete cohort membership, original trade counts, law/provenance identity, fixed metric and selection declarations, and trusted whole-group second-moment declarations from the independent moment reference. For each group g, its selected raw return or directly paired benchmark-excess mean Y_g has E[(Y_g-c_g)^2] <= M_g. The bound concerns the actual whole-group output, not individual marginal moments; within-group dependence is permitted. These are trusted artificial-law inputs, never fitted observed moments.

A new class-free model contract declares F_0 standard normal and F_t = rho F_(t-1) + sqrt(1-rho^2) epsilon_t with independent standard normal innovations, and a known |rho| <= r <1. Every group maps to one unique nonnegative integer index on the same complete latent axis. Each entire raw-and-benchmark output vector is a fixed function only of its own indexed factor and group-local noise. Local noise vectors are mutually independent and independent of the entire factor process. Output returns need not be Gaussian or bounded. Unknown or incompatible premises refuse; a sample correlation is not proof of this model.

The new route does not require global group independence and must never forge that declaration to enter the old helper. All groups, including zero-moment groups, require complete truthful contracts and geometry validation. An empty/invalid cohort refuses. M_g=0 means the group mean equals its declared center, although individual trades may cancel. This consistency check applies before any all-known shortcut.

## Proof and original estimand

Weights remain w_g=n_g/N and the estimate remains the original all-trade average, including direct paired excess where requested. Conditional independence of local noises makes cross-group conditional covariance zero. Put f_g(F_(t_g))=E[Y_g|the whole factor process]. The local-map premise makes this a function of its one indexed factor. Conditional expectation contracts variance, so Var(f_g) <= Var(Y_g) <= M_g. The sharp scalar Gaussian L2 correlation inequality then gives

    |Cov(Y_g,Y_h)| <= r^abs(t_g-t_h) sqrt(M_g M_h).
    V_0 = sum_g w_g^2 M_g
    V = V_0 + 2 sum_(g<h) w_g w_h r^abs(t_g-t_h) sqrt(M_g M_h)
    h = sqrt(V/alpha)

Chebyshev on the actual dependent law gives coverage at least1-alpha for the original population average within estimate +/-h. Centers support the moment bounds; they do not replace observed group means or the sample estimate. There is no fitted covariance or assumed cross-class independence.

Primary sources checked2026-10-01: [Veraar, scalar inequality Eq(1.1), page1](https://fa.ewi.tudelft.nl/~veraar/research/papers/Gebelein.pdf), [Gaussian AR notes](https://www.sfu.ca/~lockhart/richard/804/99_3/lectures/07/web.html), and [Chebyshev explanation](https://www.stat.berkeley.edu/~stark/SticiGui/Text/clt.htm). Use the sharp scalar constant1, not an unspecified general vector-valued constant. This project-specific application follows by conditioning as above.

## Small implementation and conservative arithmetic

Sort positive-moment groups by actual latent index. Let a_i be an upward certified enclosure of w_i sqrt(M_i). With R=0 and cross=0, decay R by exact r^(actual consecutive active gap), add upward2*a_i*R to cross, then add a_i to R. This computes the dense pair sum in linear arithmetic after sorting; exact-number growth still needs resource guards. Zero-moment groups retain their original weights and known centers, and their removal from uncertainty must not compress the latent gaps.

Keep V_0 exact rational. Enclose every positive cross contribution upward, then use V_upper=V_0+represented_cross_upper for the existing exact squared-radius certificate. At r=0, or one active group, bypass square-root accumulation and recover the original exact diagonal reference. Preflight exact power growth for all active consecutive gaps before any exponentiation. Refuse overflow, positive-value collapse, excessive exponent/number growth, or uncertifiable arithmetic. Ambient Decimal precision/traps must not affect the result.

Extract only support-neutral stationary-factor/local-map/axis/index validation and premise-free cohort/moment validation that the two real routes need. Preserve exact public type checks at entry points. The old independent route retains its independence requirement. Existing persistent bounded contracts, class validation, TV/log/Hoeffding calculations, refusal behavior and APIs remain unchanged. Do not introduce dummy classes, fake finite supports, a generic framework or a covariance matrix.

Diagnostics retain original weights, selected means, centers, moments and provenance, plus declared model identity, actual indices/gaps, r, exact diagonal variance, conservative cross allowance, V_upper and certified radius. Absolute mathematical full width2h is checked against the predeclared request. Too-wide output has diagnostics but no confidence endpoints. Preserve the independent helper's outward endpoint convention: rounding may make represented endpoint span slightly wider than mathematical2h. No precision target is adjusted after examples.

## Deterministic examples and independent checks

All examples use equal group moment bounds M=0.0004, alpha=0.05 and consecutive actual indices. These are illustrative trusted-law numbers, not estimates from exposed calibration data. A requested1 percentage-point full width is illustrative, not an accepted product floor.

| Groups / trades | Persistence bound | Mathematical full width | Illustrative precision verdict |
|---|---:|---:|---|
|24 /192 (8 trades per group)|0.5|6.146362982304 percentage points|Insufficient|
|192 /192|0.5|2.228290326187 percentage points|Insufficient|
|192 /192|0.6|2.569350598887 percentage points|Insufficient|

Primary calculated exact rational dense covariance sums and exact recurrences, then100-digit widths; an independent reviewer reproduced the table. Local ignored arithmetic evidence: var/verification/2026-10-01/persistent-moment-design/primary-covariance-check.json. The24-group shape alone does not certify or repair an existing calibration profile.

Additional primary analytic checks: unequal weights1/6,1/2,1/3, moment square roots1/5,1/10,3/20, indices0,3,9 and r=1/2 give V=3047/460800 by both dense and recurrent sums. A zero-moment middle group with original weights(1/6,1/2,1/3), moments(4,0,4), and indices0,2,10 retains gap10; its active weighted coefficients are(1/3,2/3), giving V=427/768. Negative rho=-1/2 at indices0,1,4 with equal linear coefficients1/3 gives true variance5/24 below the absolute bound35/72. Normalized second Hermite outputs at gap3 have covariance1/64 versus bound1/8; A separate normalized linear-plus-noise example Y=(F+epsilon)/sqrt(2), with independent standard normal group-local noise, has covariance1/16 at gap3 versus noiseless linear covariance1/8.

## Build acceptance after approval

1. Add the pure class-free combined calculator and narrow shared validators, protecting all old public paths with regression checks, including refusal precedence on multiply-invalid inputs and explicit fixture/law compatibility.
2. Prove dense-oracle/recurrence agreement for unequal weights and irregular gaps; test zero moments, all-known consistency, r=0 exact recovery including nonterminating alpha, one active group, direct paired excess and fixed original aggregation.
3. Use analytic linear Gaussian laws that attain the variance bound, nonlinear Hermite laws, negative persistence and independent local noise. Variance sharpness is not exact Chebyshev coverage. Use true expectations only as oracle inputs; do not estimate moments by drawing data.
4. Test unknown/false premises, incomplete/duplicate/mixed-axis coordinates, wrong provenance, invalid persistence, unsupported selection, giant gaps/preallocation guards, positive underflow, extreme magnitudes, ambient contexts and outward endpoint certificates. Width failure must return honest insufficiency.
5. Run appropriate Windows regression, Ruff, format and strict mypy; independent numerical review and ordered simplicity/engineering review; primary reproduction and bounded defect probes with exact restoration. Record exact source/hashes, tests and limitations in build evidence and update state/handover before completion.

No RNG screen, official/reserved-stream draws, real-data evaluation, strategy verdict, accepted data floor, threshold edit, inference enablement, lockbox access or broker/live path is included. Task3a and M1-M4 stay OPEN. D36 covers the preceding independent-tail build only; this combined implementation needs a new concrete operator approval.

## Review record

Two medium-effort read-only reviewers independently approved the direct proof and lean scope during design exploration: combined_moment_math and combined_moment_scope. Both checked the scalar theorem; primary reproduced their arithmetic rather than accepting messages alone. Both reviewers read the final written proposal and approved it for operator presentation with no blocker. Mathematical review clarified reproducible zero-moment inputs and the separate linear-plus-noise example; scope review required preservation of refusal precedence on multiply-invalid old inputs. Primary incorporated and checked all changes. This is proposal approval, not operator implementation approval or real-data certification.

Documentation verification: all local Markdown links in the five changed documents resolve; ranked-audit checker15 passed in0.08s; whitespace check passed; tracked-file numstat agrees with CR-insensitive numstat, preserving existing line endings. No product source was changed and no new broad code-test result is claimed.

Operator approval addendum2026-10-01: D37 approves the concrete isolated implementation and deterministic verification. Earlier proposal-stage approval statements are retained as dated design history. No held boundary was expanded.

Completion addendum2026-10-01: [build evidence](../reviews/2026-10-01-signal-persistent-moment-build.md) records the implemented class-free reference, independent reviews,1940 passing default Windows tests/10 skips,150-source static checks and three caught/restored post-commit guard defects followed by293 passing research tests. Real-data eligibility and Task3a remain unresolved.
