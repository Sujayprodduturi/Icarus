# Active calendar-score calculator boundary audit

Date: 2026-10-08. Reviewed Git HEAD `8819514944ea91365e5fa14ea32f772f4bca0913` without modifying core code, tests or docs. Active calculator SHA-256 is `7b19acfe21715fe082b13879ea9d3348d769131ab596553baf0c20fd5c600fc7`; active unit-test SHA-256 is `6e2807a0eda37ab7c2e4276592b7f09e4119954a147dfc239fd607d6f2415b6c`. The rejected historical `signal_calendar_uncertainty` implementation was not treated as the active score.

## Verdict

**Scoped GO for the current frozen synthetic-fixture diagnostic and its completed artificial-study interpretation. NO-GO for real/observed trades, product inference, positive-alpha evidence, M4 closure, method adoption or promotion.** No P0/P1 arithmetic or refusal defect was found. The existing artificial PASS establishes behavior under invented laws only.

## Findings

### P2 — caller-supplied declarations are not authenticated provenance

`Model.scope` and the four assumption fields are ordinary caller-created enum values. `_validate_model` correctly refuses `Scope.REAL`, `Declaration.OBSERVED`, `Declaration.UNKNOWN`, strings and subclasses, but it cannot tell whether an external caller has relabelled arbitrary aggregates as `Scope.SYNTHETIC` plus four `FIXTURE_DECLARED` values (`scripts/research/signal_calendar_score.py:108-132`). The deterministic probe constructs exactly that model and receives `decision_eligible=True` from arbitrary in-support totals. The module itself discloses this limitation: declarations are assumptions, not source/market certificates (`scripts/research/signal_calendar_score.py:1-6`).

This does not invalidate the current artificial study. Its only direct calculator caller builds models from fixed `StudySpec`/law objects (`scripts/research/signal_calendar_score_study.py:158-173`), replays the complete synthetic payload before calculation, and preserves adequacy as a separate precision flag (`scripts/research/signal_calendar_score_study.py:506-573`). The independent verifier reconstructs the frozen stream and reimplements totals/support/endpoints without calling the production calculator (`scripts/research/signal_calendar_score_verify.py:1`, `243-332`, `369-479`). A repository scan found no production/engine import of the calculator.

Required integration rule: do not expose this low-level helper as a real-data decision API and do not accept caller-selected declaration fields as evidence. A future real-data adapter needs a separately reviewed, source-bound applicability contract that authenticates the complete calendar, support, dependency coloring, stationarity, counts, benchmark matching and cost provenance. A new enum or boolean would not supply that proof.

### P3 — the unit suite does not pin several useful boundary regressions

The 52 current tests cover happy paths, pre-data insufficiency, rounding equality, decimal-context independence, exact points, sparse refusal, unknown assumptions, real scope, common bad geometry, common malformed rationals, count/support/cohort errors, the declared geometry table and a small exhaustive law (`tests/unit/test_signal_calendar_score_research.py:35-249`). They do not explicitly pin `NaN`/`inf`, maximum `n/classes/count`, the exact 256-bit acceptance edge, `Declaration.OBSERVED`, or the fact that fixture declarations are self-asserted rather than authenticated. The audit probe covers all of those deterministically. This is a regression-coverage gap, not a reproduced calculator failure.

## Boundary results

- Exact types are enforced. `bool`, floats, `Decimal`, `NaN`, `inf`, wrong dataclass/enum/container types and integer subclasses do not pass as exact rationals or geometry (`signal_calendar_score.py:96-105`, `108-138`, `204-215`).
- Geometry is bounded to `1 <= n <= 1,048,576`, `1 <= classes <= 64`, exact `bool dense`; the maximum geometry and `count=2*n` complete successfully in the probe (`signal_calendar_score.py:108-122`, `218-235`).
- Rational inputs are limited to 256-bit numerator/denominator. The exact 256-bit denominator edge is accepted and 257-bit input refuses before score arithmetic (`signal_calendar_score.py:96-105`).
- One to three unique metrics are required. Duplicate metrics, malformed targets, invalid win support, different cohort counts, counts outside `[0,2n]`, dense counts below `n`, zero count, support violations and non-integral win totals refuse (`signal_calendar_score.py:135-182`, `204-233`).
- Dense eligibility is fixed before totals and cannot be rescued by high observed count. Sparse output always carries `decision_eligible=False`, no joint-coverage lower bound and reason `sparse_selection_unsupported` (`signal_calendar_score.py:146-182`, `204-241`).
- The exact pre-data guard subtracts the fixed `4e-60` allowance; the `n=40,K=1,Delta=1,width=1` equality case refuses before data. Endpoints use exact integer square-root and outward fixed-grid rounding; eligible display widths are rechecked (`signal_calendar_score.py:161-165`, `185-201`, `234-251`). No false finite-width claim was reproduced.
- An interval may be computed for an ineligible dense/sparse diagnostic, but adequacy remains false. Current study callers copy that state into `precision`; they do not turn a narrow diagnostic interval into eligibility or positive trading evidence (`signal_calendar_score_study.py:550-570`).

## Applicability policy still required before real trades

The calculator cannot establish that a market cohort has complete quiet dates/halos, a trusted population support, a proved independent-class cover, stationarity, non-selective completion or source-authenticated counts. The active statistics dependency contract separately requires `inference_enabled: false` through synthetic work and blocks official inference on F48 cost exactness, complete time-resolved benchmark certificates, source-specific matching rules and the Step 7 atomic counted-trial barrier (`docs/plans/2026-09-26-signal-statistics-design.md:23-29`, `41-49`, `63-73`). `docs/STATE.md:1` and `docs/HANDOVER.md:122-148` continue to leave Task 3a, M1-M4, F48, matching, trial persistence and the public real-data runner open. None of the artificial coverage/detection counters is a strategy result.

## Verification

- `boundary_probe.py`: 22/22 deterministic cases passed in 1.168 s with Python 3.12.10. It includes malformed numeric types, bool subclasses, 256/257-bit edges, count/support/cohort/duplicate/zero cases, dense/sparse eligibility, rounding equality, maximum geometry and the self-asserted declaration reproduction.
- `.venv/Scripts/python.exe -m pytest tests/unit/test_signal_calendar_score_research.py -q`: **52 passed in 1.941 s**.
- The first `uv` invocation never launched Python because the sandboxed uv cache was read-only. The repository virtual-environment interpreter ran the same checks successfully.
- Machine-readable proof: `var/verification/2026-10-08/calculator-review/boundary/boundary-proof.json`. Reproduction script: `var/verification/2026-10-08/calculator-review/boundary/boundary_probe.py`.

No full suite, engine-heavy run, RNG, data draw, official/reserved stream, real/lockbox/broker path or cleanup was used.
