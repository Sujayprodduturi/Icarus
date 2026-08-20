# STATE.md — where Icarus actually is, today

**Last updated: 2026-08-20.** This file is the **session entry point**. It is deliberately short:
it tells a new agent (or the operator after a break) what is true right now, what happens next,
and which file to open for the detail. It holds no reasoning of its own — everything here points
somewhere durable.

**Keep it current.** If a session ends and this file still describes the session's starting state,
the session left the repo worse than it found it.

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

**Current position: the post-backtest repair plan, Step 2g-3.** Two items (2g-3, 2g-4) remain
before Step 3.

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
| `BUILD_MAP.md` | Older decision record, pre-dates `OPERATOR.md` §7b. | Rarely — history only. |

---

## 3. What is built and passing

**981 tests passing, 4 skipped. `mypy` clean (123 files). `ruff` clean (140 files).**
Verified 2026-08-20 on `dev` at `414fa0d`.

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

Full detail in the audit's §6c. Status as of 2026-08-20:

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
| **2g-3** | `rank_by` and the `xs_` words accept a market-wide value (F25) | ⬅️ **NEXT** |
| **2g-4** | Annulled flash-crash prints are still in the panel (F23) | todo |
| **3a** | Signal-test mode — every signal, uniform notional, no book (F2, D1) | todo |
| **3b** | Two capital rows: ₹10,00,000 edge run and ₹1,00,000 seed run (F15, D8, D9) | todo |
| **3c** | Common-window comparison (F16) | now the **default** after F40, not a later correction |
| **4a–4d** | Gross · costs · tax · net columns; per-trade CSV; alpha/beta/R²; withdraw the bad Nifty line | todo |
| **5a** | Capture the golden backtest regression — *from the corrected engine, never before it* | todo |
| **6a–6b** | Write the eight strategies (audit §6d), then pre-register them with a date **before** any runs | todo |
| **7** | Run. ← the next backtest | todo |

### 2g-3, in plain English (the next task)

`rank_by` sorts the universe to decide which candidates get the limited slots. Some words in the
vocabulary return **one number for the whole market**, not one per symbol — `benchmark_return`,
`advance_decline_ratio`, the breadth words, and the feed words `fii_net_index_fut`,
`client_net_index_fut`, `in_fno_ban`. Ranking a universe by a number that is identical for every
symbol is not a ranking: the sort falls through to whatever the tiebreak is, which is the symbol
name. **A degenerate alphabetical ranking that reports as a working one.** It has to be refused at
parse time, the same way F1's rupee-denominated inputs are. Affects 3b and 3c directly.

Located precisely on 2026-08-20: these words are registered in
`icarus/strategy/library/cross_sectional.py` as `Kind.SERIES` with `scale_free=True` and no
`unrankable_reason`, so they pass all three checks `_rank_by` already performs. The fix is a
**declared property on the primitive**, not a list maintained in the parser. Second, smaller point
from the same day's reading: even once market-wide words are refused, a tie should *produce* a tie
rather than falling through to alphabetical order.

---

## 6. Open — waiting on the operator

| item | what is needed | blocks |
|---|---|---|
| **O4** | **Host details.** The decisive question: does the line have a **static public IP**, and is it behind **CGNAT**? Indian residential broadband usually is, which makes a static IP impossible on that line at any price — and invariant #6 requires every order to originate from a registered static IP. Also: CPU arch, Ubuntu version, RAM/disk, always-on, UPS, remote access, timezone, disk encryption. | 🔴 Phase 1 going live (task 1.10) |
| **F45** | **Should the concentration cap trim winners?** It is an *entry* bound today: nothing re-checks a position after it opens, so a name compounding 5× drifts from 25% to **61% of the book by bar 58**. Trimming has cost and tax consequences, so it is a decision, not a bug fix. Second question in the same finding: the cap is measured against **realised** equity, so unrealised losses do not shrink it. | 3b (where concentration bites) |
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
panel · `F22` no lag operator or series arithmetic in the DSL (partly done) · `F45` above.

**F12 now has a reference implementation available.** The 2026-08-20 evaluation of the open-source
`HKUDS/Vibe-Trading` platform (`docs/reviews/2026-08-20-vibe-trading-evaluation.md`) found a
correct, MIT-licensed, self-contained DSR/PBO module whose 75 tests I ran and passed. The verdict
on the platform as a whole was **keep building Icarus** — its backtester always fills at the bar
open, models no capital-gains tax, and has no point-in-time universe for India, so nothing measured
in it could clear our gate. But `multipletesting.py` and `crossvalidation.py` are worth using as a
**test oracle** when F12 is scheduled (`CLAUDE.md` §5 requires our own in-house implementation, so
they are a cross-check, not a dependency).

**One new gap that evaluation surfaced, not yet numbered:** our audit log is a plain append with no
fsync and no hash chaining, so a retrospective edit to it would be undetectable. `CLAUDE.md` §7
requires it append-only and retained ≥5 years, and it doubles as the tax ledger. Their
`governance/ledger.py` shows the shape of the fix. Operator decision needed on whether this becomes
a numbered finding; it is not Phase-1 blocking.

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

Current: `dev` at `414fa0d`, clean. `main` is still at the Phase-0 exit commit — the whole of
Phase 1 lives on `dev` and has not been merged.
