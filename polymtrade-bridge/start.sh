#!/bin/bash
# Start Polymtrade Bridge as a persistent background service.
# This script is suitable for manual `nohup ./start.sh &` use as well as for
# launchd (~/Library/LaunchAgents/com.polyhermes.polymtrade-bridge.plist).

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$SCRIPT_DIR/.venv"
LOG_DIR="${LOG_DIR:-/tmp}"
source "$SCRIPT_DIR/supervisor_health.sh"

# Load project-wide .env first, then bridge-local .env (local wins).
if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    source "$PROJECT_ROOT/.env"
    set +a
fi
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

export BROWSER_PROXY="${BROWSER_PROXY:-http://127.0.0.1:7890}"
export BRIDGE_PORT="${BRIDGE_PORT:-8080}"
export BRIDGE_CODE_SHA="${BRIDGE_CODE_SHA:-$(git -C "$PROJECT_ROOT" rev-parse --short HEAD 2>/dev/null || echo unknown)}"

source "$VENV/bin/activate"
cd "$SCRIPT_DIR"
mkdir -p "$LOG_DIR"
export BRIDGE_HEALTH_EVENT_LOG="${BRIDGE_HEALTH_EVENT_LOG:-$LOG_DIR/polymtrade-health-events.jsonl}"
export BRIDGE_CODE_FINGERPRINT="${BRIDGE_CODE_FINGERPRINT:-$(
    find "$SCRIPT_DIR" -maxdepth 1 -type f \( -name '*.py' -o -name '*.sh' \) -print \
        | LC_ALL=C sort \
        | while IFS= read -r file; do shasum "$file"; done \
        | shasum \
        | awk '{print $1}'
)}"

# Port ownership check: fail fast if BRIDGE_PORT is held by a non-Bridge process.
# This prevents a silent mis-routing where backend calls /portfolio hit the wrong service.
PORT_PIDS=$(lsof -nP -iTCP -sTCP:LISTEN 2>/dev/null | awk -v port=":$BRIDGE_PORT" '$9 !~ /->/ && $9 ~ port "$" {print $2}' | sort -u || true)
if [[ -n "$PORT_PIDS" ]]; then
    for PID in $PORT_PIDS; do
        CMD=$(ps -p "$PID" -o command= 2>/dev/null || true)
        if echo "$CMD" | grep -qE "polymtrade-bridge|main\.py|uvicorn"; then
            echo "Port $BRIDGE_PORT is held by a stale Bridge process (pid $PID); stopping it..."
            kill -9 "$PID" 2>/dev/null || true
        else
            echo "ERROR: Port $BRIDGE_PORT is already used by a non-Bridge process (pid $PID): $CMD"
            echo "Refusing to start Polymtrade Bridge. Free the port or set BRIDGE_PORT to another value."
            exit 1
        fi
    done
fi

request_admission_drain() {
    local headers=()
    if [[ -n "${BRIDGE_ADMIN_SECRET:-}" ]]; then
        headers=(-H "X-Bridge-Admin-Secret: ${BRIDGE_ADMIN_SECRET}")
    fi
    curl -fsS --max-time 2 -X POST "${headers[@]}" \
        "http://127.0.0.1:${BRIDGE_PORT}/admin/drain?reason=planned_restart" \
        >/dev/null 2>&1 || true
}

stop_children() {
    request_admission_drain
    if [[ -f "$LOG_DIR/polymtrade-bridge.pid" ]]; then
        kill "$(cat "$LOG_DIR/polymtrade-bridge.pid")" 2>/dev/null || true
    fi
    # Legacy cleanup
    if [[ -f "$LOG_DIR/polymtrade-event-poller.pid" ]]; then
        kill "$(cat "$LOG_DIR/polymtrade-event-poller.pid")" 2>/dev/null || true
    fi
    if [[ -f "$LOG_DIR/polymtrade-logwatcher.pid" ]]; then
        kill "$(cat "$LOG_DIR/polymtrade-logwatcher.pid")" 2>/dev/null || true
    fi
    pkill -f "python $SCRIPT_DIR/main.py" 2>/dev/null || true
}

