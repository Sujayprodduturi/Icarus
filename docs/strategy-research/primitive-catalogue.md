# Strategy primitive catalogue — the vocabulary the DSL must hold

*Research pass for task 1.4. Compiled 2026-07-31. Companion to
[`donlevey-liquidity-smc.md`](donlevey-liquidity-smc.md).*

---

## 0. What this document is, and why it is organised this way

A DSL is a **vocabulary of primitives**, not a library of strategies. A strategy is a sentence;
a primitive is a word. Get the words right and the Inventor can write sentences neither of us
thought of — which is the entire reason Icarus has an Inventor at all. Get the words wrong and
no amount of search over the grammar will reach the idea we missed.

So this survey reads across the whole strategy universe — retail chart-craft, the CTA/managed-futures
tradition, the academic factor literature, the classic operators, and the India-specific data
nobody outside NSE has — and asks one question of each: **what words does it contribute?**

### 0.1 The five kinds of word

Everything below reduces to five shapes. This typology is the spine of `dsl.py`.

| Kind | Signature | Examples |
|---|---|---|
| **Series** | bars → one number per bar | `rsi(14)`, `atr(14)`, `sma(50)`, `realized_vol(20)` |
| **Level** | bars → one *price* per bar | `swing_high(5)`, `donchian_upper(20)`, `vwap()`, `order_block_top()` |
| **Event** | bars → true/false per bar | `bos_up()`, `swept_and_reclaimed_low(20)`, `cross_above(a, b)` |
| **Context** | external feed → one value per bar | `regime()`, `delivery_pct()`, `fii_index_long_ratio()`, `news_veto()` |
| **Cross-sectional** | *universe* of bars → rank/score per symbol per bar | `xs_rank(roc(126))`, `xs_zscore(...)` |

The first four are per-symbol and the backtester can evaluate them one symbol at a time.
**Cross-sectional is different in kind** — it needs every symbol's bar *t* before it can score any
symbol's bar *t*. That is the one structural demand this research makes on the backtester (1.7),
and it is called out again in §9.

### 0.2 Status flags used throughout

| Flag | Meaning |
|---|---|
| `READY` | Computable now, honestly, on Phase-1 data. Implement in 1.4. |
| `INTRADAY` | Well-defined but needs sub-daily bars. Define in the grammar; **refuse to compute** until Phase 2 data exists. |
| `FEED` | Needs a data feed we can get but have not ingested yet. The feed is named. |
| `NO-DATA` | Needs data we do not have and have no free path to. Catalogued for completeness; not defined in the grammar. |
| `BANNED` | Excluded by a safety invariant or a standing decision. Reason given. |

**`INTRADAY` and `FEED` primitives must fail loudly, never approximate.** A `killzone()` that
quietly returns "always true" on daily bars, or a `news_veto()` that returns "no veto" because the
news agent isn't built, would report an edge that depended on a filter which was not running. That
is the same class of lie the data-quality gate (1.1b) exists to prevent.

### 0.3 What Phase 1 actually has

| Data | Status | Source | Depth |
|---|---|---|---|
| Daily OHLCV, NSE equities | ✅ have | bhavcopy (1.1) | 2011→ |
| Point-in-time universe / index membership | ✅ have | bhavcopy archives (1.1c) | 2011→ |
| Corporate actions, price-return adjusted | ✅ have | (1.1c) | 2011→ |
| **Security-wise delivery qty + %** | 🆕 verified free | `sec_bhavdata_full` (2019→), `MTO_*.DAT` (2011→) | **2011→** |
| **Participant-wise F&O OI + volume** (FII/DII/Pro/Client) | 🆕 verified free | `fao_participant_oi/vol` | **2015→** |
| **F&O ban list** | 🆕 verified free | `fo_secban` | 2015→ |
| Intraday bars | ❌ Phase 2 | Upstox (Jan 2022→) or Zerodha | — |
| Tick / order-book / footprint | ❌ none | — | — |
| Options chain, per-strike OI, IV | ❌ none free historical | — | — |
| Fundamentals (earnings, ROE, margins) | ❌ none free reliable | — | — |
| News / sentiment | ⏳ task 1.2 | RSS + filings + Haiku | — |
| Crypto (funding, basis, perp OI) | ⏳ deferred (D1) | Delta India | — |

