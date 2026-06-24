#!/usr/bin/env python3
"""Tests for post-BUY verification with balance/position delta."""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from polymtrade_executor import PolymtradeExecutor  # noqa: E402


EVENT_PAGE_WITH_POSITION_HTML = """
<!doctype html>
<html>
<body>
  <div>Balance: 100.50 USDC</div>
  <div class="outcome-row">
    <div>Yes</div>
    <div>You own 5.25 shares</div>
  </div>
  <script>
    window.clickedLabels = [];
  </script>
</body>
</html>
"""


EVENT_PAGE_CHINESE_HTML = """
<!doctype html>
<html>
<body>
  <div>余额：88.00 USDC</div>
  <div class="outcome-row">
    <div>是</div>
    <div>持仓 12.5 份</div>
  </div>
</body>
</html>
"""


EVENT_PAGE_NO_POSITION_HTML = """
<!doctype html>
<html>
<body>
  <div>Balance: 50.00 USDC</div>
  <div class="outcome-row">
    <div>Yes</div>
    <div>No position</div>
  </div>
</body>
</html>
"""


EVENT_PAGE_WITH_UNRELATED_PORTFOLIO_POSITION_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <h1>Bitcoin Up or Down - June 24, 8:35AM-8:40AM ET</h1>
    <section class="portfolio">
      <h2>Portfolio</h2>
      <div class="holding-row">
        <div>Will Spain win Group H in the 2026 FIFA World Cup?</div>
        <div>No - 14.8 shares</div>
      </div>
    </section>
    <section class="market">
      <button>Up 96c</button>
      <button>Down 5c</button>
      <p>This market will resolve to Up if Bitcoin ends higher; otherwise Down.</p>
    </section>
  </main>
</body>
</html>
"""


EVENT_PAGE_WITH_TARGET_PORTFOLIO_POSITION_HTML = """
<!doctype html>
<html>
<body>
  <div class="holding-row">
    <div>Bitcoin Up or Down - June 24, 8:35AM-8:40AM ET</div>
    <div>Up - 1.04 shares</div>
  </div>
