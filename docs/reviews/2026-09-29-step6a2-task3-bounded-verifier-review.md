# Step 6a.2 Task 3 — bounded saved-result verifier review

**Status: implementation reviewed and locally verified; exact-commit Linux resource proof pending.** This repair changes how the already saved synthetic result is checked. It does not draw a reserved stream, accept a statistical floor, enable product inference or permit trading.

## Why it was needed

The first full-size [native proof](2026-09-29-step6a2-task3-native-resource-proof.md) failed safely because the verifier's memory projection multiplied the **whole** saved result by 32. The writer already emitted chunks, but completion and calibration-to-validation handoff loaded the complete file. Real test-seed validation therefore could not publish a complete result under the frozen 2 GiB address-space limit.

## Repair and independent review

- The result remains one canonical JSON file. The verifier now reads fixed 64 KiB blocks and recomputes one frozen 256-replicate chunk at a time. It checks exact field order, canonical JSON, all event partitions and parity records, counts, confidence bounds, verdict and selected floor. Completion and validation startup use the same bounded path.
- Full-file hashing, a second independent hash pass, retained descriptor identity, extent checks, deadline, resource sampling, fail-closed cleanup and private same-process completion authority remain in place.
- The frozen topology and a conservative maximum parity representation derive per-chunk caps of 1,297,158 bytes for calibration and 1,313,288 for validation. The independently bounded header and closing metadata yield total result-extent caps above 2 GiB; those are **disk extents**, not memory allowances. The 2,147,483,648-byte `RLIMIT_AS` and 7,200-second deadline stay unchanged. A 4 MiB parser-fragment ceiling and `current VMS + 32 × fragment + 64 MiB` projection cover JSON temporaries and overlapping chunk objects. The native proof must still measure actual peak use.
- The CI uploader now stages any structured report in an `always()` step, including after a failed proof, so the aggregate checker receives flat artifact paths and failure evidence is preserved.

Independent GPT-6 Astra medium-effort read-only review found a trailing-`null` pure-validator regression, missing topology-derived chunk/envelope/extent caps, failure-report loss in the workflow and an off-by-one envelope formula. All were corrected before commit. The final follow-up found no remaining authority escape, chunk undercount or envelope undercount. This is a code review, not a native resource pass.

Final Windows verification passed **1,637 tests with 10 skips** in 28 minutes 38 seconds. Ruff lint and formatting passed; `mypy` passed for the changed script and for the project's 139 source files. The first full-suite attempt exposed one outdated injected-failure test double after the resource check gained a phase argument; the corrected case passed alone, then the full suite passed on the final files. Focused large-result writer, verifier and validation-handoff tests also passed.

## Remaining hold

Commit and push; confirm exact-commit ordinary Linux CI and the three full-size native modes with raw logs, structured reports and aggregate checker. Independently inspect measured RSS/VMS/time and filesystem evidence before an exact-runner whole-system attestation. No official calibration or held-back validation draw is authorized by this review.
