# Step 6a.1 Pure Signal Estimator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a synthetic-only, independently checked CR2 variance/degree-of-freedom diagnostic for raw signal returns and win indicators, without emitting confidence intervals or enabling inference.

**Architecture:** A small `signalmetrics` module converts an immutable `SignalRunResult` plus an explicit canonical daily-session axis and its pre-registered origin into one observation per filled trade, then applies the declared source-session-block rule. It returns descriptive means and typed component refusals. A separate test oracle uses a dense projection matrix, not the product formula, to cross-check the candidate. No runner, market data, benchmark claim, placebo engine, config amendment, or broker path is added.

**Tech Stack:** Python 3.12, Decimal at the trade boundary, float64/NumPy for the estimator, pytest, Ruff, strict mypy, uv. No SciPy dependency in this slice.

**Spec:** `docs/plans/2026-09-26-signal-statistics-design.md` §§1, 3–4, 7–8. This is only Step 6a.1, not completion of Step 6a/6b.

## Global Constraints

- `goal.yaml` keeps `signal_test.inference_enabled: false`; no interval endpoints, p-values, alpha verdicts, or promotion verdicts are produced.
- Source-axis indices are full-source daily-session indices. `L = max(63, 3 × longest_holding_sessions)` from filled trades, including stale recognition duration. The caller supplies a fixed study-origin index; folds do not re-anchor it.
- One `SignalTrade` yields one observation regardless of exit-fragment count. Skips remain separate and are not zero-return observations.
- The candidate variance is `sum(S_g^2/(1-h_g))/N^2`, with `h_g=n_g/N`; candidate `nu=tr(K)^2/tr(K^2)` as in the spec. These are diagnostics until stochastic calibration and an untouched validation gate pass.
- F48 delivery-DP-fee/stale-mark accounting remains open; raw model outcomes are provisional. Existing opaque `benchmark_return` and `pre_tax_alpha` are not official benchmark evidence.
- Do not touch real data, lockbox, trial ledger, live-account details, or broker write paths.

## Review Focus

1. Duplicate signal identities in a run must refuse, not silently double weight: rely on the existing `SignalRunResult` duplicate-ID invariant and cite its existing test; do not forge invalid run objects merely to retest it.
2. A single busy block among empty blocks must refuse as `TOO_FEW_BLOCKS`, not count empty time blocks as degrees of freedom.
3. All-win/all-loss win indicators may refuse for `ZERO_VARIANCE` while differing raw returns stay available.
4. Reordering trades and moving entries within unchanged blocks must leave the candidate result unchanged.
5. A value too large to convert safely to float64, or a non-finite value, must refuse explicitly rather than contaminate arithmetic.

---

### Task 1: Pure typed inputs, source-axis checks, and descriptive results

**Files:** Create `icarus/engine/signalmetrics.py`; create `tests/unit/test_signalmetrics.py`; modify `icarus/common/config.py` only to correct its explanatory docstring/error wording (the rejection of `inference_enabled=True` must remain unchanged).

**Interfaces:** `MetricObservation(signal_id: SignalId, entry_session_index: int, holding_sessions: int, value: Decimal)`; `SourceSessionAxis(sessions: tuple[tuple[int, datetime], ...], study_origin_index: int)` with strictly increasing UTC datetimes and contiguous full-source session indices (weekends/holidays may skip calendar dates); the origin index must be present in the axis; `MetricRefusal` enum; `MetricDiagnostic(count: int, mean: float | None, moments: CandidateMoments | None, refusal: MetricRefusal | None)` (Task 1 defines the complete frozen/slotted `CandidateMoments` record specified in Task 2 but always sets `moments=None`; Task 2 populates it); `SignalDiagnostics(raw_return: MetricDiagnostic, win_rate: MetricDiagnostic, benchmark_excess: MetricDiagnostic, placebo: MetricDiagnostic, filled_count: int, skip_count: int, missing_count: int, longest_holding_sessions: int | None, block_length: int | None, study_origin_index: int, method_version: str)`; `summarize_signal_run(run: SignalRunResult, *, source_axis: SourceSessionAxis, settings: SignalTest) -> SignalDiagnostics`. An empty run has `longest_holding_sessions=None`, `block_length=None`, both raw/win `EMPTY_SAMPLE`, and separate benchmark/placebo refusals. `settings` must be an already validated `icarus.common.config.SignalTest`; compute `L=max(settings.block_min_sessions, settings.holding_period_block_multiplier*H)` rather than repeating fixed numbers in logic. Exact field names and invariant checks are pinned by tests before implementation.

