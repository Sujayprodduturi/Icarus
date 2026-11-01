# Vibe-Trading watch — delta for 2026-11-01

**Monthly watch run against `docs/reviews/2026-08-20-vibe-trading-evaluation.md` section 9.**

- **Pin at start of run (authoritative, from section 9 on `dev`):** `HKUDS/Vibe-Trading` @
  `1907e47d`, version 0.1.14 (2026-08-21).
- **HEAD this run:** `78fab6b3` (2026-10-30), version **0.1.18**.
- **1859 commits** since the authoritative pin (815 of them in the last 30 days) — still a very
  active project.
- **Scratch clone** lived in `/tmp/vibe-watch-2026-11/repo`, outside this repo, and was treated as
  untrusted data; nothing was copied or vendored. No file in it addressed me as an agent.

**One-line verdict: the "keep building Icarus" verdict from 2026-08-20 stands, unchanged.** The
Indian-connector trigger fires again on its *literal* text — a new `mstock/` connector and a wider
Zerodha profile set — but not on its *purpose*: every Indian connector (Dhan, Shoonya, Zerodha,
mStock) still refuses order placement before any network call, so there is no Indian live-order path.
The other two triggers are still absent. The one genuinely new thing this month is that the DSR
oracle `multipletesting.py` changed for the first time since the original evaluation — a fail-loud
fix we should mirror when we build our own, not a gap in current Icarus code.

---

## 0. Continuity note — read this first: the pin on `dev` is still August's

The authoritative pin in section 9 on `dev` is `1907e47` (2026-08-21). The **October watch
(`vibe-watch/2026-10-01`) ran, moved the pin to `18027a0`, wrote `docs/reviews/2026-10-01-vibe-
trading-delta.md`, and opened a PR against `dev` — but that PR was never merged.** So the October
delta and its pin move do not exist on `dev`; its branch still sits unmerged.

Two consequences, both deliberate:

1. **This run diffed against the authoritative `dev` pin `1907e47`, as section 9 instructs** — not
   against October's `18027a0`. The window `1907e47..78fab6b3` is therefore a **superset** of
   October's `1907e47..18027a0`. Everything the October delta found is re-covered here (the Zerodha
   connector, the dividend-adjustment fix, the per-segment purge rewrite), plus what landed in the
   815 commits since. Where this run re-confirms an October finding it says so.
2. **This PR will conflict with the still-open October PR on one line** — section 9's `**Pin:**`
   line, which October sets to `18027a0` and this run sets to `78fab6b3`. **Operator to reconcile:**
   closing the October PR in favour of this one is the clean path, since this delta subsumes it. If
   October is merged first, this branch needs a trivial rebase of the pin line. This run did **not**
   touch the October branch.

---

## 1. The three re-evaluation triggers — each tested with the exact command

### Trigger 1 — a real limit-order fill model in `agent/backtest/engines/`: **ABSENT**

Blocker 1 of the evaluation (every order fills at the next bar's open × a slippage constant; no
queue, no trade-through, no-fill never modelled) stands.

```
$ grep -rniE "queue|unfilled|trade[_-]through|no[_-]fill" agent/backtest/engines/
agent/backtest/engines/base.py:815:    UNFILLED_PLAN_REASONS = (
agent/backtest/engines/base.py:834:            ``unfilled_plan_rejections`` (total) and
agent/backtest/engines/base.py:835:            ``unfilled_plan_rejections_by_symbol`` ...
agent/backtest/engines/base.py:841:            if reason not in self.UNFILLED_PLAN_REASONS:
agent/backtest/engines/base.py:846:            "unfilled_plan_rejections": total,
agent/backtest/engines/base.py:847:            "unfilled_plan_rejections_by_symbol": by_symbol,
```

As in October, the only `unfilled` match is `unfilled_plan_rejections` — pre-trade plan-rejection
accounting (a rebalance plan the engine could not take for `no_data`, `no_bar`, `execution_blocked`,
`invalid_price`, `zero_size`, `insufficient_capital`), not a resting-limit no-fill. The fill
function itself is unchanged:

```
$ sed -n '889,891p' agent/backtest/engines/base.py
    def execution_open(self, bar: pd.Series) -> float:
        """Return the normal market-fill price for a bar."""
        return float(bar.get("open", bar.get("close", 0)))
```

