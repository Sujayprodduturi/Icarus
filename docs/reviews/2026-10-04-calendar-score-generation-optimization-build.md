# Calendar-score generation optimization — bounded builder evidence

2026-10-04. Implementation complete for independent source review; no supervised production preflight or sampled study performed.

Source SHA256: `58f483289f9175fec4f96153a1e7a377cc8c26e9d61a4a4e35fc8ef67b901f5e`.
Test SHA256: `e11f12da2737e4378758264f7a2a2868883233ad9f63f687040c83e848e5915c`.
Frozen protocol SHA256 remains `130569a78811e9ad4f9dcdb915410b3c350e137a78bc70974eb81ac4daf13b71`.

Changes: immutable bounded SHA-word peek with separate consumption; <=8192-date exact unsigned NumPy packing; unchanged scalar atom mapping used for custom/subclass sources, rejection and counter exhaustion. First/later progress callbacks preserve consumed-word state. Output allocation refuses above existing16MiB buffer cap. Source manifest includes installed NumPy version. Evaluator, law, evidence, score, budgets and protocol unchanged.

TDD records retained locally under `var/verification/2026-10-04/optimization/`:
- `red.log`:7 expected missing buffer/digest/version failures,62 passed.
- `red-output-cap.log`:new allocation guard test failed before guard implementation.
- `green.log`:74 focused tests passed in7.03s; existing42 tests retained.
- Targeted strict mypy:2 source files clean.
- Ruff check and format:clean using --no-cache. Default Ruff cache produced a package-cache panic; no-cache avoids that runtime issue.

Coverage includes all ten full frozen zero-key payload hashes plus independent original SHA-stream scalar bytes/count/next-word parity; two other fixed roots/replicates over P4/P7/L1;8192-date boundary; partial lanes and immutable peek ownership; atomic overflow refusal and partial failed-row counts; actual trusted batch rejections crossing row/batch boundaries;1024-rejection refusal; unsigned limit-1/limit/max boundaries; custom subclass scalar routing; callback counts and exceptions at0/65536; manifest NumPy identity.

An UNSUPERVISED test-domain generation-only diagnostic generated231492 bytes in0.2820363999926485s (`diagnostic.log`). This omits evaluation, disk I/O, replay and monitoring and is not a feasibility or resource-eligibility result. Initial diagnostic command had a quoting error, corrected by the retained diagnostic.py file. No raw output saved.

Root owns broader validation, independent ordered review, supervised feasibility, compact final artifacts and STATE/HANDOVER updates. No commits or pushes by builder.

## Primary final verification and governed timing

Root independently inspected source/test changes and reproduced the frozen hashes. Ordered [simplicity and engineering review](2026-10-04-calendar-score-generation-optimization-code-review.md) approves this source for deterministic measurement. Related calendar/law/evidence/score/compact/geometry/statistics/uncertainty and synthetic portfolio-golden selection: **324 passed in14.09s**. Global configured-strict mypy:168 sources clean; Ruff check --no-cache clean; Ruff format --check --no-cache:168 files already formatted. Default-cache format failed with a package-root cache warning; the no-cache run passed. No fresh full-suite, datastore integration or official-platform certification is claimed.

Fresh supervised full-workload command: `uv run python -m scripts.research.signal_calendar_score_study --preflight --evidence-root C:/ICARUS/var/verification/2026-10-04/calendar-score-study-preflight-optimized`, exit0 and terminal COMPLETE. Manifest `ca9fc3380420a1a50dadfb98a1676e9f9a9e19593a9df52bf75fa164d5f1c0fc`; receipt `d30d3ca07c3e88d8ddcd09f23e476b26e7a3b65322e876ed744a028e94077c31`.

| Measured/projection | Baseline | Optimized | Registered limit |
|---|---:|---:|---:|
| One full set generated/evaluated/saved |1.7293323s|0.5401904s|validation-derived0.6591796875s|
| One full set regenerated/replayed |1.7488646s|0.5129779s|validation-derived0.6591796875s|
| Development, twofold projection |7.87h|2.46h|6h|
| Development verification, twofold projection |7.96h|2.33h|12h|
| Validation, twofold projection |31.48h|9.83h|12h|
| Validation verification, twofold projection |31.84h|9.34h|12h|

