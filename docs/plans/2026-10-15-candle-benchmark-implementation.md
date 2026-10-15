# Descriptive Candle Benchmark Implementation Plan

## Frozen review repair addendum — 2026-10-15

- Refuse nonexecuted exit fragments as typed whole-trade candle-comparison unavailability and exclude them from matched coverage.
- Enforce exact integer schema version 2, exact nonnegative integer source indices, and exactly 15-minute benchmark candles at construction and parsing boundaries.
- Emit the captured-record limitation, net-stock/gross-index cost asymmetry, modeled-vs-raw availability interpretation, and per-run comparable/unavailable counts in every descriptive report.
- Retain tracked acceptance for all registered benchmark consumers plus both shared engine wrappers' successor and terminal rebalance behavior.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add one opt-in, synthetic-only `DESCRIPTIVE_CANDLE_PROXY` path through the existing guarded timed CLI, both timed engines, benchmark evaluation, and report while preserving the strict exact-observation default byte-for-byte.

**Architecture:** Extend the existing closed bundle and matching-policy contracts with a mode-discriminated benchmark candle role. Assemble descriptive panels with `Panel.benchmark=None`, bind one next-session-open decision-availability schedule to the timed fixture, route that schedule through the existing signal and portfolio engines, and dispatch completed trades to a separate captured-candle interval matcher. Keep qualification, authorization, source-pair validation, and durable reservation ahead of price decoding and reuse `GuardedTimedRunner`; no runner, ledger, strategy activation, broker, archive, lockbox, or promotion path is added.

**Tech Stack:** Python 3.12, frozen dataclasses/enums, `Fraction`/`Decimal`, NumPy, pytest, mypy, Ruff, uv.

**Spec:** `docs/plans/2026-10-15-candle-benchmark-method.md`; final design approval: `docs/reviews/2026-10-15-candle-benchmark-method-review.md`.

## Global Constraints

- `EXACT_OBSERVED_SESSION_CLOSE` remains the default; its fixture digest, public CLI behavior, timing, and exact matcher are unchanged.
- `DESCRIPTIVE_CANDLE_PROXY` is explicit and has no fallback to or from strict mode.
- Raw publication/revision time remains nullable and distinct from modeled interval-end or next-session-open availability.
- External policy, qualification, authorization, source-pair, rights/use, coverage, calendar, adjustment, and artifact bindings are checked before price decoding; the unchanged trial reservation occurs before shared price decode.
- Preserve source index `t` and physical `Session.close_ts`; one sealed schedule maps `t` to declared session `t+1` open, with terminal `t` unavailable.
- Entries, opposite-signal exits, and scheduled rebalances in both timed engines require an M15 bar start strictly later than modeled availability and must also satisfy existing latency; active protective stops are never delayed.
- Descriptive panels carry `benchmark=None`; refuse every `require_benchmark` consumer before any DSL column evaluation (the five current primitive names plus future registry entries), with no shifted benchmark view.
- Benchmark candle arithmetic accepts positive OHLC and signed return endpoints; only fully closed, single-entry trades with exact executed-quantity coverage are comparable.
- Output is a captured-candle interval with `promotion_eligible=false`; do not emit a midpoint, exact benchmark return, aggregate/proxy alpha, Information Ratio, DSR/PBO, after-tax metric, or promotion evidence.
- Do not run real data, activate a strategy/ledger, touch broker/auth paths, build a price archive, consume the lockbox, or introduce a numeric threshold.
- Preserve existing mixed newline styles and use byte-preserving targeted edits; never rewrite a whole existing file.
- Verification logs belong under `var/verification/2026-10-15/candle-replay-build/`; use `UV_CACHE_DIR=C:\ICARUS\var\uv-cache` and purposeful escalated offline test commands because sandboxed pytest imports can stall.

## File Ownership

