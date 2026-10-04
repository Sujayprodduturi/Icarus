# Calendar-score sampled lifecycle design and first-unit implementation plan

> **For agentic workers:** Use superpowers:executing-plans for the first unit, one task at a time. Primary implements; one focused reviewer checks the final unit. Later units require their own concrete plans/source gates.

**Goal:** Build a fail-closed artificial-study lifecycle, beginning with independently calculated saved-evidence verification and its actual runtime proof.
**Architecture:** Preserve the frozen calculator, law, generator mapping and statistical protocol. Separate pure study arithmetic, bounded independent verification and the once-only phase coordinator; never derive permission from a saved PASS file.
**Tech Stack:** Python3.12, uv, existing NumPy/psutil, standard-library exact integers/Fraction/SHA256, local supervised processes; no new dependency.
**Spec:** [Frozen study protocol](2026-10-04-calendar-score-study-protocol.md), SHA256 `130569a78811e9ad4f9dcdb915410b3c350e137a78bc70974eb81ac4daf13b71`.
Date2026-10-04. Design only. This document does not implement or launch a study. D23/D26/D38/D41-D44 authorize routine artificial work and focused review; real-market, broker, lockbox, old confirmation and official streams stay held.

## Global constraints

- Preserve all10 geometries,25 formal metrics,9 joint cells,4 detection cells,88 one-sided statements and eta1/1760; L1's3 metrics remain diagnostic.
- Development8192 paths/family:81920 paths/229376 metric evaluations. Validation32768/family:327680 paths/917504 evaluations. Family-major order P1,P2,P3,P4,P5,P6,P7,E+,E-,L1; within each family replicate0..R-1.
- Exact source halos/one-byte atoms and SHA prefix/word mapping/rejection counts are unchanged; strict wins>0 and strict directional detection; no truth-dependent endpoints.
- Development point gates .95 coverage/joint, .01 per directional tail, .90 detection; formal A=P=R and C+Tlo+Thi=A. Validation exact cutoffs31258/270/29668 at32768. Statistical failure completes all families; contract/source/resource/I/O error stops incomplete.
- Worker deadlines21600s/43200s; each phase verifier43200s. Worker/verifier tree RSS2GiB, parent512MiB, buffer16MiB, record256KiB, sampling<=.25s, heartbeat30s. One heavy worker at a time. Limits are monitored cancellation, not unsampled peak-memory proof.
- Development/validation caps3GiB/12GiB, combined compact per-path metadata<=8192 bytes, phase overhead<=16MiB, free-space reserve20GiB. Bound claims, results, indexes, logs, ledger and review receipts within those budgets.
- Source freeze includes every transitive study/verifier/lifecycle/helper/config/lockfile and this approved design; check actual source and runtime in parent/worker/verifier/reviewer before and after every stage. Do not edit the frozen statistical protocol.
- No retry/resume/redraw, partial extension or source substitution. Exposed attempts remain append-only. Only verified artificial raw payload may be deleted; compact rows, seeds/commitments, trial/claim/failure/terminal/source/verification/approval/cleanup records remain.

## Review focus

1. New directories or new parents bypassing the once-only attempt registry: reject before claims or experimental hashing.
2. Saved PASS/approval files or process restart manufacturing authority: require live session and reviewer service binding, otherwise refuse.
3. Independent verifier reusing production calculations or exceeding deadline: independent equations and actual supervised workload proof, not old production replay timing.
4. Mixed-source evidence, malformed/order/length drift and partially closed output: fail incomplete; terminal COMPLETE only after all write/fsync/close and final supervision checks.
5. Premature cleanup or path replacement: both verified approvals, exact digests/identities and retained allowlist; no recursive deletion or outside/reparse traversal.
## Responsibilities and authority

Existing `scripts/research/signal_calendar_score_study.py` remains the deterministic core and preflight. Source currently58f483289f9175fec4f96153a1e7a377cc8c26e9d61a4a4e35fc8ef67b901f5e. Its experimental CounterStream constructor continues to refuse throughout Units1-2. No refactor of old failed runners or their sources.

