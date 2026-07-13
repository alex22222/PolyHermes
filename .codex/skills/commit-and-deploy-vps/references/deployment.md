# PolyHermes VPS deployment map

Use the SSH key already configured on the operator machine:

```text
Host: root@66.135.16.16
Key:  ~/.ssh/polymtrade_vultr_ed25519
Dir:  /opt/polyhermes
Public URL: https://polyhermes.66-135-16-16.sslip.io
```

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
  root@66.135.16.16:/opt/polyhermes/polymtrade-bridge/polymtrade_executor.py
ssh -i ~/.ssh/polymtrade_vultr_ed25519 root@66.135.16.16 \
  'docker cp /opt/polyhermes/polymtrade-bridge/polymtrade_executor.py polymtrade-bridge:/app/polymtrade_executor.py && docker restart polymtrade-bridge'
```

For backend changes, build `backend/build/libs/*.jar`, transfer it to `/tmp`, copy it to `/app/app.jar`, restart `polyhermes`, and wait for the application startup health check. Check the production Flyway checksum before building; never edit `flyway_schema_history` or overwrite the database to make a deployment pass.

For frontend-only changes, build `frontend/dist`, copy the dist directory into `/usr/share/nginx/html` in `polyhermes`, then restart or commit the app image as appropriate. Verify the public page and its referenced asset URLs return 200.

After any container mutation, persist the reviewed runtime state with an explicit image tag only when the deployment workflow requires it:

```bash
docker commit polymtrade-bridge polyhermes-bridge:linux-amd64
docker commit polyhermes polyhermes-app:linux-amd64
```

Never expose port 8080, copy `.env`, replace browser profiles, run `docker compose down -v`, or reset MySQL as part of this skill.
