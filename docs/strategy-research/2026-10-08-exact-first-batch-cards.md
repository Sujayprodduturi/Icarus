# Exact first-batch strategy cards — 2026-10-08

**Authority and limit.** Operator decision D46 approves exact cards, supported long-only candidate
YAMLs and synthetic behavior checks. It does not authorize market-data access, a market-data
strategy evaluation, registry activation, inference, HFT, broker access or live capital. The cards
below freeze mechanics for independent review; they contain no performance claim.

## Batch identity

The immediate supported set is one plumbing control plus four signal specifications:

| Identity | Role/family | Status |
|---|---|---|
| `baseline_buy_and_hold@2` | plumbing and beta control | existing YAML; byte-for-byte unchanged |
| `donlevey_sweep_reclaim@2` | liquidity sweep/reclaim | existing YAML; byte-for-byte unchanged |
| `xs_momentum_20@2` | short-horizon cross-sectional momentum | existing YAML; byte-for-byte unchanged |
| `xs_momentum_252_21@1` | 12-minus-1 cross-sectional momentum | materialized at `strategies/xs_momentum_252_skip21.yaml` |
| `short_term_reversal_uptrend@1` | short-term reversal within an uptrend | materialized at `strategies/uptrend_pullback_3.yaml` |

The wider approved screen remains **five signal families and six specifications**: Donlevey (one),
cross-sectional momentum (two), Donchian breakout (one), reversal (one), and defensive low
volatility (one). Donchian remains blocked on an honest opposite-channel exit. Low volatility
remains blocked on a scheduled-rebalance consumer and exact turnover/retention/re-entry contract.
No YAML, name or version is reserved for either blocked specification. Quality/value remains a
conditional later family awaiting point-in-time fundamentals, and HFT remains deferred and outside
the Phase-1 daily/M15 execution model.

## On-disk and registry contract

- The YAML spellings are exactly `name`, `version`, `timeframe`, `universe`, `entry`, optional
  `rank_by`, `exit`, and `sizing`. `risk_r` and `weighting` live under `sizing`. `schema_version`
  is internal and must not be added: the parser rejects unknown top-level keys.
- YAML `name` becomes the parsed strategy name and the trial ledger's `strategy_name`. The state
  registry calls the corresponding field `strategy_id`; `(strategy_id, version)` is unique.
- Any byte change to a current file or any change to a proposed mapping requires a new card review
  before evaluation. Every evaluation or re-run after that is a new counted trial. The runner
  reservation must bind the final strategy SHA-256, panel hash, config hash, name, version and
  sorted primitive list before evaluation.
- The three current byte identities, checked 2026-10-08, are:
  - `strategies/baseline_buy_and_hold.yaml` —
    `B1BDED2F21C1817ADCED9D4E789AE79F5E9058E433827276D0D1E434C1FD721E`
  - `strategies/donlevey_sweep_reclaim.yaml` —
    `A39F9D507B16550B1BCF4A4997ABD1BA73643FCF8B52B2AEC4EA036A3BDFB295`
  - `strategies/xs_momentum_20.yaml` —
    `8905D1162D1FEA9D2194E0A39312E2512B726B24DB4B06F5D20FC5533614D725`
- The two materialized card identities, checked against the frozen builder evidence, are:
  - `strategies/xs_momentum_252_skip21.yaml` —
    `814023EC6F40F245F68CDD82E010F56883601FAEED0D24E6DFFE2E4B6643FCEC`
  - `strategies/uptrend_pullback_3.yaml` —
    `3C32817984012706E8C2E9FC1E7C6A10CE13F2FD249EA45EE0C390E7A8EB4880`

## Literal cards

The first three blocks are semantic transcriptions of the existing files. The comments and bytes
in those files remain authoritative; builders must not replace them with these shorter blocks.

### 1. Control — unchanged

```yaml
name: baseline_buy_and_hold
version: 2
timeframe: 1d
universe: nse_liquid
entry:
  above:
    a: {close: {}}
    b: {constant: {value: 0.0}}
rank_by:
  roc: {n: 252}
exit:
  - stop_loss_pct: {pct: 0.5}
sizing:
  risk_r: 0.005
  weighting: equal_weight
```

This is the existing always-positive-price control. It is not a signal-family candidate and must
not be counted as evidence that buy-and-hold has alpha.

### 2. Donlevey sweep/reclaim — unchanged

```yaml
name: donlevey_sweep_reclaim
version: 2
timeframe: 1d
universe: nse_liquid
entry:
  all:
    - sweep_and_reclaim_low: {n: 5, k: 3}
    - above:
        a: {close: {}}
        b: {sma: {n: 200}}
rank_by:
  roc: {n: 20}
exit:
  - stop_loss_atr: {atr_mult: 2.0, atr_period: 14}
  - take_profit_r: {r_multiple: 3.0}
  - time_stop: {bars: 20}
sizing:
  risk_r: 0.005
  weighting: equal_weight
```

### 3. Twenty-session cross-sectional momentum — unchanged