New `scripts/research/signal_calendar_score_verify.py`: bounded reference reconstruction from saved bytes; literal SHA framing/rejections, independent exact trade totals/truths/supports/score endpoints, index/schema/counter reconciliation and one-set benchmark. It may read immutable laws/constants as input and existing guarded I/O primitives; it must not call production generate_payload/evaluate_payload/evidence.replay/score.calculate/truth oracle/cutoff to establish correctness. Exact-value fixture comparisons and import-dependency tests enforce this boundary. Reusing primitive SHA/NumPy/Fraction is allowed; independent formulation is the requirement.

New `scripts/research/signal_calendar_score_lifecycle.py` (Unit2): once-only registry, typed state and binding records, parent session and reviewer IPC/sealed-root ownership, durable result approvals and target-specific cleanup. No generic workflow framework. Unit3 adds the actual supervised worker/verifier orchestration; no live broker or trading runtime changes.

Reviewer approval is separate from an automated verification receipt. Primary runs the bounded verifier across EVERY path; reviewer independently examines reference code/oracles and runs complete saved verification in a separate supervised invocation. Both executions consume the same phase evidence without nested heavy processes; each invocation has43200s. Their outputs retain each invocation's actual time/resource samples. Neither gets to count a shared output as two independent checks; fixture/reference equations guard shared implementation errors, and focused review is recorded explicitly. This is computational replication plus independent code/math review, not proof of different mathematical assumptions.

## Phase and evidence bindings

Canonical schema1 records use exact types (bool is not an integer), UTC-aware timestamps, bounded rationals as canonical numerator/denominator pairs, lowercase64-character SHA hashes and no nonfinite JSON. A binding contains protocol_digest, source_manifest_digest, attempt_id, session_id, phase, seed_commitment, payload_digest, index_digest, results_digest and terminal_digest. Empty evidence digests are allowed only in pre-output claims; completed receipts require all. Hash canonical records excluding only their digest field; any mismatch fails.

The fixed registry is `var/research/calendar_score_v2/attempts/<protocol_digest>/` under the project root, with a single exclusive attempt claim for this reviewed v2. A different evidence path/source/session cannot permit a second attempt against that protocol. Future attempt amendments use a separately reviewed new version and preserve the original exhausted claim. Resolve lexical ancestors before mkdir/open; reject symlinks/reparse paths and all unapproved output locations. Audit per-phase claim/terminal/failure and exposed word counts, including startup zero-draw failures. Registry failure stops before any study SHA. A stale claim remains exhausted, never automatically resumed. BEFORE starting reviewer helper or selecting any development/validation study key, exclusively write/flush/fsync/single-close an ATTEMPT_RESERVED record in that fixed registry, binding protocol/source/session/counts/budgets. This reservation has no phase seed and grants no study SHA capability. All failures after reservation, including helper startup/key selection/zero-word loss, exhaust the attempt durably; the later seed-bound per-phase CLAIM is a distinct record, never replacement of the reservation. Tests kill the helper between reservation and claim and prove new directories/sessions cannot retry. Unit1 creates no actual reservation or study key.

Claims reserve full frozen counts/budgets and validate exact manifest and full-workload eligibility before exclusive write/flush/fsync/single-close. Development root is chosen once AFTER gates and before claim; record it and its commitment with the claim. Cryptographic seed creation is distinguished from consumed study words. The first experimental SHA requires live parent-issued phase capability after durable claim; capability is private, exact-type/session-bound and supplied through authenticated local IPC, never loaded from claim JSON. Unit3 adds this path to CounterStream; public default remains refusal. Every consumed/rejected word counts; prefetch never counts as consumption, but consumed failed rows are retained in failure accounting.

Paths stream into one exclusive binary payload and one canonical compact index (which itself retains all per-path results); no redundant results copy is needed. Index row: schema, phase, family/n/replicate, exact offset/size, payload SHA, words, full aggregate/endpoints/reasons/precision/miss/detection. Header binds claim; trailer is a distinct phase record. Readers know exact expected count/order/byte totals before reading and reject truncation, duplicates, reordered/missing/extra rows, trailing payload, noncanonical representations and changed schema.
## Sealed validation root and live transition

