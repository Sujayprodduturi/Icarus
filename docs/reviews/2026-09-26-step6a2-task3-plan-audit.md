# Step 6a.2 Task 3 plan audit — historical draft review

**Update 2026-09-27:** Astra re-review is now complete; see the [new verdict](2026-09-27-step6a2-task3-rereview.md). The later approval addendum closes the three bounded plan clarifications and approves implementation under the exact contracts. Frozen draws still require independent approval of the completed runner. The handover paragraph below records the earlier state.

The first [Task 3 counted-gate draft](../plans/2026-09-26-step6a2-task3-counted-gate.md) was independently refuted before implementation or any frozen-stream draw. The reviewer found ten must-fix classes: one-file completion durability, cross-commit retry race, truncated-attempt discovery, dynamic-H outcome-dependent eligibility, incomplete event evidence, aggregate-forgery risk, resource-limit gaps, code-review commit circularity, calibration path-swap risk, and an overbroad clean-tree allowance.

The draft was revised to add a stable full-manifest-hash phase claim, one immutable result JSON plus a separate completion seal after byte verification, exact event partitions and numeric CP recomputation, predeclared eligibility, preallocation/OS memory and monotonic deadline checks, reviewed protected-code versus invocation-commit identity, secure result-handle validation, and exact artifact-path allowances.

**Handover status (2026-09-27):** revised plan is **not yet Astra-approved** and does not authorize Task 3 code or calibration. The 2026-09-26 Astra re-review attempt hit the agent service's thread limit; retry it first in the new session. Specifically ask whether the stable phase claim and completion-seal sidecars preserve the parent plan's single immutable result, whether the hard 2 GiB cap is implementable on the target platform, and whether the reviewed-code/invocation-commit separation is sound. Record the verdict and any required plan change before implementation. The parent Step 6a.2 plan and frozen values remain unchanged. The first protected calibration/validation draw remains prohibited until the completed runner receives exact-commit independent statistical/safety approval.

## 6. Ranked fix list

These IDs are local to this historical plan audit. `DECIDED` means the approved contract resolves the design question; implementation and exact-runner verification remain pending. See the current execution ledger for built slices.

| ID | Finding | Status | Why it ranks here |
|---|---|---|---|
| F1 | One-file completion durability | DECIDED: independent completion seal after reread | Partial bytes must never authorize validation |
| F2 | Cross-commit retry race | DECIDED: stable per-phase exclusive claim | Prevent a second counted attempt |
| F3 | Truncated-attempt discovery | DECIDED: retain claim even after abrupt failure | Incomplete attempts remain consumed |
| F4 | Dynamic-H outcome-dependent eligibility | DECIDED: frozen deterministic eligibility | Prevent selection using observed outcomes |
| F5 | Incomplete event evidence | DECIDED: exact event partitions and parity records | Evidence must support recomputation |
| F6 | Aggregate-forgery risk | DECIDED: recompute counts and CP checks | Supplied summaries have no authority |
| F7 | Resource-limit gaps | DECIDED: Linux capability proof; Windows refusal | Enforce limits before counted draws |
| F8 | Code-review commit circularity | DECIDED: reviewed versus invocation commit ancestry | Bind review to executed code |
| F9 | Calibration path-swap risk | DECIDED: retained handles and identity checks | Validate the bytes actually opened |
| F10 | Overbroad clean-tree allowance | DECIDED: exact verified artifact paths only | Prevent unrelated evidence allowances |
| F11 | CI can succeed while database integration tests skip | OPEN (found 2026-09-27): run `36305873021` passed 1,397 tests with four skips; integration fixtures allow missing database/migrations and CI has no migration step | Do not equate CI success with integration proof; separately require migrated services and fail on missing integration prerequisites in CI |
| F12 | Completion-seal finalization cannot be inferred from surviving bytes | DONE — 4B accepted at `bcaa900` under operator D29 (2026-09-28): inert candidate bytes plus same-process completion authority preserve strict limits and refuse restart recovery | Implement and verify the exact Slice 4B contract in `../plans/2026-09-28-step6a2-task3-completion.md`. Candidate files alone grant no authority; validation consumption and combined invocation remain later reviewed work. |

### Follow-up inspection finding — claim close ownership (2026-09-28)

At accepted code `e406a7b`, `_write_immutable_claim` closes the writer before clearing `writer_owned`. Root reproduced the failure against committed source in an isolated in-memory fake filesystem: a close that releases the writer, reuses its descriptor for an unrelated sentinel, then raises leads to two close attempts and closes the sentinel. No tracked source or real evidence was altered. A narrow adjacent repair is authorized with Slice 4B: relinquish ownership before the single close and add that exact regression witness. The separate candidate writer must prove the same rule independently. Resolved in reviewed code `bcaa900`: ownership is relinquished before close, the exact regression passed independently, and the final root full suite passed 1,557 tests. Exact Linux CI passed 1,562 tests/four pre-existing integration skips, including native completion and fork rejection.

## 7. Current implementation tracking

The [2026-09-27 execution ledger](2026-09-27-step6a2-task3-progress.md) tracks implementation and fresh verification. Plan approval is not completed-runner approval.
