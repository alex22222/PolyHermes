#!/usr/bin/env python3
"""Static fixture tests for content-driven event visibility checks."""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from polymtrade_executor import PolymtradeExecutor  # noqa: E402


COLOMBIA_EVENT_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <h1>Colombia Presidential Election</h1>
    <div class="market-row">
      <div>Abelardo de la Espriella</div>
      <div role="button">Yes 99¢</div>
      <div role="button">No 2¢</div>
    </div>
    <div class="market-row">
      <div>Gustavo Petro</div>
      <div role="button">Yes 1¢</div>
      <div role="button">No 99¢</div>
    </div>
  </main>
</body>
</html>
"""


COLOMBIA_CHINESE_TRADE_ACTION_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section class="event-card">
      <h1>2026 哥伦比亚总统选举</h1>
      <article class="market-row">
        <div>Gustavo Petro</div>
        <div role="button">买入 2¢</div>
        <div role="button">卖出 99¢</div>
      </article>
      <article class="market-row">
        <div>Abelardo de la Espriella</div>
        <div role="button">买入 99¢</div>
        <div role="button">卖出 1¢</div>
      </article>
    </section>
  </main>
</body>
</html>
"""


TRUMP_EVENT_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <h1>Will Donald Trump win the 2028 US Presidential Election?</h1>
    <div class="market-row">
      <div>Trump</div>
      <div role="button">Yes 55¢</div>
      <div role="button">No 46¢</div>
    </div>
  </main>
</body>
</html>
"""


NO_BUTTONS_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <h1>Colombia Presidential Election</h1>
    <p>Market data is loading...</p>
  </main>
</body>
</html>
"""


async def _make_executor(page):
    executor = PolymtradeExecutor()
    executor.page = page
    return executor


class FlakyNavigationPage:
    def __init__(self):
        self.evaluate_calls = 0
        self.wait_for_load_state_calls = 0
        self.url = "https://polym.trade/portfolio?eventId=34584"

    async def evaluate(self, *_args):
        self.evaluate_calls += 1
        if self.evaluate_calls == 1:
            raise Exception("Page.evaluate: Execution context was destroyed, most likely because of a navigation")
        return True

    async def wait_for_load_state(self, *_args, **_kwargs):
        self.wait_for_load_state_calls += 1

    def is_closed(self):
        return False


class FlakyGotoPage:
    def __init__(
        self,
        errors_before_success=1,
        current_url_after_error=None,
        error_message=None,
    ):
        self.goto_calls = 0
        self.url = "about:blank"
        self.errors_before_success = errors_before_success
        self.current_url_after_error = current_url_after_error
        self.error_message = error_message

    async def goto(self, url, **kwargs):
        self.goto_calls += 1
        assert kwargs.get("wait_until") == "domcontentloaded", kwargs
        if self.goto_calls <= self.errors_before_success:
            if self.current_url_after_error:
                self.url = self.current_url_after_error
            message = self.error_message or f"Page.goto: net::ERR_CONNECTION_RESET at {url}"
            raise Exception(message)
        self.url = url


class FallbackGotoPage:
    def __init__(self):
        self.goto_calls = 0
        self.wait_until_values = []
        self.wait_for_load_state_calls = 0
        self.url = "about:blank"

    async def goto(self, url, **kwargs):
        self.goto_calls += 1
        wait_until = kwargs.get("wait_until")
        self.wait_until_values.append(wait_until)
        if wait_until == "commit":
            self.url = url
            return
        raise Exception(f"Page.goto: net::ERR_CONNECTION_RESET at {url}")

    async def wait_for_load_state(self, *_args, **_kwargs):
        self.wait_for_load_state_calls += 1
        raise Exception("Timeout waiting for domcontentloaded")


async def test_is_target_event_visible_when_correct_event_rendered():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(COLOMBIA_EVENT_HTML)

            executor = await _make_executor(page)
            visible = await executor._is_target_event_visible(
                outcome="Yes",
                market_slug="will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election",
                market_title="Will Abelardo de la Espriella win the 2026 Colombian presidential election?",
                timeout=3.0,
            )
            assert visible is True
        finally:
            await browser.close()


async def test_is_target_event_visible_with_chinese_trade_actions():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(COLOMBIA_CHINESE_TRADE_ACTION_HTML)

            executor = await _make_executor(page)
            visible = await executor._is_target_event_visible(
                outcome="Yes",
                market_slug="will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election",
                market_title="Will Abelardo de la Espriella  win the 2026 Colombian presidential election?",
                timeout=3.0,
            )
            assert visible is True

            ready = await executor._wait_for_page_ready(
                timeout=3.0,
                market_title="Will Abelardo de la Espriella  win the 2026 Colombian presidential election?",
                event_id="34584",
            )
            assert ready is True
        finally:
            await browser.close()


async def test_is_target_event_visible_false_on_wrong_event():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(TRUMP_EVENT_HTML)

            executor = await _make_executor(page)
            visible = await executor._is_target_event_visible(
                outcome="Yes",
                market_slug="will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election",
                market_title="Will Abelardo de la Espriella win the 2026 Colombian presidential election?",
                timeout=2.0,
            )
            assert visible is False
        finally:
            await browser.close()


