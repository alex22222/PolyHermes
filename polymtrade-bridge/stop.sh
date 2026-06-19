#!/bin/bash
# Stop Polymtrade Bridge and Leader Event Poller.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${LOG_DIR:-/tmp}"

if [[ -f "$LOG_DIR/polymtrade-bridge.pid" ]]; then
    kill "$(cat "$LOG_DIR/polymtrade-bridge.pid")" 2>/dev/null || true
    rm -f "$LOG_DIR/polymtrade-bridge.pid"
fi

if [[ -f "$LOG_DIR/polymtrade-event-poller.pid" ]]; then
    kill "$(cat "$LOG_DIR/polymtrade-event-poller.pid")" 2>/dev/null || true
    rm -f "$LOG_DIR/polymtrade-event-poller.pid"
fi

# Legacy log watcher cleanup (remove after migration)
if [[ -f "$LOG_DIR/polymtrade-logwatcher.pid" ]]; then
    kill "$(cat "$LOG_DIR/polymtrade-logwatcher.pid")" 2>/dev/null || true
    rm -f "$LOG_DIR/polymtrade-logwatcher.pid"
fi

pkill -f "python $SCRIPT_DIR/main.py" 2>/dev/null || true
pkill -f "python $SCRIPT_DIR/leader_event_poller.py" 2>/dev/null || true
pkill -f "python $SCRIPT_DIR/log_watcher.py" 2>/dev/null || true

# Remove singleton lock so the next start is not blocked by a stale PID file.
rm -f "$SCRIPT_DIR/.polymtrade-bridge.pid"

echo "Polymtrade Bridge and Leader Event Poller stopped."
