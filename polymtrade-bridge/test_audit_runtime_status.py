#!/usr/bin/env python3
"""Tests for online audit runtime readiness gating."""

from copy import deepcopy

from main import apply_runtime_status_to_audit_result, runtime_block_reasons


BASE_AUDIT = {
    "monitor_status": {
        "status": "clear",
        "message": "No actionable Bridge failures in the selected audit window.",
        "next_action_buckets": [],
    },
    "next_action_candidates": [],
}


def test_runtime_block_reasons_for_healthy_runtime():
    runtime = {
        "ready": True,
        "logged_in": True,
        "last_error": None,
        "copy_trading_account_id": 2,
        "copy_trading_config_count": 2,
    }
    assert runtime_block_reasons(runtime) == []


def test_apply_runtime_status_preserves_clear_when_healthy():
    runtime = {
        "ready": True,
        "logged_in": True,
        "last_error": None,
        "copy_trading_account_id": 2,
        "copy_trading_config_count": 2,
    }
    result = apply_runtime_status_to_audit_result(deepcopy(BASE_AUDIT), runtime)
    assert result["runtime_status"] == runtime
    assert result["monitor_status"]["status"] == "clear"
    assert "runtime_block_reasons" not in result["monitor_status"]


def test_apply_runtime_status_blocks_when_unready_or_unconfigured():
    runtime = {
        "ready": False,
        "logged_in": False,
        "last_error": "browser closed",
        "copy_trading_account_id": None,
        "copy_trading_config_count": 0,
    }
    result = apply_runtime_status_to_audit_result(deepcopy(BASE_AUDIT), runtime)
    assert result["runtime_status"] == runtime
    assert result["monitor_status"]["status"] == "runtime_blocked"
    assert result["monitor_status"]["runtime_block_reasons"] == [
        "executor_not_ready",
        "not_logged_in",
        "copy_trading_account_missing",
        "copy_trading_config_empty",
        "last_error_present",
    ]


if __name__ == "__main__":
    test_runtime_block_reasons_for_healthy_runtime()
    test_apply_runtime_status_preserves_clear_when_healthy()
    test_apply_runtime_status_blocks_when_unready_or_unconfigured()
    print("audit runtime status tests passed")
