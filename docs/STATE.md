# STATE.md — where Icarus actually is, today

Updated 2026-10-06 after strategy simulator progress, Linux safety repair and fresh runner qualification.

**Current milestone: all three catalogue strategies exercised in both simulators on invented prices. Full statistical-study readiness still FAILED.** Unit3/R4 and Task3a/M1-M4/F48 remain OPEN. No actual attempt, study key or experimental draw; inference, real-market, official, lockbox, broker and live paths remain held.

The unchanged catalogue produced signal/portfolio trades: baseline24/4, Donlevey191/72, momentum290/70. Independent review checked next-bar execution, trade accounting and prefix-only entry/rank behavior. These are mechanics tests, not profitability evidence. Charges are modeled; toy amounts are before capital-gains tax and after-tax promotion metrics remain unavailable. [Simulation results](reviews/2026-10-06-synthetic-strategy-simulation.json).

**Verified candidate:** exact33-file manifest94d6be4f plus both demo sources;889 calendar/portfolio/characterization/audit/signal/demo tests pass389.08s. Strict181-source typing, global Ruff and352-file format checks pass. Six explicit rejection cases pass, including lost terminal channels; tests verify durable rejection and stopped children instead of requiring a graceful reply after a watchdog halt. Production watchdog remains immediate.

The current Linux CI failure at7448b72 was traced to psutil treating unreaped zombies as running. The identity check now rejects zombie/dead status and status-query errors. Meaningful RED/GREEN and independent source review pass; native Linux CI verification remains pending.

Two bounded profiles completed, with both oracles reproducing40 histories/112 metrics. Fresh dependency metadata is still discovered/read on every check; only inherited parsing of identical fresh text is memoized, with two bounded entries. Isolated parsing work improves, but **no integrated speedup or optimal budget is demonstrated**. [Progress record](reviews/2026-10-06-simulator-progress.md).

**Fresh budget blocker:** all three complete cold runs16.172/16.188/16.063s fail both unchanged timing models. Both independent checkers reproduce six phases,60 histories and168 metrics plus provenance. Refined independent worst-case projections: development writer8.75h versus6h; validation writer34.99h versus12h; validation verifiers24.45h/23.90h versus16h; session161.34h versus82h10m. These are conservative projections, not measured multi-day runtimes. No allowance or statistical threshold changed. [Cold qualification](reviews/2026-10-06-runner-cold-qualification.json).

Exactly four profile and six cold-run raw files were removed only after dual verification and compact retention under D44. Raw replay is unavailable; failed/incomplete cases and all previous failures remain. [Profile cleanup](reviews/2026-10-06-runner-cost-profile-cleanup.json), [cold cleanup](reviews/2026-10-06-runner-cold-cleanup.json).

**Next:** complete postcommit defect/restoration verification and push this progress; then address remaining full-runner cost before any actual sampled study. Do not redo completed profiling or treat mechanics results as a trading-performance gate. Real-data simulation remains a separate operator stop.

Protocol130569a7, goal c886aca6, resource96199af0, original plan5818b086 and refinement ae14fa20 remain unchanged. Prior118de923 qualification and failures remain historical evidence, not current-source permission. Commit/restoration/push receipts follow separately. Jev/Laya remain optional future text classifiers; neither is adopted.