# Clean up children when launchd stops the job (or the user hits Ctrl-C).
trap 'stop_children; exit' TERM INT

# Stop any existing instances before starting.
stop_children

# Wait for the previous Chromium process to fully release the persistent
# browser profile. Without this, launch_persistent_context may attach to an
# existing session and immediately close, causing a restart loop.
echo "Waiting for previous browser process to release profile..."
for i in {1..30}; do
    if ! pgrep -f "user-data-dir=$SCRIPT_DIR/browser_profile" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

# A crashed child can leave Chromium alive and keep the persistent profile
# locked. This profile is exclusively owned by this Bridge service, so after
# the bounded wait it is safe to terminate only matching Chromium processes.
if pgrep -f "user-data-dir=$SCRIPT_DIR/browser_profile" >/dev/null 2>&1; then
    echo "Stale Chromium process still owns Bridge profile; stopping it..."
    pkill -TERM -f "user-data-dir=$SCRIPT_DIR/browser_profile" 2>/dev/null || true
    sleep 2
    pkill -KILL -f "user-data-dir=$SCRIPT_DIR/browser_profile" 2>/dev/null || true
fi

# Remove stale singleton lock from a previous crash.
rm -f "$SCRIPT_DIR/.polymtrade-bridge.pid"

# Start Bridge
nohup python "$SCRIPT_DIR/main.py" > "$LOG_DIR/polymtrade-bridge.log" 2>&1 &
echo $! > "$LOG_DIR/polymtrade-bridge.pid"

echo "Polymtrade Bridge started (pid $(cat "$LOG_DIR/polymtrade-bridge.pid"))"
echo "Logs: $LOG_DIR/polymtrade-bridge.log"

STARTED_AT=$(date +%s)
HEALTH_FAILURES=0
HEALTH_FAILURE_THRESHOLD="${BRIDGE_HEALTH_FAILURE_THRESHOLD:-3}"
STARTUP_GRACE_SECONDS="${BRIDGE_STARTUP_GRACE_SECONDS:-240}"
LAST_HEALTH_OK_EVENT_AT=0
record_health_event service_start

# Keep this script alive so launchd can supervise the child.
# If the child dies, exit so launchd can restart the job.
while true; do
    if [[ ! -f "$LOG_DIR/polymtrade-bridge.pid" ]]; then
        echo "PID file disappeared, bridge may have exited unexpectedly"
        break
    fi
    PID="$(cat "$LOG_DIR/polymtrade-bridge.pid" 2>/dev/null || true)"
    if [[ -z "$PID" ]] || ! kill -0 "$PID" 2>/dev/null; then
        record_health_event child_exit
        echo "Bridge process (pid $PID) is no longer running"
        break
    fi
    # A live Python process is not sufficient: the Playwright browser context
    # can die while the HTTP server remains up. After startup grace, make the
    # launchd job restart the child when the fail-closed health probe fails.
    NOW=$(date +%s)
    if (( NOW - STARTED_AT >= STARTUP_GRACE_SECONDS )); then
        if curl -fsS --max-time 5 "http://127.0.0.1:${BRIDGE_PORT}/health" >/dev/null 2>&1; then
            record_health_probe success
            if (( NOW - LAST_HEALTH_OK_EVENT_AT >= 3600 )); then
                record_health_event health_ok
                LAST_HEALTH_OK_EVENT_AT=$NOW
            fi
        else
            record_health_probe failure
            echo "Bridge health probe failed (${HEALTH_FAILURES}/${HEALTH_FAILURE_THRESHOLD})"
            if health_restart_required; then
                record_health_event restart_threshold
                echo "Bridge health probe failure threshold reached; stopping child so launchd can restart it"
                kill "$PID" 2>/dev/null || true
                break
            fi
        fi
    fi
    sleep 5
done

stop_children
exit 1
