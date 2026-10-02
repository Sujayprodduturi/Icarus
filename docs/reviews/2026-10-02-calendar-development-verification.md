# Independent calendar development verification

Date: 2026-10-02. Verdict: VERIFIED COMPLETE FAILURE. Confirmation must remain unopened and undrawn.

The preceding independent aggregation successfully checked all 9216 retained paths and 26624 metric results: all 52 cell counters, 316 reported criteria and 280 formal criteria match terminal.json exactly. Frozen source manifest matches current files at commit 51559673da575b976d81bc2b83567ffddeabf554.

Methods: separately decoded exact Decimal coefficient/base64 tuples; Fraction comparisons with independently enumerated truth constants; both precision width predicates (win 1/5, raw/paired 1/50); closed coverage endpoints; strict tails; precision and signed detection. Exact binomial cutoffs computed using direct choose(N,j) integer power sums at eta=1/5600, rather than production recurrence or judge. Compared every criterion field, including point versus bound decisions, coarse bound values, impossible cutoffs and unassessable zero denominators.

The initial independent check used an incorrect win width 1/10, caught immediately against P1:64:win; corrected to the frozen 1/5 and reran full aggregation successfully. The initial independent transcript omitted the canonical trailing newline, caught at P1:64:0; corrected to the documented byte encoding before all selected transcript checks passed. Neither was a production defect; no study artifacts or source were changed.

No new seeds, experimental histories, confirmation seal reads, or source changes. Selected existing seed-address replay is verification only.

Unchanged slow-reference calculations and independently implemented SHA256 lane/rejection transcript reconstruction match all 20 selected retained paths: each family replicate zero plus first observed categories. Categories: covered, insufficient_precision, uncovered, zero_count_slice, zero_full_count.

Selected addresses: P1:64:0, P1:64:20, P1:128:0, P2:64:0, P2:128:0, P3:64:0, P3:128:0, P4:64:0, P4:128:0, P5:64:0, P5:128:0, P6:64:0, P6:128:0, P7:64:0, P7:128:0, L1:64:0, L1:64:9, L1:128:0, E+:128:0, E-:128:0.

Formal point failures: {"conditional_coverage": 46, "joint_coverage": 46, "lower_tail": 45, "precision": 12, "upper_tail": 45}. No emission or effect-detection point failures. All 46 formal cells fail overall.

The extensive observed finite-sample undercoverage rejects this frozen candidate. Passing emission, precision or detection does not rescue coverage failure. Confirmation remains prohibited; no market eligibility, product adoption or post-result alteration of this attempt is justified.

## Artifact SHA256

- claim.json: `47c2885f0672d6b7edf711dc8225b1f059cd075bf518d649c7c6497647a5be30`
- paths.jsonl: `44adc7a914d2ed853bbe2d5d59848fdd305c56850f2f8a10098ed63f89f75e15`
- terminal.json: `b9931a44708292e2f7826dc46bb6c0f1d4261bdae769083d1f60fde72dbf89ef`

## Independently reproduced counts

R=512 each. A arithmetic, C covered, L/U tails, P precision, D correct-sign effect detection. L1 descriptive only. These retained values were checked against the separate full aggregation.

