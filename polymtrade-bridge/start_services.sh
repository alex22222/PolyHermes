#!/bin/bash
# Start Polymtrade Bridge as a background daemon.
# Intended for macOS launchd / manual use.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV="$SCRIPT_DIR/.venv"
LOG_DIR="${LOG_DIR:-/tmp}"

export BROWSER_PROXY="${BROWSER_PROXY:-http://127.0.0.1:7890}"

# Activate virtual environment
source "$VENV/bin/activate"

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Stop existing instances (best effort)
kill "$(cat "$LOG_DIR/polymtrade-bridge.pid" 2>/dev/null)" 2>/dev/null || true
pkill -f "python $SCRIPT_DIR/main.py" 2>/dev/null || true

sleep 2

# Start bridge
cd "$SCRIPT_DIR"
nohup python "$SCRIPT_DIR/main.py" > "$LOG_DIR/polymtrade-bridge.log" 2>&1 &
echo $! > "$LOG_DIR/polymtrade-bridge.pid"

echo "Polymtrade Bridge started (pid $(cat "$LOG_DIR/polymtrade-bridge.pid"))"
echo "Logs: $LOG_DIR/polymtrade-bridge.log"
