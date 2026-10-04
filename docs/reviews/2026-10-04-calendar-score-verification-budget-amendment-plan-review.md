# Operational verification budget amendment: implementation-plan review

Date: 2026-10-04. Exact plan SHA-256 freshly verified: `727401f50e8ba28283b65db229358481041002c46d78b41a737de6eb45e3857c`.

Verdict: APPROVED for the bounded deterministic contract/loader/artifact integration build. This approval does not itself activate14h qualification, approve sampled execution or reinterpret existing12h failures.

The original draft had two material gaps: self-consistent amendment hashes could be rewritten before first manifest creation, and failure persistence could accidentally reload the invalid contract it was trying to report. The corrected plan closes both. Production loading pins the whole authored canonical contract in reviewed code in addition to baseline/history digests; test overrides require an explicit expected digest and are not exposed through CLI/environment. Error persistence uses only captured binding or explicit null/error, without loader/manifest re-entry, and must preserve the original refusal. Missing/corrupt-after-root and changed-after-valid failure tests are required.

The strict bounded schema, immutable two-entry history, dated resource-only post-hoc acknowledgement and exact43200/50400 comparisons are coherent. Verification limits50400/(2*32768)=0.76904296875s and legacy43200/(2*32768)=0.6591796875s are correct. Statistical counts/gates/stream and6h/12h study-worker limits stay unchanged. The stable experiment identity is distinct from resource versions so a future amendment cannot reset an exhausted attempt. Future Unit2/3 bindings are deferred requirements, not authority scaffolding to build now.

Fresh contract reads, source closure, canonical direct/transitive artifact bindings and unchanged publication/error handling require source-level review after implementation. Temporary/custom manifest tests must still bind an actual validated resource policy. Historical artifacts lacking policy are preserved and cannot silently qualify through new routes. Existing full timing costs and monitored limits remain intact.

The three explicitly declared `verifier-budget-amended-final-1..3` roots must be fresh, supervised, cold and full geometry. All three must pass the effective gate using the worst time, while each retains its original12h comparison. Primary and reviewer must verify every saved byte/result and all contract/source/receipt bindings before raw-only guarded cleanup. Effective feasibility does not establish a sustained74-hour session or platform power-loss guarantee.

No remaining plan blocker. Proceed with TDD and exact source/config/test freeze, then ordered simplicity and engineering/governance review before any effective-budget qualification run. Current code remains on12h until that reviewed integration is accepted.

## Formatting-only hash ratification

Current plan SHA-256 `791c0a23b43dce002d6ecbeeccf610a679f91ae63f22d6561f6a35fc226c4849` is approved. Independent byte check proves appending exactly one LF to the current bytes reproduces the previously approved `727401f...3857c` hash. Only a redundant EOF blank line was removed; semantics and bounded implementation authorization are unchanged. Source closure must bind this final791c hash.
