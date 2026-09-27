# Task 3a Step 5b — Portfolio Discard Ledger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Identify every emitted entry signal the portfolio simulator did not enter, without changing a trade, equity point, charge, risk decision, or existing skip count.

**Architecture:** Add typed, immutable discard observations beside the existing `RunResult.skipped` counters. Give both discarded and accepted entries the existing canonical `SignalId`; carry the records through out-of-sample fold results and the overall backtest result. The portfolio still follows its current decision order. Step 8, not Step 5b, will join these IDs to signal-test outcomes.

**Tech Stack:** Python 3.12, `uv`, dataclasses, `pytest`, Ruff, mypy.

**Spec:** [Task 3a plan](2026-08-22-signal-test.md), especially Δ6, §4 D-g, §5, and §6 Step 5b; [operator decisions](../../OPERATOR.md) D15/D16/D19/D20; [current state](../STATE.md). The operator also explicitly approved observing final-bar and untradable signals on 2026-09-25 while leaving legacy skip counts and portfolio behavior unchanged. This plan is the detailed Step-5b contract; it does not authorize real-data evaluation.

## Global constraints

- The research plane has no broker-write path; Step 5b uses synthetic fixtures only and does not touch the lockbox, trial ledger, order path, or promotion gate.
- Existing trade decisions, ranking/tie behavior, fills, equity, itemized charges, stale marks, and `RunResult.skipped` counts must remain byte-for-byte equivalent in the frozen synthetic characterization.
- Preserve the current skip precedence. A record states the first reason actually reached, not a counterfactual reason or foregone return.
- Use the same `simcore.SignalId` fields as Step 5: strategy name/version, symbol, UTC decision timestamp, and full-source decision index. Neither fold number nor simulator mode belongs in the ID.
- A portfolio entry that fills only partly is still one accepted signal. Its multiple `ClosedTrade` exit fragments must not inflate accepted-signal accounting. Compare the exact set of emitted IDs to accepted IDs plus discard IDs; a matching count alone can conceal one omitted and one invented ID.
- No new full per-signal artifact may be published before the later mandatory trial-ledger barrier. Step 5b carries records in typed results; existing JSON may expose compact counts, not a new unlogged evaluation output.
- Preserve each edited file's line endings. Keep the user-owned untracked `AGENTS.md` untouched.

## Review focus

1. A final-bar `1.0` that is also untradable or already held must be `NO_NEXT_BAR` exactly once; no final-bar entry is attempted (Task 2).
2. A non-final `1.0` on an untradable decision session must be `NOT_TRADABLE`, not silently filtered (Task 2).
3. An absent next execution bar must be `NO_EXECUTION_BAR` in the new ledger but still increment the old `NO_STOP_DISTANCE` count (Tasks 1–2).
4. A ranked candidate refused after an earlier candidate fails cash/fill checks must reflect the actual later slot boundary; observing it must not alter selection or ambiguous-tie counting (Task 2).
5. A fold sliced from full history must retain the full-source index in its ID, including when an upstream development view starts after source index zero; OOS aggregation must exclude overlapping training runs (Task 3).

## File map and interfaces

| File | Responsibility |
|---|---|
| `icarus/engine/portfolio.py` | `PortfolioOmission`, `PortfolioDiscard`, run-level accounting, and observational instrumentation at existing decision points. |
| `icarus/engine/runner.py` | Accept canonical source indices at `run_walk_forward`, pass their matching slices into each run, and carry OOS observations through `FoldResult` and `BacktestResult`. |
| `tests/unit/test_portfolio_discards.py` | Synthetic reason, precedence, identity, and reconciliation witnesses. |
| `tests/unit/test_runner.py` | Fold/OOS propagation and compact JSON count witness, without a real panel or ledger write. |
| `tests/unit/test_portfolio_characterization.py` | Existing frozen money-path regression; do not rewrite its snapshot. |
| `docs/STATE.md`, `docs/README.md`, `docs/plans/2026-08-22-signal-test.md`, current diagrams | Update only after code verification and independent review. |

### Task 1: Typed observations and exact run accounting

**Files:** Modify `icarus/engine/portfolio.py`; create `tests/unit/test_portfolio_discards.py`.

**Interfaces:** Consume `simcore.SignalId` and existing `Skipped`. Produce frozen/slotted `PortfolioDiscard(signal_id, reason)` and `RunResult` observations: `emitted_signals: int`, `accepted_signal_ids: list[SignalId]`, `portfolio_discards: list[PortfolioDiscard]`. `PortfolioOmission` has `NO_NEXT_BAR`, `NOT_TRADABLE`, `NO_EXECUTION_BAR`; `PortfolioDiscard.reason` is `Skipped | PortfolioOmission`. `RunResult.record_discard` increments `skipped` for a legacy `Skipped`, maps `NO_EXECUTION_BAR` to `Skipped.NO_STOP_DISTANCE`, and leaves the other new omissions out of legacy counts.

