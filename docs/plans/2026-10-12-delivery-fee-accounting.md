# F48 Delivery-Fee Accounting Plan

**Goal:** Charge the fixed equity-delivery DP fee exactly once for each symbol on each IST
calendar day that an executed sell removes shares from the demat account. Never charge that fee
for an unfilled order or a `STALE_MARK`, which is an accounting estimate rather than a sale.

**Why now:** Finding F48 shows that the stateless per-order quote currently adds the fixed fee to
every sell fragment. That can overcharge same-day partial exits and currently charges a stale
residual despite no executed demat sale. This must be corrected before cost-adjusted alpha is
described as contract-note exact.

## Boundaries

- This is synthetic Phase-1 accounting work only. Do not read market data, an actual trial ledger,
  the lockbox, broker state, or an official stream; do not enable inference or any live path.
- Preserve every rate, tax treatment, threshold, amendment, and byte of `goal.yaml`.
- Keep `CostModel.charges()` stateless and backward compatible: a standalone sell-side quote may
  continue to include the full configured DP fee.
- Deduplication exists only in an explicit context created inside one simulator `run()`. Reusing a
  simulator object for another run starts a fresh context.
- Signal-test observations are standalone uniform-notional hypothetical trades, not one combined
  portfolio. The current diagnostic permits only one open position per symbol, so this change does
  not add overlapping same-symbol signals. If a later emitted signal re-enters after the earlier
  one closed, it is a new independent observation and must not inherit the earlier trade's fee;
  fragments belonging to one signal observation may share its one symbol/day fee.
- The portfolio is one actual simulated book. All its executed sells share one run-local
  symbol/IST-day fee context.
- A no-fill and a stale mark neither pay nor reserve the DP fee. A later real fill on that
  symbol/day must still pay it.
- Other proportional sell costs remain on stale marks under the existing pessimistic convention;
  this task removes only the DP fee that requires an executed depository sale.
- Do not commit or push. Parent owns shared status/review documents after review.

## Intended behavior

| event | DP fee |
|---|---:|
| First executed delivery sell for actual-book symbol A on an IST day | one full configured fee |
| Later actual-book partial sell of A on the same IST day | zero |
| Executed sell of symbol B on that day | one full configured fee |
| Executed sell of A after the IST midnight boundary | one full configured fee |
| Same A/day in two signal-test observations that close and later re-enter | one full fee in each observation |
| Unfilled sell intent | zero and does not consume the day key |
| Residual `STALE_MARK` | zero and does not consume the day key |
| A new `run()` with the same inputs | the same fees as the first run; no leaked state |

The day key is derived from the UTC-aware execution timestamp converted through
`icarus.common.calendar.IST`; it is never derived from the UTC date or from the stale price-source
timestamp.

## Small implementation

### `icarus/engine/costmodel.py`

Add one small mutable `DeliveryFeeContext` whose state is a private set of
`(path_scope, symbol, ist_date)` keys. Its executed-sell method first obtains the ordinary
stateless `Charges`, then retains the DP component only for the first eligible equity-delivery key.
It validates an aware timestamp and non-empty symbol before changing state. It records a key only
when the ordinary quote contains a positive DP fee, so intraday/futures/options behavior remains
unchanged.

Add a narrow way to return an ordinary charge quote with `dp_charge=0` for a non-executed stale
estimate. Do not make callers calculate rates or manually subtract rupees. Leave
`charges()`, `round_trip()`, `breakeven_move()`, the stress multiplier, and their default outputs
unchanged.

### `icarus/engine/signaltest.py`

Create the context at the start of each `SignalSimulator.run()`. On a confirmed sell fill, request
charges with the position's `SignalId` as `path_scope`; this keeps partial fragments of that
standalone fixed-notional observation together while preventing a later same-day re-entry from
sharing its fee. Preserve the existing `symbol in book -> ALREADY_OPEN` rule; overlapping signals
remain unsupported and are not part of this fee change. Call the stale estimate path without
touching the execution context and assert its DP component is zero.

### `icarus/engine/portfolio.py`

Create one context at the start of each `PortfolioSimulator.run()`. Route only confirmed sell fills
through it with one constant actual-book scope, so same-symbol partial/re-entry sells aggregate by
IST day across the book. Keep unfilled exits before the fee call. Route `_write_off()` through the
non-executed estimate path so `STALE_MARK` has zero DP and cannot reserve a key.

No fill-model, tax-model, strategy, metric, ledger, schema, YAML, or external-data code changes.

## TDD sequence

1. **Cost contract red.** In `tests/unit/test_costmodel.py`, add focused tests for same-symbol/day
   deduplication, separate symbols, the 18:29/18:30 UTC IST-midnight boundary, separate standalone
   signal scopes, fresh-context reset, unfilled/stale non-consumption, and preservation of the existing
   stateless full-fee quote and stress multiplier. Run the module and record the expected missing
   context/API failures before implementation.
