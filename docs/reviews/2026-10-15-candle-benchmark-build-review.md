# Candle benchmark build review — 2026-10-15

Status: **independent implementation review GO; full regression completion pending**. Synthetic scope only; actual data qualification and run authorization remain false.

## Ordered simplicity review

Root applied `ponytail-review` to the eight runtime/script files and five test files changed from `e71bef748d181fbaff57ce41734502022c1c598d`. The change reuses the existing guarded runner, shared timed event loop, strategy primitive visitor and seven artifact roles. No additional runner, dependency or general schema framework was introduced. Explicit immutable contracts and refusal checks are required by the approved design.

Lean already. Ship.

This is a simplicity disposition only. It precedes, and does not replace, independent correctness/security review or completion verification.

## Frozen evidence

Runtime and test hashes: ignored `var/verification/2026-10-15/candle-replay-build/root-frozen-files.json`. Root reproduced clean `git diff --check` and identical normal versus CR-ignored diff counts. Builder's frozen public CLI log records two passing strict/descriptive 21-plan tests; targeted acceptance records seven passes. Nonempty legacy strict fixture digest is pinned as `032c89638dcd3679fe9d7cbf84b2d8d1910dce5b95f253ea4d940bbf0de12c90`.

These results are invented-data software checks, not downloaded-data strategy results. Full regressions, independent review and any resulting repairs remain pending.

## Reviewed repairs, frozen v2

The first independent review found three P2 defects: stale marks accepted as executed exits, a permissive candle schema, and missing interpretation fields. Root verified each against source and the independent probe. The builder retained failing tests before repairing them, added the independent primitive/rebalance acceptance cases to tracked tests, and froze v2 without a commit. Root's repeat simplicity pass found no additional framework or actionable cuts.

V2 manifest SHA-256 is `f42b44c6e8559049c6ba7563f0e5afcf8d7f914f27b94d3958e0fbd34aa4586c`; v1 is preserved. Builder reports 21 repair checks, 142 focused regressions and 18 final CLI/repair acceptance checks passing. Root independently recomputed the rational cash-flow example: benchmark `[-1/22,3/20]`, stock `2/25`, excess `[-7/100,69/550]`. Final independent re-review, full regressions, global static checks, commit and any postcommit fault proof are still pending.

## Final review and root checks

The independent v2 re-review is GO with zero open findings on both standards and specification axes. Thirty independent acceptance tests pass; the original malformed-candle and stale-mark probes now refuse. Strict fixture digest and exact signed arithmetic are unchanged. See [the final code review](2026-10-15-candle-benchmark-code-review.md).

Root's repository-wide mypy initially found seven test typing errors missed by the narrower builder check. Three runtime-neutral fixture corrections use a typed cast for deliberately malformed input, explicit four OHLC arguments, and an import from the registry's defining module. The 93 tests in those three modules pass again. Global mypy now passes all 196 source files; Ruff lint and formatting pass all 457 discovered files. The original full regression process had already collected tests before these typing corrections; its runtime implementation bytes remain identical to reviewed v2. Its terminal result is still pending.

Frozen v3 records only these three test-file changes; all eight runtime/script hashes remain identical to independently reviewed v2. Manifest SHA-256: `db466a8d1edbfbcf9ef35470236042df7bb18c53059713c38f83dac17dfef1e3`. V1 and v2 remain preserved. No postcommit defect reintroduction has been applied; the four-case harness is prepared but held until a commit exists and the full regression process has ended.