```yaml
name: xs_momentum_20
version: 2
timeframe: 1d
universe: nse_liquid
entry:
  xs_top_n:
    expr: {roc: {n: 20}}
    n: 10
rank_by:
  roc: {n: 20}
exit:
  - stop_loss_atr: {atr_mult: 3.0, atr_period: 14}
  - time_stop: {bars: 20}
sizing:
  risk_r: 0.005
  weighting: equal_weight
```

The omitted `min_symbols` is the registered default of 20. It stays omitted because this file is
frozen; adding the explicit default would change its bytes and create a new trial.

### 4. Twelve-minus-one cross-sectional momentum — materialized exact card

```yaml
name: xs_momentum_252_21
version: 1
timeframe: 1d
universe: nse_liquid
entry:
  xs_top_n:
    expr: {roc_skip: {n: 252, skip: 21}}
    n: 10
    min_symbols: 20
rank_by:
  roc_skip: {n: 252, skip: 21}
exit:
  - stop_loss_atr: {atr_mult: 3.0, atr_period: 14}
  - time_stop: {bars: 63}
sizing:
  risk_r: 0.005
  weighting: equal_weight
```

`roc_skip(252, 21)` is exactly
`(close[t-21] - close[t-252]) / close[t-252] * 100`. It is price-scale-free. Higher values are
preferred both by `xs_top_n` and `rank_by`. The 20-session and 12-minus-1 cards are two
specifications in one family for dependence and effective-trial accounting.

### 5. Short-term reversal within an uptrend — materialized exact card

```yaml
name: short_term_reversal_uptrend
version: 1
timeframe: 1d
universe: nse_liquid
entry:
  all:
    - above:
        a: {close: {}}
        b: {sma: {n: 200}}
    - above:
        a: {down_streak: {}}
        b: {constant: {value: 2.0}}
    - below:
        a: {internal_bar_strength: {}}
        b: {constant: {value: 0.2}}
rank_by:
  down_streak: {}
exit:
  - stop_loss_atr: {atr_mult: 2.0, atr_period: 14}
  - time_stop: {bars: 5}
sizing:
  risk_r: 0.005
  weighting: equal_weight
```

This means, literally: close is strictly above its 200-session simple average; there are **at
least** three consecutive lower closes (`down_streak > 2`); and `(close-low)/(high-low)` is
strictly below 0.2. A zero-range bar produces no usable IBS and therefore no signal. When selection
is required, the longest down streak is preferred. Equal streaks retain the engine's symbol-order
tiebreak and must be reported as an ambiguous selection if the tie crosses the slot cut. No
unwritten percentage decline, liquidity override, take-profit or cooldown is part of this card.

## Selection, sizing, execution and re-entry semantics

These are part of every card because the YAML does not repeat engine-owned rules:

1. **Eligibility.** A symbol must be point-in-time `tradable`, and the shared cross-sectional gate
   admits only a finite input score: `nan`, positive infinity and negative infinity are excluded
   before participant counts and ranks are computed. For `xs_top_n`, a date also needs at least
   `min_symbols=20` eligible names. If non-finite exclusion leaves fewer than 20, the entire date is
   `nan`; a cohort is also unavailable when requested `n` is at least the eligible count. This is a
   bounded guard on inputs to cross-sectional consumers. It does not prove every primitive's
   intermediate arithmetic or every non-cross-sectional/event output is finite, and it does not
   authenticate a market-data source.
2. **“Top 10” is a cohort, not ten holdings.** Cross-sectional ties receive the average rank of the
   places they span. A tie crossing rank 10 can therefore admit more than ten names or exclude the
   whole tied group and admit fewer. This is the current, project-owned primitive behavior; do not
   describe it as exact cardinality. The portfolio then applies `goal.yaml`'s open-position cap
   (currently four), so neither momentum card promises ten simultaneous holdings.
3. **Ordering.** `Panel.build` sorts symbols alphabetically. The portfolio applies `rank_by` only
   when candidates outnumber free slots; it sorts higher scores first and symbols ascending for an
   equal score. When candidates fit in the available slots, it keeps panel/alphabetical order.
   That order can still affect which candidate survives heat or cash limits. Cut ties increment
   `ambiguous_selection_days`; they are not evidence that the ranking resolved selection.
4. **Already-held signals.** A condition can remain true for many dates. A signal for an open symbol
   is counted as `ALREADY_HELD`, not pyramided. Exits run before entries. If a position exits and
   its entry condition is true on that same decision bar, the card allows a new next-bar entry;
   there is no cooldown. This makes continued membership after a time stop a real exit-and-re-entry
   with new costs, rather than silent retention.
5. **Sizing.** `risk_r: 0.005` means equal per-position stop risk. Quantity is whole shares rounded
   down from current equity times `risk_r`, divided by the decision-bar stop distance. The engine
   may only reduce or refuse that quantity through the configured position-value cap, portfolio
   heat, available cash including entry charges, bar participation and whole-share floor.
   `equal_weight` means equal stop-risk treatment; it does not promise equal rupee holdings.
