# Runner operational cost accounting amendment

Date: 2026-10-06
acknowledged_post_hoc: true
Status: architecture reviewed; implementation and fresh qualification required.

This append-only operational amendment follows the failed 94d6be4f three-case qualification (161.34h projected session versus82h10m allowance). Those failures and both previous models remain valid historical records. They are projections, not observed multi-day runtimes. The original5818b086 plan and ae14fa20 timing refinement remain byte-unchanged. No original result is overwritten.

The existing model deliberately multiplies once-per-stage shutdown and once-per-session bounded overhead by history count. The new model separates only source-proven fixed work. This does not promise feasibility. Statistical counts, random streams, acceptance thresholds, risk/data restrictions, the2x timing margin and all operational limits stay unchanged.

## Owned stage accounting

Child READY remains before capability issuance or data work. Add an authenticated WORK_FINISHED heartbeat immediately after write_phase/verify_phase returns with closed and durable proportional output, before monitor retirement. Serialize heartbeat writes. Parent validates exact source, owner, child, claim, kind, role and final expected counts before recording its own monotonic reception time. Reject early, duplicate, malformed or changed-count markers. Subsequent ACTIVE frames may only repeat completed counts.

READY-to-WORK_FINISHED remains repetitive, including capability, replay, cache and mathematical work. Post-WORK overhead is fixed only after successful existing completion checks: DURABLE_FINISHED, exact ACK, exit0, all resource/source/lifetime/path guards and authoritative publication. A work marker alone grants no success or runtime authority.

Every proportional payload/index scan and decode after WORK remains repetitive. Instrument full guarded payload/index hash spans without changing checks; any other proportional or unclassified post-work operation stays repetitive. Bounded metadata/control waits and retirement may be fixed only with explicit source justification. Never relabel work because a timing would become favorable.

Cost observations are immutable and identity-issued in-process, bound to the original live READY observation, owner/child/source/root/kind/role, all parent clocks, counts and scan intervals. Copied, unissued or favorably shifted observations refuse. All spans must be finite, nonnegative, contained, disjoint and counted once. Fixed plus repetitive must exactly reconcile with the original complete owned stage clock.

## Whole-session accounting

Initial control setup keeps its existing source-proven boundary. Separately measured fixed32MiB storage probe and final coordinator/helper retirement may be fixed. Retirement ends before any final evidence scan or publication containing proportional reads. Every other residual, including approval/data-capable intervals and final pipeline index scans, stays repetitive.

Stage and whole fixed/repetitive components must reconcile exactly with all original outer clocks. Use independently worst fixed and repetitive observations for every role across both phases and all three fresh cold cases, independently worst fixed control and repetitive residual. Preserve old ALL_REPEATED and STARTUP_REFINEMENT fields/verdicts; add the operational model without pretending old failures passed.

Stage bound:2*(max_fixed_role + phase_replicates*max_repetitive_role).
Session bound:2*(max_control_setup + max_pipeline_retirement + max_disk_probe + sum_phases_and_roles(max_fixed_role + phase_replicates*max_repetitive_role) + max_phase_replicates*max_repetitive_residual). Take every fixed-control bucket maximum independently across all three cases, never max(their per-case sums).
Unchanged limits: development writer21600s, validation writer43200s, each verifier57600s, complete session295800s. Complete measurement remains bounded600s. Three locally favorable runs cannot replace the independently mixed global worst-case decision.

## Proof and authority requirements

Meaningful RED/GREEN covers injected retirement/scan delays, bad/early/duplicate WORK markers, changed counts after WORK, missing final ACK, forged/copied observations, overlapping/negative/nonfinite clocks and scans. Existing failure/halt paths remain enforced. Engineering/safety review independently checks proportional reads and source closure.

Include this amendment in the complete34-file source closure. Source changes invalidate qualification. Three new full-geometry two-phase public PREF runs must execute on the final frozen manifest. Primary and independent reviewer reproduce all saved paths, math, provenance and all three model projections before any D44 raw-only cleanup. Regression, typing, lint, format and commit/restoration requirements remain.

Saved records grant no runtime permission. Actual sampled execution requires genuine fresh in-process readiness plus all original phase/once-only/resource/approval prerequisites. This amendment does not grant official reserved streams, real-market data, product adoption, broker paths or live orders. If corrected repetitive work still exceeds a budget, it remains a blocker requiring implementation improvement rather than reduced tests or relaxed thresholds.

Independent architecture review approved this design subject to implementation proof: proportional reads stay repetitive, heartbeat writes serialize, all original completion checks remain, disjoint intervals reconcile exactly, and final retirement excludes evidence scans. Numerical feasibility is deliberately unclaimed.
