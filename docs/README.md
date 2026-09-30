# Icarus documentation map

Start with [STATE.md](STATE.md), especially its **Resume here** section, then the [current handover](HANDOVER.md) for the next-session checklist. Read [OPERATOR.md](../OPERATOR.md) for working decisions and [TASKS.md](../TASKS.md) for the ordered build and acceptance criteria. [PRD.md](../PRD.md) is the full product and safety specification; [AGENTS.md](../AGENTS.md) is the short safety contract.

## Current work

- [2026-09-30 session handover](HANDOVER.md): completed exact-runner evidence, the documentation-commit attestation consequence, native-host and operator hold points, and the sequence for the first official synthetic attempt. No reserved stream has been drawn.

- [2026-09-27 orchestration roadmap](plans/2026-09-27-orchestration-roadmap.md): verified handover, immediate plan blockers, milestone sequence toward autonomous trading, and operator follow-ups.

- [Task 3a plan](plans/2026-08-22-signal-test.md): ordered signal-test work and scope boundaries.
- [Step 4 record contract](plans/2026-09-25-signal-records.md): the implemented stable signal identity and outcome records.
- [Step 5 simulator contract](plans/2026-09-25-signal-simulator.md) and [implementation plan](plans/2026-09-25-signal-simulator-implementation.md): implemented synthetic-only simulator, committed at `997bbd2`.
- [Step 5b portfolio discard ledger plan](plans/2026-09-25-portfolio-discard-ledger-implementation.md): implemented at `ed9f46b` with synthetic-only tests and unchanged portfolio trade/equity/cost trace.
- [Time-resolved benchmark design](plans/2026-09-26-time-resolved-benchmark-design.md): operator-approved source-neutral stock/Nifty timing and provenance contract for Step 6 planning; no daily-price alpha approximation or product code is enabled.
- [Step 6 statistical design](plans/2026-09-26-signal-statistics-design.md): Astra- and safety-reviewed clustered-uncertainty and benchmark-refusal contract; inference remains disabled.
- [Step 6a.1 estimator implementation](plans/2026-09-26-step6a1-estimator-implementation.md) and [final review](reviews/2026-09-26-step6a1-final-review.md): Tasks 1–2 completed through `88d0417`; candidate moments are synthetic-only. Step 6a.2 now has a reviewed counted runner, but no official result or accepted floor.
- [Step 6a.2 synthetic calibration plan](plans/2026-09-26-step6a2-calibration-implementation.md), [exact Task 3 contracts](plans/2026-09-27-step6a2-task3-contracts.md), [execution ledger](reviews/2026-09-27-step6a2-task3-progress.md), and [whole-runner review](reviews/2026-09-29-step6a2-task3-whole-runner-review.md): Tasks 1–2 are frozen/offline; Task 3 code passed exact-source CI and full-size native test-only proof at `81fc971`, with attestation at `614fa7a`. This documentation commit requires renewed exact-commit attestation before any guarded invocation. The first reserved draw also requires a native host and separate operator decision. See [HANDOVER.md](HANDOVER.md).
- [Trade-lineage and learning proposal](plans/2026-09-24-trade-lineage-learning.md): later work, not current implementation or promotion authority.
- [Newest ranked audit](reviews/2026-08-09-post-backtest-audit.md): known findings, including items not yet scheduled in TASKS.

## Visual map

The current visual orientation is three titled, layered boards. Each has an editable SVG source and a rendered PNG in `diagrams/`:

1. [System map: Phase 1 research boundary](../diagrams/icarus-system-map-2026-09-25.svg) — what is built, what is next, and how future learning/live execution stay separate.
2. [Task 3a: one signal, one outcome](../diagrams/icarus-signal-outcomes-2026-09-25.svg) — the Step 4 record contract and implemented Step 5 synthetic simulator path.
3. [Evidence roadmap](../diagrams/icarus-evidence-roadmap-2026-09-25.svg) — completed repair, the next implementation slice, later diagnostics, and the operator gate.

The older `icarus-status-*`, `icarus-task3a-*`, and `icarus-safe-loop-*` diagrams remain as dated history, not the current map. Status words inside the new boards are authoritative; colors are secondary. These snapshots are not acceptance evidence. A *built* research component is not deployed, and there is no live order path in Phase 1. Check [STATE.md](STATE.md) for the latest build position.
