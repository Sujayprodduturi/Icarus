# Kite acquisition build — scoped local GO

## Partial acquisition stop and raw-quarantine repair

The first full acquisition saved 16 historical chunks / 4,236 candle records,
then stopped with `SchemaFailure` after AARTIDRUGS's first 2015 M15 chunk.
The original failing response was discarded, so its exact cause remains unknown;
no vendor-price anomaly is inferred from that generic error alone.

The reviewed repair preserves byte-exact rejected historical responses with a
closed rejection code. Isolated candle-quality rejections remain unusable and
excluded from accepted coverage while independent requests continue. Structural
schema, auth/network and required preflight failures still halt. Cached rejected
records remain rejected without refetching or reclassification. Atomic final
reports enumerate accepted/empty/rejected counts and missing names, retain
`source_qualified=false`, and distinguish completion with rejections (exit 3).

Root's initial review caught a later-lockbox-row bypass after an earlier quality
failure; it was fixed with a complete-response timestamp prescan before any
archive decision. Recognised 2023+ records, including early IST dates whose UTC
date is still December 31, never become persisted price artifacts. Root and
reviewer also caught unvalidated cached rejection enums and explicit null-field
state bypasses; strict read/write checkpoint state guards now refuse them.

The final root suite passes **103 tests**, global Ruff lint, targeted formatting
and strict typing over five files. Independent review passes 31 focused tests
and the full invented mixed-flow probe: four requested names / three resolved /
one missing, 12 chunks comprising 10 accepted / one empty / one rejected, adjacent
and next-symbol continuation, exit 3, and resume with one session call / zero
history calls. Structural/auth/preflight halts and mixed-row lockbox no-write
guards pass. Final scoped GO receipt:
`var/kite-review/quarantine-final/receipt.json`, SHA-256
`41de9791bcc6a224db258b343df278acf7e6c10dd182473a1e29f34650779f2a`.

The same run ID is reopened for fresh local login. Existing data is retained;
actual acquisition must still demonstrate the failed chunk's reason and full
completion. No source qualification or strategy evaluation is granted by these
software checks. Earlier checkpoints below describe the preceding revisions.

## Actual first connection and narrow compatibility repair

The first submitted callback authenticated successfully and acquired the NSE
instrument master (687,745 bytes, SHA-256
`48adffbfde4a9248ef5541b4273531671e87da3a4b745881125aef02a7bf0d22`)
and 125 INFY M15 candles for 2022-12-26 through 2022-12-30 (7,898 bytes, SHA-256
`a3c154170cb3c91d81340003e4ca9dd946401fef6ae5c0dc8ce24fc02f77f9cc`).
No performance result was calculated. This confirms that request's authenticated
history access, not full-source coverage or qualification.

The next Nifty mapping check failed because the current vendor master uses
`segment=INDICES`, while the downloader required the older `NSE-INDICES` example.
It was a downloader compatibility bug, not a bad operator callback. The narrow
repair accepts these two known aliases while retaining exact NSE/EQ/name/symbol
and uniqueness guards. TRI, futures, wrong venues and ambiguous matches refuse.
Existing raw artifacts are unchanged and reused; no inferred timestamps or
coverage were added. Root's repaired regression passes 90 tests; independent
review passes 18 focused tests and gives scoped GO. Review receipt SHA-256:
`a835beadfdb086d17bd3ea46f433e9ceba4018df5b4c03e920e609db5b110d33`.

The failed process discarded its memory-only daily token. A new local credential
prompt is opened with the same run ID; fresh operator login is required before
Nifty probing/full acquisition can continue. Full acquisition, DATA_QUALIFIED and
actual strategy RUN_AUTHORIZED remain unclaimed. The earlier checkpoint below
describes the state before this first authenticated response.

## Outcome

The operator-side historical downloader is built and independently reviewed.
It is ready for local hidden credential entry, manual Kite login, sample checks
and checkpointed daily 2011–2022 / M15 2015–2022 acquisition. At this checkpoint
no authenticated entitlement or new Kite history is claimed. Acquisition does
not qualify the source or authorize a strategy study.