- Modify: `icarus/engine/timing.py` — immutable modeled decision-availability contract and opt-in digest binding.
- Modify: `icarus/engine/benchmark_match.py` — benchmark candle types, typed refusals, captured-return interval matcher.
- Modify: `icarus/engine/timed_runner.py` — closed role parsing, qualification-before-decode assembly, descriptive panel/fixture creation.
- Modify: `icarus/engine/timed_simulation.py` — shared decision-availability accessor used by the signal engine.
- Modify: `icarus/engine/timed_simulation.py` — the same common event loop already implements both signal and portfolio modes, including entries, opposite exits, and rebalances.
- Modify: `icarus/engine/timed_evaluation.py` — pre-DSL benchmark-consumer refusal, mode dispatch, cost/notional comparison, descriptive serialization.
- Modify: `scripts/run_timed_backtest.py` — public CLI mode binding and descriptive report fields through the existing runner.
- Modify: `tests/unit/test_timed_runner.py`, `tests/unit/test_timed_strategy_management.py`, `tests/unit/test_timed_evaluation.py`, `tests/unit/test_timed_cli.py` — RED-first contract, engine, evaluator, and public CLI coverage.
- Modify only if the production contracts replace its current exact-only helper cleanly: `tests/unit/test_synthetic_execution_replay.py`; do not create another runtime replay framework.
- Create/update verification logs only under the declared verification directory. Root retains ownership of `docs/STATE.md`, `docs/HANDOVER.md`, `OPERATOR.md`, method/design review, and build report.

## Current Contracts to Preserve

```python
assemble_timed_inputs(preflight: BundlePreflight, source_pair: PairQualification | None = None) -> AssembledTimedInputs
run_timed(strategy: StrategyCandidate, panel: Panel, signals: Mapping[str, Column], stops: Mapping[str, Column], *, fixture: TimedFixture, source_indices: Sequence[int], fills: FillModel, costs: CostModel, ...) -> TimedRun
CataloguePayload.from_assembled(assembled: AssembledTimedInputs, cards: tuple[StrategySpec, ...]) -> CataloguePayload
GuardedTimedRunner.run(authorization, binding, plans, payload_factory, evaluator) -> tuple[tuple[EvaluationOutcome, ...], ...]
Panel.require_benchmark(where: str) -> Bars
match_benchmark(trade: SyntheticTrade, observations: ObservationIndex, policy: MatchingPolicy, expected: FixtureIdentity) -> BenchmarkMatch
```

The implementation may add keyword-only mode/candle arguments or immutable fields with strict-mode defaults, but it must not change the behavior of calls using these current signatures.

## Review Focus

- A terminal daily row, calendar gap, or duplicate next session must produce typed unavailability and never infer an open.
- A benchmark primitive hidden in any card expression/rank/exit field must be refused before the first DSL evaluator call.
- A candle containing a fill retrospectively may match after interval completion, but it can never become a causal strategy input.
- Quantity mismatch, residual inventory, multiple entries, overlapping/duplicate candles, or a stock interval spanning two benchmark intervals must refuse the whole comparison without partial output.
- A strict fixture and its hash must be identical before and after this feature, while any descriptive schedule or policy mutation changes the opt-in identity.

---

### Task 1: Closed candle contract, loader, and opt-in fixture identity

**Files:**
- Modify: `icarus/engine/timing.py`
- Modify: `icarus/engine/benchmark_match.py`
- Modify: `icarus/engine/timed_runner.py`
- Test: `tests/unit/test_timed_runner.py`

**Interfaces:**
- Consumes: existing `BundlePreflight`, captured artifact metadata/bytes, `Session`, `TimedFixture`, `Panel.build`, `SourceDeclaration`, and `timed_fixture_digest`.
- Produces: `BenchmarkMode`, `AvailabilityBasis`, `BenchmarkCandle`, `DecisionAvailability`, descriptive fields on `AssembledTimedInputs`, `parse_benchmark_candle_jsonl(raw: bytes, expected: SourceDeclaration) -> tuple[BenchmarkCandle, ...]`, and `decision_available_ts(fixture: TimedFixture, source_index: int) -> datetime | None`.

- [ ] **Step 1: Write failing parser, assembly, and identity tests**

