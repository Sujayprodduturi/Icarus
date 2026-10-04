# Verifier optimization iteration 2 build

Approved plan SHA256: b2d913f0ec455fd5c612c703e835b95beaa66a38aa3a0e226d72c4aa685d4387.

The manifest now performs one fresh package-version lookup for each of psutil and NumPy on every call. Only PackageNotFoundError omits a library; other failures propagate. Source rehashes and existing checkpoints remain. The unused distribution helper was removed. SOURCE_PATHS additionally binds the approved iteration2 plan.

The native reference SHA loop binds the per-stream copy method and list append locally, hashes the unchanged eight-byte counter, and joins all32-byte digests in the original order. The unused per-block helper was removed. Existing overflow checks, buffered ownership, public-prefix mutation and custom digest hook fallback remain.

All diagnostic and test logs below are retained in var/verification/2026-10-04/calendar-score-verify/.

The declared five alternating-order paired full10 in-memory reconstruction diagnostic compared original versus local copy/list append. Every path had exact payload-byte and consumed-word equality on every trial. Baseline median0.213128599993s; candidate median0.196378199995s. Median paired fractional improvement7.296392229percent exceeds the approved5percent adoption threshold. This diagnostic excludes import/setup and supplies no workload feasibility or study authority. Evidence: iteration2-declared-paired.py and iteration2-declared-paired-corrected.log. The initial print-only diagnostic failed on an empty unused alternative timing list; iteration2-declared-paired.log preserves that error. The corrected diagnostic reran five declared pairs; earlier diagnostic timings were not used for adoption. Both scripts and logs are retained.

TDD RED: iteration2-red.log records3 meaningful failures and1 pass. Failures expose4 metadata calls instead of2, an extra lookup after another package is missing, and17 hash copy lookups instead of1. The unexpected metadata failure already propagated correctly. The native test independently hashes literal counters255 through271 and checks buffered lanes and consumption; existing full framing, mutation, hook, rejection and overflow tests remain.

GREEN: iteration2-green.log records151 focused study/verifier tests passing in9.61s. Targeted strict mypy reports no issues in2 source files. Ruff check and format check pass for all4 owned source/test files. Logs: iteration2-mypy.log, iteration2-ruff.log and iteration2-format.log. Initial cached Ruff formatting panicked on a corrupt package-root cache; --no-cache succeeded without deleting shared cache.

Frozen SHA256 values:

- scripts/research/signal_calendar_score_study.py: 6965082cadcb555869d00da72ef29c41d23e9bb89b803c3bcf9adc64de04e18f
- scripts/research/signal_calendar_score_verify.py: 4f13444a01740702656fdec630ab2814bc9e2f15e134a1c2e2f38bbecd5ed23e
- tests/unit/test_signal_calendar_score_study_research.py: 090e694e76ce6bcab828372de0bff0d53730004ade012a94be6c188d59790442
- tests/unit/test_signal_calendar_score_verify_research.py: fc77b8ee8dca2ddd521f39bb2ccb7ed8ce3b82ffb9b2cac13c51e5a0d9152c11

The frozen statistical protocol remains130569a78811e9ad4f9dcdb915410b3c350e137a78bc70974eb81ac4daf13b71. No actual supervised benchmark, sampled stream, broad regression, commit, push or raw cleanup was run by the builder. Root owns independent review, remaining required checks and governed three-run qualification. Qualification remains pending; iteration1 failed evidence remains retained.


## Root global gates and test-only correction

416 related calendar/portfolio-synthetic-golden/audit tests passed16.90s. The first global strict type check caught4 new test import/export typing errors, preserved in mypy-iteration2.log. Builder corrected only tests to explicitly import importlib.metadata; affected4 tests pass0.26s. Final study-test SHA is a852b580e09417d8741843eaba8bc93de9158aaee41e66cd8ee99c3158fe580e. Production sources are unchanged. Root final global strict170-source mypy, Ruff and316-file formatting checks pass; reviewer verified the final test-only change and released the three cold benchmarks.

## Final cold measurements and search decision

All3 actual supervised cold runs FAIL unchanged12h:0.6904660/0.6796444/0.6820135s, worst45250.379776s=12.5696h. All10 paths/28 metrics per run independently checked by primary and reviewer; source/runtime/claim/index/report/terminal/receipt and timing projections matched. Fixed-root ancestor/regular-file/hash/identity guards, durable intent, immediate recheck, raw-only unlink and absence receipt completed for all3. Compact evidence retains failures/results/receipts/cleanup. No raw replay is now available.

Native_SHA2 five paired diagnostics gained only1.09percent with unstable ordering; immutable-text metadata parsing gained22.41ms across9 manifests, below31.29ms worst gap with added contracts. Both rejected; retained alternative-diagnostics JSON. Low-risk search ends at best tested source, not a claimed global optimum. Runtime issue R3 remains OPEN; a separately versioned14h operational proposal is the next reviewed task. Effective budget is still12h, all statistical criteria and no-draw boundaries unchanged. Prior a982ff6 CI37214178688 and native surrogate37214178589 independently refreshed as SUCCESS; these are prior-source results, not current optimization CI.
