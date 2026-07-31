# LLM Council review — PRD Phases 0, 1, 2

*Run 2026-07-31 at the operator's request. Five advisors answered independently, peer-reviewed each
other anonymously, and the findings below were then verified against the repo. **Verification
matters: two of the council's most forceful claims did not survive it.***

**Method caveat, stated up front.** Karpathy's original council dispatches to *different vendors*, so
its diversity is genuine model diversity. This run used five Claude sub-agents wearing different
thinking lenses. That produces real, structured disagreement — but correlated blind spots stay
correlated. Trust it to find gaps in reasoning; do not trust it to independently verify a fact.
Hence the verification pass.

---

## The questions asked

1. Is the Phase 0/1/2 sequence right, or is something mis-sequenced, missing, or over-built for the
   capital at stake?
2. Is the Phase-1 stop gate genuinely designed to **falsify** the system, or designed to pass?
3. Is the 12-agent message-bus architecture the right shape for one operator on one small VM?
4. What is this plan missing that will hurt most in month six?

---

## 1. Unanimous: the stop gate is not a gate

**All five advisors, independently, reached the same verdict on question 2.** That is the highest-
confidence signal the method can produce.

**Verified.** `TASKS.md:94` reads:

> **🛑 PHASE 1 STOP GATE.** Produce a **metric sheet for one hand-written strategy** … **Deliver it
> to the operator and pause.**

Every other task in `TASKS.md` carries an `**AC:**` line with a testable criterion. The one decision
that determines whether real money is ever risked does not. It specifies a *deliverable*, not a
*threshold*.

Three compounding problems the advisors named:

- **No pre-registered numbers.** Nothing states what result would mean *stop*. A criterion written
  after seeing results is a rationalisation, not a test.
- **The builder is the judge.** The sole reviewer is the author of six months of work.
- **The human trial count is invisible.** "One hand-written strategy" is fiction in practice — the
  operator will iterate by hand until something clears DSR > 0.95. Those human trials never enter
  the effective-trial ledger that task 1.9 counts, so the multiple-testing guard is blind to the
  only searcher that exists in Phase 1.

That third point is the sharpest thing the council produced. The overfitting defence has a hole in
exactly the place Phase 1 operates.

---

## 2. Verified: the risk model cannot be expressed in whole shares

Raised in peer review, arithmetic partly wrong, **conclusion correct and worse than stated.**

At ₹25,000 equity and 0.5% risk, a trade risks ₹125. Position size = risk ÷ stop distance. With a
2×ATR stop on a stock whose ATR is ~2% of price, stop distance ≈ 4%, so position value ≈ ₹3,125.

| Share price | Shares affordable | Quantisation error |
|---|---|---|
| ₹500 | 6.25 → **6** | 4% |
| ₹1,000 | 3.1 → **3** | 4% |
| ₹2,000 | 1.56 → **1** | **36%** |
| ₹3,000+ | 0.6 → **0** | **position impossible** |

**Confirmed absent from the repo:** no lot-size, rounding, or quantisation logic anywhere
(`grep` for `lot_size|round_lot|quantiz|whole share` returns nothing in `icarus/`, `goal.yaml`, or
`PRD.md`).