- [ ] Write constructor and reconciliation tests first. For example, a synthetic result with two emitted signals, one accepted ID and one `NO_NEXT_BAR` record must reconcile; duplicate or overlapping IDs must raise. A `NO_EXECUTION_BAR` record must increment only the historical `NO_STOP_DISTANCE` counter.

```python
assert result.emitted_signals == len(result.accepted_signal_ids) + len(result.portfolio_discards)
assert len(set(result.accepted_signal_ids)) == len(result.accepted_signal_ids)
assert not set(result.accepted_signal_ids).intersection(
    discard.signal_id for discard in result.portfolio_discards
)
assert result.skipped[Skipped.NO_STOP_DISTANCE] == 1
```

- [ ] Run `uv run pytest tests/unit/test_portfolio_discards.py -q` and confirm RED for the missing record/accounting API, not a fixture error.
- [ ] Add the minimal typed records and a run-end accounting assertion. Maintain a run-local set of IDs for every exact `1.0` signal cell and require that set to equal the disjoint union of accepted and discarded IDs. The legacy projection must equal `RunResult.skipped` exactly; unknown reason types, duplicate IDs, an accepted/discarded overlap, an invented ID, or a missing outcome fail closed. Do not infer accepted count from `ClosedTrade`.

```python
class PortfolioOmission(enum.StrEnum):
    NO_NEXT_BAR = "no_next_bar"
    NOT_TRADABLE = "not_tradable"
    NO_EXECUTION_BAR = "no_execution_bar"


@dataclass(frozen=True, slots=True)
class PortfolioDiscard:
    signal_id: SignalId
    reason: Skipped | PortfolioOmission
```

- [ ] Run the focused tests GREEN. Run `uv run pytest tests/unit/test_portfolio_characterization.py -q`; its committed SHA-256 and complete trade/equity/cost payload must remain unchanged.

### Task 2: Observe every existing decision without moving it

**Files:** Modify `icarus/engine/portfolio.py`; extend `tests/unit/test_portfolio_discards.py`.

**Interfaces:** `PortfolioSimulator.run(..., source_indices: Sequence[int] | None = None)` accepts full-source contiguous nonnegative indices; standalone callers default to their local panel coordinates. Runner callers in Task 3 must pass the original indices explicitly. Before membership or final-bar filtering, scan exact `1.0` input cells and add their IDs to a run-local expected-ID set independently of accepted/discard recording. Each ID is then either accepted when `book[symbol]` is created or discarded at the first reached refusal; `emitted_signals` is the size of that input-derived set, never a sum of outcomes.

- [ ] Add RED synthetic tests with literal `(symbol, decision_index, reason)` expectations for all eight existing skip reasons and the three omissions. Exercise both `NO_SLOT` sites (already-full book and capacity exhausted during ranked iteration), the last-bar/untradable precedence, an absent next bar, partial entry fill, and re-entry after a close. Each test must name a realistic wrong branch that would make it fail. Include a mutation witness that suppresses one discard append but leaves its input `1.0` intact; the run-end emitted-ID equality must fail.

```python
assert [
    (d.signal_id.symbol, d.signal_id.decision_index, d.reason.value)
    for d in result.portfolio_discards
] == [
    ("AAA", 45, "not_tradable"),
    ("BBB", 49, "no_next_bar"),
]
assert result.emitted_signals == len(result.accepted_signal_ids) + len(result.portfolio_discards)
```

- [ ] Run the focused file and confirm RED for missing observations while the frozen characterization remains GREEN.
- [ ] Add observational ID construction without changing candidate order, rank sorting, entry sizing, `FillModel` calls, or the position book. On the final session record `NO_NEXT_BAR` for every emitted `1.0`; on earlier sessions record `NOT_TRADABLE` for emitted `1.0` cells excluded by membership. Replace each existing `record_skip` call with a same-site `record_discard` call. Split the absent-execution-bar observation from the invalid-stop observation without changing their common legacy counter. Append an accepted ID only after the existing successful position creation.

```python
source = tuple(range(len(panel))) if source_indices is None else tuple(source_indices)
if len(source) != len(panel) or any(type(i) is not int or i < 0 for i in source):
    raise ValueError("source_indices must match the panel with nonnegative whole indices")
if any(b != a + 1 for a, b in pairwise(source)):
    raise ValueError("source_indices must be contiguous full-source indices")
```