```python
def test_descriptive_assembly_is_closed_mode_and_has_no_dsl_benchmark() -> None:
    assembled = assemble_timed_inputs(
        candle_preflight(), mode=BenchmarkMode.DESCRIPTIVE_CANDLE_PROXY
    )
    assert assembled.panel.benchmark is None
    assert assembled.benchmark_mode is BenchmarkMode.DESCRIPTIVE_CANDLE_PROXY
    assert assembled.fixture.sessions[0].index == assembled.decision_availability[0].source_index
    assert (
        assembled.decision_availability[0].modeled_available_ts
        == assembled.fixture.sessions[1].open_ts
    )
    assert assembled.decision_availability[-1].modeled_available_ts is None


def test_raw_unknown_is_not_filled_from_modeled_or_retrieval_time() -> None:
    candle = parse_benchmark_candle_jsonl(candle_bytes(raw_available_ts=None), expected_source())[0]
    assert candle.raw_available_ts is None
    assert candle.modeled_available_ts == candle.interval_end_ts


def test_strict_default_hash_is_unchanged_and_descriptive_schedule_is_bound() -> None:
    assert timed_fixture_digest(strict.sessions, strict.refinements, strict.inactive) == frozen_hash
    assert descriptive.digest != replace(descriptive, decision_availability=mutated).digest
```

- [ ] **Step 2: Run the focused tests and record the intended RED result**

Run outside the sandbox, offline, with `UV_CACHE_DIR=C:\ICARUS\var\uv-cache`:

```powershell
uv run --offline pytest tests/unit/test_timed_runner.py -k "descriptive or decision_availability or strict_default_hash" -q
```

Expected: FAIL because the closed candle mode/types/parser and schedule binding do not exist; save stdout/stderr and exit code as `01-contract-red.log`.

- [ ] **Step 3: Implement the minimal closed contracts and parser**

```python
class BenchmarkMode(StrEnum):
    EXACT_OBSERVED_SESSION_CLOSE = "EXACT_OBSERVED_SESSION_CLOSE"
    DESCRIPTIVE_CANDLE_PROXY = "DESCRIPTIVE_CANDLE_PROXY"


class AvailabilityBasis(StrEnum):
    MODELED_INTERVAL_END = "MODELED_INTERVAL_END"
    MODELED_NEXT_SESSION_OPEN = "MODELED_NEXT_SESSION_OPEN"


@dataclass(frozen=True, slots=True)
class DecisionAvailability:
    source_index: int
    raw_available_ts: datetime | None
    modeled_available_ts: datetime | None
    basis: AvailabilityBasis


@dataclass(frozen=True, slots=True)
class BenchmarkCandle:
    source: SourceDeclaration
    record_id: str
    revision: str
    session_index: int
    interval_start_ts: datetime
    interval_end_ts: datetime
    open: Fraction
    high: Fraction
    low: Fraction
    close: Fraction
    raw_available_ts: datetime | None
    modeled_available_ts: datetime
    basis: AvailabilityBasis
    quarantined: bool
```

Validate an exact schema, source identity, Price Index basis, ordered positive OHLC, half-open M15 interval, declared session membership, uniqueness, non-overlap, quarantine, and nullable raw facts. In descriptive mode derive availability only by adjacent declared sessions and include the policy/model identifier plus every `(source_index, modeled_available_ts)` in the opt-in digest. Branch around only the strict Nifty daily projection; construct `Panel.build(..., benchmark=None)`. Strict mode continues using the existing artifacts, projection, and digest call unchanged.

- [ ] **Step 4: Run focused GREEN and strict regression tests**

```powershell
uv run --offline pytest tests/unit/test_timed_runner.py tests/unit/test_timing.py -q
```

Expected: PASS; store `01-contract-green.log`. Confirm the previously frozen strict digest assertion is unchanged.

### Task 2: Shared modeled decision availability in both timed engines

