#!/usr/bin/env python3
"""Static fixture tests for Polymtrade multi-market row selection."""

import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from polymtrade_executor import PolymtradeExecutor  # noqa: E402


WORLD_CUP_FINAL_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section id="whole-event">
      <h1>世界杯：进入决赛的国家</h1>
      <div class="market-row">
        <div>France</div>
        <div>$1.5万</div>
        <div role="button">Yes\n30¢</div>
        <div role="button">No\n71¢</div>
      </div>
      <div class="market-row">
        <div>Spain</div>
        <div>$1.1万</div>
        <div role="button">Yes\n25¢</div>
        <div role="button">No\n76¢</div>
      </div>
      <div class="market-row">
        <div>Argentina</div>
        <div>$6433.9</div>
        <div>$3.9万</div>
        <div>194K</div>
        <div role="button">Yes\n21¢</div>
        <div role="button">No\n80¢</div>
      </div>
    </section>
  </main>
  <script>
    window.clickedLabels = [];
    document.addEventListener("click", (event) => {
      window.clickedLabels.push((event.target.innerText || event.target.textContent || "").trim());
    });
  </script>
</body>
</html>
"""


async def _run_selector_fixture() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(WORLD_CUP_FINAL_HTML)

            keywords = PolymtradeExecutor._extract_market_keywords(
                "will-argentina-reach-the-2026-fifa-world-cup-final",
                "Will Argentina reach the 2026 FIFA World Cup final?",
            )
            assert keywords == ["argentina", "阿根廷"], keywords

            result = await page.evaluate(
                PolymtradeExecutor._select_outcome_script(),
                ["No", ["否", "No"], keywords],
            )
            clicked_labels = await page.evaluate("window.clickedLabels")

            assert result["clicked"] is True, result
            assert result["label"] == "No 80¢", result
            assert "Argentina" in result["rowText"], result
            assert clicked_labels == ["No 80¢"], clicked_labels

            page = await browser.new_page()
            await page.set_content(WORLD_CUP_FINAL_HTML)
            missing_result = await page.evaluate(
                PolymtradeExecutor._select_outcome_script(),
                ["No", ["否", "No"], ["curacao", "库拉索"]],
            )
            assert missing_result["clicked"] is False, missing_result
            assert missing_result["skippedGlobalFallback"] is True, missing_result
        finally:
            await browser.close()


def main() -> int:
    asyncio.run(_run_selector_fixture())
    print("selector fixture passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
