# Icarus documentation map

Start with [STATE.md](STATE.md), especially its **Resume here** section for a new session: it is the current build position and the source of truth for what is complete, in progress, or blocked. Then read [OPERATOR.md](../OPERATOR.md) for working decisions and [TASKS.md](../TASKS.md) for the ordered build and acceptance criteria. [PRD.md](../PRD.md) is the full product and safety specification; [AGENTS.md](../AGENTS.md) is the short safety contract.

## Current work

- [2026-09-27 orchestration roadmap](plans/2026-09-27-orchestration-roadmap.md): verified handover, immediate plan blockers, milestone sequence toward autonomous trading, and operator follow-ups.

- [Task 3a plan](plans/2026-08-22-signal-test.md): ordered signal-test work and scope boundaries.
- [Step 4 record contract](plans/2026-09-25-signal-records.md): the implemented stable signal identity and outcome records.
- [Step 5 simulator contract](plans/2026-09-25-signal-simulator.md) and [implementation plan](plans/2026-09-25-signal-simulator-implementation.md): implemented synthetic-only simulator, committed at `997bbd2`.
- [Step 5b portfolio discard ledger plan](plans/2026-09-25-portfolio-discard-ledger-implementation.md): implemented at `ed9f46b` with synthetic-only tests and unchanged portfolio trade/equity/cost trace.
- [Time-resolved benchmark design](plans/2026-09-26-time-resolved-benchmark-design.md): operator-approved source-neutral stock/Nifty timing and provenance contract for Step 6 planning; no daily-price alpha approximation or product code is enabled.
- [Step 6 statistical design](plans/2026-09-26-signal-statistics-design.md): Astra- and safety-reviewed clustered-uncertainty and benchmark-refusal contract; inference remains disabled.
- [Step 6a.1 estimator implementation](plans/2026-09-26-step6a1-estimator-implementation.md) and [final review](reviews/2026-09-26-step6a1-final-review.md): Tasks 1–2 complete through `88d0417`; this is a partial Step 6a foundation with synthetic-only CR2/Satterthwaite candidate moments. Next is the pre-registered Step 6a.2 calibration protocol; there are no intervals, accepted floors, benchmark alpha, or real-data runs.
- [Step 6a.2 synthetic calibration plan](plans/2026-09-26-step6a2-calibration-implementation.md), [Astra plan review](reviews/2026-09-26-step6a2-plan-review.md), and [Task 1 manifest/preflight review](reviews/2026-09-26-step6a2-task1-review.md): the frozen protocol and analytic preflight are committed through `eb90def`; Task 2 offline generator/evaluator is committed at `13ccece` after [independent and Astra review](reviews/2026-09-26-step6a2-task2-review.md). Task 3 counted phase gate is next; its [revised draft plan](plans/2026-09-26-step6a2-task3-counted-gate.md) and [adversarial audit](reviews/2026-09-26-step6a2-task3-plan-audit.md) received [Astra re-review on 2026-09-27](reviews/2026-09-27-step6a2-task3-rereview.md): architecture accepted, three plan clarifications still block implementation approval. No calibration or validation stream has been drawn, and no inference floor exists.
- [Trade-lineage and learning proposal](plans/2026-09-24-trade-lineage-learning.md): later work, not current implementation or promotion authority.
- [Newest ranked audit](reviews/2026-08-09-post-backtest-audit.md): known findings, including items not yet scheduled in TASKS.

## Visual map

The current visual orientation is three titled, layered boards. Each has an editable SVG source and a rendered PNG in `diagrams/`:

1. [System map: Phase 1 research boundary](../diagrams/icarus-system-map-2026-09-25.svg) — what is built, what is next, and how future learning/live execution stay separate.
2. [Task 3a: one signal, one outcome](../diagrams/icarus-signal-outcomes-2026-09-25.svg) — the Step 4 record contract and implemented Step 5 synthetic simulator path.
3. [Evidence roadmap](../diagrams/icarus-evidence-roadmap-2026-09-25.svg) — completed repair, the next implementation slice, later diagnostics, and the operator gate.

The older `icarus-status-*`, `icarus-task3a-*`, and `icarus-safe-loop-*` diagrams remain as dated history, not the current map. Status words inside the new boards are authoritative; colors are secondary. These snapshots are not acceptance evidence. A *built* research component is not deployed, and there is no live order path in Phase 1. Check [STATE.md](STATE.md) for the latest build position.