- [ ] **Step 1: Write failing tests** for empty run, two trades with distinct IDs, negative/Boolean origin, entry before origin, index/timestamp mismatch, non-contiguous or unsorted axis, duplicate axis date, non-UTC datetime, trade outside axis, non-finite or float64-overflowing Decimal, and one trade with two exit fragments yielding one return observation. Map every decision, entry, exit price-source and recognition `(index, ts)` to the supplied canonical axis; include skip/missing decision coordinates, even though they do not enter the estimator. Include a forged exit recognition index/timestamp test showing it cannot change H/L. Use existing synthetic trade helpers or a local minimal builder; do not load a `Panel`. Malformed record construction or run/axis mismatch raises `TypeError`/`ValueError` (schema refusal); valid but statistically degenerate analysis returns a typed `MetricRefusal`. Duplicate signal IDs and invalid source coordinates are schema errors, not successful diagnostic results.
Example first red assertion (the test module supplies a synthetic `SignalRunResult` and axis):

```python
result = summarize_signal_run(empty_run, source_axis=axis, settings=signal_settings)
assert result.raw_return.refusal is MetricRefusal.EMPTY_SAMPLE
assert result.raw_return.count == 0
assert result.longest_holding_sessions is None
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_signalmetrics.py -q`; confirm the expected missing-module failure.
- [ ] **Step 3: Implement** frozen/slotted input, source-axis, and result types, require a validated `SignalTest` for the public adapter, correct the config's stale "Step 6 alone enables inference" wording, typed analytic refusals `EMPTY_SAMPLE`, `TOO_FEW_BLOCKS`, `ZERO_VARIANCE`, `INVALID_VARIANCE`, `INVALID_DF`, `MISSING_BENCHMARK`, `INDEFENSIBLE_PLACEBO_NULL`; malformed/duplicate/non-finite input and axis mismatches raise `TypeError`/`ValueError` before analysis; preserve descriptive mean/count even when variance inference refuses where meaningful. Validate exact `int` indices, UTC timestamps, axis correspondence, and `Decimal.is_finite()` before float conversion. Do not read the `benchmark_return` field; no general inference-bypass switch exists.
The Task-1 adapter constructs one observation as `MetricObservation(trade.signal_id, trade.entry_index, trade.holding_sessions, trade.net_return)` after mapping every coordinate to `source_axis`; for the win component use `Decimal(1) if trade.net_return > 0 else Decimal(0)`. For nonempty runs, derive `H=max(observation.holding_sessions for observation in observations)` and `L=max(settings.block_min_sessions, settings.holding_period_block_multiplier * H)`; assign `block_id=(entry_session_index-source_axis.study_origin_index)//L`.

- [ ] **Step 4: Run** the targeted tests, `uv run ruff check icarus/engine/signalmetrics.py tests/unit/test_signalmetrics.py`, `uv run ruff format --check icarus/engine/signalmetrics.py tests/unit/test_signalmetrics.py`, and `uv run mypy icarus tests`; keep this module side-effect free.
- [ ] **Step 5: Commit** the independently testable typed boundary after fresh simplification and code review; do not mark Step 6a complete. The test must show `inference_enabled` remains false and no CI/p-value field exists.

### Task 2: CR2 candidate variance, Satterthwaite degrees of freedom, and independent oracle

**Files:** Modify `icarus/engine/signalmetrics.py`; modify `tests/unit/test_signalmetrics.py`; create `tests/unit/test_signalmetrics_oracle.py`.

**Interfaces:** Private pure `_cr2_moments(values: tuple[float, ...], block_ids: tuple[int, ...]) -> CandidateMoments | MetricRefusal`. `CandidateMoments` (defined in Task 1) is frozen/slotted and holds `count`, ordered `(block_id, count)` pairs, `mean`, `sample_variance`, `cr2_variance`, `degrees_of_freedom`, `design_effect`, `effective_n_uncapped`, `effective_n_display`, and `effective_n_capped`; the public wrapper adds `H`, `L`, origin, and method version. Refusal precedence is `EMPTY_SAMPLE` → `TOO_FEW_BLOCKS` (fewer than two observations/occupied blocks) → `ZERO_VARIANCE` (zero sample/score variance) → `INVALID_VARIANCE` (non-finite/non-positive variance) → `INVALID_DF` (non-finite/non-positive df). Inputs that are malformed, duplicated, or axis-inconsistent raise before the kernel. No interval endpoints.

