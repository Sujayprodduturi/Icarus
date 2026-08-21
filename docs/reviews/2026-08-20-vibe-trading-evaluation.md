# Evaluating HKUDS/Vibe-Trading against Icarus

**Date: 2026-08-20.** Written in response to `docs/ICARUS - Evaluate Vibe-Trading.md`.
Nothing was merged, copied, or vendored. This is the written evaluation that task asked for.

**Verdict in one line: keep building Icarus, and lift two files.** Not a hybrid platform — a
two-module borrow that closes one of our open findings and changes nothing else.

---

## 0. What I actually did

Cloned `HKUDS/Vibe-Trading` at `7329cb0` (release 0.1.14) into a scratch directory, read the
subsystems the task named, and **ran the parts I proposed to borrow** in a clean Python 3.12
virtualenv. I did not install the full platform and did not run anything against a network data
source or a broker.

The repo is real and the brief's description of it is accurate — mildly *understated*, if anything:

| the brief said | what is actually there |
|---|---|
| 456 alpha factors | **462** factor modules (`alpha101` 101, `gtja191` 191, `qlib158` 154, academic 12, fundamental 4) |
| 79 finance skills | **90** skill directories |
| ~29 swarm presets | **30** preset YAMLs |
| ~28k stars, MIT | **31,321** stars, MIT, created 2026-04-01, **pushed the same day I read it** |
| MCP server | **66** MCP tools |

Scale: ~356,000 lines of Python, of which ~173,000 is source and ~139,000 is tests across 499 test
files. This is a serious, actively maintained project, not a README with a thin library behind it.
It is also not a Qlib or TradingAgents fork, as the brief said.

**One correction to my own working note:** my first run of their India engine tests showed 2
failures. That was my environment — I had installed pandas 3.0.5 while they pin `pandas<3.0.0`.
Inside their supported range (pandas 2.3.3) **all 94 tests I ran passed.** No defect there; the
only real observation is that the project is not yet pandas-3 ready, which their pin states openly.

---

## 1. The four blockers — why we cannot adopt their research/backtest layer

The brief's proposed hybrid was: *use Vibe-Trading's research + factor + backtest layer, keep
Icarus's execution plane + quant gate + broker failover on top.* I went looking for reasons that
would work. It does not, and the reasons are not matters of taste — each one collides with a
safety invariant we already wrote down, and **each collides in the optimistic direction**, which is
the direction that costs money.

### Blocker 1 — their fill model always fills, at the open, at a fixed slippage

`agent/backtest/engines/base.py` executes every order at the next bar's open price, multiplied by
a slippage constant (`execution_open()`, `apply_slippage()`). I searched the entire 356k-line repo
for the vocabulary of a limit-order simulation — queue position, unfilled, trade-through, no-fill.
It is not there. The word "limit" inside the engine means a **circuit band** (the ±20% price band)
or a forward-fill window, never a limit order.

This is the single most important finding in this evaluation. Our own rulebook says:

- **Invariant #12** ("touch ≠ fill" is forbidden): a resting LIMIT order fills only if price trades
  *strictly through* it, with pessimistic queue position, and **no-fill is a real modeled outcome**.
- **Invariant #5** (LIMIT orders only, never MARKET): the NSE bars plain market orders placed via
  algo, so our execution agent may only ever place marketable-limit orders.

Their engine models the thing we are forbidden to do, and models it as always succeeding. Any
strategy that clears their backtest has been measured under an assumption we have already ruled
out as dishonest. We would have to rebuild the fill model — which is task `1.7b`, already **built
and passing** on our side, with trade-through, queue position, next-bar execution and partial fills.

To be fair to them: they are careful about *time*. Signals are shifted one bar (`_align()`,
"next-bar-open semantics"), and there is an explicit comment refusing to use the current bar's
close for sizing because "using it is lookahead". Their lookahead discipline is good. Their
**fill realism** is the gap.

### Blocker 2 — there is no capital-gains tax anywhere in the project

Their cost stack for India is genuinely good and close to ours: STT, exchange transaction charge,
SEBI turnover fee, stamp duty (buy-side only), GST on the right subset, DP charge on sells, all
config-driven, with an honest docstring warning that SEBI tariffs change and should be re-verified.
That is real work and it matches our `CostModel`.

