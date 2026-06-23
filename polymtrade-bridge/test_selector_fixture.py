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

INLINE_BUY_FORM_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section class="trade-panel">
      <h2>Will Canada win the 2026 FIFA World Cup?</h2>
      <div>Canada</div>
      <label>金额</label>
      <input inputmode="decimal" placeholder="金额" />
      <button>确认买入</button>
    </section>
  </main>
</body>
</html>
"""


SELL_POSITION_WITH_PM_WALLET_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section class="wallet-card">
      <div>余额 0 PM</div>
      <button id="pm-sell">卖出 $PM</button>
      <button>买入 $PM</button>
      <div>Solana钱包地址 217m...5y9x</div>
    </section>
    <section class="event-page">
      <h1>Argentina vs. Austria</h1>
      <div class="position-card">
        <div>持仓</div>
        <div>Argentina • Yes</div>
        <button id="position-sell">卖出</button>
        <div>剩余</div>
        <div>3.33</div>
        <div>PnL +0%</div>
      </div>
    </section>
  </main>
  <script>
    window.clickedIds = [];
    document.addEventListener("click", (event) => {
      window.clickedIds.push(event.target.id || (event.target.innerText || "").trim());
    });
  </script>
</body>
</html>
"""


SELL_CONFIRM_DIALOG_HTML = """
<!doctype html>
<html>
<body>
  <div role="dialog" class="trade-modal">
    <h2>卖出 Argentina Yes</h2>
    <input name="soldAmount" inputmode="decimal" />
    <button id="max">100%</button>
    <button id="confirm-sell">确认卖出</button>
  </div>
  <script>
    window.clickedIds = [];
    document.addEventListener("click", (event) => {
      window.clickedIds.push(event.target.id || (event.target.innerText || "").trim());
    });
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


async def _run_trade_form_fixture() -> None:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            executor = PolymtradeExecutor()
            executor.page = page

            await page.set_content(INLINE_BUY_FORM_HTML)
            await executor._enter_amount(2.0)
            value = await page.eval_on_selector("input", "el => el.value")
            assert value == "2.0", value

            await page.set_content(SELL_POSITION_WITH_PM_WALLET_HTML)
            is_open = await executor._is_sell_dialog_open(timeout=0.5)
            assert is_open is False, "Portfolio sell buttons must not count as an open sell dialog"

            await executor._open_sell_dialog(
                "Yes",
                market_slug="fifwc-arg-aut-2026-06-22-arg",
                market_title="Will Argentina win on 2026-06-22?",
            )
            clicked_ids = await page.evaluate("window.clickedIds")
            assert clicked_ids == ["position-sell"], clicked_ids

            await page.set_content(SELL_CONFIRM_DIALOG_HTML)
            is_open = await executor._is_sell_dialog_open(timeout=0.5)
            assert is_open is True, "Dialog with soldAmount input should be treated as sell dialog"
            entered = await executor._enter_sell_shares(2.4691)
            assert entered is True, "Expected sell shares input to be filled"
            value = await page.eval_on_selector("input[name='soldAmount']", "el => el.value")
            assert value == "2.4691", value
            await executor._click_sell_button()
            clicked_ids = await page.evaluate("window.clickedIds")
            assert "confirm-sell" in clicked_ids, clicked_ids
        finally:
            await browser.close()


def main() -> int:
    asyncio.run(_run_selector_fixture())
    asyncio.run(_run_network_modal_fixture())
    asyncio.run(_run_balance_fixture())
    asyncio.run(_run_trade_form_fixture())
    print("selector fixture passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