`base.py` changed a lot over the window (Argentina/BYMA engine, crypto-base classification,
sub-penny fill prices in `trades.csv`, config-key warnings), but none of it is limit-order, queue,
or trade-through logic. Blocker 1 stands.

### Trigger 2 — a capital-gains tax layer: **ABSENT**

```
$ grep -rniE "STCG|LTCG|capital[_ ]?gain" --include=*.py agent/ | wc -l
0
```

Zero hits repo-wide, source and tests alike. The broader search
(`grep -rniE "STCG|LTCG|capital[_ ]?gain|holding[_ ]period|short[_ ]term.*gain|long[_ ]term.*gain"`)
returns only VaR horizon-scaling in `agent/src/quantlib/risk.py` and one shadow-account
"median holding period" diagnostic — neither a tax. No short-term/long-term equity treatment, no
crypto VDA treatment. Blocker 2 stands.

### Trigger 3 — a Zerodha/Upstox connector, or an Indian connector gaining a live path: **FIRED on the letter (expanded), not on the purpose**

The connector directory list has grown. Indian-market connectors at HEAD:

```
$ for c in dhan shoonya zerodha mstock upstox; do \
    [ -d "agent/src/trading/connectors/$c" ] && echo "$c: PRESENT" || echo "$c: absent"; done
dhan: PRESENT
shoonya: PRESENT
zerodha: PRESENT
mstock: PRESENT
upstox: absent
```

Two things are new relative to the **authoritative** August pin, and one is new even relative to
October:

**(a) `zerodha/` (added in October, re-confirmed here) now carries a live profile set, but order
placement is still paper-only.** The config accepts `profile ∈ {paper, live-readonly, live}`, but
those richer profiles gate *reads*. `place_order` and `cancel_order` both still refuse any non-paper
config on the first statement:

```
$ sed -n '577,579p' agent/src/trading/connectors/zerodha/sdk.py
    cfg = config or load_config()
    if not cfg.is_paper:
        return {"status": "error", "error": _PAPER_ONLY_ERROR}
```

(`is_paper` is true only when the profile's environment is `paper`; `live`/`live-readonly` map to the
`live` environment, so both are refused by `place_order`.) The docstring is explicit: "Kite exposes
no sandbox, so this connector is structurally capped at paper … There is no live order path, by
design." Same reasoning as Dhan/Shoonya.

**(b) A new `mstock/` connector — Mirae Asset mStock, an Indian broker — is LIVE but READ-ONLY, and
both order entry points refuse before any network call.** Added in `ec87d3f4`
("feat(agent): add mStock read-only profile"), new since October's HEAD. It is the first Indian
connector that talks to the *real* account over the network (GET-only: holdings, net positions,
fund summary), so it is a more substantive "letter" hit than a paper simulator. But orders are
disabled in every environment:

```
$ sed -n '144,154p' agent/src/trading/connectors/mstock/sdk.py
def place_order(*args, config: MStockConfig | None = None, **kwargs):
    """Refuse every order before any network operation."""
    if config is None or config.environment != "paper":
        raise MStockAPIError("mStock order placement is disabled for every environment")
    raise MStockAPIError("mStock has no paper order implementation")
```

Its own `README-classification.md` states the boundary plainly: "It exposes no paper simulation or
live trading capability. A new order transport would require its own verified discriminator and
mandate gate." Its classification map pins `place_order`/`cancel_order` as WRITE (fail-closed), and
its profile withholds `account.read` because fund limits are not net equity.

**(c) Dhan and Shoonya are unchanged in substance** — both still refuse on the first statement of
`place_order` (`if not cfg.is_paper: return _PAPER_ONLY_ERROR`, dhan sdk.py:473, shoonya sdk.py:452),
though each gained some surrounding plumbing over the window.

**(d) No Upstox connector.**

**What this means for the verdict.** The trigger's second clause — "either Indian connector gaining
a live (non-paper) order path" — is the one tied to the blocker, and it is **still absent across all
four Indian connectors**. The evaluation's standing position ("there is no Indian execution to
replace", section 1) holds: SEBI algo-ID tagging, registered-static-IP origination, marketable-limit-
only placement, the order-rate governor and the broker failover remain ours to build regardless,
exactly as `TASKS.md` schedules. The hybrid question does not reopen.