- [ ] Run focused tests GREEN, then the frozen characterization. Verify the old `skipped` dict still matches the projection from the new records for every reason. A separate assertion covers `emitted = accepted + discarded`; it is not a claim that existing legacy counters always summed every emitted signal.

### Task 3: Preserve canonical identity across folds and overall result

**Files:** Modify `icarus/engine/runner.py`; extend synthetic runner tests and `tests/unit/test_portfolio_discards.py`.

**Interfaces:** `run_walk_forward(..., source_indices: Sequence[int] | None = None)` accepts indices for its incoming panel, defaulting to that panel's local axis for current callers. `_run_span` passes the matching `source_indices[start:end]` to the sliced `PortfolioSimulator.run`. A future caller that clips a safe source to the development view must supply the original safe-source coordinates; a panel alone cannot recover them. `FoldResult` carries test-side `emitted_signals`, immutable accepted IDs, and immutable `PortfolioDiscard` records; `BacktestResult` aggregates OOS records and IDs only. Existing JSON may add `accepted_signals`, `emitted_signals`, and reason counts; it must not publish a raw per-signal list before the Step-7 trial-ledger barrier.

- [ ] Add RED tests where the same decision appears once in a full synthetic panel and once in a development slice with nonzero original-source offset. Pass that offset through `run_walk_forward` as well as a direct portfolio run; assert identical `SignalId` and UUID in the portfolio observations and, where the same signal is exercised, in the Step-5 signal simulator. Assert rejected non-contiguous or length-mismatched source indices before any simulation event.

```python
assert sliced_discard.signal_id == full_discard.signal_id
assert sliced_discard.signal_id.uuid == full_discard.signal_id.uuid
assert fold.portfolio_discards == tuple(test_run.portfolio_discards)
assert backtest.oos_portfolio_discards == [
    discard for fold in backtest.folds for discard in fold.portfolio_discards
]
```

- [ ] Add RED propagation tests using synthetic folds and `ledger=None` only for the synthetic fixture. Prove training-window records are not copied into OOS aggregation, each OOS decision is present once, and compact JSON counts agree with the typed records. Assert `FoldResult.as_json()` and `BacktestResult.as_json()` contain no per-signal ID, UUID, decision timestamp, accepted-ID list, or discard-record list; those full observations remain typed/in-memory until the later trial-ledger barrier.

```python
fold_json = fold.as_json()
assert fold_json["portfolio_discard_counts"] == {"no_slot": 2}
assert "portfolio_discards" not in fold_json
assert "accepted_signal_ids" not in fold_json
assert str(fold.portfolio_discards[0].signal_id.uuid) not in str(fold_json)
```

- [ ] Thread `source_indices` from `run_walk_forward` through `_run_span`, populate `FoldResult`, and aggregate into `BacktestResult` without touching metrics, taxation, gate logic, window selection, or logging of results. Step 8 must hand the original safe-source indices alongside any clipped development panel; do not silently restart IDs at zero after clipping.
- [ ] Run focused runner/discard tests GREEN and rerun portfolio characterization.

### Task 4: Safety review, verification, and handoff

**Files:** Documentation files in the file map only after the code passes.

- [ ] Compare `git diff --numstat` against `git diff --ignore-cr-at-eol --numstat` per edited file; any difference is a line-ending rewrite to repair before review.
- [ ] Run `uv run pytest tests/unit -q`, `uv run ruff format --check icarus tests`, `uv run ruff check icarus tests`, and `uv run mypy icarus tests`. Preserve the frozen synthetic snapshot hash `98e9aa17227371b9762c56b93ff04ce93de3f8f4ccba0f10b8109b5ef5d00164`.
- [ ] Run the required simplification review, then independent standards/spec/safety code review. Verify each finding against the code and fix it before claiming completion. A later golden real-data backtest is still unavailable; do not substitute an unlogged real-panel run.
- [ ] Commit reviewed code/tests on `dev`, excluding the unrelated `AGENTS.md`. After the commit, use non-destructive mutation checks for missing/duplicate record paths, legacy reason projection, fold-local-ID regression, and an artificial selection change; restore each mutation safely and reverify. Do not use `git checkout --` to restore an uncommitted file.
- [ ] Update `docs/STATE.md`, the Task-3a build row, documentation map, and the current visual roadmap to show Step 5b built and Step 6a/6b still awaiting their separate statistical design. Commit documentation separately. Summarize what was implemented, what remained unchanged, test evidence, and what is still unavailable.

## Stop conditions

Stop and seek operator direction if the implementation would need to alter which signal is selected, when an order is attempted, how a risk/cash limit is applied, any existing skip total, trade/equity/cost output, the lockbox/trial-ledger boundary, or a promotion decision. Step 5b records observed refusals; it does not estimate what refused trades would have earned.
