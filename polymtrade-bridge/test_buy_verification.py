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


async def _make_executor(page):
    executor = PolymtradeExecutor()
    executor.page = page
    return executor


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


def main() -> int:
    tests = [
        test_get_event_page_position_quantity,
        test_capture_buy_baseline,
        test_verify_buy_executed_balance_decreased,
        test_verify_buy_executed_quantity_increased,
        test_verify_buy_executed_new_position,
        test_verify_buy_executed_no_change,
    ]
    for test in tests:
        asyncio.run(test())
    print("all buy verification tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
