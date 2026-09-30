# Step 6a.2 Task 3 — bounded verifier native resource evidence

**Status of this measured run:** the full-size, non-reserved native proof and ordinary Linux CI passed at code commit `148bb3f6faac5dae08d1ed31a0c8e0343aea6ae4`. Later exact source `81fc971` also passed [native proof](https://github.com/Sujayprodduturi/Icarus/actions/runs/36561344390), [CI](https://github.com/Sujayprodduturi/Icarus/actions/runs/36561344466), and [independent whole-runner review](2026-09-29-step6a2-task3-whole-runner-review.md), attested at `614fa7a`. The subsequent [2026-09-30 handover](../HANDOVER.md) changes invocation ancestry and requires renewed exact-commit attestation. All these runs are test-only resource evidence, not official calibration or an accepted statistical floor.

## Exact-source evidence

- [Native proof run](https://github.com/Sujayprodduturi/Icarus/actions/runs/36557431783): all three jobs and the aggregate checker passed. The aggregate verdict was `WITHIN_FROZEN_LIMITS`, with `authority: NONE` and `official_streams_drawn: false`. A local rerun of `scripts.check_signalcalibration_envelope` over the downloaded artifacts returned the same verdict.
- [Ordinary CI](https://github.com/Sujayprodduturi/Icarus/actions/runs/36557431815): 1,644 passed, four existing integration skips, Ruff lint/format and strict mypy clean across 139 source files. The local Windows suite passed 1,637 with 10 platform skips; its run preceded the final Linux-only smoke-test stub correction, which the exact Linux CI exercised.
- Independent read-only code and resource-evidence reviews found no blocking defect. The three raw logs each end in JSON identical to their structured report. They contain no exception. All reports identify the same source commit, bare Linux with `systemd`, ext4, two CPUs, the frozen 45 × 10,000 calibration and 37 × 20,000 validation topology, non-reserved test seeds `2026092911` and `2026092912`, and zero reserved-seed draws.

| Test-only witness | Result bytes | Largest **written** chunk bytes | Phase seconds | Statistical verdict |
|---|---:|---:|---:|---|
| Real test-seed calibration | 41,643,867 | 47,698 | 1,790.03 | FAILED |
| Scripted passing calibration | 104,779,854 | 60,892 | 110.51 | PASSED |
| Real test-seed validation after scripted calibration | 58,960,144 | 46,873 | 1,449.56 | FAILED |
| Scripted passing validation | 162,940,278 | 58,316 | 236.14 | PASSED |

The scripted result and actual written-chunk sizes exceed their corresponding generated measurements in both phases. The largest observed peak VMS across reports was 385,773,568 bytes, peak RSS 143,523,840 bytes, and verifier projection 582,967,296 bytes. Each phase finished below the unchanged 2,147,483,648-byte address-space cap and 7,200-second deadline. Generated, scripted and fallback jobs respectively recorded 3,610/12, 9,466/56 and 9,466/56 successful fsync/close operations, with zero failures.

Downloaded structured-report SHA-256 values: generated `b017b71bdbdbefeddd142bf883339f40e2a8563396cd60ad1f026be1a7a7032d`; scripted `df96f7b4e92411c7dbadb113dcf44e14a5da0b4016aabf9968bc09558cba132f`; validation-fallback `d1d9e413bea6af5ae7e5b5622d580e35b198f76c7051009be41a99d3d766b358`.

## Boundary

The generated statistical failures are expected possible outcomes of test seeds. They do not imply anything about the held-back reserved streams or product performance. The first official calibration draw remains locked pending renewed attestation for the current handover commit, an eligible native host, and a separate operator decision. No real market data, lockbox, broker, live order or product inference was used.