All four 🆕 rows were probed live on 2026-07-31 and returned HTTP 200 with parseable content.
Historical depth was verified by sampling one mid-week session per year.

---

## 1. Evidence honesty — read this before the catalogue

The schools below are **not equally supported**, and the DSL should not pretend they are. This
matters because Icarus's validation gate (DSR > 0.95 on effective trial count) is calibrated to
punish data-mined edges — and how much prior belief a strategy deserves changes how suspicious we
should be of a good backtest.

| School | Evidence quality | Honest summary |
|---|---|---|
| **Time-series momentum / trend following** | **Strong.** Peer-reviewed, 58 instruments, multi-decade, out-of-sample since publication. Moskowitz–Ooi–Pedersen (2012). | The single best-documented systematic edge in the survey. Also the most crowded. |
| **Cross-sectional momentum** | **Strong.** Jegadeesh–Titman (1993) and 30 years of replication, including on NSE. | Works in India; liquidity-conditioned versions work better. Prone to violent crashes on regime turns. |
| **Short-horizon mean reversion** | **Moderate.** Well documented, but the edge is small and cost-sensitive — exactly where our CostModel bites. | Plausible on daily NSE data; the ₹15.34 DP charge will eat much of it on small delivery trades. |
| **Volatility targeting / risk parity sizing** | **Strong** as a *sizing* technique; it improves risk-adjusted returns of an existing edge rather than creating one. | Adopt as sizing vocabulary, not as a signal. |
| **Volatility contraction / breakout** (Darvas, Minervini VCP, opening range) | **Weak-to-moderate.** Widely practised, thinly evidenced in peer review. | Mechanically definable, which is what matters. Treat as hypothesis. |
| **SMC / ICT / Wyckoff / Weinstein** | **Weak.** No peer-reviewed evidence base. What exists is retail backtests with no cost model, no multiple-testing correction, and visible survivorship in who publishes. Reported figures (61% win rate, 2.17 profit factor) come from blog posts, not papers. | **Not a reason to skip it** — the operator has chosen this direction, it is mechanically definable, and the gate exists precisely to test unproven ideas honestly. It *is* a reason to treat a good SMC backtest with more suspicion than a good momentum backtest, and to say so on the metric sheet. |

**A note on one tempting number.** A 2026 SSRN paper reports cross-sectional momentum on Nifty-50
constituents at ~133% annualised with Sharpe 2.90 out-of-sample. Sharpe 2.9 on a long-only-ish
equity strategy is roughly triple what the best systematic equity funds sustain. Before believing
it: check the trade count, the cost model, the universe's survivorship, and how many parameter sets
were tried. This is the exact scenario DSR was invented for. **We reproduce it inside our own gate
or we do not cite it.**

---

## 2. Price, trend and moving averages

The oldest vocabulary. Cheap to compute, heavily mined, individually near-worthless — but they are
the connective tissue almost every other school builds on.

