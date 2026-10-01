# Calendar uncertainty deterministic build

Date: 2026-10-01. Operator D40 scope. Source commit `7d5d9f571221ed16baa7dadad8d21b48b0d51618`. This completes the isolated calculator/refusal implementation, not Task3a, statistical calibration or product adoption.

## Result and contracts

The pure [calendar module](../../scripts/research/signal_calendar_uncertainty.py) preserves original whole-trade sum/count weighting, entry-session attribution, synchronous stocks, quiet sessions and complete authorized holding footprints. It computes every scheduled overlapping slice, exact deviation order/quantile ranks and sign-safe outward endpoints. Proposed b is the exact smallest integer with b^3>=n^2; product settings are unchanged.

All states remain `ASYMPTOTIC_CANDIDATE_UNCALIBRATED`, `market_eligible=False`. Endpoints are named `candidate_lower/candidate_upper`, never eligible-market confidence. Precision insufficiency retains candidate arithmetic and provenance. Unknown premises, incomplete identity manifests, malformed axes/records, unauthorized/model-incompatible footprints, stale/forced-end outcomes, zero scheduled slice counts, degenerate roots/quantiles and numeric/resource failures refuse. Missing benchmark affects core paired-excess inference; raw arithmetic may remain. Supplied nonfinite optional fields are malformed source records, distinct from absent optional benchmark data.

Exit coordinates are the sorted unique exit-session footprint after fragment aggregation, not one entry per execution fragment. Finite-lookback/completion, stationary joint count/return and CLT declarations are synthetic premises, not certificates. Endogenous signal counts are permitted; outcome-selected study/filter/precision policies are not. No source adapter, real-data detector or order path exists.

## Test-first findings and reviews

- Initial behavior suite:33 deliberate failures before source, recorded `tdd-red.txt`. Resource probes then produced2 failures; integrity follow-up recorded1 failure/1 pass; schema probes2 failures. These logs retain their actual outcomes rather than treating every drafted test as a demonstrated red witness.
- Primary independently reproduced two actual defects during development: same-bar decision/entry and plain-string metric aliases were accepted as candidates. Tests now require strict decision<entry and exact enum contracts. Complete actual-event footprints and aggregate/pre-expansion budgets also have refusal tests.
- An extreme10^4000 mean exposed avoidable precision sizing; bits are now converted to an upper decimal-digit count rather than used as decimal precision. The finite-endpoint/extreme-mean regression passes.
- Independent GPT-6 Astra mathematical reviewer approved final implementation hash, using nine nonzero actual-API geometries plus shifted origins, signed quantiles, rational/irrational scales, tiny-width insufficiency, hostile Decimal context, sparse counts and invalid numerics. Oracle uses exact Fractions and180-digit integer-square-root bounds, not production numeric helpers.
- Actual ponytail-review completed first: Lean already, no changes. Actual engineering code-review followed after primary confirmation: APPROVE, no actionable findings. Reviewer independently ran41 tests and369 malformed-field substitutions without escaping exceptions. Both reviews verified frozen hashes.
- Primary actual-API oracle independently checked eight geometries with exact aggregation/ranks and220-digit squared-certified sqrt brackets, including same-sign endpoint cases. A hand-worked8-session example returns mean .007, candidate endpoints approximately .00487867965644 and .00841421356237. This is arithmetic evidence only.

## Verification on the current Windows PC

- New deterministic tests:41 pass; independent reviewer run0.14s. Primary relevant regression:583 passed in13.12s, parent14.197s. Includes all eight research test files, signal simulator/statistics/oracle, fills, cost/tax, synthetic portfolio characterization and audit checks.
- Strict `uv run mypy icarus tests scripts/research/signal_calendar_uncertainty.py`:148 source files clean. Ruff clean;158 Python files formatted. All tracked Python files reside under the checked `icarus/scripts/tests` directories.
- Initial broad `ruff ... .` scanned an independent reviewer's untracked `.scratch` oracle and failed on scratch style. Retained first failure evidence; final tracked-source-directory lint/format checks pass. No lint configuration or production code was relaxed. Passed regression/mypy were not unnecessarily rerun for that scratch-only failure.
- After source commit, three bounded code defects were caught: same-bar guard relaxed, text-metric guard weakened, quantile direction reversed. Each exact anchor/application was checked, source bytes restored in finally blocks, and final334 research tests passed in4.92s. The first two reintroduce actual found defects; the third is a deliberate arithmetic defect.
- Protected config and existing simulator/statistics/cost/bounded/moment source hashes are byte-identical to entry. Source SHA256 `ef28eeebb2c807bbbed2c707cd1e20a752d448b537646a7beea0426fe2828ec9`; tests SHA256 `c0ed226704fec25db96b97a08702f5efb094b33b185147036ba5456deb7d711b`.

Evidence under ignored `var/verification/2026-10-01/calendar-build/`: red logs, primary oracle JSON, captured regression/static commands/logs, first scratch-lint failure, protected hashes, post-commit guard JSON/logs and restored regression. Independent oracle was subsequently moved from the task-created `.scratch/calendar_math_review.py` into ignored `var/verification/2026-10-01/calendar-build/independent-calendar-math-review.py`; its evidence is preserved and the untracked scratch file removed.

## Limits and next milestone

No RNG draw, sampled coverage study, market panel, trial-ledger write, lockbox, threshold/config change, method adoption or broker/live path. The whole-zero-slice refusal does not guarantee emission or nominal coverage conditional on emission. Finite-endpoint/reset effects, regime drift, rare tails and actual market assumptions remain unresolved.

No fresh full-suite/datastore integration or production golden backtest claim: the relevant synthetic portfolio characterization passed. Prior complete1940-pass/10-skip evidence retains its original source. Windows official-calibration resource/durability limits remain separate and unproven here.

Next task: write and independently review a separately preregistered artificial-market stress/confirmation protocol with exact target laws, profiles, emission/coverage/precision criteria, independent confirmation and stop rules before requesting any sampled study. M1-M4, F48 and Task3a remain OPEN; inference stays disabled. Original Step6b/7/8 dependencies and the later source/matcher/accounting schedule amendment remain required.
