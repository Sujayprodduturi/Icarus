# Icarus orchestration roadmap - 2026-09-27

Status: handover synthesis and proposed milestone sequence, not implementation or trading authorization. Existing approved plans, operator decisions and safety invariants remain governing. Detailed implementation stays one reviewed task at a time.

## End goal and current evidence

The goal is autonomous equity-first trading with bounded learning: observe outcomes, propose one explicit change, count the evaluation, validate, version, canary, promote or reject, monitor and roll back. Strategy entry/exit timing and execution timing are separate hypotheses. Research never holds broker credentials or reaches broker endpoints. Numeric validation and hard risk limits remain outside the learner's control.

Fresh checks at session start: `dev` at `c031b00`, 46 commits ahead of the locally recorded `origin/dev`; only user-owned `AGENTS.md` untracked. No fetch was performed. `goal.yaml:244` keeps inference off; `scripts/signal_calibration.py` exposes preflight and selection checking, not counted calibration/validation. Its clean-tree verifier rejects unlisted untracked files. The per-call delivery DP-fee discrepancy is visible in `icarus/engine/costmodel.py:162` and remains open.

The handover records 1,307 unit tests and Ruff/mypy passing on 2026-09-26; those are historical results, not a fresh suite run. Phase 0 is recorded complete. Phase 1 data, vocabulary, fill/portfolio mechanics and substantial repair work exist. Signal simulation, discard accounting, candidate statistical moments and synthetic calibration Tasks 1-2 exist. Counted calibration, accepted floors, product intervals, benchmark matching and the diagnostic runner remain incomplete. No valid current strategy-profitability conclusion follows from the void August backtests.

## Immediate milestone: make Task 3 implementation-ready

Read the [Astra re-review](../reviews/2026-09-27-step6a2-task3-rereview.md) alongside the [Task 3 plan](2026-09-26-step6a2-task3-counted-gate.md) and [parent protocol](2026-09-26-step6a2-calibration-implementation.md).

- [ ] Resolve the exact validation clean-tree allowance: verified calibration claim/result/seal as input evidence, plus only the exact current validation artifact paths and existing user-file exception.
- [ ] Freeze result, claim, seal and review-attestation schemas: key sets, types, nesting, state transitions and reviewed-code versus invocation identity. Verify ancestry and every intervening changed path, not just final blob equality.
- [ ] Specify the target-platform memory enforcement and durable-file contract; distinguish enforced committed-memory limits from observed resident-memory peaks. Define test-only failure probes and refuse unsupported guarantees.
- [ ] Obtain Astra's explicit approval of those bounded clarifications. Preserve all frozen cells, seeds, thresholds, candidate ordering and inference-off state.

These are agent-owned engineering clarifications under operator decision D23, not new operator policy questions. The continuation resolved them in the [exact contracts](2026-09-27-step6a2-task3-contracts.md), and Astra's dated approval addendum now authorizes bounded implementation. The checklist above records the original planning work; code progress lives in the [execution ledger](../reviews/2026-09-27-step6a2-task3-progress.md). No frozen draw is approved.

## Milestones toward autonomous trading

| Order | Deliverable | Evidence required before moving on |
|---|---|---|
| 1 | Implement the counted synthetic gate in its four bounded slices | Failure-first tests for exclusivity, provenance, complete accounting, byte verification and cutoffs; deterministic and separate test-seed fixtures only; simplification then code/security/statistical review; full unit/static checks and portfolio characterization |
| 2 | Independently approve the exact committed runner, then execute the frozen protocol | First calibration invocation authorized by exact-code review; complete immutable evidence and parity checks; held-back validation only after calibration bytes verify; failure stays recorded, no silent retry or threshold change |
| 3 | Finish signal diagnostics and comparison plumbing | Separately reviewed acceptance/pinning of floors; product interval/refusal behavior, source-matched benchmark evidence and runner/trial integration; no inference enabled merely because a synthetic floor passed; synthetic end-to-end signal/skip accounting |
| 4 | Finish the portfolio and metric-sheet repairs | INR 1,000,000 edge and INR 100,000 seed rows; seed run controls promotion; standing concentration trim per approved D12; gross/cost/tax/net and per-trade export; matched-window benchmark metrics; cost stress and regime evidence; address open cost/data findings before dependent claims |
| 5 | Freeze the corrected engine and evaluation protocol | Overfitting controls (DSR/PBO/BHY) before strategy preregistration; corrected golden regression; eight published-rule candidates preregistered before evaluations; every inspected real-data evaluation counted |
| 6 | Obtain honest development results and complete Phase-1 validation | Controlled development evaluations; integrated numeric validation; final lockbox access under a separately frozen single-consumption protocol; replay parity and at least three weeks of live-data simulation with auth/restart/reconciliation/disconnect coverage; operator reviews metric sheet before Phase 2 |
| 7 | Build the live execution plane, initially one validated equity strategy | Credential/network separation; serialized risk reservation; exactly-once intents; recovery/reconciliation and protective stops; independent kill path; datastore/auth failure halts; tiny canary before full permitted size; current broker/regulatory requirements reverified at build |
| 8 | Add bounded learning and then scale on forward evidence | Typed one-change proposals, lifetime trials and spend budgets; registry lineage; automatic validation/canary/demotion/rollback; original exit rules preserved for open positions; separate approval contract for execution-policy learning; unattended-operation fault drills before claiming 24-hour autonomy |

