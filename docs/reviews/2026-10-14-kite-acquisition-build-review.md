# Kite acquisition build — scoped local GO

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