| Primitive | Kind | Status | Note |
|---|---|---|---|
| `open/high/low/close/volume` | Series | READY | The raw fields; everything else is a function of these. |
| `typical_price()`, `median_price()`, `ohlc4()` | Series | READY | (H+L+C)/3 etc. Used by VWAP-family and some bands. |
| `sma(n)` | Series | READY | Simple moving average. |
| `ema(n)` | Series | READY | Exponential. Needs a documented seeding rule — SMA-seeded vs first-value-seeded changes early bars. |
| `wma(n)`, `hma(n)` | Series | READY | Weighted / Hull. Hull is EMA-of-EMA arithmetic; low marginal value but trivial. |
| `dema(n)`, `tema(n)` | Series | READY | Low priority. |
| `kama(n)`, `vidya(n)` | Series | READY | Adaptive MAs — period responds to efficiency ratio. Genuinely different behaviour, worth having. |
| `linreg_slope(n)`, `linreg_value(n)`, `r2(n)` | Series | READY | Regression channel maths. `r2` doubles as a trendiness measure. |
| `roc(n)`, `roc_skip(n, skip)`, `momentum_abs(n)` | Series | READY | Percentage change over n bars; the same skipping the most recent `skip` bars (12-1 momentum); and the rupee-denominated form. **Renamed 2026-08-12** — `momentum` meant the rupee version and was being ranked across symbols, which ranks share price (finding F1). `momentum_abs` is `scale_free=False`, so the cross-sectional words now refuse it. |
| `cross_above(a, b)`, `cross_below(a, b)` | Event | READY | The MA-cross primitive. Must be strict (`a[t-1] <= b[t-1] and a[t] > b[t]`) so a flat touch is not a cross. |
| `slope_positive(series, n)` | Event | READY | Sign of `linreg_slope`. |
| `efficiency_ratio(n)` | Series | READY | Kaufman: net move ÷ sum of absolute moves. A clean, cheap trend-vs-chop measure. Underrated. |
| `adx(n)`, `di_plus(n)`, `di_minus(n)` | Series | READY | Wilder's directional movement. ADX is the canonical "is there a trend" filter. |
| `aroon_up(n)`, `aroon_down(n)` | Series | READY | Bars since the n-bar high/low. Structurally similar to Donchian. |
| `supertrend(n, mult)` | Series+Level | READY | ATR-banded trailing trend line. Very widely used in Indian retail algos specifically. |
| `psar(step, max)` | Level | READY | Parabolic SAR. Stateful — must be computed forward-only, which is a good test of our no-look-ahead discipline. |
| `ichimoku_*` (tenkan, kijun, senkou A/B, chikou) | Level | READY | Displaced averages. **The chikou span is displaced *backwards* — a naive implementation is a look-ahead bug.** Worth having precisely because it forces the guard. |

## 3. Volatility, range and risk

| Primitive | Kind | Status | Note |
|---|---|---|---|
| `true_range()` | Series | READY | max(H−L, |H−C₋₁|, |L−C₋₁|). Gap-aware, unlike H−L. |
| `atr(n)` | Series | READY | Wilder-smoothed TR. The unit of risk in half this document. |
| `natr(n)` | Series | READY | ATR ÷ close. Comparable across symbols — required for cross-sectional work. |
| `realized_vol(n)` | Series | READY | Stdev of log returns, annualised. |
| `parkinson_vol(n)`, `garman_klass_vol(n)`, `rogers_satchell_vol(n)`, `yang_zhang_vol(n)` | Series | READY | Range-based volatility estimators. Far more efficient than close-to-close on daily bars — Yang-Zhang handles overnight gaps. **Genuinely useful and almost never in retail toolkits.** |
| `bollinger_upper/mid/lower(n, k)` | Level | READY | SMA ± k·stdev. |
| `bollinger_bandwidth(n, k)`, `percent_b(n, k)` | Series | READY | Bandwidth is the squeeze detector; %B is position within the band. |
| `keltner_upper/lower(n, mult)` | Level | READY | EMA ± mult·ATR. |
| `donchian_upper(n)`, `donchian_lower(n)`, `donchian_mid(n)` | Level | READY | n-bar high/low. **The Turtle primitive.** Must exclude the current bar to avoid trivial self-reference. |
| `squeeze_on(n)` | Event | READY | Bollinger inside Keltner — the classic volatility-contraction trigger. |
| `vol_percentile(n, lookback)` | Series | READY | Where current vol sits in its own history. Regime input. |
| `vol_of_vol(n)` | Series | READY | Stdev of realized vol. |
| `chandelier_stop(n, mult)` | Level | READY | Trailing stop = highest high − mult·ATR. |
| `ulcer_index(n)` | Series | READY | Depth-and-duration drawdown measure. Better than max-DD for a filter. |
| `garch_vol(p, q)` | Series | FEED | Needs a fitted model; deferred to metrics, not a DSL primitive for now. |
| `implied_vol()`, `iv_rank()`, `iv_percentile()` | Context | NO-DATA | No free historical NSE options chain. Catalogued; not defined. |