Milestone 3 follows the existing Task-3a Step-6 ordering. The time-resolved benchmark design is approved for planning only; acquisition, subscription and product implementation have separate boundaries. Missing timing evidence produces an unavailable metric, never a daily-price approximation. Milestone 6 does not authorize lockbox use now: replay and final evaluation must be reconciled into one frozen evidence package before consuming it.

## Findings and contradictory older prose

- The living audit's old after-run table still places overfitting work later. The 2026-08-20 decision and current STATE move DSR/PBO/BHY before preregistration; use that order.
- Older TASKS text still describes crypto alongside equity and a five-trade reflection cadence. OPERATOR's equity-first deferral and current configured 15-trade cadence supersede those historical descriptions; neither expands the present build.
- OPERATOR's final open-items list still calls concentration trimming undecided; decision D12 already settles it for portfolio step 3b. Do not reopen it as a new policy question.
- F48, repeated delivery DP fees and stale-mark charging, needs a separate reviewed accounting fix before contract-note-exact cost-adjusted claims. F47, entry-only tradability masking, remains open; resolve semantics before using the mask as an exit prohibition.
- India-feed history/integration, two-source panel checks, regime stress and remaining DSL gaps need explicit completion or justified applicability/deferral when each dependent evaluation is scoped. Being absent from a current task does not close them.
- Older phase numbers in comments and diagrams are orientation, not authorization. A research module being built does not mean its runtime safety guarantees are deployed.

## Orchestration and operator decisions

For each task: explain the concrete outcome, use one bounded implementer, parallel independent reviewer angles where useful, independently verify load-bearing findings, integrate serially, run required checks, commit, and update STATE. A reviewer can reject a deliverable independently of its builder. Do not multiply abstractions or agents without a distinct purpose. Documentation-only updates are exempt from code-review skills under OPERATOR section 5b.

Operator update: the current PC is the intended host (D24); the operator requests our authentication recommendation and has not consulted a CA. In the continuation, the operator confirmed continuous PC/router power with UPS backup can be arranged; ISP identity is unknown. Feasibility is not proof UPS is installed or static IP is available. These answers do not block offline plan clarification. No broker tooling was used. Recommendations below are not recorded as accepted operator policy.

The historical September 30 code-complete target is not substantiated by today's remaining work. Re-estimate after the counted-gate milestone and host readiness; the required live simulation has a minimum three-week calendar duration. No first-trade date or profitable outcome is promised.

## Host, authentication and tax follow-up

Fresh read-only host inspection: Windows 11 Pro 64-bit, Ryzen 5 5600 (6 cores/12 threads), 15.9 GiB RAM and about 314 GiB free on C:. WSL lists only stopped Docker Desktop, not a deployed Ubuntu environment. AC sleep timeout is 10,800 seconds (three hours). No settings changed. This is candidate hardware, not an operational acceptance result. Decide the Linux deployment arrangement after checking workload isolation, restart behavior and resource headroom; confirm always-on availability, UPS and static public-IP/CGNAT status before live-data simulation deployment. Do not infer ISP capability from a private LAN address.

Authentication recommendation: use the official manual browser login each trading day, automate the documented token exchange after that login, and alert/halt the affected plane when authentication is absent. Call this a short daily login, not a guaranteed literal one-tap experience. [Kite's current login documentation](https://www.kite.trade/docs/connect/v3/user/) says tokens expire at 6 AM the following day. [Zerodha's published developer guidance](https://kite.trade/forum/discussion/11871/kite-api-apps-and-totp-requirments) explicitly advises against automated login; that statement is dated September 2022 and should be reconfirmed before Phase-2 deployment. No password/TOTP automation is recommended or authorized here. Sources checked 2026-09-27.

Tax recommendation: retain the documented capital-gains assumption as provisional, make both capital-gains and business-income stress visible, and do not treat automation or delivery settlement as proof of capital-gains status. [CBDT Circular 6/2016](https://www.incometaxindia.gov.in/documents/20117/6507196/Circular-no-6.pdf/f1d2c4d8-df3c-27fb-6ac4-5c4b98ceb52e?t=1762868058099) gives a consistency-based assurance for listed holdings longer than 12 months and treats other cases as fact-specific; it does not automatically protect shorter systematic trades. [The Department's share-sale guide](https://www.incometaxindia.gov.in/en/sale-of-shares) distinguishes investment assets from trading stock. Sources checked 2026-09-27; this is planning guidance, not a personal tax determination. Ask a CA for a written view using expected holding periods, frequency/turnover, investment-versus-trading records and funding source; also ask about current-year law, loss setoff, advance tax, books/audit and filing requirements. No tax config or rates were changed.
