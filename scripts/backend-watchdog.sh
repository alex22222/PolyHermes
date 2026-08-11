#!/bin/bash
# Restart the launchd-supervised backend after three consecutive business probe failures.

set -euo pipefail

BASE_URL="${BACKEND_BASE_URL:-http://127.0.0.1:8000}"
STATE_FILE="${BACKEND_WATCHDOG_STATE_FILE:-/tmp/polyhermes-backend-watchdog.failures}"
LOCK_DIR="${BACKEND_WATCHDOG_LOCK_DIR:-/tmp/polyhermes-backend-watchdog.lock}"
LABEL="${BACKEND_LAUNCHD_LABEL:-com.polyhermes.backend-local}"
PLIST="${BACKEND_LAUNCHD_PLIST:-$HOME/Library/LaunchAgents/${LABEL}.plist}"
DOMAIN="gui/$(id -u)"
THRESHOLD="${BACKEND_WATCHDOG_THRESHOLD:-3}"
STARTUP_GRACE_SECONDS="${BACKEND_WATCHDOG_STARTUP_GRACE_SECONDS:-600}"
SERVICE_PID="${BACKEND_WATCHDOG_SERVICE_PID:-$(pgrep -f 'backend-local\.jar' | head -n 1 || true)}"

if ! mkdir "$LOCK_DIR" 2>/dev/null; then
    exit 0
fi
trap 'rmdir "$LOCK_DIR" 2>/dev/null || true' EXIT

elapsed_seconds_for_pid() {
    local elapsed="$1"
    local days=0
    local first second third

    if [[ "$elapsed" == *-* ]]; then
        days="${elapsed%%-*}"
        elapsed="${elapsed#*-}"
    fi
    IFS=: read -r first second third <<< "$elapsed"
    if [[ -z "$third" ]]; then
        third="$second"
        second="$first"
        first=0
    fi
    printf '%s\n' $((days * 86400 + first * 3600 + second * 60 + third))
}

if [[ -n "$SERVICE_PID" && "$STARTUP_GRACE_SECONDS" =~ ^[0-9]+$ ]]; then
    elapsed=$(ps -o etime= -p "$SERVICE_PID" 2>/dev/null | tr -d ' ' || true)
    elapsed_seconds=$(elapsed_seconds_for_pid "$elapsed" 2>/dev/null || true)
    if [[ "$elapsed_seconds" =~ ^[0-9]+$ ]] && (( elapsed_seconds < STARTUP_GRACE_SECONDS )); then
        rm -f "$STATE_FILE"
        echo "Backend startup grace active (${elapsed_seconds}s/${STARTUP_GRACE_SECONDS}s): pid=$SERVICE_PID"
        exit 0
    fi
fi

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
if ! launchctl print "$DOMAIN/$LABEL" >/dev/null 2>&1; then
    if [[ ! -f "$PLIST" ]]; then
        echo "Cannot restart $LABEL: launchd service is not loaded and plist is missing: $PLIST"
        exit 1
    fi
    echo "Launchd service $LABEL is not loaded; bootstrapping $PLIST"
    launchctl bootstrap "$DOMAIN" "$PLIST" 2>/dev/null || true
fi
launchctl kickstart -k "$DOMAIN/$LABEL"
