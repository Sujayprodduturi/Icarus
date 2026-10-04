# Operational budget amendment: code review

Date: 2026-10-04. Candidate study SHA `c2a5055c0ecdfe7f4b0ec9d5c7c55353d80cc22e9e1df2bca6111673b723a8b3`, verifier `dee76774e67c38075e2ee5f133218977e20f7c2e5e497c3efd14d58a039a1449`; contract `8a2225727e08cb7eb848e46ab856eca5649d727c15a101f0ab1bb3d9a1d313bc`; plan `791c0a23b43dce002d6ecbeeccf610a679f91ae63f22d6561f6a35fc226c4849`.

Ordered simplicity then engineering/governance review: localized loader/dataclass and record wrappers avoid unbuilt authority scaffolding. Whole-file/source pin, baseline predecessor, canonical boolean discrimination, bounded parsing, actual evidence hashes and UTC timestamp checks satisfy the resource-history design. Existing failure wrappers explicitly supply captured bindings/null and avoid default loader re-entry; no sampled authority is added. Independent mathematical core remains unchanged.

## Blocking finding

P1, `_read_preflight_receipt`: fresh operational binding and budget-comparison fields are validated, but `eligible` itself is trusted. A fully rehashed receipt with both verification projections60000 seconds, correctly recomputed effective eligibility=false and top-level eligible=true is accepted and returned as eligible. A bounded reviewer in-memory reproduction replaced only the canonical-record reader and produced `accepted eligible=True effective_validation=False`; no source/disk artifact mutation occurred. Recompute the composite result from validated counts, worker/verifier projections and existing resource bounds, then require an exact boolean match. Include fully rehashed contradictory eligibility and bool-as-int failure tests. Approval for new effective-budget qualification is withheld pending correction.

A separate route question remains for the direct `execute_preflight` API: it creates an evidence root before loading the contract but has no outer durable failure recorder; the supervised parent does record such failures. Either cover this public direct route or explicitly constrain it as an internal helper under the supervised boundary, consistent with the plan's missing/corrupt-after-root guarantee. No heavy suite or benchmark was run by this reviewer during the parent's checks.

## Corrected candidate review

Fresh hashes confirm study `78fa9ea1041df6eddbe0f4f48cb61daacee4c2937d3aa45fe914f12b9c1269ed`, verifier `40f40acd5096f69b52e7694317c67c2fd6213b543f02f7514d174385e569cb02`, study tests `5a1d3c0d0e6375904ba7c35ec562b31ef3ccedf5b99935c63de3ef7e8e8caa75`, verifier tests `a81aec072d1ab356c0554033d46d6d1b5ffc18c490747c3232ec19fa1b945bd4`.

Ordered review closes the receipt finding: intake now requires exact fields/types, trusted plan, recomputed projections/counts, both fresh budget comparisons and exact composite eligibility. Six fully rehashed contradiction cases exercise verification/generation/count/boolean/RSS/disk failures. The direct preflight wrapper now captures resources and durably records missing/corrupt/drift failures after guarded root creation. The verifier failure writer now guards exists/binding/open errors and notes secondary persistence failure without replacing the original exception.

One instance of the same secondary-error issue remains in `run_supervised_preflight`: its exception branch still performs failure-file exists and captured-binding/payload construction outside the persistence try. A filesystem exception there masks the original resource refusal. Move the complete failure-record branch inside the existing guarded persistence boundary, and test a secondary exists failure. Cancellation errors should likewise be noted while preserving the triggering error and still attempting termination. This is a surgical completion of the already-required failure-honesty fix; approval remains held until resolved.

## Final corrected freeze: source GO

Fresh filesystem hashes confirm study `abd6f6cb7ff92802eebd1efa696b3a38bcb0080ff2c7f11009f2e970f4255231`, verifier `40f40acd5096f69b52e7694317c67c2fd6213b543f02f7514d174385e569cb02`, study tests `2be94e1913dea4f1cf82d1b18004eaa6ef6a9ad99be11dc853c82c6cba60c0c3`, verifier tests `a81aec072d1ab356c0554033d46d6d1b5ffc18c490747c3232ec19fa1b945bd4`. Contract and final plan remain the8a222572/791c0a23 versions above.

Ordered simplicity then engineering/governance review closes the remaining finding. Supervised cancellation and failure-evidence persistence have separate guarded boundaries; secondary poll/kill/exists/binding errors attach notes to the original exception and cannot suppress the subsequent evidence attempt. Four regression cases assert exact original-exception identity, no success receipt, and retained failure evidence for cancellation failures. The reviewer read these tests and retained logs:201 focused tests passed in12.24s, strict four-file mypy and Ruff clean. No further source blocker found.

GO for the three declared supervised cold full-workload budget-amended benchmarks after the root's final broad regression/static gates pass. The reviewed operational contract may now be evaluated with explicit original43200/effective50400 comparisons; no existing failure is relabelled. Actual all-three effective qualification, saved all-path verification and cleanup approval remain outstanding. No sampled authority, study key or long-session reliability claim follows.

## Saved amended-budget benchmarks: correctness accepted, overall qualification failed

The independent reviewer replayed all three `verifier-budget-amended-final-1..3` roots with a standalone literal scalar SHA, naive integer trade-sum and finite-truth/rational-endpoint oracle importing no project math. Every10-path/28-metric set,1388952 words and231492 raw bytes matched. The reviewer also verified the entire canonical operational contract against its reviewed SHA, both history-entry digests/predecessor/acknowledgement and actual evidence hashes; fresh source closure before/after, direct artifact resource bindings, claim/index/report/terminal/receipt/candidate identity, all summary cells and both old/new projection comparisons passed. Exclusive fsynced reviewer receipts with the exact four-field resource binding were retained. Oracle elapsed1.9672999/1.9261068/1.9320057s; ending RSS below23MiB, not a peak claim.

All three bind payload `816a0ae0a31c0cf97bf3fd1aa309b063551951305b4dfaac78370db22759afc2`, index `2ede63a4d112feb8ec20d7f873712cfe2ea9a91e3e2188719c3cb42c13653058`, terminal `c3ec2fb063f119d0ec29f256397b3c306d2a8cc126fba1b7c22df7311a7e1031`, and manifest `a76ffe13e11555831eeb6084a376069eb6686c25cddf5d3009ce75047f3ad68e`.

Effective-budget outcomes are false/false/true. Projections50,691.2702456/50,411.4970627/49,665.9791870 seconds mean the worst exceeds50,400: overall qualification remains FAILED. All three original43,200-second validation comparisons remain false. The one passing run cannot replace the declared all-three/worst rule; no budget auto-adjustment is approved. Any further exact-equivalent optimization needs its own reviewed change and fresh measurements.

Reviewer approves only exact231492-byte raw payload cleanup for these three roots after matching primary receipts and the existing ancestor/regular-file/identity/hash/durable-intent protocol. Keep all bindings, endpoints, counters, failures, verification and cleanup provenance. No reviewer cleanup was performed; no sampled authority follows.
