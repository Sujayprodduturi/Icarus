# Strategy research — Matt Donlevey's mechanical liquidity / SMC method

> Source: Matt Donlevey, "liquidity" overview video — https://www.youtube.com/watch?v=YUUefUXeZwI
> (transcript read 2026-07-28). This is his *overall philosophy* video; more of his content to mine later.
> Purpose: capture the methodology as the DNA for Icarus strategies. See `PRD.md` §12 (the DSL).

## Core thesis
Trade **with institutional liquidity**. Big players need large pools of *opposing* resting orders
(retail stop-losses) to fill size without slippage. So price hunts those pools — sweeps them — then
moves the intended way. Find where the pools are; trade the reaction.

## The three-layer framework
1. **Market structure → direction.** Higher-highs/higher-lows = bullish; lower-highs/lower-lows =
   bearish. Higher timeframe = trend vs pullback phase; medium timeframe (M15) = the session bias.
2. **Supply/demand zones → where to enter** (points of interest, "POIs").
3. **Liquidity → timing/refinement** of the entry (the edge).

## Key mechanical concepts
- **Liquidity pools** rest behind structural highs (buy-side, i.e. stops of shorts) and lows
  (sell-side, i.e. stops of longs). More significant the swing → bigger the pool.
- **Inducement** — obvious patterns (double bottoms, breakouts) bait retail into placing stops in
  predictable spots, *generating* the pool the institutions want.
- **Liquidity sweep** — price spikes *through* a swing high/low (triggering those stops) then
  reverses. A strong low formed *by sweeping* the liquidity below it = high-quality long location.
- **Sweep zones (past)** — a demand zone created while sweeping a low signals institutional backing.
- **Available-liquidity test (future)** — for a zone to hold there must be liquidity **to the left**
  (a prior swing low) **or built to the right** (a fresh sweep / a low that broke a high). Neither →
  the zone itself is the liquidity → it gets swept (a **trap**).
- **High vs low resistance liquidity** — a pullback that leaves corrective lows *without* a sweep →
  shallow pullback (low resistance); a pullback *with* a strong sweep → deeper pullback (high
  resistance). Use to anticipate pullback depth.

## Entry models
1. **Limit** at the refined zone after a sweep/liquidation.
2. **Trail-in** — after the sweep, trail candles until price tags you.
3. **Confirmation** — wait for structure to shift, then enter the pullback (extreme zone / 0.618 /
   fair-value-gap).

## His meta-rule (repeated throughout)
Make **everything mechanical**: exact definitions for what counts as a sweep, how near inducement
must be to the POI, which timeframes/phases it applies to, and precise invalidation. "Consistent
actions = consistent results." (He sells the exact numbers via his paid community; we must *define
our own* mechanical thresholds and let the validation gate judge them honestly.)

---

## How Icarus uses this

**Reality:** the full method is **intraday** (M5/M15, session liquidity) and needs new DSL primitives
(swing structure, break-of-structure, supply/demand zones, inducement, fair-value-gap,
multi-timeframe). That's a build + an intraday-data dependency — **planned for Phase 2-era** (see
[[icarus-strategy-direction]]).

**Phase-1 (daily data) distillation — the "liquidity-sweep reversal":**
mechanically capture his *core* on daily bars, losing the intraday session nuance but keeping the
structural-sweep idea:
- **Trend filter (structure):** only take longs while the daily structure is up (e.g. higher swing
  highs+lows over a lookback), shorts while down.
- **Sweep trigger:** a bar's low trades *below* a recent swing low (sweeps sell-side liquidity) then
  the bar (or next) *closes back above* that swing low (reclaim) → long. Mirror for shorts.
- **Stop:** just beyond the sweep extreme. **Target:** prior swing high / a fixed R multiple.
- Every threshold (swing lookback, how far the sweep, reclaim window) is an explicit parameter the
  backtester + validation gate evaluate — no discretion.

This runs beside a **plain moving-average-cross baseline** so the Phase-1 scorecard shows the engine
on both a trivial strategy and a Donlevey-flavoured one. The gate will tell us honestly whether
either has an edge *after cost and tax* — it may not, and that's the point.