Eligibility=true for this deterministic preflight; no budget/statistical threshold changed. Set generation is about3.20x faster, verification about3.41x. These are one-set local measurements and extrapolations, not a sustained32768-set completion promise. The32MiB probe completed end-to-end write4.1435328s/read0.0343574s; this includes probe generation/hash/fsync and is not physical disk bandwidth. Worker self-sampled RSS40,054,784 bytes; parent observed40,144,896 bytes. Transient peaks between<=0.25s samples and Windows power-loss equivalence remain unproved.

Root's separate literal-SHA/unbiased-map plus integer-prefix trade oracle rebuilt all10 full histories/28 results/1,388,952 consumed words. Every index row, byte hash, total, confidence endpoint, reason and precision output matches the prior committed baseline exactly. Full231492-byte payload SHA256 `816a0ae0a31c0cf97bf3fd1aa309b063551951305b4dfaac78370db22759afc2`. Source/manifest/receipt/terminal hashes and all runtime projections were independently checked; primary verification receipt retained. Independent saved-file reviewer verification and D44 cleanup are recorded below when complete.

Full sampled worker, saved-path verifier, development/validation authority, root sealing and verify-then-cleanup lifecycle remain OPEN/UNBUILT. Experimental draws=0; no method adoption, product inference or real-market evaluation. Goal/law/evidence/score/protocol bytes unchanged. Phase1/Task3a/M1-M4/F48 remain OPEN.

## Independent saved verification and D44 cleanup

Independent reviewer reproduced all10 histories/28 totals/truths/endpoints and every source/runtime/receipt/probe identity without production calculation imports; durable reviewer receipt passed. Root inspected that receipt and review, then executed the fixed-new-root cleanup script after matching both approvals and all path hashes. Only231492-byte `preflight-payload.bin` was deleted at2026-10-04T11:37:12.978896+00:00; its full hash and filesystem identity were durably recorded before deletion. Probe had already been verified and deleted. Later raw replay is unavailable; completed checks are dated evidence, not continuing file availability. Sources, compact results, claims/terminal, both verification records and cleanup intent/receipt remain in [committed compact evidence](2026-10-04-calendar-score-generation-optimization-preflight.json). No recursive cleanup, real data or old counted-study recreation.

Before commit, root compared normal and ignore-cr-at-eol numstats, checked whitespace, exact approved source/test hashes, unchanged goal/helper/protocol hashes and reviewer approval. User-owned untracked AGENTS.md is preserved. D26 requires normal push of reviewed committed dev changes; the existing ordinary CI and non-reserved native surrogate resource workflow may run automatically. This is not official evidence or a manually dispatched experimental study. Post-commit deliberate defect checks/restoration are recorded in the final provenance addendum.

## Final commit and restored defect checks

Implementation/evidence commit `3e99177`. After commit, primary deliberately planted two bounded faults separately: logical consumption stopped updating its count; custom subclasses were improperly trusted by the batch route. Each selected regression failed as expected (exit1), so both defects were caught. Before mutation an exclusive immutable byte snapshot was retained; finally restored exact approved source SHA58f483289f9175fec4f96153a1e7a377cc8c26e9d61a4a4e35fc8ef67b901f5e. Fresh restored calendar/synthetic-golden selection:324 passed in14.86s. Working tree then contained only user-owned untracked AGENTS.md. Local scripts/logs are under ignored var/verification/2026-10-04/optimization; this committed addendum is durable evidence. Documentation-only provenance addendum is exempt from another source-review/mutation pass.

Current next milestone is one reviewed full sampled-lifecycle design, not another generator optimization and not a real-market trial. Required independent verification and D44 cleanup are complete for this deterministic checkpoint; all later study/lifecycle gates remain binding.
