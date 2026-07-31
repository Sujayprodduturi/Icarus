# Can the validation machinery ever reach significance?

*Measured 2026-07-31, in response to the LLM council's finding that time-to-first-evidence
(BUILD_MAP risk **M4**) was unstated. Real NSE daily bars, 19 liquid large/mid caps, 2016-01-01 →
2026-07-30 (~10.4 years each).*

**This is a feasibility measurement, not a backtest.** No costs, no fill model, no next-bar
discipline, no walk-forward. It answers exactly one question: *how many trades per year can this
system produce?* — because that determines whether the DSR/PBO/canary apparatus can reach
statistical significance at all.

---

## The result

| Strategy archetype | Signals/symbol/yr | Median hold | **Portfolio trades/yr** (3 slots) | Time to 30 sim trades |
|---|---|---|---|---|
| SMA(20/50) cross, exit on opposite cross | 2.7 | 42 bars | **18** | **20 months** |
| Sweep + reclaim (Donlevey distillation) | 2.4 | 9 bars | **84** | **4.3 months** |
| Cross-sectional momentum, monthly rebalance | — | ~21 bars | **36** (upper bound) | **10 months** |

## The finding that matters

**Signals are never the constraint. Slots are.**

Even a 20-symbol universe generates ~50 signals/year — against 18–84 available slot-turnovers. At
100 or 500 symbols it's 240–1,340 signals/year. The universe size is irrelevant to trade count.

What actually determines trade count is pure arithmetic:

```
portfolio trades/year  =  max_open_positions × 252 / median_holding_days
```

Every term is a config value or a strategy property. **Nothing about this needed a backtester to
discover, and it should have been computed before the validation machinery was designed.**

## Consequences

**1. The MA-cross baseline cannot go to sim forward-run or canary.** At 18 trades/year, task 1.10's
≥30-trade requirement takes 20 months, and the Phase-2 canary (≥10 more) another 7. A verdict
arrives in 2029. It remains valuable as a *backtest-only control* — it exercises the engine on
something trivial, which is its whole purpose — but it must be explicitly barred from the
calendar-consuming stages.

**2. The sim forward-runner must run all candidates in parallel.** Calendar time is shared, not
summed. Running three candidates sequentially costs three times the wall-clock for the same
information. This is a design requirement on task 1.10, not an optimisation.

**3. The Donlevey sweep is the only proposed strategy that clears the bar comfortably.** At 84
trades/year it reaches a sim verdict in ~4 months. That is a point in favour of the operator's
chosen direction — and it is a *structural* argument (short holding period), independent of whether
the strategy has any edge.

**4. `max_open_positions` is tighter than the heat cap requires.** `goal.yaml` sets
`max_open_positions: 3` and `max_portfolio_heat: 0.02` at `per_trade_risk_r: 0.005`. The heat cap
alone permits **4** concurrent positions (2% ÷ 0.5%). Raising 3 → 4 lifts every trade count by 33%
(MA 18→24, sweep 84→112, XS momentum 36→48) **without loosening a single risk limit** — the heat
budget, not the position count, is the real control. Worth an explicit operator decision rather than
leaving 3 as an unexamined default.

## Method

`SMA(20/50)`: long on fast-above-slow cross, exit on the opposite cross. `Sweep + reclaim`: a
confirmed k=10 swing low (marked only from the bar it became *confirmable* — no look-ahead), swept
by a later bar's low, with that bar closing back above it; 1.5×ATR stop, 2R target, 40-bar time
stop, pool valid 30 bars. Cross-sectional momentum estimated analytically at full monthly turnover
(21-bar hold), which is its upper bound.

Sample skews toward large caps, which trend more smoothly than mid/small caps; holding periods on a
wider universe would likely be somewhat shorter, raising trade counts. Treat these as
order-of-magnitude, not precise.

*Script: `$CLAUDE_JOB_DIR/tmp/tradecount2.py` (throwaway; the real version belongs in the
backtester once 1.7 exists).*
