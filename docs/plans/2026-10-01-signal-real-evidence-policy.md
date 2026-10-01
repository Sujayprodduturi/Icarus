# Real-data evidence policy and next implementation boundary

Date: 2026-10-01. Status: proposal for independent written review and the major operator decision. Phase 1, Task 3a Step 6 remains in progress. No method adoption or study authorization.

## Purpose in plain English

The simulator answers what trades a strategy would have taken and what they returned. The uncertainty work asks how much of that result might be luck. The artificial-model calculators work, but they cannot establish that real trades follow their assumed model. That distinction must be settled before judging strategies.

Recommendation: separate descriptive facts, assumed-model sensitivity and eligible statistical evidence. Prepare a small pure research readiness report and a separately reviewed practical-method design. Another artificial-law calculator is not the next step.

## Options and recommendation

| Option | Benefit | Limitation | Recommendation |
|---|---|---|---|
| Externally justified finite-sample assumptions | Strong conditional mathematical statement | History cannot certify every unseen tail or the whole trading-path model | Retain this eligibility rule for the existing mathematical references |
| Explicitly assumed-model sensitivity | Shows how ranges change under stated assumptions | No calibrated market confidence or strategy verdict | Proposed reporting lane; never select a favorable assumption setting |
| Design and validate a practical dependent-data estimator | May address trading paths and market-selected observations more directly | Still depends on assumptions; empirical checks cannot guarantee every possible market | Separate research/design lane, requiring the major operator choice below |

GPT-6 Astra and an independent source/governance reviewer approved the written proposal for operator presentation. Their target-specific and scheduling clarifications are incorporated. No rejected estimator is rehabilitated. Original 45-profile failures remain evidence against those methods. No floor, threshold, confidence level, method or task dependency changes here.

## Accounting and allowed claims

| Output | Target and denominator | Cohort/time rule | Accounting and claim |
|---|---|---|---|
| Simulator observations | One filled signal is one trade; actual deployed entry capital; quantity-weighted exit fragments | Every emitted signal reconciles to a trade or explicit skip; expected missing inputs separate; decision/execution clocks retained | Current modelled charges, before tax; authorized synthetic behavior checks only |
| Raw descriptive mean | Original equal-per-trade arithmetic mean, without clipping or book weighting | All filled observations represented, including labelled stale marks | Net of modelled costs, before tax; arithmetic description, not population-edge evidence |
| Exact benchmark-relative mean | Original mean of direct paired trade excess | Certified entry and every actual exit; all filled trades matched; stale residual invalidates exact whole-trade excess | Same capital/event clocks, versioned source/benchmark certificate; before tax; currently unavailable |
| Artificial-model reference / sensitivity | Original weights n_g/N and declared whole-group moments | Fixed geometry, actual factor gaps and justified local-map assumptions | Declared raw or paired-excess target; conditional mathematics only |
| Later eligible signal inference | Same original diagnostic target, no favorable matched-subset substitution | Reviewed selection/denominator/full-footprint policy and complete source/benchmark eligibility | Corrected costs, before tax; unavailable until method and engineering prerequisites pass |
| Portfolio promotion | Actual capital-constrained account, fold-matched evidence | Existing walk-forward, trial, source and lockbox rules | After costs AND account-level taxes; separate later gate; a signal diagnostic never PROMOTES |

Verified at entry HEAD c12f022: `icarus/engine/signaltest.py` lines 252-285 subtract entry/all fragment charges from fragment P&L and divide by deployed capital; lines 295-338 distinguish stale marks and benchmark arithmetic. `signalmetrics.py` lines 293-294 raises if inference is enabled; lines 369-370 always refuse benchmark/placebo inference. No current output is reclassified.

## Why calculation is not eligibility

Premises must distinguish observed facts, empirical estimates, scenario assumptions and externally justified mathematical bounds. A provenance string or successful typed constructor is not independent proof. Sample variance cannot become a trusted population moment bound through routine conversion; fitted persistence cannot become a certified dependence bound.

Entry/completion counts and n_g/N depend on market paths. Holding outcomes depend on many bars and can overlap other trades. The combined proof instead requires fixed aggregation and each whole group to depend only on its own indexed Gaussian factor plus mutually independent local noise. Conditioning on selected trades/counts does not automatically preserve those assumptions. Normality tests, quiet autocorrelation or a variance multiplier cannot repair that mismatch.

Deterministic counterexample, not a market model: X is zero with probability .999 and 100 otherwise. In 100 independent observations, all values are zero with probability .999^100 = .9047921471..., although E[X^2]=10. Increasing the rare value makes the second moment arbitrarily large while preserving that quiet-sample probability and finite moments for each distribution. Finite variance existing differs from knowing a valid numerical bound.

