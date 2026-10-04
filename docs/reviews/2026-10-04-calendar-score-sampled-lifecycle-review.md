# Calendar-score sampled lifecycle and first-unit design review

Date:2026-10-04. Independent focused design review. Initial reviewed SHA256 `d392438918eacc26c5e7379060c3c8ac12a0595573f42ede59076bc18cee7ad4`; actual frozen protocol `130569a78811e9ad4f9dcdb915410b3c350e137a78bc70974eb81ac4daf13b71` and optimized source `58f483289f9175fec4f96153a1e7a377cc8c26e9d61a4a4e35fc8ef67b901f5e` independently rehashed and matched. No source implementation, keys, experimental words, market data or old held evidence accessed.

## Initial finding

**P2 — Reserve the attempt before creating either seed-owning service.** The draft chooses/seals validation key before development claim, but says reviewer-helper/key loss consumes the attempt. If the first fixed-registry marker is written only after key creation, helper death in that interval leaves an empty registry and permits another session to choose a new key. Specify a distinct global exclusive durable attempt RESERVATION before helper/key creation; the later phase CLAIM binds actual seeds/commitments/counts and still precedes every study SHA. Failure after reservation exhausts the attempt even with zero consumed words. Unit1 must continue to create neither real reservation nor study seed. This ordering correction is required for the full lifecycle design; it does not invalidate the independent-verifier mathematics.

## Architecture and first-unit assessment

The division into independent verifier, later lifecycle contracts and final sampled integration is coherent. Unit1 has a concrete bounded implementation sequence with failing tests, independent equations, strict source dependency barriers, full artifact checking and measured supervision. Existing calculator, finite law, byte/word mapping and statistical protocol remain fixed. The full sampled lifecycle is explicitly unbuilt and no first-unit completion can grant sampling authority.

The largest earlier operational gap is addressed: benchmark the ACTUAL independently authored verifier, including regeneration, read/hash/schema/report checks and durable receipt, rather than reuse production replay timing. Recomputed validation per-set ceiling is43200/(2*32768)=0.6591796875s. Separate primary/reviewer invocations each have43200s; neither may conceal or pool the second check. The design properly discloses same-implementation computational replication plus independent review, rather than claiming two wholly different mathematical methods.

Numeric contract matches frozen requirements:10 families,25 formal metrics,9 joint cells,4 detections and88 one-sided statements;8192 development and32768 validation paths/family; exact validation cutoffs31258/270/29668. L1 remains diagnostic. Refusal and unexpected arithmetic/source/resource errors are incomplete ERROR; a fully reconstructed statistical FAILED result remains a valid completed evaluation, never permission to continue development failure into validation.

Source, terminal, result and cleanup bindings are appropriately explicit; typed canonical records reject bool-as-int, malformed rationals/nonfinite values, changed schema, missing/duplicate/reordered/trailing rows, hashes and offsets. Independent integer-prefix reconstruction includes a mandatory int64 bound proof or Python-integer fallback, avoiding silent vector overflow. No source/protocol adjustment can be disguised as repair after an outcome. The retained compact index permits raw-only cleanup with exact file identity and two matching checks.

## Concrete implementation checkpoints, not additional current blockers

- Benchmark fixture completeness must be labelled one complete10-history TEST set, never full8192/32768 development/validation completeness. Fixture verification can succeed while the frozen full-phase decision remains unavailable; reduced expected_paths must never yield production feasibility or phase authority.
- The later Unit2 plan must separate an authenticated reviewer-only approval transition from the coordinator's release-request channel. A coordinator that knows the shared IPC secret must not be able to manufacture the reviewer's approval. Bind approval to exact source/evidence/commitment/session, enforce once-only release and parent/helper death semantics.
- Source manifests must bind every new executable dependency and actual protocol bytes. Merely trusting a supplied manifest digest or importing production calculators indirectly is not an independent correctness check; import-trap and fault-injection tests must enforce call boundaries.
- Frozen dataclasses containing dicts are not deeply immutable. Validate/copy/canonicalize serialized values at trust boundaries and do not treat a mutable mapping as authority. This is an implementation detail with no need for a generic immutable-object framework.
- The declaration-only interface ellipses are appropriate in a design document; they are not executable placeholder implementation. The first build must replace them with tested behavior as the plan states.

Final exact-hash approval follows resolution of the reservation ordering above. No large run or experimental draw is authorized by this design review; Units2-3 still require their own concrete plans and reviewed gates.

## Final amended-design verdict

**APPROVED FOR DESIGN AND DETERMINISTIC UNIT1 IMPLEMENTATION ONLY.** Final proposal SHA256 `c32e6fe54cc9c7b5b158b0c4103cf01020981d3055d14f21df930aebfdb6fceb`, independently rehashed after rereading the amendments. The P2 ordering finding is closed: ATTEMPT_RESERVED now durably precedes helper/key creation, grants no study capability, and exhausts on any later failure even with zero words; seed-bound phase CLAIM is separate. State progression and the helper-loss-before-claim regression now encode that boundary. Unit1 explicitly creates neither reservation nor study key.

The amendment also separates reviewer-only approval authentication from coordinator release requests, clarifies shallow dataclass/dict mutability, prohibits labelling the10-path/28-result fixture as a full development phase, and includes initialization/summary/receipt/cache costs in actual verifier feasibility. No remaining design blocker found. Interface declaration ellipses are acceptable design notation, not permission to ship placeholders.

This approval does not approve implementation not yet written, Units2-3 without their concrete plans, study seed selection/reservation, experimental draws, or real-data evaluation. Unit1 still needs RED/GREEN exact and failure tests, ordered immutable-source review, actual independently authored verifier runtime proof, all-path saved verification and recorded raw lifecycle. Failed feasibility must stop undrawn; the frozen statistical protocol and resource gates remain unchanged.

## Mechanical formatting hash ratification

Independently inspected the current plan diff and recomputed SHA256 `c12129e2799e580cb0d4a7541ac304598c8ad953034eabfe2f9cd69b920a8e61`. Changes only add blank lines and wrap Python-fence declarations/test calls for Ruff formatting; prose, interface signatures, equations, gates and approved scope are unchanged. The final design/Unit1-only approval above therefore applies to this mechanically reformatted hash. No source, calculator or frozen statistical-protocol change was reviewed or authorized by this ratification.