## What changed

- Standalone stdlib downloader and fixed-destination CONNECT proxy under
  `tools/kite_acquire`, separate from the Icarus/research runtime and broker SDK.
- Docker acquirer uses UID 10001, read-only root, dropped capabilities, bounded
  memory/PIDs and internal network only. Proxy allows api.kite.trade:443 only.
  End-to-end vendor TLS verification remains enabled; redirects and broker order
  routes refuse. Console logging is disabled in both services.
- Only raw export is mounted. Secrets use hidden interactive prompts and memory;
  no secret/session responses are exported. The operator performs browser login.
- Bound request list: 693 legacy research symbols plus NIFTY50, exact text hash
  `f29a40682f220eb3dce723a1d32ebdd1fc59baa8d96a3d23db7b74484c8739bf`.
  Input classification remains requested coverage, not certified PIT membership.
- IST API request dates, UTC stored instants, pre-2023 guards, immutable response
  hashes, explicit empty/unresolved coverage and verified checkpoint reuse.
- PowerShell launcher uses a named worker and refuses a pre-existing same-run
  container before building/starting services. Repeated launches must not tear
  down the original worker's proxy.

## Review and verification

Root's final offline regression passed **89 tests**: 17 downloader checks plus
existing portfolio characterization, strict-through fills and backtest/lockbox
checks. Global Ruff lint, targeted format and strict typing over five files pass.
The repository's actual Task 1.12 golden backtest is still scheduled/open; this
packet does not claim it completed. Two earlier root invocations failed due to
a missing test-output parent and restricted Windows uv cache, respectively;
the corrected outside-sandbox run passed. Those setup failures were not code
guard detections or passing product evidence.

Independent source and end-to-end review is scoped GO. A mocked download with
two resolved names plus one missing name completed 26 daily and 66 M15 requested
chunks and two nonempty 2022 probes. First execution made 96 transport calls;
same-run resume made only one session-refresh call and reused all data artifacts.
Missing names stayed in the requested denominator. Reviewer receipt:
`var/kite-review/download-flow/review-receipt.json`, SHA-256
`6d681ccb3f1c2dedb06ffdcb210e7b58a9e4e0f2b2776da17f452d8aab4f4023`.

Actual Docker checks passed all eight acquisition assertions: nonroot identity,
read-only root, no Icarus/SDK/cache/secret environment, blocked direct broker TCP,
rejected unwanted proxy destination and successful verified Kite TLS handshake.
This was credential-free transport verification, not a historical request.
A separate official Python container using UID 10002, no mounts and network-none
also refused outbound access and had no secret environment. It proves that
specified boundary, not the security of existing native research programs.
Receipt: `var/verification/2026-10-14/kite-acquisition/root/docker-receipt.json`.

Review caught and repaired: undocumented Nifty instrument-type assumption,
incorrect API timestamp formatting/IST labels, request-list provenance omission,
impossible OHLC acceptance, checkpoint refetch, Docker build-context scope,
unbounded proxy header reads, launcher exit/concurrency handling and logging.
No price/timestamp semantic evidence, licence or missing history was invented.

## Next and remaining boundaries

Complete the local credential prompt, browser login and token callback. Download
mode first checks late-2022 INFY/Nifty M15 samples in the same session, then starts
the agreed ranges. Observe metadata manifests and final report, not credential
logs. Keep the terminal and Docker open; use the same run ID for an interrupted
acquisition. Output is staging material and must later be independently hashed,
sealed, qualified and handed to a separate offline research container.

Source coverage/licence, delisted mapping, PIT/calendar/actions/opening liquidity,
Kite candle semantics and exact benchmark compatibility remain open. Actual
ledger activation, strategy evaluation, inference, promotion, live orders and
2023+ lockbox use remain unapproved. Hosted CI for this source is pending until
publication; do not claim it from local checks or the previous source.
