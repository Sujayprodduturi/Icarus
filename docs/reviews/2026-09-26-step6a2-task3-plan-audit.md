# Step 6a.2 Task 3 plan audit — pending Astra re-review

The first [Task 3 counted-gate draft](../plans/2026-09-26-step6a2-task3-counted-gate.md) was independently refuted before implementation or any frozen-stream draw. The reviewer found ten must-fix classes: one-file completion durability, cross-commit retry race, truncated-attempt discovery, dynamic-H outcome-dependent eligibility, incomplete event evidence, aggregate-forgery risk, resource-limit gaps, code-review commit circularity, calibration path-swap risk, and an overbroad clean-tree allowance.

The draft was revised to add a stable full-manifest-hash phase claim, one immutable result JSON plus a separate completion seal after byte verification, exact event partitions and numeric CP recomputation, predeclared eligibility, preallocation/OS memory and monotonic deadline checks, reviewed protected-code versus invocation-commit identity, secure result-handle validation, and exact artifact-path allowances.

**Status:** revised plan is **not yet Astra-approved** and does not authorize Task 3 code or calibration. The requested Astra re-review could not be dispatched because the agent service reported its thread limit. The parent Step 6a.2 plan and all frozen values remain unchanged. The first protected calibration/validation draw is still prohibited pending implementation and independent review of the exact committed runner.
