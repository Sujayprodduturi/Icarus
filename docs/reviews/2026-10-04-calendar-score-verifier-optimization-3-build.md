# Verifier optimization iteration3 build

Approved plan SHA256:8a569d0ac5af212cf0e69ab485c308c87fdd7907e5300ecbdd8c1da037d6e00e. Base commitfc84af333fa0ba2c63c95818702a03ad8756671b. This build is a candidate; fresh workload qualification remains pending.

Study _is_reparse now derives symlink classification from stat.S_ISLNK(info.st_mode) using its first fresh lstat snapshot, retaining the identical Windows attribute mask and FileNotFoundError handling. Other errors still propagate. SOURCE_PATHS adds only the approved iteration3 plan. Source diff is2 added/1 removed lines; no other production file changed.

TDD RED: optimization3-red.log records6 meaningful failures and3 passes in0.52s. Realistic status objects include regular/directory/symlink st_mode plus absent/zero/reparse/unrelated Windows attributes. The old predicate ignores the first snapshot symlink mode and queries status again; it fails the explicit coherent/fresh-snapshot assertions. Tests require one snapshot each invocation and a fresh next invocation; missing file and original PermissionError/OSError identity remain checked.

GREEN:210 focused study/verifier tests passed12.36s in optimization3-green.log. Strict mypy for owned source/test2 files is clean (optimization3-mypy.log). No-cache Ruff and format are clean (optimization3-ruff.log). All logs are retained under var/verification/2026-10-04/calendar-score-verify/.

Frozen SHA256:

- study source:699c459a6082a549e6f198f6e7b481f71a046533a28f0cdc2cf75b0c1ed3fd68
- study tests:c0102306e07ba125cf3f4bd2e8ccacd98d8645bbceda7760fc5b0cee63fde762
- verifier source unchanged:40f40acd5096f69b52e7694317c67c2fd6213b543f02f7514d174385e569cb02
- verifier tests unchanged:a81aec072d1ab356c0554033d46d6d1b5ffc18c490747c3232ec19fa1b945bd4
- operational contract unchanged:8a2225727e08cb7eb848e46ab856eca5649d727c15a101f0ab1bb3d9a1d313bc

No caches, checkpoints, guards, source/hash reads, mathematics, stream framing or resource/timing limits were changed. One coherent status snapshot does not make the surrounding path/open sequence atomic or establish Windows power-loss equivalence. Guard-level ancestor/root/leaf/containment regressions remain green. Statistical protocol remains130569a78811e9ad4f9dcdb915410b3c350e137a78bc70974eb81ac4daf13b71.

Builder ran no actual benchmark, broad regression, raw cleanup, commit or push. Root owns the declared five paired provenance diagnostics, ordered review, global checks and three fresh cold runs. Previous failed qualifications remain retained. Inference=false, Task3a/M1-M4/F48 OPEN and Units2-3 UNBUILT.

## Root final measurements and verification

Five alternating paired fresh provenance diagnostics preserve exact complete resource/manifest equality. Means58.1213ms old/57.12156ms candidate,1.72percent lower; two candidate rounds are slower and retained. [Diagnostic](2026-10-04-calendar-score-verifier-optimization-3-diagnostic.json) is not qualification. Fresh526 related regressions pass23.08s; strict170-source mypy/global Ruff/324-file no-cache formatting pass. CRLF-aware and ordinary numstats agree.

Three declared actual cold full10-history/28-metric runs cost0.7649364000099013/0.7503309000021545/0.8002868999901693s. Effective14h verdicts true/true/false; worst52447.60227775574s versus50400 means overall FAILED. Startup0.312/0.312/0.344s illustrates variability; retain the full timing boundary and all runs, never minimum/retry. Every legacy12h validation verdict remains false.

Primary and reviewer standalone scalar oracles reproduce all231492 payload bytes/1388952 words,28 mathematics/summary cells and actual source/runtime/operational contract/claim/index/terminal/receipt/projection bindings. Exclusive matching independent receipts preceded guarded D44 raw-only cleanup with durable intent/immediate identity+SHA recheck/absence receipt. [Compact all3 evidence](2026-10-04-calendar-score-verifier-optimization-3-benchmarks.json) remains; raw replay unavailable. No source changed until both checks and cleanup completed.

A separate resource view calculates15h headroom23.69ms/set versus observed32ms startup spread, before new-history overhead;16h headroom78.62ms/set is the more defensible proposal. Neither is qualification. Budget remains14h; any16h append requires a separate reviewed dated post-hoc proposal/source pin/new all3 cold measurement. All original failures/statistical gates/2x/once-only identity remain. No global-optimum, sustained-session, transient-peak or Windows power-loss claim. Units2-3 UNBUILT, inference=false, Task3a/M1-M4/F48 OPEN.

## Commit and post-commit proof

Commit10552a30a2ef868005549716ba63dd80a1879627 pushed; HEAD=origin/dev confirmed. Three deliberate semantic defects (ignored symlink mode, ignored Windows reparse attribute, swallowed status errors) each fail meaningful regressions. Exclusive snapshots and finally restoration reproduce study699c459a/verifier40f40acd exact approved bytes; fresh526 related regressions pass21.83s after restoration. Documentation-only provenance follow-up is exempt from another source mutation cycle. Current-source CI is not assumed.
