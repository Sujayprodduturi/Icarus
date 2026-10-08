# Strategy breadth screen before any real-market evaluation

**Status:** research and test proposal only  
**Evidence checked through:** 2026-10-08  
**Authority created:** none. This document does not authorize a real-data run, lockbox access, a catalogue/YAML change, an inference claim, or any broker/live path.

**Independent review:** [tracked review evidence](../reviews/2026-10-08-strategy-breadth-review.md) gives a scoped GO for literature screening and rule-card planning, and a NO-GO for treating all six specifications as immediately executable.

## Recommendation

Do not treat the three present YAML files as the best strategies. They are one plumbing control and two invented, mechanically testable hypotheses. The current artificial-price work can show that signals, fills, exits, accounting and statistical code behave as specified; it cannot show that any strategy has good market performance.

Use a small initial breadth screen of **five genuinely different signal families**, with the buy-and-hold file kept outside that count as a control:

1. liquidity sweep and reclaim — the present Donlevey daily distillation;
2. cross-sectional momentum — the present 20-session rule and one longer-horizon 12-minus-1 variant, counted as **one family**, not two independent discoveries;
3. time-series trend/breakout — one Donchian-style long breakout specification, not a collection of moving-average, channel and Supertrend variants presented as independent evidence;
4. short-term reversal inside a primary uptrend — one deliberately low-turnover pullback specification, with costs and liquidity treated as possible killers;
5. defensive low volatility — one long-only selection rule, explicitly separated from leveraged long-short “betting against beta.”

That is six candidate specifications across five hypotheses because momentum gets two horizons. It is a **planning screen, not an executable batch**: the faithful breakout exit and scheduled low-volatility rebalance are currently blocked on missing consumers/contracts described below. The screen is broad enough to test different economic stories and small enough to pre-register and audit. There is no “two winners” target. Zero passing strategies is a valid result, and no frozen acceptance gate may be lowered to manufacture a winner.

Quality and value belong in the catalogue as a **conditional next family**, but not in the first executable batch until Icarus has point-in-time fundamental statements and their public-availability dates. Classic pairs/statistical arbitrage and high-frequency market making are useful boundary cases, but they are not honest long-only daily/M15 candidates and should be deferred rather than represented by a toy backtest.

## Repository boundaries applied to this screen

| Boundary | Consequence for strategy research |
|---|---|
| Long-only NSE cash equity delivery for the current build | A paper's short leg, leverage or futures implementation is not silently converted into evidence for a long-only candidate. Short selling reopens only after the long-only system works end to end. |
| Liquid, non-surveillance large/mid-cap point-in-time universe; low-priced/penny universe banned | Every cross-sectional rule uses the dated eligible universe. A result from today's survivor list would be inadmissible. |
| Daily development/walk-forward history through 2022; separately pinned M15 history when the approved source exists; lockbox starts 2023-01-01 | Daily and M15 candidates never borrow each other's sample length. The lockbox cannot help choose or tune this catalogue. |
| Portfolio evidence at ₹10,00,000 edge capital and ₹1,00,000 seed capital; the seed row controls the stop gate | A strategy that works only when flat costs are diluted is not promoted at seed. Signal diagnostics remain a separate, non-promoting view. |
| Next-bar, LIMIT-only, strict-through/no-fill execution with current costs and tax | Published close-to-close returns are research motivation, not an executable Icarus result. |
| Phase 1 has no live order path; the PRD expressly excludes high-frequency trading | Literature review may record HFT ideas and prerequisites, but this screen cannot advance the HFT stage or emulate it on bars. |

## What the current three files establish

| Current file | Honest role | What is not established |
|---|---|---|
| `baseline_buy_and_hold.yaml` | Plumbing and beta control. It enters any tradable positive-priced name and ranks by 252-session return. | It is not a strategy discovery and must stay outside the breadth count. |
| `donlevey_sweep_reclaim.yaml` | A precise daily version of “sweep a prior low, reclaim it, trade with the long trend.” | The institutional-liquidity story and profitability are unproved. Daily geometry is a lossy stand-in for the operator's intended M5/M15 method. |
| `xs_momentum_20.yaml` | A 20-session cross-sectional relative-strength hypothesis and a test of point-in-time panel ranking. | Its artificial-price trades are mechanics evidence only. They are not evidence of an NSE edge. |

