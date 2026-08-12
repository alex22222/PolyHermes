#!/bin/bash
# Build an exact Git commit and safely deploy the backend JAR to production.

set -euo pipefail

PROJECT_ROOT=$(cd "$(dirname "$0")/.." && pwd)
DEPLOY_COMMIT="HEAD"
EXECUTE=false
ALLOW_NEW_MIGRATIONS=false
VPS_HOST="${VPS_HOST:-root@66.135.16.16}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/polymtrade_vultr_ed25519}"
APP_CONTAINER="${APP_CONTAINER:-polyhermes}"
PROD_DIR="${PROD_DIR:-/opt/polyhermes}"

usage() {
    echo "Usage: $0 [--commit <git-ref>] [--execute] [--allow-new-migrations]"
    echo "Without --execute, builds and validates the artifact without replacing production."
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --commit) DEPLOY_COMMIT=${2:?missing Git ref}; shift 2 ;;
        --execute) EXECUTE=true; shift ;;
        --allow-new-migrations) ALLOW_NEW_MIGRATIONS=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

COMMIT=$(git -C "$PROJECT_ROOT" rev-parse --verify "${DEPLOY_COMMIT}^{commit}")
WORK_DIR=$(mktemp -d "${TMPDIR:-/tmp}/polyhermes-release.XXXXXX")
cleanup() {
    rm -rf "$WORK_DIR"
    if [[ -n "${REMOTE_CURRENT:-}" && -n "${REMOTE_GUARD:-}" ]]; then
        "${SSH[@]}" "rm -f '$REMOTE_CURRENT' '$REMOTE_GUARD' '${REMOTE_CANDIDATE:-}'" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

echo "Building immutable Git commit $COMMIT"
git -C "$PROJECT_ROOT" archive "$COMMIT" | tar -x -C "$WORK_DIR"
source "$PROJECT_ROOT/scripts/java-env.sh"
(cd "$WORK_DIR/backend" && ./gradlew bootJar)
CANDIDATE_JAR=$(find "$WORK_DIR/backend/build/libs" -maxdepth 1 -name '*.jar' ! -name '*-plain.jar' -print -quit)
[[ -n "$CANDIDATE_JAR" ]] || { echo "ERROR: backend JAR was not built" >&2; exit 1; }

SSH=(ssh -o BatchMode=yes -o ConnectTimeout=10 -i "$SSH_KEY" "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=10 -i "$SSH_KEY")
REMOTE_ID="polyhermes-release-${COMMIT:0:12}-$$"
REMOTE_CURRENT="/tmp/${REMOTE_ID}-current.jar"
REMOTE_GUARD="/tmp/${REMOTE_ID}-guard.py"
CURRENT_MANIFEST="$WORK_DIR/current-migrations.json"

"${SCP[@]}" "$PROJECT_ROOT/scripts/backend_artifact_guard.py" "$VPS_HOST:$REMOTE_GUARD"
"${SSH[@]}" "docker cp '$APP_CONTAINER:/app/app.jar' '$REMOTE_CURRENT' && python3 '$REMOTE_GUARD' manifest --jar '$REMOTE_CURRENT'" > "$CURRENT_MANIFEST"

GUARD_ARGS=(compare --current-manifest "$CURRENT_MANIFEST" --candidate-jar "$CANDIDATE_JAR")
if [[ "$ALLOW_NEW_MIGRATIONS" == true ]]; then
    GUARD_ARGS+=(--allow-new-migrations)
fi
python3 "$PROJECT_ROOT/scripts/backend_artifact_guard.py" "${GUARD_ARGS[@]}"

LOCAL_SHA=$(shasum -a 256 "$CANDIDATE_JAR" | awk '{print $1}')
echo "Candidate SHA-256: $LOCAL_SHA"
if [[ "$EXECUTE" != true ]]; then
    echo "Validation complete; production was not changed. Re-run with --execute to deploy."
    exit 0
fi

REMOTE_CANDIDATE="/tmp/${REMOTE_ID}-candidate.jar"
BACKUP_JAR="$PROD_DIR/backups/app-before-${COMMIT:0:12}-$(date +%Y%m%d-%H%M%S).jar"
"${SCP[@]}" "$CANDIDATE_JAR" "$VPS_HOST:$REMOTE_CANDIDATE"
REMOTE_SHA=$("${SSH[@]}" "sha256sum '$REMOTE_CANDIDATE'" | awk '{print $1}')
[[ "$REMOTE_SHA" == "$LOCAL_SHA" ]] || { echo "ERROR: uploaded JAR SHA-256 mismatch" >&2; exit 1; }

rollback() {
    echo "Deployment failed; restoring $BACKUP_JAR" >&2
    "${SSH[@]}" "docker cp '$BACKUP_JAR' '$APP_CONTAINER:/app/app.jar' && docker restart '$APP_CONTAINER' >/dev/null"
    "${SSH[@]}" "for i in \$(seq 1 48); do [ \"\$(docker inspect -f '{{.State.Health.Status}}' '$APP_CONTAINER' 2>/dev/null)\" = healthy ] && exit 0; sleep 5; done; exit 1"
}

"${SSH[@]}" "mkdir -p '$PROD_DIR/backups' && docker cp '$APP_CONTAINER:/app/app.jar' '$BACKUP_JAR' && chmod 600 '$BACKUP_JAR' && docker cp '$REMOTE_CANDIDATE' '$APP_CONTAINER:/app/app.jar' && docker restart '$APP_CONTAINER' >/dev/null"

if ! "${SSH[@]}" "for i in \$(seq 1 48); do [ \"\$(docker inspect -f '{{.State.Health.Status}}' '$APP_CONTAINER' 2>/dev/null)\" = healthy ] && code=\$(curl -sS --max-time 10 -o /dev/null -w '%{http_code}' -X POST -H 'Content-Type: application/json' -d '{}' http://127.0.0.1:8088/api/auth/check-first-use || true) && [ \"\$code\" = 200 ] && exit 0; sleep 5; done; exit 1"; then
    rollback
    exit 1
fi

RUNNING_SHA=$("${SSH[@]}" "docker exec '$APP_CONTAINER' sha256sum /app/app.jar" | awk '{print $1}')
if [[ "$RUNNING_SHA" != "$LOCAL_SHA" ]]; then
    rollback
    echo "ERROR: running JAR SHA-256 mismatch" >&2
    exit 1
fi

echo "Deployment complete: $COMMIT ($RUNNING_SHA)"
