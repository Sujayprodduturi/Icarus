# STATE.md — where Icarus actually is, today

Updated2026-10-05 after full-runner build and power-failure recovery.

**Current milestone: full runner implemented; readiness FAILED.** Unit3/R4 and Task3a/M1-M4/F48 remain OPEN. No actual attempt/key/draw, real-market/official/lockbox/broker/live path or inference enablement.

The runner has full-count generation, separate primary/reviewer verification, once-only claims/key release, fail-closed owned-process completion, bounded resources, append-only records and verified raw-only cleanup. Saved records cannot restore authority after a restart. Exact33-file manifest118de923 is independently reviewed.

**Verified:**148 focused production tests passed206.61s; fresh broader762 calendar/portfolio/synthetic-characterization/audit tests passed373.48s on final test bytes. Strict179-source mypy, global no-cache Ruff and345-file format checks pass. Both independent checkers reproduce8 saved phases/80 histories/224 metrics and complete record/resource/timing chains.

**Budget blocker:**all3 complete cold measurements15.578/15.703/15.625s fail both retained timing models. With unchanged2x margin and independent global maxima:
- Development writer8.03h versus6h.
- Validation writer32.13h versus12h.
- Each validation verifier23.90h versus16h.
- Complete session156.26h versus82h10m.

These are conservative one-set projections, not measured multi-day runtimes or a proven optimum. Original32-file baseline and every12/14-hour failure remain unchanged. No threshold or resource allowance was raised.

**Retention:**exactly8 fresh dual-verified raw files removed under D44; compact phase/registry/math/process/source/timing/cleanup evidence remains. Raw replay UNAVAILABLE. Unverified/incomplete fixtures are not removed by this cleanup.

**Next:**complete progress commit/postcommit deliberate-defect restoration/push provenance, then the independently reviewed bounded [cost-profile task](plans/2026-10-05-calendar-score-full-runner-cost-profile.md) to identify repeated costs before one exact-output optimization. Profiling has not started. Actual sampling remains held before the readiness milestone; no routine operator decision is pending for the profiling design.

**Fixed inputs:**protocol130569a7, goal c886aca6, resource96199af0, original full-runner plan5818b086 and refinement ae14fa20. Source/runtime changes require fresh qualification. Jev/Laya remain optional future text classifiers; neither is adopted.

[Qualification and limitations](reviews/2026-10-05-calendar-score-full-runner-qualification.md), [all-three compact evidence](reviews/2026-10-05-calendar-score-full-runner-refinement-benchmarks.json), [cleanup proof](reviews/2026-10-05-calendar-score-full-runner-refinement-cleanup.json), [independent review](reviews/2026-10-05-calendar-score-full-runner-review.md).

Older checkpoints are preserved in [the historical STATE snapshot](reviews/2026-10-05-state-history-before-full-runner-checkpoint.md) and [HANDOVER.md](HANDOVER.md). Their stale next-task or completion claims do not override this page.
