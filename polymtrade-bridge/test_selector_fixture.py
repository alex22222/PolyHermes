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


WORLD_CUP_GROUP_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <div class="event-card">
      <h1>世界杯F组冠军</h1>
      <div>体育 世界杯 FIFA世界杯 2026年世界杯足球赛</div>
    </div>
    <ul class="space-y-2 p-4 pt-0">
      <div class="flex items-center justify-between">
        <div class="flex items-center">
          <div class="mr-1">荷兰</div>
        </div>
        <div class="button cursor-pointer">是\n77¢</div>
        <div class="button cursor-pointer">否\n25¢</div>
      </div>
      <div class="flex items-center justify-between">
        <div class="flex items-center">
          <div class="mr-1">日本</div>
        </div>
        <div class="button cursor-pointer">是\n22¢</div>
        <div class="button cursor-pointer">否\n80¢</div>
      </div>
      <div class="flex items-center justify-between">
        <div class="flex items-center">
          <div class="mr-1">瑞典</div>
        </div>
        <div class="button cursor-pointer">是\n4¢</div>
        <div class="button cursor-pointer">否\n96¢</div>
      </div>
    </ul>
    <div class="comments">
      <div>netherlands ties sweden. Easy money.</div>
    </div>
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

            # Categorical event page: should click the side button inside the
            # specific outcome row, not the outer event card or a comment.
            page = await browser.new_page()
            await page.set_content(WORLD_CUP_GROUP_HTML)
            keywords = PolymtradeExecutor._extract_market_keywords(
                "world-cup-group-f-winner",
                "Will Netherlands win Group F in the 2026 FIFA World Cup?",
            )
            assert "netherlands" in keywords, keywords
            assert "荷兰" in keywords, keywords

            result = await page.evaluate(
                PolymtradeExecutor._select_outcome_script(),
                ["No", ["否", "No"], keywords],
            )
            clicked_labels = await page.evaluate("window.clickedLabels")

            assert result["clicked"] is True, result
            assert result["label"] in ("否\n25¢", "否 25¢"), result
            assert "荷兰" in result["rowText"], result
            assert clicked_labels == [result["label"]], clicked_labels

            # WNBA-style binary outcome page: "Toronto Tempo" as the Yes side.
            page = await browser.new_page()
            await page.set_content('''
            <main>
              <div class="market-row">
                <div>Toronto Tempo</div>
                <div class="button cursor-pointer">是\n11¢</div>
                <div class="button cursor-pointer">否\n89¢</div>
              </div>
              <div class="market-row">
                <div>Connecticut Sun</div>
                <div class="button cursor-pointer">是\n89¢</div>
                <div class="button cursor-pointer">否\n11¢</div>
              </div>
            </main>
            <script>
              window.clickedLabels = [];
              document.addEventListener("click", (event) => {
                window.clickedLabels.push((event.target.innerText || event.target.textContent || "").trim());
              });
            </script>
            ''')
            keywords = PolymtradeExecutor._extract_market_keywords(
                "wnba-tor-conn-2026-06-19",
                "Toronto Tempo vs. Connecticut Sun",
            )
            result = await page.evaluate(
                PolymtradeExecutor._select_outcome_script(),
                ["Toronto Tempo", ["是", "Yes"], keywords],
            )
            clicked_labels = await page.evaluate("window.clickedLabels")
            assert result["clicked"] is True, result
            assert "Toronto Tempo" in result["rowText"], result
            assert "是" in result["label"], result
            assert clicked_labels == [result["label"]], clicked_labels
        finally:
            await browser.close()


NETWORK_MODAL_HTML = """
<!doctype html>
<html>
<body>
  <div role="dialog" class="modal" id="network-modal">
    <h2>选择网络和代币</h2>
    <button>Polygon</button>
    <button>Ethereum</button>
    <button>USDC</button>
    <button>USDT</button>
    <button id="confirm-btn">Confirm</button>
  </div>
  <script>
    window.selections = [];
    document.addEventListener("click", (event) => {
      window.selections.push((event.target.innerText || event.target.textContent || "").trim());
      if (event.target.id === 'confirm-btn') {
        document.getElementById('network-modal').style.display = 'none';
      }
    });
  </script>
</body>
</html>
"""


DEPOSIT_MODAL_HTML = """
<!doctype html>
<html>
<body>
  <div role="dialog" class="modal">
    <h2>选择网络和代币</h2>
    <p>Insufficient balance. Please deposit.</p>
    <button>Polygon</button>
    <button>USDC</button>
    <button>Confirm</button>
  </div>
  <script>
    window.selections = [];
    document.addEventListener("click", (event) => {
      window.selections.push((event.target.innerText || event.target.textContent || "").trim());
    });
  </script>
</body>
</html>
"""


BALANCE_HTML = """
<!doctype html>
<html>
<body>
  <div data-testid="balance">Balance: 12.345 USDC</div>
  <div>Some other text</div>
  <script>
    window.selections = [];
  </script>
</body>
</html>
"""


async def _run_network_modal_fixture() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            executor = PolymtradeExecutor()
            executor.page = page

            # Normal network selection modal: should select Polygon + USDC + Confirm.
            await page.set_content(NETWORK_MODAL_HTML)
            selected = await executor._select_network_and_token_in_modal()
            assert selected is True, "Expected network/token selection to succeed"
            selections = await page.evaluate("window.selections")
            assert "Polygon" in selections, selections
            assert "USDC" in selections, selections
            assert "Confirm" in selections, selections

            # Deposit/insufficient balance modal: should refuse to select and return False.
            page2 = await browser.new_page()
            executor.page = page2
            await page2.set_content(DEPOSIT_MODAL_HTML)
            selected2 = await executor._select_network_and_token_in_modal()
            assert selected2 is False, "Expected deposit modal to be rejected"
            selections2 = await page2.evaluate("window.selections")
            assert "Polygon" not in selections2, selections2
        finally:
            await browser.close()


async def _run_balance_fixture() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            executor = PolymtradeExecutor()
            executor.page = page

            await page.set_content(BALANCE_HTML)
            balance = await executor._get_usdc_balance()
            assert balance == 12.345, f"Expected 12.345, got {balance}"

            await page.set_content("<div>No balance here</div>")
            balance = await executor._get_usdc_balance()
            assert balance is None, f"Expected None, got {balance}"
        finally:
            await browser.close()


def main() -> int:
    asyncio.run(_run_selector_fixture())
    asyncio.run(_run_network_modal_fixture())
    asyncio.run(_run_balance_fixture())
    print("selector fixture passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
