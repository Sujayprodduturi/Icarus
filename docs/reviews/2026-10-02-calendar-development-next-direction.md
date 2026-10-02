# Calendar development failure: independent diagnosis and next direction

Date: 2026-10-02. Independent GPT-6 Astra, medium effort. Scope: existing development evidence only; no new experimental paths, estimator changes, threshold changes or real data.

## Verified outcome

The retained terminal says state COMPLETE, complete=true, passed=false. This is a successfully completed experiment that rejected the candidate, not an execution error and not a strategy verdict. Terminal SHA256: `b9931a44708292e2f7826dc46bb6c0f1d4261bdae769083d1f60fde72dbf89ef`. Source/evaluator hashes in claim.json match the reviewed runner1f94d8fd...006f53f and compacte18e49a7...d442969. The review did not read a confirmation seal or seed.

I independently streamed all9216 saved paths, decoded retained Decimal coefficients without production counter helpers and recomputed replicate/arithmetic/coverage/both-tail/precision counts. All52 cells exactly match terminal.json. There are46 formal qualification cells; every one fails coverage criteria. Their observed coverage ranges from299/512=58.40% to437/512=85.35%. This is broad undercoverage, not one exceptional profile narrowly missing a threshold.

| Cell | Truth covered /512 | Precision-ready /512 | Meaning |
|---|---:|---:|---|
| P1 baseline,n64,raw |391|512|Even the baseline emits narrow but unreliable ranges|
| P1 baseline,n128,raw |426|512|Longer tested span improves this cell, without approaching acceptance|
| P3 overlap,n128,win |390|119|Both reliability and the twenty-point win-width requirement fail|
| P7 long holds,n64,raw |299|500|Apparently usable widths conceal especially poor coverage|
| P7 long holds,n128,raw |365|506|The larger tested span remains inadequate|
| L1 sparse,both spans,all metrics |0|0|Every history refuses rather than inventing evidence|

All four signed-effect controls detect the deliberately large effect512/512, yet cover their actual means only411-432/512. Detection success therefore does not rescue uncertainty calibration. For sparse n64, refusals are130 zero-full-count and382 zero-slice; n128 has37 and475 respectively.

## Direct evidence for rare-tail failure

From retained atom codes,400 of512 P5/n128 paths contain no rare +8/25 jump in the core. Their paired ranges cover293/400, with102 misses above the upper endpoint. The112 paths containing the rare atom cover105/112 and have zero upper-endpoint misses. P6 mirrors this:397 paths without the rare negative atom produce96 lower-endpoint misses;115 paths containing it produce only one. This is diagnostic conditioning on already exposed histories, not a new acceptance test. It shows exactly where the one-sided failures concentrate; it does not isolate all causal mechanisms.

The majority of short histories miss the rare event that balances the population mean. Recycling blocks within such a history cannot create the missing extreme observation. Selecting a different block length or fitting a multiplier to these results would not establish that the next unseen tail is covered.

## Finite-window geometry: established facts versus inference

The estimator uses b16 of n64 and b26 of n128: b/n=.25 and.203125. These are substantial fractions of the entire history. The49 or103 overlapping roots are not independent repeated histories. P7's32-session forward shock window is longer than either block; its full lookback/completion footprint spans40 sessions. These are exact design facts, not estimated explanations.

A simple analytic subcase illustrates centering distortion. For IID fixed-count observations of variance sigma^2, any contained b-block has Var(mean_b-mean_n)=sigma^2*(1/b-1/n), so the sqrt(b) root has variance sigma^2*(1-b/n), whereas the limiting mean-root variance is sigma^2. The corresponding scale factors at these geometries are sqrt(.75) and sqrt(.796875), both below one. This calculation does NOT prove a correction factor for Icarus's dependent random-count ratios; overlapping empirical quantile variability and dependence remain additional issues. Do not insert 1/sqrt(1-b/n) as an unreviewed fix.

The primary subsampling theorem is asymptotic with increasing b and b/n tending to zero, not a finite-sample guarantee for these histories: [Politis, Romano and Wolf, section4](https://www3.stat.sinica.edu.tw/statistica/oldpdf/A11n49.pdf), already checked in the reviewed design on2026-10-01. The current evidence is consistent with inadequate finite-window calibration, but one experiment cannot assign a unique fraction of the loss to centering, overlapping quantiles, dependence or rare tails.

Independent existing-path summaries reinforce the narrow-range problem. P1/n128 raw empirical mean-error SD is.00120894 while median full width is.00349087; mean error is only-.00002832. P7/n128 raw SD is.00469967 while median width is.01013468; mean error is-.00004023. These empirical summaries are descriptive diagnostics of the exposed sample, not population variance certificates or new criteria.

## Recommended next bounded task

Prepare one finite-window diagnosis and candidate-revision proposal, not another immediate calculator or sampled screen. First derive exact finite-horizon score variances for the known artificial raw/paired laws, where W_t=A_t-theta*C_t. Their finite Rademacher/shared-shock structure permits algebraic covariance calculations and positive independent-noise contributions. Compare b-length and n-length score behavior, and document count variability using the already retained histories. Score variance is not exact ratio variance; keep that distinction explicit.

Use that deterministic analysis to choose one next research direction: a studentized calendar-block construction with explicit finite-window applicability, or a longer-history design with explicit insufficient-evidence handling. Studentization means scaling the statistic by an estimated uncertainty measure; it adds assumptions and can fail on sparse/rare histories. Longer histories change the amount of evidence, not the confidence bar, but require a separately reviewed geometry/resource design. Neither is approved or predicted to succeed here. The present failure does not justify choosing the most favorable n, excluding failed cells or declaring a practical minimum-data floor.

A useful next proposal must say which demonstrated mechanism it addresses, which rare-tail/sparse limitations remain, how the original all-trade target is preserved and how independent confirmation will be protected. If it cannot supply that argument, stop at an honest unresolved diagnosis rather than generating another unmotivated estimator. Any later implementation and new development draws require a new recorded candidate/protocol version; the current exposed paths remain development evidence forever.

## Held conclusions

Keep this calendar candidate rejected under its frozen protocol and preserve every failed cell. Do not draw confirmation, weaken widths/coverage criteria, reinterpret the signal diagnostic as after-tax promotion or infer that trading strategies failed. M1-M4, Task3a and real-market applicability remain open. No new sampled experiment, code change or market-data access was performed for this review; only this review document was written.

## Finite-window diagnosis plan scope review

Date:2026-10-02. Read `docs/plans/2026-10-02-calendar-finite-window-diagnosis.md` before implementation. Verdict: APPROVE the bounded deterministic diagnostic under current D41 continuation. One pure rational module plus independent coefficient-vector tests is useful and minimal for separating finite-window centering/overlap geometry from claims about calibrated uncertainty. It introduces no sampling, interval, width adjustment, practical floor or modification to the failed estimator/streams.

The plan is narrower than the original next-direction recommendation: its linear-filter covariance is a toy oracle, not the frozen laws' exact random-count score covariance. That limitation is explicit and must remain in any final explanation. The count-weighted centering identity directly guards the tempting but invalid substitution of b/n for C_block/C_full. Test proper contained blocks and valid integer counts, including strongly unequal block/full count ratios; retain resource-bounded numeric inputs as well as geometry. These are implementation clarifications, not an expanded research task.

Acceptance requires exact independent variance/covariance oracles and refusal tests; a green diagnostic does not explain a numerical fraction of the observed undercoverage or select a correction. Once those identities are established, report them and return to the candidate-revision decision rather than extending this toy into another generic uncertainty framework. No blocker or additional routine operator permission is required for this stated deterministic scope.