The repository already has useful price-only primitives: `roc_skip`, `xs_top_n`, `realized_vol`, `xs_bottom_n`, `donchian_breakout_up`, `internal_bar_strength`, `down_streak`, `above`, `sma`, ATR stops and time stops. It also refuses several capabilities honestly: inverse-volatility weighting and volatility targeting have no consumer; event-driven exit signals are not in the exit vocabulary; pairs primitives are deliberately absent without pair selection; point-in-time sector mapping, delivery context and several intraday/order-book words cannot currently be evaluated.

## Evidence screen and its limits

The table separates evidence for a repeatable market pattern from evidence that a named proprietary firm earned audited profits. None of the sources below supplies an audited private-firm track record that can be carried into Icarus.

| Family | Source-checked evidence | Evidence quality and portability limit |
|---|---|---|
| Cross-sectional momentum | Jegadeesh and Titman report that buying past winners and selling past losers produced positive returns over 3–12 month holding periods in their sample. AQR's *Fact, Fiction, and Momentum Investing* surveys broader evidence. NSE Indices currently defines Indian momentum indices using six- and twelve-month returns adjusted for volatility. [Journal of Finance article](https://onlinelibrary.wiley.com/doi/pdf/10.1111/j.1540-6261.1993.tb04702.x); [AQR article](https://www.aqr.com/-/media/AQR/Documents/Journal-Articles/JPM-Fact-Fiction-and-Momentum-Investing.pdf?sc_lang=en); [Nifty200 Momentum 30 methodology page](https://www.niftyindices.com/indices/equity/strategy-indices/nifty200-momentum-30) | Peer-reviewed paper plus firm-authored survey and official index methodology. The classic result is long-short; the Icarus long-only adaptation is a new hypothesis. The AQR paper is research, not audited AQR product performance. The NSE page proves a published Indian ruleset exists, not that Icarus can reproduce its historical returns or execution. |
| Time-series trend/breakout | Hurst, Ooi and Pedersen construct a time-series momentum history back to 1880 across 67 markets; their basic construction is long positive trends and short negative trends. [A Century of Evidence on Trend-Following Investing](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/AQR-JPM-Fall-2017.pdf) | Published firm research with a very long external sample, but mostly futures and a bidirectional construction. It supports testing a family; it does not prove a long-only NSE cash-equity channel breakout or disclose proprietary firm P&L. |
| Short-term reversal / trend pullback | Frazzini, Israel and Moskowitz use almost one trillion dollars of anonymized live institutional trades from 19 developed equity markets and find short-term reversal was the style most constrained by trading costs. Other published work finds reversal can survive particular cost models. [Trading Costs of Asset Pricing Anomalies](https://pages.stern.nyu.edu/~afrazzin/pdf/Trading%20Cost%20of%20Asset%20Pricing%20Anomalies%20-%20Frazzini%2C%20Israel%20and%20Moskowitz.pdf); [Another Look at Trading Costs and Short-Term Reversal Profits](https://doi.org/10.1016/j.jbankfin.2011.07.015) | Strong warning against a universal conclusion. The first study contains real trade-cost observations, but applies them to anomaly portfolios; it is not an audited return series and does not model current Indian retail delivery charges. Reversal is cost-fragile, not universally banned. |
| Defensive low volatility | Baker, Bradley and Wurgler document low-beta/low-volatility underperformance of high-risk stocks and offer a delegated-benchmark explanation. NSE Indices publishes a Nifty100 Low Volatility 30 methodology based on the prior year's daily-return volatility. [Paper](https://pages.stern.nyu.edu/~jwurgler/papers/wurgler_bradley_baker.pdf); [NSE Indices methodology](https://www.niftyindices.com/Methodology/Method_Nifty100_Low_Volatility_30.pdf) | Academic/industry paper plus official Indian index rules. This supports a long-only defensive screen. It does not prove alpha after Icarus costs and tax. The official index uses inverse-volatility weights; Icarus currently implements equal risk only, so an equal-risk adaptation must be labelled as a different rule. |
| Quality/value, conditional | *Quality Minus Junk* defines quality through profitability, growth, safety and payout in a long-short global factor. NSE Indices publishes Indian quality and value definitions using ROE, leverage, EPS stability, earnings/price, book/price, sales/price and dividend yield. [Quality Minus Junk](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2312432); [Nifty200 Quality 30](https://www.niftyindices.com/Methodology/Method_NIFTY200_Quality30.pdf); [Nifty500 Value 50](https://niftyindices.com/indices/equity/strategy-indices/nifty500-value50) | Working paper/firm-affiliated research plus official index methodology. Current constituent lists or restated fundamentals cannot be projected backwards. A test needs point-in-time statements, filing timestamps, delisted firms and a fixed lag rule. Until then this family is blocked, not approximated. |
| Pairs/statistical arbitrage, deferred | Gatev, Goetzmann and Rouwenhorst test self-financing long-short pairs chosen by normalized-price distance and note that some profits may be microstructure-related. [NBER working paper 7032](https://www.nber.org/papers/w7032) | Serious classic evidence for the actual long-short object. Removing the short leg changes that object. Current Icarus is long-only and deliberately lacks honest pair-selection/cointegration plumbing, so this is not an initial-screen family. |
| Betting against beta, not relabelled as low-vol | Frazzini and Pedersen's BAB factor is long a **leveraged** low-beta portfolio and short high-beta assets. [NBER working paper 16601](https://www.nber.org/papers/w16601) | The paper supports BAB, not an unlevered long-only low-vol portfolio. Icarus may test defensive low-volatility, but must not cite BAB as evidence that its adaptation is the same trade. |
| HFT market making/order flow, deferred | SEBI defines tick-by-tick data as order-book additions, modifications, cancellations and trades, and requires exchange latency reporting. NSE offers co-location, order connectivity and latency reporting. Queue-position research shows that position in a price-time queue affects fill value and adverse-selection exposure. [SEBI 2018 circular](https://www.sebi.gov.in/sebi_data/attachdocs/apr-2018/1523271816354.pdf); [NSE co-location facility](https://www.nseindia.com/static/trade/platform-services-co-location-facility); [Moallemi and Yuan queue-position paper](https://business.columbia.edu/sites/default/files-efs/pubfiles/25461/queue-value-2016.pdf) | Primary regulatory/exchange material plus an academic model. Icarus has daily/M15 replay, no tick/order-event history, no queue reconstruction and a pessimistic bar-fill model. A toy “market maker” on bars would fabricate fills, spread capture and latency. The PRD also explicitly excludes high-frequency trading. |

## Proposed first-batch rule cards

These are **design candidates**, not YAML and not permission to evaluate. Every numeric parameter proposed below is a **project-owned choice requiring exact rule-card review**; the cited literature motivates a family but does not prove that Icarus's particular lookback, cohort, stop or holding period is superior. Before a run, each card must be converted into one exact, immutable rule document: universe, entry basis, ranked eligibility and tie handling, sizing and position rules, re-entry, exit, protective stop, holding convention, evaluation dates, benchmark, capital rows and data dependencies. Any change after seeing a result is a new counted trial.

| Family and variant budget | Proposed mechanical question | Current path | Blocker or implementation note |
|---|---|---|---|
| Liquidity sweep/reclaim — **1 existing variant** | Does the already-frozen five-bar swing / three-bar reclaim rule, only above the 200-session average, have after-cost value? | Existing daily OHLCV and primitives. | Existing exact rule stays unchanged. M15 is a later, separately pinned variant and cannot inherit daily results. |
| Cross-sectional momentum — **2 total variants** | Keep the existing 20-session candidate. Add one longer-horizon candidate: top ten by 12-minus-1 return (`roc_skip(252, 21)`), one position per symbol, 63-session time stop, three-ATR protective stop. | Daily PIT universe; `roc_skip`, `xs_top_n`, `rank_by`, ATR stop and time stop exist. | Both horizons belong to one family for breadth and dependence reporting. The proposed long-only rule is an Icarus adaptation, not a verbatim replication of a long-short paper or the NSE factor index. |
| Time-series breakout — **1 variant** | Test one 55-session Donchian upside breakout with the classic separate 20-session downside channel exit and ATR protection. | Entry primitive and ATR protection exist. | The honest opposite-channel exit is not expressible in the current exit vocabulary. Close that small capability gap before evaluation; do not substitute an arbitrary time stop and call it the classic rule. |
| Short-term reversal in an uptrend — **1 variant** | Require close above the 200-session average, a three-session down streak and internal-bar strength below 0.2; protect at two ATR and exit after five sessions. | Price-only daily primitives exist. | This is a pre-registration proposal rather than a literature-replication claim. Freeze it once, apply the liquidity/capacity screen, and expect turnover and delivery charges to be decisive. No parameter sweep in the first batch. |
| Defensive low volatility — **1 variant, currently BLOCKED** | Proposed card: select the 30 lowest one-year realized-volatility names from an eligible liquid large/mid-cap universe and rebalance every 63 sessions, with a protective stop required by Icarus. | PIT universe, `realized_vol` and `xs_bottom_n` exist, but this is only partial support. | A scheduled-rebalance consumer does not exist. Build and prove that consumer, then review and freeze exact turnover, incumbent retention, exit and re-entry semantics before evaluation. A card claiming 30 names must refuse when fewer than 30 are eligible rather than silently shrink the cohort; the final cohort/minimum policy is still a card-review choice, not adopted here. Equal-risk Icarus sizing differs from the NSE index's inverse-vol weighting and must be named as an adaptation. Do not enable the currently refused weighting declaration without an implemented consumer. |

This initial batch intentionally excludes three tempting expansions:

- Do not multiply breakout, moving-average, Supertrend and regression-channel settings and count them as independent strategy families. If later admitted, they share one trend-family variant budget and their dependence is reported.
- Do not add a quality/value proxy made from current constituents or current fundamentals. That would violate point-in-time and survivorship requirements.
- Do not add RL, neural-network, options, HFT, order-flow or market-making variants. They require different data, execution machinery, explainability or product scope and do not answer the current breadth question.

## Evaluation protocol after the current real-data stop is separately lifted

1. **Freeze before looking.** Give every candidate a dated rule card and content hash. State the family-level variant budget. A re-tune, rerun, changed universe, altered date, changed exit or implementation repair that can affect results is a new trial.
2. **Count all search.** Record every human-authored and machine-authored evaluation in the same trial ledger, including failures and repeats. Signal-test runs influence selection and therefore increase the effective trial count even though they do not carry portfolio Sharpe.
3. **Use one comparable truth set.** Run the same point-in-time eligible universe, corporate-action convention, daily folds, seam rules and next-bar execution for all daily candidates. Compare over exact matched dates. M15 candidates use their separately pinned window and daily membership authority; they do not borrow the daily sample length.
4. **Use the same pessimistic execution.** A limit touch is not a fill. Apply strict-through/no-fill logic, queue pessimism where the data supports it, and the same participation and liquidity constraints. A family is not allowed a friendlier fill model because its source paper used closes.
5. **Report two different questions.** First run the non-promoting signal diagnostic under its existing contract. Then run the portfolio test with both the ₹10,00,000 edge row and ₹1,00,000 seed row. Show gross, costs, tax and net separately. Only the matched portfolio result can approach the promotion gate.
6. **Match benchmarks to the claim.** All equity candidates need Nifty-relative, after-cost-and-tax alpha on the same timestamps. Low-vol also needs beta and realized-risk context; momentum and trend need turnover and crash/regime concentration; reversal needs cost drag and capacity. These are diagnostics in addition to, not replacements for, the frozen gate.
7. **Use walk-forward evidence and preserve the lockbox.** Development and walk-forward work remains before 2023 under the pinned split. The 2023-onward lockbox is consumed exactly once for the final go/no-go, never for choosing among these cards.
8. **Correct for catalogue search.** Use the effective trial count in deflated Sharpe and a frozen, source-eligible PBO/CSCV method only where its assumptions are met. Five families do not create five independent observations, and a larger catalogue does not solve adaptive overfitting.
9. **Allow refusal.** Missing point-in-time inputs, an unavailable matched benchmark, insufficient independent blocks, or unresolved charge/tax accounting produces an unavailable/refused result, not a guessed metric.

## Proposed acceptance criteria for the breadth milestone

The breadth milestone should pass when:

- the control plus five distinct families above have immutable rule cards, provenance and family-level variant budgets;
- every executable card can be represented without an ignored DSL field, unavailable feed or unfaithful substitute;
- all candidates share the same eligible data, execution, cost/tax and matched-comparison contracts;
- blocked families remain visibly blocked with a named reopening condition;
- the ledger can count every evaluation and the validation report can show family dependence and the effective trial count; and
- no real-data result, lockbox observation or acceptance threshold was used to choose these rules.

It should **not** require a fixed number of strategies to pass. Later promotion still requires the existing frozen numeric gate, positive after-cost-and-tax alpha versus the matched benchmark, and all safety checks. If every family fails, the correct result is “none promoted”; the next decision is whether to improve the input data or test a genuinely different pre-registered family, not to lower the bar.

## Source-quality note

The cited papers establish historical results for their own samples and constructions. Firm-affiliated authorship is disclosed where applicable, and the sources do not provide audited private-fund performance. NSE/Nifty documents are authoritative for exchange facilities or index rules, but index methodology and backfilled index history are not live executable fund returns. No paper win rate, Sharpe ratio or proprietary-firm reputation is imported as an Icarus expectation. Icarus performance remains unknown until a separately authorized, source-eligible, trial-counted real-data evaluation is completed.
