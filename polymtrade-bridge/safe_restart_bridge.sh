#!/bin/bash
# Safely reload the launchd-managed Bridge.
#
# Default mode is check-only. Pass --execute to restart. This first reload after
# adding /admin/drain cannot rely on the running process to support draining, so
# check-only stays read-only and execute falls back to a stable signals_received
# counter when the running build does not expose admission state.

set -euo pipefail

LABEL="${BRIDGE_LAUNCHD_LABEL:-com.polyhermes.polymtrade-bridge}"
PORT="${BRIDGE_PORT:-8080}"
QUIET_SECONDS="${BRIDGE_RESTART_QUIET_SECONDS:-45}"
STARTUP_GRACE_SECONDS="${BRIDGE_STARTUP_GRACE_SECONDS:-240}"
POST_START_TIMEOUT="${BRIDGE_RESTART_POST_START_TIMEOUT:-$((STARTUP_GRACE_SECONDS + 60))}"
DRAIN_TIMEOUT="${BRIDGE_RESTART_DRAIN_TIMEOUT:-30}"
EXECUTE=0

if [[ "${1:-}" == "--execute" ]]; then
    EXECUTE=1
elif [[ $# -gt 0 ]]; then
    echo "usage: $0 [--execute]" >&2
    exit 64
fi

fetch_metrics() {
    curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/metrics"
}

json_value() {
    local expr="$1"
    python -c "import json,sys; data=json.load(sys.stdin); value=${expr}; print('' if value is None else value)"
}

signals_received() {
    json_value "data.get('metrics', {}).get('signals_received', 0)"
}

queue_depth() {
    json_value "data.get('metrics', {}).get('signal_queue_depth', 0)"
}

accepting_signals() {
    json_value "data.get('metrics', {}).get('accepting_signals')"
}

request_admission_drain() {
    if [[ -n "${BRIDGE_ADMIN_SECRET:-}" ]]; then
        curl -fsS --max-time 2 -X POST \
            -H "X-Bridge-Admin-Secret: ${BRIDGE_ADMIN_SECRET}" \
            "http://127.0.0.1:${PORT}/admin/drain?reason=safe_restart" \
            >/dev/null
        return
    fi
    curl -fsS --max-time 2 -X POST \
        "http://127.0.0.1:${PORT}/admin/drain?reason=safe_restart" \
        >/dev/null
}

require_healthy() {
    curl -fsS --max-time 3 "http://127.0.0.1:${PORT}/health" >/dev/null
}

echo "Checking Bridge health on port ${PORT}..."
require_healthy

before_metrics="$(fetch_metrics)"
before_signals="$(printf '%s' "$before_metrics" | signals_received)"
before_queue="$(printf '%s' "$before_metrics" | queue_depth)"
before_accepting="$(printf '%s' "$before_metrics" | accepting_signals)"

if [[ "$before_queue" != "0" ]]; then
    echo "Bridge signal queue is not empty: depth=${before_queue}" >&2
    exit 2
fi

if [[ "$EXECUTE" == "1" && ( "$before_accepting" == "True" || "$before_accepting" == "False" ) ]]; then
    echo "Requesting admission drain before restart..."
    if ! request_admission_drain; then
        echo "Admission drain request failed; refusing to restart." >&2
        exit 2
    fi

    deadline=$(( $(date +%s) + DRAIN_TIMEOUT ))
    while (( $(date +%s) < deadline )); do
        drain_metrics="$(fetch_metrics)"
        drain_queue="$(printf '%s' "$drain_metrics" | queue_depth)"
        drain_accepting="$(printf '%s' "$drain_metrics" | accepting_signals)"
        if [[ "$drain_queue" == "0" && "$drain_accepting" == "False" ]]; then
            echo "Admission drained: queue_depth=0 accepting_signals=False"
            break
        fi
        sleep 1
    done

    final_metrics="$(fetch_metrics)"
    final_queue="$(printf '%s' "$final_metrics" | queue_depth)"
    final_accepting="$(printf '%s' "$final_metrics" | accepting_signals)"

    if [[ "$final_queue" != "0" || "$final_accepting" != "False" ]]; then
        echo "Bridge did not drain before restart: queue_depth=${final_queue} accepting_signals=${final_accepting}" >&2
        exit 2
    fi
else
echo "Waiting for quiet signal window: ${QUIET_SECONDS}s..."
sleep "$QUIET_SECONDS"

after_metrics="$(fetch_metrics)"
after_signals="$(printf '%s' "$after_metrics" | signals_received)"
after_queue="$(printf '%s' "$after_metrics" | queue_depth)"

if [[ "$before_signals" != "$after_signals" ]]; then
    echo "Signals arrived during quiet window: before=${before_signals} after=${after_signals}" >&2
    exit 2
fi

if [[ "$after_queue" != "0" ]]; then
    echo "Bridge signal queue became non-empty: depth=${after_queue}" >&2
    exit 2
fi

    if [[ "$EXECUTE" == "1" ]]; then
        echo "Running build does not expose admission state; using quiet-window restart path."
    fi
fi

if [[ "$EXECUTE" != "1" ]]; then
    echo "Quiet-window check passed. Re-run with --execute to restart."
    exit 0
fi

echo "Restarting launchd service ${LABEL}..."
launchctl kickstart -k "gui/$(id -u)/${LABEL}"

deadline=$(( $(date +%s) + POST_START_TIMEOUT ))
while (( $(date +%s) < deadline )); do
    if require_healthy >/dev/null 2>&1; then
        metrics="$(fetch_metrics 2>/dev/null || true)"
        if [[ -z "$metrics" ]]; then
            sleep 2
            continue
        fi
        loaded="$(printf '%s' "$metrics" | accepting_signals)"
        if [[ "$loaded" == "True" || "$loaded" == "False" ]]; then
            echo "Bridge restarted and exposes admission state: accepting_signals=${loaded}"
            exit 0
        fi
    fi
    sleep 2
done

echo "Bridge did not expose admission state within ${POST_START_TIMEOUT}s" >&2
exit 1
