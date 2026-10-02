# Calendar research runner: ordered simplicity and engineering review

Date: 2026-10-02. Independent GPT-6 Astra, medium effort. Status: REQUEST CHANGES pending final repaired-source review. No experimental study was launched by this reviewer.

## Ordered actual skills

Read and applied `C:/Users/sujay/.agents/skills/ponytail-review/SKILL.md` first to the four new source modules, their four test files and the implementation plan. Source structure was lean for the approved research scope. Requested removal of obsolete dynamic module-discovery helpers in compact, runner and statistics tests; primary confirms these test-only simplifications are implemented. Only after primary confirmation did this reviewer read and apply `C:/Users/sujay/.codex/plugins/cache/claude-cowork/engineering/1.2.0/skills/code-review/SKILL.md`.

## Independently hashed initial engineering snapshot

- `signal_calendar_runner.py`: `b5603f0dfc96b6e0291a31c9725410ca3901ebe73a3ee4a354779c72b2bc8a73`.
- `signal_calendar_compact.py`: `e18e49a7d8cdf8d3c975a08c6b4267bb37d3d0ca42a25f9c793f5ad29d442969`.
- `signal_calendar_laws.py`: `811070fa4247a10c5aad612829a6b3f20421f04793a77a3b44017e7ee18b6ba4`.
- `signal_calendar_statistics.py`: `136a0b8425f2012f6e2bd0f2153481a235a13636654a5c3339c1e4e79c67e288`.
- Unchanged reference calculator: `ef28eeebb2c807bbbed2c707cd1e20a752d448b537646a7beea0426fe2828ec9`.

## Findings requiring correction

1. Preflight tests only aggregate `arithmetic > 0`; it does not require endpoint-producing witnesses for every family/metric. Independent deterministic actual-API checks found no such witness for P3/n64/win or P3/n128/win under patterns0/1. Other cells make the aggregate positive, hiding their omitted endpoint costs. Require all52 cell witnesses and include their arithmetic/encoding/replay work in feasibility measurements; absence must block. Root confirmed this finding and reports a fix in progress.
2. `verify()` issues the live verified marker before successful terminal persistence and without excluding earlier failed attempts. Thus complete retained path evidence from a failed/timed-out attempt can be independently verified and then authorize confirmation despite the no-resume contract. Return ordinary verified data from the verifier; issue live completion authority only after the parent successfully persists COMPLETE. Root reproduced this issue and reports that repair in progress.
3. `_Confirmation` is reusable: no consumption or persistent stream reservation prevents the same permission/phase seed from launching another destination after success or failure. Consume authority once at claim, preserve consumed state on failure and bind append-only stream identity so changing destination cannot silently redraw an already claimed stream. A separately reviewed retry amendment must not be confused with automatic replay/resume.

## Resource and scope assessment

Read the dated amendment and implementation plan. The amendment keeps original statistics and changes confirmation only to10800 seconds/3GiB, preserving development1800 seconds/2GiB and memory2GiB. Both original protocol and amendment are source-bound. Compact integer aggregation and packed Decimal evidence retain the reference estimator and required results; final equivalence/encoding checks still need the frozen-source rereview.

Current preflight is a measured projection, not a worst-case proof: deterministic patterns plus fixed margins do not establish execution time or artifact size for every possible path. This limitation is explicitly disclosed in the amendment. Per-cell nondegenerate witnesses and runtime cancellation remain necessary, and a passing projection alone is not independent acceptance of the operational envelope. This reviewer has not independently measured final full-size throughput/storage or run the full suite.

Final approval requires the three findings to be closed and the exact final source/test hashes verified. Any interim primary test result belongs to its stated source; this initial review is not a final attestation.

## Repaired-source verification and remaining retry identity finding

Independently verified runner SHA256 `b23f223733609957e24305bcef7addad825c5772c32f63d7b9b66336816029e2`. The all52-cell witness gate, non-authorizing raw verifier and post-terminal-fsync live marker are implemented. Persistent exclusive stream claims prevent repeating the same phase/seed into a different destination. Independent focused run of all four new test files:77 passed in5.87 seconds, process exit0. This includes all-family compact/reference equivalence, all52 witness coverage, raw replay denial and same-stream retry rejection. Test-only deterministic byte mappings were exercised; no experimental study was launched.

One related retry gap remains: the same live passing development report can issue another confirmation permission with a different confirmation commitment after an earlier attempt fails. The stream reservation only binds the actual phase/seed, so a changed confirmation seed avoids it without a reviewed amendment. Bind a one-shot confirmation-family claim to the verified development identity, or consume the live development completion capability when confirmation is first claimed. Keep this consumed after failure. Status remains REQUEST CHANGES for that narrow issue; the original three findings are closed in this snapshot.

## Final engineering verdict: APPROVE

Independently inspected and hashed final runner `1f94d8fd5d96e5726bced011d86ca904d43b3131c2418cc1f0c2b3adc006f53f`. All four findings are closed. Before worker launch, confirmation now creates an exclusive persistent claim keyed by the exact manifest and verified development seed commitment. A different confirmation seed cannot reroll the same development identity after failure or success. The existing separate stream claim also prevents identical phase/seed reuse. Raw replay still carries no authority; only successfully fsynced terminal completion permits the live marker.

Independently ran the final runner tests:27 passed in2.48 seconds, process exit0. The timeout test now explicitly attempts confirmation with two different seeds and the same development identity: the first retains its ERROR; the second fails the persistent family reservation and also retains ERROR. The earlier independent77-test run covered all four modules; the final focused rerun covers the subsequent runner repair. No experimental development/confirmation study was launched by this reviewer.

Final verified source hashes for compact, laws and statistics remain the initial hashes listed above. Final test SHA256 values:

- compact: `1b83090729c92ed440182ef58ead458db36a9202bc24b4c062e939ab4ebb53bc`.
- laws: `28bc331c7b2af382402b98846abd00a26a7f214c2cc11e534d9df661f92ee6a4`.
- runner: `e1869154c4b3bcf9db1b41331fddcd5aa31610275d649ed9428f0875a71c49ec`.
- statistics: `d8f9d12767e48e4fcf6b4f2d7540c124ec30878c4b62dbceefa658bff866ade5`.
- Resource amendment: `06ab50ce55fc0b6eb225f7959d7202ad8afc11835bc0c9bf5f367bd51bba9d7c`.

This approves the bounded research implementation after the required actual simplicity-then-engineering sequence. It does not certify all-path runtime/storage, independent mathematical assumptions, market inference, statistical acceptance or the official Windows resource/durability contract. Exact-source measured preflight and all other pre-draw checks remain required; no claim is made here that the primary's prior timing projection applies unchanged to this repaired hash. The original blocked feasibility evidence and all review findings remain retained above.
