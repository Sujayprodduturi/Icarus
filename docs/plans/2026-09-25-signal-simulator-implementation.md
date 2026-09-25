# Signal-Only Simulator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the synthetic-only Task 3a Step 5 simulator so every emitted entry signal becomes exactly one filled trade observation or an explicit refusal.

**Architecture:** Keep `PortfolioSimulator` and `SignalSimulator` as siblings. Extract only pure panel-to-bar helpers to `simcore.py`, reuse the existing `FillModel`, `CostModel` and exit ladder, and represent outcomes with the already-reviewed Step 4 records. The new result has no portfolio metrics, tax, gate, persistence, or broker access.

**Tech Stack:** Python 3.12, NumPy, Decimal, pytest, Ruff, mypy, uv.

**Spec:** [Task 3a Step 5 contract](2026-09-25-signal-simulator.md), within the [Task 3a master plan](2026-08-22-signal-test.md).

## Global Constraints

- Only synthetic fixtures in this slice; no real panel, lockbox read, trial ledger write, live order path, broker import, or numeric promotion verdict.
- Signal input values are exactly `0.0`, `1.0`, or labelled `NaN`; all other values fail preflight before any event runs.
- `source_indices` are nonnegative, strictly increasing and contiguous; missingness-map keys use these canonical indices, and event timestamps are canonical UTC session timestamps.
- Intent is the configured `signal_test.notional_inr` (₹1,00,000), whole shares sized against `FillModel.marketable_price`; filled deployment must not exceed it.
- Decision bar *t* executes no earlier than *t+1*; resting limits never fill on a mere touch.
- All exit-fragment `benchmark_return` values are `None`; no daily-price approximation for intraday exits, no capital-gains tax in this diagnostic.
- Existing portfolio exit behavior and frozen synthetic characterization remain byte-for-byte equivalent after helper extraction.

## Review Focus

1. `NaN` in an untradable, already-open or final-bar cell must still fail if unlabelled; Task 2's preflight test covers it.
2. Slippage/tick rounding that makes the buy dearer than the bar open must never deploy more than ₹1,00,000; Task 3's price-boundary test covers it.
3. A protective stop on the entry bar must use the original decision timestamp, not the entry timestamp; Task 4's gap-stop test covers it.
4. An unfilled or partial final exit must leave a labelled mark, not an invisible holding; Task 4's residual test covers it.
5. Full-source and sliced views of the same decision must preserve its original canonical index and identical signal ID; applying a uniform source offset preserves holding-session counts, while a sparse axis must fail. Tasks 2 and 4 cover this.

---

### Task 1: Extract remaining pure panel helpers without changing the portfolio simulator

**Files:**
- Modify: `icarus/engine/simcore.py` — own `_ts_at`, `_sim_bar`, `_last_traded_close`.
- Modify: `icarus/engine/portfolio.py` — import those helpers and preserve compatibility exports.
- Test: `tests/unit/test_portfolio_characterization.py`, `tests/unit/test_simcore.py` (new helper tests).

**Interfaces:**
- Consumes: `Panel` and `SimBar` already used by `portfolio.py`.
- Produces: `simcore._ts_at(panel: Panel, t: int) -> datetime`, `simcore._sim_bar(panel: Panel, index: int, t: int, ts: datetime) -> SimBar | None`, `simcore._last_traded_close(panel: Panel, index: int, t: int) -> tuple[Decimal, int]`.

- [ ] **Step 1: Write failing helper-location and behavior tests.** Assert a UTC timestamp, `None` for a missing symbol bar, last finite close plus its local bar index, and that `simcore` exports these functions. A concrete first test:

  ```python
  def test_shared_bar_helper_refuses_missing_symbol_session():
      from tests.unit.test_portfolio_characterization import _panel
      from icarus.engine.simcore import _sim_bar, _ts_at
      panel = _panel()
      panel.bars[0].open[1] = np.nan
      assert _sim_bar(panel, 0, 1, _ts_at(panel, 1)) is None
  ```

