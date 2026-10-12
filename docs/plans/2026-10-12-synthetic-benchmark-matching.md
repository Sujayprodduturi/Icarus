# Synthetic exact-time benchmark matcher — 2026-10-12

The operator's latest instruction schedules this bounded synthetic prerequisite under the
standing major-milestone cadence. This dated amendment implements one isolated research helper
and tests. It does not adopt the2026-09-26 umbrella design as product code or authorize real data.

## What it does

Given invented entry/exit timing records and invented index observations, compute the index's
return over exactly the modeled holding times. Keep one original filled quantity and all partial
exit quantities. Return no whole-trade value when any required leg lacks a defensible match.
This is arithmetic under declared synthetic assumptions, not authenticated market evidence.

## Small implementation

Only `scripts/research/synthetic_benchmark_match.py` and
`tests/unit/test_synthetic_benchmark_match.py` are production/test scope. Use stdlib immutable
typed records and exact `Fraction` arithmetic. No dependencies, I/O, CLI, source acquisition,
generic provenance framework or integration into existing simulators/demo/metrics/ledger.

Records describe:

- Timing precision: session-only, bar-resolved or event-resolved; optional exact instant and
  interval bounds. Given timestamps must be UTC-aware; impossible intervals fail closed.
- An invented trade's original positive filled quantity and immutable exit fragments with
  unique identities, positive quantities, executed-versus-stale status, timing, price-source
  and recognition times. Stale source and recognition remain separate.
- Declared fixture benchmark identity/version/price basis and artifact identity/hash/schema,
  plus observation record identity, event time, availability time, positive rational level and
  observed/stale/synthesized state. OBSERVED represents an observed tick inside invented data;
  constructors and supplied hashes do not certify actual sources or calendars.

Pin malformed type/value/schema/timezone/interval/price errors as fail-closed constructor
exceptions. Missing, unresolved, stale, conflicting or incompatible well-typed declarations
and incomplete total quantity produce explicit matcher refusals. Tests distinguish those paths.

## Fixed matching and arithmetic

The policy is SYNTHETIC_EXACT_TIMESTAMP_ONLY. Each leg requires event-resolved timing and one
unique index observation whose event timestamp equals the fill timestamp and whose availability
is no later than that fill. Availability before its observation event is impossible chronology.
Session/bar labels refuse even if bounds coincide. A nonzero event interval cannot become a
point. No nearest/asof fallback, interpolation, forward-fill or daily-open approximation.

Compare observation benchmark/basis/artifact declarations against the expected fixture identity.
Reject duplicate/conflicting record IDs or timestamps; never silently overwrite or choose one.
Validate chronological ordering and exact sum(exit quantities)=original filled quantity. Any
stale-mark residual refuses the whole-trade match even when its recognition time has an index
quote. No-fill/zero quantity cannot masquerade as a completed executed fragment.

Compute `sum((q_j / Q_original) * (index_exit_j / index_entry - 1))` with exact rationals.
For example, Q100, exits25/75 and levels100 to102/104 give7/200. One absent exit leg yields
None, not a reweighted available subset. Report immutable per-leg refusal/coverage diagnostics;
observed zero return remains distinct from unavailable. Inputs remain untouched.

Return only explicitly scoped synthetic benchmark-return arithmetic. No stock-return subtraction,
alpha, confidence, p-values, profitability, promotion or market-eligibility/certification switch.
Existing product caller-supplied benchmark fields stay untouched; no adapter derives precision
from their daily timestamps. Actual M15 execution replay, source-specific age/sampling rules,
authoritative source/calendar/benchmark evidence, excess/accounting integration, M4/method
adoption, real trial-ledger activation and D41 real-data permission remain held. Zero age is a
fixture policy, not an approved vendor rule. Goal, cards, existing engines and study streams stay
unchanged; inference remains disabled, with no lockbox, broker or live path.

## Proof before completion

TDD: unequal-fragment hand calculation; exact-zero result; incomplete quantity and one missing
partial leg; late availability; daily false precision and ambiguous/collapsed M15 labels;
stale price-source versus recognition; duplicates/conflicts; benchmark/basis/artifact mismatch;
invalid UTC/schema/price/quantity declarations; immutable inputs and explicit synthetic output.
Use deterministic invented records only, no random draws or real panels. Run focused/related
signal and golden tests, strict explicit mypy and global Ruff. Independent simplicity then
correctness review must verify arithmetic and failure paths. Freeze source before commit;
known-bug variants run postcommit only with exact restoration and fresh positive tests.
Record exact proof and current checkpoints, publish once, and inspect new-source hosted checks.

Prerequisite2922109 CI38234029118 passed2992 tests/four skips and resource38234029185 SUCCESS,
freshly verified2026-10-12. Those receipts do not pre-approve later source changes.
