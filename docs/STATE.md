# STATE.md — where Icarus actually is, today

**Last updated: 2026-09-30.** This file is the **session entry point**: it records the current build position, next action and held boundaries. The [current handover](HANDOVER.md) gives the next-session checklist. Older sections below retain dated history; section 0 controls the current action.

**Keep it current.** If a session ends and this file still describes the session's starting state,
the session left the repo worse than it found it.

---

## 0. Resume here — 2026-09-30

**Current operator direction:** Use the current Windows PC for the simulator and supported tests. The operator confirmed on 2026-09-30 that no separate Linux system is available (D30 — local testing on the current PC). D24 already selected this PC; neither decision authorizes an OS migration. Do not ask for a separate machine as a prerequisite to local synthetic testing.

**Completed locally at source `cdf127b`:** The existing synthetic signal simulator ran twice with identical results: five emitted signals became two trades and three explicit skips, with both entries executing on the next bar. The simulator/fill/accounting/statistics test group passed **268 tests** in 31.51 seconds. The earlier counted-runner safety test group completed **301 passed, six platform skips** in 1,618.21 seconds. Deterministic preflight, Ruff, formatting and strict mypy passed. The [Windows evidence record](reviews/2026-09-30-windows-simulator-check.md) contains commands, provenance, limitations and the toy results. These are synthetic behavior checks, not strategy performance or accepted calibration.