**The part nobody said out loud:** this squeezes the tradable universe from both ends. `goal.yaml`
sets `min_close_inr: 30` for the penny ban (invariant #14, §29.2), and share quantisation imposes an
*implicit maximum* around ₹2,000–3,000. Icarus can only honestly size positions in a price band it
has never written down. Combined with the flat **₹15.34 DP charge** on every delivery sell — 0.49%
of a ₹3,125 position — the economics of the whole seed tier live in that unstated band.

**This needs a task.** Sizing must round to whole shares, report the resulting risk error, and
**refuse the trade** when quantisation pushes actual risk outside tolerance — rather than silently
rounding to 1 share and taking 3× the intended risk.

---

## 3. Verified: O3/O4 gate Phase 1, not Phase 2

`TASKS.md` marks the AWS VM + Elastic IP (O4) and the Delta account + testnet (O3) as
*"Blocks Phase 2."* But task **1.10 (sim forward-runner)** — a Phase 1 task — runs on Delta testnet
and live Zerodha data. **Phase 1 cannot finish without them.** Roughly two hours of operator work
each, gating weeks of calendar. Mislabelled.

---

## 4. What did NOT survive verification

Recording these because a council that is never wrong is a council that is not thinking.

**❌ "D3 hides the infrastructure cost."** The Contrarian argued that reclassifying Kite's ₹500/mo as
capital makes the true economics invisible and that the gate will promote strategies that cannot
break even. Two peer reviewers pushed back, and the repo confirms them. `BUILD_MAP.md:129` states it
plainly and unprompted:

> at a ₹25–30k seed, ~₹3,000/mo is 10–12% of the whole account every month before a single trade …
> **The system cannot out-earn its own hosting bill at seed scale.**

D3 further *requires* the ₹500 to appear as its own line in the daily report and the metric sheet,
never netted into strategy P&L. And Phases 0–1 cost ₹700–1,200/mo, not ₹3,000 — the AWS layer only
switches on at Phase 2. The cost is documented, quantified, and deliberately excluded from the
*per-trade hurdle* on the stated grounds that a fixed monthly cost is not a function of trade count.
**The accounting is sound; the underlying economic point — the machine cannot pay its own rent at
seed scale — was already in the docs before the council convened.**

**❌ "SEBI algo approval may be per-strategy, which forbids Phase 3."** Already researched in
`PRD.md:214`: below the 10 OPS ceiling **no full per-algo exchange registration is required**; API
orders need a *generic* algo-ID via the broker and must be tagged. That is precisely why the
order-rate governor is pinned at ≤2 OPS. Worth re-confirming with Zerodha (operator item O1), but it
is not an unaddressed structural hole.

**⚠️ "The 12-agent mesh is over-built."** Genuine disagreement, unresolved — see §5.

---

## 5. Where the council clashed

**On architecture, three ways.** The Contrarian: only three process boundaries earn their keep
(write-credentials, no-credentials, kill-bot); the other nine are functions in one asyncio loop, and
decision D2 is still open in the repo's own map. The First Principles Thinker reframed it — the
problem isn't complexity, it's that the architecture is *pre-committed to a trade frequency the
capital has already falsified*. The Expansionist inverted it entirely: marginal cost per agent is
one supervised task, so the mesh is the cheapest optionality in the build and is *under*-exploited.

**Reasonable people disagree here because they are optimising different scarce resources** — the
Contrarian optimises operator attention, the Expansionist optimises optionality. Both peer reviewers
who commented sided against the Expansionist, on the grounds that the binding constraint for a solo
builder working evenings is calendar, not capability — and that "more scope" is the one prescription
this plan cannot afford.

**On scope, sharply.** The Executor wants task **1.2 (Macro/News) cut from Phase 1 entirely** and
**1.3 (Regime) stubbed**, on the grounds that nothing consumes sentiment until Phase 3 — it is an RSS
pipeline, an LLM bill, a prompt-injection test suite and a schema, all built to sit idle through the
gate. The Expansionist wants *more* built. Two of three reviewers backed the Executor.

---

## 6. The convergent finding: nothing measures time-to-evidence

Four of five advisors arrived at the same month-six failure from different directions, and it is not
a bug — it is arithmetic nobody has done.

Daily bars, max 3 concurrent positions, a 1.5× cost hurdle. Task 1.10 requires ≥30 trades before a
verdict; the Phase-2 canary requires ≥10 more over ≥1 week. **If a candidate strategy fires ~30
trades/year, the sim forward-run alone consumes 12 months and the canary another 4.** The answer
arrives in 2028.

Below roughly 50 trades/year the entire DSR/PBO/canary apparatus is **statistically inert** — it is
machinery that cannot reach significance on the sample the strategy will produce. `BUILD_MAP.md`
already carries this as risk **M4** ("time-to-first-evidence is months and isn't stated — Open").
The council's contribution is that M4 is not a documentation gap; it is potentially a *design*
falsifier, and it is computable in an afternoon from data already ingested.

**This should be computed before the backtester is built, not after.** If the number is low, the
honest response is intraday data (Phase 2 dependency) or a higher-frequency strategy class — not
more validation machinery.

---

## 7. The council's strongest single insight

From the Outsider, who by design read no files:

> **All 22 invariants protect against catastrophe; none protect against the likely outcome.**
> Every rule guards a fast death — wrong order type, wrong IP, double-send. The actual failure mode
> is a slow, perfectly-compliant bleed to zero while every assert passes.

Verified by inspection: there is no invariant of the form *"if net-of-cost P&L is flat or down after
N trades, halt the system."* The kill-switches in §14 are all **drawdown**-triggered (−3% daily,
−10% peak-to-trough). A strategy that grinds −0.3%/month indefinitely trips nothing.

The same advisor's second point stands too: **there is a kill switch on trades and none on the
project.** ₹25,000 is not the scarce resource — a year of evenings is.

---

## 8. Recommendation

Four changes, in order. None of them is "build more."

1. **Put numbers in the stop gate, before task 1.7 is written.** Pre-registered thresholds in
   `goal.yaml`, asserted in code, decided while the outcome is still unknown: minimum OOS Sharpe net
   of cost *and* tax, maximum IS→OOS decay, DSR > 0.95, minimum trade count, minimum OOS calendar
   span. Plus the sentence that does not currently exist anywhere: **what result means stop.**
2. **Count the human trials.** The effective-trial ledger in 1.9 must include hand-authored
   iterations, not just Inventor-generated ones. Otherwise the multiple-testing guard is blind
   throughout Phase 1.
3. **Compute the expected trade count now** — an afternoon on data already in hand. It determines
   whether the validation apparatus can reach significance at all, and therefore whether the current
   plan is coherent.
4. **Add a position-quantisation task.** Round to whole shares, report the induced risk error, refuse
   the trade when it exceeds tolerance, and write down the implicit price band.

**And one economic gate worth stating plainly:** a stagnation halt. Not drawdown-triggered —
*flatness*-triggered. If net-of-cost P&L is not distinguishable from zero after N trades, the system
should stop and say so.

---

## 9. The one thing to do first

**Write the falsification criteria into `goal.yaml` and `TASKS.md` today, before the backtester
exists.** Everything else on the list can be sequenced. This one cannot, because its entire value
comes from being written while the answer is still unknown — and the backtester is what produces the
answer.

---

*Advisors: Contrarian, First Principles, Expansionist, Outsider, Executor. Peer review: 3 reviewers
over anonymised responses (mapping A=Expansionist, B=Outsider, C=Contrarian, D=Executor,
E=First Principles). All three reviewers independently ranked the Executor strongest and the
Expansionist as holding the largest blind spot. Verification against the repo performed afterwards;
see §4 for what failed it.*