- [ ] **Step 2: Run red.** `uv run pytest tests/unit/test_simcore.py -q`; expect an import failure for the unextracted helper, not a fixture or syntax error.
- [ ] **Step 3: Move the three bodies unchanged** into `simcore.py`; import them in `portfolio.py`, retaining old module-level names for existing callers. Do not move `_scaled`, `_committed_cash`, ranking or write-off bookkeeping.
- [ ] **Step 4: Run green and characterization.** `uv run pytest tests/unit/test_simcore.py tests/unit/test_portfolio_characterization.py -q`; verify the recorded synthetic hash/output is unchanged. This is an internal checkpoint; final commit follows independent review.

### Task 2: Preflight and typed diagnostic result

**Files:**
- Modify: `icarus/engine/signaltest.py` — add `SignalMissingReason`, `SignalMissing`, `SignalRunResult`, `SignalSimulator` preflight and a `NO_EXECUTION_BAR` skip reason.
- Test: `tests/unit/test_signal_simulator.py` (new).

**Interfaces:**
- `SignalSimulator(*, notional_inr: Decimal, costs: CostModel, fills: FillModel, stale_after_sessions: int, segment: Segment = Segment.EQUITY_DELIVERY)`.
- `run(strategy: StrategyCandidate, panel: Panel, signals: Mapping[str, Column], stops: Mapping[str, Column], *, source_indices: Sequence[int], missing_reasons: Mapping[str, Mapping[int, SignalMissingReason]] | None = None) -> SignalRunResult`; missing-reason inner keys are canonical source indices.
- `SignalRunResult` is frozen/slotted with `trades: tuple[SignalTrade, ...]`, `skips: tuple[SignalSkipped, ...]`, `missing: tuple[SignalMissing, ...]`, an independently preflight-counted `emitted_signals: int`, `unfilled_exits: int`, and a constructor assertion that emitted count equals trades plus skips with unique/disjoint IDs; it has no portfolio metric fields. `SignalMissing` holds symbol, UTC decision timestamp, canonical decision index, and `WARMUP`/`MISSING_INPUT` reason.

**Test fixture foundation:** Start `tests/unit/test_signal_simulator.py` with this helper, using the already-frozen six-session synthetic panel; import `Decimal`, `numpy as np`, `parse_strategy`, `default_registry`, `CostModel`, `FillModel`, `SignalSimulator`, `_panel`, `_STRATEGY`, `_RISK`, `_COSTS`, and `REALISM` from their existing modules.

```python
def _case():
    panel = _panel()
    strategy = parse_strategy(
        _STRATEGY, registry=default_registry(), max_risk_r=_RISK.per_trade_risk_r
    )
    signals = {symbol: np.zeros(len(panel), dtype=np.float64) for symbol in panel.symbols}
    stops = {symbol: np.full(len(panel), 10.0) for symbol in panel.symbols}
    simulator = SignalSimulator(
        notional_inr=Decimal("100000"), costs=CostModel(_COSTS),
        fills=FillModel(REALISM), stale_after_sessions=20,
    )
    return strategy, panel, signals, stops, simulator
```

- [ ] **Step 1: Write red preflight tests.** For a three-session fixture, test `NaN` without a reason, infinity, `0.5`, reason on finite 0/1, reason for unknown symbol or index, missing/extra symbol columns, wrong length, malformed panel bar/membership shapes or axes, duplicate/descending/sparse source indices, and repeated/non-monotonic dates. Each must raise before a fill model is invoked. Pin a labelled warm-up and missing-input `NaN` as separate diagnostics, including local cell 1 with canonical source index 41.

  ```python
  def test_unlabelled_nan_fails_even_on_untradable_last_bar():
      strategy, panel, signals, stops, simulator = _case()
      signals["AAA"][-1] = np.nan
      panel.tradable[panel.index_of("AAA"), -1] = False
      with pytest.raises(ValueError, match="unlabelled NaN"):
          simulator.run(strategy, panel, signals, stops, source_indices=range(40, 46))
  ```

