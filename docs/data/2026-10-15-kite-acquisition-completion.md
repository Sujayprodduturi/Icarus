# Kite historical collection — 2026-10-15

## Completion report

Run `historical-2011-2022-v1` ended with `COMPLETED_WITH_REJECTIONS`.
The worker and proxy are no longer running. This is finished raw collection,
not source qualification or a strategy test.

| Requested work | Reported result |
|---|---:|
| Historical stock/index names requested | 694 |
| Names resolved by the vendor master | 544 |
| Unresolved names retained as gaps | 150 |
| Planned/resolved-symbol chunks | 25,024 |
| Accepted chunks | 19,938 |
| Empty chunks | 4,760 |
| Quarantined chunks | 326 |

The planned request count independently matches `544 * 46 = 25,024`.
Accepted and empty coverage contains 24,698 rows and the rejection list contains
326 rows. The quarantines comprise 321 `NON_POSITIVE_OHLC` and five
`INVALID_OHLC_ENVELOPE` chunks. Those are validator reason codes, not a vendor
explanation of the underlying cause. Empty responses are unknown coverage, not
verified holidays or listing dates. Missing current-master mappings do not prove
that all 150 names are delisted.

Daily request coverage is 2011–2022; M15 request coverage is 2015–2022. Request
completion does not establish complete observed bars inside those ranges.
Two successful preflight history artifacts and the instrument master are separate
from the 25,024 planned full-range chunks.

Final report: `var/kite-history/download/historical-2011-2022-v1/report.json`;
SHA-256 `43b80fc9e42387b978622676c15ce9c69c564772e006f9627a627bc729f429e0`.
Requested-list SHA-256 remains
`f29a40682f220eb3dce723a1d32ebdd1fc59baa8d96a3d23db7b74484c8739bf`.
Downloaded records, request lists and detailed reports remain git-ignored.

## Verification and next step

Independent metadata-only reconciliation passes: every resolved identifier has
exactly the 46 expected nonoverlapping request ranges; requested/resolved/missing
sets are disjoint and exhaustive, NIFTY50 is included, and every rejection and
coverage row matches its manifest. All 25,027 request archives passed strict
checkpoint/raw-byte hash verification, covering 1,327,365,083 raw bytes. A sorted
external content snapshot indexes 50,056 files. Root independently matched three
raw-file hashes, the report/receipt/index hashes and a fresh complete path/size
inventory; no extra, missing, reparse or symlink files were found. No price
records were decoded or strategies evaluated for this completion check.

The first full audit read found no raw mismatch, but its final expected-success
counter omitted the instrument master. That failed attempt is preserved as
`first-pass-failure.json` and is not claimed PASS. The corrected second full pass
completed with a successful bound index and receipt; no metadata-only replacement
was used as proof of raw hashes. This is a content snapshot, not physical
write protection, a backup, vendor authentication or source qualification.

Audit receipt: `var/verification/2026-10-15/kite-completion/audit-receipt.json`,
SHA-256 `04a5241eb7449d81d50906383239d5c18f933ca3e52541652339d9623e99a991`.
Snapshot: `var/verification/2026-10-15/kite-completion/content-snapshot-index.jsonl`,
SHA-256 `86aae96d13a4046c4b0f6ba08b6e97e2bcf1b1ca4b2f834b44a767ce089214f0`.

Independent review: `var/kite-review/completion-20261015/completion-review.json`,
SHA-256 `6086c80699bc5636ef867781b2b9236dd61583ac989b1421523162ec6944a5b5`.

Coverage-health review confirms every resolved name has at least one nonempty
accepted chunk; 193 resolved names have at least one rejected chunk and remain
in the denominator. NIFTY50 has 13 accepted daily and 33 accepted M15 chunks,
with no empty or rejected chunks. Its first accepted M15 timestamp is 2015-01-09;
compare that with the requested 2015-01-01 start during source/calendar review.
These metadata checks do not establish continuous observed-bar coverage.
Health receipt SHA-256:
`11ce2712728d54f14e97f3a1e4c422beff940d1a8d17639ba435005425cd789a`.

Hosted CI and resource checks both succeeded for `b98f442` (runs 38579488811 and
38579489081), as did both checks for runtime source `0c6060d` (38579163028 and
38579162957). These are software gates, not data-quality/source certificates.

Before simulation, retain an external content snapshot, resolve or explicitly
account for missing and rejected inputs, independently qualify PIT membership,
corporate actions, calendar, opening liquidity, price/adjustment and timestamp
semantics, licence and source-specific benchmark policy, then prepare the
canonical bundle. Do not substitute surviving names or accept bad price fields.
Actual strategy evaluation/ledger activation, inference, promotion, live orders
and lockbox evaluation remain held. `source_qualified=false` in the final report
is intentional and remains controlling.