async def test_is_target_event_visible_false_when_side_buttons_missing():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(NO_BUTTONS_HTML)

            executor = await _make_executor(page)
            visible = await executor._is_target_event_visible(
                outcome="Yes",
                market_slug="will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election",
                market_title="Will Abelardo de la Espriella win the 2026 Colombian presidential election?",
                timeout=2.0,
            )
            assert visible is False
        finally:
            await browser.close()


async def test_wait_for_page_ready_succeeds_without_event_id_in_url():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(COLOMBIA_EVENT_HTML)
            # The URL does not contain the target eventId; the check should still
            # pass because it is now content-driven.
            assert "34584" not in page.url

            executor = await _make_executor(page)
            ready = await executor._wait_for_page_ready(
                timeout=5.0,
                market_title="Will Abelardo de la Espriella win the 2026 Colombian presidential election?",
                event_id="34584",
            )
            assert ready is True
        finally:
            await browser.close()


async def test_wait_for_page_ready_fails_when_content_missing():
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(NO_BUTTONS_HTML)

            executor = await _make_executor(page)
            ready = await executor._wait_for_page_ready(
                timeout=2.0,
                market_title="Will Abelardo de la Espriella win the 2026 Colombian presidential election?",
                event_id="34584",
            )
            assert ready is False
        finally:
            await browser.close()


async def test_wait_for_page_ready_retries_navigation_race():
    executor = PolymtradeExecutor()
    page = FlakyNavigationPage()
    executor.page = page

    ready = await executor._wait_for_page_ready(
        timeout=2.0,
        market_title="Will Abelardo de la Espriella win the 2026 Colombian presidential election?",
        event_id="34584",
    )

    assert ready is True
    assert page.evaluate_calls == 2
    assert page.wait_for_load_state_calls == 1


async def test_goto_with_retry_retries_transient_network_error():
    executor = PolymtradeExecutor()
    page = FlakyGotoPage(errors_before_success=2)
    executor.page = page

    await executor._goto_with_retry(
        "https://polym.trade/portfolio?eventId=98287&eventSlug=world-cup-group-h-winner&eventSource=polymarket",
        max_retries=3,
    )

    assert page.goto_calls == 3
    assert page.url.endswith("eventSource=polymarket")


async def test_goto_with_retry_retries_interrupted_by_portfolio_navigation():
    target = "https://polym.trade/?eventId=598793&eventSlug=cs2-vit-fal2-2026-06-19&eventSource=polymarket"
    executor = PolymtradeExecutor()
    page = FlakyGotoPage(
        errors_before_success=1,
        error_message=(
            'Page.goto: Navigation to "https://polym.trade/?eventId=598793" '
            'is interrupted by another navigation to "https://polym.trade/portfolio"'
        ),
    )
    executor.page = page

    await executor._goto_with_retry(target, max_retries=2)

    assert page.goto_calls == 2
    assert page.url == target


async def test_goto_with_retry_retries_err_aborted_navigation():
    target = "https://polym.trade/?eventId=98287&eventSlug=world-cup-group-h-winner&eventSource=polymarket"
    executor = PolymtradeExecutor()
    page = FlakyGotoPage(
        errors_before_success=2,
        error_message=f"Page.goto: net::ERR_ABORTED at {target}",
    )
    executor.page = page

    await executor._goto_with_retry(target, max_retries=3)

    assert page.goto_calls == 3
    assert page.url == target


async def test_goto_with_retry_accepts_reached_target_after_abort():
    target = "https://polym.trade/portfolio?eventId=98287&eventSlug=world-cup-group-h-winner&eventSource=polymarket"
    executor = PolymtradeExecutor()
    page = FlakyGotoPage(errors_before_success=5, current_url_after_error=target)
    executor.page = page

    await executor._goto_with_retry(target, max_retries=3)

    assert page.goto_calls == 1


async def test_goto_with_retry_falls_back_to_commit_after_transient_failures():
    target = "https://polym.trade/portfolio"
    executor = PolymtradeExecutor()
    page = FallbackGotoPage()
    executor.page = page

    await executor._goto_with_retry(target, max_retries=2)

    assert page.wait_until_values == ["domcontentloaded", "domcontentloaded", "commit"]
    assert page.url == target
    assert page.wait_for_load_state_calls == 1


if __name__ == "__main__":
    asyncio.run(test_is_target_event_visible_when_correct_event_rendered())
    asyncio.run(test_is_target_event_visible_with_chinese_trade_actions())
    asyncio.run(test_is_target_event_visible_false_on_wrong_event())
    asyncio.run(test_is_target_event_visible_false_when_side_buttons_missing())
    asyncio.run(test_wait_for_page_ready_succeeds_without_event_id_in_url())
    asyncio.run(test_wait_for_page_ready_fails_when_content_missing())
    asyncio.run(test_wait_for_page_ready_retries_navigation_race())
    asyncio.run(test_goto_with_retry_retries_transient_network_error())
    asyncio.run(test_goto_with_retry_retries_interrupted_by_portfolio_navigation())
    asyncio.run(test_goto_with_retry_retries_err_aborted_navigation())
    asyncio.run(test_goto_with_retry_accepts_reached_target_after_abort())
    asyncio.run(test_goto_with_retry_falls_back_to_commit_after_transient_failures())