## 4. Oscillators and mean reversion

| Primitive | Kind | Status | Note |
|---|---|---|---|
| `rsi(n)` | Series | READY | Wilder smoothing, not simple average — the two differ materially. |
| `stoch_k(n, smooth)`, `stoch_d(...)` | Series | READY | |
| `stoch_rsi(n)` | Series | READY | Stochastic applied to RSI. |
| `williams_r(n)` | Series | READY | Rescaled stochastic. |
| `cci(n)` | Series | READY | |
| `macd(fast, slow, signal)`, `macd_hist(...)` | Series | READY | |
| `ppo(fast, slow)` | Series | READY | MACD in percent — cross-symbol comparable. |
| `zscore(series, n)` | Series | READY | **The general mean-reversion atom.** (x − mean) ÷ stdev. Composable with anything. |
| `percentile_rank(series, n)` | Series | READY | Non-parametric alternative to z-score. |
| `distance_from_ma(n)` | Series | READY | (close − sma(n)) ÷ atr(n). ATR-normalised extension. |
| `rsi_divergence(n)` | Event | READY | Price makes a higher high, RSI does not. Mechanically definable via swing points — **must be defined on *confirmed* swings only**, or it look-aheads. |
| `connors_rsi(...)` | Series | READY | Composite short-term mean-reversion oscillator. |
| `internal_bar_strength()` | Series | READY | (C−L)/(H−L). Tiny, cheap, well-documented short-horizon reversion signal. |
| `n_day_down_streak()`, `n_day_up_streak()` | Series | READY | Consecutive-close counter. The basis of several documented reversion systems. |

## 5. Volume, participation and flow

| Primitive | Kind | Status | Note |
|---|---|---|---|
| `volume_sma(n)`, `relative_volume(n)` | Series | READY | Today's volume ÷ average. |
| `dollar_volume(n)` / `traded_value(n)` | Series | READY | **Our liquidity filter.** Rupee turnover, not share count — the only honest cross-symbol liquidity measure. Feeds the capacity model (1.8b). |
| `obv()` | Series | READY | On-balance volume. |
| `ad_line()`, `chaikin_money_flow(n)` | Series | READY | |
| `mfi(n)` | Series | READY | Volume-weighted RSI. |
| `vwap()` | Level | READY *(session-anchored: INTRADAY)* | On daily bars only a rolling/anchored VWAP is honest; true intraday session VWAP needs Phase 2 data. **Two distinct primitives, not one.** |
| `anchored_vwap(anchor_event)` | Level | READY | Anchored to a swing point or event. Daily-computable. |
| `vwap_bands(n, k)` | Level | READY | |
| `volume_profile_poc()`, `value_area_high/low()` | Level | INTRADAY | Needs intra-bar price-volume distribution. Daily bars cannot produce a real profile. |
| `delivery_pct()` | Context | **READY 🆕** | % of volume that settled as delivery. **India-only, free, daily, back to 2011.** High delivery = conviction/positioning; low = intraday churn. No Western equivalent. |
| `delivery_qty()` | Context | **READY 🆕** | Absolute delivered shares. |
| `delivery_pct_zscore(n)` | Context | **READY 🆕** | Unusual delivery vs the symbol's own norm — the actually-tradeable form. |
| `fii_index_fut_long_ratio()` | Context | **READY 🆕** | FII long ÷ (long+short) in index futures. Classic India positioning gauge. Market-wide, not per-symbol. |
| `fii_net_index_fut()`, `dii_net_*()`, `pro_net_*()`, `client_net_*()` | Context | **READY 🆕** | Participant-wise OI/volume. Note **client (retail) positioning is the natural fade** — the one place "smart money vs dumb money" is a measurable number in India rather than a chart pattern. |
| `in_fno_ban()` | Context | **READY 🆕** | Symbol in the F&O ban list. Not a signal — a **hard tradeability veto**; ban-list entry distorts price action and cash-market behaviour. |
| `order_flow_delta()`, `footprint_imbalance()`, `cvd()` | Series | NO-DATA | Needs tick/bid-ask trade classification. Catalogued only. |
| `bid_ask_spread()`, `book_imbalance(n)` | Context | INTRADAY | Needs depth snapshots. Phase 2 for live; never for historical backtest. |

