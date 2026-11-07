# Vibe-Trading watch — delta for 2026-10-01

**Monthly watch run against `docs/reviews/2026-08-20-vibe-trading-evaluation.md` section 9.**

- **Pin at start of run:** `HKUDS/Vibe-Trading` @ `1907e47d`, version 0.1.14 (2026-08-21).
- **HEAD this run:** `18027a0c` (2026-09-30), version **0.1.16**.
- **999 commits** since the pin — a very active two months.
- **Scratch clone** lived in `/tmp` outside this repo and was treated as untrusted data; nothing was copied or vendored. No file in it addressed me as an agent.

**One-line verdict: the "keep building Icarus" verdict from 2026-08-20 stands, unchanged.** One
watch trigger fired on its *literal* text — a Zerodha connector now exists — but not on its
*purpose*, because that connector is structurally paper-only and adds no Indian live-order path. The
other two triggers are still absent. Two watched paths changed in ways worth remembering for work we
have already scheduled, but neither opens a gap in Icarus that was not already closed or planned.

Why a delta doc exists at all for a verdict that did not move: the watch list's output rule writes a
file whenever a trigger fires *or* watched paths change. Both happened. A quiet month writes nothing;
this was not a quiet month, even though the conclusion is quiet.

---

## 1. The three re-evaluation triggers — each tested with the exact command

### Trigger 1 — a real limit-order fill model in `agent/backtest/engines/`: **ABSENT**

The fill is still next-bar open × a slippage constant; no queue position, no trade-through test, no
no-fill outcome. Blocker 1 of the evaluation (fill model always fills at the open) stands.

```
$ grep -rniE "queue|unfilled|trade_through|trade-through|no_fill|no-fill" agent/backtest/engines/
agent/backtest/engines/base.py:758:    UNFILLED_PLAN_REASONS = (
agent/backtest/engines/base.py:777:            ``unfilled_plan_rejections`` (total) and
agent/backtest/engines/base.py:789:            "unfilled_plan_rejections": total,
  ... (5 hits, all the same symbol)
```

The only match is `unfilled_plan_rejections`, and reading it (base.py around line 758) shows it is
**pre-trade plan-rejection accounting**, not a resting-limit no-fill: it counts opening plans the
engine *wanted* but could not take for reasons `no_data`, `no_bar`, `execution_blocked`,
`invalid_price`, `zero_size`, `insufficient_capital` (their issue #1235 — a sleeve that never clears
one lot was silently dropping out of the book). The word "unfilled" there means "the plan was
rejected before execution", not "a limit order rested and price never traded through it".

The fill function itself is unchanged:

```
$ sed -n '832,834p' agent/backtest/engines/base.py
    def execution_open(self, bar: pd.Series) -> float:
        """Return the normal market-fill price for a bar."""
        return float(bar.get("open", bar.get("close", 0)))
```

`agent/backtest/engines/base.py` grew by +478/−32 lines, but the change is plan-fitting and
rejection accounting (`_fit_rebalance_opens`, `_plan_rejection_metrics`, `_on_plan_rejected`,
`evaluation_start_index`) — the engine scaling a rebalance to fit available capital and recording
what it could not take. No limit-order, queue, or trade-through vocabulary appears on the `+` side.

### Trigger 2 — a capital-gains tax layer: **ABSENT**

```
$ grep -rniE "STCG|LTCG|capital[_ ]?gain" --include=*.py agent/ | wc -l
0
```

Zero hits repo-wide, source and tests alike. A broader search
(`grep -rniE "STCG|LTCG|capital[_ ]?gain|holding[_ ]period|short[_ ]term.*gain|long[_ ]term.*gain"`)
returns only VaR horizon-scaling in `agent/src/quantlib/risk.py` ("holding period in periods") and
one shadow-account diagnostic ("median holding period"), neither of which is a tax. There is still no
short-term/long-term equity treatment and no crypto VDA treatment. Blocker 2 stands.

### Trigger 3 — a Zerodha/Upstox connector, or an Indian connector gaining a live path: **PARTIAL — fired on the letter, not the purpose**

```
$ ls -d agent/src/trading/connectors/zerodha agent/src/trading/connectors/upstox
agent/src/trading/connectors/zerodha
ls: cannot access 'agent/src/trading/connectors/upstox': No such file or directory
```

