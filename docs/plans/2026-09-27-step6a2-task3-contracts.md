# Step 6a.2 Task 3 — evidence, provenance and platform contracts

**Status:** implementation contract for Task 3. It resolves the three blockers in the 2026-09-27 Astra re-review. It changes no manifest value, seed, cell, threshold, estimator, family size or first-passing rule, and it authorizes no frozen-stream draw.

## 1. Boundary and implementation shape

The counted runner remains in `scripts/signal_calibration.py`. Task 3 may add private classes and functions there, but it must not add a new project-owned imported module: the frozen manifest protects only the harness, estimator, manifest and detached digest. Keeping the implementation in the protected harness avoids silently widening the frozen code boundary. The review-to-invocation ancestry rule below additionally proves that every other tracked file, including the estimator's transitive imports, is unchanged after review.

Tests live in `tests/unit/test_signalcalibration_task3.py` and use scripted outcomes, sentinels or the existing test-only seed. Production validation always requires all frozen cells; reduced manifests are permitted only inside pure helper-unit tests and may not reach a counted context or CLI.

Implementation is ordered as four independently reviewable slices:

1. Pure strict-schema parsing and `validate_phase_result(manifest, result, expected_provenance)`, including event partitions, CP recomputation, parity completion and first-passing selection. No phase context, artifact I/O, CLI or counted RNG.
2. Review attestation, ancestry, cleanliness, exclusive claim/result/seal I/O, Linux resource enforcement and private phase context. No counted draw.
3. Counted provider and chunk orchestration using the already-frozen equations, followed by the same pure validator.
4. Calibration-to-validation unlock, CLI refusal paths and whole-run verification.

### Slice 1B input clarification — approved 2026-09-27

Fresh Astra Medium review approves a private immutable expected-context dataclass containing phase, independently established provenance/claim identity, expected runtime snapshot and `verified_calibration_floor`. Validate context values as strictly as artifact fields. Calibration requires no floor; validation requires exactly the independently verified passing calibration floor. The later calibration-trio boundary constructs production context; its type alone proves no verification.

Cell summary metrics and chunk metrics are ordered arrays exactly `raw`, `win`, `synthetic_excess`. All manifest-owned topology and order come from the full authenticated manifest, not caller overrides. Bind the complete runtime snapshot to independent controller inputs and require the Linux backend/source pair, frozen limits, finite nonnegative measurements and WITHIN_LIMIT. This checks recorded consistency, not actual OS enforcement. The runtime literals are `platform: linux`, `resource_backend: linux-rlimit-as`, and `peak_rss_source: getrusage-ru_maxrss-kib`; the source unit is KiB and stored peak values are converted to bytes. An immutable context may store canonical JSON bytes for its attempt/provenance/runtime records, parsed and strictly validated internally; a frozen dataclass containing mutable dictionaries is insufficient.

Refusal controls reconstruct geometry/masks and explicitly apply candidate floors. Tests must witness block-floor rejection and degree-of-freedom rejection when the block floor passes. Base event partitions cannot contain candidate-floor refusals. The pure verifier accepts complete PASSED or FAILED evidence only with UNVERIFIED terminal state, null failure and complete recomputed partitions/parity/summaries. It rejects INCOMPLETE evidence and never creates a seal or unlocks validation. Unsaved-trigger completeness remains a later orchestration obligation.

## 2. Common JSON rules

All four evidence documents are strict UTF-8 JSON with one trailing LF, no BOM, duplicate keys, trailing bytes, `NaN` or infinities. Writers use sorted keys and separators `(',', ':')`; parsers reject bytes that do not round-trip to that canonical form. Unknown or missing keys fail. JSON `integer` below excludes booleans; `number` is a finite JSON integer or float. IDs are non-negative integers. Lists whose name ends in `_ids` are strictly increasing and duplicate-free.

