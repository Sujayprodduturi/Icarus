# Deterministic finite-window diagnosis build

Date:2026-10-02. D41 continuation after verified artificial-calendar failure.
This module provides exact toy variance geometry and observed-count identities;
it provides no confidence interval, width fix or actual-market/law certificate.

Reviewed [plan](../plans/2026-10-02-calendar-finite-window-diagnosis.md), independent
[mathematics](2026-10-02-calendar-geometry-math-review.md), and ordered actual
[simplicity/engineering](2026-10-02-calendar-geometry-code-review.md) all approve.
Source SHA256 `5f068bd188d75f869c4b442e1991601271413ca0af2b99e2be3708da9ea06f74`;
tests `656c2e1fc6b93e41200dc8e3141849b771310aea14e4eae9db446572f6478512`.

Actual TDD red:50 tests failed on absent implementation in0.49s. Final component
green:50 passed2.94s. Primary focused regression:168 passed8.22s, mypy152 source
files clean, Ruff clean and168-file formatting clean. Fresh complete default
Windows regression is running; its result will be appended after completion.

The primary independently reproduced exact unit-score examples: n64/b16 centered
variance3/4 and adjacent covariance11/16; n128/b26 variance51/64 and covariance
631/832. For filter(1,-1), n64/b16 full-root variance1/32, boundary centered
variance13/128 and interior17/128. This counterexample prevents treating the iid
shrink factor as a universal correction. Counts16/20 with totals3/10 and theta1/5
give exact block-minus-full mean-5/16 and observed count weight4/5.

The mathematical reviewer independently checked8 full-root,268 centered and260
adjacent variances/covariances with innovation-vector oracles beyond the tests.
Engineering additionally checked27 geometries against exhaustive16-atom laws,
with no sampling. Zero variance/filters are valid; invalid floats/bools/negative
variance/counts and oversized geometry/scalars refuse. Exact numeric inputs are
bounded to256 bits, filter64 and geometry256 dates.

These facts explain why overlap and count weighting must be handled carefully.
They do not apportion the actual observed undercoverage or establish a calibrated
interval. The failed estimator, its source manifest, thresholds, data and sealed
confirmation remain unchanged. M1-M4/Task3a remain OPEN; inference stays disabled.
The next research decision requires actual-law score covariance/count analysis
and a single justified candidate/resource protocol, with a new exposed version.
No new experiment or real-market simulator is enabled by this component.