A **`zerodha/` connector directory is new** since the pin (added in their commit `bf3f3868`,
"feat(broker): add Zerodha Kite Connect support for Indian equities"). There is no `upstox`
connector. So the trigger's first clause — "a Zerodha or Upstox connector in
`agent/src/trading/connectors/`" — is literally satisfied.

But the trigger's second clause — "either Indian connector gaining a live (non-paper) order path" —
is **absent**, and that is the clause tied to the blocker. The Zerodha connector is read-path plus a
locally simulated paper fill, structurally capped exactly as Dhan and Shoonya are. Its
`place_order` refuses any non-paper config on the first line:

```
$ sed -n '557,578p' agent/src/trading/connectors/zerodha/sdk.py
def place_order(... ) -> dict[str, Any]:
    """Place a PAPER-ONLY order on Zerodha (simulated locally).

    Kite exposes no sandbox, so this connector is structurally capped at paper:
    the very first check refuses any non-paper config. There is no live order
    path, by design.
    """
    cfg = config or load_config()
    if not cfg.is_paper:
        return {"status": "error", "error": _PAPER_ONLY_ERROR}
```

Their reasoning matches Dhan/Shoonya and matches the evaluation's own account of why those two are
paper-only: a Kite access token reaches the real account with no runtime paper/live discriminator,
so rather than trust a config flag with real money they expose no live path at all. The Dhan and
Shoonya hard guards are themselves unchanged (`if not cfg.is_paper: return _PAPER_ONLY_ERROR`, still
the first statement of each `place_order`).

**What this means for the verdict.** The evaluation's standing note — "there is no Indian execution
to replace" (section 1) — is still true. A read-only, paper-capped Zerodha bridge does not give
Vibe-Trading a live Indian order path, which is the blocker this trigger protects. So the hybrid
question the 2026-08-20 evaluation argued against does not need re-arguing on this account: SEBI
algo-ID tagging, static-IP origination, marketable-limit-only placement and the rest remain ours to
build regardless, exactly as scheduled. The connector is wired into the read-side broker bridge —
`agent/backtest/loaders/india_broker_loader.py` now prefers Zerodha → Shoonya → Dhan for *historical
bars only*.

---

## 2. Watched-path blob comparison (verified by sha, not inferred)

`git ls-tree <rev> -- <path>` blob shas at the pin vs HEAD:

| path | pin → HEAD | verdict |
|---|---|---|
| `agent/src/quantlib/multipletesting.py` | `d76ffed16e` → `d76ffed16e` | **byte-identical** — our DSR/PBO oracle is unchanged |
| `agent/src/quantlib/crossvalidation.py` | `be8d412174` → `1e33f07a53` | changed (+63/−26) |
| `agent/src/governance/ledger.py` | `e24e094563` → `8ece74049b` | changed (+4/−4) |
| `agent/backtest/engines/india_equity.py` | `fd50f88148` → `e6c18c24b6` | changed (+42/−20) |
| `agent/backtest/engines/base.py` | `2c36ecdd16` → `2f8b8a2fe9` | changed (+478/−32) — not a fill model (see Trigger 1) |
| `agent/backtest/loaders/india_broker_loader.py` | `dd43d2ebf0` → `51d968ff46` | changed (+17/−7) — Zerodha added to broker order |
| `agent/backtest/loaders/yahoo_loader.py` | `eeae1b0ab2` → `ffcf741115` | changed (+23/−11) |
| `agent/backtest/loaders/yfinance_loader.py` | `7fe97b42ad` → `8cbc3d4a29` | changed (+40/−7) |
| `agent/src/factors/base.py` | `fa807aa98a` → `4cd3a3e1ec` | changed (+45/−1) |

`agent/backtest/loaders/yahoo_client.py` (not in the watch table, but named in Blocker 3 as the file
that ignored `adjclose`) also changed, +59/−12 — see section 3.1.

---

## 3. The standing question — "did they solve something we have ignored?"

Three answers, ranked by how much they bear on work Icarus already has scheduled. None changes the
verdict; two are worth carrying into the relevant task when it comes up.

### 3.1 Dividend adjustment — they closed the half of Blocker 3 the evaluation predicted they would