**Files:**
- Modify: `icarus/engine/timing.py`
- Modify: `icarus/engine/timed_simulation.py`
- Modify: `icarus/engine/timed_simulation.py` (the existing shared signal/portfolio event loop)
- Modify: `icarus/engine/timed_evaluation.py`
- Test: `tests/unit/test_timed_strategy_management.py`
- Test: `tests/unit/test_timed_evaluation.py`

**Interfaces:**
- Consumes: `decision_available_ts(fixture, source_index)`, existing latency, queued signal/management events, protective-stop branches, loaded strategy primitive inventory.
- Produces: one shared timestamp for entry, opposite exit, and scheduled rebalance decisions in signal and portfolio modes; `UnsupportedBenchmarkConsumer` before DSL evaluation.

- [ ] **Step 1: Write failing timing, terminal, stop, and pre-DSL tests**

```python
@pytest.mark.parametrize("mode", ["signal", "portfolio"])
@pytest.mark.parametrize("action", ["entry", "opposite_exit", "rebalance"])
def test_next_open_availability_skips_opening_bar_but_keeps_source_index(
    mode: str, action: str
) -> None:
    run = run_descriptive_case(mode=mode, action=action)
    assert run.trace.source_index == 10
    assert run.trace.decision_available_ts == sessions[11].open_ts
    assert run.trace.execution.interval_start == sessions[11].open_ts + timedelta(minutes=15)


def test_terminal_row_cannot_create_new_decision_but_active_stop_still_fires() -> None:
    run = run_terminal_case(with_active_stop=True)
    assert run.new_decisions == ()
    assert run.stop_exit.execution_ts == terminal_bar.ts


def test_benchmark_consumer_refuses_before_dsl_evaluation(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(evaluator, "evaluate_columns", lambda *_: pytest.fail("DSL evaluated"))
    with pytest.raises(UnsupportedBenchmarkConsumer, match="benchmark_return"):
        CataloguePayload.from_assembled(descriptive, (card_using("benchmark_return"),))
```

- [ ] **Step 2: Run focused tests and record RED**

```powershell
uv run --offline pytest tests/unit/test_timed_strategy_management.py tests/unit/test_timed_evaluation.py -k "next_open or terminal or active_stop or benchmark_consumer" -q
```

Expected: FAIL on current `session.close_ts` scheduling and missing early refusal; save `02-availability-red.log`.

- [ ] **Step 3: Replace decision scheduling with the shared accessor**

```python
available = decision_available_ts(fixture, session.index)
if available is None:
    continue  # typed terminal unavailability; never infer a date
queued.append((signal, daily_by_source[session.index], available))

eligible = bar.bar.ts > available and bar.bar.ts >= available + latency
```

Use the accessor at every current close-time decision site for entries, opposite exits, and rebalances in both modes. Keep source index and daily arrays at `t`. Leave the protective-stop path independent of the new decision clock. Discover benchmark consumers from the registered primitive metadata/compiled card inventory and refuse any `require_benchmark` consumer before evaluating a column; do not hard-code only the five current card strings.

- [ ] **Step 4: Run GREEN plus existing management regressions**

```powershell
uv run --offline pytest tests/unit/test_timed_strategy_management.py tests/unit/test_timed_evaluation.py tests/unit/test_strategy_consumers.py -q
```

Expected: PASS; save `02-availability-green.log`.

### Task 3: Captured-candle interval matcher and exact trade cash-flow comparison

**Files:**
- Modify: `icarus/engine/benchmark_match.py`
- Modify: `icarus/engine/timed_evaluation.py`
- Test: `tests/unit/test_timed_evaluation.py`
- Test: `tests/unit/test_synthetic_execution_replay.py`

**Interfaces:**
- Consumes: `TimedTrade`, existing entry/exit `Timing`, actual executed quantities, allocated entry/exit charges, `BenchmarkCandle`, source seals, and `BenchmarkMode`.
- Produces: `match_candle_benchmark(...) -> CandleBenchmarkMatch`, `CapturedReturnInterval`, `DescriptiveTradeComparison`, typed per-leg/whole-trade refusals, and mode dispatch from `_trade_benchmark`.