## 6. Market structure and Smart Money Concepts

The full chest, per the operator's instruction. Sources: ICT/SMC canon and the Donlevey method
note. **Resolution honesty is the whole game here** — a large share of this vocabulary is defined
on M5/M15 session behaviour and cannot be computed on daily bars without lying.

### 6.1 Swing structure — the foundation

| Primitive | Kind | Status | Note |
|---|---|---|---|
| `swing_high(k)`, `swing_low(k)` | Level | READY | A bar whose high exceeds the k bars either side. **Confirmation lag is k bars** — a swing is not known until k bars later, and pretending otherwise is the most common look-ahead bug in all of SMC. The primitive must return the swing only from the bar it was *confirmable*. |
| `last_swing_high(k)`, `last_swing_low(k)` | Level | READY | Most recent confirmed swing. |
| `swing_sequence(k)` | Series | READY | Encodes the HH/HL/LH/LL chain. |
| `higher_highs(k, n)`, `higher_lows(k, n)` | Event | READY | n consecutive HH / HL. |
| `lower_highs(k, n)`, `lower_lows(k, n)` | Event | READY | Mirror. |
| `market_structure(k)` | Context | READY | Derived label: `bullish` (HH+HL) / `bearish` (LH+LL) / `ranging`. **The trend filter for every SMC entry.** |
| `structure_range_high/low(k)` | Level | READY | Bounds of the current structural range. |

### 6.2 Structural breaks

| Primitive | Kind | Status | Note |
|---|---|---|---|
| `bos_up(k)`, `bos_down(k)` | Event | READY | Break of Structure — close beyond the last confirmed swing high/low **in the direction of the existing trend** (continuation). Body-close vs wick is a parameter, not an assumption. |
| `choch_up(k)`, `choch_down(k)` | Event | READY | Change of Character — the *first* break **against** the prevailing structure. BOS and CHoCH are the same geometry with opposite trend context; they must not be one primitive. |
| `msb(k)` | Event | READY | Market Structure Break — some traditions use this as a synonym for BOS; we define it as the union and document the difference rather than pick a side silently. |
| `failed_break(k, n)` | Event | READY | Break that reverses within n bars — the "failed auction" idea, shared with Wyckoff's spring. |

### 6.3 Liquidity

| Primitive | Kind | Status | Note |
|---|---|---|---|
| `liquidity_pool_high(k)`, `liquidity_pool_low(k)` | Level | READY | Where stops rest: above swing highs, below swing lows. |
| `equal_highs(k, tol)`, `equal_lows(k, tol)` | Event+Level | READY | Two-or-more swings within `tol` (in ATR) — a denser stop cluster than a single swing. |
| `swept_high(k)`, `swept_low(k)` | Event | READY | Price traded *through* a liquidity pool. |
| `sweep_and_reclaim_low(k, n)` | Event | READY | **The Donlevey core.** Low trades below a prior swing low, then close returns above it within n bars. Mirror: `sweep_and_reclaim_high`. |
| `stop_run_extent(k)` | Series | READY | How far beyond the pool the sweep went, in ATR. Distinguishes a genuine sweep from a slow grind through. |
| `inducement(k)` | Event | INTRADAY | Donlevey's strict sense — a minor pullback high/low engineered to bait entries before the real move. Definable on daily bars only as a degenerate case; **honest form needs intraday.** |
| `liquidity_void(n)` | Level | READY | Range crossed by a single large bar with little trading — daily-computable approximation of an imbalance. |
| `trendline_liquidity(k)` | Event | READY | Stops along a diagonal. Definable but parameter-heavy; low priority. |

### 6.4 Imbalance and zones