- [ ] **Step 1: Write failing hand tests:** three observations with values `(0,1,2)` and block counts `(1,2)` give mean `1`, CR2 variance `0.5`, df `1`, and effective N `2`; homogeneous values give `ZERO_VARIANCE`; one occupied block gives `TOO_FEW_BLOCKS` regardless of empty calendar blocks. Include unequal occupancy, reordering, unchanged block membership, fold origin, longest-hold L expansion, and separate return/win-rate effective N. Test finite Decimal-to-float overflow and nonzero Decimal underflow-to-zero as schema errors; finite-input summation/square overflow must return `INVALID_VARIANCE`. Derive win indicators from Decimal signs first.
Example hand oracle test:

```python
moments = _cr2_moments((0.0, 2.0, 4.0, 6.0), (0, 0, 1, 1))
assert isinstance(moments, CandidateMoments)
assert moments.mean == 3.0
assert moments.cr2_variance == 4.0
assert moments.degrees_of_freedom == 1.0
```

- [ ] **Step 2: Run** `uv run pytest tests/unit/test_signalmetrics.py tests/unit/test_signalmetrics_oracle.py -q` and record the intended red failures.
- [ ] **Step 3: Implement** the exact scalar spec formulas with guarded finite sums; use `math.fsum`, reject non-finite/non-positive V and df, and retain the block provenance. Do not silently cap df or create an interval.
Implement the compact computation independently of the test oracle: for each occupied block `g`, `n_g=len(values_g)`, `S_g=math.fsum(y-mean for y in values_g)`, and `h_g=n_g/N`. Use `V=math.fsum(S_g*S_g/(1-h_g) for g in blocks)/(N*N)`; construct `K_gh` from the design's exact formula, then `nu=trace(K)**2/trace(K@K)`. Guard arithmetic before creating `CandidateMoments`.

- [ ] **Step 4: Add independent oracle tests** that form `M=I−11ᵀ/N`, vectors `p_g=M c_g/[N sqrt(1−n_g/N)]`, and dense `Q=Σ_g p_g p_gᵀ`; compute oracle variance `yᵀQy` and df `tr(Q)²/tr(Q²)`. Hand-check `[0,2,4,6]` across two equal blocks (`V=4`, df `1`) and `[0,1,2,3,4,5]` across block sizes `(1,2,3)` (`V=1.5`, df `5/3`). Compare NumPy `default_rng(20260926)` vectors with occupancy `(1,2,3)` and `(2,2,2,5)` at `rel_tol=1e-12`, `abs_tol=1e-14`; these are formula-differential tests, not coverage calibration or floor evidence. Assert no random data is loaded from the repo.
- [ ] **Step 5: Run** `uv run pytest tests/unit/test_signalmetrics.py tests/unit/test_signalmetrics_oracle.py tests/unit/test_signaltest.py tests/unit/test_signal_simulator.py tests/unit/test_config.py -q`, `uv run pytest tests/unit/test_portfolio_characterization.py -q`, `uv run pytest tests/unit -q`, `uv run ruff check icarus tests`, `uv run ruff format --check icarus tests`, `uv run mypy icarus tests`, and `git diff --check`. No real-panel golden regression is run. Independently review the formula, refusal precedence, and non-vacuous tests; commit only after green checks.

## Deferred, explicitly not implemented by this plan

The stochastic coverage/refusal calibration matrix, frozen candidate floors, untouched validation, t-quantile interval endpoints, benchmark-match certificates, placebo pricing/p-values, F48 cost correction, Step 7 trial ledger, and Step 8 runner each require their own reviewed design/plan and may not be implied by this milestone. The next plan must freeze the numeric calibration matrix before generating its first stochastic replicate. `inference_enabled` stays false throughout.

## Verification and milestone report

Report the exact commit(s), test counts, static-check results, independent oracle result, remaining refusal/coverage work, and explicit statement that no statistical edge or benchmark alpha was established. Update `docs/STATE.md` and `docs/README.md` to point to this plan and accurately mark Step 6a.1 as partial. Preserve the untracked user-owned `AGENTS.md`.