Before development claim, an independent-reviewer-owned local helper chooses one new32-byte validation key, returns only SHA commitment plus a session challenge binding, and retains the key solely in its own process memory. No key in development environment, command line, logs, claim files, shell history or shared disk. This is trusted-role blinding, not claimed OS protection against a malicious administrator. No broker credential enters either process.

Helper uses a loopback/local authenticated coordinator IPC channel with a fresh in-memory session secret sent by inherited private pipe; no reusable authority file. Reviewer approval is a DIFFERENT authenticated reviewer-only control channel whose secret/capability is unavailable to coordinator and study workers. The coordinator may request release but cannot submit approval or mark the helper's reviewer-approved state. Reviewer separately authenticates and binds the complete all-path check; shared coordinator IPC authentication alone never suffices. It registers exactly one coordinator PID/session, reviewed source/protocol/attempt and validation commitment. Parent/source/service death, lost IPC, changed PID/session/source, unmatched commitment or a second release invalidates the session and prevents continuation; key is discarded on service termination. Parent watches helper lifetime during development and verification; helper watches parent and exits on loss. No detach/resume/reconstruction. Losing the key consumes the attempt, rather than generating a replacement.

State progression: READY -> ATTEMPT_RESERVED -> VALIDATION_KEY_SEALED -> DEVELOPMENT_CLAIMED -> DEVELOPMENT_COMPLETE -> DEVELOPMENT_VERIFIED -> REVIEW_APPROVED -> VALIDATION_AUTHORIZED -> VALIDATION_CLAIMED -> VALIDATION_COMPLETE -> VALIDATION_VERIFIED -> FINAL_VERDICT. Any error is terminal ERROR; complete statistical development failure is terminal DEVELOPMENT_FAILED with no validation. Cleanup is a separate terminal-evidence operation; it cannot mint sampling authority.

Development COMPLETE means child exited0, all output streams durably finished/single-closed, no heartbeat errors and final tree/parent/disk/deadline checks passed. Parent privately mints completion token only while this same process/session is alive. Full primary verification must reconcile terminal, all bytes/streams/rows/totals/cutoffs/report. Reviewer service records a separate live reviewed approval after the independent reviewer has completed ALL saved verification and reviewed the exact PASS evidence; a copied JSON approval has no service-side approval state.

Validation release requires live completion token, exact passing development decision, complete primary receipt, independently approved receipt and matching binding fields. Recheck all source/evidence digests and helper lifetime BEFORE release. Service releases key ONCE into a private parent pipe, zeroes/drops its retained key buffer best-effort and records release commitment; Python does not guarantee secure memory erasure. Parent checks commitment and distinctness from development before durable validation claim, then hands key privately to the supervised child. On claim/release failure record ERROR, consume attempt, never request a new root.

Persisted PASS, terminal, seal, receipts or cleanup records are inert evidence on restart. A validation worker CLI/forged capability/record must refuse. Source changes after development require a new exposed protocol/version review, not reusing validation data. Validation outcomes never enable goal inference or product promotion; verdict is restricted artificial qualification only.

## Completion, verification and cleanup

Worker loops family then replicate; before each append enforce raw+index+phase overhead caps, source identity, monotonic deadline, free-space reserve and heartbeat status. Track completed paths plus active path consumed words for failure records. Report all formal metric/family/effect counters and sparse diagnostics separately. Compute exact full summaries from completed rows; do not increment covered/precision on refusal. Both verifiers reconstruct the full summary and fixed decision from saved rows, not trust report text.

Each supervised verification invocation is the heavy child itself; it uses bounded inputs and emits a digest-bound success receipt only after all file/resource checks. No subprocess verifier inside a running study worker. Any verifier corruption/timeout/source/durability failure produces incomplete ERROR and no qualification/release/cleanup approval. The separate independent-review record must identify exact sources, equations/fixtures checked and all paths verified, not just cite tests.

