---
name: commit-and-deploy-vps
description: Safely commit requested PolyHermes code changes and deploy them to the configured Vultr VPS, with scoped staging, secret protection, tests, container updates, and post-deploy health checks. Use when the user asks to提交代码、创建 Git commit、发布、部署、同步到服务器、更新 VPS, or asks to automate this workflow for the PolyHermes project.
---

# Commit and deploy PolyHermes

Use this skill only for `/Users/henry/projects/polyhermes`. Treat committing and production deployment as two explicit phases: validate and commit the requested code, then deploy only the components affected by the diff.

## Workflow

1. Inspect before changing state:

   ```bash
   git status --short
   git diff --stat
   git diff --check
   ```

   Read the files being deployed and identify whether the change affects `backend/`, `frontend/`, or `polymtrade-bridge/`. Do not stage unrelated work.

2. Run the narrowest relevant verification, then broader checks when practical:

   - Backend: `source scripts/java-env.sh && (cd backend && ./gradlew compileKotlin)`.
   - Frontend: `(cd frontend && npm run build)`.
   - Bridge: `polymtrade-bridge/.venv/bin/python -m pytest -q polymtrade-bridge/test_portfolio_parser.py` (add the relevant suite when needed).

   Report pre-existing failures instead of hiding or “fixing” unrelated tests.

3. Protect secrets before staging. Never commit `.env`, private keys, browser profiles, databases, logs, build artifacts, or credentials. Run `scripts/commit_guard.sh` after staging; it rejects common secret paths and secret-shaped files.

4. Stage exact paths and commit with a specific message. Do not use `git add .` or amend an existing commit unless the user explicitly requests it:

   ```bash
   git add <reviewed paths>
   scripts/commit_guard.sh
   git diff --cached --check
   git commit -m "<specific change>"
   ```

5. Deploy only the affected component. Read [deployment.md](references/deployment.md) for the current VPS address, SSH key, container names, and component-specific commands. Preserve production data and browser profiles. Do not run destructive Docker or database commands.

6. Verify after deployment:

   - Container is running and the relevant health endpoint responds.
   - Public site returns HTTP 200 when a frontend change was deployed.
   - Bridge `/portfolio` or `/status` is healthy when Bridge code changed.
   - Backend logs show successful startup and no migration checksum failure.
   - Re-check `git status --short` and report the commit hash, deployed components, and any remaining warnings.

## Safety rules

- Ask before deploying if the user asked only for a commit, or before enabling live trading.
- Never expose Bridge port `8080` publicly.
- Never overwrite VPS MySQL data, `.env`, or `browser_profile`.
- Do not claim “deployed” until a post-deploy check succeeds.
- If SSH is unreachable, stop and report the exact command/error; do not retry destructive operations.

## Bundled resource

- `scripts/commit_guard.sh` checks the staged index for secret and runtime paths before a commit.
- [references/deployment.md](references/deployment.md) contains the PolyHermes VPS deployment map and safe component commands.
