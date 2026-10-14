# Kite historical acquisition — operator-side data plane

## Authority and purpose

On 2026-10-14 the operator reported creating the Kite app and paying for the
subscription, then explicitly requested connection and historical acquisition.
This authorizes obtaining historical inputs, not evaluating strategies, activating
the actual trial ledger, touching the 2023+ lockbox, or placing orders. Subscription
status is operator-reported until an authenticated historical request succeeds.

The next concrete milestone is a successful isolated authentication and small
coverage probe, followed by checkpointed acquisition of daily 2011–2022 and
15-minute 2015–2022 records for the requested historic symbols and Nifty 50.

## Reviewed boundary

Use a standalone acquisition image containing only the downloader and a distinct
fixed-destination CONNECT proxy. No Icarus engine, broker SDK or research code is
installed in that image. The acquisition process runs as UID 10001, with a
read-only root filesystem, dropped capabilities, no-new-privileges, bounded
memory/PIDs and tmpfs. Its only writable mount is the raw export directory.

The acquirer joins only an internal Docker network. The proxy joins that network
and an outbound network and accepts only CONNECT to api.kite.trade:443. The client
has closed constructors for POST /session/token and GET /instruments/NSE or
/instruments/historical/<token>/(day|15minute), rejects redirects, and never calls
orders, positions, funds, WebSockets or cancellation. TLS verifies the vendor
certificate end to end. The proxy does not terminate TLS or see credentials.

App key, app secret and request token are entered through hidden local interactive
prompts. Secret and access token remain in memory, never command arguments,
environment variables, persistent files, manifests, logs or exception messages.
The operator completes browser login manually. Export only raw historical and
instrument responses plus non-secret request metadata; never export token-session
responses. No repo, home, credential file, Docker socket or datastore mounts.

The later research consumer must be a separate UID 10002 container with
network disabled, no credential mounts and read-only sealed data. The operator
workstation controls acquisition; it is not an authenticated research runtime.
Do not run a native research process alongside acquisition or move broker secrets
into the research image. This acquisition does not certify the existing native
development environment as a secure research runtime.

Independent reviewer: CONDITIONAL GO to this boundary, conditioned on enforced
outbound host restriction, closed routes and the disjoint mounts described above.

## Acquisition and evidence

First probe INFY and the uniquely identified NSE Nifty 50 index at the old and new
boundaries. A successful probe proves authenticated access and those responses,
not every intervening date or every symbol. Full acquisition uses an explicit
historical request list; today's instrument master supplies token lookup only,
never the historical research universe. Missing or ambiguous token mappings remain
explicit unresolved rows, including delisted or renamed instruments.

Use serial requests at no more than two per second, bounded retries for transient
failures, immediate auth halt, bounded response sizes and disjoint date chunks.
Persist immutable response bytes and UTC retrieval time, byte length, SHA-256,
instrument mapping, requested range, interval and response count/first/last time.
Resume only after checking request identity and existing artifact hashes. Empty
responses are coverage unknown, not proof of a holiday or inactive listing.

Preserve provider timestamps and response bytes. Do not manufacture event or
availability times, original revision identities, corporate actions, calendars,
point-in-time membership or exact point Nifty observations. Acquisition output is
staging material, not an approved canonical simulator bundle. Licence, timestamp,
adjustment and coverage qualification remain independent requirements.

## Verification and execution handoff

### Acquisition-only rejection handling — reviewed 2026-10-14

The first real full download halted on an AARTIDRUGS M15 `SchemaFailure` after
16 history chunks were saved. The failing response was not retained, so its
exact cause is unknown. Do not infer a vendor defect or relax a validator.

Preserve bounded original historical responses with immutable request/hash
identity and a closed, non-secret rejection reason. Isolated candle-quality
rejections (range/order, price envelope or volume/OI validity) halt that request,
keep it unusable, and allow independent raw collection to continue. Malformed
JSON/envelope/status/shape/timestamp syntax, authentication, network failure and
required preflight rejection still halt the acquisition. Any identified 2023+
record halts and is not persisted as a price artifact.

Resume reuses rejected checkpoints without refetching or reclassifying them.
Rejected chunks never appear in accepted coverage. Final reports enumerate the
requested denominator, unresolved names, accepted/empty/rejected request counts
and every rejected range/reason/hash. Atomic completion reports explicitly say
`COMPLETED_WITH_REJECTIONS` or `COMPLETED_UNQUALIFIED`; both retain
`source_qualified=false`. A separate completion-with-rejections exit/status is
shown clearly by the launcher rather than inviting another login loop.

This is raw acquisition behavior, not simulator admission, trading through a
fault, or source approval. Preserve the strict validator and all research holds.
Independent reviewer gives scoped design GO to these conditions. Verify original
rejected-byte retention, continuation across requests/symbols, cached rejection
reuse, structural/auth/preflight halts and exclusion from accepted coverage.

Before accepting real credentials, test endpoint/proxy refusal, redirects,
lockbox guards, secret redaction, auth halt, malformed/oversized responses,
ambiguous mappings, explicit gaps, retry bounds and checkpoint tamper detection
with invented responses. Run targeted tests, strict typing/lint/format, daily
golden regression, independent source review and an actual isolated Docker smoke.
Never claim an authenticated connection or acquired history from mock tests.

Primary provider references checked 2026-10-14:

- https://kite.trade/docs/connect/v3/user/ — operator login and token exchange.
- https://kite.trade/docs/connect/v3/historical/ — candles and day/15minute API.
- https://kite.trade/docs/connect/v3/market-quotes/ — daily current instrument dump.
- https://kite.trade/forum/discussion/16124/historical-15-minute-ohlc-data-availability-pricing-and-api-limits-for-equity-stocks
  — provider reports intraday history from 2015 subject to instrument availability
  and 200-day M15 request maximum. Conservative configured chunks are shorter.

No paid-source claim establishes archival rights or complete delisted coverage.
