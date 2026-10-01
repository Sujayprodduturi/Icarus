# Combined Gaussian-factor moment implementation
Date:2026-10-01. Operator D37 approved the [reviewed proposal](2026-10-01-signal-persistent-moment-proposal.md). Build verification in progress; [evidence](../reviews/2026-10-01-signal-persistent-moment-build.md) controls completion.

## Bounded unit and acceptance
- Add GaussianMomentModelContract and estimate_persistent to the existing moment research module, with PersistentMomentResult retaining the original calculation plus explicit dependence/model diagnostics.
- Share only support-neutral stationary-local premises and complete latent-coordinate validation with the bounded module. Keep its existing public type and class-partition ordering unchanged.
- Reuse premise-free cohort validation and finishing; independent estimate retains its required-independence check and original behavior. Combined estimate never forges that premise.
- Exact original weights, means, centers, moments and diagonal variance; conservative linear recurrence for shared covariance; original latent gaps after zero-moment projection; preflight all powers before allocation; certified upward square roots/radius and outward endpoints. At zero persistence/one active group recover exact old diagonal calculation, including alpha1/3.
- Unknown model/cohort/moment/selection, invalid map, nonfinite/oversized inputs and uncertifiable numerics refuse. All-known cases still validate geometry and moment contradictions. Absolute width failure returns diagnostics without endpoints.
- Deterministic linear Gaussian sharp-variance, negative-persistence, nonlinear Hermite, independent local-noise, unequal-weight/irregular-gap, irrational square-root, huge-mean/tiny-radius and hostile-context checks. No sampled coverage claim.
- TDD red/green, Windows default suite,150-source strict mypy/Ruff/format, independent numerical review, ordered simplicity then engineering review, primary actual-API oracle and old-API snapshots, commit then bounded guard mutations with exact byte restoration. Record any suite skips/failures without implying datastore or official-runner certification.

## Implementation decisions
The recurrence carries upward weighted standard deviations and decays between actual consecutive active indices. The exact diagonal is never reconstructed from rounded roots. The shared finalizer accepts an exact represented nonnegative cross allowance and keeps the old diagnostic types and absolute mathematical-width rule. The class-free model carries seven UNKNOWN-by-default declarations, including whole local raw/benchmark mapping and preservation of the actual moment law; these are trusted artificial-law premises, not evidence authenticated from observed data.

Only the new route prevalidates persistence through the moment input guard before the shared older parser. This closes large Decimal coefficient allocation without changing the old bounded API. Resource caps are research allocation limits, not strategy thresholds.

No product adapter/import, RNG screen, official/reserved stream, real-data trial, accepted method/floor, config threshold, inference enablement, lockbox or broker/live path is included. Task3a and M1-M4 remain OPEN. Next is a separately reviewed real-data assumption/accounting and validation/stress policy; this build does not establish those premises.