- [ ] **Step 1: Write failing exact-arithmetic and refusal tests**

```python
def test_exact_captured_interval_and_costed_stock_excess() -> None:
    result = compare_closed_trade(
        stock_entry=Fraction(100),
        stock_exits=((1, Fraction(125)), (1, Fraction(95))),
        total_allocated_cost=Fraction(4),
        benchmark_entry=(Fraction(100), Fraction(110)),
        benchmark_exits=((1, Fraction(120), Fraction(130)), (1, Fraction(90), Fraction(100))),
    )
    assert result.benchmark_interval == (Fraction(-1, 22), Fraction(3, 20))
    assert result.stock_return == Fraction(2, 25)
    assert result.excess_interval == (Fraction(-7, 100), Fraction(69, 550))
    assert result.promotion_eligible is False


@pytest.mark.parametrize(
    "case",
    [
        "missing",
        "duplicate",
        "overlap",
        "quarantine",
        "identity",
        "adjustment",
        "wrong_session",
        "quantity_mismatch",
        "multiple_entries",
        "open_inventory",
        "multi_interval",
    ],
)
def test_whole_trade_refusal_never_emits_partial_comparison(case: str) -> None:
    result = descriptive_case(case)
    assert result.interval is None and result.refusals
```

- [ ] **Step 2: Run focused tests and record RED**

```powershell
uv run --offline pytest tests/unit/test_synthetic_execution_replay.py tests/unit/test_timed_evaluation.py -k "captured or candle or exact_arithmetic or whole_trade_refusal" -q
```

Expected: FAIL because candle matching and descriptive cash-flow output do not exist; save `03-matcher-red.log`.

- [ ] **Step 3: Implement the minimal retrospective matcher and comparison**

```python
lower = sum(
    Fraction(exit.quantity, trade.original_quantity) * (exit.low / entry.high - 1) for exit in exits
)
upper = sum(
    Fraction(exit.quantity, trade.original_quantity) * (exit.high / entry.low - 1) for exit in exits
)
stock_return = trade.fully_allocated_realised_net_pnl_before_tax / (
    trade.entry.executed_price * trade.original_quantity
)
excess = CapturedReturnInterval(stock_return - upper, stock_return - lower)
```

Select exactly one qualified half-open benchmark interval for each event-resolved fill, or the identical interval for a bar-resolved leg. Do not require the retrospective candle's modeled completion time to precede the fill. Require one executed entry, closed inventory, exact `sum(exit.quantity) == original_quantity`, positive prices, finite ordered endpoints, and complete cost allocation. Serialize every matched candle ID/interval, raw availability (possibly `None`), modeled basis/time, refusal, stock cost basis, tax status, `promotion_eligible=false`, and the labels `captured_candle_price_return_interval` / `descriptive_excess_interval`.

- [ ] **Step 4: Prove signed returns and forbidden-field absence**

Add tests where valid positive prices yield negative and zero bounds and where a deliberately omitted extreme changes only the captured-record interval claim. Recursively assert the descriptive payload contains none of:

```python
{
    "midpoint",
    "alpha",
    "information_ratio",
    "dsr",
    "pbo",
    "validation",
    "after_tax_promotion_metrics",
}
```

Run:

```powershell
uv run --offline pytest tests/unit/test_synthetic_execution_replay.py tests/unit/test_timed_evaluation.py -q
```

Expected: PASS; save `03-matcher-green.log`.

### Task 4: Existing guarded public CLI, 21-plan synthetic vertical, and CI gate

**Files:**
- Modify: `scripts/run_timed_backtest.py`
- Modify: `tests/unit/test_timed_cli.py`
- Modify: `tests/unit/test_timed_evaluation.py`
- Verification: `var/verification/2026-10-15/candle-replay-build/*`

**Interfaces:**
- Consumes: current `run` CLI, `GuardedTimedRunner`, seven production card identities, three evaluation modes, qualification/authorization/source-pair evidence, descriptive matching policy, and mocked `PostgresTrialLedger` boundary.
- Produces: a real public-CLI synthetic invocation that reserves then decodes, evaluates all 21 plans, reaches at least one `TimedTrade`, and writes a descriptive-only report.

