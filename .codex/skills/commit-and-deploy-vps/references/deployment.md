# PolyHermes VPS deployment map

Use the SSH key already configured on the operator machine:

```text
Host: root@107.191.42.75
Key:  ~/.ssh/polymtrade_vultr_ed25519
Dir:  /opt/polyhermes
Public URL: https://polyhermes.107-191-42-75.sslip.io
```

The former host `66.135.16.16` (instance
`cb1daf46-d38c-4f9b-89c7-02ffc3b5470a`) was permanently destroyed in Vultr on
2026-10-16 after explicit user confirmation and verified local encrypted backup.
It is not a rollback or deployment target; never reconnect, restart or deploy to
that address. The active instance is `98fd7402-d8b8-441c-b92e-df8824b84f00`.

The active private runtime definition is `/opt/polyhermes/.migration/compose.json`
(root-only; contains environment secrets, never print or commit it). Always use
that file explicitly, with `--profile cutover` for app/relay commands. Do not run
the legacy default Compose build/up against restored production data. Current
clean image tags are `polyhermes-app:risk-guard-20261016` and
`polyhermes-bridge:portfolio-recovery-20261016`.

Containers:

```text
polyhermes          backend + Nginx + frontend (127.0.0.1:8088 -> 80)
polymtrade-bridge   Bridge API (127.0.0.1:8080)
polyhermes-mysql    production MySQL (do not replace or reset data)
```

For Bridge-only Python changes, upload the reviewed file, copy it into the running container, restart, and persist the image:

```bash
rsync -av -e 'ssh -i ~/.ssh/polymtrade_vultr_ed25519' \
  polymtrade-bridge/polymtrade_executor.py \
  root@107.191.42.75:/opt/polyhermes/polymtrade-bridge/polymtrade_executor.py
ssh -i ~/.ssh/polymtrade_vultr_ed25519 root@107.191.42.75 \
  'docker cp /opt/polyhermes/polymtrade-bridge/polymtrade_executor.py polymtrade-bridge:/app/polymtrade_executor.py && docker restart polymtrade-bridge'
```

For backend changes, use the guarded deployment script. It builds an exact Git commit in a clean archive, compares its Flyway migration manifest with the running JAR, verifies the upload checksum, backs up the running JAR, checks container and business health, and rolls back on failure:

```bash
# Safe default: build and validate only; production is unchanged.
scripts/deploy-backend-vps.sh --commit <commit>

# Replace production only after the validation succeeds.
scripts/deploy-backend-vps.sh --commit <commit> --execute
```

New migrations are rejected by default. Use `--allow-new-migrations` only when the exact migrations have been separately reviewed and explicitly authorized. Modified or removed existing migrations are always rejected. Never edit `flyway_schema_history` or overwrite the database to make a deployment pass.

For frontend-only changes, build `frontend/dist`, copy the dist directory into `/usr/share/nginx/html` in `polyhermes`, then restart or commit the app image as appropriate. Verify the public page and its referenced asset URLs return 200.

Persist reviewed artifacts using a clean derived image and update the explicit
private runtime definition. Never `docker commit` a production container: its
environment can embed database/JWT/other secrets into the image configuration.

Never expose port 8080, copy `.env`, replace browser profiles, run `docker compose down -v`, or reset MySQL as part of this skill.
