#!/bin/bash
# Start Polymtrade Bridge as a persistent background service.
# This script is suitable for manual `nohup ./start.sh &` use as well as for
# launchd (~/Library/LaunchAgents/com.polyhermes.polymtrade-bridge.plist).

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
VENV="$SCRIPT_DIR/.venv"
LOG_DIR="${LOG_DIR:-/tmp}"

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

source "$VENV/bin/activate"
cd "$SCRIPT_DIR"
mkdir -p "$LOG_DIR"

# Port ownership check: fail fast if BRIDGE_PORT is held by a non-Bridge process.
# This prevents a silent mis-routing where backend calls /portfolio hit the wrong service.
PORT_PIDS=$(lsof -i ":$BRIDGE_PORT" -t 2>/dev/null || true)
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

stop_children() {
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

# Remove stale singleton lock from a previous crash.
rm -f "$SCRIPT_DIR/.polymtrade-bridge.pid"

# Start Bridge
nohup python "$SCRIPT_DIR/main.py" > "$LOG_DIR/polymtrade-bridge.log" 2>&1 &
echo $! > "$LOG_DIR/polymtrade-bridge.pid"

echo "Polymtrade Bridge started (pid $(cat "$LOG_DIR/polymtrade-bridge.pid"))"
echo "Logs: $LOG_DIR/polymtrade-bridge.log"

# Keep this script alive so launchd can supervise the child.
# If the child dies, exit so launchd can restart the job.
while true; do
    if [[ ! -f "$LOG_DIR/polymtrade-bridge.pid" ]]; then
        echo "PID file disappeared, bridge may have exited unexpectedly"
        break
    fi
    PID="$(cat "$LOG_DIR/polymtrade-bridge.pid" 2>/dev/null || true)"
    if [[ -z "$PID" ]] || ! kill -0 "$PID" 2>/dev/null; then
        echo "Bridge process (pid $PID) is no longer running"
        break
    fi
    sleep 5
done

stop_children
exit 1
