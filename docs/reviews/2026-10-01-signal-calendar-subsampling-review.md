# Calendar ratio subsampling design review

Date: 2026-10-01. Entry source c0ca734c92a3642ff83e575fee827ef602b39d32. Scope: operator-D39-authorized design and review only.

Reviewed [candidate design](../plans/2026-10-01-signal-calendar-subsampling-design.md), final SHA256 `1410dd365326b59a968c1e130f9e02d0b72f52f8f85ba5f7669b164bdc940bde`.

## Independent reviews

GPT-6 Astra, medium effort: APPROVE for bounded design, no mathematical/scope blocker. Independently checked the ratio/CLT identity, block normalization, quantile direction, proposed deterministic size sequence, dependent windows, zero-count refusal caveat and worked example. Read the primary PRW2001 section4 theorem/remark directly. Suggested clarifying deterministic *sequence* rather than fixed b, and explicitly continuous positive-variance limiting law; both incorporated.

Source/governance reviewer, medium effort: APPROVE for operator milestone, no target/accounting/source or dependency blocker. Independently checked original trade weighting, complete exit footprints, synchronous stocks, unchanged D18 product settings, target-specific accounting and Step6b/7/8 ordering; independently reproduced the example. Suggested making acceptance records an explicit required checklist; incorporated. D39 is now recorded and state/handover updated.

Final clarifications also explicitly refuse an outcome halo crossing the lockbox or another unauthorized source period. They narrow claims, without authorizing source loading, implementation or study. Review approval is for design presentation, not a proven empirical method.

## Primary verification

- Fetched and read [PRW2001 section4 equation16, theorem4.1 and remark4.1](https://www3.stat.sinica.edu.tw/statistica/oldpdf/A11n49.pdf), as of2026-10-01. The uniform-over-sizes theorem has stronger mixing requirements; its remark recovers deterministic sequences. This is asymptotic conditional theory.
- Fetched and checked [Tewes/Politis/Nordman theorem5](https://arxiv.org/pdf/1706.07237), as of2026-10-01. Mean-based conditions are mapped to the project W-process, then ratio/denominator argument; no claim that it certifies actual selected trades.
- Read actual `signaltest.py` entry/holding/final-exit seams and `simcore.py` END_OF_DATA/STALE_MARK meanings. No panel loaded. Existing reset/forced-end and cost/matcher problems remain unresolved.
- Exact Fraction oracle reproduced all five means and roots; 60-digit Decimal oracle reproduced endpoints `.00487867965644035742679746691368545288214549218693457789023498` and `.00841421356237309504880168872420969807856967187537694807317668`. This is arithmetic evidence, not coverage evidence.
- Documentation audit regression:15 passed in0.07s. Final local links, whitespace, narrow line-ending diff and protected-file hashes checked. No code changed; unchanged broad tests were not rerun. Prior suite evidence retains its original source/skips.

Scratch evidence: `var/verification/2026-10-01/calendar-subsampling-design/primary-oracle.json` and protected hashes. User-owned AGENTS.md remains untracked and preserved.

## Outcome

D39 design milestone complete. Proposed next unit: isolated deterministic research calculator and failure/refusal tests, after the operator implementation decision and separately reviewed test-first plan. Stochastic stress/confirmation needs its own frozen numeric protocol and authorization. No calculator implementation, experiment, reserved draw, market evaluation, accepted floor, inference enablement, lockbox, task-order amendment or broker/live path. Task3a and M1-M4 remain open.