| Primitive | Kind | Status | Note |
|---|---|---|---|
| `fvg_up(n)`, `fvg_down(n)` | Level | READY | Fair Value Gap — three-bar pattern where bar 1's high < bar 3's low (bullish). Fully daily-computable. |
| `fvg_filled(n)` | Event | READY | Price has since traded back through the gap. |
| `bpr()` | Level | READY | Balanced Price Range — overlapping opposing FVGs. |
| `order_block_bull(k)`, `order_block_bear(k)` | Level | READY *(daily-scale)* | Last opposing candle before an impulsive move that breaks structure. Definable on daily bars, but the *institutional* interpretation is an M5/M15 claim — we implement the geometry and make no claim about who was buying. |
| `breaker_block(k)` | Level | READY | A failed order block, flipped to the opposite role. |
| `mitigation_block(k)` | Level | READY | Origin of a move that returns to it without taking the prior extreme. |
| `rejection_block(k)` | Level | READY | Wick-based variant. |
| `premium_zone(k)`, `discount_zone(k)`, `equilibrium(k)` | Level | READY | Upper/lower/mid half of the current structural range. Trivial geometry; the *discipline* (only buy in discount) is the value. |
| `ote_zone(k)` | Level | READY | Optimal Trade Entry — the 0.62–0.79 retracement band of the last impulse. |
| `fib_retracement(k, level)` | Level | READY | General retracement of the last confirmed swing leg. |
| `imbalance_ratio(n)` | Series | READY | Body-to-range ratio; cheap proxy for displacement. |
| `displacement(n, mult)` | Event | READY | A bar whose range exceeds mult·ATR *and* closes near its extreme — the "energy" that validates an order block. |

### 6.5 Session and time — the intraday wall

| Primitive | Kind | Status | Note |
|---|---|---|---|
| `killzone(name)` | Context | INTRADAY | London/NY/Asia session windows. Meaningless on daily bars. |
| `session_range_high/low(session)` | Level | INTRADAY | Asian-range liquidity etc. |
| `opening_range_high/low(minutes)` | Level | INTRADAY | ORB — needs the first n minutes. **A well-known Indian intraday strategy family; blocked purely on data.** |
| `judas_swing()` | Event | INTRADAY | Early-session false move. |
| `power_hour()` | Context | INTRADAY | |
| `silver_bullet()` | Event | INTRADAY | Specific hour-window ICT setup. |
| `daily_open()`, `weekly_open()`, `monthly_open()` | Level | READY | Higher-timeframe opens **are** daily-computable and are genuine reference levels. |
| `prev_day_high/low/close()` | Level | READY | PDH/PDL — the most-used liquidity levels in all of ICT, and fully available on daily bars. |
| `prev_week_high/low()`, `prev_month_high/low()` | Level | READY | |
| `htf_bias(timeframe)` | Context | READY | Multi-timeframe structure — daily bars can express weekly/monthly bias by resampling. **Resampling must be causal**: a weekly bar is only usable after the week closes. |

## 7. The classic operators

Discretionary traditions, mined for the mechanical parts. Each contributes vocabulary even where
the method as a whole is not backtestable.

| Source | Contributes | Status |
|---|---|---|
| **Turtles / Richard Dennis** | `donchian_*` (20/55-day breakout), ATR "N" position sizing, 2N stop, 0.5N pyramiding, opposite-breakout exit. The single cleanest fully-specified mechanical system in existence. | READY — full system expressible today |
| **Wyckoff** | `spring()` (= a sweep below support that reclaims — *the same geometry SMC calls a liquidity sweep, forty years earlier*), `upthrust()`, accumulation/distribution range logic, effort-vs-result (volume vs range divergence). | READY |
| **Weinstein stage analysis** | 4-stage classification from a 30-week MA and its slope — `stage()` as a Context primitive. Simple, mechanical, and a genuinely good regime filter for swing equity. | READY |
| **Darvas box** | `darvas_box_top/bottom(n)` — consolidation box, buy the breakout, trail the box. | READY |
| **Minervini SEPA / VCP** | `volatility_contraction(n)` — successively tighter pullbacks; plus the trend template (price > MA150 > MA200, MA200 rising, % off 52w high/low). | READY |
| **O'Neil CANSLIM** | The C, A, N, S, I letters need earnings and institutional-ownership data. The **RS-rating** (relative strength vs universe) is cross-sectional and we *can* do it. | Partly READY, mostly NO-DATA |
| **Livermore** | `pivotal_point()` — breakout of a prior consolidation extreme with volume expansion. Also the "sit tight" logic → time-based exits. | READY |
| **Dow theory** | Confirmation across two series; formalised as HH/HL structure. Already covered by §6.1. | READY |
| **Elliott wave / Gann** | Not mechanically definable without discretion in wave labelling. | **BANNED** — un-backtestable by construction; violates the white-box requirement in spirit. |

