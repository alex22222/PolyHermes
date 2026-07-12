#!/bin/bash

set -euo pipefail

PROJECT_ROOT_REAL="$(cd "$(dirname "$0")/.." && pwd)"
TMP_ROOT=$(mktemp -d)
trap 'rm -rf "$TMP_ROOT"' EXIT

mkdir -p "$TMP_ROOT/backend/src/main/resources/db/migration"
git -C "$TMP_ROOT" init -q
git -C "$TMP_ROOT" config user.email test@example.com
git -C "$TMP_ROOT" config user.name Test
printf '%s\n' 'SELECT 1;' > "$TMP_ROOT/backend/src/main/resources/db/migration/V1__init.sql"
git -C "$TMP_ROOT" add .
git -C "$TMP_ROOT" commit -qm init

PROJECT_ROOT="$TMP_ROOT" "$PROJECT_ROOT_REAL/scripts/check-applied-migrations.sh" >/dev/null
printf '%s\n' 'SELECT 2;' > "$TMP_ROOT/backend/src/main/resources/db/migration/V2__new.sql"
PROJECT_ROOT="$TMP_ROOT" "$PROJECT_ROOT_REAL/scripts/check-applied-migrations.sh" >/dev/null
printf '%s\n' 'SELECT 3;' > "$TMP_ROOT/backend/src/main/resources/db/migration/V1__init.sql"
if PROJECT_ROOT="$TMP_ROOT" "$PROJECT_ROOT_REAL/scripts/check-applied-migrations.sh" >/dev/null 2>&1; then
    echo "expected modified migration check to fail" >&2
    exit 1
fi

STATE_FILE="$TMP_ROOT/failures"
LOCK_DIR="$TMP_ROOT/lock"
for expected in 1 2; do
    BACKEND_BASE_URL=http://127.0.0.1:1 \
        BACKEND_WATCHDOG_STATE_FILE="$STATE_FILE" \
        BACKEND_WATCHDOG_LOCK_DIR="$LOCK_DIR" \
        BACKEND_WATCHDOG_DRY_RUN=true \
        "$PROJECT_ROOT_REAL/scripts/backend-watchdog.sh" >/dev/null
    actual=$(cat "$STATE_FILE")
    [[ "$actual" == "$expected" ]] || { echo "expected $expected failures, got $actual" >&2; exit 1; }
done
BACKEND_BASE_URL=http://127.0.0.1:1 \
    BACKEND_WATCHDOG_STATE_FILE="$STATE_FILE" \
    BACKEND_WATCHDOG_LOCK_DIR="$LOCK_DIR" \
    BACKEND_WATCHDOG_DRY_RUN=true \
    "$PROJECT_ROOT_REAL/scripts/backend-watchdog.sh" | grep -q 'would restart'
[[ ! -e "$STATE_FILE" ]] || { echo "failure state was not reset" >&2; exit 1; }

echo "runtime guard tests passed"
