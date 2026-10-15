# Independent alias-retrieval preparation review — 2026-10-15

## Verdict

**GO for retaining the 24-symbol alias list as metadata-only candidate-collection preparation. NO-GO for identity admission, point-in-time universe use, historical token continuity, authenticated launch, data qualification, or strategy use.** `DATA_QUALIFIED=false` and `RUN_AUTHORIZED=false` remain required.

Scope reviewed: `docs/plans/2026-10-15-alias-retrieval.md`, `docs/data/2026-10-15-alias-retrieval-evidence.md`, and the ignored alias helper, two tests, evidence, request, provenance, current-NSE receipt and `EQUITY_L.csv`. The existing collector was inspected only at its local symbol/provenance validators. No credentials, SDK session, socket, broker path, price query, acquisition, strategy, ledger or lockbox path ran.

## Findings

No blocking correctness or scope finding was found.

The routing classification is honest: every candidate says `identity_continuity=UNKNOWN`, `token_continuity=UNKNOWN`, and retrieval-only use. Post-2022 rows are explicitly modern routing metadata rather than 2022 universe input. The prepared request contains 24 distinct current Kite NSE/EQ symbols plus one `NIFTY50` probe, with no duplicate. The unchanged collector validators accept all 25 and the classification `MODERN_ALIAS_RETRIEVAL_CANDIDATES_NOT_HISTORICAL_IDENTITY`; this proves request/provenance shape only, not identity or permission to launch.

The three changed-ISIN routes are correctly guarded rather than admitted: `AMIORG→ACUTAAS` (`INE00FF01017→INE00FF01025`), `HEG→HEGAM` (`INE545A01016→INE545A01024`), and `IIFLWAM→360ONE` (`INE466L01020→INE466L01038`). The other 21 matching current ISINs strengthen retrieval candidacy but still do not prove uninterrupted identity, merger/demerger treatment, adjusted-history semantics, or token continuity.

## Independent reproduction

Before parsing, host metadata checks and a separate constrained-container `sha256sum` both reproduced the six physical input pins:

- original 694-line request snapshot: 5,699 bytes, `f29a40682f220eb3dce723a1d32ebdd1fc59baa8d96a3d23db7b74484c8739bf`;
- 150-name gap classification: 94,761 bytes, `26cca5b71d5a7c6d620ada9562df33965454ce13f7cd284d1d79fc6027254fe1`;
- full symbol-change CSV: 69,219 bytes, `69c0c5e18cca3350c2e07f7c8c4c1ebbfe38d81c8fa32c51f6ca9ea332e85f17`;
- sealed 2022-12-30 ZIP: 87,662 bytes, `636cb895992d40dfbf92dfe4b634d4e4000be6f218f6075c30631402683e19e7`;
- captured Kite master: 687,745 bytes, `48adffbfde4a9248ef5541b4273531671e87da3a4b745881125aef02a7bf0d22`;
- current NSE EQ list: 183,984 bytes, `951c5d376d83ef0ddf8b040f9a52cd8b19388e7a51de8880af9a0b06ea0865a1`.

Two invented tests pass in `python:3.12-slim`. A fresh actual derivation then ran with `--network none --user 10002:10002 --read-only --cap-drop ALL --security-opt no-new-privileges --memory 1g --cpus 2`, bounded tmpfs, only the helper and six individual inputs mounted read-only, and only `alias-retrieval/root-review/` writable. No home, repository, socket, credentials or SDK was mounted.

Fresh results exactly match the prepared counts and candidate semantics: 693 labels; 150 unmatched; 159 all-label and 85 unmatched both-side change rows; 35/58 late-2022 names and 37 rows; 58 exact raw-date EQ ISINs; 49 broader current candidates; 24 raw-cohort current-Kite candidates; 21 same-current-ISIN candidates; three changed-ISIN candidates. The regenerated request is byte-identical, 25/25 unique, SHA-256 `037318fe0951f97e3873c1f0f2a4b1222794e5628b6853927a80806cb5099154`. Review outputs are `root-review/evidence.json` (`ee5b7b150a5c9b902c5e2ac876de1df328139c19d99c8cf2032eb9683cde7fb9`), `request.txt`, and `provenance.json` (`5ec3458c16e75a58ff3223b6a42a0e3a3642b1db4587d79695101b9c8d4867fb`). Evidence/provenance JSON hashes differ from the prepared versions only because the independently mounted input/output paths differ; counts, candidates, limits and request bytes match.

Commands: constrained `docker run ... python -m unittest test_build_alias_retrieval`; constrained `sha256sum` over the six mounts before parse; constrained `build_alias_retrieval.py` into the new review directory; constrained import of unchanged `validate_symbol_file` and `validate_provenance`; host-side hashing and comparison of generated metadata outputs only. The raw ZIP was parsed only in the isolated container.

## Frozen-matrix continuity check

The original matrix remains 96,363,300 bytes with SHA-256 `4de39c206b47efce6a0af9f366dee506f71207082dc131a3426c7a17f816de00`. The amended overlap receipt SHA-256 is exactly `369dcca5ff8c10c2abb9933259a0b690cd71a42bd6403f37de39a122ae0d1a36`; it reproduces the prior finding: 1,421,549 requested-row observations, 1,416,583 unique source observations, and 4,966 excess alias assignments split as 1,294 `SKSMICRO`, 1,285 `IBVENTURES`, and 2,387 `STRTECH`.

## Remaining gate

Any later acquisition still needs the existing manual isolated operator-auth boundary and a new run ID. Its output must remain candidate evidence until each route has sufficient dated identity/corporate-action proof; an empty provider response is a retrieval gap, not delisting or discontinuity evidence. Provider retention and adjustment semantics remain unresolved.
