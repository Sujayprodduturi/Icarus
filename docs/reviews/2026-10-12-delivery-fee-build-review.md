# Delivery-fee accounting completion - 2026-10-12

SCOPED PASS for F48's simulator paths at source `e64133e`. Executed delivery sales now allocate the configured fixed fee once per symbol/IST day in the portfolio book. A standalone signal observation owns its own fee scope; partial fragments share that scope, while serial independent observations retain their own fees. Existing ALREADY_OPEN refusal remains. Stale marks and no-fills neither pay nor consume the delivery fee. Each run starts clean.

The ordinary stateless per-side cost quote is unchanged. Other pessimistic stale-mark friction remains labelled as an estimate. Rates, taxes, risk limits, existing YAML and the golden fixture are unchanged. This corrects allocation; it is not verification of actual contract notes or a profitability claim.

Parent independently reproduced the UTC/IST boundary and passed 206 focused/golden tests. Reviewer independently ran public signal integration: partial fragments [15.34,0], serial observations [15.34,15.34], and identical repeated runs. Global mypy198, lint, formatting and diff checks passed. Four postcommit known-bug variants were caught with behavioral failures; exact committed bytes were restored and 206 restored checks passed.

One workflow deviation is retained: the builder tested a temporary wrong-scope variant before commit, contrary to the standing postcommit-only rule. Parent verified exact restoration and subsequently completed all four checks after commit. The deviation leaves no unresolved source state; subsequent feature mutations must remain postcommit.

No actual ledger, panel, market data, lockbox, broker or live path was accessed. Inference remains disabled. The next authorized unit is the reviewed breakout exit and scheduled low-volatility consumer, in progress.

[Compact proof](2026-10-12-delivery-fee-build-proof.json).
