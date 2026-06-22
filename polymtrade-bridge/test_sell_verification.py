#!/usr/bin/env python3
"""Tests for post-SELL verification with balance/position delta."""

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


async def test_capture_sell_baseline():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(EVENT_PAGE_WITH_POSITION_HTML)
            executor = await _make_executor(page)
            baseline = await executor._capture_sell_baseline("Yes")
            assert baseline["balance"] == 100.50, baseline
            assert baseline["position_quantity"] == 5.25, baseline
            assert "captured_at" in baseline
        finally:
            await browser.close()
    print("test_capture_sell_baseline passed")


async def test_verify_sell_executed_quantity_decreased():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(EVENT_PAGE_WITH_POSITION_HTML)
            executor = await _make_executor(page)
            baseline = await executor._capture_sell_baseline("Yes")

            # Post-trade: quantity decreased from 5.25 to 1.0
            await page.set_content("""
            <!doctype html>
            <html><body>
              <div>Balance: 100.50 USDC</div>
              <div class="outcome-row"><div>Yes</div><div>You own 1.00 shares</div></div>
            </body></html>
            """)
            verified = await executor._verify_sell_executed(
                outcome="Yes", size_shares=4.25, baseline=baseline
            )
            assert verified is True, f"Expected True, got {verified}"
        finally:
            await browser.close()
    print("test_verify_sell_executed_quantity_decreased passed")


async def test_verify_sell_executed_balance_increased():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(EVENT_PAGE_WITH_POSITION_HTML)
            executor = await _make_executor(page)
            baseline = await executor._capture_sell_baseline("Yes")

            # Post-trade: balance increased
            await page.set_content("""
            <!doctype html>
            <html><body>
              <div>Balance: 110.00 USDC</div>
              <div class="outcome-row"><div>Yes</div><div>You own 5.25 shares</div></div>
            </body></html>
            """)
            verified = await executor._verify_sell_executed(
                outcome="Yes", size_shares=4.25, baseline=baseline
            )
            assert verified is True, f"Expected True, got {verified}"
        finally:
            await browser.close()
    print("test_verify_sell_executed_balance_increased passed")


async def test_verify_sell_executed_success_indicator_fallback():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(EVENT_PAGE_WITH_POSITION_HTML)
            executor = await _make_executor(page)
            baseline = await executor._capture_sell_baseline("Yes")

            # Post-trade: no quantity/balance change, but success indicator present
            await page.set_content("""
            <!doctype html>
            <html><body>
              <div>Balance: 100.50 USDC</div>
              <div class="outcome-row"><div>Yes</div><div>You own 5.25 shares</div></div>
              <div>Order submitted</div>
            </body></html>
            """)
            verified = await executor._verify_sell_executed(
                outcome="Yes", size_shares=4.25, baseline=baseline
            )
            assert verified is True, f"Expected True, got {verified}"
        finally:
            await browser.close()
    print("test_verify_sell_executed_success_indicator_fallback passed")


async def test_verify_sell_executed_no_change():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(EVENT_PAGE_WITH_POSITION_HTML)
            executor = await _make_executor(page)
            baseline = await executor._capture_sell_baseline("Yes")

            # Post-trade: nothing changed.
            await page.set_content(EVENT_PAGE_WITH_POSITION_HTML)
            verified = await executor._verify_sell_executed(
                outcome="Yes", size_shares=4.25, baseline=baseline
            )
            assert verified is False, f"Expected False, got {verified}"
        finally:
            await browser.close()
    print("test_verify_sell_executed_no_change passed")


def main() -> int:
    tests = [
        test_capture_sell_baseline,
        test_verify_sell_executed_quantity_decreased,
        test_verify_sell_executed_balance_increased,
        test_verify_sell_executed_success_indicator_fallback,
        test_verify_sell_executed_no_change,
    ]
    for test in tests:
        asyncio.run(test())
    print("all sell verification tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