---

## 2. Watched-path blob comparison (verified by sha, not inferred)

`git ls-tree <rev> -- <path>` blob shas at the authoritative pin vs HEAD. The "since Oct" column
flags paths that also moved relative to the unmerged October HEAD `18027a0`, to make clear what is
genuinely new this window.

| path | pin → HEAD | since Oct? | verdict |
|---|---|---|---|
| `agent/src/quantlib/multipletesting.py` | `d76ffed16e` → `3cfe11dd0e` | yes | **changed (+26/−8)** — first change to our DSR oracle; see §3.1 |
| `agent/src/quantlib/crossvalidation.py` | `be8d412174` → `e65b43e8bc` | yes | changed (+106/−30); see §3.2 |
| `agent/src/governance/ledger.py` | `e24e094563` → `420af028e3` | yes | changed; hash-chain hardening, see §3.3 |
| `agent/backtest/engines/india_equity.py` | `fd50f88148` → `b2b922d340` | yes | changed; cost/rule fixes, see §3.4 |
| `agent/backtest/engines/base.py` | `2c36ecdd16` → `61acfe55d2` | yes | changed; **not a fill model** (Trigger 1) |
| `agent/backtest/loaders/india_broker_loader.py` | `dd43d2ebf0` → `51d968ff46` | no (same as Oct) | changed since pin: Zerodha added to broker order (Oct) |
| `agent/backtest/loaders/yahoo_loader.py` | `eeae1b0ab2` → `ab8d9e2bf4` | yes | changed; Argentina/currency routing, not India PIT |
| `agent/backtest/loaders/yfinance_loader.py` | `7fe97b42ad` → `acb2809191` | yes | changed; incl. Oct dividend fix `auto_adjust=True` |
| `agent/backtest/loaders/yahoo_client.py` | `bfbc96d20b` → `66bd4653c7` | no (same as Oct) | changed since pin: Oct dividend-adjustment fix |
| `agent/src/factors/base.py` | `fa807aa98a` → `ebfcde5670` | yes | changed; NaN/tie hardening, OLS BETA/RESI — not a gap for us |

`agent/src/trading/connectors/dhan/sdk.py` (+40/−5) and `shoonya/sdk.py` (+31/−7) also changed over
the window; the paper-only guards are intact (§1c).

---

## 3. The standing question — "did they solve something we have ignored?"

Ranked by how much it bears on work Icarus already has scheduled. None changes the verdict; the
first two bear directly on our open finding **F12 (DSR / PBO / multiple-testing control, not yet
built)**, which is on our critical path and which `CLAUDE.md` §5 requires us to implement in-house.

### 3.1 The DSR oracle changed for the first time — a fail-loud fix worth mirroring

`agent/src/quantlib/multipletesting.py` — the module the evaluation named as our DSR/PBO oracle for
F12 — was **byte-identical at every prior watch run** (`d76ffed16e` from the original evaluation
through October). This month it changed (`3cfe11dd0e`), in a single commit `5983889e`
("fix(quantlib): reject non-finite schedule and Sharpe-summary inputs by name", +26/−8).

The fix makes `probabilistic_sharpe_ratio` and `expected_maximum_sharpe` **reject non-finite inputs
by name** (NaN or ±inf in `observed_sharpe`, `n_observations`, `benchmark_sharpe`, `skew`,
`kurtosis`, `n_trials`, `trial_sharpe_std`) instead of letting them flow through. The commit's own
comments state the bug it closes:

> Every check below is a comparison, and a comparison with NaN is False: without this admission, a
> NaN benchmark returned NaN as "confidence" and an infinite one returned a clean 0.0 or 1.0.

and, in `expected_maximum_sharpe`:

> NaN fails every comparison below and `norm.ppf(1 - 1/inf)` is inf: the first surfaces as a NaN
> bar, the second as an unbeatably infinite one, and `deflated_sharpe_ratio` reports both as an
> ordinary pass/fail verdict.

