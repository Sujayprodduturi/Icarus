# systemd units

Process definitions for the Linux deploy host. Each plane/process is its own unit so they restart
and are resource-governed independently (PRD §18, §39.1).

- **`icarus-alerting.service`** — the alerting/kill process. Runs as its OWN unit, **started before
  the orchestrator**, so the kill path survives a wedged orchestrator (invariant #17). Ready now.
- **`icarus-orchestrator.service`** — *arrives in Phase 1* with the orchestrator's run-loop
  entrypoint. It will carry the resource limits (`CPUWeight`, `MemoryMax`) that keep research work
  from preempting the live plane (§39.1). Not shipped yet because the entrypoint doesn't exist —
  we don't ship a unit that points at nothing.

Install (once both exist):
```bash
sudo cp deploy/systemd/*.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now icarus-alerting.service      # kill process first
# sudo systemctl enable --now icarus-orchestrator.service  # Phase 1+
```
