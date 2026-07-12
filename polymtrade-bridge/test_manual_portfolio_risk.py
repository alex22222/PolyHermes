#!/usr/bin/env python3

import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import main
from fastapi import BackgroundTasks
from portfolio_risk_client import PortfolioRiskCheck


class TestManualPortfolioRisk(unittest.IsolatedAsyncioTestCase):
    def request(self, side="BUY"):
        return main.ExecuteRequest(
            market_slug="market-slug",
            side=side,
            outcome="Yes",
            amount_usdc=1.25,
            conditionId="condition-1",
            marketTitle="Bitcoin market",
            sizeShares=1.0 if side == "SELL" else None,
        )

    async def test_manual_buy_runs_precheck_final_and_success_completion(self):
        executor = SimpleNamespace(execute_trade=AsyncMock(return_value={"verified": True}))
        recorder = MagicMock()
        check = AsyncMock(return_value=PortfolioRiskCheck(True, True, "d", "WOULD_BLOCK", "SHADOW"))
        complete = AsyncMock()

        with (
            patch.object(main, "executor", executor),
            patch.object(main, "recorder", recorder),
            patch.object(main, "_evaluate_manual_buy_risk", check),
            patch.object(main, "_complete_manual_buy_risk", complete),
        ):
            await main._execute_and_record(1, self.request(), "manual-1")

        self.assertEqual([call.args[2] for call in check.await_args_list], ["precheck", "final"])
        executor.execute_trade.assert_awaited_once()
        complete.assert_awaited_once_with("bridge:manual-1:manual", "SUCCESS")
        recorder.update_status.assert_called_with(1, "SUCCESS")

    async def test_manual_sell_skips_buy_risk(self):
        executor = SimpleNamespace(execute_trade=AsyncMock(return_value={"verified": True}))
        recorder = MagicMock()
        check = AsyncMock()

        with (
            patch.object(main, "executor", executor),
            patch.object(main, "recorder", recorder),
            patch.object(main, "_evaluate_manual_buy_risk", check),
            patch.object(main, "_get_live_position_quantity", AsyncMock(return_value=main.Decimal("2"))),
            patch.object(main, "_wait_for_live_position_decrease", AsyncMock(return_value=main.Decimal("1"))),
        ):
            await main._execute_and_record(1, self.request("SELL"), "manual-sell")

        check.assert_not_awaited()
        executor.execute_trade.assert_awaited_once()

    async def test_manual_buy_denial_finishes_reservation_without_ui_execution(self):
        executor = SimpleNamespace(execute_trade=AsyncMock())
        recorder = MagicMock()
        check = AsyncMock(return_value=PortfolioRiskCheck(True, False, "d", "BLOCK", "ENFORCED"))
        complete = AsyncMock()

        with (
            patch.object(main, "executor", executor),
            patch.object(main, "recorder", recorder),
            patch.object(main, "_evaluate_manual_buy_risk", check),
            patch.object(main, "_complete_manual_buy_risk", complete),
        ):
            await main._execute_and_record(1, self.request(), "manual-denied")

        executor.execute_trade.assert_not_awaited()
        complete.assert_awaited_once_with("bridge:manual-denied:manual", "FAILED")
        self.assertIn("Portfolio risk blocked", recorder.update_status.call_args.kwargs["error_message"])

    async def test_execute_reuses_caller_idempotency_key_without_second_record(self):
        executor = SimpleNamespace(is_ready=lambda: True, is_logged_in=lambda: True)
        recorder = MagicMock()
        recorder.exists.return_value = True
        request = self.request("SELL").model_copy(update={"external_trade_id": "reduction-draft-1"})
        tasks = BackgroundTasks()

        with patch.object(main, "executor", executor), patch.object(main, "recorder", recorder):
            result = await main.execute_trade(request, tasks)

        self.assertEqual("duplicate", result["status"])
        self.assertEqual("reduction-draft-1", result["external_trade_id"])
        recorder.record_pending.assert_not_called()
        self.assertEqual(0, len(tasks.tasks))


if __name__ == "__main__":
    unittest.main()