But those are **transaction** taxes. A search across the whole repo for capital-gains vocabulary —
`STCG`, `LTCG`, `capital gain` — returns **zero hits in any source file**. There is no
short-term/long-term equity treatment and no crypto VDA treatment.

`CLAUDE.md` §5 requires costs **and taxes** computed inside every backtest, and after task 2f our
stop gate is an *after-tax* gate. Their "net" number is net-of-cost only. Feeding it into our gate
would be comparing two different quantities, which is precisely the class of error the 2026-08-09
audit exists to stop.

### Blocker 3 — no point-in-time universe for India, and the price feed is not dividend-adjusted

They do have point-in-time discipline — for **fundamentals** and for **news/events**, both of which
carefully gate on a knowable-date. And China gets properly forward-adjusted prices (`cn_adjust.py`,
`qfq`) through akshare/tushare/tencent.

India gets neither. The loader chain is `yahoo → yfinance → india_broker → local`:

- The primary `yahoo_client.py` reads `indicators.quote[0]` from Yahoo's chart endpoint and
  **never touches the `adjclose` array**.
- `yfinance_loader.py` calls `yf.download(..., auto_adjust=False)` and its column map contains
  `"Close" → "close"` with no entry for `Adj Close`.
- The broker loader is opt-in and only returns a bounded window of *recent* bars, so it cannot
  supply deep history at all.
- There is **no historical index-membership and no delisted-symbol handling anywhere** — nothing
  that reconstructs what was tradeable on a past date.

Our **invariant #14** requires point-in-time data, no survivorship, and back-adjustment for
corporate actions. We have already built that: 2,962 sessions × 693 point-in-time symbols, and a
`Panel` that structurally *refuses to be built* without point-in-time membership. Taking their data
layer would be a regression, not an acceleration.

**What I cannot verify from the code, and am therefore not claiming:** Yahoo restates history for
splits upstream, so the practical gap here is most likely *dividend* adjustment — price-return
where we want total-return — rather than raw unadjusted prices. How well Yahoo handles Indian
corporate actions specifically (bonus issues, demergers) is not answerable from this repo. What I
*can* state from the code is that the adjusted series Yahoo provides is available and unused.

### Blocker 4 — a strategy is arbitrary Python, not a constrained vocabulary

A Vibe-Trading strategy is a `signal_engine.py` module with
`generate(data_map: Dict[str, pd.DataFrame]) -> Dict[str, pd.Series]`, loaded with `importlib`.

`backtest/runner.py` does run an AST scan over it first — but reading it closely, that scan is an
**import-time execution guard**: it rejects decorators, non-literal defaults, and unsafe
annotations so that merely importing a strategy file cannot run code. It is not a semantic guard.
Once `generate()` is called, arbitrary pandas runs, and nothing prevents `close.shift(-1)` — a
direct read of tomorrow.