After both ALL-path checks, retain index/results, claim seeds, manifests, terminal, trial/failure/verification/approval records. Cleanup raw payload only; retained index already contains all endpoint/aggregate provenance. Before deletion compute/hash stream without whole-file read, confirm fixed raw filename, regular file identity(size/inode/device/mtime), all ancestor guards and both binding receipts. Durably persist cleanup intent, repeat identity/hash guard, unlink only that file, persist absence receipt with UTC time/hash/bytes. Partial cleanup/durability failure remains explicit CLEANUP_ERROR; never reports success or implies raw replay remains. No deletion of old-study or real-market files.

In incomplete/corrupt attempts keep raw until independent investigation records precisely what is verifiable and a separate bounded cleanup approval is issued; missing expected records cannot be silently interpreted as completed verification. No automatic error-path recursive cleanup. Windows directory/power-loss equivalence remains unclaimed.
## Unit1: independent verifier and saved-fixture format (actual next build)

**Files:** Create `scripts/research/signal_calendar_score_verify.py` and `tests/unit/test_signal_calendar_score_verify_research.py`. Modify only study source-manifest enumeration if required to bind the new verifier, plus documentation. Leave experimental stream refusal, calculator/evidence/law/goal/protocol unchanged. Ignored verification logs in `var/verification/2026-10-04/calendar-score-verify/`; deterministic raw fixtures cleaned only after both checks.

**Interfaces defined here:** frozen dataclasses below, bounded fixture writer/reader, exact reference reconstructor and report checker. No PhaseCapability or seed service exists in this unit. Use TEST_NAMESPACE/test_fixture or existing zero-key preflight only; reject EXPERIMENT_NAMESPACE in every fixture API.
```python
@dataclass(frozen=True, slots=True)
class ReferenceResult:
    count: int
    raw: Fraction
    wins: int
    excess: Fraction
    rows: tuple[dict[str, object], ...]
    words: int
@dataclass(frozen=True, slots=True)
class VerificationReceipt:
    binding: dict[str, str]
    paths: int
    metrics: int
    words: int
    payload_bytes: int
    seconds: float
def reference_path(profile_id: str, n: int, payload: bytes,
                   identity: dict[str, object]) -> ReferenceResult: ...
def verify_fixture(root: Path, *, expected_manifest: str,
                   expected_paths: tuple[tuple[str, int, int], ...]) -> VerificationReceipt: ...
```
The implementation replaces these declaration-only ellipses with tested logic. Path geometry, coefficient scale and score exponent come from the frozen spec; no caller can tune thresholds or accept absent evidence. Frozen dataclasses prevent field reassignment, not mutation of contained dictionaries. Validate and canonical-serialize/copy dictionaries at boundaries; live tokens retain immutable canonical digest fields, never caller-owned mutable references. Public serialized dictionaries carry no authority.
### Task1: exact independent path reconstruction

- [ ] Write failing tests for a hand-packed short history with known zero/tie/positive/negative outcomes; quiet and halo dates cannot enter the count. Compare all10 zero-key full geometry payload hashes to committed compact baseline, independent word counts and all28 output rows/endpoints.
```python
def test_reference_reproduces_frozen_full_set():
    for item, payload, identity, saved_row in full_zero_key_fixtures():
        actual = reference_path(item.profile_id, item.n, payload, identity)
        assert actual.count == saved_row["results"][0]["count"]
        assert pack_reference_rows(actual.rows) == saved_row["results"]
        assert actual.words == saved_row["words"]
```
Fixture helpers are test-local: construct identities literally from the frozen protocol, use existing deterministic generator ONLY to produce fixture bytes, compare to old committed hashes. The reconstructor never imports that generator/evaluator. Test asymmetric excess centering, strict win/detection ties, halos, sparse zero count, missing truth and outward rounding with independently hand-computed Fraction/integer-square-root expectations.
- [ ] Run `uv run pytest tests/unit/test_signal_calendar_score_verify_research.py -q`; capture expected RED, not an environment/import-launch failure.
- [ ] Implement literal SHA words/unbiased atoms with bounded input and1024-rejection/counter-overflow handling; derive trade sums from independent prefix sums over signed factors/volatility and per-symbol masks, not the production rolling loop. Exact integer scale is LCM of rational coefficients. If vectorized int64 sums are used, prove per-profile maximum intermediate AND cumulative totals fit before arithmetic; otherwise use Python integers. No silent overflow or float endpoints.
- [ ] Independently enumerate finite analytical truths and fixed support from frozen coefficients. Reproduce score radius with integer square-root ceiling and outward fixed60-decimal-grid rounding; compare unrounded rational components too. Do not copy production calls into reference code.
- [ ] Test all atom bit patterns/legal jump indexes, deterministic rejection shifts and invalid upper bits/length, huge integers/overflow fallback, dense count limits and sparse diagnostic labels. Guard dependencies through an import-trap test that raises if production evaluator/truth/cutoff functions are called.
- [ ] Run GREEN and exact oracle comparison logs; record hashes. No phase claim or experimental capability added.

