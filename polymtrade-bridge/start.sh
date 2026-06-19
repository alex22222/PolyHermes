#!/bin/bash
# Start Polymtrade Bridge as a persistent background service.
# This script is suitable for manual `nohup ./start.sh &` use as well as for
# launchd (~/Library/LaunchAgents/com.polyhermes.polymtrade-bridge.plist).

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
LOG_DIR="${LOG_DIR:-/tmp}"

# Load optional local environment overrides (not committed to git).
if [[ -f "$SCRIPT_DIR/.env" ]]; then
    set -a
    source "$SCRIPT_DIR/.env"
    set +a
fi

export BROWSER_PROXY="${BROWSER_PROXY:-http://127.0.0.1:7890}"

source "$VENV/bin/activate"
cd "$SCRIPT_DIR"
mkdir -p "$LOG_DIR"

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
    pkill -f "python $SCRIPT_DIR/leader_event_poller.py" 2>/dev/null || true
    pkill -f "python $SCRIPT_DIR/log_watcher.py" 2>/dev/null || true
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
