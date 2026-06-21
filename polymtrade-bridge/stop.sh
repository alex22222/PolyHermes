#!/bin/bash
# Stop Polymtrade Bridge.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
LOG_DIR="${LOG_DIR:-/tmp}"

if [[ -f "$LOG_DIR/polymtrade-bridge.pid" ]]; then
    kill "$(cat "$LOG_DIR/polymtrade-bridge.pid")" 2>/dev/null || true
    rm -f "$LOG_DIR/polymtrade-bridge.pid"
fi

pkill -f "python $SCRIPT_DIR/main.py" 2>/dev/null || true

# Remove singleton lock so the next start is not blocked by a stale PID file.
rm -f "$SCRIPT_DIR/.polymtrade-bridge.pid"

echo "Polymtrade Bridge stopped."
