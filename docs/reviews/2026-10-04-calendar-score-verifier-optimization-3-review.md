# Verifier optimization iteration 3: plan review

Date: 2026-10-04. Freshly checked plan SHA-256: `8a569d0ac5af212cf0e69ab485c308c87fdd7907e5300ecbdd8c1da037d6e00e`.

APPROVED for the bounded implementation and declared diagnostics. No plan blocker found. This is not source or runtime qualification approval.

Current `_is_reparse` obtains lstat for Windows attributes, then calls is_symlink for another status query. Testing `stat.S_ISLNK(info.st_mode)` alongside the existing reparse attributes is equivalent for a stable filesystem and uses one coherent non-following snapshot. Preserve FileNotFoundError behavior and propagate other original errors. Each invocation must perform a new lstat. Windows junctions remain rejected through FILE_ATTRIBUTE_REPARSE_POINT even when their mode is a directory.

Under concurrent filesystem mutation the snapshots can differ; neither implementation makes path-check/open atomic. The proposal correctly discloses this rather than claiming new TOCTOU protection. Existing lexical ancestor screening, containment, descriptor/lexical identity and final fresh source checks must remain unchanged. Source review must confirm only the predicate and plan closure change.

The proposed tests cover both independent rejection mechanisms, fresh-call count, ordinary paths and error identity; retain existing guard-level ancestor/root/leaf tests. Five alternating paired diagnostics must preserve full binding/manifest equality and retain every observation. Three subsequent fresh cold benchmarks still use worst time and require all effective50400-second gates to pass while reporting legacy43200 comparisons. Contract/statistics/stream/timing boundary stay unchanged. Every saved path and receipt remains independently verifiable before raw cleanup.

This one-line predicate simplification is preferable to the rejected parsed-policy framework at the measured bottleneck. Gain and effective14h feasibility remain unproved until the declared actual runs. No sampled authority or global-optimality claim follows.

## Exact source approval

Fresh filesystem hashes confirm study `699c459a6082a549e6f198f6e7b481f71a046533a28f0cdc2cf75b0c1ed3fd68`, study tests `c0102306e07ba125cf3f4bd2e8ccacd98d8645bbceda7760fc5b0cee63fde762`; verifier40f40acd and verifier-testsa81aec07 remain exactly unchanged. Ordered ponytail review then engineering review found the complete production diff is the declared one-snapshot predicate plus source-plan binding. No other guard, mathematical, resource or timing behavior changed. Tests explicitly verify two independent rejection mechanisms, fresh per-call snapshots and original error identity.

Reviewer inspected the retained paired diagnostic script/results and current regression/static logs. Five old/candidate rounds assert complete resource/manifest equality; mean diagnostic cost changes0.0581213s to0.05712156s (1.72percent), a small measured reduction, not eligibility evidence. Related526 tests passed in23.08s; strict170-source mypy and Ruff passed. No further blocker found.

GO for the three declared `verifier-optimized-3-final-1..3` cold full-workload benchmarks after all final formatting checks pass. Retain every outcome; all three effective50400-second gates and worst timing govern. Legacy43200 comparisons and independent all-saved-path checks remain mandatory. No sampled authority or cleanup approval follows from source GO.

## Actual iteration 3 saved results and failed qualification

Reviewer independently replayed all three declared roots with literal scalar SHA and naive integer/finite-truth/rational-endpoint equations, importing no project math. Each10-path/28-result set,1388952 words and231492 bytes matched exactly, including supports, endpoints, flags and all summary cells. Canonical operational history/evidence/full-file pin, direct artifact bindings, source closure before/after, record seals, claims/index/terminals/receipt publication and all old/effective timing calculations passed. Exclusive fsynced resource-bound reviewer receipts were saved. Own oracle times1.9162352/1.9272221/1.9269155s; ending RSS below23MiB, not peak proof.

All three bind manifest `9e70bbbdc598fe2d8a821b6abf2759af47db29d613ee8336d9daadcfca1c6a17`, index `eb52a80f3cb06fc97b7ebe0d4627f658fae9f7147f0bc93d22df152ddd0d9027`, terminal `a461ed1c53feffd66b9b10714c9d6c840b616ca64306ef2a47432d3a8fc501ff`, and unchanged full payload `816a0ae0a31c0cf97bf3fd1aa309b063551951305b4dfaac78370db22759afc2`.

Effective outcomes true/true/false mean overall qualification FAILED. Validation projections50,130.8719/49,173.6859/52,447.6023s retain worst14.5688h above14h; all original12h validation comparisons remain false. No passing minimum or retry substitutes for the required worst/all-three rule. This evidence does not approve another budget increase; any new resource amendment requires its concrete separately reviewed proposal/contract/source and fresh runs.

Reviewer permits exact231492-byte raw-only cleanup in these three roots after primary receipts pass and the existing fixed-root/ancestor/regular-file/identity/hash/durable-intent checks complete. No reviewer deletion occurred. Preserve compact results, every failure and cleanup provenance; sampled lifecycle remains unavailable.