`sha256` is exactly 64 lowercase hexadecimal characters. `git_oid` is a full lowercase SHA-1 object ID (40 hex characters in this repository). `utc` is `YYYY-MM-DDTHH:MM:SS.ffffffZ`. `Floor` is exactly `{"minimum_blocks":integer,"minimum_nu":number}` and must equal one frozen candidate object byte-for-value after canonical parsing.

The evidence directory is `docs/reviews/step6a2/<manifest_sha256>/`. Paths are derived, never accepted from an artifact. For phase `P` and reviewed commit `R`:

- claim: `<P>.claim`
- result: `<P>-<R>-<P>.json`
- seal: `<P>.seal`
- review attestation: `task3.review.json`

`attempt_id` is the string `<R>-<P>`. The result filename is therefore named by `reviewed_commit`, the exact code reviewed. `invocation_commit` is recorded separately and may differ only by the review documents allowed below. The ambiguous term `harness-commit` is not used.

## 3. Review attestation and ancestry

The independent reviewer, not the implementation worker, creates and commits `task3.review.json` after reviewing the exact completed code. Its exact schema is `step6a2-task3-review-v1`:

```text
{
  schema: literal schema name,
  protocol_version: literal manifest protocol version,
  manifest_sha256: sha256,
  verdict: "APPROVED",
  reviewed_commit: git_oid,
  reviewed_tree: git_oid,
  protected_blobs: object {repo-relative protected path: sha256},
  review_record_path: repo-relative string,
  allowed_intervening_paths: sorted array of repo-relative strings,
  review_scope: ["artifact_verifier","counted_calibration","held_back_validation","resource_and_durability"],
  reviewer: {model:string,role:"independent_statistical_safety"},
  reviewed_at_utc: utc
}
```

`protected_blobs` has exactly the four paths in `manifest.integrity.protected_paths`, keyed by their repository paths. `reviewed_tree` must equal `git rev-parse <reviewed_commit>^{tree}`. `review_record_path` and this attestation path are the only two members of `allowed_intervening_paths`; both must be under `docs/reviews/`, must exist at invocation HEAD, and the attestation bytes are hashed into the claim.

Before claim creation the runner proves all of the following:

- `reviewed_commit` is an ancestor of `invocation_commit == HEAD`; the range is linear and contains no merge commit.
- For every commit in `reviewed_commit..invocation_commit`, the exact changed-path set is a subset of `allowed_intervening_paths`. This per-commit check prevents a change-and-revert from hiding code changes.
- The endpoint diff also contains only those paths; the reviewed tree and four protected blob hashes match the attestation.
- Every tracked working-tree byte matches invocation HEAD. The only unrelated untracked allowance is the frozen manifest's exact `AGENTS.md` entry.

These rules protect all tracked transitive imports without editing the frozen manifest or maintaining a guessed import-closure list.

## 4. Claim contract

The claim schema is `step6a2-phase-claim-v1` with exactly these keys:

```text
{
  schema, protocol_version, manifest_sha256, phase:"calibration"|"validation",
  attempt_id, reviewed_commit, invocation_commit,
  protected_blobs:{repo-relative path:sha256},
  review_attestation:{path:string,sha256:sha256},
  artifact_paths:{claim:string,result:string,seal:string},
  started_at_utc:utc
}
```

The claim is canonical and immutable. Its phase, paths, commits, blobs and attestation must equal independently derived values. Existing, malformed or truncated claim bytes permanently refuse that manifest/phase; this workflow never removes, repairs or replaces them.

## 5. Result contract

The result schema is `step6a2-calibration-result-v1` (the literal frozen by the parent plan). It has exactly these top-level keys:

```text
{
  schema, protocol_version, phase, attempt, provenance, phase_contract,
  chunks, summary, runtime, terminal
}
```

`attempt` is exactly `{attempt_id,started_at_utc}`. The end timestamp belongs to the terminal record, written after streamed chunks; this keeps the sorted top-level JSON append-only. `provenance` is exactly `{manifest_sha256,method_version,selection_artifact_schema,reviewed_commit,invocation_commit,protected_blobs,review_attestation_sha256,claim_sha256,dependencies}`. `dependencies` is exactly `{python,numpy,scipy,psutil}` and equals the manifest. `protected_blobs` uses the four repository-path keys above.

