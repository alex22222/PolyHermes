import unittest

from polymtrade_executor import PolymtradeExecutor


class ScrollPage:
    def __init__(self):
        self.states = [
            {"height": 100, "rows": 1},
            {"height": 200, "rows": 2},
            {"height": 200, "rows": 2},
            {"height": 200, "rows": 2},
        ]
        self.calls = 0

    async def evaluate(self, expression):
        state = self.states[min(self.calls, len(self.states) - 1)]
        self.calls += 1
        return state


class TestPortfolioScroll(unittest.IsolatedAsyncioTestCase):
    async def test_scroll_stops_after_two_stable_samples(self):
        executor = PolymtradeExecutor()
        page = ScrollPage()
        executor.page = page

        await executor._scroll_portfolio_until_stable(
            max_scrolls=8,
            settle_seconds=0,
        )

        self.assertEqual(4, page.calls)


if __name__ == "__main__":
    unittest.main()
