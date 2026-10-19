# Daily descriptive-pilot input package — 2026-10-19

## Result

The fixed NSE daily input package has been published privately and locally and passed [independent final qualification review](../reviews/2026-10-19-daily-input-package-review.md), review SHA-256 `ace24c587e3e17b05827ef87bd6965db000c06258b4e949405d0ab95b67e7f1a`. It contains all 693 requested labels over the exact 257 reviewed sessions from 2021-12-21 through 2022-12-30. This is an input-package result, not a strategy result: no strategy, actual trial ledger, broker, 2023 lockbox record, inference or promotion path ran.

The operator's [source-use disposition](2026-10-19-source-use-disposition.md) authorizes this scoped personal offline use. `source_use_authorized=true` in the qualification candidate has that narrow meaning. It is not a provider licence, contractual-permission finding or redistribution authority.

## Published artifacts and bindings

All market-data artifacts remain git-ignored under `var/daily-descriptive-pilot/2026-10-19/published/` and are not distributed by this document.

| Artifact | Bytes | SHA-256 | Meaning |
|---|---:|---|---|
| `artifacts/daily-panel.npz` | 2,132,118 | `536ab5e5b3a3157bc3667c0c49b22a9615fd129f41cc49e47cb67679bd9f4ef2` | Write-once encoded panel |
| decoded panel identity | 7,302,141 array bytes | `46da68ed9b62b8ad74cf390b25f0ad28bceec4acf95b40ef173f67b9279d19a8` | Canonical decoded-content digest verified inside the confined publisher |
| `artifacts/pending-publication.json` | 163,552 | `5cee54d295a51093817b952d6194b3338a21b9e17c9c0cbd90ff92a42e748222` | Inner publisher receipt; all qualification, source-use and run flags remain false |
| `artifacts/qualification.json` | 98,941 | `af4212a672ccef85313148b46c231c81fbbd53a1b039db943bb60ac003d2144c` | Exact 18-field `load_actual_admission` qualification candidate accepted by the separate final review |
| `publication-receipt.json` | 1,959 | `0056b1488964a2a402444779675a68d3da704d4b775819e0d2f484427d336185` | Outer source/code/policy/publication binding |
| `container-inspect.json` | 10,972 | `ba6fbe0266d01cb02b96f90991b38de442c0b2c5b9401bca3a45a2925775bca4` | Pre-start Docker configuration proof |

The package accounts for exactly 178,101 cells: 150,215 observed and 27,886 explicitly absent. It preserves 693 label dispositions, five unresolved-action records and the reviewed raw-screen statuses. The qualification candidate binds `goal.yaml` at `c886aca6b198257486d0daefc484f818458e60fa32a5aa861b95d1413282fa0c` and the seven-card catalogue at `ffa2cd82f29b19c76c0f491b9ebda46ccd3257a4cc6e4591d64c36f1fd827ec3`. The separate outer publication receipt binds the operator disposition at `e2ece157773e59288493770aa84290b1abae086a4116c0439f8ad8b3e1ecda67`. The metadata-only loader check produced admission binding `a9428517889a84af3ca3897d6ad513c703b2197059845167e32803f8e7e0de25`; the panel itself was not decoded on the host.

The publisher reused source commit `c92074d8abd24a784d5af1b7fbb7397aa8e85b49` and stage manifest `b9ffe3d29a4272afbb18aa3a21fde44f92587900fed6dda7b1a40c09cff6b788`. It rehashed 622 manifest-listed workspace inputs before and after publication; both state digests are `6b5ce3e1afb6aa64f415307f8e9791352628e1289eb37f66e3da097f3ff4cb83`. The separately pinned manifest makes 623 bound artifacts. The preparer independently verified 526 selected files, including all 514 raw/cache payload files, and reproduced input-state digest `0434e4cd6a6b031310f619d886547c664a8e0467c216a608c64dc81e4ed7ac45`.

## Confinement and verification

The retained pre-start container inspection proves image `sha256:108cdd2c8a2f9dc333c86256fce48d4ba1e37ec562be90c079c8019bd736da4c`, UID/GID 10002, network `none`, read-only root, all capabilities dropped, `no-new-privileges`, 64 PID limit, 4 GiB imposed memory limit, 8 GiB memory-plus-swap limit, two imposed CPUs, and exactly five mounts: four read-only inputs and `/output` as the sole read-write mount. There was no Docker-socket mount. The helper asserted that its three critical imports came from the staged `/workspace` and that `kiteconnect` and `ccxt` were absent. Peak RSS was not measured and is recorded as null; the 4 GiB and 8 GiB values are limits, not usage measurements.

Before execution, two helper tests passed, strict mypy passed, and Ruff lint/format passed. The existing write-once publisher regression passed. Root's combined preparer/publication selection passed 17 tests in 12.77 seconds. An independent reviewer approved the frozen helper `6d807b7cdee0e6691cd27cac92dea439d760dcd677f654a733a3b2ec3655b8c0` and launcher `7ac3d62ba2000671b9e948eb4921273fd6f6509ba058435f272627fe047c54ae` before execution, then gave the completed package a scoped final GO.

## Why Kite daily is not the route for this pilot

Switching this seven-card daily pilot to the already downloaded Kite DAY data would add unresolved work and no needed capability. The [Kite collection completion report](2026-10-15-kite-acquisition-completion.md) records 544 of 694 current-master resolutions, 150 retained mapping gaps, 326 quarantined chunks and no proof of continuous observed-bar coverage. Nineteen unresolved names pass the NSE price/liquidity screen on at least one pilot date, so dropping them would bias the denominator; see the [pilot candle coverage](2026-10-15-pilot-candle-coverage.md).

The downloaded Kite snapshot was retrieved in 2026 and may reflect corporate actions after the 2022 study boundary. Its exact price/volume adjustment factors and effective-dated lineage are not certified; the [source-semantics review](2026-10-15-source-semantics-evidence.md) and [price-basis diagnosis](2026-10-16-price-basis-diagnosis.md) show concrete Kite DAY/NSE mismatches and the double-adjustment risk. By comparison, the NSE route now has an exact, reviewed 693-by-257 source/action/PIT/calendar composition and a published panel. Kite remains an authorized fallback only if a later need justifies source-specific lineage, coverage and adjustment requalification.

## Remaining actual-run gate

Actual evaluation remains held. The next authorization would cover exactly seven counted `SignalSimulator` trials, one for each frozen card, on decisions dated 2022-12-26 through 2022-12-30. Applicability checks must pass first; then all seven reservations must be written to the activated Postgres trial ledger before any strategy-price decode. There is no reduced-card fallback, retry-based parameter search or winner selection. The 2022-12-30 decision cannot open on 2023-01-02.

Any result must remain explicitly descriptive: modeled daily outcomes net of transaction charges, before account capital-gains tax; benchmark return and pre-tax alpha are null; no statistical inference, promotion or profitability claim. Actual mode still requires a current external authorization document bound to this qualification, panel bundle, operator policy, goal, seven cards and runner, plus explicit activation of the counted ledger. See the [runner contract](2026-10-16-daily-pilot-runner.md).
