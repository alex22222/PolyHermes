#!/bin/bash
# Run Polyburg Telegram sync in unattended mode.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
LOG_DIR="${LOG_DIR:-$PROJECT_ROOT/logs}"
mkdir -p "$LOG_DIR"

cd "$PROJECT_ROOT"

if [[ -f "$PROJECT_ROOT/.env" ]]; then
    set -a
    # shellcheck source=/dev/null
    source "$PROJECT_ROOT/.env"
    set +a
fi

MODE="${POLYBURG_SYNC_MODE:-auto}"
PYTHON_BIN="${POLYBURG_PYTHON_BIN:-}"

if [[ -z "$PYTHON_BIN" ]]; then
    if [[ -x "/Library/Frameworks/Python.framework/Versions/3.14/bin/python3" ]]; then
        PYTHON_BIN="/Library/Frameworks/Python.framework/Versions/3.14/bin/python3"
    else
        PYTHON_BIN="python3"
    fi
fi

if [[ "$MODE" == "telegram-api" || ( "$MODE" == "auto" && -n "${TELEGRAM_API_ID:-}" && -n "${TELEGRAM_API_HASH:-}" ) ]]; then
    if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import telethon
PY
    then
        if [[ "${POLYBURG_AUTO_INSTALL_DEPS:-false}" == "true" ]]; then
            "$PYTHON_BIN" -m pip install --user telethon
        else
            echo "ERROR: telethon is missing. Install with: $PYTHON_BIN -m pip install telethon" >&2
            exit 1
        fi
    fi
    exec "$PYTHON_BIN" "$PROJECT_ROOT/scripts/sync_polyburg_telegram.py" --import "$@"
fi

if ! "$PYTHON_BIN" - <<'PY' >/dev/null 2>&1
import playwright
PY
then
    if [[ "${POLYBURG_AUTO_INSTALL_DEPS:-false}" == "true" ]]; then
        "$PYTHON_BIN" -m pip install --user playwright
    else
        echo "ERROR: playwright is missing. Install with: $PYTHON_BIN -m pip install playwright" >&2
        exit 1
    fi
fi

exec "$PYTHON_BIN" "$PROJECT_ROOT/scripts/sync_polyburg_web.py" --import --headless "$@"