**Completed remotely at exact source `cdf127b0ea32270056d34e2273f3fefc2929e34f`:** [Linux CI](https://github.com/Sujayprodduturi/Icarus/actions/runs/36680292873) passed 1,644 tests with four existing skips, Ruff and mypy. [All three native test-only resource proof modes](https://github.com/Sujayprodduturi/Icarus/actions/runs/36680292816) passed aggregate `WITHIN_FROZEN_LIMITS`. The primary and an independent reviewer downloaded and inspected the raw logs/reports, matched each final log JSON to its report, and reproduced the production aggregate verdict with the exact source identity. Zero reserved draws or durability failures were reported. GitHub supplied test-only proof, not an official evidence host.

**Build position:** Phase 1, Task 3a — a trustworthy signal diagnostic. The synthetic simulator, candidate moments, test-only generator, guarded combined calibration/validation runner, bounded saved-file verifier and same-process completion authority are built. The official calibration/validation has not run, no floor is accepted, and `goal.yaml` still has `signal_test.inference_enabled: false`.

- **Local continuation:** Run existing synthetic simulator/fixture tests, deterministic preflight and static checks on this PC. No Linux host, broker connection, real-data strategy evaluation or reserved stream is needed for that lane.
- **Separate official-calibration restriction:** The current reviewed contract and implementation support bare native Linux only; Windows refuses before claim/RNG. There is no eligible official host. Making the official counted experiment work on this PC would require a separately explained and reviewed platform/durability design; do not bypass the OS/resource/filesystem guards with WSL, containers or monkeypatching. The instruction to run local tests is not authorization to consume the one-shot streams.
- **Exact-source review:** The old canonical attestation at `614fa7a` reviews `81fc971` and does not cover the later handover ancestry. The successful `cdf127b` checks establish evidence for that source only; these documentation corrections create a later source identity. Renew exact-source checks and independent attestation only when preparing an actual official invocation, after finalizing its source/host and before requesting the separate stream decision. Local synthetic tests do not need that official attestation.
- **Later work:** Step 6b pins minimum data requirements only after valid reviewed synthetic calibration and validation; trial-ledger, benchmark/source/cost review and real-data runner work remain later dependencies. No official real-data rerun, actual lockbox evaluation or live order path is enabled.
- **Open verification limitations:** Six Windows platform skips, four existing Linux integration skips and the unperformed power-loss experiment remain disclosed. The synthetic portfolio characterization still passes; the separate production golden backtest is deliberately not captured yet.
- **Repository entry:** Work on `dev`; check live `HEAD`, `origin/dev` and cleanliness. Preserve the user-owned untracked `AGENTS.md`. At entry to this local-test follow-up both commits were `cdf127b`; consult Git for the later documentation commit.

**Earlier evidence and failure history:** `81fc971` passed the earlier [CI](https://github.com/Sujayprodduturi/Icarus/actions/runs/36561344466) and [native proof](https://github.com/Sujayprodduturi/Icarus/actions/runs/36561344390), independently reviewed and attested at `614fa7a`. The first native proof at `8598255` failed safely when whole-file verification exceeded the frozen memory budget; the bounded-reader repair and fixture correction preceded the later passes. Details remain in the [native proof plan](plans/2026-09-28-step6a2-task3-native-envelope.md) and review records. A test-only statistical FAILED verdict is not an official reserved-stream outcome.

---

## 1. The thirty-second version

Icarus is at **Phase 1** — data, backtesting, and an honest metric sheet. **No live-order code
exists** and none may exist before Phase 2 (`CLAUDE.md` §0, invariant #11).

The engine has run end-to-end on real data once, on 2026-08-07. **All three strategies failed the
pre-registered stop gate, and the verdict was "no edge", not "overfitted"** — mean *in-sample*
Sharpe was negative, meaning they lost money on the very data they could have been fitted to.

Then an audit of that run found the engine had been measuring something other than the strategies
that were written down. **Every number from that run is void.** We are part-way through the repair
plan that has to finish before the next backtest is worth running.

**Current position: Step 2g is complete; Task 3a is in progress.** Its plan was corrected on 2026-09-24 with operator approval (D16). Step 0, the synthetic pre-extraction characterization, is complete at `b54f3cb`; Step 1, the behavior-preserving shared exit extraction, is complete at `83ff601`. Step 2 (`signal_test` config and loader refusals) is complete at `61191d6`; Step 3 (lockbox span guards) is committed at `3cf0bf3`; Step 4 (typed signal trade/skip records) is committed at `e5d9fee`; Step 5 (the synthetic-only signal simulator and remaining pure helper extraction) is complete at `997bbd2` after independent safety and standards review. Step 5b (observational portfolio discard ledger) is built at `ed9f46b` under the approved `docs/plans/2026-09-25-portfolio-discard-ledger-implementation.md` plan. It records why each emitted portfolio signal was accepted or discarded, including final-bar and untradable-session omissions, without changing the old skip counters or the frozen trade/equity/cost trace. Review found and closed a real duplicate-OOS-ID risk: overlapping test folds now fail closed rather than silently double-counting a signal. The 2026-09-25 verification passed 1,197 unit tests, Ruff format/check, and mypy. Post-commit mutation probes killed missing-discard and source-index-reset mutants; safety controls refused transient legacy-counter corruption and candidate-reordering mutants, so those two mutation claims remain unverified. The focused restoration checks passed. Step 6a/6b statistical design is independently reviewed in `docs/plans/2026-09-26-signal-statistics-design.md`. The bounded Step 6a.1 implementation plan is `docs/plans/2026-09-26-step6a1-estimator-implementation.md`: Task 1's immutable typed boundary and source-axis checks are committed at `34257f8`, and Task 2's guarded CR2/Satterthwaite candidate moments plus independent dense oracle are complete through numeric/order-stability fixes at `88d0417`. Astra's [final implementation review](reviews/2026-09-26-step6a1-final-review.md) approved **Tasks 1–2 complete (Step 6a.1 milestone)**; At that Step 6a.1 milestone, Step 6a was partial: no calibrated product confidence interval/floor, benchmark/alpha inference, placebo p-value, combined calibration runner or real-data evaluation existed. Since then the combined synthetic calibration runner has been built; product inference remains disabled, no floor is accepted, and the real-data signal-test runner remains unbuilt. The operator chose explicit caller-supplied missingness reasons (unlabelled NaNs rejected) and no daily-bar benchmark approximation for intraday exits (D20); both boundaries remain. No Task-3a real-data evaluation or lockbox run has occurred. Any real-data rerun still counts as a trial. The redesigned three-board visual map is linked from `docs/README.md`; the older diagrams remain dated history. See `docs/plans/2026-08-22-signal-test.md`. 2g-4 was closed as not-a-defect.

**The operator clarified on 2026-09-24 that learning must examine both strategy entry/exit timing and order-execution timing (D17).** The proposed phased lineage contract is `docs/plans/2026-09-24-trade-lineage-learning.md`; it does not enable future-phase behavior now. On 2026-09-26 the operator chose a time-resolved stock-and-Nifty route for benchmark-relative signal results (D21). Its source-neutral specification in `docs/plans/2026-09-26-time-resolved-benchmark-design.md` was approved for Step 6 planning on 2026-09-26 (D22); Step 6a.1 Tasks 1–2 are complete and independently reviewed; Step 6a remains partial. The [final review record](reviews/2026-09-26-step6a1-final-review.md) documents 1,246 unit tests plus Ruff and mypy passing at `88d0417`. **Now:** the [Astra-reviewed Step 6a.2 synthetic calibration plan](plans/2026-09-26-step6a2-calibration-implementation.md) is in progress. Its Task 1 manifest and deterministic preflight are committed at `fbaa3f7` and hardened at `eb90def`; [Task 1 review](reviews/2026-09-26-step6a2-task1-review.md) approved this freeze for Task 2. Task 2's offline generator and interval evaluator are committed at `13ccece` after independent spec/standards and Astra review; [the review record](reviews/2026-09-26-step6a2-task2-review.md) documents the repaired findings. The frozen calibration and held-back validation streams remain untouched; product inference stays disabled. **Historical next step after Task 2:** Task 3's counted phase gate, immutable artifacts, and validation authorization (subsequently built; see section 0 for current local testing and the separate official restriction). Its [revised implementation plan](plans/2026-09-26-step6a2-task3-counted-gate.md) has an [adversarial plan audit](reviews/2026-09-26-step6a2-task3-plan-audit.md); the [2026-09-27 Astra approval addendum](reviews/2026-09-27-step6a2-task3-rereview.md) now approves bounded implementation against the exact contracts. The pure evidence verifier, startup controller, guarded generator, statistical event adapter and durable writer are accepted through `12e1a8a`. Slice 4A independent saved-file verification is implemented at `e406a7b` and independently reviewed. Operator D29 settled the completion-authority ruling; Slice 4B implements candidate writing and same-process authority at `bcaa900`; Slice 4C adds private validation authorization and resource handoff at `c694e4a`; Slice 4D adds guarded validation generation at `11241b8`. The combined counted CLI is implemented at `9f7360c`; exact `81fc971` passed native proof/CI and was independently attested at `614fa7a`. This handover change requires renewed exact-commit attestation, and frozen-stream draws still need a separate operator decision. Candidate floors are not accepted floors, and inference remains disabled. The first timing overlay remains M15 on the separately pinned intraday lane, and no benchmark matcher or historical-data subscription has been added. D20's refusal of daily-bar intraday-exit alpha remains in force until that route is proven. The hosted Zerodha MCP is available to Codex as separate operator tooling, but its exposed mutations make it potentially write-capable; it must not enter Icarus's research plane or serve as the Phase-1 acquisition path.

**The plan grew on 2026-08-20, by operator decision.** Two items were added after an evaluation of
the open-source `HKUDS/Vibe-Trading` platform found it had built things we had not: **F12
(DSR/PBO)** moves onto the critical path *before* strategies are pre-registered, and the
**audit-log hash chain** is scheduled after the run. Reasoning in
`docs/reviews/2026-08-20-vibe-trading-evaluation.md`.

---

## 2. Read these, in this order

| file | what it is | when you need it |
|---|---|---|
| `CLAUDE.md` | The **26 safety invariants** and the engineering conventions. Nothing overrides these. | Every session, first. |
| `OPERATOR.md` | How the operator wants to work; the **append-only decision log** (§7b) and the deferrals with their reopening triggers (§7c). | Every session, second. |
| **this file** | Where the build actually is. | Every session, third. |
| `docs/reviews/2026-08-09-post-backtest-audit.md` | **The living checklist** (§6) and **the ordered plan** (§6c). Between "found" and "scheduled", a finding lives here and nowhere else. | Before starting any repair-plan work. |
| `TASKS.md` | The phase-by-phase build checklist. Phases 0–3 are build-ready. | When the repair plan is finished and the numbered list resumes. |
| `PRD.md` | The full requirements. | When you need the spec for something specific. |
| `goal.yaml` | Every threshold. Nothing risk-related is hard-coded in logic. | Before touching any number. |
| `docs/README.md` | Documentation map and dated layered architecture/progress diagrams. | For a visual orientation, then return to this current state file. |
| `BUILD_MAP.md` | Older decision record, pre-dates `OPERATOR.md` §7b. | Rarely — history only. |

---

## 3. What is built and passing

**Latest measured verification (2026-09-30, source `cdf127b`):** Windows simulator/fill/accounting/statistics group: 268 passed; counted-runner safety group: 301 passed, six platform skips. Deterministic preflight, Ruff, formatting and mypy passed. Exact-source [Linux CI](https://github.com/Sujayprodduturi/Icarus/actions/runs/36680292873): 1,644 passed, four existing skips; [native test-only proof](https://github.com/Sujayprodduturi/Icarus/actions/runs/36680292816): all three modes and aggregate passed, raw evidence independently checked. See the [Windows evidence record](reviews/2026-09-30-windows-simulator-check.md). These are completed checks for `cdf127b`, not an attestation or proof for a later documentation commit. The old `81fc971` review remains historical evidence. Reserved streams remain untouched.

**Earlier Slice 4E verification (2026-09-28):** code `9f7360c` passed 1,612 Windows unit tests (six platform skips) and 1,618 exact-commit Ubuntu CI tests (four existing integration skips), plus Ruff, mypy and independent review. The integrated test exercised a scripted calibration-to-validation handoff without a reserved RNG draw. The later exact-runner proof and attestation are recorded above. Power-loss testing remains unperformed. Neither reserved stream has been drawn; inference stays disabled. See the [combined-runner review](reviews/2026-09-28-step6a2-task3-combined-runner-review.md).

*One pre-existing `mypy` complaint sits outside that scope and is not new:*
`scripts/build_panel.py:118` returns a bare `tuple`. The project's `mypy` invocation is
`mypy icarus tests`; adding `scripts` finds it. Noted rather than fixed — unrelated to 2g-3.

| area | state |
|---|---|
| Phase 0 — skeleton, safety rails, no-order-path proof | ✅ complete (0.1–0.12 + the v2 hardening items) |
| Data layer (1.1, 1.1b, 1.1c, 1.1d) | ✅ 2,962 sessions × 693 point-in-time symbols, 2011-01-03 → 2022-12-30 |
| `CostModel` (1.5) / `TaxModel` (1.6) | ✅ costs and taxes computed inside every backtest |
| Pre-registered stop gate (1.0g) | ✅ pinned 2026-08-01, loader asserts the date has not moved |
| Strategy DSL (1.4a–c) | ✅ **224 primitives**; 125 declared `scale_free`, 99 price-denominated |
| Backtester + fill model (1.7, 1.7b) | ✅ pessimistic: trade-through required, queue position, next-bar execution, partial fills |
| Panel builder + runner (1.7c, 1.7d) | ✅ walk-forward, anchored, lockbox untouched |
| Metric battery (1.8) | 🔨 partial — regime stability and cost stress not run |
| Overfitting guards (1.9 — DSR/PBO) | ❌ not built (finding F12) |
| Synthetic pre-extraction characterization (3a Step 0) | ✅ committed `b54f3cb`; exact portfolio outcome + SHA-256, no real panel or ledger |
| Shared simulator exit mechanics (3a Step 1) | ✅ committed `83ff601`; characterization unchanged |
| Signal-test config refusals (3a Step 2) | ✅ committed `61191d6`; D15 + provisional statistics pinned, inference disabled |
| Lockbox span guards (3a Step 3) | ✅ committed `3cf0bf3`; whole-source refusal, fixed 2023 boundary, aligned valid axes, inclusive UTC-session dates |
| Signal identity and outcome records (3a Step 4) | ✅ committed `e5d9fee`; stable ID, trade/skip outcomes, partial-exit accounting, stale-mark provenance and pre-tax diagnostic alpha |
| Isolated signal simulator (3a Step 5) | ✅ committed `997bbd2`; synthetic-only outcomes, no portfolio return or promotion |
| Portfolio discard ledger (3a Step 5b) | ✅ committed `ed9f46b`; every emitted signal accepted or assigned one discard reason; old trade/equity/cost/skip trace unchanged; duplicate OOS identity fails closed |
| Candidate signal moments (3a Step 6a.1 Tasks 1-2) | ✅ Tasks 1–2 complete at `88d0417` ([final review](reviews/2026-09-26-step6a1-final-review.md)); partial Step 6a only, with calibration pending and inference disabled |
| Synthetic calibration freeze (3a Step 6a.2 Task 1) | ✅ manifest/preflight at `fbaa3f7` + `eb90def`, independently and Astra reviewed; no calibration draws or accepted floors |
| Synthetic generator and interval evaluator (3a Step 6a.2 Task 2) | ✅ offline fixture and batch interval code at `13ccece`, independently and Astra reviewed; test-only seed, frozen phase streams unopened |
| Counted calibration/validation gate (3a Step 6a.2 Task 3) | Combined runner built. `cdf127b` passed fresh CI/native test-only proof; Windows safety checks passed. `81fc971`/`614fa7a` are the earlier review/attestation. Official Windows execution remains unsupported, no official host exists, and no official result/floor is accepted. |
| Golden backtest regression (1.12) | ❌ deliberately not captured yet — see Step 5a |
| Live order path | ❌ **and must stay that way until Phase 2** |

Entry points: `scripts/backfill_bhavcopy.py`, `scripts/build_panel.py`, `scripts/run_backtest.py`.
Strategy files: `strategies/*.yaml` (three, all at v2 after the F1 rewrite).

---

## 4. The numbers rule — what may and may not be quoted

- **Nothing measured before 2026-08-16 is comparable with anything measured after it.** Task 2f
  moved fold boundaries, changed indicator values at the start of every span, and made the gate
  stricter (after-tax metrics plus an after-tax P&L check).
- **The 2026-08-07 result table in `TASKS.md` is void** and is marked as such in place. It stays
  written down because deleting a wrong number hides that it was ever believed.
- **The Nifty CAGR/drawdown comparison is separately invalid** even for the surviving Sharpe
  comparison — the baseline deploys ~4% of equity, so it is not like-for-like against a fully
  invested index. Scheduled for withdrawal in Step 4d (finding F13).
- **The lockbox (`data_split.lockbox_start`, 2023-01-01) has never been touched and is consumed
  exactly once** (invariant #26). The loader rejects a walk-forward window that overlaps it, and
  `assert_panel_stops_before_lockbox` refuses a panel that reaches it.
- **Every evaluation counts as a trial** against the ledger, including hand-authored ones and
  re-runs (invariant #24). Running a backtest is not free.
- **The gate does not move.** If every candidate fails, the response is to change the *input* —
  intraday data, a different strategy class, the India-specific feeds — never to lower the bar
  (invariant #25).

---

## 5. The repair plan — where we are in it

Full detail in the audit's §6c. Status as of 2026-08-21:

| step | what | status |
|---|---|---|
| **1** | Make the panel itself trustworthy | ✅ done |
| **2a** | Units in the strategy vocabulary (F1) | ✅ 2026-08-12 |
| **2b** | The engine's idea of how far back a strategy looks (F3, F28) | ✅ 2026-08-13 |
| **2c** | Positions in symbols that stop trading (F4) | ✅ 2026-08-14 |
| **2d** | The book could spend money it did not have (F6) | ✅ 2026-08-15 |
| **2e** | Config that lies, in both directions (F11, F36, F37) | ✅ 2026-08-16 |
| **2f** | The guards that don't guard (F29, F30, F38–F44) | ✅ 2026-08-16 |
| **F40** | The purge that protected nothing → one fixed `seam_sessions` (D10; closes F16, F31) | ✅ 2026-08-17 |
| **2g-1** | The look-ahead sweep was blind, not thin (F24) | ✅ 2026-08-17 |
| **2g-2** | Unverified `scale_free` flags (F27) + the concentration cap (F34, D11) | ✅ 2026-08-17 |
| **2g-3** | `rank_by` and the `xs_` words accept a market-wide value (F25) | ✅ 2026-08-20 |
| **2g-4** | ~~Annulled flash-crash prints are still in the panel (F23)~~ | ❌ closed 2026-08-21 — **not a defect**, premise false (D14) |
| **3a** | Signal-test mode — every signal accounted for, uniform notional, no book (F2, D1); diagnostic only | 🔨 Steps 0–5b and Step 6a.1 built; Step 6a.2 Tasks 1–2 frozen/offline and Task 3 counted runner reviewed. Documentation update requires renewed exact-commit attestation; first official synthetic draw needs a separate operator decision and native host. Calibrated product intervals, benchmark matching, real-data signal-test runner and evaluation remain unbuilt. |
| **3b** | Two capital rows: ₹10,00,000 edge run and ₹1,00,000 seed run (F15, D8, D9) | todo |
| **3c** | Common-window comparison (F16) | now the **default** after F40, not a later correction |
| **4a–4d** | Gross · costs · tax · net columns; per-trade CSV; alpha/beta/R²; withdraw the bad Nifty line | todo |
| **F12** | DSR/PBO/BHY overfitting guard — **added 2026-08-20**, and it must land *before* 6b: the correction is part of the gate, so adding it after results exist would change a promotion decision after the fact | todo |
| **5a** | Capture the golden backtest regression — *from the corrected engine, never before it* | todo |
| **6a–6b** | Write the eight strategies (audit §6d), then pre-register them with a date **before** any runs | todo |
| **7** | Run. ← the next backtest | todo |
| *after* | Audit-log hash chain + `verify_chain` — **added 2026-08-20**, deliberately off the critical path: no orders exist in Phase 1, so it moves no number on the metric sheet | todo |

### Why 2g-4 was closed without being built (2026-08-21)

**The finding said NSE annulled the 2012-10-05 flash-crash trades. It didn't.**

Emkay Global applied for annulment after its dealer error crashed the Nifty ~16%. **NSE's Relevant
Authority denied the application.** Emkay bore the loss — around ₹51 crore, more than its own
market capitalisation. It appealed; in September 2014 SAT **remanded** the matter for NSE to
reconsider rather than annulling anything, and it ended in 2015 as a private settlement between
Emkay and two counterparty brokers: compensation between members, not an exchange annulment.

So those prints are **legally valid trades**. Somebody bought at those lows that morning and kept
the gain — which is precisely why the application was refused. A backtest stop filling against that
low is modelling what really happened, and blanking the bars would repeat the biased deletion of
the tail that the ATR bad-tick detector already attempted and was reverted for.

There is also nothing else to put in a list: India had **no annulment framework at all** before
July 2015. SEBI created one *because of* this case and made it near-impossible to invoke — request
within 30 minutes, fee of 5% of trade value — and no NSE cash-segment annulment is documented
anywhere in 2011-2022. Halts are not annulments.

**Decision D14 supersedes D13**, which had scoped this task on the false premise. The corrections
are written into `panelbuild.py`, the audit, this file and `TASKS.md`, each with its source and
as-of date. **The lesson, which cost a scheduled task:** an external fact that schedules work has
to be sourced *before* it is scheduled. F23 sat in the plan for eleven days, and a scope for it was
approved, on a sentence nobody had checked.

**Two things worth keeping from the investigation.** The "32 symbols" figure had **no saved
derivation** anywhere — re-measuring the raw bhavcopy, a −15% intraday cut lands on exactly 32, so
it is reproducible by a natural measure rather than re-derived. And the **Nifty benchmark carries
the print too**: `benchmark_low` 4888.20 against a 5746.95 close, which every index-relative word
reads.

### What 2g-3 did (2026-08-20)

`Primitive.market_wide`, declared beside the computation and resolved at construction like
`scale_free`. **Required** of every `needs_panel`/`requires_feed` word; a word handed only one
symbol's `Bars` derives `False`, and claiming `True` without a panel or feed is refused as a
contradiction. `_assert_scale_free` became `_assert_comparable_across_symbols` and now makes both
checks wherever symbols are ordered against each other. Final count: **7 market-wide, 13
per-symbol, 0 undeclared** of 224 words.

**The code-review pass found five real defects in the first version of this fix, one of them
fatal to it**, and they are the reason the standing rule exists. The guard originally checked only
the *outermost* word, so `rank_by: benchmark_return` was refused while
`rank_by: zscore(benchmark_return(126))` parsed cleanly — the fix could be walked around by
wrapping the very words it existed to stop. **Normalising does not repair a market-wide value**: a
number identical across symbols has no cross-sectional dispersion for a z-score to normalise. That
is the exact asymmetry with F1, where wrapping a rupee quantity genuinely *does* repair it, and
both halves are now pinned by tests. The search walks the whole expression tree, and the
assumption that makes it exact — every reachable wrapper nests at most one series — is itself
asserted, so it cannot rot quietly.

The other four: `ambiguous_selection_days` was counted and never carried out of the simulator (the
same mistake `unfilled_exits` already records having made once); the tie was probed at a fixed
index rather than where the slots actually ran out, which the allocation loop moves whenever a
candidate is skipped; a full book was counted as an ambiguous *selection* when nothing was
selected; and two words were declared market-wide while routed down the per-symbol evaluation
path, which is now refused at construction.

Two things worth carrying forward:

- **The finding was wrong about `in_fno_ban`.** F25 lists it as market-wide; the F&O ban is
  per-scrip and the word's own summary says "Symbol is in the F&O ban list". Declared per-symbol,
  with a test pinning the correction. Following the finding would have retired a usable veto.
- **Ties are counted, not silently broken.** A refusal cannot stop two symbols genuinely scoring
  the same, so a ranker that ties *across the cut* now increments `ambiguous_selection_days`
  exactly as declaring no ranker does. That also catches an all-`nan` ranker — the F3/F28 failure
  wearing a ranker's name.

---

## 6. Open — waiting on the operator

**2026-09-27 update (D24):** the operator selected the current PC as intended host. It is Windows 11 with 15.9 GiB RAM; Linux deployment, static public IP/CGNAT, UPS and always-on readiness remain open, so O4 is not complete. The operator requested our auth/tax recommendations and has not consulted a CA. See the [roadmap follow-up](plans/2026-09-27-orchestration-roadmap.md#host-authentication-and-tax-follow-up): manual daily broker login recommended; tax assumption remains provisional with both tax stresses. Neither recommendation is an accepted new policy yet.

| item | what is needed | blocks |
|---|---|---|
| **O4** | **Host details.** The decisive question: does the line have a **static public IP**, and is it behind **CGNAT**? Indian residential broadband usually is, which makes a static IP impossible on that line at any price — and invariant #6 requires every order to originate from a registered static IP. Also: CPU arch, Ubuntu version, RAM/disk, always-on, UPS, remote access, timezone, disk encryption. | 🔴 Phase 1 going live (task 1.10) |
| **O5** | Daily broker auth: operator one-tap vs TOTP automation. | Phase 2 |
| **O7** | CA confirmation on the equity-delivery tax classification. | Tax model confidence |

Full list at the top of `TASKS.md`; O1 is done, O2/O3 are deprioritised (equity-first).

---

## 7. Open findings not yet scheduled

These live in the audit's §6 table and nowhere else. **A finding not in `TASKS.md` is not thereby
closed.**

`F7` India feeds never wired into the panel · `F7b` their history never downloaded ·
`F10` alpha/beta/R² vs Nifty (invariant #21) · `F12` DSR/PBO · `F13` withdraw the invalid Nifty
CAGR line · `F14` universe is ~98 names not 600–900 (not a defect; the scope was chosen on a wrong
number) · `F17` regime breakdown + cost stress · `F20` two-source cross-check never applied to the
panel · `F22` no lag operator or series arithmetic in the DSL (partly done) · **`F47` `tradable` does not stop an exit, only an entry** — new 2026-08-21 · **`F48` same-day partial delivery sells can be charged the per-symbol/day DP fee more than once** — new 2026-09-26. F45 was decided in D12 and is scheduled for 3b.

**F12 now has a reference implementation available.** The 2026-08-20 evaluation of the open-source
`HKUDS/Vibe-Trading` platform (`docs/reviews/2026-08-20-vibe-trading-evaluation.md`) found a
correct, MIT-licensed, self-contained DSR/PBO module whose 75 tests I ran and passed. The verdict
on the platform as a whole was **keep building Icarus** — its backtester always fills at the bar
open, models no capital-gains tax, and has no point-in-time universe for India, so nothing measured
in it could clear our gate. But `multipletesting.py` and `crossvalidation.py` are worth using as a
**test oracle** when F12 is scheduled (`CLAUDE.md` §5 requires our own in-house implementation, so
they are a cross-check, not a dependency).

**One new gap that evaluation surfaced — and a correction to how it was first written down.** The
first version of this note claimed our audit log was "a plain append with no fsync and no hash
chaining". **That was wrong.** `icarus/state/audit.py` writes to a Postgres table with a
**DB-level trigger blocking UPDATE and DELETE**, inside the caller's transaction, secrets scrubbed
(migration `d8847faf5e20`). On tamper-*prevention* we are ahead of them.

The real gap is **tamper-detection**: our own downgrade migration drops that trigger in one
statement, after which rows are editable and nothing would ever know. The fix is a hash chain
(`prev_record_hash`, `record_hash`) plus a `verify_chain` routine, keeping the trigger — prevention
and detection are different properties and a log with both is stronger than either. **Approved
2026-08-20, scheduled after the next backtest**: no orders exist in Phase 1, so it moves no number
on the metric sheet and is not critical path.

---

## 8. Process rules that have actually been broken

Not theory — each of these was violated in a real session and cost real rework. `OPERATOR.md` §5
carries the full versions.

1. **Run `ponytail`/`simplify` *and* `code-review` before committing.** Both. Mutation testing is
   not a substitute and was substituted once — it proves the tests catch the bug you already
   thought of; the reviews catch the one you did not. Seven findings came out of running them late.
2. **Never `git checkout --` a file while the tree is uncommitted.** It destroyed a session's work
   once. Snapshot in memory instead.
3. **Line endings are per-file.** Most docs are CRLF, some are LF, the audit is mixed. A multi-line
   anchor that assumes the wrong one matches nothing and reports zero replacements *silently*.
   Verify with `diff <(git diff --numstat) <(git diff --ignore-cr-at-eol --numstat)`.
4. **The console is cp1252.** `₹` (U+20B9) and `⚠` (U+26A0) raise `UnicodeEncodeError` when
   printed. Operator-facing output is ASCII (finding F46).
5. **Never cite `#N` / `FN` / `§N` / `DN` without saying what it means** — `#` = invariant,
   `F` = audit finding, `D` = decision, `§` = PRD or document section, `O` = operator item.
6. **Explain in plain English → get approval → build → summarise.** In that order, every time.
7. **Over-correcting is still getting it wrong.** A review finding of "five of these are wrong" is
   not licence to change fifteen; nine of fourteen `requires_lt` declarations were wrong in exactly
   that way.

---

## 9. Git

Repo `Sujayprodduturi/Icarus`. Work on **`dev`**; `main` holds only working code. **Commit every
change.** **No session link in commit messages.**

Current work remains on `dev`; check `git status` and `git log` for the live commit. `main` still
holds the Phase-0 exit; Phase 1 has not been merged.
