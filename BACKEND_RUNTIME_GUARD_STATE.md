# Backend Runtime Guard State

## Goal

Keep the local Backend available without masking Flyway drift or relying on an operator to restart it.

## Active Controls

- `com.polyhermes.backend-local`: launchd process supervision with `KeepAlive`.
- `com.polyhermes.backend-watchdog`: one-minute business health check.
- Three consecutive failures trigger `launchctl kickstart -k`.
- `scripts/check-applied-migrations.sh`: blocks modified or removed committed migrations before a new jar is built.

## Health Contract

- Liveness: `GET /actuator/health` contains `"status":"UP"`.
- Business readiness: `POST /api/auth/check-first-use` contains `"code":0`.
- Bridge: `GET :8080/health` contains `executor_ready=true`.

## Verification

- Runtime guard tests pass.
- V53 restored to its applied form and database checksum restored to `-119978587`.
- Controlled Java termination recovered automatically from PID `14958` to PID `27453`.
- Backend and Bridge health checks passed after recovery.
