# Calendar stress/confirmation design milestone

Date:2026-10-01. Scope: routine design/review under operator D38/D39 after the completed D40 calculator. No new implementation, sampled study or method adoption. Entry `dev` HEAD/origin `8a47ef15f36cba5b80591fbb1f69a5ea06646216`; user-owned AGENTS.md preserved untracked.

## Reviewed proposal and material correction

The [concrete protocol](../plans/2026-10-01-signal-calendar-stress-confirmation-protocol.md) pins finite stationary whole-trade laws, two short calendar spans, original selected-trade targets, target-specific widths, emission/coverage/tail/precision/effect criteria, independent confirmation, retained exposure and resource/stop rules. Final protocol SHA256 `4d5d1749c799d124129ced0e3def82af91ca6f61fcccdcca7fe7a0f8fd044255`.

The independent [mathematical review](2026-10-01-signal-calendar-stress-math-review.md) caught a material flaw in the initial4096-replicate proposal. Its strict simultaneous criteria would reject even an ideal95%-coverage procedure with high probability: conditional coverage needed3904/4096, giving only18.96% single-criterion pass probability; a2.5% tail passed the102-error cutoff only51.03% of the time. Primary independently reproduced both integer thresholds and binomial probabilities. This was corrected before any draw; the original finding is preserved.

Confirmation now proposes32768 replicates per cell, keeping all280 one-sided criteria and family allocation unchanged. Independent exact integer/Fraction binomial tails and primary independent SciPy beta inversion plus binomial-tail identities agree on the integer cutoffs. For the explicitly hypothetical ideal benchmark (arithmetic/precision emission1, coverage.95, tails.025, effect detection.90), the union rejection upper bound is0.000285365662602, so family pass probability is at least0.999714634337398. No independence across cells is required. This is a test-design operating check, not a calculator success rate or proof of actual runtime feasibility.

The independent [governance/simplicity review](2026-10-01-signal-calendar-stress-governance-review.md) separately checks restricted scope, sparse limitations, held boundaries, Windows resource disclosure, evidence, counted attempts and untouched confirmation. Review approval concerns the proposal; implementation/experiment correctness still needs exact-source verification.

## Primary verification beyond reviewer messages

Deterministic rational enumeration of all profile atoms independently confirms every raw truth0, paired truth-1/200, and win truths:

| Profile | Exact selected-trade win truth |
|---|---:|
| P1 | 1/4 |
| P2 / L1 | 7/12 |
| P3 | 121/256 |
| P4 | 9887/24576 |
| P5 | 1143/2048 |
| P6 | 3577/6144 |
| P7 | 74146261351971311/144115188075855872 |

Conditioning on shared innovations leaves independent stock-specific signs. Raw/paired long-run variance has lower bound E[C V^2]>0; win has lower bound E[C/4 *1{-V<base<=V}]>0. Primary exact enumeration gives positive bounds for all eight profiles; the independent review provides the finite-dependence argument. Runner generator equivalence and implementation of these declarations are still unbuilt.

Primary reproduced all16 profile/span resource envelopes; the largestP7n128 gives256 rows,11520 total footprint items and246376 expanded items, inside frozen technical caps. This is deterministic input-allocation feasibility, **not elapsed-time, process-memory or durable-artifact feasibility**. L1 maximum emission is0.2762022794 atn64 and0.4086045648 atn128; this known in-model limitation cannot be hidden behind survivor coverage or a restricted dense-family pass.

52 metric cells have18 shared path families: proposed development9216 paths/26624 metric evaluations; confirmation589824 paths/1703936 evaluations. Neither full-size phase has run. The larger confirmation must first pass independently checked deterministic runtime/artifact feasibility with margin inside the proposed unchanged7200-second/2GiB phase envelope. Failure or missing proof blocks sampling; no smallerR, weaker criteria, missing evidence or automatic budget rescue.

Primary deterministic evidence is retained under ignored `var/verification/2026-10-01/calendar-protocol/`: `primary_oracle.py`, `primary-oracle.json`, `operating_check.py`, `operating-check.json`. These contain exact finite-law enumeration and deterministic numerical binomial computations, **no RNG or sampled market histories**. The independent reviewer uses separate exact integer binomial sums, not the primary's numerical inversion. Documentation consistency regression `uv run pytest tests/unit/test_audit_ledger.py -q`:15 passed in0.12s. Diff line counts match with/without CR-at-EOL normalization; whitespace checks pass. Local links, frozen protocol/review hashes and protected source/config checks are verified before commit; no unchanged code-suite rerun is claimed.

## Current outcome and next action

Design is concrete for operator presentation after final written hash-specific reviews. No sampled reliability result exists, no floor/method is accepted, Task3a/M1-M4/F48 remain OPEN and inference stays disabled. No product/source/config/threshold/official-manifest edits, reserved draws, real-data trials, lockbox or broker/live path.

Next proposed unit: approve/build the isolated synthetic research runner with deterministic tests and ordered reviews. Only after exact-source generator/numeric/attempt/resource verification and a separate sampled-study decision may the development screen run. Confirmation depends on a complete passing development decision and untouched independent stream. Original source/benchmark/accounting/trial prerequisites, step order and official Windows durability/resource blockers remain unchanged.
