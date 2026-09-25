# Icarus documentation map

Start with [STATE.md](STATE.md): it is the current build position and the source of truth for what is complete, in progress, or blocked. Then read [OPERATOR.md](../OPERATOR.md) for working decisions and [TASKS.md](../TASKS.md) for the ordered build and acceptance criteria. [PRD.md](../PRD.md) is the full product and safety specification; [AGENTS.md](../AGENTS.md) is the short safety contract.

## Current work

- [Task 3a plan](plans/2026-08-22-signal-test.md): ordered signal-test work and scope boundaries.
- [Step 4 record contract](plans/2026-09-25-signal-records.md): the specific implementation contract for stable signal identity and one outcome per signal.
- [Trade-lineage and learning proposal](plans/2026-09-24-trade-lineage-learning.md): later work, not current implementation or promotion authority.
- [Newest ranked audit](reviews/2026-08-09-post-backtest-audit.md): known findings, including items not yet scheduled in TASKS.

## Visual map

The current visual orientation is three titled, layered boards. Each has an editable SVG source and a rendered PNG in `diagrams/`:

1. [System map: Phase 1 research boundary](../diagrams/icarus-system-map-2026-09-25.svg) — what is built, what is next, and how future learning/live execution stay separate.
2. [Task 3a: one signal, one outcome](../diagrams/icarus-signal-outcomes-2026-09-25.svg) — the Step 4 record contract and proposed Step 5 simulator path.
3. [Evidence roadmap](../diagrams/icarus-evidence-roadmap-2026-09-25.svg) — completed repair, the next implementation slice, later diagnostics, and the operator gate.

The older `icarus-status-*`, `icarus-task3a-*`, and `icarus-safe-loop-*` diagrams remain as dated history, not the current map. Status words inside the new boards are authoritative; colors are secondary. These snapshots are not acceptance evidence. A *built* research component is not deployed, and there is no live order path in Phase 1. Check [STATE.md](STATE.md) for the latest build position.
