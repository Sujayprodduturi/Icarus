# Strategy breadth proposal review — 2026-10-08

This tracked record consolidates the read-only review of
[`2026-10-08-strategy-breadth-screen.md`](../strategy-research/2026-10-08-strategy-breadth-screen.md).
No strategy, market data, lockbox, broker path or actual trial ledger was evaluated.

Copied source record:

- `var/verification/2026-10-08/strategy-breadth/review/screen-review.md` — SHA-256 `7A8CA287976754C8F36F8ABB1749AA6B1ADD046F29FA6BA8022D5B87E105FCB9`

## Read-only review — scoped GO for research and rule-card planning

Verdict: SCOPED GO for literature screen/rule-card planning only; NO-GO for treating all six specifications as an executable first batch.

P2 screen.md:69: Mark scheduled 63-session rebalance explicitly BLOCKED on an implemented consumer and frozen turnover/re-entry semantics; freezing its rule alone does not make the current engine execute it.

P2 screen.md:67: Opposite Donchian exit is correctly declared unavailable; retain this block until a separate DSL/engine proposal and synthetic parity tests, not an arbitrary time-stop substitute (dsl.py:741-755).

P2 screen.md:59-69: Exact cards still need entry basis, ranked eligibility/ties, sizing/position/re-entry/stop semantics and data availability pinned; this screen is not implementation-ready or a real-data approval.

screen.md:11-19,73,86: Five economic hypotheses/six specs is an honest breadth budget, not five independent discoveries; momentum variants and shared trend exposure remain correlated and must be reported.

screen.md:5,28-33,75,77: Long-only Phase1, no HFT, no lockbox/broker/live and separately lifted real-data stop remain explicit; no scope escape found.

screen.md:46-57,103: No paper win rate, proprietary-firm performance or synthetic result is represented as Icarus profitability; literature motivates hypotheses only.

Selected primary check: [Nifty momentum](https://www.niftyindices.com/indices/equity/strategy-indices/nifty200-momentum-30) confirms volatility-adjusted six/twelve-month score; a 20-session or 12-minus-1 Icarus card is an adaptation.

Selected primary check: [AQR 2017 trend paper](https://www.aqr.com/-/media/AQR/Documents/Insights/Journal-Article/AQR-JPM-Fall-2017.pdf) confirms 67 markets, 1880-2016 and bidirectional monthly 1/3/12-month construction, not a cash-equity Donchian replication.

Selected primary checks: [NSE low-vol methodology, September2019](https://www.niftyindices.com/Methodology/Method_Nifty100_Low_Volatility_30.pdf) confirms one-year daily volatility, quarterly review and inverse-vol weights; [2012 cost paper](https://pages.stern.nyu.edu/~afrazzin/pdf/Trading%20Cost%20of%20Asset%20Pricing%20Anomalies%20-%20Frazzini,%20Israel%20and%20Moskowitz.pdf) confirms institutional 19-market evidence and reversal cost constraint. Neither is an Indian retail net-return prediction.

Read-only review; no strategy evaluation, YAML/runtime/shared-document edit, actual ledger access or data approval; other cited references were not comprehensively audited.

## Amendment disposition

The proposal now marks the low-volatility rule blocked on an implemented scheduled-rebalance consumer plus reviewed turnover/re-entry semantics, retains the Donchian-exit block, and labels every proposed number as a project-owned rule-card choice rather than a paper-proved optimum. A claimed 30-name cohort must refuse if fewer than 30 names are eligible; the final cohort policy remains subject to exact card review. The result remains a scoped GO for research/cards and a NO-GO for treating all six as immediately executable.
