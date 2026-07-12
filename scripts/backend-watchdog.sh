#!/bin/bash
# Restart the launchd-supervised backend after three consecutive business probe failures.

set -euo pipefail

BASE_URL="${BACKEND_BASE_URL:-http://127.0.0.1:8000}"
STATE_FILE="${BACKEND_WATCHDOG_STATE_FILE:-/tmp/polyhermes-backend-watchdog.failures}"
LOCK_DIR="${BACKEND_WATCHDOG_LOCK_DIR:-/tmp/polyhermes-backend-watchdog.lock}"
LABEL="${BACKEND_LAUNCHD_LABEL:-com.polyhermes.backend-local}"
THRESHOLD="${BACKEND_WATCHDOG_THRESHOLD:-3}"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

actuator=$(curl -fsS --max-time 8 "$BASE_URL/actuator/health" 2>/dev/null || true)
business=$(curl -fsS --max-time 8 -X POST "$BASE_URL/api/auth/check-first-use" 2>/dev/null || true)

if [[ "$actuator" == *'"status":"UP"'* && "$business" == *'"code":0'* ]]; then
    rm -f "$STATE_FILE"
    exit 0
fi

failures=0
if [[ -f "$STATE_FILE" ]]; then
    failures=$(cat "$STATE_FILE" 2>/dev/null || echo 0)
fi
if ! [[ "$failures" =~ ^[0-9]+$ ]]; then
    failures=0
fi
failures=$((failures + 1))
printf '%s\n' "$failures" > "$STATE_FILE"
echo "Backend probe failed ($failures/$THRESHOLD): actuator=${actuator:-unavailable}, business=${business:-unavailable}"

if (( failures < THRESHOLD )); then
    exit 0
fi

rm -f "$STATE_FILE"
if [[ "${BACKEND_WATCHDOG_DRY_RUN:-false}" == "true" ]]; then
    echo "Dry run: would restart $LABEL"
    exit 0
fi

echo "Restarting $LABEL after $failures consecutive failures"
launchctl kickstart -k "gui/$(id -u)/$LABEL"
