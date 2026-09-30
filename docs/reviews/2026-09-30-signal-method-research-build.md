# Signal uncertainty research build and Windows screen

Date: 2026-09-30. Scope: operator-approved D32 isolated mathematical research, Phase 1 Task 3a. Outcome: implementation verified; fixed-b development candidate rejected as a general uncertainty method. No product adoption or official phase verdict.

## What was built

The pure typed estimator in `scripts/research/signal_uncertainty.py` keeps trade-weighted means and the full original calendar-block grid, including gaps. Bartlett bandwidth is floor(G/4), the published fixed-b 97.5% critical polynomial is used without an extra finite multiplier, and invalid/nonfinite/zero-variance inputs refuse. The candidate receives neither known targets nor RNG/DGP labels. The synthetic-only comparison in `scripts/research/signal_method_probe.py` pairs raw returns, raw-derived wins and benchmark excess on exactly the same synthetic trades. It records refusals, both tails, joint/emission coverage, widths, bias and known-effect controls; it has no broker, real-panel, promotion or official completion authority.

The parent preregisters source/environment/protocol before spawning; same-directory atomic checkpoints retain the last prefix; errors/timeouts retain attempts and kill/join the worker. The current Windows venv launches its real interpreter directly using CPython's own workaround, preserving the parent-PID barrier and supervisor ownership. [Primary CPython source](https://github.com/python/cpython/blob/v3.12.10/Lib/multiprocessing/popen_spawn_win32.py#L55-L60), checked 2026-09-30, and the installed matching source were inspected. This provides no Linux address-space or power-loss durability equivalence.

## Verification and independent review

- TDD estimator: 27 RED before implementation, then GREEN; two additional constant-decimal regressions caught tiny spurious variance from rounded fsum/N. Exact identical outcomes now refuse ZERO_VARIANCE. Independent dense-kernel oracle, geometry/gaps/unequal counts, invariances and refusal tests pass: 29 estimator tests.
- Initial build regression: 397 passed in 35.29 seconds, covering research, existing signal simulator/statistics/oracle/calibration helpers, fill/cost/tax and synthetic portfolio characterization. Log: `var/verification/2026-09-30/method-design/build-regression.log`. This is a focused regression, not a full-suite or production golden-backtest claim.
- Windows launcher regression: RED missing helper, then real subprocess identity/environment test. Final focused group: 41 passed in 1.82 seconds; mypy 143 sources clean, Ruff checks clean, all143 files already formatted. Ruff used --no-cache after an unrelated corrupt local Ruff cache. Final small test cleanup kills/joins a timed-out test child.
- Independent medium-effort numerical reviewer approved formula, pairing/source axes, control addresses, count partitions and CP families. Independent medium-effort safety reviewer completed ponytail and engineering review: approved atomic checkpoint/provenance/failure cleanup, then the direct interpreter fix. Primary re-read sources and independently recomputed saved rates; reviewers did not supply a substitute for primary verification.
- Post-commit mutation check caught all three actual defects: removing constant-outcome protection, replacing checkpoints in place, and reintroducing the Windows redirector. Each targeted regression failed for the intended assertion; exact original bytes were restored in finally blocks. Restoration group: 41 passed in1.67 seconds. Log: `var/verification/2026-09-30/method-design/mutation-check.log`.
- All six protected estimator/reference/manifest/digest/goal/lock paths have no diff from the preceding source. No frozen seed, manifest, threshold or inference setting changed.

## Attempt history and exact evidence

Command: `uv run python -m scripts.research.signal_method_probe`, run locally on the current Windows PC. Each invocation uses its own exclusive scratch directory; neither attempt is hidden or overwritten.

1. Source `bc92743867bd6f0de0601bfc5fee78f422bdfa95`, attempt `var/research/signal_uncertainty/9c2870d9-4d2d-4772-9a00-ca6327ebd3fe`: startup ERROR before RNG/data generation. Seed and source hashes matched, but the Windows venv redirector created an intermediary and getppid did not equal the recorded supervisor. Preregistration, STARTED/ERROR ledger and traceback retained. Root reproduced parent23688 vs child parent12900; direct base launch reproduced parent18724 and child/Popen PID19288 with the expected venv and NumPy.
2. Repaired exact source `7cbd372dd71fbdb641a40cb1418a406814fb2bf8`, attempt `var/research/signal_uncertainty/815b499d-0ee7-4604-babc-c652b63542d1`: COMPLETE, parent process exit0 in92.00 seconds, worker89.234 seconds, below the300-second development deadline. Seed2026093012; 45 existing artificial profiles plus3 Gaussian controls, 1024 replicates each. Two methods x3 metrics yield288 summaries and294912 recorded metric evaluations. Result protocol equals preregistration; source hashes matched current bytes before the completion documentation update. No in-progress residue remains.

