# Simulator progress and runner repairs

The operator asked on 2026-10-06 to resolve stalled progress and actually test the strategies. All three unchanged catalogue strategies now run on deterministic invented prices through SignalSimulator and PortfolioSimulator. The final exact-source case is `catalogue-20261006-final`; the independent reviewer reproduced trade accounting and prefix-only entry/rank behavior. The retained [simulation evidence](2026-10-06-synthetic-strategy-simulation.json) contains source hashes, trial records and reviewer checks.

| Strategy | Signal trades | Portfolio trades |
|---|---:|---:|
| Baseline buy and hold | 24 | 4 |
| Donlevey sweep/reclaim | 191 | 72 |
| Cross-sectional momentum 20 | 290 | 70 |

These are mechanics tests, not evidence of trading edge. Prices are invented; no market data, broker connection, official study draw, lockbox or live order was used. Charges are modeled; toy net amounts are before capital-gains tax, and after-tax promotion metrics remain unavailable. Inference is disabled. The original first demonstration's evaluator count was clarified append-only; the final run records both simulator evaluations before each strategy executes.

The Linux CI failure at revision7448b72 was independently traced to psutil treating an unreaped zombie as running. ProcessIdentity now rejects zombie/dead status and status-query errors while retaining PID/creation-time matching. Meaningful RED caught four bad cases; GREEN passed all eight. Native Linux CI must verify the original killed-helper integration test before a native pass is claimed.

Two bounded cost profiles completed under the existing public deterministic fixture API. Both primary and reviewer independently reproduced all four saved phases, 40 histories and112 metrics. Profile times are instrumented and overlap; they do not qualify readiness. [Profiles](2026-10-06-runner-cost-profiles.json) and [cleanup evidence](2026-10-06-runner-cost-profile-cleanup.json) retain compact provenance. Four exact dual-verified raw payloads were removed; raw replay is unavailable.

The measured repeated cost was dependency metadata parsing during fresh source checks. A two-entry cache now reuses only parsing of freshly read complete text, using the inherited standard-library parser. Discovery, metadata reads, source/resource checks, errors and guard frequency remain fresh. Folded/duplicate/missing/surrogate/oversized cases and warmed replacement/removal/fallback/errors passed; independent review approved the exact source. No threshold, timing allowance, stream, numerical law or statistical gate changed.

The first broad regression was invalidated by a primary test-annotation edit during its run:878 passes, one correct source-drift halt. A subsequent frozen regression produced886 passes and one test failure caused by the watchdog halting a forbidden coordinator approval before a graceful ERROR reply. A focused rerun exposed the same competing halt paths for a second key release. Production remains fail-closed; the test now accepts only the observed authentication exception with exact case/session/source-bound rejection records, stopped child identities and proof of no unauthorized approval/release/validation/publication. Second-release checks bind the single original release to its sealed commitment and exact approval evidence. Explicit terminal-channel-loss cases exercise these assertions.

Final regression, cold qualification and commit receipts will be appended after verification. Unit3/R4 and Task3a/M1-M4/F48 remain OPEN; no actual sampling permission is granted by this document.
