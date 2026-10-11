#!/bin/bash
# Foreground private SSH transport only; no trading controls or daemon setup.
set -euo pipefail

FUTURE_TUNNEL_HOST="root@66.135.16.16"
FUTURE_TUNNEL_KEY="$HOME/.ssh/polymtrade_vultr_ed25519"
REMOVE_STALE_SOCKET=false
SOCKS_PROXY=""
FUTURE_TUNNEL_CHILD=""
RETRY_SECONDS=5

usage() {
    echo "Usage: bash scripts/start-future-btc5m-tunnel.sh [--remove-stale-socket] [--socks-proxy 127.0.0.1:PORT]"
    echo "Keep this foreground process running to connect the production relay to the local assistant."
    echo "The optional recovery removes only the fixed Unix socket after its connection is refused."
    echo "SSH disconnects retry in 5/10/20/30 seconds; Ctrl-C or TERM stops reconnecting."
    echo "--socks-proxy sends both SSH connections through a local SOCKS5 proxy when direct port 22 is unreliable."
}

while [[ $# -gt 0 ]]; do
    case "$1" in
        --remove-stale-socket) REMOVE_STALE_SOCKET=true; shift ;;
        # Loopback only: the proxy is the operator's own local client, never a remote relay.
        --socks-proxy)
            [[ $# -ge 2 && "$2" =~ ^127\.0\.0\.1:([1-9][0-9]{0,4})$ && "${BASH_REMATCH[1]}" -le 65535 ]] || { usage >&2; exit 2; }
            SOCKS_PROXY="$2"; shift 2 ;;
        -h|--help) usage; exit 0 ;;
        *) usage >&2; exit 2 ;;
    esac
done

stop_tunnel() {
    trap - INT TERM
    if [[ -n "$FUTURE_TUNNEL_CHILD" ]]; then
        kill -TERM "$FUTURE_TUNNEL_CHILD" 2>/dev/null || true
        wait "$FUTURE_TUNNEL_CHILD" 2>/dev/null || true
    fi
    exit "$1"
}
trap 'stop_tunnel 130' INT
trap 'stop_tunnel 143' TERM

run_foreground() {
    local result=0
    "$@" <&0 &
    FUTURE_TUNNEL_CHILD=$!
    wait "$FUTURE_TUNNEL_CHILD" || result=$?
    FUTURE_TUNNEL_CHILD=""
    return "$result"
}

[[ -r "$FUTURE_TUNNEL_KEY" ]] || { echo "Configured SSH key is unavailable" >&2; exit 1; }
command -v ssh >/dev/null || { echo "SSH is unavailable" >&2; exit 1; }
PROXY_OPTIONS=()
if [[ -n "$SOCKS_PROXY" ]]; then
    command -v nc >/dev/null || { echo "nc is unavailable for the SOCKS proxy" >&2; exit 1; }
    PROXY_OPTIONS=(-o "ProxyCommand=nc -X 5 -x $SOCKS_PROXY %h %p")
fi
run_foreground curl --noproxy '*' -fsS --max-time 3 -o /dev/null http://127.0.0.1:8766/status || {
    echo "Local Future assistant is unavailable on 127.0.0.1:8766" >&2
    exit 1
}

SSH=(ssh -T -o BatchMode=yes -o ConnectTimeout=10 -o ControlMaster=no -o ControlPath=none
     -o ServerAliveInterval=15 -o ServerAliveCountMax=3 ${PROXY_OPTIONS[@]+"${PROXY_OPTIONS[@]}"}
     -i "$FUTURE_TUNNEL_KEY" "$FUTURE_TUNNEL_HOST")

check_socket() {
    run_foreground "${SSH[@]}" python3 - "$REMOVE_STALE_SOCKET" <<'PY'
import errno
import os
import socket
import stat
import sys

path = "/opt/polyhermes/future-btc5m/assistant.sock"
try:
    before = os.lstat(path)
except FileNotFoundError:
    print("Fixed tunnel socket does not exist; no recovery needed")
    raise SystemExit(0)
if not stat.S_ISSOCK(before.st_mode):
    raise SystemExit("Refusing recovery: fixed path is not a Unix socket")
if sys.argv[1] != "true":
    raise SystemExit("Refusing startup: fixed tunnel socket already exists; use explicit stale-socket recovery")
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
}

retry_tunnel() {
    echo "Future SSH transport disconnected; retrying in $RETRY_SECONDS seconds" >&2
    run_foreground sleep "$RETRY_SECONDS"
    RETRY_SECONDS=$((RETRY_SECONDS * 2))
    [[ "$RETRY_SECONDS" -le 30 ]] || RETRY_SECONDS=30
}

while true; do
    result=0
    check_socket || result=$?
    if [[ "$result" -eq 255 ]]; then
        retry_tunnel
        continue
    fi
    [[ "$result" -eq 0 ]] || exit "$result"

    echo "Starting foreground Future private tunnel; stop with Ctrl-C"
    run_foreground ssh -T -N -o BatchMode=yes -o ConnectTimeout=10 -o ControlMaster=no -o ControlPath=none \
        -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 \
        -o StreamLocalBindUnlink=no -o StreamLocalBindMask=0177 ${PROXY_OPTIONS[@]+"${PROXY_OPTIONS[@]}"} \
        -i "$FUTURE_TUNNEL_KEY" \
        -R /opt/polyhermes/future-btc5m/assistant.sock:127.0.0.1:8766 "$FUTURE_TUNNEL_HOST" || result=$?
    [[ "$result" -eq 255 ]] || exit "$result"
    REMOVE_STALE_SOCKET=true
    retry_tunnel
done