Environment: Python3.12.10, NumPy2.1.3, SciPy1.14.1, Windows-11-10.0.26200-SP0. Protocol records full source SHA, author/version, parentPID and protected/research/design/implementation/lock byte hashes.

| Retained file in completed attempt | SHA-256 |
|---|---|
| preregister.json | 26c06c8177dd5c59002698b76879e42a67e8a83496d03b5eeb6bda2326b2bfc4 |
| result.json | fdf2a73e03023d7ec990a821534d00d37630f1570df541ccd96dd4155382dd84 |
| ledger.jsonl | 1dd088a82cf97eccea9a00a35cf97e151d282b606dcc71df7faf7a3ac0f01130 |
| worker.log | 3dccc8e5909466b9df6ace2925c4bc07213459fb64cb8ad7c80bfdf6c6b5fcbf |

The committed [all-profile summary CSV](2026-09-30-signal-method-screen.csv) preserves every profile/method/metric count, refusal, five descriptive CP bounds, widths and bias. SHA-256: ddfb79b017fb45c92069e8e31cfd55dc919cb368143497884610eb92df09153c. Raw scratch files stay local/ignored. This CSV is derived evidence, not an official calibration artifact.

## What the comparison revealed

Coverage means how often an intended95% interval contains the known true answer. Each row below uses the same1024 generated samples for both methods; these displayed rows emitted1024 intervals each. Profiles are synthetic situations, not Icarus strategies.

| Situation / metric | Original covered /1024 | Candidate covered /1024 | Original median width | Candidate median width |
|---|---:|---:|---:|---:|
| 28 serial dependence, raw mean | 802 (78.32%) | 913 (89.16%) | .00535114 | .00796403 |
| 28 serial dependence, win rate | 801 (78.22%) | 912 (89.06%) | .263532 | .394563 |
| 30 rare magnitude, raw mean | 835 (81.54%) | 839 (81.93%) | .00581272 | .00594481 |
| 1 independent rare-win, win rate | 949 (92.68%) | 952 (92.97%) | .0616073 | .0678767 |
| 34 regime mixture, raw mean | 1024 (100%) | 1024 (100%) | .00618371 | .0146100 |

Serial coverage improves substantially but remains inadequate. Rare-large outcomes barely improve. Tail imbalance persists: candidate cell30 raw misses180 below the lower endpoint and5 above the upper endpoint. Rare-win/skewed cells9 and12 also remain deficient (candidate raw875/1024 and881/1024). No averaging across profiles can erase these failures. Independently computed descriptive simultaneous upper coverage bounds for candidate raw cell28=.9263637490 and cell30=.8639339736, both below .95 even with alpha=.05/1350. These are rejection witnesses from a development prefix, not a full frozen-gate verdict.

Both methods pass the predeclared vacuity sentinel (NON_INFORMATIVE=false). In independent Gaussian controls, candidate raw coverage is982/1024,983/1024,969/1024; median widths .00638785/.00638824/.00628521. It detects the strong positive/negative raw effects in1024/1024 cases each. For the corresponding win effects, correct-direction exclusion is1020/1024 and1018/1024; a null control excludes .5 in47/1024. These are descriptive sensitivity measurements, not a newly invented power gate. Regime profile34 widens considerably and loses sensitivity to small excess effects; width tradeoffs are visible, not accepted by coverage alone.

Primary and independent reviewer verified all288 count partitions and all1440 CP bounds using SciPy beta quantiles with the predeclared families1350/90, exact profileIDs, protocol equality, source hashes, terminal ledger and controls. Neither recomputation drew data or retried the screen. Saved results contain aggregate counts/quantiles, not individual intervals/outcomes: verification checked summary consistency and exact formula/rate recomputation, not an independent replay of empirical coverage numerators or width samples.

## Current decision and next work

The research build is complete; this development candidate is not accepted for product use. Inference remains disabled. The next statistical task is a reviewed alternative design addressing rare/discrete/skewed outcomes as well as serial dependence, including explicit insufficiency/refusal behavior and width/effect sensitivity criteria before a new confirmation draw. Simply widening covariance bands or accepting a bootstrap name without testing rare-event absence is not evidence of repair. Do not tune this candidate against exposed samples and present them as confirmation.

Original protected method and frozen protocol remain unchanged; both official reserved streams remain untouched. Current-PC research supplies no official Windows resource/durable-claim proof. Step6b minimum-data requirements, trial-ledger/benchmark matching and the real-data signal runner remain later work. No actual strategy-performance conclusion, lockbox use, inference enablement or broker/live path follows from this screen.

Operator explanation preferences are recorded as standing guidance in OPERATOR.md section2: purpose and roadmap first, plain English, concrete examples before jargon/formulas, built/tested/proposed distinctions, numerical meaning and clear next action. D32 records the user's build/style authorization.