`phase_contract` is exactly `{master_seed,replicates_per_cell,cell_definitions,candidate_floors,metrics,checks,family_size}`. Every value is copied from the authenticated manifest for this phase; `cell_definitions` is the complete ordered cell array, not a caller-supplied subset.

Each `chunks` member has exactly:

```text
{
  cell_id:integer, chunk_id:integer,
  replicate_start:integer, replicate_stop_exclusive:integer,
  metrics:[MetricEvents]
}
```

Chunks are in manifest cell order then increasing chunk ID, cover `[0,R)` exactly once in declared chunks of 256 plus the final remainder, and never overlap. `MetricEvents` has exactly:

```text
{
  metric:"raw"|"win"|"synthetic_excess",
  emitted_ids:[integer],
  refusals:[{reason:string,ids:[integer]}],
  coverage_ids:[integer], lower_miss_ids:[integer], upper_miss_ids:[integer],
  joint_success_ids:[integer],
  parity:[ParityRecord]
}
```

Chunk `MetricEvents` are base-estimator events computed once without candidate floors. `BELOW_CALIBRATED_BLOCKS` and `BELOW_CALIBRATED_DF` occur only in deterministic candidate refusal controls, never by filtering base event partitions; candidate selection applies only frozen eligibility masks.

Refusal reasons are the frozen manifest's uppercase strings and appear in manifest order; empty reasons are omitted. Internal `BatchRefusal` names and lowercase values are never serialized. The counted adapter maps zero observations to `EMPTY_SAMPLE`, exactly one occupied block to `ONE_OCCUPIED_BLOCK`, a predeclared candidate block-floor failure to `BELOW_CALIBRATED_BLOCKS`, and a predeclared degree-of-freedom-floor failure to `BELOW_CALIBRATED_DF`; every other internal status maps to its one exact manifest reason or fails schema validation. Within a chunk, `emitted_ids` and all refusal lists form a disjoint partition of its replicate range. `coverage_ids`, `lower_miss_ids` and `upper_miss_ids` partition `emitted_ids`; `joint_success_ids` equals `coverage_ids`. IDs belong to this chunk and cell only. The generated set is the chunk range and is not duplicated as a large list.

`ParityRecord` has exactly `{replicate_id,triggers,max_abs_outcome,batch,scalar,cr1}`. `triggers` is a sorted non-empty subset of `ordinary|non_finite|zero|near_zero|t_critical`; `max_abs_outcome` is finite and non-negative. Each of `batch` and `scalar` is exactly `{status,mean,cr2_variance,nu,sample_variance,design_effect,effective_n,raw_lower,raw_upper,coverage,lower_miss,upper_miss}`; `status` is `EMITTED` or a frozen refusal, numeric fields are finite numbers or `null`, and decision fields are booleans or `null`. Emitted records have all numeric/decision fields; refused records have them all `null`. The verifier applies the frozen absolute mean tolerance `1e-14 * max_abs_outcome` and variance tolerance `1e-14 * max_abs_outcome^2`, checks zero/near-zero trigger consistency, and recomputes the `t_critical` condition from `nu`, mean, the manifest cell target and variance. `cr1` has the same shape except `cr2_variance` is named `cr1_variance`; it is report-only and never changes a gate verdict. Ordinary required audit IDs and every saved trigger/moment must be internally consistent. Exhaustive trigger emission for vectors that were not saved is guaranteed by the reviewed orchestration and sentinel tests; event IDs alone cannot prove that no trigger was omitted.

`summary` is exactly `{cells,candidate_results,selected_floor,parity_complete,phase_verdict}`. Each ordered cell summary is `{cell_id,generated,metrics}`. Each metric summary is exactly:

```text
{
  metric,
  counts:{emitted,refusal_total,coverage_successes,lower_tail_misses,
          upper_tail_misses,joint_successes},
  checks:{
    coverage_lower:{successes,trials,bound,threshold,passed},
    lower_tail_upper:{successes,trials,bound,threshold,passed},
    upper_tail_upper:{successes,trials,bound,threshold,passed},
    emission_lower:{successes,trials,bound,rate,absolute_minimum,threshold,passed},
    joint_lower:{successes,trials,bound,threshold,passed}
  }
}
```

All counts and bounds are recomputed from chunk event IDs using the frozen family size and CP functions. Each candidate item is `{floor:Floor,fixed_refusal_controls_passed:boolean,passed:boolean}`. The verifier recomputes `fixed_refusal_controls_passed` from deterministic geometry/mask construction and explicit application of that floor; it never trusts the supplied boolean. For calibration, `candidate_results` is the complete ordered four-floor manifest list and `selected_floor` is its first passing `Floor` or `null`. For validation, `candidate_results` contains exactly one item for the verified calibration floor, `selected_floor` equals that floor only if it passes, and no other floor is evaluated or represented. `phase_verdict` is `PASSED|FAILED|INCOMPLETE`. `parity_complete` is true only when every fixed and triggered audit ID has an exact batch/scalar comparison under the frozen tolerances.

**INCOMPLETE summary clarification (2026-09-27, Astra Medium and root):** complete-summary requirements above apply only to complete results. An incomplete result uses exactly `{cells:[],candidate_results:[],selected_floor:null,parity_complete:false,phase_verdict:"INCOMPLETE"}`. Durably committed chunk partitions preserve observed counts and generated ranges; the terminal failure identifies where processing stopped. Do not invent unfinished outcomes or compute partial-run confidence bounds. This failure representation does not change the statistical protocol or permit a seal.

`runtime` is the pre-verification snapshot exactly `{platform,resource_backend,address_space_limit_bytes,peak_rss_before_verification_bytes,peak_rss_source,planned_peak_bytes,maximum_result_bytes,generation_elapsed_seconds,deadline_seconds,resource_state}`; `resource_state` must be `WITHIN_LIMIT` for an unverified complete result. `terminal` is exactly `{state:"UNVERIFIED"|"INCOMPLETE",ended_at_utc:utc,failure:null|{kind:string,message:string,cell_id:integer|null,chunk_id:integer|null,replicate_ids:[integer]}}`. A complete statistical pass or failure is still `UNVERIFIED` until the seal exists. Caught failures close valid JSON as `INCOMPLETE`; abrupt failure may leave invalid bytes, which remain reserved.

## 6. Seal contract

**Implementation hold, 2026-09-28:** the schema below is retained, but the seal's successful finalization point needs an explicit ruling. Identical surviving bytes can follow successful finalization or a post-write deadline/fsync failure; later hashing cannot distinguish that history. Do not implement sealing or validation unlock until this is resolved. Independent result verification proceeds separately under the [Slice 4A plan](2026-09-28-step6a2-task3-verification.md).

The seal schema is `step6a2-completion-seal-v1` with exactly:

```text
{
  schema, protocol_version, manifest_sha256, phase, attempt_id,
  claim_path, claim_sha256, result_path, result_sha256, result_size_bytes,
  reviewed_commit, invocation_commit, review_attestation_sha256,
  phase_verdict:"PASSED"|"FAILED", verification_verdict:"COMPLETE",
  verifier:{schema:"step6a2-result-verifier-v1",harness_sha256:sha256},
  verification_elapsed_seconds:number, total_elapsed_seconds:number,
  verification_projected_bytes:integer, final_peak_rss_bytes:integer,
  final_resource_verdict:"WITHIN_LIMIT", verified_at_utc:utc
}
```

A seal may be created only after reopening the final result through the retained evidence-directory handle, hashing those same bytes, strict parsing, and independent recomputation of provenance, partitions, parity, bounds, verdicts and first-passing selection. `INCOMPLETE` results are never sealed. `COMPLETE` describes evidence completeness; validation unlock additionally requires calibration `phase_verdict == PASSED` and a non-null first-passing floor.

