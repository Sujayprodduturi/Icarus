# Signal uncertainty research implementation plan

> **For agentic workers:** Use test-driven development and independent numerical/safety review; execute the two tasks below sequentially at their integration boundary.

**Goal:** Build and run the operator-approved isolated mathematical comparison on the current Windows PC.
**Architecture:** Pure typed estimator in `scripts/research/signal_uncertainty.py`; synthetic-only experiment, ledger and bounded supervisor in `scripts/research/signal_method_probe.py`. Existing generator/CR2 are references; no product imports from research.
**Tech stack:** Python 3.12, existing NumPy/SciPy, uv, pytest, Ruff, mypy.
**Spec:** `2026-09-30-signal-method-research-design.md`.
**Authorization:** Operator explicitly asked on 2026-09-30 to build the uncertainty mathematics after the plain-English explanation. This covers this concrete research scope and Windows screen; no additional approval requested for these steps.

## Global constraints
- No original estimator/harness/manifest/config edits; no reserved seeds, real panel, broker or official output.
- Candidate Bartlett M=floor(G/4), correct 97.5% polynomial, no finite multiplier; retain canonical temporal distances and trade-weighted mean.
- Screen seed2026093012, all45 x1024 profiles, three Gaussian controls x1024, three paired metrics, one candidate vsCR2. Descriptive CP families1350/90; no official pass/floor.
- <=4096 grid blocks, bounded256-row stream cache; 300-second supervised deadline, one foreground experiment.

## Review focus
Temporal gaps/unequal counts; off-by-one kernel bandwidth; synthetic pairing/missingness; incomplete attempt persistence; forbidden seed/path refused before draw/write. Tests and reviews address each.

## Task 1: Pure research mathematics
Files: `scripts/research/signal_uncertainty.py`, `tests/unit/test_signal_uncertainty_research.py`.
Interface: `estimate(values, block_ids, *, first_block, last_block)` returns a typed estimate or typed refusal; the estimator receives no targets/family/seed. Estimate records mean, variance, critical, untrimmed bounds and original geometry. Refusal includes empty, invalid, nonfinite, zero variance, too few occupied/grid and too-large-grid.
- [x] Write failing tests for independent dense Bartlett quadratic form, critical2.72003125, unequal weights, original gaps, zero/overflow/nonfinite/bad IDs and geometry bounds.
- [x] Run focused pytest and confirm failure before implementation.
- [x] Implement score sums and lag formula; verify against independent oracle and refusal tests.
- [x] Independent numerical review; focused Ruff/mypy.

## Task 2: Synthetic experiment and persistence
Files: `scripts/research/signal_method_probe.py`, `tests/unit/test_signal_method_probe_research.py`.
Interfaces: validate unique synthetic trade records/axes/pairing; metric adapter calls pure estimator/reference without truth; evaluator accumulates emitted/refused/coverage/tails/joint/width/bias/zero-exclusion. Main process exclusively creates scratch run directory and preregistration/ledger before spawning bounded worker. Process timeout retains incomplete output and records failure; no retries inside a run.
- [x] Write failing tests for reserved-seed/path barriers, duplicate IDs/bad axis/pairing, outcome-derived wins, candidate-only target isolation, partition counts, full-range/unbounded stubs, exclusive attempt collision and supervisor failure handling.
- [x] Confirm red, then implement minimal typed adapters, exact span/control addresses and descriptive summaries.
- [x] Run focused tests, estimator/parity/simulator characterization, Ruff/mypy and independent safety/numerical/code review.
- [ ] Freeze exact source/protocol/environment hashes in preregistration; run authorized full screen once on Windows under300s supervisor.
- [ ] Independently recompute saved summaries/check logs; record failed attempts rather than hide/overwrite them.
- [ ] Update STATE/HANDOVER/TASKS/audit and operator explanation style; commit/push verified work. Report statistical failures plainly; completion is not method acceptance.
