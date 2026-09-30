# Bounded uncertainty research implementation plan

> **For agentic workers:** Use test-driven development and independent review. Implement the single coherent research unit below; no product or stochastic follow-up.

**Goal:** Build the operator-approved pure finite-sample research benchmark and evidence-insufficiency calculator.
**Architecture:** Immutable fixture/source/member/group/support contracts and pure arithmetic in scripts/research/signal_bounded_uncertainty.py, with deterministic tests in tests/unit/test_signal_bounded_uncertainty_research.py. Existing engine and research methods stay unchanged.
**Tech stack:** Python3.12 standard-library Fraction/Decimal, existing pytest/uv/Ruff/mypy. No dependency edits.
**Spec:** 2026-09-30-signal-bounded-uncertainty-design.md.
**Authorization:** Operator explicitly said Yes do it on2026-09-30 to this reviewed component and deterministic tests. This covers its concrete plan/build/reviews; no new Monte Carlo screen/product method/data floor or official stream is authorized.

## Global constraints
- Synthetic fixture only, immutable predeclared grouping/counts/support and explicit assumption provenance. No real-data adapter or independence detector/certificate issuer.
- Trade-weighted mean; individual-trade support; paired whole-cohort excess; fixed source/member coverage. Unknown support/dependence, outcome-selected geometry and invalid data refuse.
- Confidence/desired precision supplied by caller's fixture specification; no hardcoded product policy and no goal/manifest/digest/lock edits.
- Exact rational mean/weights/support/Q from exact inputs. Decimal logarithm/square-root upper bounds and outward endpoint conversion with local context; no nearest-rounded float confidence endpoints.
- Structural known output only when every declared support is a consistent singleton; observed constants alone do not qualify. Precision insufficiency has no interval claim.
- No RNG, network, broker, Panel, inference enablement, real-data trial, lockbox use or official platform work.

## Review focus
- Numerical upper/lower arithmetic must dominate the exact real-number formula; no underflow or context leaks.
- Refusals are not covered/emitted intervals. The guarantee is not nominal conditional-on-emission coverage after data-dependent refusal.
- Support is a trusted fixture assumption, not data-estimated range or a broker stop guarantee.
- Geometry/member identity and weights remain intact across metrics and reordering.
- Exact-zero support differs from tiny nonzero supports and large cancelling offsets.

## Task1: Typed helper and deterministic proof checks
- [x] Write immutable typed source/member/group/assumption/observation/result/refusal contracts and test the intended API through failing tests before implementation.
- [x] Observe RED for missing/unimplemented helper, then implement input validation and paired metric vectors with stable explicit refusals.
- [x] Implement Fraction aggregates and bounded Hoeffding formula; Decimal monotone upper log/radius and outward interval endpoints. Record untrimmed/intersected endpoints, support/Q/counts/concentration/precision and research/conditional-assumption labels.
- [x] Test independent high-precision arithmetic oracle, fixed unequal weights, row invariance and affine transforms; positive observed-constant radius; heterogeneous singleton result; numerical extremes/refusals.
- [x] Exhaustively enumerate tiny independent two-point group fixtures and exact outcome probabilities. Check coverage and report counts/refusals honestly; never redraw or claim a45-profile verdict.
- [x] Test192 trades/24groups vs192 independent units, concentration,24 vs119group precision illustration, and precision evaluated before favorable clipping.
- [x] Run focused and relevant simulator/statistics/portfolio-characterization regressions, strict mypy/Ruff and formatting.
- [x] Independent numerical plus ponytail/engineering/governance review; primary independently verify at least one numeric value and failure path before acceptance.
- [x] Commit verified implementation, reintroduce actual found bugs in isolated byte snapshots to prove regressions fail, restore exact bytes and rerun focused checks.
- [x] Update STATE/HANDOVER/TASKS/audit, record evidence/limits/operator approval, commit/push. Task3a and dependent-series inference remain incomplete.
