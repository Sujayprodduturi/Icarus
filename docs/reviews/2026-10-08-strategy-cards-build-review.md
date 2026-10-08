# Strategy candidate build review - 2026-10-08

SCOPED PASS for two approved candidate definitions and artificial mechanics checks at source commit `a14384c`. This establishes implementation, not profitable strategies, market-data eligibility or statistical-method adoption.

The catalogue now has one unchanged buy-and-hold control and four signal specifications across three families. New files implement twelve-minus-one momentum (252/21 lookback, top-ten cohort, three-ATR stop, 63-bar holding limit) and an uptrend pullback (close above SMA200, at least three falling closes, IBS below 0.2, two-ATR stop, five-bar holding limit). Parameters are project-owned pre-registered hypotheses. Momentum horizons remain one correlated family. The wider five-family/six-specification proposal still needs an opposite-channel Donchian exit and a scheduled low-volatility rebalance consumer.

Independent plan, safety amendment and final implementation reviews ran simplicity before engineering. Parent independently checked both files against the reviewed card models and reproduced the overflow defect with consistent, positive finite artificial OHLC prices. The shared cross-sectional eligibility predicate now excludes NaN and infinity and recomputes the unchanged minimum participant count. It does not certify all arithmetic outputs or market inputs. No score clipping or risk/gate change was introduced.

Builder: 24 candidate checks and 472 affected regressions passed. Parent: 72 focused, exit, catalogue and golden/metric-sheet checks passed; strict mypy over 198 sources, global Ruff lint/376-file formatting and diff checks passed. Independent reviewer reproduced four key behaviors. Four postcommit source mutations were caught as behavioral assertion failures; exact restoration of every tracked file was verified and the restored candidate/cross-sectional suite passed 56 tests. Compact proof records hashes, exact commit, receipts and root reproductions.

Checks cover the skipped-month percentage formula and price-scale invariance, causal signals, finite-score eligibility/floor, average cutoff ties, strict pullback boundaries, actual next-bar trades, no pyramiding, time exits and re-entry with new costs. STOP equality triggers a protective exit; a resting LIMIT still requires strict trade-through. The original invented demo prices are unchanged. Its guard explicitly names all five cards: four produce trades, the reversal correctly emits none on that fixture, and a separate constructed pullback fixture exercises its positive trade path. None is evidence of profitability.

The previous ledger source at `175f3db` passed hosted full CI (2,881 passed/four skipped) and resource checks. That result does not establish the new candidate source's full-suite status; final-push hosted checks remain pending. No second 32-minute local full suite was run for this bounded change.

Existing three strategy YAMLs, goal/risk settings, portfolio logic, fill model, DSL parser and demo generator bytes remained unchanged. No actual panel or operator ledger was evaluated, no activation/migration occurred, and inference remains disabled. Existing consumed-study artifacts and lockbox are untouched.

Next: reviewed per-symbol/IST-day delivery-fee accounting for real executed exits, with no delivery charge on a residual stale mark (open F48); then missing strategy consumers and source/time/benchmark/applicability prerequisites. D41 still stops before real-market evaluation. No winner quota, threshold reduction or HFT/shorting expansion is authorized.

[Exact cards](../strategy-research/2026-10-08-exact-first-batch-cards.md) - [Compact proof](2026-10-08-strategy-cards-build-proof.json).

## Independent final review

2026-10-08 — Ordered simplicity then engineering review of two new YAMLs, shared eligibility predicate, candidate tests and explicit catalogue-demo guard; frozen files independently hashed against build/red-green.md.
GO for bounded artificial-only integration/commit; no runtime or documentation blocker remains. Shared card check #10 now matches the approved explicit five-name demo guard; invented prices remain unchanged and reversal is correctly expected to emit zero there.
Simplicity: declarative YAMLs use existing primitives/exit consumers; one shared np.isfinite predicate is the smallest consistent safety repair. No new simulator, portfolio architecture or statistical threshold is introduced.
Momentum entry/rank uses roc_skip(252,21), top cohort10/minimum20, ATR3x/63-bar exit; reversal uses close>SMA200, down_streak>2, IBS<0.2, descending streak preference, ATR2x/5-bar exit. Existing three strategy bytes remain pinned and untouched.
Actual tests verify causal/scale-free arithmetic, average-rank cutoff cohorts of 11 and 9, strict reversal boundaries, zero-range NaN, overflow exclusion and 20-to-19 whole-date refusal, next-bar entry, 63-bar exit/reentry with ALREADY_HELD and repeated costs, and the positive five-bar reversal fixture.
Fill checks correctly distinguish STOP equality trigger from RESTING_LIMIT strict trade-through and prove entry-session protective exits; no same-bar signal execution or touch-as-limit-fill assumption is introduced.
Catalogue guard names all five cards explicitly, requires zero reversal signals/trades on its unchanged IBS geometry, exact signal outcome accounting, no benchmark alpha/after-tax promotion metric, and refusal of artifact-root reuse.
Builder evidence: meaningful RED for infinity eligibility and absent YAML, then 24 candidate tests PASS/1.44s, 472 affected mechanics/cost/tax/demo tests PASS/22.26s, targeted lint/type/diff checks clean. Reviewer inspected behavior/code/evidence rather than duplicating a concurrent heavy job.
Frozen hashes match independently: helper c7e9067a; momentum 814023ec; reversal 3c328179; candidate tests f6119004; demo tests bb2da107 (full SHA256 values remain in build evidence).
Parent independently reports 72 focused tests PASS/5.12s, explicit mypy198 PASS, global lint PASS, format376 PASS and diff clean; reviewer independently reran overflow (+/- endpoint), momentum time/reentry and positive pullback nodes: 4 PASS/1.30s. Prepared four postcommit mutants still need meaningful detection, exact restoration and passing restored checks before task completion.
GO is mechanics-only: no profitability/win-rate claim, fees-fixed claim, accepted inference method, real-data readiness or registry/ledger activation. F48, source/time/benchmark/applicability dependencies and D41 remain held.
No runtime/shared-doc edit, actual market or ledger read, network/broker access or strategy study was performed by this reviewer; the independent four synthetic checks ran only after parent released the test-idle window.
