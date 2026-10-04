# Calendar-score deterministic-preflight build record

Date: 2026-10-04. Status: **INDEPENDENT SOURCE REVIEW APPROVED; DETERMINISTIC PREFLIGHT COMPLETE, RESOURCE ELIGIBILITY FALSE.** Saved-file independent verification/cleanup completion is recorded below. No sampled study phase ran. Experimental draws: **0**.

## Delivered scope

This build delivers the frozen pure calendar-score contracts and an actual supervised deterministic preflight only. The full development/validation sampler, sampled-file verifier, live phase authority, validation-root sealing and sampled cleanup lifecycle remain **OPEN/UNBUILT**. This narrowing follows the independent architecture advice recorded in `docs/reviews/2026-10-04-calendar-score-study-protocol-review.md`: provisional deterministic timing predicted the frozen stage deadlines would fail, so building dormant sampled authority before governed feasibility measurement was rejected.

The preflight uses only the public all-zero root in `icarus/calendar-score-research/test-preflight/v2`. Every attempted experimental-namespace stream refuses. The public CLI defaults to refusal and exposes only preflight. No market data, secrets, brokers, network, old held roots, official streams or experimental roots were accessed.

Frozen protocol SHA-256: `130569a78811e9ad4f9dcdb915410b3c350e137a78bc70974eb81ac4daf13b71`.

Frozen implementation:

- `scripts/research/signal_calendar_score_study.py`: `6f8e6d0f929bcd45d56a4a1f6b0b3f1c87ca9f7be095ed23d05d25560d37ac79`
- `tests/unit/test_signal_calendar_score_study_research.py`: `5c08618d2240668de92ce52b65bd6fe997074b057ea94975b1d62d70ca08658f`

The source manifest checks the actual protocol bytes against the frozen protocol hash, closes over the generator/evidence/score/uncertainty sources, `goal.yaml`, runtime and lockfile, and is rechecked in parent and worker. This is file and in-memory provenance binding, not a Python security sandbox.

## Implemented preflight boundaries

- Frozen ten-profile geometry, exact supports/truths, original-`a` centering, strict wins, atom framing/mapping, SHA counter stream and exact `eta=1/1760` binomial cutoffs.
- One identical full-geometry path for each profile, deterministic saved payload/index, full regeneration/replay, ordered identity/hash/word/result checks, and separate generation/write/sync versus replay/read projections at 8192 and 32768 replicates.
- 32 MiB deterministic disk probe with streamed hashing, size/hash/identity checks and probe-only cleanup receipt. Preflight payload and compact index were retained until independent review; the final raw cleanup and retained index are recorded below.
- Exclusive bounded canonical writes with short-write completion, flush/fsync/close failure propagation, per-record caps and bounded readers.
- Lexical root/leaf/ancestor reparse screening before every directory creation/write, no-follow exclusive opens, open-file identity checks and fixed-root containment.
- Separate child process, immediate worker heartbeat, propagated heartbeat I/O failure, process-tree RSS/disk/deadline/log monitoring, completion-time checks, tree termination and stable staged failure receipts.

RSS is an enforced sampled cancellation gate at intervals no greater than 0.25 seconds. It is **MONITORED**, not a hard address-space cap; transient peaks between samples remain **UNPROVED**. Windows directory-sync/power-loss equivalence remains **NOT CLAIMED**. The supervisor records its observed worker peak separately.

## TDD and verification evidence

The initial RED import test is retained at `var/verification/2026-10-04/calendar-score-study-red.log`. Test reference errors found before implementation were corrected against unchanged law oracles: frozen order is `P1..P7,E+,E-,L1`; P1 truths are raw `0`, strict win `1/4`, synthetic excess `-1/200`; its constant constructed atom has excess `13n/1000`. These were fixture corrections, not production-law fixes.

Independent code review requested the simplicity removal plus six engineering changes: remove unused sampled aggregation; bind actual protocol bytes; handle every short write; propagate heartbeat failures; inspect ancestors above the selected root; run final supervision checks; and preserve stable failure provenance. The reproduced RED run is retained at `var/verification/2026-10-04/calendar-score-study-review-red.log`: **9 failed, 30 passed, exit 1**. Two additional pre-write ordering regressions failed before the lexical-before-mkdir fix.

Focused GREEN:

```text
uv run pytest tests/unit/test_signal_calendar_score_study_research.py -q -p no:cacheprovider
42 passed in 1.50s; exit 0
```

Green log and exit code: `var/verification/2026-10-04/calendar-score-study-review-green.log` and `.exit`.

Primary independent verification at the frozen hashes:

```text
calendar/new-study/synthetic-golden regressions: 292 passed in 10.31s; exit 0
uv run mypy icarus tests scripts/research: 168 source files clean (strict=true in pyproject.toml)
uv run ruff check --no-cache icarus tests scripts/research: clean
uv run ruff format --check --no-cache icarus tests scripts/research: 168 files already formatted
```

