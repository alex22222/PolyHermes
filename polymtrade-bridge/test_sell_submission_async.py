import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from polymtrade_executor import PolymtradeExecutor


class TestSellSubmissionAsync(unittest.IsolatedAsyncioTestCase):
    async def test_execute_sell_can_skip_synchronous_verification(self):
        executor = PolymtradeExecutor()
        executor._ready = True
        executor._logged_in = True
        executor.page = SimpleNamespace(is_closed=lambda: False)
        executor.context = SimpleNamespace(pages=[executor.page])
        submitted = {
            "status": "executed",
            "side": "SELL",
            "baseline": {"position_quantity": 2.0},
        }

        with (
            patch.object(executor, "_resolve_event", AsyncMock(return_value=("1", "event"))),
            patch.object(executor, "_execute_sell", AsyncMock(return_value=submitted)),
            patch.object(executor, "_verify_sell_executed", AsyncMock()) as verify,
        ):
            result = await executor.execute_trade(
                market_slug="btc-updown-15m-1",
                side="SELL",
                outcome="Up",
                amount_usdc=0,
                size_shares=1,
                verify=False,
            )

        self.assertIsNone(result["verified"])
        verify.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
