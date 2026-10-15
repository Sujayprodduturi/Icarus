# Paired daily/M15 source adapter — build review

Status: **LOCAL SOFTWARE VERIFIED; POSTCOMMIT FAULT PROOF GO**,
under operator approval D56. Source qualification and actual strategy evaluation
remain held.
The reviewed source is committed locally as
`bb52837aef3ef756b8682445c31319285d26faf1`; all five product files were restored byte-for-byte after fault checks.
Approved scope: [paired-source adapter](../plans/2026-10-15-paired-source-adapter-proposal.md).

## Required behavior

Official daily records remain the signal/PIT input. M15 records remain the
execution input. The legacy path still requires exact aggregation. The new
path requires external qualification bytes pinned through the public CLI's
existing certificate and execution authorization before reservation/decode.
It must not use a boolean to bypass content/lineage/action checks.

Shared economic bases are effective-dated per security. Separate close
construction does not excuse incompatible split/bonus/rights/dividend bases.
Unknown required relationships refuse. Source-supported extrema containment
and volume rules are deterministic, without arbitrary tolerance or price repair.
Bindings must detect changed files and changed in-memory daily/M15 values,
including sliced walk-forward inputs. All existing grid, liquidity, missing
held inventory, benchmark interval and risk behavior remains controlling.

## Verification checkpoints

- Builder recorded module-absent and paired-engine-absent RED checks before
  implementation. Both signal and portfolio paths are integrated, including
  the guarded 21-plan public CLI fixture. Final local OHLCV focused checks pass.
- The ordered simplification pass is lean/acceptable. Final independent code
  and security review is GO on the exact five product hashes below; its own
  frozen gate passes 107 tests in 70.49 seconds. Receipt SHA-256:
  `a5a145373442f1c25808aa1a65c125b17748ca5ca95881afc8f468dd2794da95`.
- Root's final sealed-candidate gate passes **236 tests in 76.08 seconds**.
  Global Ruff and format checks pass for 437 files; strict typing passes for
  all 90 source files. Accounting/backtest and prior strict-path regressions
  are included; this does not close the separately unfinished full-history
  golden-backtest task or any actual-data/statistical acceptance gate.
- Root's independent invented-value probe preserves daily close108 versus
  M15 close107 without modifying either. Mismatched open, extrema and volume
  receive the intended typed refusals; supported subset volume passes. A
  daily close9999 above its own high110 now refuses as `PAIR_OHLC`.
  Actual paid-data archives are excluded from all these builds and tests.

| Product file | Frozen SHA-256 |
|---|---|
| `source_pair.py` | `ce5a78bc37b8d6a26cb7e259814304456195fc3384779b660119b7918c5b1268` |
| `timed_runner.py` | `7198b2845c5fd97f3fc532f239f849e341fc67f1da147d8c9941805ed71b48df` |
| `timed_simulation.py` | `ed4a3a728da405f5fda548072be8837c91e68cbdf66a5e1463d9c08eb6acd7ff` |
| `timed_evaluation.py` | `3c72fc69be768adaea88ef089d0bc7f589178d200b41b0a477f36f698c299e7f` |
| `run_timed_backtest.py` | `a26bdd3f015330aba28dd251961b2757b18b25028fbe042b54eebee490e5eec6` |

### First frozen candidate

Root's first independent gate passed 221 tests in 79.02 seconds, including
source-pair, shared timing, runner/CLI, evaluator, timing management, accounting,
fills/backtest and audit-document checks. Global Ruff and formatting (437 files)
and strict typing of the five changed product modules passed. These checks
precede the final single-source-of-truth correction and are not the final proof.

The ordered simplification review identified duplicate bound qualification
state in assembled inputs and the fixture. Code review confirmed a real bypass:
the evaluator could inspect one alias while the engine consumed the other.
Remove the duplicate and test that post-assembly mutation cannot evade the
remaining seal. Two optional cuts are retained deliberately: the binder's small
hash check protects that boundary independently; the CLI's explicit multi-symbol
fixture remains independent of the one-symbol parser fixture.

Other verified review corrections include removing a trust boolean, requiring
closed supported volume/opening rules, rejecting relative price conversions,
sealing daily axes and benchmark arrays, verifying the full projection before
slicing, rechecking captured document bytes, and covering full sessions with
dated security mappings. These passed final code/security review; postcommit
semantic fault checks subsequently passed as recorded below.
The final candidate also checks vendor/revision identities against captured
metadata and validates both daily and M15 candles independently before allowing
different closing conventions. Relative action-factor conversion is unsupported.
Lineage/reviewer declarations remain external attestations, not software proof
of the vendor's historical truth or a replacement for source qualification.

## Postcommit proof checkpoint

The first harness attempt correctly stopped on a zero-match CRLF anchor before
counting that case; reviewed product bytes were restored. Cases M01–M11 were
then caught by their intended tests. M12 exposed a real test weakness: the
benchmark fixture aliased a stock Bars object, so a benchmark mutation also
changed stock data and masked an omitted benchmark seal. That first M12 result
is retained as **not caught**, not converted into a PASS.

The test-only correction copies every benchmark array and verifies a benchmark
mutation leaves stock close unchanged. Root's simplification pass and formal
review are GO; both corrected daily/benchmark checks pass. Product hashes remain
unchanged. The test correction was committed as 2c67992 before continuing
M12–M14. The continuation caught all three intended failures; M01–M11 remain
caught in the preserved receipt. Overall postcommit verdict: GO, 14 cases caught.
The continuation baseline passed 107 tests in 82.27 seconds and final restored
positives passed 107 in 58.45 seconds. All five product hashes and line-ending
counts match the reviewed source exactly. Continuation receipt SHA-256:
4279caec63c1bd433e251f7ce3500418e6458a5c1a303405536af7616601f75a.

## Final CI-equivalent local check

The exact default `uv run mypy` initially found seven typing errors in two
new tests that the earlier source-only typing command omitted. Reviewed
variable names and explicit Optional opening handling fix these in test-only
commit `a6b238f`; runtime hashes remain unchanged. Root then independently
passed typing across all 195 configured files, 109 relevant restored tests
in 15.18 seconds, global Ruff and formatting of 437 files. Independent formal
review of the correction is GO with four affected tests passing. A sandbox
UV default-cache permission failure was resolved by using the existing
workspace-local cache; it was not counted as a successful verification.

This is local software proof. New-head hosted CI is pending publication;
actual data qualification, interval benchmark policy and full-history golden
acceptance remain separate.
## Prior hosted failure corrected locally

The preceding documentation commit `97069b2` passed resource proof but failed
CI `38693272302`: three audit-checklist tests failed after 3,297 passes and four
skips. The new audit used an unsupported heading/three-column table instead of
the required ranked fix list with explicit status. Root reproduced all three
failures, corrected that document without changing tests, and all 21 audit
ledger tests pass locally. This is not a full new-source hosted CI success.

`DATA_QUALIFIED=false`; actual-study `RUN_AUTHORIZED=false`. No numeric gates,
benchmark methodology, actual trial ledger, broker/live path, inference or
lockbox evaluation changes are authorized by this build.