Builder's earlier focused selection passed190 tests in5.05s (`calendar-score-study-focused.log`, exit0); primary's existing calendar/law/evidence/score/synthetic-golden selection independently passed250 tests in7.45s before the final292-test run. No fresh full repository suite was run; unchanged unrelated tests were deliberately excluded after focused and global static coverage.

## Reviewed measurement and feasibility

Final ordered independent review approved these exact source/test hashes for deterministic measurement only; all six findings plus pre-write directory ordering are closed. Reviewer independently reran42 tests in1.40s and fault probes; [review](2026-10-04-calendar-score-study-code-review.md).

Actual invocation: `uv run python -m scripts.research.signal_calendar_score_study --preflight --evidence-root C:/ICARUS/var/verification/2026-10-04/calendar-score-study-preflight-final`, exit0. Public all-zero test-preflight domain only. Ten full geometries generated and replayed;231492 complete source bytes,1388952 consumed words,28 metric records. Generation/evaluation/durable output1.7293323000s; regeneration/saved replay1.7488646000s. Separate32MiB deterministic write/fsync probe4.124066s and streamed read/hash0.0304273s. These are end-to-end PC measurements, not disk-device bandwidth or a sustained multi-day run.

| Twofold-margin projection | Seconds | Registered limit | Result |
|---|---:|---:|---|
| Development generation/output |28333.3804|21600|FAIL|
| Development verification |28653.3976|43200|within|
| Validation generation/output |113333.5216|43200|FAIL|
| Validation verification |114613.5904|43200|FAIL|

Resource eligibility is **false**. Storage estimates remain within3GiB/12GiB; free disk337497473024 bytes exceeds reserve+estimated validation payload. Parent-observed worker-tree peak28680192 bytes and worker self-sample28475392 bytes are below monitored caps; unobserved peaks remain unproved. The source-bound COMPLETE terminal means deterministic preflight execution completed; it is not study qualification.

Manifest digest38c657c161b1fa6e69a54b31f62de4bc47bc489240b690567c4338f7cd01b027; receipt digestf4a1eec793134e6078c378be7f37daa198094c45590807e03d43c3340257c5fc; raw payload SHA256816a0ae0a31c0cf97bf3fd1aa309b063551951305b4dfaac78370db22759afc2. Primary rechecked every source against the manifest, terminal/receipt digests, exact projections and probe cleanup. Independent literal SHA framing/rejection/atom generator rebuilt all ten saved paths; a separate integer-prefix trade loop reproduced all28 totals/counts. No experimental namespace was used.

## Remaining route

Saved-file reviewer verification and targeted raw cleanup are recorded below when complete. The failed feasibility gate keeps development and validation undrawn; full sampled worker/verifier/phase authority/root sealing/cleanup remain OPEN. Next is a reviewed optimization preserving exact byte/law results, followed by a fresh supervised preflight; any operational amendment must be separate, pre-draw and reviewed. Statistical criteria and the frozen protocol are unchanged. M1-M4/F48/Task3a remain OPEN; inference=false, stop before real-market simulation.

## Independent saved verification and D44 cleanup

Reviewer independently rebuilt all10 complete histories,1388952 words and28 endpoints/results without importing production calculation modules; all source/canonical/hash/truth/rounding/projection checks pass. Both verification receipts bind raw SHA816a0ae0a31c0cf97bf3fd1aa309b063551951305b4dfaac78370db22759afc2. Primary checked exact file identity/hash immediately before deleting only231492-byte preflight-payload.bin, then durably recorded DELETED_VERIFIED_RAW at2026-10-04T07:04:45.380373+00:00. Compact index/manifest/results/claim/terminal/audit/verification/cleanup receipts remain locally; [compact committed provenance](2026-10-04-calendar-score-study-preflight.json) preserves results and receipts. Raw replay is now unavailable; the prior successful all-byte verification is a completed dated check. Probe-only cleanup had already removed33554432 verified bytes. No real data, old-study artifacts or held roots were deleted.

## Commit and post-commit defect checks

Protocol commit363ca74; implementation/feasibility checkpoint commitd10dd78f52e7f55209c87accb02f23023a2a8d49. Ordered simplicity/engineering review approved the exact source before commit; no push requested.

After commit, primary saved an exact-byte source snapshot and ran two bounded deliberate defects: changing excess centering to adjusted-a and accepting a zero-byte write. Each intended test failed with exit1; the source was restored in finally and compared byte-for-byte with the snapshot. No actual remaining implementation defect is claimed. Restored source SHA6f8e6d0f929bcd45d56a4a1f6b0b3f1c87ca9f7be095ed23d05d25560d37ac79 and test SHA5c08618d2240668de92ce52b65bd6fe997074b057ea94975b1d62d70ca08658f match the independent approval. Final restored calendar/new-study/synthetic-golden regression:292 passed in8.27s, exit0; retained ignored logs post-commit-defect-checks.log and primary-restored-regression.log. No experimental words or source changes remain.

This final follow-up changes verification/handover documentation only and is exempt from a new code-review pass under OPERATOR section1. It does not extend source approval to modified code or enable inference/sampling.