## 8. Regime, macro and context

Per the operator decision: these **veto, gate, or shrink — they never originate.**

| Primitive | Kind | Status | Note |
|---|---|---|---|
| `regime()` | Context | FEED (task 1.3) | `trend_up/trend_down/range/high_vol/low_vol` from 20-day rolling return + ATR. |
| `regime_confidence()` | Context | FEED (1.3) | |
| `benchmark_return(n)`, `beta_to(benchmark, n)`, `correlation_to(benchmark, n)` | Series | READY | Nifty is in the bhavcopy. Needed by the alpha gate (1.8b) anyway. |
| `index_above_ma(n)` | Context | READY | Market-wide trend filter — the cheapest, most robust regime switch there is. |
| `breadth_pct_above_ma(n)` | Cross-sectional | READY | % of universe above its own n-day MA. Real breadth, computable from our own universe data. |
| `advance_decline_ratio()` | Cross-sectional | READY | |
| `new_highs_minus_new_lows(n)` | Cross-sectional | READY | |
| `india_vix()` | Context | FEED | NSE publishes it; needs a small ingest addition. The Indian fear gauge. |
| `sentiment_score()` | Context | FEED (1.2) | LLM-derived, range [−1,1]. **Data only. Veto/gate only.** |
| `news_veto()` | Context | FEED (1.2) | Hard block. |
| `earnings_within(n)` | Context | FEED | NSE corporate-announcements calendar. Event blackout — genuinely important for overnight equity risk. |
| `macro_event_within(n)` | Context | FEED (1.2) | RBI policy, budget, US CPI/FOMC. Blackout windows. |
| `is_expiry_week()`, `days_to_expiry()` | Context | READY | Derivable from the NSE calendar we already have. Expiry distorts cash-market behaviour in India specifically. |
| `day_of_week()`, `day_of_month()`, `month()` | Context | READY | Calendar effects. Cheap, and the honest way to *test* them rather than assume them. |

## 9. Cross-sectional — the structural decision

**This is the one place the research changes the architecture rather than just adding words.**

Per-symbol primitives ask "should I buy RELIANCE today?". Cross-sectional primitives ask "of these
100 stocks, which are the best 10 today?" — a question that cannot be answered one symbol at a
time. The backtester must hold the whole universe at bar *t* before it can score any symbol at
bar *t*.

The payoff for that cost: cross-sectional momentum is one of the two best-evidenced edges in the
entire survey, it works on NSE, and a 100-stock liquid universe is exactly the setting it was
designed for. Building the grammar without it would mean rebuilding the backtester later.

| Primitive | Kind | Status | Note |
|---|---|---|---|
| `xs_rank(expr)` | Cross-sectional | READY | Rank every symbol in the universe by any per-symbol expression, at each bar. |
| `xs_percentile(expr)`, `xs_zscore(expr)` | Cross-sectional | READY | Normalised forms — comparable across dates. |
| `xs_top_n(expr, n)`, `xs_bottom_n(expr, n)` | Event | READY | Membership of the top/bottom cohort. |
| `xs_demean(expr)` | Cross-sectional | READY | Subtract the universe mean — makes a signal market-neutral by construction. |
| `xs_sector_neutral(expr)` | Cross-sectional | FEED | Needs a point-in-time sector map. NSE publishes index constituents; sector classification needs a source. |
| `relative_strength(benchmark, n)` | Series | READY | Per-symbol vs index — the per-symbol cousin of RS-rating. |
| `pairs_spread(a, b, n)`, `pairs_zscore(a, b, n)` | Cross-sectional | READY | Stat-arb atom. Cointegration testing belongs in validation, not the DSL. |

