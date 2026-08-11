from types import SimpleNamespace

import pytest

from polymtrade_executor import PolymtradeExecutor


class FakePage:
    def __init__(self):
        self.activated = False

    async def bring_to_front(self):
        self.activated = True

    async def evaluate(self, _expression):
        return []

    def is_closed(self):
        return False


class PortfolioExecutor(PolymtradeExecutor):
    async def _goto_with_retry(self, *_args, **_kwargs):
        assert self.page.activated is True

    async def _wait_for_portfolio_rows(self, timeout=12.0):
        return True

    async def _scroll_portfolio_until_stable(self):
        return None

    async def get_wallet_address(self):
        return None


@pytest.mark.asyncio
async def test_portfolio_page_is_activated_before_navigation():
    executor = PortfolioExecutor()
    executor.page = FakePage()

    result = await executor._fetch_portfolio_positions_on_active_page()

    assert result["portfolio_complete"] is True


@pytest.mark.asyncio
async def test_trade_page_is_activated_before_execution_validation():
    executor = PolymtradeExecutor()
    page = FakePage()
    executor.page = page
    executor.context = SimpleNamespace(pages=[page])
    executor._ready = True
    executor._logged_in = True

    with pytest.raises(ValueError, match="Invalid side"):
        await executor.execute_trade("market", "invalid", "Yes", 1.0)

    assert page.activated is True
