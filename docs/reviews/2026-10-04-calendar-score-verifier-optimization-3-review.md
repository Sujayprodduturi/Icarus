# Verifier optimization iteration 3: plan review

Date: 2026-10-04. Freshly checked plan SHA-256: `8a569d0ac5af212cf0e69ab485c308c87fdd7907e5300ecbdd8c1da037d6e00e`.

APPROVED for the bounded implementation and declared diagnostics. No plan blocker found. This is not source or runtime qualification approval.

Current `_is_reparse` obtains lstat for Windows attributes, then calls is_symlink for another status query. Testing `stat.S_ISLNK(info.st_mode)` alongside the existing reparse attributes is equivalent for a stable filesystem and uses one coherent non-following snapshot. Preserve FileNotFoundError behavior and propagate other original errors. Each invocation must perform a new lstat. Windows junctions remain rejected through FILE_ATTRIBUTE_REPARSE_POINT even when their mode is a directory.

Under concurrent filesystem mutation the snapshots can differ; neither implementation makes path-check/open atomic. The proposal correctly discloses this rather than claiming new TOCTOU protection. Existing lexical ancestor screening, containment, descriptor/lexical identity and final fresh source checks must remain unchanged. Source review must confirm only the predicate and plan closure change.

The proposed tests cover both independent rejection mechanisms, fresh-call count, ordinary paths and error identity; retain existing guard-level ancestor/root/leaf tests. Five alternating paired diagnostics must preserve full binding/manifest equality and retain every observation. Three subsequent fresh cold benchmarks still use worst time and require all effective50400-second gates to pass while reporting legacy43200 comparisons. Contract/statistics/stream/timing boundary stay unchanged. Every saved path and receipt remains independently verifiable before raw cleanup.

This one-line predicate simplification is preferable to the rejected parsed-policy framework at the measured bottleneck. Gain and effective14h feasibility remain unproved until the declared actual runs. No sampled authority or global-optimality claim follows.
