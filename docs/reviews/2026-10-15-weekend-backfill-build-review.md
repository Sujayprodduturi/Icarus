# Weekend archive discovery — build review

Status: **LOCAL SOFTWARE VERIFIED; POSTCOMMIT REVIEW GO**.

The data-qualification review found that the legacy archive scanner enumerates
only weekdays. A published Saturday or Sunday special session is excluded
before the source is queried. The approved repair enumerates every calendar
date in the requested inclusive range, retaining chronological order and the
existing empty result for reversed ranges. It changes discovery coverage,
not the criteria for admitting a qualified historical calendar.

## Evidence and boundaries

- Root reproduced the original bug before implementation: five failures and
  one pass in the new invented-source tests. Both Saturday and Sunday published
  sessions were omitted; a weekend transient error was also never encountered.
- Sandboxed test startup stalled before producing results. Those attempts were
  stopped and are not evidence. The actual RED check ran outside the restriction
  and completed in 0.61 seconds without any network or broker call.
- The test cases cover published Saturday/Sunday sessions, absent weekends,
  unchanged weekday behavior, inclusive/reversed bounds and transient failures.
- Existing archive-absence closure inference remains a legacy derived label,
  not authoritative exchange evidence. No numeric threshold or canonical timed
  calendar rule changes. Old caches are not rewritten, regenerated or upgraded.
- No downloader, real-price inspection, strategy, trial ledger, broker,
  inference or lockbox evaluation is launched by this repair.

The existing 2,962-date pre-2023 cached axis still excludes all weekends after
this software repair. Its source completeness remains unqualified. Dated NSE
session notices and a separately authorized, bounded acquisition/rebuild are
needed before any replacement dataset can be admitted.

## Completion proof

All completion checks below passed. The independently reintroduced weekday
filter failed both Saturday/Sunday assertions (two failures in 1.94 seconds).
Finally, original bytes and LF/CRLF counts were restored exactly; six focused
positives passed in 0.69 seconds with a separate fresh bytecode cache.
Receipt SHA-256: 71a98e2afe0dde4c25ad4120cdacd571421eba3de6cfab03b93091edf0ece3b2.
The reviewer relinquished temporary mutation authority.

The reviewed repair is committed as `6b71533`. Ordered root simplification
and independent formal code/security review are GO. Root's final gate passes
75 tests in 9.31 seconds; default strict typing passes 196 files, and global
Ruff lint/format passes (443 files). Independent reviewer passes 54 relevant
checks. The product hashes are:

| File | SHA-256 |
|---|---|
| `icarus/agents/data/backfill.py` | `65977a7bf94955a2d17d0e7f244ea4fc84afc684f633e4949a71a2590a53e79c` |
| `scripts/backfill_bhavcopy.py` | `701f43ac31c2847de1eac709d0bdb2b0743c1e0e227726207822286832e839e9` |
| `tests/unit/test_backfill_candidates.py` | `45924b12f6c4fe655fdebb36a6207e6557c7010ee36bd5d962a41c77bacad710` |