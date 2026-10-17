"""A new portfolio page must select holdings, not parse the default history."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import async_playwright

from polymtrade_executor import PolymtradeExecutor


def test_history_view_is_switched_before_reading_positions():
    selected = False

    async def select(*_args, **_kwargs):
        nonlocal selected
        selected = True

    async def snapshot(_expression):
        position = {"marketTitle": "Market", "side": "Yes", "quantity": 2}
        history = {"marketTitle": "Market", "side": "Buy", "quantity": None}
        return {"positions": [position if selected else history], "hasErrorBanner": False}

    tab = SimpleNamespace(click=AsyncMock(side_effect=select), get_attribute=AsyncMock(return_value="cursor-pointer"))
    page = SimpleNamespace(
        wait_for_selector=AsyncMock(return_value=tab),
        wait_for_function=AsyncMock(),
        evaluate=AsyncMock(side_effect=snapshot),
    )
    executor = PolymtradeExecutor()
    executor.page = page
    executor._goto_with_retry = AsyncMock(return_value=SimpleNamespace(status=200))
    executor._wait_for_portfolio_rows = AsyncMock(return_value=True)
    executor._scroll_portfolio_until_stable = AsyncMock()
    executor._enrich_position = AsyncMock(return_value={})

    result = asyncio.run(executor._fetch_portfolio_positions_on_active_page())

    assert result["portfolio_complete"] is True
    assert result["positions"][0]["quantity"] == 2
    tab.click.assert_awaited_once()
    page.wait_for_function.assert_awaited_once()


def test_unselectable_positions_tab_fails_closed_before_scraping():
    executor = PolymtradeExecutor()
    executor.page = SimpleNamespace(wait_for_selector=AsyncMock(side_effect=RuntimeError("positions tab missing")))
    executor._goto_with_retry = AsyncMock(return_value=SimpleNamespace(status=200))
    executor._wait_for_portfolio_rows = AsyncMock(return_value=True)
    executor._scroll_portfolio_until_stable = AsyncMock()

    result = asyncio.run(executor._fetch_portfolio_positions_on_active_page())

    assert result["portfolio_complete"] is False
    assert result["empty_state_confirmed"] is False
    assert "positions tab missing" in result["error"]
    executor._wait_for_portfolio_rows.assert_not_awaited()
    executor._scroll_portfolio_until_stable.assert_not_awaited()


@pytest.mark.parametrize("label", ["Positions", "持仓"])
def test_real_history_dom_is_replaced_with_holdings_before_parse(label):
    async def scenario():
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)
            try:
                page = await browser.new_page()
                await page.set_content("""
                    <div class="flex">
                      <div id="positions" class="mr-2 cursor-pointer">LABEL</div>
                      <div id="history" class="cursor-pointer text-foreground">History</div>
                    </div>
                    <ul><li class="flex px-4 py-2 border-b text-xs items-center cursor-pointer">
                      <div>Market</div><div>$1</div><div>Buy</div>
                    </li></ul>
                    <script>
                      document.querySelector('#positions').onclick = function () {
                        this.classList.add('text-foreground');
                        document.querySelector('#history').classList.remove('text-foreground');
                        document.querySelector('li').innerHTML =
                          '<div>Market</div><div>$1</div><div>Yes • 2 shares</div>';
                      };
                    </script>
                """.replace("LABEL", label))
                executor = PolymtradeExecutor()
                executor.page = page
                executor._goto_with_retry = AsyncMock(return_value=SimpleNamespace(status=200))
                executor._scroll_portfolio_until_stable = AsyncMock()
                executor._enrich_position = AsyncMock(return_value={})

                result = await executor._fetch_portfolio_positions_on_active_page()

                assert result["portfolio_complete"] is True
                assert result["positions"][0]["side"] == "Yes"
                assert result["positions"][0]["quantity"] == 2
            finally:
                await browser.close()
    asyncio.run(scenario())