### Task2: bounded artifact verification and summary reconstruction

- [ ] Write RED tests for schema/phase/identity mismatch; missing/duplicate/reordered/trailing rows or bytes; bad size/offset/hash/count/endpoints; noncanonical JSON/rationals; source drift; successful child with failed close; partial writes and missing terminal. Assert stable refusal and absence of success receipt.
```python
@pytest.mark.parametrize("damage", ["duplicate", "reorder", "truncate",
                                  "trailing", "wrong_digest", "wrong_endpoint"])
def test_corruption_never_receipts_success(tmp_path, damage):
    root = full_test_fixture(tmp_path)
    corrupt_fixture(root, damage)
    with pytest.raises(VerificationError):
        verify_fixture(root, expected_manifest=fixture_manifest(root),
                       expected_paths=fixture_path_order())
    assert not (root / "verified.json").exists()
```
Corruption helpers operate only temporary test-domain fixtures. Complete index schema and fixed expected sequence come from contracts above; reduced geometry cannot be called production feasibility proof.
- [ ] Implement reads capped by256KiB record/8192-byte combined path metadata/16MiB buffer and phase caps. Read one path at a time; reject lengths BEFORE allocation. Check exact family-major order, regenerate every path/word count, reconcile every Fraction/count/endpoint and terminal hash, rebuild all counters,25+9+4 statements and diagnostic labels.
- [ ] Independently derive small-N exact binomial tails and full fixed cutoffs; verify boundary inclusivity31257/31258,270/271,29667/29668, and development integer-rational point gates. Always-wide/refuse/wrong-tail/missing-family fixtures cannot pass.
- [ ] Test complete statistical FAILED versus incomplete ERROR; development failure does not imply verifier corruption. Neither state can grant validation, and this module has no grant API.
- [ ] Run GREEN plus15 audit-ledger checks; source review covers reference correctness and bounded I/O. Do not edit frozen protocol to accommodate failure.

### Task3: supervised full-workload verifier measurement and checkpoint

