# Real-data simulator software-readiness build review — 2026-10-14

**Verdict: GO — LOCAL SOFTWARE VERIFIED.** The reviewed
candidate is sources `68b5` plus `eb65474`, with latest test-only proof commit `3dcdcf5`.
It implements immutable local bundle capture,
strict external trust and qualification bindings, causal calendar/PIT/daily/M15 assembly,
source-specific benchmark matching, and guarded counted evaluation of all seven existing
cards in signal mode and the two configured portfolio capital modes. Independent ordered
simplicity and engineering source review is GO.

## Scoped evidence

- Root's related accounting and simulator regression gate passed **616 tests with two skips in 63.19 seconds**.
- The supplemental guard gate passed **97 tests in 6.37 seconds**.
- The unified invented-file CLI proof passed **four tests in 32.88 seconds**. It used the
  unchanged `goal.yaml`, obtained all **21 reservations before price decoding**, and retained
  all **21 terminal results** across seven cards and three mode/capital identities.
- The pre-proof strict mypy gate passed over **97 source files** and global Ruff covered
  **420 files**.
- Independent cash reconstruction for the invented Rs100,000 baseline is exactly
  `482055217528559/5000000000`, matching the recorded decimal cash.
- The CLI proof exercised an ordinary trade, a Donchian `opposite_signal` exit and a
  low-volatility `rebalance` exit, and retained costs, quantities, cash, benchmark source
  identity and full evaluation identities.
- The original provisional union SHA-256
  `641bfcb3068659eac69acc7c4c3e4e3e0ffcdaad97e709f10edbbe0aee6915e8`
  is retained but superseded: six environment-masked `WinError 5` cases did not prove their
  intended guards. The outside-sandbox reproof SHA-256 is
  `16f155020c8043d9d8b49e215af7ade421b7af8909a07608672bc1b57f55c9a0`;
  all six cases fail their intended predicates and seven positive controls pass. Independent
  review reconciled all 39 semantic mutants under corrected union SHA-256
  `277323d69d16c7de3e31ae8acd064571e75f644fa05c4f1602142acd5a8ddea1`.
- The final restored gate passed **119 tests with two capability skips** (121 collected); a
  formatted witness passed **four tests in 0.71 seconds**. Final strict mypy covered **98
  source files** and global Ruff covered **422 files**.
- Test-only formatting preserved the Python AST: old witness SHA-256
  `6585885e15a9ef65e6501b9bd57174b44ab8f31041ceed98b5a9e5e05ac92c71`
  and formatted witness SHA-256
  `16bfc01152ea1a8c5ab578d97430b3334d15872b38e54febe681325e94612e44`.
  The full runtime files and compatibility facade were preserved, as was legacy cache SHA-256
  `2ea1e377eeec88605f8d1a8e6851516b1bbc4676ad4340ea5c5c75f4aa84724a`.
- Retained failed proof attempts include weak witnesses across boundary,
  inactive/finite, authorization/read and projection cases, a target-wiring error, and
  sandbox setup failures. Their tests were repaired without runtime source changes; they are
  not counted as successful mutation detections.

## Status boundaries

`SOFTWARE_VERIFIED=true` for bounded local invented-data mechanics. Independent final review
gave scoped GO after direct inspection of the six repaired raw causes, seven controls, all 39
mutants and all 14 protected files against HEAD. Reviewer receipt SHA-256 is
`976879f5ebd933104875542120d3c3a2ce2a1a3ff832d3e3989787fce1c0a550`.
No current-source hosted CI pass is claimed.

`DATA_QUALIFIED=false`. The software checked structure and causality only against invented
files. It did not establish vendor authority, licence, historical completeness, timestamp
semantics, adjustment truth, full-history memory/runtime feasibility, or authoritative
calendar and point-in-time coverage.

`RUN_AUTHORIZED=false`. No actual PostgreSQL ledger was activated and no actual market-data
or strategy run occurred. No subscription, purchase, vendor contact, network feed,
inference, lockbox, broker or live path was used. A future run still requires independently
reviewed external qualification evidence, exact input bindings, fresh run authorization and
an activated actual ledger.

This review records software mechanics only. It provides no profitability, alpha,
statistical-applicability, validation, promotion or live-readiness claim.
