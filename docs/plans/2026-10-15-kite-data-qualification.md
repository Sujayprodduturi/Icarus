# Kite input qualification — bounded data-plane review

## Approved intent

After collection finished, the operator approved reviewing gaps and rejected
records and preparing aligned stock/Nifty inputs. This unit gathers facts that
can support a later source certificate. It does not evaluate strategies or
claim the existing source satisfies the canonical simulator contract.

## Pinned starting point

- 694 requested names: 544 resolved and 150 unresolved.
- 25,024 planned ranges: 19,938 accepted, 4,760 empty and 326 rejected.
- Report SHA256 `43b80fc9e42387b978622676c15ce9c69c564772e006f9627a627bc729f429e0`.
- Snapshot index SHA256 `86aae96d13a4046c4b0f6ba08b6e97e2bcf1b1ca4b2f834b44a767ce089214f0`.
- Original raw archives remain unchanged. All research/strategy holds remain.

## Independent work

1. **Unresolved names:** retain every requested name and record exact current
   master matches and first/last presence in the existing pre-2023 NSE daily
   archive. Presence is not listing truth; absence is not delisting truth. Never
   guess a rename or infer no-position liquidation. Keep the NSE daily PIT
   authority and separate daily 2011–2022 / M15 2015–2022 ranges.
2. **Rejected records:** a standalone stdlib helper audits only the 326 rejected
   chunks. Verify each opened raw file's hash and size against the pinned snapshot
   and manifest before decoding. Keep one bounded response in memory at a time,
   enumerate every applicable closed invalid-bar category plus a union-invalid
   count, and emit timestamps/counts/identities only, never price values. Do not
   repair, filter into a usable bundle or reclassify the acquisition rejection.
3. **Source evidence:** verify primary vendor/exchange documentation for candle
   labels, availability, adjustments/revisions, index identity, permitted archival
   use, calendar and corporate-action lineage. Distinguish verified assertions,
   dated staff statements, local observations and unknowns. A paid plan and a
   matching hash do not certify these facts.
4. **Paired readiness:** after initial findings, review a bounded stock/Nifty
   timestamp-overlap and daily/M15 aggregation comparison. It remains data-QA,
   not return/performance calculation. Separate source adjustment bases and
   timestamp unknowns; never turn a candle close into an exact raw index event.

## Runtime boundary and verification

Record decoding runs in a separate official Python container, UID10002,
network-none, read-only root, dropped capabilities, no-new-privileges, bounded
memory/CPU/PIDs, read-only raw/code mounts and an output-only evidence mount.
No broker SDK, credentials, home/repo/socket or database mounts. No strategy
imports, signals, returns, P&L, trial ledger, inference, or lockbox evaluation.

Test QA predicates with invented fixtures first. Measure a fixed ten-chunk
sample including the original AARTIDRUGS failure; run all 326 only if projected
under five minutes and 1GiB. Avoid a second full raw-archive hash pass. Preserve
sample and full receipts, original hashes, exact denominators and explicit
unavailable outcomes. Independent review and root spot checks precede claims.

Helpers and paid-data reports stay under ignored `var/kite-qualification/`;
only non-price findings and review decisions enter tracked documents. Source
classification remains `DATA_QUALIFIED=false` until independently justified;
software cannot grant its own source approval or actual run authorization.
