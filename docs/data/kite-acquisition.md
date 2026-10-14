# Connect Kite and acquire historical records

The operator-side downloader runs separately from the simulator. The app secret
and daily access token stay in container memory. It can authenticate and read
the NSE instrument master and historical candles; it has no order workflow.

## First connection and automatic download

Keep Docker Desktop running. From a local PowerShell terminal:

```powershell
& C:\ICARUS\scripts\start_kite_acquisition.ps1 `
  -Mode download `
  -ExportDirectory C:\ICARUS\var\kite-history `
  -SymbolsFile C:\ICARUS\var\kite-acquisition-input\requested-symbols.txt `
  -ProvenanceFile C:\ICARUS\var\kite-acquisition-input\provenance.json `
  -RunId historical-2011-2022-v1
```

1. Enter the app's API key and API secret in the local hidden prompts. Input will
   not appear while typing or pasting. Do not put either value into chat.
2. Open the login URL printed in that terminal in your browser and complete Kite
   login and two-factor authentication yourself.
3. After login, the browser redirects to the app's configured local URL. With the
   initial `http://127.0.0.1/` setup, a connection-refused page is expected because
   no local website is running. The address bar still contains the callback URL.
   Copy that full address into the terminal's hidden request-token prompt. Never
   paste the token into chat. The helper accepts the bare token or a callback on
   `http://127.0.0.1/` or `http://localhost/`; a different configured callback needs
   an explicitly reviewed adjustment.
4. The helper exchanges the short-lived request token, fetches the instrument
   master, and checks nonempty late-2022 15-minute samples for INFY and Nifty 50.
   If those checks succeed, the same session starts the full acquisition.
5. Leave the terminal and Docker running. Progress contains symbol, interval,
   requested dates, status and bytes, never prices or access tokens.

The request set is 693 names from the existing simulator's symbol metadata plus
Nifty 50. This is requested legacy research coverage, not a certified historical
universe. Today's master is only a token lookup. Unresolvable names stay missing;
they are never removed to make the coverage look complete.

## Dates, interruption and output

Daily requests cover 2011-01-01 through 2022-12-31; M15 requests cover
2015-01-01 through 2022-12-31. API request times use IST; stored retrieval and
range instants use UTC. No request includes the 2023+ lockbox.

Requests are serial, at most two per second, with 365-day daily chunks and
90-day M15 chunks. The maximum planned request count is roughly 32,000 before
unresolved names, so allow several hours; this is a rate-limit estimate, not a
measured completion forecast. Progress is checkpointed per successful request.

If interrupted, run the same command with the **same RunId and input files**.
Log in again to create a new daily session. Verified saved chunks are reused;
changed bytes or conflicting input identities refuse. An interrupted, incomplete
artifact pair is retained and refuses rather than being silently overwritten.

Files are under `C:\ICARUS\var\kite-history\download\historical-2011-2022-v1`.
Each request has original response bytes and a hash/metadata manifest. Final
`report.json` lists requested symbols, unresolved names and chunk coverage.
Empty chunks indicate missing/unknown coverage; they do not prove a holiday.

Downloading is not source certification. Before the simulator consumes these
records, separately review coverage, adjustment and timestamp semantics, licence,
point-in-time membership, calendar, opening liquidity and benchmark policy. Kite
candles do not automatically provide exact event/availability-time Nifty points.
Research must consume sealed files in an offline container, with no credentials.
This process performs no strategy evaluation or trading.
