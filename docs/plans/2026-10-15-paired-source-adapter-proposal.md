# Next proposed unit: preserve daily signals and qualify M15 execution data

Proposal only; D55's approval covers the descriptive QA, not changes to engine
acceptance or benchmark semantics. No implementation is claimed here.

## Problem and resulting behavior

The current invented-data simulator proves daily/M15 identity by requiring the
daily bar to be exactly the aggregate of its M15 bars. Real official daily and
vendor intraday feeds have separate closing and capture conventions. The right
integration must preserve those separate meanings rather than alter official
prices or delete a check until data passes.

Build one source adapter and its engine integration, tested first on invented
records. Official NSE daily data continues to drive daily signals and the
point-in-time universe; M15 records drive modeled execution only. A separately
reviewed qualification binds every symbol/date mapping, adjustment basis and
calendar. The existing strict aggregate path remains for its existing fixtures.
An explicit separately qualified source-pair path may use distinct daily and
M15 records, while preserving all causal, complete-grid, fill and risk checks.

The qualification must bind independent evidence, exact daily/M15/action/lineage
digests, effective intervals and reviewer/approval identity. Both lanes must use
the same economic price basis for each symbol/date: cumulative split, bonus and
rights factors and a pinned dividend convention. A separate close-construction
rule never waives that compatibility. Require declared capture/session rules
and deterministic cross-source invariants for overlapping content, including
action-normalized M15 extrema contained within official daily extrema wherever
the pinned source/session definitions support that relationship. Any volume
relationship must also be source-supported. An unsupported required relationship
refuses; a price match alone cannot certify the source pair.

Unknown or conflicting lineage, basis, calendar, quarantine and coverage
remain typed refusals with residual inventory preserved. Keep every requested
name and session in the disposition report; do not form a survivors-only panel.
Cross-source differences remain immutable diagnostics, with no blanket numeric
tolerance and no price repair.

## Acceptance tests

- A fully mapped invented daily/M15 pair with separate declared closing
  conventions preserves daily values exactly and uses M15 prices for fills.
- A missing or wrong effective-date security mapping, conflicting adjustment,
  duplicate source identity, changed qualified bytes or unqualified declaration
  refuses before evaluation.
- Equal declared bases with impossible cross-source containment refuse. A
  different daily close passes only under a pinned closing convention with
  every other applicable reconciliation invariant still satisfied.
- Missing M15 bars, late liquidity inputs, quarantined data and special-session
  conflicts retain their existing refusal behavior. No holding disappears.
- Existing synthetic exact-aggregate fixtures and accounting regressions pass.
- An M15 fill remains an interval. It cannot receive an exact point benchmark
  return, and the final Nifty M15 candle cannot become an official daily close.

Do not include a new interval-benchmark return rule in this build. That is a
separate pre-registered methodological decision: define comparison intervals or
bounds, source availability and cost/tax treatment, then review before any
strategy results. Until then, interval benchmark results stay unavailable.

## Actual-data prerequisites and stopping point

Software tests may use invented fixtures. Admitting the downloaded snapshot
still needs source evidence for adjustment, dated security lineage, regular and
special sessions, archival use and causal benchmark availability. The adapter
cannot certify these itself. Full-range resource qualification follows a
concrete bundle; actual strategy evaluation still needs a pinned authorization
and activated trial ledger. No lockbox use, thresholds change or live orders.
