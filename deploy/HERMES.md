# HERMES.md — deployment runbook for the Hermes agent

This runbook is written **for an agent** deploying Icarus on the Linux PC. Follow it top to
bottom. Do not improvise around a failed step — if a check fails, stop and report it. Nothing here
places a live order (Phase 0–1 has no order path), so it is safe to run end to end.

## Preconditions
- Linux host (Ubuntu 22.04+ or similar), Python 3.12, `git`, and Docker (or a native Postgres 16 +
  Valkey 8). ~4 GiB RAM.
- Network access to GitHub and to PyPI.
- **Secrets are NOT in the repo.** You will create a local `.env` from `.env.example`. Never commit it.

## 1. Get the code
```bash
git clone https://github.com/Sujayprodduturi/Icarus.git
cd Icarus
git checkout dev          # dev = latest working code; main = last blessed milestone
```

## 2. Install the toolchain
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh    # if uv is not present
uv sync --extra dev --extra crypto
```
On Linux the normal (compiled) mypy installs fine — no special handling needed (the Windows dev box
pins a pure-Python mypy; that pin is harmless here).

## 3. Start the datastores
```bash
docker compose -f deploy/compose.yaml up -d
docker compose -f deploy/compose.yaml ps        # both must be "healthy"
```
(Or point `ICARUS_PG_DSN` / `ICARUS_VALKEY_URL` at a native Postgres/Valkey.)

## 4. Configure
```bash
cp .env.example .env
# Fill in ONLY what this phase needs. Phases 0–1 need no broker WRITE keys and no static IP.
export ICARUS_PG_DSN="postgresql+psycopg://icarus:icarus@localhost:5432/icarus"
export ICARUS_VALKEY_URL="redis://localhost:6379/0"
```

## 5. Create the database schema
```bash
uv run alembic upgrade head
```

## 6. Verification checklist — ALL must pass before reporting success
Run each; every one must be green.
```bash
uv run ruff check .                 # lint: "All checks passed!"
uv run ruff format --check .        # format: no files would be reformatted
uv run mypy                         # types: "Success: no issues found"
uv run pytest -q                    # unit + integration tests: all pass
```
Then confirm the Phase-0 safety properties explicitly:
```bash
# a) No order-placement path exists anywhere:
uv run pytest tests/unit/test_no_order_path.py -q

# b) The audit log is append-only at the DB level (UPDATE/DELETE must FAIL):
docker exec icarus-postgres-1 psql -U icarus -d icarus \
  -c "INSERT INTO audit_log(event_type,payload) VALUES('hermes_check','{}'::jsonb);"
docker exec icarus-postgres-1 psql -U icarus -d icarus \
  -c "UPDATE audit_log SET event_type='x' WHERE event_type='hermes_check';"   # expect ERROR: append-only

# c) The HALT flag round-trips through Valkey:
docker exec icarus-valkey-1 valkey-cli set icarus:halt '{"reason":"hermes-check","source":"hermes","set_at":"now"}'
docker exec icarus-valkey-1 valkey-cli get icarus:halt
docker exec icarus-valkey-1 valkey-cli del icarus:halt
```

Report success ONLY if steps 6a–6c behave as annotated (tests green; the UPDATE is rejected with
an "append-only" error; the HALT flag reads back then clears).

## 7. Services (later — not required to pass Phase 0)
`deploy/systemd/` holds the unit for the separate alerting/kill process, which runs as its OWN unit
(it must outlive the orchestrator — invariant #17). The orchestrator unit ships in Phase 1 with its
run-loop entrypoint. See `deploy/systemd/README.md`.
```bash
sudo cp deploy/systemd/icarus-alerting.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now icarus-alerting.service    # the kill process
```

## Do NOT
- Do not commit `.env` or any secret.
- Do not enable any live-order path — none exists before Phase 2, and only after the operator
  reviews the Phase-1 metric sheet.
- Do not `git push` to `main`; deploy from `dev` and let the operator promote to `main`.
