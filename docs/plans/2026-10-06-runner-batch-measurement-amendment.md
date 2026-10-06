# Full-geometry measured-batch timing amendment

Date: 2026-10-06
acknowledged_post_hoc: true
Status: reviewed design; source implementation and fresh qualification required.

Single-replicate4207cb70 qualification completed three genuine cold PREF workloads and dual independent verification of60 histories/168 metrics. All three accounting models fail; independently mixed operational session bound512504.244s exceeds295800s. Writer validation107546.358s exceeds43200s; verifier validation73729.720/70649.496s exceeds57600s. Those records and failures stay immutable. The operational split alone is insufficient.

A single history set still measures one-time capability/source checks and preparation inside its repeated interval. Instead of choosing favorable intercepts or guessing further fixed boundaries, measure a complete16-replicate batch and conservatively repeat that entire measured batch cost. No actual experiment counts, statistical gates, streams, operational budgets or2x margins change. Both actual phase counts8192/32768 are exactly divisible by16.

## Fixture and clock

Public PREF executes all10 existing full geometries for each distinct replicate0..15:160 paths/448 metrics per phase,3,703,872 payload bytes. Preserve every path, mathematical computation, guard, close/fsync, parent full scan, independent reviewer, source/resource/lifetime/once-only check. Both phases and all six owned workers run. Ordinary TEST remains one replicate. PREF has no experimental stream/key or study authority.

Bind measurement_batch_size=16 explicitly to the source-issued observation, claim, canonical result and readiness validation; every phase claim/index/count must prove the same batch size. Reject a changed/unissued/favorably copied batch size. A claimed divisor without the complete160 histories is never permitted.

Fresh runtime observation on this Windows Python3.12 shows time.monotonic uses GetTickCount64 with0.015625s resolution, while time.perf_counter uses monotonic QueryPerformanceCounter with1e-7s resolution. Short complete-file scans can otherwise record zero. Move runner and runner-service clocks consistently to perf_counter, including shared absolute reservation anchors, deadlines, parent observations and validity checks. Do not patch the global time module. Other components' independent relative clocks remain untouched. Tests compare the same clock and prove positive measured scans. All stored trading timestamps remain UTC; performance clocks are durations, not trading timestamps.

PREF-only local stage/control/service allowances use the existing complete-fixture600s outer ceiling so the larger fixture cannot be cut off by one-replicate15/30/90s test limits. The complete PREF remains bounded600s, not600s for each stage without an outer cap. Ordinary TEST15/30/90s limits, all actual phase/session deadlines, heartbeat limits and resource caps remain unchanged.

## Fourth accounting model

Preserve the previous three result fields and models as conservative comparisons. Add an explicitly named measured-batch model for readiness. Previously published single-replicate failures are not recalculated as successes.

For each role and scalar control bucket, take independent maxima of the RAW complete16-batch observations across both phases and all three fresh cases. Fixed measured setup/retirement/probe and role fixed costs are charged once. Stage bound:2*(max_fixed_role + (actual_replicates/16)*max_batch_repetitive_role). Session bound:2*(max_setup+max_retirement+max_probe + sum_phases_and_roles(max_fixed_role+(actual_replicates/16)*max_batch_repetitive_role) + (max_actual_replicates/16)*max_batch_repetitive_residual).

Never divide the whole bound or a fixed cost by16. Unknown/data-capable overhead remains repeated once per measured batch. Refuse a nondivisible phase count; do not round down. Actual writer limits21600/43200s, verifier57600s each and session295800s remain unchanged. Measurement/storage accounting retains all original outer clocks and disjoint intervals.

## Required proof

Meaningful RED/GREEN covers complete16 claim/count/index identities, immutable divisor binding, nondivisible actual counts, correctly scaled repeated costs with fixed costs unchanged, independently mixed maxima, high-resolution scan timing and PREF total-deadline refusal. Existing WORK/final ACK/exit0/source/resource/once-only/failure paths remain required.

Include this new document in the complete35-file source closure. Prior34-source4207 and33-source94d6 histories and amendments stay immutable. Freeze final source, pass appropriate regression/golden/static checks and ordered simplicity/engineering/safety review, then execute three NEW complete cold16-batch cases on separate fresh processes. Both independent literal oracles must reproduce every160-path phase, all metrics, provenance and all four models/group decisions before cleanup. A saved result cannot issue runtime authority.

The latest operator instruction to fix and run authorizes the isolated artificial research study after genuine same-process fresh readiness, current source and all original phase/once-only/approval/resource gates. No official reserved stream, real-market simulation, lockbox, product inference, broker or live order permission is granted. Failure of the larger fixture keeps the actual attempt untouched and requires an implementation improvement; no numerical feasibility or global optimum is promised.