- [ ] Write RED tests proving timeout/RSS/free-space/heartbeat/I/O errors terminate verifier tree, propagate stable failure and never emit successful receipt; test completion-time checks and failed heartbeat join. Reuse reviewed supervision primitives without weakening limits or spawning nested heavy jobs.
- [ ] Add deterministic-only `--verify-fixture` and `--benchmark` CLI entrypoints; no study launch. Benchmark saves one full10-history zero-key set, then times ACTUAL complete independently authored verifier including regeneration, reference arithmetic, bounded read/hash/schema/report checks and receipt durability. Supervision output binds new source manifest and exact geometry.
- [ ] Run `uv run python -m scripts.research.signal_calendar_score_verify --benchmark --evidence-root NEW_FIXED_ROOT` only after exact-source review and known-stream/oracle GREEN. Twice measured complete per-set validation verification time times32768 must be<=43200s (per-set<=0.6591796875s); development verification likewise<=43200s. Record actual times, end-to-end I/O, RSS limits and disk. Existing .5129779s production replay is historical and cannot qualify this verifier. The one-per-family fixture has10 paths/28 metrics, not81920/229376 development observations; its summary must be labelled deterministic fixture only, never full-phase COMPLETE/PASS or qualification. Test this distinction explicitly. Include verifier initialization/summary/receipt work in measured feasibility; caching fixed truths/cutoffs is permitted, but do not omit its measured cost or reuse unbound cache artifacts.
- [ ] If verifier gate fails, persist precise undrawn blocker. Reviewed exact-output optimization or separately versioned pre-draw operational amendment is a NEW task; no implicit larger deadline, skipped regeneration, spot checks or phase count reduction.
- [ ] Run relevant verifier/calendar/law/score/evidence/geometry/statistics/uncertainty/synthetic-golden tests, `uv run mypy icarus tests scripts/research`, `uv run ruff check --no-cache icarus tests scripts/research` and `uv run ruff format --check --no-cache icarus tests scripts/research`. Disclose exclusions; no full-suite claim without fresh full run.
- [ ] One reviewer performs ordered ponytail-review then engineering/math review of frozen hashes; primary independently reproduces outputs/resource arithmetic and all saved fixtures. Reviewer approval is separate from automated receipt.
- [ ] After both checks, fixed-identity/hash-bound D44 raw cleanup retains compact rows/receipts; commit explicit files preserving AGENTS.md/mixed newlines. Plant two bounded defects after exclusive byte snapshot, show tests catch them, restore hashes and rerun affected regressions. Commit provenance addendum and push per D26.
- [ ] Update STATE/HANDOVER/TASKS/audit; explain checkpoint. Unit1 cannot claim a study, create experimental streams, seal/release actual study keys or enable inference.

## Later units: bounded deliverables, not executable plans yet

**Unit2 — state/registry/blinding/cleanup contracts on fixed test fixtures.** Subsequent concrete plan specifies private typed session/completion/verification/reviewer-approval tokens, global exclusive claim API, PID/lifetime-authenticated reviewer-helper IPC, one-time commitment-bound release, canonical phase/failure records and raw-only identity-bound cleanup. Test process death, copied/mismatched approvals, file-only/restarted state, duplicate claims under new roots, equal roots, malicious lengths/paths, failed durable claim and partial cleanup. Test-domain deterministic keys only; experimental CounterStream remains refused. Unit2 can be rejected independently of Unit1 mathematics.

**Unit3 — supervised sampled integration.** Only after Units1-2 reviewed and actually feasible: concrete worker CLI/parent launch and claim-capability stream factory, fixed full loops/counters, source manifests, completion authority, complete saved verification and reviewer approval integration, sealed release/validation claim and verified cleanup. TDD includes real subprocess startup/final-check/I/O/heartbeat failures, no hashes before claim, direct worker refusal and dev FAILED/ERROR/no permission, source drift and zero-draw terminal. Fresh exact-source full-workload generation AND actual independent verifier feasibility must pass. Run no study from mere implementation approval. Present readiness at major milestone; only all applicable source/resource/phase gates permit D41-authorized artificial sampling.

Budget each primary/reviewer invocation separately at43200s and record total elapsed session costs; no pooled timing or concealed second verification. Hold coordinator/reviewer helper alive through full session; process loss terminal, never backfilled from files. Long session/power reliability unproved until exercised. Metadata/log/claim overhead must fit frozen16MiB phase reserve and8192-byte path cap.

## Primary self-review and current evidence

Protocol coverage: fixed arithmetic/multiplicity in Unit1; claim/seed/authority/cleanup contracts in Unit2; supervised full counts in Unit3. All five review-focus failures assigned above. No production code or seed changed by this design. Goal/helper/protocol hashes and experimental refusal rechecked before commit.

Prior GitHub source9b367bd: CI completed2295 passed/4 skipped and1 documentation-status failure; unsupported audit status replaced by declared CLOSED, limited optimized-preflight scope retained in evidence. Local audit-ledger15 passed. Docs-only correction exempt from code review/mutation; it does not make that failed GitHub run green. Native resource-proof workflow reports success; full raw-report attestation not renewed. No official platform/calibration claim.

Independent review addresses architecture, verifier feasibility, blinded root release and attempt accounting. Final review verdict and next-unit readiness recorded separately. M1-M4/Task3a/F48 remain OPEN; inference=false; no market evidence, method adoption or live path.