**Why this is the month's real answer to the standing question.** This is the exact failure mode a
gate is supposed to prevent: a degenerate moment (a NaN from an empty or constant return series, an
inf from a pathological input) silently producing a *plausible* confidence number and a clean
pass/fail, rather than refusing. It is not a gap in current Icarus code — **we have not built F12
yet** — but it is a concrete correctness requirement for when we do: our in-house DSR must fail loud
on non-finite moments, by name, rather than emit a verdict. When F12 is scheduled, this commit
belongs in our differential-test corpus alongside the formulas. Mirror the *behaviour*; the module
still never enters our production dependency list (`CLAUDE.md` §5).

### 3.2 The purge/embargo oracle improved again — and the three-run-old `group_purged` caveat is now addressed

`agent/src/quantlib/crossvalidation.py` changed +106/−30 across six commits over the window. The
substantive ones:

- `71a483d0` — multi-segment test sets: purge/embargo are now computed around **each contiguous test
  segment**, not around one span from first to last test index (the per-segment fix October first
  recorded; re-confirmed here from the authoritative pin).
- `a55dd201` — reject unordered label indices; `250ef746` — a label cannot end before its own
  observation starts; `b89c4e38` — skip walk-forward folds where purging empties the training set,
  as the splitter contract promises. These are fail-loud guards.
