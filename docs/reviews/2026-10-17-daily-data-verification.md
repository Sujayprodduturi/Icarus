# Daily data qualification verification — 2026-10-17

The seven-card pilot now has a reviewed preparer and has passed a transient composition check on the real daily sources. This establishes technical composition for the bounded pilot, not source-use permission, strategy performance, a completed admission package or actual-run authority. Provider questions remain **UNSENT**.

## Published source and checks

Source commit: `c92074d8abd24a784d5af1b7fbb7397aa8e85b49`. Root's combined daily/source/preparer/panel/simulator/golden regression passed **164 tests in 27.54s**. After the final cache-retention correction, root's frozen qualification subset passed **66 in 24.84s**; strict typing passed 203 configured source files plus the standalone helper/test pair. Global Ruff lint and format passed 489 files. Goal hash remains `c886aca6b198257486d0daefc484f818458e60fa32a5aa861b95d1413282fa0c`.

The independent reviewer reintroduced ten known defects after the commit and verified substantive regression failures, including two strengthened fixtures that demonstrate actual acceptance escapes. Twelve mutant executions and two green controls are retained; ten distinct defects were caught. Every modified source was restored byte for byte. Fresh-bytecode regression passed **66 in 26.42s**; root independently confirmed no source/test/script diff and exact restored hashes. Details and log paths are in the [review](2026-10-17-daily-data-qualification-review.md).

Published prerequisite `cc995da` has successful [CI](https://github.com/Sujayprodduturi/Icarus/actions/runs/38894658706) and [resource proof](https://github.com/Sujayprodduturi/Icarus/actions/runs/38894658673). New source c92074d triggered [CI](https://github.com/Sujayprodduturi/Icarus/actions/runs/39007865100) and [resource proof](https://github.com/Sujayprodduturi/Icarus/actions/runs/39007865237); both were in progress at the recorded check. Those jobs are not pre-claimed successful.

## Real-source transient result

Root ran the reviewed binder/preparer in memory only under D55/D61. It emitted counts, digests and label dispositions; it called neither panel publication nor a strategy, simulator or trial ledger.

- Receipt: `var/verification/2026-10-17/daily-action-composition/composition-receipt.json`, SHA-256 `0917d707f27413a618a3e2249a7991bcc2ef97321ba99b17a196e3c0c0bb5430`, exit 0, no error.
- Exact staged c92074d code and input whitelist: 526 data/control files, including 514 raw/cache payloads, plus 95 package Python files and the reviewed entrypoint. Manifest SHA-256 `b9ffe3d29a4272afbb18aa3a21fde44f92587900fed6dda7b1a40c09cff6b788`.
- All 623 stage/manifest files, 157,475,667 bytes, unchanged before/after. State digest `2f2597ce49c9b1f02abcb9150c2289e28fc73da7ea3243b73cf9fa14d76317c2`.
- 693 labels × 257 sessions = 178,101 cells: 150,215 observed and 27,886 explicitly absent. All 185 reviewed raw-ISIN overrides applied. No requested observed cell required the sub-INR-1 exclusion; the earlier 330 source exclusions concerned the broader raw EQ population.
- 31 exact split/bonus rows, 29 action cuts, zero priceable pilot-session actions, five known unpriceable quarantines; no unexplained residual gap was accepted. In-memory panel arrays total 7,302,141 bytes.
- Root independently reconciled the five all-693 disposition sets: **232, 232, 227, 225, 226 eligible** on December 26–30. These are data-admission counts, not trades or returns.

The container used UID/GID 10002, network none, read-only root and exactly one read-only whitelisted mount, all capabilities dropped, no-new-privileges, 4 GiB memory, two CPUs and 64 PIDs. Broker SDKs, credentials and Docker socket were absent. Image ID: `sha256:108cdd2c8a2f9dc333c86256fce48d4ba1e37ec562be90c079c8019bd736da4c`; root independently reran its isolation probe. Launcher SHA-256 `bef9acfd674ee3e0e08fa4fb45111a1c9216332e97976a9b9e6f67f92cbf4e75`; entrypoint SHA-256 `0315dc3731bae9807ca5046ca0858baf9797316acb2c986bc9d04e994d1b483d`. Peak RSS was unavailable and is explicitly null; passing inside a hard cap is not a measured peak. The temporary container was removed.

## What remains

Applicable permission for the NSE website archive route is unresolved; the Kite subscription receipt contains no additional permission for that separate source. See the [source-use check](../data/2026-10-17-daily-source-use-check.md). No provider has been contacted.

Once that evidence is resolved, publish the reviewed all-label panel once, bind its encoded/decoded hashes and reviewed source/calendar/action/PIT dispositions into the existing qualification contract, complete the confined package/resource proof, and pass the separate actual-run authorization gate. The preparer's pending packet cannot grant those approvals. `DATA_QUALIFIED=false`, `source_use_authorized=false` and `RUN_AUTHORIZED=false` remain correct. No real-data strategy result, actual ledger activation, benchmark/alpha result, promotion claim or lockbox evaluation exists from this work.