- [ ] **Step 2: Run red.** `uv run pytest tests/unit/test_signal_simulator.py -q`; expect the missing class/API or missing validation to cause the chosen assertions to fail.
- [ ] **Step 3: Implement only preflight and immutable result types.** Convert each valid labelled `NaN` into one `SignalMissing` with full-source index and UTC decision time. Reject invalid axes and values before creating a book or executing a fill. `run()` may initially return an empty result for all-zero fixtures; do not invent trade handling yet.
- [ ] **Step 4: Run green.** `uv run pytest tests/unit/test_signal_simulator.py -q`; then `uv run mypy icarus tests` and `uv run ruff check icarus tests`. Keep this as an internal checkpoint until final review.

### Task 3: Entry attempts, skips, and simple completed trades

**Files:**
- Modify: `icarus/engine/signaltest.py` — decision loop and one private mutable position accumulator satisfying `simcore._ExitPosition`.
- Test: `tests/unit/test_signal_simulator.py` — synthetic entries and every skip.

**Interfaces:**
- Consumes Task 2 API and Step 4 `SignalId`, `SignalSkipped`, `SignalTrade` records; produces explicit skips and complete single-fill trades, without book-level cash/slot/heat constraints. Task 4 extends this to partial and marked exits.

- [ ] **Step 1: Write red tests** for last-bar `NO_NEXT_BAR`, decision-day `NOT_TRADABLE`, same-symbol `ALREADY_OPEN`, absent execution bar `NO_EXECUTION_BAR`, invalid/nonpositive stop, price above notional, zero-volume/participation `ENTRY_NOT_FILLED`, and valid partial entry. Add more simultaneous symbols than the configured portfolio slot cap, a simple fully filled end-of-data exit for each successful entry, and a higher modelled marketable price proving deployment never exceeds ₹1,00,000.

  ```python
  def test_deployment_uses_filled_price_not_open():
      strategy, panel, signals, stops, simulator = _case()
      signals["BBB"][0] = 1.0  # this fixture stays flat until a full final-bar exit
      result = simulator.run(strategy, panel, signals, stops, source_indices=range(6))
      trade = result.trades[0]
      assert trade.deployed_capital == trade.entry_charges.turnover
      assert trade.deployed_capital <= Decimal("100000")
      assert trade.entry_price > Decimal("100")  # next open is 100
  ```

- [ ] **Step 2: Run red.** `uv run pytest tests/unit/test_signal_simulator.py -q`; inspect the expected assertion failures.
- [ ] **Step 3: Implement minimal date-major entry processing and simple complete exits.** Process exits before decisions; a one-fill `END_OF_DATA` exit must finalize `SignalTrade` so this task's public result assertions can pass. Task 4 then adds the remaining exit cases. Size `int(notional / fills.marketable_price(next_bar.open, side=OrderSide.BUY))`, create `Intent(BUY, MARKETABLE_LIMIT, qty, decision_ts)`, check actual fill and charge only filled shares. Never check risk slots, portfolio cash or heat. Apply one documented skip-precedence order and assert `fill.price * fill.filled_quantity <= notional`.
- [ ] **Step 4: Run green.** Run focused tests, frozen portfolio characterization and Ruff/mypy; keep this as an internal checkpoint until the final independent review and commit.

### Task 4: Exit aggregation, stale marks, and exactly one completed outcome

**Files:**
- Modify: `icarus/engine/signaltest.py` — exit loop and private `SignalTrade` finalization.
- Test: `tests/unit/test_signal_simulator.py` — filled and marked exits with hand-calculated P&L.

**Interfaces:**
- Consumes the private open-position accumulator, `simcore._trail_stop`, `simcore._exit_intent`, `simcore._last_traded_close`, `FillModel.execute`, `CostModel.charges`.
- Produces exactly one `SignalTrade` after all entry shares have been represented by `SignalExitFragment` records; each fragment has `benchmark_return=None`.

