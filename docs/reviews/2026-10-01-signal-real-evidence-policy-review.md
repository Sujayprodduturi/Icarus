# Real-data evidence policy review

Date: 2026-10-01. Entry source: c12f02209196f3bb3130d128406f3ed03135a933. Scope: documentation/design milestone only, not implementation approval, method adoption or official-runner attestation.

## Reviewed proposal

[Real-data evidence policy](../plans/2026-10-01-signal-real-evidence-policy.md), final SHA256 `21a331d9a1e47cc33f624814d304f2ed49c92ae566912e9f0274fe68898e07b3`.

GPT-6 Astra, medium effort, independently reviewed the architecture and exact written proposal: APPROVE for operator presentation, no blocking revision. The source/governance reviewer, medium effort, independently read the relevant implementation and exact proposal: APPROVE for presentation, no blocking defect. Their approvals concern decision framing, not implementation or experiments.

Both nonblocking clarifications were incorporated: readiness is target-specific (missing benchmark blocks paired-excess, not raw arithmetic; empirical moments are not trusted bounds but do not prohibit future empirical-method research); F47/F20 remain open findings to resolve/adjudicate in the later schedule amendment, without silently adding task dependency edges.

## Primary verification

- Independently inspected deployed-capital/fragment accounting, stale marks and benchmark arithmetic in `signaltest.py`; inspected sell/stale-mark charge calls and stateless DP fees in `costmodel.py`. F48 remains unresolved.
- Independently read the disabled inference/refusal path in `signalmetrics.py` and original Step6b/7/8 ordering. No product bridge or schedule amendment is supplied here.
- Fetched the full [Veraar primary paper](https://fa.ewi.tudelft.nl/~veraar/research/papers/Gebelein.pdf), 2026-10-01; equation1.1 requires jointly Gaussian inputs and square-integrable centered functions. The project must establish its own trading-path applicability separately.
- Reproduced the deterministic rare-tail example with 60-digit Decimal arithmetic: `.999**100 = .904792147113709042032214606239950347800488416333469929276205`; `.001 * 100**2 = 10`. No random draws or market samples were used.
- Documentation audit regression: `uv run pytest -q tests/unit/test_audit_ledger.py`, 15 passed in0.08s. Whitespace and tracked line-ending checks passed. Local links checked after this review record was created.
- SHA256 comparison confirms `goal.yaml`, `signaltest.py`, `signalmetrics.py`, `costmodel.py` and the combined moment reference are byte-identical to entry. Documentation-only change; the unchanged full suite was not rerun. Prior 1940-pass/10-skip evidence retains its original source and limitations.

Local scratch evidence: `var/verification/2026-10-01/real-evidence-policy/` protected-before/after JSON. The handover, state, task note, audit and append-only D38 now record the milestone and requested explanation cadence. User-owned untracked AGENTS.md is preserved.

## Outcome and remaining decision

Written policy milestone complete. Recommendation: a separately preregistered practical diagnostic-method design, explicit about assumptions and refusal, rather than another artificial-law calculator. Operator choice remains pending. No readiness helper, estimator, accepted floor, study, real-data trial, reserved-stream consumption, lockbox access, inference enablement or broker/live path. Task3a and M1-M4 remain open.