Primary source checked 2026-10-01: [Veraar, scalar Gebelein inequality, equation 1.1](https://fa.ewi.tudelft.nl/~veraar/research/papers/Gebelein.pdf) assumes a jointly Gaussian pair and square-integrable centered functions. It does not certify the project's reduction for traded signals. The applicability reasoning and counterexample are project arguments.

## Smallest proposed build: pure research readiness report

Use invented metadata only. No panel loading, fitting, strategy execution, estimator invocation, persistence or network. Keep it isolated under research, without product/config integration or an adoption switch. It explains missing prerequisites; it cannot authorize a study.

Metadata covers study identity and requested target; source/time-axis identity; cohort and selection/holding footprint; accounting label/cost exactness; complete benchmark matching/stale residuals; trial-persistence readiness; model-premise evidence category; method/precision-policy status. These are declarations, not authenticated certificates. Unknown, missing or incompatible facts block the affected target. Missing benchmark matching blocks paired-excess evidence, not raw arithmetic. Empirical moments cannot qualify as trusted mathematical bounds, but do not prohibit proposing a future empirical estimator. No raw descriptive result becomes authorized real-data evaluation through this distinction.

Distinguish unknown applicability, known contradiction and insufficient conditional precision. If all declared prerequisites are present, say only "declared prerequisites complete; independent review still required". No state authorizes inference or a run. No confidence endpoints, p-values, profitability, strategy verdict or PROMOTED field. Existing sensitivity calculators stay separate.

Acceptance tests use invented records: unknown provenance and empirical moments cannot confer eligibility; incomplete matching, stale marks, inexact costs, wrong tax labels, incompatible holding footprints and absent trial readiness block; even an all-declared fixture cannot authorize inference. Do not build a generic assumptions framework or duplicate matcher/ledger/source certificates.

## Future stress and validation requirements

This is a requirements checklist, NOT a frozen experiment or draw authorization. Numeric cells, budgets, thresholds, stream identities and stopping rules require design/review before any run. Exposed samples cannot become untouched validation.

| Challenge | Required checks in a future preregistered design |
|---|---|
| Rare signed magnitudes and skew | Both interval tails, mean bias, width, refusal/emission; retain existing rare-profile failures |
| Persistence, volatility clustering, regimes and common shocks | Whole-path and cross-symbol dependence, near-boundary behavior; distinguish in-model and deliberately out-of-model cases |
| Unequal weights and overlapping outcomes | Original target, full holding footprint, actual gaps; random denominators and market-selected counts |
| Missingness and selected completion | Pinned cohort/refusal rules; no favorable complete-case or successful-run filtering |
| Zero/nonzero effect controls | Coverage plus prespecified absolute informativeness/width and detection criteria; broad ranges alone cannot pass |
| Repeated method search | Immutable exposure history/counting; retained failures/errors; independent untouched confirmation and stop-on-failure |

Signal stress retains D15's net-of-cost, before-tax diagnostic. Portfolio promotion retains existing 1.5x cost and equity/crypto tax scenarios. No fabricated per-trade account tax or post-hoc threshold changes. Frozen official protocol and reserved streams stay unchanged.

## Dependencies and findings still open

- M1-M4 remain OPEN: coverage, generally valid intervals, informativeness and actual-law applicability are unresolved.
- F48 remains OPEN: `CostModel.charges` adds delivery DP fees on each sell call; `_mark_position` calls sell charges for an unexecuted stale mark. A separate reviewed accounting fix needs symbol/day, same-day partial-sell and stale-mark tests plus portfolio regression. Existing configured rates are not freshly verified external rates here.
- F47 tradable exits and F20 source cross-check remain open findings to resolve or explicitly adjudicate in the later schedule amendment. They do not acquire a new task dependency edge here. Time-resolved source provenance and certified entry/every-exit benchmark matching remain required for official benchmark inference.
- Step 7's mandatory atomic, serialized signal-trial batch before results is unbuilt. Existing source/lockbox refusal cannot replace it.
- Step 6b needs accepted calibration; Step 7 depends on 6b; Step 8 needs the written/reviewed schedule amendment for source/matcher/accounting work. This policy is not that amendment. Do not silently skip dependencies.
- Windows official-resource/durable-claim and datastore findings remain separate. Continue supported tests on this PC; old attestation does not cover new sources.

## Major operator choice and next sequence

Recommend allowing future diagnostic research to design a preregistered, empirically tested method that states its market assumptions and refuses weak evidence. That is not a universal guarantee or a lowering of portfolio promotion requirements. Alternatively, require externally justified finite-sample bounds only and accept that inference may remain unavailable with current inputs.

Explain this choice at the milestone. If the practical direction is chosen, prepare one bounded literature/design assessment targeting dependent full trading paths and random counts; calendar-block/subsampling is a candidate for assessment, not an adopted method. Design any readiness implementation and stress protocol within the chosen scope before coding or draws. Later product work requires the schedule amendment above. No real-data run, reserved stream, lockbox, subscription, broker or live path is authorized.

Authority: [statistics design](2026-09-26-signal-statistics-design.md), [original task sequence](2026-08-22-signal-test.md), [method audit](../reviews/2026-09-30-signal-method-audit.md), [combined build](../reviews/2026-10-01-signal-persistent-moment-build.md), [operator decisions](../../OPERATOR.md).
