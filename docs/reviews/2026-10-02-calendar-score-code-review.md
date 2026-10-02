# Calendar-score helper: ordered focused final review

Date: 2026-10-02. Verdict: APPROVE the isolated deterministic synthetic-model helper at the exact hashes below. No blocking findings. This is not approval of a sampled study, market inference, source-adapter authentication, or Task3a completion.

## Review order and scope

1. Read and applied [ponytail-review](C:/Users/sujay/.agents/skills/ponytail-review/SKILL.md) first, after reading both source and tests. Its complexity-only pass found no speculative abstraction or unnecessary dependency: **Lean already. Ship.** No deletion recommendation.
2. Then read and applied [engineering code-review](C:/Users/sujay/.codex/plugins/cache/claude-cowork/engineering/1.2.0/skills/code-review/SKILL.md). Reviewed correctness, bounded arithmetic/performance, strict types, refusal behavior, side effects and test coverage. Ran focused tests and independent deterministic arithmetic after that pass.

No children/delegation, random draws, study replay, confirmation-seal access, market data, or source mutations. Only this review file was written. No duplicate full suite was run.

## Frozen files and executed checks

- `scripts/research/signal_calendar_score.py`: SHA256 `7b19acfe21715fe082b13879ea9d3348d769131ab596553baf0c20fd5c600fc7`.
- `tests/unit/test_signal_calendar_score_research.py`: SHA256 `6e2807a0eda37ab7c2e4276592b7f09e4119954a147dfc239fd607d6f2415b6c`.
- Independently executed `python -m pytest tests/unit/test_signal_calendar_score_research.py -q`: **52 passed in 0.14 seconds**.

## Correctness assessment

The radius squared is exactly 10*K*n*Delta^2/C^2, matching q=5 and daily score support width2*Delta. The pre-data maximum full-width square is40*K*Delta^2/n. The exponent series is the exact positive rational partial sum through degree10; `2*number_of_targets/series` conservatively bounds the union of the requested tails, with one to three unique fixed metrics. No metric independence is assumed. The strict synthetic/declaration checks are assumptions contracts, explicitly not certificates of an observed trading source.

Dense eligibility compares the maximum width square with (requested_width-4e-60)^2 before seeing totals. Thus high observed counts cannot rescue an inadequate history. Radius rounding uses integer square root plus an exact square check; both endpoint signs use correct floor/ceiling rational grid operations. Decimal tuple construction is exact independently of caller precision. The4e-60 allowance covers both radius inflation and both endpoint roundings. Point targets retain their exact Fraction, separately from a possibly nonzero displayed enclosure.

Counts are positive exact integers bounded by2n; dense totals additionally require C>=n. Every reported target must have the same count. Aggregate support consistency and integer wins are checked. Equal count cannot establish actual shared cohort membership, and the docstring correctly requires that semantic source premise. Sparse adequacy reports neither dense maximum width nor joint-coverage lower bound; it retains only unconditional emitted-and-miss control and never claims selected-output conditional coverage. Zero counts refuse explicitly.

## Additional independent numerical evidence

Checked16 endpoint cases across (n,K,C)=(1,64,1),(40,1,40),(2048,2,4096),(1048576,64,1048576). Centers/support widths included -19/7 with width1/113, 2^200/3 with width7/5, -1/2^200 with width1/2^180, and a zero-width point. An independently computed80-digit rational square-root enclosure verified outward lower/upper endpoints, the exact radius square, and width inflation at most4e-60. All cases passed; K>n is conservative and does not invalidate the cover-size upper bound.

A caller Decimal context with precision1, Emax1, Emin-1, clamp enabled and InvalidOperation/Inexact/Rounded/Overflow/Underflow traps produced exactly the same result as the ordinary context. This is stronger than testing ordinary low precision alone.

Enumerated257 exact binomial sufficient-statistic states for n=256 under an independent-date artificial law B~Bernoulli(1/2), C_t=1+B and A_t=2B. This has endogenous counts/outcomes and population trade-ratio target2/3. Summing exact rational binomial probabilities outside the returned interval gave miss probability approximately0.000002352195997075022, below the declared one-target conservative bound approximately0.013663012625946366. No histories were sampled. This finite example checks the ratio path and count dependence; it is not the proof of uniform validity, which remains the score/cover derivation.

## Engineering and remaining boundaries

Strict type checks reject bool/float/Decimal where exact rational inputs are required, unsupported q values, unknown/observed declarations, real scope, malformed metric budgets, invalid support and count/cohort inconsistencies. Input numerators/denominators are bounded at256 bits, n at1048576, K at64, and metrics at3; exact integer work is consequently bounded. These bounds and the absence of I/O, network, RNG, broker interfaces or generic extension machinery fit the approved unit.

The focus tests cover the planned equality-rounding refusal, point targets, sparse refusal, metric budget, unknown assumptions, numerical bounds and pre-data selection behavior. The retained long-history geometry choices remain mathematical benchmarks only. Full evidence storage/runtime feasibility, trusted full-path adapters, unknown-law assumptions, strategy search multiplicity and real-data authorization remain unresolved. No passing unit test or analytic fixture establishes any of those claims.
