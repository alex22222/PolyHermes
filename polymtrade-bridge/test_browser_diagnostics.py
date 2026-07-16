import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock

from polymtrade_executor import PolymtradeExecutor


class FakePage:
    def __init__(self, url, closed=False):
        self.url = url
        self._closed = closed

    def is_closed(self):
        return self._closed

    async def close(self):
        self._closed = True

    async def inner_text(self, selector, timeout=None):
        return "polym.trade/?ref=0x0372c9d06b9ce45D7365085A3Cc0737e4B924942"


class FakeContext:
    def __init__(self, page):
        self.page = page
        self.pages = []

    async def new_page(self):
        self.pages.append(self.page)
        return self.page


class TestBrowserDiagnostics(unittest.TestCase):
    def test_reports_page_roles_without_navigation(self):
        executor = PolymtradeExecutor()
        default_page = FakePage("https://polym.trade")
        portfolio_page = FakePage("https://polym.trade/portfolio")
        extra_page = FakePage("about:blank", closed=True)
        executor.page = default_page
        executor.portfolio_page = portfolio_page
        executor.context = SimpleNamespace(pages=[default_page, portfolio_page, extra_page])

        result = executor.browser_diagnostics()

        self.assertEqual(3, result["page_count"])
        self.assertFalse(result["default_page_closed"])
        self.assertFalse(result["portfolio_page_closed"])
        self.assertEqual(
            ["default", "portfolio", "other"],
            [page["role"] for page in result["pages"]],
        )


class TestKnownUnmanagedPageCleanup(unittest.IsolatedAsyncioTestCase):
    async def test_closes_docs_page_only(self):
        executor = PolymtradeExecutor()
        default_page = FakePage("https://polym.trade")
        portfolio_page = FakePage("https://polym.trade/portfolio")
        docs_page = FakePage("https://docs.polym.trade/")
        trade_page = FakePage("https://polym.trade/event/btc-up-or-down")
        executor.page = default_page
        executor.portfolio_page = portfolio_page
        executor.context = SimpleNamespace(pages=[default_page, portfolio_page, docs_page, trade_page])

        closed = await executor.close_known_unmanaged_pages()

        self.assertEqual(1, closed)
        self.assertTrue(docs_page.is_closed())
        self.assertFalse(default_page.is_closed())
        self.assertFalse(portfolio_page.is_closed())
        self.assertFalse(trade_page.is_closed())


class TestPortfolioPageIdleClose(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_schedules_idle_portfolio_page_close(self):
        executor = PolymtradeExecutor()
        executor._portfolio_page_idle_close_seconds = 0.01
        page = FakePage("https://polym.trade/portfolio")
        executor.context = FakeContext(page)
        executor._fetch_portfolio_positions_on_active_page = AsyncMock(return_value={"positions": []})

        result = await executor.fetch_portfolio_positions()
        await asyncio.sleep(0.03)

        self.assertEqual({"positions": []}, result)
        self.assertTrue(page.is_closed())
        self.assertIsNone(executor.portfolio_page)

    async def test_portfolio_page_reuse_cancels_previous_idle_close(self):
        executor = PolymtradeExecutor()
        executor._portfolio_page_idle_close_seconds = 0.04
        page = FakePage("https://polym.trade/portfolio")
        executor.context = FakeContext(page)
        executor._get_usdc_balance = AsyncMock(return_value=1.0)

        first = await executor.get_portfolio_balance()
        await asyncio.sleep(0.02)
        second = await executor.get_portfolio_balance()
        await asyncio.sleep(0.03)

        self.assertEqual(1.0, first)
        self.assertEqual(1.0, second)
        self.assertFalse(page.is_closed())

        await asyncio.sleep(0.03)
        self.assertTrue(page.is_closed())

    async def test_wallet_address_uses_portfolio_page_without_moving_default_page(self):
        executor = PolymtradeExecutor()
        executor._logged_in = True
        executor._portfolio_page_idle_close_seconds = 0
        default_page = FakePage("https://polym.trade/")
        portfolio_page = FakePage("https://polym.trade/portfolio")
        executor.page = default_page
        executor.context = FakeContext(portfolio_page)
        executor._goto_with_retry = AsyncMock()

        address = await executor.get_wallet_address()

        self.assertEqual("0x0372c9d06b9ce45d7365085a3cc0737e4b924942", address)
        self.assertIs(default_page, executor.page)
        self.assertIs(portfolio_page, executor.portfolio_page)
        executor._goto_with_retry.assert_awaited_once()


if __name__ == "__main__":
    unittest.main()