## 7. Validation evidence allowance

Calibration preflight allows only `AGENTS.md` plus the exact current calibration claim/result/seal paths derived above. Before calibration claim, those paths must not exist.

Validation first opens and verifies the exact calibration claim, result and seal derived from the calibration claim; a user path is only a locator and must equal the derived result path. After verification, validation cleanliness allows exactly:

- the frozen `AGENTS.md` allowance;
- the three exact verified calibration paths;
- the three exact current validation claim/result/seal paths.

No directory prefix, glob, other result, selection summary, temporary file or sibling evidence path is allowed. The calibration trio may remain untracked and does not count as an intervening commit. If committed, HEAD would violate the review-only ancestry rule and validation refuses. File identity for the opened calibration result is retained and rechecked through validation claim and result reservation.

## 8. Resource and durability contract

The statistical limits remain exactly 2 GiB and two hours. Counted mode is supported only on native Linux. Native Windows and every unproved platform refuse before claim creation, context creation, cache lookup or RNG construction; deterministic preflight and fixture tests remain supported there. This is a platform refusal, not a weaker Windows durability claim.

On Linux, before claim or RNG, the controller must:

- resolve the evidence mount from `/proc/self/mountinfo`, accept only `ext4`, `xfs` or `btrfs`, and reject network, overlay, FUSE, `tmpfs` and unknown filesystems;
- set both soft and hard `resource.RLIMIT_AS` to 2 GiB and verify the installed value; this caps virtual address space, not RSS;
- start one monotonic two-hour deadline covering preflight, generation, result close, independent verification and seal creation;
- open and retain no-follow directory handles for the evidence path.

Peak resident memory is measured separately with Linux `getrusage(RUSAGE_SELF).ru_maxrss` converted to bytes, sampled after the largest allocation and every chunk, and recorded as peak RSS. Current RSS plus simultaneously live planned arrays/cache is checked before allocation. The hard address-space cap remains active during result verification. Before reading result bytes, require `current_vms + 32 * result_size_bytes + 64 MiB <= 2 GiB`; otherwise close as incomplete and do not seal. The factor is a conservative JSON bytes-plus-object allowance, not a statistical threshold. Result writing also refuses before exceeding that projected verifier budget.

Evidence files are opened relative to retained directory handles with `O_CREAT|O_EXCL|O_NOFOLLOW|O_CLOEXEC`, mode `0600`. The runner rejects non-regular files, extra hard links and device/inode changes. It fsyncs every checkpoint and final file, then fsyncs the containing directory. When it creates a directory, it fsyncs the new directory and its parent before continuing. Any unsupported flag, limit, filesystem proof, fsync, allocation, flush, identity or deadline failure refuses before a draw when possible; after claim it produces or leaves an incomplete attempt and never a seal. No rename, overwrite, truncation, resume or cleanup path exists.

Sources for the platform semantics, checked 2026-09-27: [Python 3.12 `resource`](https://docs.python.org/3.12/library/resource.html) (`RLIMIT_AS` is address-space, not RSS) and [Linux `fsync(2)`](https://man7.org/linux/man-pages/man2/fsync.2.html) (file fsync does not make directory entries durable; the directory also needs fsync).

## 9. Acceptance invariants

- A result with a missing/extra key, duplicate/trailing byte, changed cell, incomplete range, duplicated/foreign ID, trusted aggregate, non-first floor or incomplete parity never receives a seal.
- A redelivered launch sees the stable claim and refuses before RNG, regardless of result or seal condition.
- Validation cannot unlock from a summary or digest alone; it requires the exact verified calibration trio and recomputes the complete result.
- Review ancestry is checked commit-by-commit; endpoint blob equality alone is insufficient.
- Resource installation and durable directory/file creation are proved with failure-injection tests before any counted draw.
- The first frozen calibration draw remains a separate hold point requiring independent approval of the implemented, committed runner and this contract.