- `9befcbae` ("purge groups whose labels reach into the test block", 2026-10-04 — **new this
  window**, after October's HEAD).

That last commit **addresses the caveat that has been open on this watch list since the first run
(2026-08-21)**: `group_purged_kfold_splits` previously embargoed forward only and never purged train
rows backward (effectively `purged=0`), a leakage path for panels with multi-day labels. The current
docstring and code state that when `label_end_times` is supplied, "overlap removes a whole group;
embargo starts after the furthest test label ends", i.e. it now purges groups whose labels reach into
the test block. **Assessed by reading the code, not by running it** — but the long-standing caveat
appears resolved for the `label_end_times`-supplied path. When F12 is built, use *this* version of
`crossvalidation.py` as the purge/embargo and `detect_boundary_leakage` oracle.

As in October, our own design (operator decision D10 — the single fixed `seam_sessions` that replaced
a purge) means the per-segment and group-purge fixes matter chiefly for *combinatorial* splits we do
not use; they are reference improvements, not defects we are carrying.

### 3.3 The hash-chain ledger gained whole-history verification and crash-safety

`agent/src/governance/ledger.py` — the hash-chained, fsynced, append-only ledger whose *design* the
evaluation approved borrowing (two columns plus a `verify_chain` routine on top of the DB-level
append-only trigger we already have) — gained, over the window:

- `5c28d493` — the Windows byte-range-lock sentinel fix October flagged (relevant because operator
  decisions D24/D30 put our simulator host on Windows 11).
- `77fc417e` — "make archive ledger verification report corruption instead of crashing".
- `8079de92` — "verify the whole history before sealing a ledger segment".

All three are robustness properties to carry into our own `prev_record_hash` / `record_hash` /
`verify_chain` when the audit-log hash chain is built (scheduled after the next backtest): report
corruption as a result rather than an exception, and verify the full chain before sealing, not just
the tail. Not a gap in current code (chain not built yet); a checklist for when it is.

### 3.4 India cost/rule fixes — informational, our CostModel is separate

`agent/backtest/engines/india_equity.py` (+42/−20, three commits) fixed: stamp duty charged on the
**buy side of a short** (`773e5067`), the circuit-band check reading the **right band when covering a
short** (`d17f2ccb`), and India rules enforced through **composite (multi-market) state**
(`8ffdfc7a`). The first is a genuine SEBI-tariff-application nuance (stamp duty is buy-side; a short's
opening leg is a sell, its closing leg a buy) worth a glance against our `CostModel` when India
costs are next revisited — `CLAUDE.md` §2 flags SEBI tariffs as "verify at build". The composite-
state fixes are their multi-market plumbing and do not transfer to our single-market numpy panel.
Informational; no action implied.

### 3.5 Dividend adjustment (re-confirmed from August) and the survivorship half still absent

Re-confirmed from the authoritative pin, since this window's diff includes it: the Yahoo loader paths
now serve dividend-adjusted OHLC (`1fcab81d`, October — `yahoo_client.py` applies an `adjclose/close`
ratio; `yfinance_loader.py` uses `auto_adjust=True`). The evaluation predicted exactly this
("the practical gap here is most likely *dividend* adjustment"). It closes the **price-adjustment**
half of Blocker 3 only. The **survivorship / point-in-time-universe** half is still absent for India:

```
$ grep -rniE "survivorship|point.?in.?time|index.?member|constituent|delist" \
    --include=*.py agent/ | grep -iE "india|nse|nifty"
(no India hits; survivorship machinery is fundamentals/events + a US S&P-500 flag only)
```

Our invariant #14 (point-in-time data, no survivorship, back-adjustment for corporate actions)
requires both halves, and our `Panel` enforces the point-in-time half structurally. Taking their
India data layer would still be a regression. Not a gap for us.

### 3.6 Factor NaN/tie hardening — not a gap for us

`agent/src/factors/base.py` (NaN-policy hardening, OLS for Qlib BETA/RESI, backend-independent
`ts_argmax`/`ts_argmin` tie-breaking) did not change their cross-sectional `rank(axis=1,
method="average")` tie convention — the idea the evaluation borrowed for the already-closed DSL task
2g-3. Our typed DSL with parse-time refusal is ahead here. No action.

---

## 4. Recommendation

**No re-evaluation of the "keep building Icarus" verdict is warranted.**

1. Trigger 1 (fill model) and Trigger 2 (capital-gains tax) are both still absent; Blockers 1 and 2
   stand verbatim.
2. Trigger 3 fired again on its literal clause — a new live-but-read-only Indian connector (mStock)
   and a wider Zerodha profile set — but not on its purpose: all four Indian connectors (Dhan,
   Shoonya, Zerodha, mStock) refuse order placement before any network call, so there is still no
   Indian live-order path. "No Indian execution to replace" holds; the hybrid question stays closed.
3. On the standing question, the month's real content is that **our DSR oracle changed for the first
   time** — a fail-loud fix for non-finite moments — and the long-open `group_purged_kfold_splits`
   purge caveat is now addressed. Both bear on finding F12 (DSR/PBO, not yet built), neither is a gap
   in current Icarus code, and both are correctness requirements to carry into F12 when it is
   scheduled.

Things to carry forward into already-scheduled work, none urgent:

- **When finding F12 (DSR/PBO) is built:** require our in-house DSR to reject non-finite Sharpe-
  summary inputs by name (mirror `5983889e`), and use the current `crossvalidation.py` as the
  purge/embargo and boundary-leakage oracle (the per-segment and group-purge fixes are correct);
  the `group_purged_kfold_splits` caveat appears resolved but was assessed by reading, not running.
- **When the audit-log hash chain is built** (after the next backtest): report corruption rather than
  crashing, verify the whole chain before sealing, and avoid the Windows byte-range-lock sentinel bug
  (relevant on our D24/D30 Windows host).
- **When India costs are next revisited:** check stamp-duty application on the buy side of a short
  against our `CostModel` (`773e5067`).

Nothing in this run requires a code change to Icarus. The pin moves to `78fab6b3` (0.1.18,
2026-10-30). **Operator: reconcile the still-open, unmerged October PR (`vibe-watch/2026-10-01`)
against this one — this delta subsumes it (see §0).**

---

## 5. What I did and did not verify

- **Did:** blob-sha comparison of every watched path at the authoritative pin vs HEAD (and vs the
  October HEAD for continuity); the three triggers by direct grep with the commands quoted above;
  read the Zerodha and mStock order guards and the Dhan/Shoonya first-statement refusals; read the
  `multipletesting.py`, `crossvalidation.py`, `ledger.py` and `india_equity.py` diffs; re-confirmed
  the survivorship half of Blocker 3 is still absent for India.
- **Did not:** run any of their tests this month (the `multipletesting.py` change was assessed by
  reading the diff and its stated rationale, not by executing the 75-case corpus; the
  `group_purged_kfold_splits` purge resolution was likewise read, not run); make any network call to
  a broker; hold any venue credentials; verify Yahoo's Indian corporate-action accuracy; audit the
  factor modules.

*Scratch clone at `/tmp/vibe-watch-2026-11/repo`, outside this repo, treated as untrusted data and
not committed. Nothing from Vibe-Trading was copied into Icarus.*
