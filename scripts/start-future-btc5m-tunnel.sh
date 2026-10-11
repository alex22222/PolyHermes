#!/bin/bash
# Foreground private SSH transport only; no trading controls or daemon setup.
set -euo pipefail

FUTURE_TUNNEL_HOST="root@66.135.16.16"
FUTURE_TUNNEL_KEY="$HOME/.ssh/polymtrade_vultr_ed25519"
REMOVE_STALE_SOCKET=false

usage() {
    echo "Usage: bash scripts/start-future-btc5m-tunnel.sh [--remove-stale-socket]"
    echo "Keep this foreground process running to connect the production relay to the local assistant."
    echo "The optional recovery removes only the fixed Unix socket after its connection is refused."
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --remove-stale-socket) REMOVE_STALE_SOCKET=true; shift ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

[[ -r "$FUTURE_TUNNEL_KEY" ]] || { echo "Configured SSH key is unavailable" >&2; exit 1; }
command -v ssh >/dev/null || { echo "SSH is unavailable" >&2; exit 1; }
curl --noproxy '*' -fsS --max-time 3 -o /dev/null http://127.0.0.1:8766/status || {
    echo "Local Future assistant is unavailable on 127.0.0.1:8766" >&2
    exit 1
}

SSH=(ssh -T -o BatchMode=yes -o ConnectTimeout=10 -o ControlMaster=no -o ControlPath=none
     -i "$FUTURE_TUNNEL_KEY" "$FUTURE_TUNNEL_HOST")

if [[ "$REMOVE_STALE_SOCKET" == true ]]; then
    "${SSH[@]}" python3 - <<'PY'
import errno
import os
import socket
import stat

path = "/opt/polyhermes/future-btc5m/assistant.sock"
try:
    before = os.lstat(path)
except FileNotFoundError:
    print("Fixed tunnel socket does not exist; no recovery needed")
    raise SystemExit(0)
if not stat.S_ISSOCK(before.st_mode):
    raise SystemExit("Refusing recovery: fixed path is not a Unix socket")
connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
connection.settimeout(2)
try:
    connection.connect(path)
except OSError as error:
    if error.errno != errno.ECONNREFUSED:
        raise SystemExit("Refusing recovery: socket is not confirmed stale")
else:
    raise SystemExit("Refusing recovery: tunnel socket is active")
finally:
    connection.close()
after = os.lstat(path)
if not stat.S_ISSOCK(after.st_mode) or (before.st_dev, before.st_ino) != (after.st_dev, after.st_ino):
    raise SystemExit("Refusing recovery: fixed socket changed during inspection")
os.unlink(path)
print("Removed only the confirmed stale Future tunnel socket")
PY
fi

echo "Starting foreground Future private tunnel; stop with Ctrl-C"
exec ssh -T -N -o BatchMode=yes -o ConnectTimeout=10 -o ControlMaster=no -o ControlPath=none \
    -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
    -o StreamLocalBindUnlink=no -o StreamLocalBindMask=0177 \
    -i "$FUTURE_TUNNEL_KEY" \
    -R /opt/polyhermes/future-btc5m/assistant.sock:127.0.0.1:8766 "$FUTURE_TUNNEL_HOST"