</body>
</html>
"""


async def _make_executor(page):
    executor = PolymtradeExecutor()
    executor.page = page
    return executor


class NavigationRaceConfirmPage:
    async def query_selector(self, _selector):
        raise Exception("Page.query_selector: Execution context was destroyed, most likely because of a navigation")


async def test_get_event_page_position_quantity():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(EVENT_PAGE_WITH_POSITION_HTML)
            executor = await _make_executor(page)
            qty = await executor._get_event_page_position_quantity("Yes")
            assert qty == 5.25, f"Expected 5.25, got {qty}"

            page2 = await browser.new_page()
            await page2.set_content(EVENT_PAGE_CHINESE_HTML)
            executor.page = page2
            qty2 = await executor._get_event_page_position_quantity("是")
            assert qty2 == 12.5, f"Expected 12.5, got {qty2}"

            page3 = await browser.new_page()
            await page3.set_content(EVENT_PAGE_NO_POSITION_HTML)
            executor.page = page3
            qty3 = await executor._get_event_page_position_quantity("Yes")
            assert qty3 is None, f"Expected None, got {qty3}"

            page4 = await browser.new_page()
            await page4.set_content(EVENT_PAGE_WITH_UNRELATED_PORTFOLIO_POSITION_HTML)
            executor.page = page4
            qty4 = await executor._get_event_page_position_quantity(
                "Up",
                market_slug="btc-updown-5m-1782304500",
                market_title="Bitcoin Up or Down - June 24, 8:35AM-8:40AM ET",
            )
            assert qty4 is None, f"Expected unrelated portfolio position to be ignored, got {qty4}"

            page5 = await browser.new_page()
            await page5.set_content(EVENT_PAGE_WITH_TARGET_PORTFOLIO_POSITION_HTML)
            executor.page = page5
            qty5 = await executor._get_event_page_position_quantity(
                "Up",
                market_slug="btc-updown-5m-1782304500",
                market_title="Bitcoin Up or Down - June 24, 8:35AM-8:40AM ET",
            )
            assert qty5 == 1.04, f"Expected 1.04, got {qty5}"
        finally:
            await browser.close()
    print("test_get_event_page_position_quantity passed")


async def test_capture_buy_baseline():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(EVENT_PAGE_WITH_POSITION_HTML)
            executor = await _make_executor(page)
            baseline = await executor._capture_buy_baseline("Yes")
            assert baseline["balance"] == 100.50, baseline
            assert baseline["position_quantity"] == 5.25, baseline
            assert "captured_at" in baseline
        finally:
            await browser.close()
    print("test_capture_buy_baseline passed")


async def test_verify_buy_executed_balance_decreased():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            # Pre-trade page: balance 100, no position text
            await page.set_content(EVENT_PAGE_NO_POSITION_HTML)
            executor = await _make_executor(page)
            baseline = await executor._capture_buy_baseline("Yes")

            # Post-trade page: balance dropped to 90 (more than 50% of amount=15)
            await page.set_content("""
            <!doctype html>
            <html><body>
              <div>Balance: 90.00 USDC</div>
              <div class="outcome-row"><div>Yes</div><div>You own 0 shares</div></div>
            </body></html>
            """)
            verified = await executor._verify_buy_executed(
                outcome="Yes", amount_usdc=15.0, baseline=baseline
            )
            assert verified is True, f"Expected True, got {verified}"
        finally:
            await browser.close()
    print("test_verify_buy_executed_balance_decreased passed")


async def test_verify_buy_executed_quantity_increased():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(EVENT_PAGE_WITH_POSITION_HTML)
            executor = await _make_executor(page)
            baseline = await executor._capture_buy_baseline("Yes")

            # Post-trade: quantity increased from 5.25 to 10.0
            await page.set_content("""
            <!doctype html>
            <html><body>
              <div>Balance: 100.50 USDC</div>
              <div class="outcome-row"><div>Yes</div><div>You own 10.00 shares</div></div>
            </body></html>
            """)
            verified = await executor._verify_buy_executed(
                outcome="Yes", amount_usdc=5.0, baseline=baseline
            )
            assert verified is True, f"Expected True, got {verified}"
        finally:
            await browser.close()
    print("test_verify_buy_executed_quantity_increased passed")


async def test_verify_buy_executed_new_position():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(EVENT_PAGE_NO_POSITION_HTML)
            executor = await _make_executor(page)
            baseline = await executor._capture_buy_baseline("Yes")

            # Post-trade: no pre-trade quantity, but now a position appears.
            await page.set_content("""
            <!doctype html>
            <html><body>
              <div>Balance: 50.00 USDC</div>
              <div class="outcome-row"><div>Yes</div><div>You own 3.00 shares</div></div>
            </body></html>
            """)
            verified = await executor._verify_buy_executed(
                outcome="Yes", amount_usdc=5.0, baseline=baseline
            )
            assert verified is True, f"Expected True, got {verified}"
        finally:
            await browser.close()
    print("test_verify_buy_executed_new_position passed")


async def test_verify_buy_executed_no_change():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(EVENT_PAGE_WITH_POSITION_HTML)
            executor = await _make_executor(page)
            baseline = await executor._capture_buy_baseline("Yes")

            # Post-trade: nothing changed.
            await page.set_content(EVENT_PAGE_WITH_POSITION_HTML)
            verified = await executor._verify_buy_executed(
                outcome="Yes", amount_usdc=5.0, baseline=baseline
            )
            assert verified is False, f"Expected False, got {verified}"
        finally:
            await browser.close()
    print("test_verify_buy_executed_no_change passed")


async def test_confirm_trade_treats_post_submit_navigation_race_as_submitted():
    executor = PolymtradeExecutor()
    executor.page = NavigationRaceConfirmPage()
    await executor._confirm_trade()
    print("test_confirm_trade_treats_post_submit_navigation_race_as_submitted passed")


def main() -> int:
    tests = [
        test_get_event_page_position_quantity,
        test_capture_buy_baseline,
        test_verify_buy_executed_balance_decreased,
        test_verify_buy_executed_quantity_increased,
        test_verify_buy_executed_new_position,
        test_verify_buy_executed_no_change,
        test_confirm_trade_treats_post_submit_navigation_race_as_submitted,
    ]
    for test in tests:
        asyncio.run(test())
    print("all buy verification tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