**Sizing vocabulary that only makes sense cross-sectionally** — `equal_weight`, `inverse_vol_weight`,
`vol_target(annual_pct)`, `rank_weight`. These belong in the `sizing:` block of the strategy spec,
subordinate always to the Risk agent's caps (invariant #4 — sizing vocabulary may only *reduce*).

## 10. Crypto — catalogued, deferred

Per D1 the crypto leg is deferred and 1.5b owns its cost model. Vocabulary noted so the grammar
does not need reshaping later: `funding_rate()`, `funding_rate_ma(n)`, `perp_basis()`,
`term_basis(days)`, `open_interest()`, `oi_change(n)`, `long_short_ratio()`, `liquidation_volume(n)`,
`exchange_netflow()`. All `FEED`/deferred.

**`BANNED`:** every options primitive (Greeks, theta, IV surface, skew) — invariant #20, no crypto
options until the DSL models expiry. Also **on-chain primitives**, which have no reliable free
historical feed and would be unverifiable in a backtest.

## 11. Explicitly excluded, with reasons

| Excluded | Reason |
|---|---|
| Elliott wave, Gann angles, harmonic patterns | Require discretionary labelling; not mechanically reproducible; fail the white-box requirement. |
| Neural / opaque ML signals | SEBI white-box requirement + invariant: every promoted strategy must be explainable. |
| Anything on the penny/low-priced universe | §29.2 — banned, cannot be backtested honestly. |
| Market-order-dependent setups (e.g. true ORB at open) | Invariant #5 — LIMIT only. A setup that *requires* a market fill is not implementable. |
| Same-bar signal-and-execution setups | Invariant #13 — next-bar execution. Anything needing "buy at the close of the signal bar" must be re-expressed as next-open or a resting limit. |
| Tick / footprint / order-flow | No data, no free path to historical. |
| Fundamental screens (CANSLIM's C/A/N/S/I) | No reliable free historical fundamentals for NSE. |

---

## 12. What this means for task 1.4

**Counts:** ~165 primitives catalogued. **~120 are `READY`** on Phase-1 daily data (including the
four new India feeds). ~20 are `INTRADAY` — defined in the grammar, refuse to compute.
~15 are `FEED` — waiting on tasks 1.2/1.3 or a small ingest addition. ~10 are `NO-DATA`/`BANNED`.

**Three findings that change the plan:**

1. **The India-specific data is the most interesting thing in this document.** `delivery_pct` and
   participant-wise positioning are free, daily, historical to 2011/2015, and have *no Western
   equivalent* — which means they are also not mined by the global quant industry. Everything else
   in this catalogue has been tested by thousands of people with better data than us. These have
   not. If Icarus has an edge anywhere, the prior should favour here. **Recommend a new task 1.1d**
   to ingest them (delivery + participant OI + ban list), reusing the dual-format fetcher pattern
   1.1c already established for bhavcopy.

2. **Cross-sectional support must go in the grammar now** (operator decision) and it obliges the
   backtester to be universe-parallel rather than symbol-serial. That cost lands in 1.7, not 1.4.

3. **Wyckoff's spring and SMC's liquidity sweep are the same geometry.** So are Livermore's pivotal
   point and the Turtle breakout. A well-designed primitive set collapses these into shared words
   with different parameters, rather than reimplementing each tradition's vocabulary separately.
   That is the difference between a coherent library and a pile of indicators.

---

*Sources consulted 2026-07-31: NSE archive endpoints probed directly (see §0.3); Moskowitz, Ooi &
Pedersen, "Time Series Momentum" (JFE 2012); Jegadeesh & Titman (1993) and Indian replications;
the ICT/SMC canon via published glossaries; the original Turtle rules; the Donlevey method note in
this directory. Evidence-quality judgements in §1 are mine and should be re-argued, not inherited.*
