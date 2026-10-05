# STATE.md — where Icarus actually is, today

Updated 2026-10-05 after the full-runner build and power-failure recovery.

**Current milestone: full runner implemented; readiness FAILED.** Unit3/R4 and Task3a/M1-M4/F48 remain OPEN. No actual attempt, study key or experimental draw. Inference remains disabled; real-market, official, lockbox, broker and live paths remain held.

The runner generates the full workload, requires separate primary/reviewer checks, enforces once-only claims and key release, stops on process/resource failures, and retains append-only evidence. Saved records cannot restore permission after a restart. The exact 33-file manifest 118de923 is independently reviewed.

**Verified:** 148 focused tests and 762 broader calendar/portfolio/synthetic-characterization/audit tests passed. After code commit e744519, all three planted defects were caught, all 33 files restored exactly, and 422 affected tests passed again. Strict typing of 179 sources, global Ruff and formatting of 345 files pass. Two independent checkers reproduced eight saved phases, 80 artificial histories and 224 metrics with complete provenance.

**Budget blocker:** all three complete cold measurements (15.578/15.703/15.625 seconds) fail both retained timing models. With the unchanged twofold margin and independent worst-case costs:

- Development writer: 8.03 hours versus 6 allowed.
- Validation writer: 32.13 hours versus 12 allowed.
- Each validation verifier: 23.90 hours versus 16 allowed.
- Complete session: 156.26 hours versus 82 hours 10 minutes allowed.

These are conservative one-set projections, not measured multi-day runtimes or a proven optimum. The original baseline and all earlier 12/14-hour failures remain unchanged. No statistical threshold or resource allowance was raised.

Exactly eight newly dual-verified raw files were removed under D44; compact results and audit evidence remain. Raw replay is unavailable. Incomplete or corrupt fixtures were not included in that cleanup.

**Next:** the independently reviewed bounded [cost-profile task](plans/2026-10-05-calendar-score-full-runner-cost-profile.md), to identify repeated costs before one exact-output optimization. Profiling has not started. Actual sampling remains blocked by readiness. Code and restoration proof pushed through 57be334; HEAD=origin/dev confirmed. Both current GitHub runs were in progress at that checkpoint; no CI pass is claimed. [Push receipt](reviews/2026-10-05-calendar-score-full-runner-push.json) records that revision; this docs-only provenance commit has separate CI.

**Fixed inputs:** protocol 130569a7, goal c886aca6, resource 96199af0, original plan 5818b086 and timing refinement ae14fa20. Source/runtime changes require fresh qualification. Jev/Laya remain optional future text classifiers; neither is adopted.

[Qualification](reviews/2026-10-05-calendar-score-full-runner-qualification.md), [all-three evidence](reviews/2026-10-05-calendar-score-full-runner-refinement-benchmarks.json), [postcommit proof](reviews/2026-10-05-calendar-score-full-runner-postcommit.json), [cleanup](reviews/2026-10-05-calendar-score-full-runner-refinement-cleanup.json). Older checkpoints are retained in the [historical snapshot](reviews/2026-10-05-state-history-before-full-runner-checkpoint.md) and [HANDOVER](HANDOVER.md); they do not override this page.
