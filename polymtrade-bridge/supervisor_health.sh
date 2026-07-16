#!/bin/bash

record_health_event() {
    local event="$1"
    if [[ -z "${BRIDGE_HEALTH_EVENT_LOG:-}" ]]; then
        return 0
    fi
    mkdir -p "$(dirname "$BRIDGE_HEALTH_EVENT_LOG")"
    local extra=""
    if [[ -n "${BRIDGE_CODE_SHA:-}" ]]; then
        extra="${extra},\"code_sha\":\"${BRIDGE_CODE_SHA}\""
    fi
    if [[ -n "${BRIDGE_CODE_FINGERPRINT:-}" ]]; then
        extra="${extra},\"code_fingerprint\":\"${BRIDGE_CODE_FINGERPRINT}\""
    fi
    printf '{"timestamp":%s,"event":"%s","consecutive_failures":%s%s}\n' \
        "$(date +%s)" "$event" "${HEALTH_FAILURES:-0}" "$extra" >> "$BRIDGE_HEALTH_EVENT_LOG"
}

record_health_probe() {
    case "$1" in
        success)
            if (( HEALTH_FAILURES > 0 )); then
                record_health_event probe_recovered
            fi
            HEALTH_FAILURES=0
            ;;
        failure)
            HEALTH_FAILURES=$((HEALTH_FAILURES + 1))
            record_health_event probe_failure
            ;;
        *)
            return 2
            ;;
    esac
}

health_restart_required() {
    (( HEALTH_FAILURES >= HEALTH_FAILURE_THRESHOLD ))
}