2. **Cost contract green.** Implement only the context and no-DP estimate seam; rerun the cost
   module. Reject naive datetimes rather than silently choosing a calendar day.
3. **Signal integration red/green.** In `tests/unit/test_signal_simulator.py` and only where a
   typed outcome invariant belongs in `tests/unit/test_signaltest.py`, prove same-day partials pay
   once, two sequential same-symbol observations that close then re-enter each pay once, the
   existing overlapping-signal refusal remains unchanged, no-fill followed by a real fill pays
   once, partial real fill plus stale residual pays only the executed fee, a pure stale result pays
   zero DP, and repeated runs do not leak context. First witness the old overcharge/stale failures,
   then make the minimal call-site change.
4. **Portfolio integration red/green.** Add synthetic intraday timestamps to
   `tests/unit/test_portfolio_exits.py` or `test_portfolio_dark.py` to prove actual-book same-day
   partials deduplicate, symbols do not, the IST day boundary resets the fee, no-fill/stale paths
   do not consume it, and repeated `run()` calls reset it. Witness failure before the portfolio
   call-site change.
5. **Golden accounting.** Run `tests/unit/test_portfolio_characterization.py` before and after the
   fix. If `tests/golden/portfolio_characterization.json` changes, inspect and update only the
   intended DP/cost/P&L/equity fields. Record the exact old/new values; never regenerate or bless a
   broad snapshot blindly. If it does not exercise F48, record that fact and rely on the explicit
   synthetic integration cases.

Each new behavior must be seen failing for the intended reason before its production change, then
seen passing. Tests assert itemised `dp_charge` as well as total cost/P&L so a compensating error
cannot hide the bug.

## Verification and evidence

Use `./.venv/Scripts/python.exe` and an explicit owned temp/cache base under
`var/verification/2026-10-12/fees/build`; do not use an implicit shared temp location.

Run once after green:

```powershell
./.venv/Scripts/python.exe -m pytest tests/unit/test_costmodel.py tests/unit/test_signaltest.py tests/unit/test_signal_simulator.py tests/unit/test_portfolio_exits.py tests/unit/test_portfolio_dark.py tests/unit/test_portfolio_characterization.py -q
./.venv/Scripts/python.exe -m pytest tests/unit/test_runner.py tests/unit/test_metrics.py tests/unit/test_metric_sheet.py tests/unit/test_signalmetrics.py tests/unit/test_strategy_breadth_candidates.py -q
./.venv/Scripts/python.exe -m mypy icarus/engine/costmodel.py icarus/engine/signaltest.py icarus/engine/portfolio.py tests/unit/test_costmodel.py tests/unit/test_signaltest.py tests/unit/test_signal_simulator.py tests/unit/test_portfolio_exits.py tests/unit/test_portfolio_dark.py tests/unit/test_portfolio_characterization.py
./.venv/Scripts/python.exe -m ruff check icarus/engine/costmodel.py icarus/engine/signaltest.py icarus/engine/portfolio.py tests/unit/test_costmodel.py tests/unit/test_signaltest.py tests/unit/test_signal_simulator.py tests/unit/test_portfolio_exits.py tests/unit/test_portfolio_dark.py tests/unit/test_portfolio_characterization.py
./.venv/Scripts/python.exe -m ruff format --check icarus/engine/costmodel.py icarus/engine/signaltest.py icarus/engine/portfolio.py tests/unit/test_costmodel.py tests/unit/test_signaltest.py tests/unit/test_signal_simulator.py tests/unit/test_portfolio_exits.py tests/unit/test_portfolio_dark.py tests/unit/test_portfolio_characterization.py
git diff --check
```

Do not repeat a heavy full suite in this bounded child build. Preserve command output, before/after
SHA-256 hashes for owned runtime/test/golden files, the red/green evidence, and any exact golden
delta under `var/verification/2026-10-12/fees/build/`. The final builder report is at most 15 lines
and states commands, counts, hashes, intentional deltas, and any unrun broad check without
overclaiming.

## Acceptance

- Exactly one configured/stressed DP fee exists per eligible execution key described above.
- No fill and every `STALE_MARK` have `dp_charge == 0` and cannot suppress a later real fee.
- Counterfactual signal paths remain independent; the actual portfolio book aggregates globally
  only within one run.
- Existing stateless quotes, rates, tax values, thresholds, and YAML bytes are unchanged.
- Focused accounting, affected regressions, golden characterization, strict typing, lint, format,
  and diff checks have fresh passing evidence, or any failure is reported by exact test/check name.
- No claim is made about actual contract notes, strategy performance, F48 closure beyond these
  simulator paths, real-data readiness, or permission to proceed to the next feature.
