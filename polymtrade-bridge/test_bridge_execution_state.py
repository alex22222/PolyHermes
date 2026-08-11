#!/usr/bin/env python3
"""Regression tests for persisted Bridge execution states."""

import unittest
from unittest.mock import AsyncMock, patch

import main

from bridge_execution_state import (
    STATUS_FAILED,
    STATUS_FAILED_RETRYABLE,
    STATUS_SKIPPED,
    is_retryable_pre_submit_failure,
    status_for_failure,
)


class TestBridgeExecutionState(unittest.IsolatedAsyncioTestCase):
    def test_ui_dialog_failure_is_retryable(self):
        reason = "Could not open buy dialog after outcome click"
        self.assertTrue(is_retryable_pre_submit_failure(reason))
        self.assertEqual(STATUS_FAILED_RETRYABLE, status_for_failure(reason))

    def test_click_submit_is_not_retryable(self):
        reason = "Could not click submit button"
        self.assertFalse(is_retryable_pre_submit_failure(reason))
        self.assertEqual(STATUS_FAILED, status_for_failure(reason))

    def test_safety_guard_is_skipped(self):
        self.assertEqual(
            STATUS_SKIPPED,
            status_for_failure("Last-mile price drift blocked BUY before submit: signal=0.2 quoted=0.5"),
        )

    def test_unknown_failure_stays_failed(self):
        self.assertEqual(STATUS_FAILED, status_for_failure("unexpected executor error"))

    async def test_retry_reenters_signal_path_once_with_existing_record(self):
        signal = main.LeaderTradeSignal(
            timestamp=1,
            leaderAddress="0xleader",
            transactionHash="0xtx",
            conditionId="condition-1",
            marketSlug="market-slug",
            title="Market",
            side="BUY",
            outcome="Yes",
            outcomeIndex=0,
            price=0.5,
            size=1,
        )
        handler = AsyncMock()
        with (
            patch.object(main, "handle_signal", handler),
            patch.object(main.asyncio, "sleep", AsyncMock()),
        ):
            await main._retry_pre_submit_ui_failure_once(signal, 42)

        handler.assert_awaited_once_with(signal, retry_record_id=42, retry_attempt=1)


if __name__ == "__main__":
    unittest.main()