6. **Entry.** A close-bar signal at `t` can enter no earlier than `t+1`. The engine uses a
   marketable LIMIT at the next bar's open with configured adverse slippage, tick rounding and the
   participation cap. There is no YAML field for a different entry basis. No next bar, no execution
   bar, no volume or a failed capacity check is a counted omission/refusal, not a synthetic fill.
7. **Protective exit.** ATR is computed through the decision bar. Initial stop price is the actual
   entry fill minus the declared ATR multiple times ATR(14). The resting stop is live on the entry
   session, triggers when the bar reaches it, and fills at the worse of trigger and open subject to
   the same participation model. A same-bar stop wins over a profit target.
8. **Time exit.** `bars` counts valid printed bars while held, including the entry session. At the
   declared count the time exit is a marketable LIMIT and is checked after the protective stop.
   Missing/dark sessions do not advance the count. End-of-fold liquidation remains engine-owned.
9. **Costs, tax and identity.** Actual fills use the current equity-delivery fee model. Account-level
   annual tax is applied only to the portfolio aggregate; signal metrics remain before tax. F48 is
   open, so current fees are not claimed to be contract-note exact. The run must use one config hash
   and one panel hash for all cards in a comparison. Each attempted card/run/re-run is reserved and
   finalized in the counted trial ledger; a different card version, YAML hash or config is a
   different trial.

## Required synthetic behavior checks for the two materialized YAMLs

The builder must add focused, hand-worked tests that prove all of the following without loading a
real panel or evaluating an actual ledger:

1. Both new YAML blocks parse with `default_registry()`, use only registered words, report the
   exact names/versions/primitives above, and reject an unknown or misspelled field.
2. `roc_skip(252, 21)` equals the stated formula on an ordinary finite-price constructed series,
   uses no bar after `t`, is `nan` before sufficient history, and ranks percentage returns rather
   than rupee changes. An extreme finite-input overflow must reach the shared cross-sectional gate
   as infinity and be excluded there; this does not claim the primitive itself cannot overflow.
3. The long-momentum entry masks non-members, `nan`, positive infinity, negative infinity and fewer
   than 20 finite eligible names; selects the intended unique-score cohort; and pins both cutoff-tie
   outcomes where average rank produces fewer or more than ten signals. Ordinary finite ranking and
   tie outputs must remain byte/value-equivalent to the behavior before the bounded guard.
4. Portfolio selection proves the two ordering paths: descending `rank_by` plus symbol tiebreak
   when candidates exceed free slots, and panel/alphabetical order when they do not. A tie across
   the actual slot cut must increment `ambiguous_selection_days`.
5. Reversal boundaries are exact: equality to SMA(200) fails; a two-bar down streak fails; three
   and longer pass; IBS equal to 0.2 fails; IBS below 0.2 passes; and a zero-range bar cannot signal.
6. A signal fills only on the next bar using the engine's marketable-limit price. Missing next bar,
   zero volume, participation truncation/refusal, whole-share rounding, cash, heat and position-cap
   paths remain counted and cannot be bypassed by either card.
7. The stop distance is exactly the declared multiple of decision-bar ATR(14), a gap through the
   stop fills at the worse open, and a stop can act on the entry session. The 5- and 63-bar time
   exits count the entry bar, lose to the stop on an ambiguous bar, and do not count dark sessions.
8. Repeated true signals while held become `ALREADY_HELD`; an exit-day true signal can re-enter on
   the next bar and pays a new entry/exit cost cycle. The test must cover this explicitly for the
   momentum time stop rather than implying scheduled retention.
9. The three current files' byte hashes remain the values above. The two new final files are hashed
   only after independent card review, and a synthetic reservation proves those hashes and versions
   are what the counted ledger would bind without reading or migrating any actual ledger.
10. Expand the catalogue-demo name guard from the existing three names to these exact five while
    keeping its existing synthetic panel fixture unchanged. The unchanged panel's reversal result is
    expected to be zero because its IBS does not cross the card boundary; that is a valid negative
    wiring case. Retain positive-trade checks for each of the original three cards and require a
    positive trade for the new momentum card on that same unchanged panel. Add a separate,
    explicitly versioned positive pullback fixture that really crosses every reversal boundary. Do
    not alter the catalogue panel to manufacture trades. A synthetic trade or nonzero signal count
    proves wiring only and must never be labelled profit or evidence of edge.

The frozen builder record at
`var/verification/2026-10-08/strategy-cards/build/red-green.md` reports 24 candidate checks passing,
472 affected checks passing in 22.26 seconds, focused Ruff and mypy success, clean diff checking and
the exact five source hashes. These are builder-reported synthetic mechanics results pending the
separate final code review; they do not establish market performance, promotion, general arithmetic
finiteness, fee exactness, or permission to cross D41's real-data stop. F48, the Donchian opposite
exit and the low-volatility rebalance consumer remain open.
