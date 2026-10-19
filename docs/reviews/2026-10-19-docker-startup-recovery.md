# Docker Desktop startup recovery — 2026-10-19

## Failure and evidence

Docker Desktop 4.83.0 failed before engine startup while initializing its inference manager. The host log reported that it could not remove:

`C:\Users\sujay\AppData\Local\Docker\run\dockerInference`

The object existed as a zero-byte `Archive, ReparsePoint` entry. Both `Get-Acl` and `fsutil reparsepoint query` failed on it with Windows error 1920 (`The file cannot be accessed by the system`). The containing `run` directory was an ordinary directory with expected ownership and FullControl ACLs for the user, SYSTEM, and Administrators. This supports classifying `dockerInference` as a stale or otherwise unusable AF_UNIX socket object; it does not prove filesystem corruption.

## Minimal repair

Only the failed Docker Desktop and `com.docker.backend` processes were stopped. The ephemeral IPC directory was preserved by moving it to:

`C:\Users\sujay\AppData\Local\Docker\run.stale-20261019-b6307ce4`

Docker Desktop was then restarted and created a fresh `run` directory. No Docker images, volumes, WSL data, Docker configuration, repository files, or application data were deleted or reset.

## Verification

A fresh `docker info` completed successfully and reported Docker Engine 29.6.2. This verifies that the engine started and the client could reach it after the IPC-directory replacement.

The preserved `run.stale-20261019-b6307ce4` directory may be retained for diagnostic evidence until the operator chooses to remove it. Factory reset, reinstall, and WSL distribution deletion were not used.