- [ ] **Step 1: Write red tests** for stop/target both inside one bar (stop wins), stop on the entry bar, time stop, trailing ratchet matching portfolio order, partial exits and entry charge once, dark bars/stale threshold, unfilled and partial final exits followed by a residual mark, source index offset and same-symbol re-entry after closure. Assert hand-computed turnover, costs, net P&L, recognition versus price-source coordinates, holding sessions, and `benchmark_return is pre_tax_alpha is None`.

  ```python
  def test_unfilled_final_exit_marks_residual():
      strategy, panel, signals, stops, simulator = _case()
      signals["BBB"][0] = 1.0
      panel.bars[panel.index_of("BBB")].volume[-1] = 1.0
      result = simulator.run(strategy, panel, signals, stops, source_indices=range(6))
      trade = result.trades[0]
      assert sum(f.quantity for f in trade.exit_fragments) == trade.filled_quantity
      assert trade.marked_quantity == trade.filled_quantity
      assert trade.exit_fragments[-1].reason is ExitReason.STALE_MARK
  ```

- [ ] **Step 2: Run red.** `uv run pytest tests/unit/test_signal_simulator.py -q`; verify missing exits/aggregation, not a broken fixture, cause the failures.
- [ ] **Step 3: Implement exit processing matching `portfolio.py`.** Increment dark sessions when `_sim_bar` is absent; otherwise update held bars and peak close, ratchet trailing stop, then call the shared exit ladder. Preserve the original decision timestamp inside exit intents. Charge every real exit; keep the residual open after a partial. At stale threshold or final session, separately mark remaining shares at the last traded close with source and recognition coordinates, label it `STALE_MARK`, and charge the assumed exit. Finalize one trade only when the shares reconcile. Do not consult `panel.tradable` for exits while the separate finding remains open.
- [ ] **Step 4: Run green.** Focused tests, frozen portfolio characterization, entire `tests/unit` suite, Ruff format/check and mypy. Keep this as an internal checkpoint until final review.

### Task 5: Structural safety and final review

**Files:**
- Test: `tests/unit/test_signal_simulator.py` — source import and result-surface assertions.
- Modify: `docs/STATE.md`, `docs/README.md`, `docs/plans/2026-08-22-signal-test.md` — only after verification; record Step 5 status and next Step 5b without moving later gates.

**Interfaces:** No new runtime API.

- [ ] **Step 1: Write tests** that reject `signaltest.py` importing `portfolio.py`, broker modules, `metrics.py` or `TaxModel`; `SignalRunResult` must lack `equity`, `sharpe`, `max_drawdown`, `gate_verdict`, and a `__dict__`. Confirm a repeated `run()` does not leak prior book state.
- [ ] **Step 2: Run focused and entire unit suite.** `uv run pytest tests/unit -q`; inspect every failure and warning. Run `uv run ruff format --check icarus tests`, `uv run ruff check icarus tests`, `uv run mypy icarus tests`, `git diff --check`, and the frozen synthetic portfolio characterization. Do not claim a real-data golden replay.
- [ ] **Step 3: Independent review.** First run the repo's ponytail simplification review, then an independent code/spec and safety review; fix accepted findings with new failing tests. Re-run checks after any fix.
- [ ] **Step 4: Update docs and commit.** Say exactly what was built and not built; retain the old invalid backtest warning, unopened lockbox, and Phase-1/no-live status. Stage only task files; preserve user-owned `AGENTS.md`.

## Self-review record

- Spec coverage: input refusal, canonical indices, outcome identity, fill/exit accounting, benchmark unavailability, structural boundary and synthetic-only scope are each assigned above.
- Type consistency: one `SignalSimulator.run()` API is used throughout; Task 2 owns result/missing types, Tasks 3–4 fill it; Task 1 produces pure helpers used by Task 4.
- Review-focus coverage: the five listed corner cases map to explicit tests in Tasks 2–4.
- No later Task 3a step or real-data evaluation is included.
