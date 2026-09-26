# Step 6a.2 Task 1 — manifest/preflight review

**Decision (2026-09-26): approved for Task 2 deterministic implementation at `eb90def`.** This is not approval for a calibration run, validation run, product interval, accepted floor, or real-data inference.

The protocol plan was committed at `84e4285`. Task 1 committed the canonical manifest, detached digest, development-only SciPy/psutil dependencies, deterministic geometry and acceptance preflight, and a locked validation-selection CLI at `fbaa3f7`. Independent and Astra review found that its first preflight trusted some self-consistent but wrong manifest claims. The follow-up `eb90def` added fail-closed checks for fixed H→L, complete dynamic-H outcomes/L, and independently recomputed analytic targets. Both reviewers approved the repaired boundary.

Evidence: unchanged manifest SHA-256 `0ffd312b3a3bfd03d465bc1ce5d655bff2055861a99d1cf4c17287b4a450e3e5`; 45 calibration and 37 distinct validation cells; exact cutoff triples 9396/9582/327 and 18734/19114/697; deterministic tamper probes for missing H=21, altered raw target, and mismatched fixed H now raise `ManifestError`. The final targeted suite passed 23 tests; the full unit suite passed 1,269; Ruff, format, mypy, and post-commit deterministic preflight passed. No RNG draw, validation observation, real panel, lockbox, or broker path was used.

**Next gate:** Task 2 implements the synthetic generator and interval evaluator under the frozen manifest. Independent parity/statistical review must precede any full stochastic calibration stream. `validate-selection` deliberately remains fail-closed until Task 3 binds its hash to immutable calibration-result bytes.