| Cell | A | C | L | U | P | D |
|---|---:|---:|---:|---:|---:|---:|
| E+:128:raw | 512 | 411 | 52 | 49 | 512 | 512 |
| E+:128:synthetic_excess | 512 | 432 | 41 | 39 | 512 | 512 |
| E-:128:raw | 512 | 422 | 48 | 42 | 512 | 512 |
| E-:128:synthetic_excess | 512 | 426 | 35 | 51 | 512 | 512 |
| L1:128:raw | 0 | 0 | 0 | 0 | 0 | 0 |
| L1:128:synthetic_excess | 0 | 0 | 0 | 0 | 0 | 0 |
| L1:128:win | 0 | 0 | 0 | 0 | 0 | 0 |
| L1:64:raw | 0 | 0 | 0 | 0 | 0 | 0 |
| L1:64:synthetic_excess | 0 | 0 | 0 | 0 | 0 | 0 |
| L1:64:win | 0 | 0 | 0 | 0 | 0 | 0 |
| P1:128:raw | 512 | 426 | 50 | 36 | 512 | 0 |
| P1:128:synthetic_excess | 512 | 427 | 42 | 43 | 512 | 0 |
| P1:128:win | 512 | 423 | 38 | 51 | 512 | 0 |
| P1:64:raw | 512 | 391 | 55 | 66 | 512 | 0 |
| P1:64:synthetic_excess | 512 | 412 | 45 | 55 | 512 | 0 |
| P1:64:win | 512 | 386 | 46 | 80 | 485 | 0 |
| P2:128:raw | 512 | 431 | 48 | 33 | 512 | 0 |
| P2:128:synthetic_excess | 512 | 434 | 46 | 32 | 512 | 0 |
| P2:128:win | 512 | 420 | 52 | 40 | 457 | 0 |
| P2:64:raw | 512 | 392 | 69 | 51 | 512 | 0 |
| P2:64:synthetic_excess | 512 | 407 | 66 | 39 | 512 | 0 |
| P2:64:win | 512 | 388 | 80 | 44 | 288 | 0 |
| P3:128:raw | 512 | 400 | 54 | 58 | 506 | 0 |
| P3:128:synthetic_excess | 512 | 404 | 49 | 59 | 512 | 0 |
| P3:128:win | 512 | 390 | 49 | 73 | 119 | 0 |
| P3:64:raw | 512 | 335 | 101 | 76 | 459 | 0 |
| P3:64:synthetic_excess | 512 | 343 | 94 | 75 | 511 | 0 |
| P3:64:win | 512 | 339 | 85 | 88 | 81 | 0 |
| P4:128:raw | 512 | 417 | 52 | 43 | 512 | 0 |
| P4:128:synthetic_excess | 512 | 434 | 32 | 46 | 512 | 0 |
| P4:128:win | 512 | 434 | 42 | 36 | 462 | 0 |
| P4:64:raw | 512 | 393 | 60 | 59 | 507 | 0 |
| P4:64:synthetic_excess | 512 | 411 | 52 | 49 | 512 | 0 |
| P4:64:win | 512 | 380 | 66 | 66 | 300 | 0 |
| P5:128:raw | 512 | 426 | 24 | 62 | 512 | 0 |
| P5:128:synthetic_excess | 512 | 398 | 12 | 102 | 512 | 0 |
| P5:128:win | 512 | 437 | 32 | 43 | 454 | 0 |
| P5:64:raw | 512 | 406 | 41 | 65 | 506 | 0 |
| P5:64:synthetic_excess | 512 | 395 | 26 | 91 | 510 | 0 |
| P5:64:win | 512 | 407 | 57 | 48 | 292 | 0 |
| P6:128:raw | 512 | 414 | 71 | 27 | 512 | 0 |
| P6:128:synthetic_excess | 512 | 402 | 97 | 13 | 512 | 0 |
| P6:128:win | 512 | 423 | 51 | 38 | 458 | 0 |
| P6:64:raw | 512 | 411 | 75 | 26 | 502 | 0 |
| P6:64:synthetic_excess | 512 | 388 | 100 | 24 | 512 | 0 |
| P6:64:win | 512 | 401 | 63 | 48 | 310 | 0 |
| P7:128:raw | 512 | 365 | 75 | 72 | 506 | 0 |
| P7:128:synthetic_excess | 512 | 386 | 68 | 58 | 512 | 0 |
| P7:128:win | 512 | 401 | 62 | 49 | 415 | 0 |
| P7:64:raw | 512 | 299 | 88 | 125 | 500 | 0 |
| P7:64:synthetic_excess | 512 | 330 | 71 | 111 | 508 | 0 |
| P7:64:win | 512 | 343 | 77 | 92 | 348 | 0 |

Scope: all retained counts and judgments independently recomputed; slow-reference and independent stream reconstruction cover only the selected paths. This is not independent slow-reference recalculation of all 9216 paths. No market or asymptotic generalization follows.