This is the most substantive change of the month. Blocker 3 of the evaluation said the Indian price
feed was neither point-in-time nor dividend-adjusted, and specifically that `yahoo_client.py` read
`indicators.quote[0]` and "never touches the `adjclose` array", while `yfinance_loader.py` called
`yf.download(..., auto_adjust=False)`. Both are now fixed (their commit `1fcab81d`, "fix(backtest):
serve adjusted prices on the Yahoo loader paths"):

- `yahoo_client.py` now requests `events=div,splits`, reads the `adjclose` series, and multiplies
  OHLC by an `adjclose/close` ratio per bar (volume left raw), with a guard that falls back to raw
  when the ratio is missing or outside `[0.01, 100]`. Its own comment states the intent plainly:
  "every ex-dividend gap books as a fake loss. adjclose/close is therefore the dividend factor
  alone … applying it to OHLC brings this source to the same qfq caliber as eastmoney/tencent."
- `yfinance_loader.py` flipped to `auto_adjust=True` ("Adjusted OHLC like every other loader on the
  chain … volume stays raw on both sides").

The evaluation called this exactly: "the practical gap here is most likely *dividend* adjustment —
price-return where we want total-return". They have now closed it.

**Why this does not move the verdict, and is not a gap for us.** Icarus is already ahead on this
axis: our panel is dividend/corporate-action back-adjusted *and* structurally point-in-time, enforced
by `Panel`. Vibe-Trading has closed the *price-adjustment* half of Blocker 3 but **not the
survivorship / point-in-time-universe half** — I confirmed there is still no historical NSE index
membership and no delisted-symbol reconstruction for India
(`grep -rniE "survivorship|point.?in.?time|index.?member|constituent|delist" --include=*.py agent/`
returns point-in-time machinery only for *fundamentals* and *events*, plus a US S&P-500
`survivorship_bias` metadata flag — nothing that reconstructs a tradable Indian universe on a past
date). Our invariant #14 (point-in-time data, no survivorship, back-adjustment for corporate
actions) requires both halves, so taking their India data layer would still be a regression.

**What I cannot verify and am not claiming:** how well Yahoo's `adjclose` handles Indian corporate
actions specifically (bonus issues, demergers). The adjustment *mechanism* now exists; its
correctness for Indian names is Yahoo's to get right and is not answerable from this repo — the same
caveat the original evaluation recorded.

### 3.2 The hash-chain ledger gained a Windows fix — and Windows is now *our* host

`agent/src/governance/ledger.py` is the hash-chained, fsynced, append-only ledger the evaluation
approved borrowing the *design* of (two columns plus a `verify_chain` routine, on top of the
DB-level append-only trigger we already have). It changed +4/−4 in their commit `5c28d493`
("fix(windows): cross-platform locks, path handling, and test robustness"). The fix:

> Windows byte-range locks are valid beyond EOF, so an empty ledger is locked at offset 0 WITHOUT
> writing anything. Writing a `b"\0"` sentinel made the chain walk see a malformed line 0 and refuse
> every first append with `LedgerCorruptionError`.

This is worth keeping because the ground under it shifted on *our* side since the evaluation was
written. The evaluation scheduled adopting this hash-chain design "after the next backtest". Since
then, operator decisions D24 and D30 (recorded in `docs/STATE.md` section 0) selected a **Windows 11**
PC as the host for local simulator and tests. If and when we implement our own `prev_record_hash` /
`record_hash` / `verify_chain`, this is a concrete Windows file-locking footgun to avoid: do not
bootstrap a Windows byte-range lock by writing a sentinel byte into the file a hash chain then has to
parse. This is the clearest instance this month of "something we would otherwise have hit" — not a
gap in our current code (we have not built the chain yet), but a landmine on the exact path we
scheduled.

### 3.3 The purge/embargo oracle improved; the DSR oracle did not change

`agent/src/quantlib/crossvalidation.py` (+63/−26) is one of the two files the evaluation earmarked as
a **test oracle** for finding F12 (the DSR/PBO/multiple-testing guard that is on our critical path
before strategies are pre-registered, and that we must implement in-house per CLAUDE.md section 5).
The change rewrites `_apply_purge_and_embargo` and `detect_boundary_leakage` to purge and embargo
around **each contiguous test segment** rather than around one span from the first to the last test
index. For a combinatorial-purged split whose test set is several disjoint blocks, the old code
treated the whole thing as one block and over-purged the training rows in the gaps between blocks;
the new code is correct per-segment. It also adds fail-loud guards: a non-monotonic or non-unique
label-end index is rejected, a label that ends before its own observation starts is rejected, and
every split function now raises rather than silently yielding a fold whose training set purge+embargo
emptied.

Relevance, stated without overstating: when F12 is scheduled, use *this* version of
`crossvalidation.py` as the oracle, not the pinned one — the per-segment purge is a genuine
correctness fix, and `detect_boundary_leakage` (a test we do not have) is now sharper. But the
per-segment fix matters chiefly for *combinatorial* splits, and our design (decision D10) replaced
the purge with a single fixed `seam_sessions` on a walk-forward, so this is a reference improvement,
not a defect we are carrying. **The DSR oracle itself, `multipletesting.py`, is byte-identical to the
pin** (sha `d76ffed16e` both ends), so there is no DSR fix to mirror this month.

One caveat the first watch run (2026-08-21) raised remains open: the newer `group_purged_kfold_splits`
reportedly yields `purged=0` and embargoes forward only. This month's change added an empty-train
guard to that function but did not alter its purge count, so that caveat stands — verify before use.

### 3.4 Minor — an India T+1 fix that rhymes with our own open finding

`agent/backtest/engines/india_equity.py` (+42/−20) refactored `can_execute` into a shared
`india_can_execute(state, rules, …)` so that in a composite (multi-market) run, the T+1
delivery check reads the *composite* engine's shared positions instead of the India sub-engine's
always-empty ones — without it, same-day delivery sells slipped through (their issue #1292). It also
threads `position_direction` into the circuit-band check so a short-covering buy is tested against
the upper band, not the lower. This is their composite-engine plumbing and does not transfer to our
single-market panel, but the *class* of bug — an execution-permission check reading stale state so a
sell is wrongly allowed — rhymes with our open audit finding F47 ("`tradable` does not stop an exit,
only an entry"). Informational only; no action implied beyond noting the resonance when F47 is
scheduled.

`agent/src/factors/base.py` (+45/−1) hardened NaN policy (a new `observed_over` helper so a
comparison or `np.fmin`/`np.fmax` cannot turn a windowed input's gap into a false verdict; their
issues #1463/#1452). It did **not** change their cross-sectional tie/rank convention
(`rank(axis=1, method="average", …)`), which the evaluation borrowed as an idea for the already-closed
task 2g-3. Our typed DSL with parse-time refusal is arguably ahead here; not a gap for us.

---

## 4. Recommendation

**No re-evaluation of the "keep building Icarus" verdict is warranted.** Stated against the three
triggers and the standing question:

1. Trigger 1 (fill model) and Trigger 2 (capital-gains tax) are both still absent; Blockers 1 and 2
   stand verbatim.
2. Trigger 3 fired on its literal first clause (a Zerodha connector now exists) but not on its
   purpose: the connector is structurally paper-only, so there is still no Indian live-order path and
   the "no Indian execution to replace" position is intact. The hybrid question does not reopen.
3. On the standing question, the month's real content is that they closed the *dividend-adjustment*
   half of Blocker 3 — which the evaluation predicted and on which we are already ahead (we also do
   the survivorship/point-in-time half they still lack). Nothing here is a capability we have ignored.

Two things to carry forward into already-scheduled work, neither urgent:

- **When the audit-log hash chain is built** (scheduled after the next backtest), avoid the Windows
  byte-range-lock sentinel bug their `5c28d493` fixed — relevant now that D24/D30 put us on Windows.
- **When finding F12 (DSR/PBO) is built**, use the current `crossvalidation.py` as the purge/embargo
  and boundary-leakage oracle (the per-segment fix is correct), while remembering the DSR oracle
  `multipletesting.py` is unchanged and the `group_purged_kfold_splits` `purged=0` caveat from
  2026-08-21 is still open.

Nothing in this run requires a code change to Icarus. The pin moves to `18027a0c`.

---

## 5. What I did and did not verify

- **Did:** blob-sha comparison of every watched path; the three triggers by direct grep with the
  commands quoted above; read the Zerodha, Dhan and Shoonya `place_order` guards; read the
  `yahoo_client` adjustment code and the `crossvalidation`/`ledger`/`india_equity`/`factors` diffs in
  full; confirmed the survivorship half of Blocker 3 is still absent.
- **Did not:** run any of their tests this month (the evaluation ran the two borrow-candidate
  modules once; I did not re-run them — `multipletesting.py` is byte-identical so its 75-case result
  carries over, and `crossvalidation.py` changed but I assessed it by reading, not execution); make
  any network call to a broker; hold any venue credentials; verify Yahoo's Indian corporate-action
  accuracy; audit the 462 factor modules.

*Scratch clone at `/tmp/vibe-watch/repo`, outside this repo, treated as untrusted data and not
committed. Nothing from Vibe-Trading was copied into Icarus.*