Their protection against that is *convention*: the operator library deliberately omits a negative
shift ("Lookahead ban: `delta(df, d)` requires `d >= 1`; the negative-shift `Ref(df, -n)` form is
intentionally absent"). That is admirable discipline and it is exactly the right instinct. It is
still convention, and it is enforced on the 462 factors they wrote, not on the strategy an LLM
writes tonight.

Icarus's DSL is a closed vocabulary of **224 typed words** with declared lookback, declared units
and declared scale-free status, refused at parse time. That difference is the whole point of the
DSL and it is not something we would give up.

### And the part the brief assumed we'd keep anyway — there is no Indian execution to replace

Worth stating plainly, because it removes the hybrid's main attraction. **No Indian broker in that
repo can place a live order.** Both India connectors are structurally capped at paper:

```python
# dhan/sdk.py, place_order()
# ---- HARD GUARD: structurally paper-only (must run before anything) ----
if not cfg.is_paper:
    return PAPER_ONLY_REFUSAL
```

Their reasoning is sound and honest: Dhan's API exposes no runtime paper/live discriminator — the
same token reads the same account either way — so rather than trust a config flag with real money,
they refuse to expose a live path at all. Shoonya is the same shape.

Live order placement exists only for Alpaca, Binance, eToro, Futu, MT5, OKX and Tiger. **Zerodha
and Upstox are not present in the repo at all.** So the execution plane, the broker failover, the
algo-ID tagging and the static-IP origination requirement are not "ours to keep on top" — they are
ours to build regardless, exactly as `TASKS.md` already schedules.

---

## 2. Overlap map

| capability | Vibe-Trading | Icarus | who is ahead |
|---|---|---|---|
| Indian daily equity backtest | yes | yes | **Icarus** (point-in-time panel, tax, honest fills) |
| India transaction-cost stack | good, config-driven | good, config-driven | tie |
| Capital-gains / VDA tax | **absent** | built (`taxmodel.py`) | **Icarus** |
| Fill realism | open + fixed slippage, always fills | trade-through, queue, partial, no-fill | **Icarus** |
| Next-bar execution, no same-bar lookahead | yes | yes | tie |
| Point-in-time universe, survivorship | fundamentals/events only; not India prices | structural, enforced by `Panel` | **Icarus** |
| Walk-forward with purge/embargo | yes, incl. combinatorial | yes (one fixed `seam_sessions`) | tie |
| DSR / PBO / multiple-testing control | **built and tested** | **not built** (open finding F12) | **Vibe-Trading** |
| Factor library | 462 formulaic alphas | 224 DSL words | different things (see §3) |
| Strategy specification | arbitrary Python | constrained typed DSL | **Icarus** |
| Pre-registered, non-negotiable gate | no equivalent | yes, date-pinned | **Icarus** |
| Audit log — tamper **prevention** | file-based; nothing blocks a rewrite | **DB trigger blocks UPDATE/DELETE** | **Icarus** |
| Audit log — tamper **detection** | **hash-chained, fsynced, verifiable** | none | **Vibe-Trading** |
| Live order path (India) | none | none yet, by design (Phase 2) | tie |
| Agent/LLM research layer | large (swarms, skills, MCP) | planned, not built | Vibe-Trading |

Two rows deserve emphasis because they cut against the "keep building" verdict, and honesty
requires them to be as visible as the rest: **they have shipped DSR/PBO and we have not**, and
**their audit ledger is better engineered than ours.**

---

## 3. Borrow list — concrete, with evidence

### Worth borrowing now

**1. `agent/src/quantlib/multipletesting.py` — 568 lines.**

Probabilistic Sharpe Ratio, expected-maximum-Sharpe under the null, Deflated Sharpe Ratio,
Benjamini-Hochberg false-discovery control, and PBO via CSCV. This is **finding F12** — "DSR/PBO
not built" — which is currently sitting in our open-findings list with no task number against it.

Quality evidence, not vibes:

- The maths follows Bailey/López de Prado faithfully. `expected_maximum_sharpe` uses the
  Euler-Mascheroni form; `probabilistic_sharpe_ratio` carries the skew/kurtosis variance term
  rather than being a disguised t-test.
- The module docstring names **the two conventions that silently break these formulas** — Sharpe
  must be per-observation not annualised (an annualised Sharpe with a daily `T` inflates the
  statistic by roughly √252 and "turns a coin flip into a certainty"), and kurtosis must be
  non-excess (scipy and pandas both return excess by default). It then *enforces* the second one
  with a validation error that says "excess kurtosis was probably passed."
- Dependencies: `numpy`, `pandas`, and `scipy.stats.norm`. Nothing else. No LLM, no framework.

**I ran it.** Clean venv, Python 3.12, only numpy/scipy/pandas/pydantic/pyyaml installed:

```
tests/quantlib/test_multipletesting.py tests/quantlib/test_crossvalidation.py
75 passed in 4.39s
```

**2. `agent/src/quantlib/crossvalidation.py` — 473 lines.**

Purged k-fold, purged walk-forward, combinatorial purged splits, and a `detect_boundary_leakage`
routine. Relevant to decision D10 (the single fixed `seam_sessions` that replaced the purge that
protected nothing). `detect_boundary_leakage` in particular is a test we do not have.

**How to take them — and this matters.** `CLAUDE.md` §5 says to implement DSR and PBO/CSCV
**in-house from the cited formulas**. So the correct use of these two files is as a **reference
implementation and a differential-test oracle**, not as a vendored dependency. Their 75 tests
become our test corpus: we write our own numpy implementation and assert it agrees with theirs to
tolerance. That is a stronger position than vendoring, and it keeps §5 intact.

**Cost of borrowing.** Icarus today depends on numpy and nothing else numeric — **no pandas, no
scipy**. Their modules are pandas-typed and need `scipy.stats.norm` for two calls (`cdf` and
`ppf`). Two options: add scipy, or reimplement those two normal-distribution calls (`cdf` is
`math.erfc`; `ppf` needs an inverse-normal approximation). Using them as an oracle in the *test*
environment only means the production dependency list does not change at all. That is my
recommendation.

**Estimated saving: 3–5 days on F12**, mostly in not re-deriving the formulas and not discovering
the annualisation and excess-kurtosis traps the hard way.

**3. One design idea, free of charge — and it lands on 2g-3.**

Their cross-sectional rank is:

```python
df.rank(axis=1, method="average", pct=True, na_option="keep")
```

A row where every symbol has the same value returns **0.5 for everyone** — a tie produces a tie.
Ours falls through to alphabetical order. Same latent problem, different failure mode, and theirs
is the safer one. See §6.

### Worth noting, not borrowing yet

**`agent/src/governance/ledger.py`** — a hash-chained, fsynced, append-only JSONL ledger. Every
record embeds its sequence number and the previous record's hash, so editing any earlier record
breaks every hash after it. It fsyncs the file *and* the parent directory on creation, holds a
cross-platform file lock across the read-tail-and-append critical section, and **refuses to extend
an already-broken chain** rather than building a valid-looking suffix on corrupted history.

**Corrected 2026-08-20, same day, before any of this was built.** The paragraph here originally
said our audit log "is currently the simpler thing their own docstring describes as the weakness
they fixed: a bare append with no fsync and no chaining." **That was wrong, and it was wrong
because I read their docstring and assumed it described us without checking ours.**

What we actually have (`icarus/state/audit.py`, migration `d8847faf5e20`) is a Postgres table with
a **database-level trigger that blocks UPDATE and DELETE outright**, written inside the caller's
transaction so the audit record commits atomically with the state it describes, with secrets
scrubbed on the way in. Durability is Postgres's problem and it is solved. On *prevention* we are
ahead of them, not behind.

The real gap is narrower and different: **we have tamper-prevention and no tamper-detection.** Our
own downgrade migration contains `DROP TRIGGER IF EXISTS audit_log_append_only` — one statement,
after which rows are editable and nothing in our system would ever know. Their hash chain does not
prevent that either; it makes it *detectable*. The two properties are complementary and a log that
has both is stronger than a log with either.

So the borrow is smaller and sharper than first described: two columns (`prev_record_hash`,
`record_hash`) and a `verify_chain` routine, on top of a trigger we already have. Approved by the
operator on 2026-08-20 and scheduled **after** the next backtest — no orders exist in Phase 1, so
it changes no number on the metric sheet and does not belong on the critical path.

**`agent/src/live/`** — a mandate/enforcement gate with hard caps (max order notional, max total
exposure, max leverage, max trades per day), a consent token, and a read/write classification of
every broker SDK call that is **fail-closed**: anything unlisted is treated as a WRITE. That
fail-closed default is a good pattern and matches our posture.

### Not worth borrowing

**The 462-factor zoo.** This is the borrow the brief was most hopeful about, and it is the one I
would decline. Three reasons:

1. **Wrong data model.** Every factor operates on wide pandas DataFrames indexed date × symbol.
   Our engine is a numpy panel. Porting 462 factors is a rewrite, not a lift.
2. **Wrong provenance for our gate.** These are US and China formulaic alphas (Kakushadze's 101,
   GTJA's 191, Qlib's 158). They are *hypotheses*, and our pre-registered gate plus trial ledger
   would treat 462 of them as 462 trials — which is exactly what their own `multipletesting.py`
   docstring warns about: "run 462 factors over one history, keep the best Sharpe, and you have not
   measured an edge — you have measured the maximum of 462 draws."
3. **Wrong phase.** A hypothesis source belongs to the Strategy-Inventor, which is Phase 3+. Right
   now it would be a very expensive distraction from a repair plan with two steps left.

Revisit at the Inventor stage, as a source of *ideas* to re-express in our DSL — never as code.

**The platform itself** (CLI, Web UI, REST API, MCP server, swarms, 90 skills). Impressive, and
irrelevant to us: it is a research-assistant surface, and its dependency footprint is langchain +
langgraph + fastapi + uvicorn + weasyprint + matplotlib + tushare + akshare + ccxt + duckdb +
scikit-learn. Icarus's entire production dependency list is six packages. One genuinely good
property worth recording: **their backtest layer has no LLM coupling at all** — I checked, and
`backtest/` imports nothing from langchain or any model provider. The library is usable headlessly.
That is why the two-file borrow is even possible.

---

## 4. Our moat, specifically

Not "we have an execution plane and they don't" — here is what is actually load-bearing:

1. **The fill model.** Pessimistic by construction: trade-through required, queue position,
   next-bar execution, partial fills, and no-fill as a real outcome. Theirs is optimistic by
   construction. This is the difference between a backtest that can disappoint you and one that
   cannot.
2. **Tax inside the loop.** `taxmodel.py`, including the crypto VDA reclassification stress
   scenario. They have no capital-gains model at all.
3. **The point-in-time panel.** Enforced structurally — `Panel` refuses to be built without
   point-in-time membership, and `assert_panel_stops_before_lockbox` refuses a panel that reaches
   the lockbox.
4. **The constrained DSL.** 224 typed words, declared lookback and units, parse-time refusal —
   versus arbitrary Python behind an import-time sandbox.
5. **The gate that cannot be renegotiated.** Date-pinned 2026-08-01, loader asserts the date has
   not moved, amendments append-only and flagged if made after results exist. Plus the trial ledger
   that counts human attempts, and a lockbox consumed exactly once. They have a run card, an
   evidence store and a governance ledger — good engineering — but nothing that stops a threshold
   from being quietly lowered after seeing the metric sheet. That mechanism is the most
   distinctively valuable thing we have built, and it exists because we wrote down what we would
   accept *before* we knew whether we could hit it.
6. **SEBI-specific execution law.** Algo-ID tagging on every order, registered-static-IP
   origination asserted daily, market orders refused in code, order-rate governor. None of this
   exists in their repo, for any market.
7. **Halt-on-stagnation** (invariant #23 — halt on a slow, compliant bleed, not just a fast loss).
   Nothing in their repo addresses it.

---

## 5. Recommendation

**Keep building Icarus. Borrow two files as reference implementations. Do not adopt the platform.**

The brief asked me to pressure-test the hybrid — *their research/factor/backtest layer under our
execution plane and gate* — and to argue for or against with evidence from the code. I argued
against, on four grounds, each verified: their fills always succeed, they model no capital-gains
tax, their Indian price history is neither point-in-time nor dividend-adjusted, and their
strategies are arbitrary Python. Any one of those would need repairing before a single number from
their engine could pass our gate. Repairing all four *is* our backtester — which is built.

The honest way to put the schedule effect: **this evaluation saves us 3–5 days on F12 and costs us
nothing else.** It does not accelerate Phase 1, and it does not change the repair plan. I would
rather say that plainly than dress a two-file borrow up as a strategic pivot.

One thing this exercise did change: it is now clear we are **behind on two specific things** —
multiple-testing control (which we knew) and audit-log tamper-evidence (which we did not). Both are
now written down here rather than only in my head.

A caveat against my own verdict, stated because it is the strongest argument on the other side:
their project has 31,000 stars, 90 skills, and a research surface we have not begun. If the goal
were "have a capable research assistant this month", adopting it would win easily. The goal is a
system that places real money under SEBI rules and cannot fool itself. On that goal, the four
blockers decide it.

---

## 6. What this means for task 2g-3 — the answer to "read it first and you'll understand why"

**2g-3 still needs doing, unchanged.** Nothing in Vibe-Trading removes the need for it, because we
are not adopting the layer it would have belonged to.

The task, restated: `rank_by` sorts the universe to decide which candidates get the limited slots.
Some words return **one number for the whole market**, not one per symbol. Ranking a universe by a
number identical for every symbol is not a ranking — the sort falls through to the tiebreak, which
is the symbol name. A degenerate alphabetical ranking that reports as a working one.

Reading our own code alongside theirs sharpened the fix. In `icarus/strategy/dsl.py`, `_rank_by`
already refuses three things: a boolean-producing word, a word carrying an `unrankable_reason`, and
a non-scale-free word. The market-wide words slip through **all three**, because in
`icarus/strategy/library/cross_sectional.py` they are registered as `Kind.SERIES` with
`scale_free=True` and no `unrankable_reason` — for example `breadth_pct_above_ma`,
`advance_decline_ratio`, `new_highs_minus_new_lows` and `benchmark_return`, all of which compute a
single row and broadcast it. That module's own header even says it plainly: these words return
"one row per symbol (**or a single row when the answer is the same for everyone, like market
breadth**)". The knowledge was already written down; it was simply never enforced.

So the fix has the same shape as F1's units fix — a **declared property on the primitive, refused
at parse time**, not a list maintained in the parser. Plus the feed words the task names
(`fii_net_index_fut`, `client_net_index_fut`, `in_fno_ban`), and the same refusal applied to the
`xs_*` words, which carry the identical between-symbols requirement.

And one idea worth taking from them: even after market-wide words are refused, ties can still
occur. Their `rank(..., method="average")` makes a tie *produce* a tie rather than an arbitrary
order. Ours should not silently fall through to alphabetical either.

**I have not started 2g-3.** Per the working loop — explain, approve, build, summarise — this is
the explanation; the plan above is what I would build on your go-ahead.

---

## 7. If we ever do go hybrid, the first concrete step

Not a merge. A **differential test**: implement DSR in-house in numpy against the cited formulas,
then assert our implementation agrees with `multipletesting.py` to tolerance across their 75-case
corpus. Their module never enters the production dependency list; it lives in the test environment
as an oracle. If the two disagree, we have found a bug in one of them before either touches a
strategy decision — and that is worth more than the code itself.

---

## 8. Risks and caveats

- **Licence: fine.** MIT, with per-zoo `LICENSE.md`/`NOTICE` files inside the factor directories.
  Attribution required, which for a two-file borrow means a source-and-date comment — which
  `CLAUDE.md` §6 requires of us anyway for any external fact.
- **Adding scipy** is a real if small cost; avoidable entirely by using their code as a test-only
  oracle. Recommended.
- **They are not pandas-3 ready** (`pandas<3.0.0`). I tripped over this myself.
- **Maintenance risk is low but real.** Very actively developed — pushed the day I read it — but
  221 of the commits visible in a shallow clone are from a single author. A young project (created
  2026-04-01) at version 0.1.14. Another argument for copying ideas rather than taking a dependency.
- **Their code quality is high.** I want to say this without hedging, because it is the strongest
  reason to take their maths seriously: the docstrings explain *why*, the failure modes are named,
  the guards are fail-closed, and the tests are numerous and real. Where I disagree with their
  design it is about what the system is *for* — a research assistant across twelve markets, versus
  an autonomous system that must not fool itself about one.

### What I could not verify from the code, and am not claiming

- Whether all 462 factors correctly implement their source papers. I read one (`alpha_001`) closely
  and it matches Kakushadze's published formula. The other 461 are unaudited.
- Any connector's live behaviour. I hold no credentials for Dhan, Shoonya or any other venue, and
  did not attempt a network call to a broker.
- The Web UI, desktop app, and swarm/agent layer beyond reading their structure. No LLM was run.
- How well Yahoo's Indian corporate-action handling actually performs (see Blocker 3).
- Monte-Carlo backtesting and portfolio optimisation quality beyond reading `validation.py` and
  the five optimiser modules. I did not run them.

---

## 9. Watch list — what would change this verdict

*Added 2026-08-20 on operator instruction: "we need to keep a track of this repo and the
enhancements in it that can add value to us."* A monthly scheduled check runs against this list.

**Pin:** `HKUDS/Vibe-Trading` @ `1907e47`, version 0.1.14, **2026-08-21**. Everything below is a
delta against that commit. *(Originally pinned at `7329cb0`, 2026-08-20; moved after the first
watch run.)*

### First watch run — 2026-08-21

**No re-evaluation warranted.** 68 commits since the original pin; version unchanged at 0.1.14.
Nine of the ten watched paths were **byte-identical** — compared by blob sha, not diff text — and
none of the three triggers fired. All four blockers stand.

One watched path changed: `agent/src/quantlib/crossvalidation.py`, **+87/−0**, purely additive —
a new `group_purged_kfold_splits` that groups rows by a time-group id so simultaneous observations
across assets cannot straddle a train/test boundary. Nothing existing was modified, so **there is
no fix here for us to mirror**: the oracle's existing behaviour is untouched.

⚠️ **And a caveat worth keeping, if we ever reach for that new function.** The run reports it
yields `purged=0` unconditionally and embargoes *forward* from the test block without purging train
rows backward — where the original `purged_kfold_splits` computes a real purge count. For a panel
with multi-day labels that is a leakage path the older function closes and the newer one does not.
**Reported by the watch run and not independently verified here**; verify before use.

### The three that would force a re-evaluation

Any one of these appearing means the "keep building Icarus" verdict has to be re-argued, because
each removes one of the four blockers in §1:

1. **A real limit-order fill model** in `agent/backtest/engines/` — anything introducing queue
   position, a trade-through test, or no-fill as an outcome. Watch for the vocabulary that is
   currently absent repo-wide: `queue`, `unfilled` (in an engine, not `factor_costs.py`),
   `trade_through`, `no_fill`.
2. **A capital-gains tax layer** — any appearance of `STCG`, `LTCG`, `capital_gain`, or a holding-
   period-dependent tax. Today: zero hits repo-wide.
3. **A Zerodha or Upstox connector** in `agent/src/trading/connectors/`, or either Indian connector
   gaining a live (non-paper) order path.

### The paths worth diffing each month

| path | why we care |
|---|---|
| `agent/src/quantlib/multipletesting.py` | our DSR/PBO oracle — a fix there is a fix we should mirror |
| `agent/src/quantlib/crossvalidation.py` | same, for purge/embargo and boundary leakage |
| `agent/src/governance/ledger.py` | the hash-chain design we are adopting |
| `agent/backtest/engines/india_equity.py` | India cost stack; SEBI tariffs change |
| `agent/backtest/engines/base.py` | where a real fill model would land |
| `agent/backtest/loaders/india_broker_loader.py`, `yahoo_loader.py`, `yfinance_loader.py` | India data path; adjustment handling |
| `agent/src/trading/connectors/dhan/`, `shoonya/` | Indian broker surface |
| `agent/src/factors/base.py` | operator semantics — where their tie/rank conventions live |

### The routine that runs this

**Scheduled cloud agent `trig_01ESBxmpeokKZo2Gjki1Wmxn`**, monthly on the 1st at 03:30 UTC
(09:00 IST). First run 2026-09-01. Manage at
`https://claude.ai/code/routines/trig_01ESBxmpeokKZo2Gjki1Wmxn`. It reports "nothing changed" and
stops when that is the answer — a quiet month is meant to produce no output at all.

✅ **Fully wired as of 2026-08-21.** The routine now checks out *this* repo, reads the watch list
below directly (no drifting snapshot), clones the HKUDS repo into a temp directory as untrusted
data, and on a real change writes a delta doc, moves the pin, and opens a **pull request against
`dev`** — never pushing to `dev` or `main`.

*How it got there, since it took two attempts and the first fix was not the one that worked:*
connecting the account-level **GitHub connector was not sufficient** — the update still returned
HTTP 403 ("You don't have access to a repository this routine uses"). Running
**`/install-github-app`** in a Claude Code session is what granted the access. Worth knowing if a
future routine needs a private repo.

Two consequences worth knowing:

1. **The snapshot can drift from this section.** If you change the watch list above, update the
   routine's prompt too, or it will keep checking the old list.
2. **The pin is updated by hand.** The routine reports the new HEAD; someone edits it in here.

To remove both: authorise the Claude Code GitHub app for `Sujayprodduturi/Icarus`, then update the
routine's `sources` to this repo and restore the "write a delta doc and open a PR against `dev`"
instruction. After that the watch list has one home and the routine reads it directly.

### The standing question to ask each time

Not "what changed" but **"did they solve something we have ignored?"** That is the lesson this
evaluation was commissioned to produce, and a diff that only lists files answers the wrong
question.

---

*Scratch clone lives outside the repo, in the session's temp directory, and is not committed.
Nothing from Vibe-Trading has been copied into Icarus.*
