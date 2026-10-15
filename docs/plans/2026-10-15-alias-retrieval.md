# Alias retrieval plan — 2026-10-15

## Purpose and boundary

Prepare additional historical retrieval attempts for names missing an exact current Kite symbol. This is metadata routing only. A modern alias does not enter the 2022 point-in-time universe and does not prove continuous security identity, merger treatment, or historical token continuity. `DATA_QUALIFIED=false` and `RUN_AUTHORIZED=false` remain unchanged.

## Prepared sequence

1. Pin each of the 58 late-2022 unresolved names to its exact `2022-12-30 + symbol + EQ + ISIN` row in the sealed NSE bhavcopy sample.
2. Search the captured public NSE symbol-change file on both `OLD SYMBOL` and `NEW SYMBOL` across all 150 unmatched labels and all 693 equity request labels. Rows after 2022 may propose a current retrieval symbol only; they cannot rewrite historical membership.
3. Join proposed modern symbols independently to the captured Kite NSE/EQ master (token, current symbol, current name) and to the newly captured official current NSE EQ list (current symbol, company name, ISIN).
4. Preserve every candidate as `identity_continuity=UNKNOWN` and `token_continuity=UNKNOWN`. A matching current ISIN raises confidence in the retrieval candidate but remains insufficient proof of uninterrupted identity or corporate-action treatment.
5. Use the unchanged isolated collector with a new run ID and the separately pinned candidate-bridge evidence. Keep the original 694-line request snapshot untouched. Review output before any authenticated launch.

## Prepared inputs and test

The ignored directory `var/kite-qualification/2026-10-15/alias-retrieval/` contains the helper, two invented-fixture tests, captured `EQUITY_L.csv`, the evidence JSON, a 25-line request file (24 candidates plus required `NIFTY50` probe), and provenance accepted by the existing `validate_provenance()` contract. The tests prove both-side matching, exact raw ISIN attachment, current metadata capture, and explicit unknown continuity; they do not prove real identities.

## Authenticated command, deliberately not run

After root review and the operator's existing manual-auth boundary is satisfied:

```powershell
.\scripts\start_kite_acquisition.ps1 -Mode download -ExportDirectory C:\ICARUS\var\kite-history -SymbolsFile C:\ICARUS\var\kite-qualification\2026-10-15\alias-retrieval\requested-modern-aliases.txt -ProvenanceFile C:\ICARUS\var\kite-qualification\2026-10-15\alias-retrieval\provenance.json -RunId alias-retrieval-20261015-v1
```

The current provenance contract can honestly represent this request because its classification and source dictionaries bind both the original request snapshot and the candidate bridge by SHA-256. The collector remains unchanged. It may return empty/unresolved history for a modern token; that is evidence of a retrieval gap, never evidence of delisting or identity discontinuity.

Provider retention/adjustment semantics still require operator-approved provider contact before qualification. No SDK/authentication, price request, broker write, strategy, trial-ledger, or lockbox action occurred in this preparation.
