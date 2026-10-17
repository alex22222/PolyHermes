#!/bin/bash
set -euo pipefail
FUTURE_INSTALL_ROOT="$(cd -- "$(dirname -- "$0")" && pwd)"
if [[ $# -eq 0 ]]; then
    set -- doctor
fi
if [[ -x "$FUTURE_INSTALL_ROOT/.venv/bin/python" ]]; then
    exec "$FUTURE_INSTALL_ROOT/.venv/bin/python" "$FUTURE_INSTALL_ROOT/manage.py" --root "$FUTURE_INSTALL_ROOT" "$@"
fi
FUTURE_FRAMEWORK_PYTHON="/Library/Frameworks/Python.framework/Versions/3.13/bin/python3.13"
if [[ -x "$FUTURE_FRAMEWORK_PYTHON" ]]; then
    exec "$FUTURE_FRAMEWORK_PYTHON" "$FUTURE_INSTALL_ROOT/manage.py" --root "$FUTURE_INSTALL_ROOT" "$@"
fi
exec /usr/bin/env python3 "$FUTURE_INSTALL_ROOT/manage.py" --root "$FUTURE_INSTALL_ROOT" "$@"
