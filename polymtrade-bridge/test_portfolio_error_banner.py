"""A rendered cached row does not establish a complete live portfolio."""
from unittest.mock import AsyncMock

import pytest
from playwright.async_api import async_playwright

from polymtrade_executor import PolymtradeExecutor


@pytest.mark.parametrize("has_error_banner", [True, False])
async def test_portfolio_completeness_requires_no_connection_error(has_error_banner):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            error = '<div data-test="portfolio-error-banner">Check your connection and reload.</div>' if has_error_banner else ''
            await page.set_content(error + """
                <div class="cursor-pointer text-foreground">Positions</div>
                <ul><li class="flex px-4 py-2 border-b text-xs items-center cursor-pointer">
                  <div>Will the example market resolve Yes?</div>
                  <div>$1</div><div>Yes • 2 shares</div>
                  <div>+$0.1</div><div>10%</div>
                </li></ul>
            """)
            executor = PolymtradeExecutor()
            executor.page = page
            executor._ensure_portfolio_page = AsyncMock(return_value=page)
            executor._goto_with_retry = AsyncMock(return_value=None)
            executor._wait_for_portfolio_rows = AsyncMock(return_value=True)
            executor._scroll_portfolio_until_stable = AsyncMock()
            executor._enrich_position = AsyncMock(return_value={})
            executor.get_wallet_address = AsyncMock(return_value=None)
            executor._schedule_portfolio_page_idle_close = lambda: None

            result = await executor.fetch_portfolio_positions(force_refresh=True)

            assert result["portfolio_complete"] is not has_error_banner
            assert result["empty_state_confirmed"] is False
            assert ("error" in result) is has_error_banner
            assert len(result["positions"]) == 1
            assert (executor.last_portfolio_synced_at == 0) is has_error_banner
            assert not page.is_closed()
            executor.get_wallet_address.assert_not_awaited()
        finally:
            await browser.close()
