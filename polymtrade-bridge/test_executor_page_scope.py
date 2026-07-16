import asyncio
import unittest

from polymtrade_executor import PolymtradeExecutor


class TestExecutorPageScope(unittest.IsolatedAsyncioTestCase):
    async def test_page_scope_is_isolated_between_tasks(self):
        executor = PolymtradeExecutor()
        default_page = object()
        first_page = object()
        second_page = object()
        executor.page = default_page
        release = asyncio.Event()

        async def scoped_page(page):
            with executor._page_scope(page):
                await release.wait()
                return executor.page

        first = asyncio.create_task(scoped_page(first_page))
        second = asyncio.create_task(scoped_page(second_page))
        await asyncio.sleep(0)

        self.assertIs(default_page, executor.page)
        release.set()
        self.assertIs(first_page, await first)
        self.assertIs(second_page, await second)
        self.assertIs(default_page, executor.page)


if __name__ == "__main__":
    unittest.main()
