# Real-data bundle contract

This is the local input contract for the time-resolved simulator. Passing metadata preflight
means only that separately supplied evidence pins the exact local bytes. It does not prove that a
vendor is authoritative, that the licence permits this use, that the contents are complete, or
that a strategy may be run. The status fields stay separate:

- `SOFTWARE_VERIFIED`: the bounded parser and execution mechanics passed software checks.
- `DATA_QUALIFIED`: every payload passed its typed schema, causal, calendar, point-in-time,
  adjustment, coverage, and cross-artifact checks under independently reviewed source evidence.
- `RUN_AUTHORIZED`: a fresh external authorization pins the bundle, source policy, goal, seven
  cards, runner, mode and capital identities, and the actual PostgreSQL trial ledger is activated.

An independently dated qualification certificate sits between the first two statuses and run
authorization. It lives outside the uploaded bundle and pins the manifest, approval, matching
policy and required source-evidence identifiers. Its SHA-256 is part of the execution binding.
Software parsing cannot create this certificate or establish that a vendor claim is true.

Metadata preflight is the default and never decodes price records, evaluates DSL expressions,
reserves a trial, opens a database, or uses a network service.

Run the metadata-only gate with either the explicit `preflight` command or its equivalent
`check` alias:

```powershell
uv run python scripts/run_timed_backtest.py preflight --manifest 'C:\path\bundle\manifest.json' --approval 'C:\path\external\approval.json' --source-policy 'C:\path\external\source-policy.json'
```

Replace the quoted example paths with the local bundle and external-evidence paths. Omitting the
subcommand also defaults to metadata-only preflight. Execution is available only
through the explicit `run` subcommand and additionally requires `--matching-policy`,
`--qualification`, exactly three external-document flags—`--qualification-evidence
archive=PATH`, `--qualification-evidence licence=PATH`, and `--qualification-evidence
raw_event_availability=PATH`—plus `--authorization`, `--activated-ledger-dsn`, and `--out`
(with optional `--goal` and `--strategy-dir`). The qualification certificate contains eight
evidence-role hashes; the other five bind captured bundle artifacts and must not be supplied as
external-document flags. Do not supply execution flags until an external reviewer has qualified
the exact package and full-range resource evidence, and the operator has issued fresh run
authorization and activated the actual ledger. The next action is to obtain and review a
metadata/schema package and coverage/resource evidence; metadata success alone is not real-data
or study readiness.

## Files and external evidence

`manifest.json` has schema version 1 and exactly seven ordered artifacts: `daily_stock`,
`pit_universe`, `corporate_action`, `m15_stock`, `nifty_observation`, `session_calendar`, and
`opening_liquidity`. Each row records a relative member path, byte size, SHA-256, JSON/JSONL
format, schema and parser versions, vendor, venue, canonical instrument and price basis, source
revision, UTC retrieval time, UTC coverage, archival evidence, use evidence and projection policy.

The approval and matching-policy files must live outside the bundle tree. The approval pins the
manifest, policy and every artifact hash and records its authority, licence evidence, UTC approval
time, and whether it is invented. The policy records a dated source binding, exact contents hash,
resource limits, and one approved matching rule. An upload cannot approve itself. Symlinks,
junctions/reparse aliases, absolute paths, traversal, changed bytes, unknown or loose schemas,
duplicate roles, and excess sizes fail closed.

## Canonical event records

Every JSONL row is UTF-8 JSON with schema version 1, a stable `record_id`, source `revision`, and
explicit fields; unknown fields fail. Timestamps use UTC with `Z`. Numbers used in exact matching
are integer numerator/denominator pairs. Missing means unavailable and is represented explicitly;
rows and names are never deleted to make a run pass.

Calendar rows preserve full-source indices and `regular`, `special`, and `closed` dates. Open and
close timestamps are mandatory for open sessions and absent for closed dates. There is exactly one
row for every consecutive calendar date in the declared range, including weekends and holidays;
the first and last dates match the manifest coverage boundaries in IST. Daily stock rows,
point-in-time membership and corporate-action bases share the full daily axis. M15 rows use their
own declared 2015–2022 source range and map back to that full axis; walk-forward slices retain the
original indices. Any 2023-or-later lockbox overlap is rejected before price decoding.

Every daily symbol/session cell remains present. Its state is `OBSERVED`, `INACTIVE_ABSENT`, or
`DATA_GAP`. Observed cells carry all finite OHLCV strings and an empty reason. The other states
carry null for every OHLCV field and a nonempty reason. `INACTIVE_ABSENT` also requires daily
`tradable=false` and PIT `eligible=false`; it is the only state whose missing refinement can be
skipped when there is no holding or queued eligible intent. A `DATA_GAP`, or missing refinement
needed by a holding or queued intent, refuses the affected span and preserves residual inventory.
No price, exit, delisting sale, or cohort removal is invented.

Nifty observations identify `NIFTY 50`, venue `NSE`, and `PRICE_INDEX`. Each observation retains
its raw event time, availability time, revision, observed state, and exact price. Futures, TRI,
constituent reconstructions, interpolation, future-nearest selection, and implicit forward fills
are incompatible inputs. Exact matching requires the event itself at the resolved execution time.
The optional latest-available-observed rule requires an independently pinned nonnegative maximum
age and chooses only an observed event whose event and availability times are no later than the
resolved fill. Conflicting identities or revisions refuse the whole trade. Bar-resolved fills
remain intervals and cannot acquire exact point benchmark returns.

The separate daily projection policy is `EXACT_OBSERVED_SESSION_CLOSE`. Benchmark close requires
a raw observed index event at the calendar close that was available by that close. An exact
observed open may populate open; unsupported high, low and volume remain `NaN`. Sessions outside
declared Nifty coverage remain explicitly unavailable. No opening value is copied into close.

Opening-liquidity rows identify an earlier-available independent observation or a registered
prior-only calculation using the pinned method `PRIOR_OBSERVED_QUANTITY_V1`; availability must be
strictly earlier than the bar event. The eventual volume of the current M15 candle is forbidden as an opening
sizing input. The execution model still reconciles the whole batch against realized volume and
retains next-session execution, latency, strict-through resting limits, pessimistic queue position,
partial fills, and explicit no-fill outcomes.

## Counted execution

All seven cards are scheduled in signal mode and in separate portfolio reservations for the
Rs100,000 seed and Rs1,000,000 edge capital modes. The existing ledger contract allows exactly one
portfolio evaluation per batch, so capital modes never share one reservation. Every reservation
is durably obtained before the shared price payload is decoded or any DSL column is evaluated.
A recovery-only receipt, identity conflict, failed reservation, or missing ledger activation
stops before decoding. Results remain behind the durable terminal barrier; a lost completion
acknowledgement retries only the idempotent terminal persistence and never the evaluation.
Each reservation also stores the card's sorted, unique primitive inventory.

The raw Nifty observation artifact has its own source declaration using the captured vendor,
source revision and exact artifact SHA-256. Reports and evaluator inputs use this identity for the
benchmark; the equity session/M15 fixture digest is never substituted for benchmark provenance.

Reports are descriptive and pre-tax. They retain empty and refused cards, costs, residual
holdings, benchmark coverage and refusal reasons, and original execution times. They do not claim
after-tax alpha, statistical applicability, inference, promotion, or Validation readiness.

The currently advertised NSE cash-market and index products are availability leads only. Their
coverage, licence, event/availability semantics, corporate-action basis, opening-liquidity source,
and complete regular/special-session calendar have not been qualified. No real run is authorized.
