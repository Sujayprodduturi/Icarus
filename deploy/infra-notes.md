# infra-notes.md — hosting, static IP, and the SPOF runbook

Companion to `HERMES.md`. Covers what the operator provisions and how to recover the host.
Full rationale in `PRD.md` §18 and §36.6.

## Hosting options (decided at Phase 2, not before)
- **Cloud VM** — AWS `t4g.small` in `ap-south-1` (Mumbai) + a dedicated **Elastic IP** (~₹1,400/mo).
- **Home PC** — viable now that we're equity-first (the live plane only needs NSE hours). Requires a
  **static IP add-on from the ISP** (~₹200–500/mo). Cheaper, but the box holds broker WRITE creds →
  lock it down (disk encryption, dedicated machine, UPS + hotspot failover).

Phases 0–1 need **neither** — no capital, no static IP (data endpoints are IP-exempt).

## The static IP (Phase 2)
Orders may originate ONLY from one IP registered with each broker (SEBI). Whichever host is chosen,
register that single IP with Zerodha (and later Upstox/Delta). Icarus asserts
`egress_ip == registered_static_ip` before any order path each day (invariant #6).

## Clock (required)
Enable NTP (`chrony` on Linux). Icarus asserts clock sync at startup — Delta's HMAC signature is
valid only 5s, and exactly-once order IDs depend on the clock (§36.6).

## SPOF / recovery runbook (VM loss)
1. Relaunch the host from the latest image/backup.
2. **Reattach the SAME static IP** — never release it; the broker whitelist is keyed to it.
3. Restore Postgres from the latest off-box backup (WAL archive or `pg_dump`; cadence ≤ 20 min).
4. Restore/verify Valkey (AOF); confirm the HALT flag state.
5. Re-authenticate (daily-auth); the orchestrator starts in RECOVERY and three-way-reconciles
   against broker truth before any trading (invariant #16). Any unresolved drift → stays halted.
6. RTO target: state it explicitly for your host (e.g. ≤ 30 min) and test it.

## Backups
Postgres WAL archiving (or periodic `pg_dump`) to off-box storage every 15–30 min and on
`POST_CLOSE`. ≥5-year audit retention (SEBI) requires off-box copies regardless.
