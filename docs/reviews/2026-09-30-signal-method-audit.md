# Signal uncertainty research audit
Date: 2026-09-30. Scope: current Phase-1 statistical-method continuation. This is not a whole-runner attestation. Original post-backtest findings/repair schedule and the Task-3 runner audit retain their own ID namespaces.

## Ranked fix list
| ID | Finding | Status | Evidence / required next action |
|---|---|---|---|
| M1 | Original candidate intervals fail non-reserved serial and rare/discrete/skewed coverage/tails | OPEN | [Full selected-cell diagnosis](2026-09-30-test-calibration-failure-diagnosis.md): cell 28 required by every existing floor, raw/win coverage 79.10%/78.71%; independent cell 1 also fails. Review [one-candidate research design](../plans/2026-09-30-signal-method-research-design.md), then obtain its concrete scope approval before implementation. No product method accepted. |
| M2 | Covariance-only changes and merging blocks do not establish valid intervals | OPEN | Windows throwaway probe in the new design: merging quartets raises serial raw coverage to 1,849/2,048 yet rare-magnitude raw remains 1,739/2,048; ordinary-t lag-4 HAC lowers independent rare-win coverage to 1,822/2,048. Fixed-b candidate itself has not been tested. |
| M3 | Coverage/emission alone can reward uninformative intervals | OPEN | Proposed research must report widths, tails, bias and known-effect informativeness controls, with a deterministic vacuity sentinel. Product power/width limits need prior review before later confirmation, never post-hoc adoption. |
| P1 | Windows official resource and durable-claim equivalence unestablished | OPEN | [Reviewed investigation design](../plans/2026-09-30-windows-calibration-support-design.md): official startup still refuses before claim/RNG. Current-PC research does not establish those barriers. |
| R1 | CI integration skips do not prove datastore integration | OPEN | Historical Task-3 audit F11 retains this requirement; four Linux integration skips and six Windows platform skips remain disclosed. No new integration claim. |

## Historical runner-audit correction
Task-3 historical audit F13 described the first native whole-file-reader memory failure as open. The bounded-reader repair subsequently passed exact-source native proof/CI at `81fc971` and again at `cdf127b`, as independently verified in the [current Windows/remote evidence record](2026-09-30-windows-simulator-check.md). That original memory failure is resolved for those sources; it is not the current Windows platform blocker. This correction does not extend the old official attestation to later ancestry.

## Held boundaries
No frozen gate/manifest edit, official draw, accepted floor, real-data trial, lockbox access, inference enablement or broker/live path. The research design is concrete and reviewable; its operator implementation approval remains pending. Update this list when research evidence closes a finding; a proposed design does not close a statistical failure.