- [ ] **Step 1: Write the failing full public CLI test**

```python
def test_public_cli_runs_candle_only_bundle_through_all_twenty_one_plans(
    tmp_path, monkeypatch
) -> None:
    packet = build_fully_bound_descriptive_packet(tmp_path)
    order: list[str] = []
    monkeypatch.setattr(cli, "PostgresTrialLedger", mocked_ledger_recording(order))
    monkeypatch.setattr(timed_runner, "_decode_prices", decode_recording(order))
    assert main(["run", *packet.argv]) == 0
    report = json.loads(packet.output.read_bytes())
    assert order.index("reserve") < order.index("decode")
    assert len(report["results"]) == 21
    assert any(outcome_has_actual_trade(row) for row in report["results"])
    assert all(row["benchmark_mode"] == "DESCRIPTIVE_CANDLE_PROXY" for row in report["results"])
    assert report["promotion_eligible"] is False
```

Also assert missing qualification, authorization, rights/use evidence, policy mismatch, source-pair mismatch, or mutated modeled schedule fails before `reserve`/decode as appropriate; mutation after reservation must fail closed without a success report.

- [ ] **Step 2: Run public CLI test and record RED**

```powershell
uv run --offline pytest tests/unit/test_timed_cli.py -k "candle_only or descriptive or twenty_one" -q
```

Expected: FAIL because the CLI does not bind or report descriptive mode; save `04-cli-red.log`.

- [ ] **Step 3: Wire mode through the existing CLI and runner**

Parse the closed matching-policy mode before artifact decode, include its hash and availability-model identifier in `ExecutionBinding`, select `assemble_timed_inputs(..., mode=policy.mode)`, and leave `GuardedTimedRunner.run(...)` as the only reservation/evaluation framework. Report only source/policy hashes, raw/model timestamps, refusal/comparable counts, per-trade intervals, exact stock cost basis, `PRE_TAX`, and `promotion_eligible=false`; do not aggregate or filter comparable trades.

- [ ] **Step 4: Run the full focused suite and static checks**

```powershell
uv run --offline pytest tests/unit/test_timing.py tests/unit/test_timed_runner.py tests/unit/test_timed_strategy_management.py tests/unit/test_timed_evaluation.py tests/unit/test_timed_cli.py tests/unit/test_benchmark_policy.py tests/unit/test_synthetic_benchmark_match.py tests/unit/test_synthetic_execution_replay.py tests/unit/test_strategy_consumers.py -q
uv run --offline mypy icarus scripts/run_timed_backtest.py scripts/research/synthetic_execution_replay.py
uv run --offline ruff check icarus scripts/run_timed_backtest.py scripts/research/synthetic_execution_replay.py tests/unit/test_timing.py tests/unit/test_timed_runner.py tests/unit/test_timed_strategy_management.py tests/unit/test_timed_evaluation.py tests/unit/test_timed_cli.py tests/unit/test_synthetic_execution_replay.py
uv run --offline ruff format --check icarus scripts/run_timed_backtest.py scripts/research/synthetic_execution_replay.py tests/unit/test_timing.py tests/unit/test_timed_runner.py tests/unit/test_timed_strategy_management.py tests/unit/test_timed_evaluation.py tests/unit/test_timed_cli.py tests/unit/test_synthetic_execution_replay.py
```

Expected: all PASS; save four separate logs. Do not commit, push, run mutation tests, or update root-owned status/review documents until the root agent explicitly opens those stages.

## Frozen Stopping Point

The build stops when the synthetic public CLI vertical and focused CI checks pass. The resulting lane is descriptive, synthetic, pre-tax, non-aggregate, and promotion-ineligible. Actual source qualification, a bounded real-data window, fresh run authorization, permanent-storage policy, lockbox access, strategy activation, ledger activation, and every broker/live path remain outside this plan.
