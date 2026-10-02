# Calendar-score reference: implementation and verification

Date: 2026-10-02. The operator explicitly approved proceeding and using required resources after the reviewed design milestone. This completes the isolated deterministic helper, not a sampled experiment, accepted market method, Task3a or strategy promotion.

## What changed

`scripts/research/signal_calendar_score.py` implements the approved synthetic-only calendar score bound for up to three fixed targets. The original all-trade mean uses validated totals and counts; trusted stationarity, support, independent date classes and complete-calendar declarations are mandatory. It has no broker, network, file IO or random sampling.

`assess` checks useful eligibility without observing totals. Its exact fixed-grid allowance prevents outward rounding from exceeding the requested width on dense eligible paths. `calculate` uses exact rational squared radii, integer square-root ceilings and outward Decimal tuple construction, unaffected by a caller's Decimal precision. Nonterminating point targets retain an exact Fraction and a separately bounded display enclosure. Count/support violations, malformed budgets and unknown/observed/real assumptions raise typed errors.

The guarantee remains conditional on the stated synthetic model: declarations and aggregate bounds do not authenticate source rows, complete shared cohorts, real dependence, costs/taxes or benchmarks. For sparse models the result deliberately reports no dense maximum-width or joint-coverage lower bound, only an unconditional emitted-and-miss upper bound. It never claims confidence conditional on sparse or precision-selected survivors. Zero counts refuse. A high realized count cannot rescue failed pre-data eligibility.

## Verification at the reviewed source

- Initial test-first run:52 assertion failures because the new helper did not exist, before implementation. First implementation:52 passed. An additional sparse-label assertion then failed as intended, before replacing inappropriate dense width/coverage fields with unavailable values for sparse models. Final52 passed in0.14s.
- Relevant research tests plus the existing synthetic portfolio characterization:514 passed in16.90s. This includes the new52, old failed-candidate/reference/runner regression tests and the available golden fixture. It does not claim a newly captured production backtest.
- Strict mypy for `icarus`, `tests` and `scripts/research`:164 source files clean. Full `icarus scripts tests` Ruff check clean;170 files already formatted.
- Primary exact rational checks:225 endpoint/radius/width/coverage cases across all25 requested supports/nine proposed geometries, plus bounded large signed/tiny-rational input cases. An independent integer-binomial sum reproduced the reviewer's257-state endogenous-count oracle: miss probability approximately2.352195997075022e-6, below the single-target bound approximately0.013663012625946366. This enumerates a finite mathematical law; it samples no histories and does not qualify an experiment.
- One focused reviewer performed the actual simplicity review first, then engineering/mathematical review;52 tests,16 independent endpoint checks and severe Decimal-context checks passed. [Exact-hash review](2026-10-02-calendar-score-code-review.md) approves the files below. No additional agents or duplicate full-suite run.

Reviewed source SHA256:`7b19acfe21715fe082b13879ea9d3348d769131ab596553baf0c20fd5c600fc7`.
Reviewed test SHA256:`6e2807a0eda37ab7c2e4276592b7f09e4119954a147dfc239fd607d6f2415b6c`.

Primary retained commands/output under `var/verification/2026-10-02/calendar-geometry/score-*.txt`, plus `score_primary_oracle.py`. PowerShell redirected logs are UTF-16. The initial sparse-field correction was a real development finding; later intentional mutants, if recorded below, are test-strength checks rather than discovered production bugs.

## Resources and next step

Read-only current-PC snapshot:12 logical CPUs,15.93GiB RAM total,2.41GiB available at inspection,318.23GiB workspace disk free. Availability is transient, not a runtime guarantee. The operator's resource authorization permits preparing a larger finite experiment budget; it does not retroactively alter the failed v1 protocol, prove current memory/runtime feasibility, or authorize real-market data. The old3GiB experiment cap is a frozen design limit, not the physical capacity of this PC.

The conservative proposal's long-history path payload lower bound is14GiB before other records. A future resource proposal can account for available disk and measured runtime; it still needs a new stream/protocol, full source-adapter/evidence design and preflight. The current helper cannot supply those by itself. No new sampled driver or large-history adapter was built, no new stochastic history was drawn, and the old confirmation root remains unopened.

Next: a bounded design for retaining/verifying long-history evidence on this PC and measuring its actual runtime, or a sharper justified method if the conservative history burden is impractical. The operator has authorized required resources, so do not ask again merely because the new budget differs from v1. Record any resource amendment before its own draws and preserve all statistical/safety boundaries. Practical sparse/market applicability and M1-M4 remain open; inference stays disabled.

The previous2108-pass/10-skip full Windows suite remains historical evidence; this build freshly ran the relevant514-test regression and global static checks. No fresh full-suite or datastore/OS proof is claimed.

## Post-commit safeguard verification

Source committed at `0b9eba3`. Three bounded intentional defects were then applied serially to the new helper only: round the radius inward, ignore pre-data history eligibility, and claim a sparse joint-coverage lower bound. Each selected test run failed with pytest exit1; the exact source bytes were restored in a `finally` block after every case and matched the approved source hash. `score-mutations.json` retains the results. The restored calendar/reference/runner/geometry/portfolio regression then passed221 tests in8.91s. These are deliberate test-strength checks, not newly discovered implementation defects. No test mutation or source change remains.
