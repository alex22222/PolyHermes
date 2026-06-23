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
        <div>Mexico</div>
        <div>$9000</div>
        <div role="button">Yes\n13¢</div>
        <div role="button">No\n88¢</div>
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


WORLD_CUP_GROUP_MULTI_COUNTRY_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section class="event-card">
      <h1>2026 FIFA 世界杯小组冠军</h1>
      <div>Group H / Group E / Group G</div>
    </section>
    <section class="markets">
      <article class="market-row">
        <div class="outcome-label">乌拉圭</div>
        <div role="button">是\n41¢</div>
        <div role="button">否\n60¢</div>
      </article>
      <article class="market-row">
        <div class="outcome-label">厄瓜多尔</div>
        <div role="button">是\n32¢</div>
        <div role="button">否\n70¢</div>
      </article>
      <article class="market-row">
        <div class="outcome-label">德国</div>
        <div role="button">是\n58¢</div>
        <div role="button">否\n44¢</div>
      </article>
      <article class="market-row">
        <div class="outcome-label">比利时</div>
        <div role="button">是\n68¢</div>
        <div role="button">否\n34¢</div>
      </article>
      <article class="market-row">
        <div class="outcome-label">西班牙</div>
        <div role="button">Yes\n82¢</div>
        <div role="button">No\n20¢</div>
      </article>
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


WORLD_CUP_REMAINING_COUNTRY_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section class="event-card">
      <h1>世界杯国家市场</h1>
      <div>世界杯小组 / 晋级决赛 / 单场胜负</div>
    </section>
    <section class="markets">
      <article class="market-row">
        <div class="outcome-label">海地</div>
        <div role="button">是\n18¢</div>
        <div role="button">否\n84¢</div>
      </article>
      <article class="market-row">
        <div class="outcome-label">库拉索</div>
        <div role="button">是\n9¢</div>
        <div role="button">否\n93¢</div>
      </article>
      <article class="market-row">
        <div class="outcome-label">佛得角</div>
        <div role="button">是\n4¢</div>
        <div role="button">否\n97¢</div>
      </article>
      <article class="market-row">
        <div class="outcome-label">苏格兰</div>
        <div role="button">是\n28¢</div>
        <div role="button">否\n74¢</div>
      </article>
      <article class="market-row">
        <div class="outcome-label">美国</div>
        <div role="button">Yes\n7¢</div>
        <div role="button">No\n95¢</div>
      </article>
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


POLITICAL_CANDIDATE_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section id="candidate-event">
      <h1>2026 Colombian presidential election winner</h1>
      <div class="market-row">
        <div>Gustavo Petro</div>
        <div role="button">Yes\n2¢</div>
        <div role="button">No\n99¢</div>
      </div>
      <div class="market-row">
        <div>Abelardo de la Espriella</div>
        <div role="button">Yes\n99¢</div>
        <div role="button">No\n1¢</div>
      </div>
      <div class="market-row">
        <div>Sergio Fajardo</div>
        <div role="button">Yes\n5¢</div>
        <div role="button">No\n96¢</div>
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


ESPORTS_TEAM_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section id="esports-event">
      <h1>IEM Cologne Major 2026 winner</h1>
      <div class="market-row">
        <div>Team Vitality</div>
        <div role="button">Yes\n31¢</div>
        <div role="button">No\n70¢</div>
      </div>
      <div class="market-row">
        <div>Team Spirit</div>
        <div role="button">Yes\n27¢</div>
        <div role="button">No\n74¢</div>
      </div>
      <div class="market-row">
        <div>G2 Esports</div>
        <div role="button">Yes\n18¢</div>
        <div role="button">No\n83¢</div>
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


ESPORTS_MATCH_MARKET_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section id="cs-event">
      <h1>Counter-Strike: Vitality vs Team Falcons</h1>
      <div class="market-row">
        <div>Vitality</div>
        <div role="button">是\n57¢</div>
        <div role="button">否\n45¢</div>
      </div>
      <div class="market-row">
        <div>Team Falcons</div>
        <div role="button">是\n44¢</div>
        <div role="button">否\n58¢</div>
      </div>
      <div class="market-row">
        <div>G2</div>
        <div role="button">是\n51¢</div>
        <div role="button">否\n50¢</div>
      </div>
      <div class="market-row">
        <div>Spirit</div>
        <div role="button">是\n62¢</div>
        <div role="button">否\n40¢</div>
      </div>
      <div class="market-row">
        <div>Team Falcons +1.5</div>
        <div role="button">是\n63¢</div>
        <div role="button">否\n39¢</div>
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

            # World Cup group pages often render country labels in Chinese.
            # Cover the high-frequency uncovered countries from the bridge audit.
            group_cases = [
                (
                    "will-uruguay-win-group-h-in-the-2026-fifa-world-cup",
                    "Will Uruguay win Group H in the 2026 FIFA World Cup?",
                    "No",
                    ["否", "No"],
                    "乌拉圭",
                    "否",
                ),
                (
                    "will-ecuador-win-group-e-in-the-2026-fifa-world-cup",
                    "Will Ecuador win Group E in the 2026 FIFA World Cup?",
                    "Yes",
                    ["是", "Yes"],
                    "厄瓜多尔",
                    "是",
                ),
                (
                    "will-germany-win-group-e-in-the-2026-fifa-world-cup",
                    "Will Germany win Group E in the 2026 FIFA World Cup?",
                    "No",
                    ["否", "No"],
                    "德国",
                    "否",
                ),
                (
                    "will-belgium-win-group-g-in-the-2026-fifa-world-cup",
                    "Will Belgium win Group G in the 2026 FIFA World Cup?",
                    "No",
                    ["否", "No"],
                    "比利时",
                    "否",
                ),
                (
                    "will-spain-win-group-h-in-the-2026-fifa-world-cup",
                    "Will Spain win Group H in the 2026 FIFA World Cup?",
                    "No",
                    ["否", "No"],
                    "西班牙",
                    "No",
                ),
            ]
            for slug, title, outcome, side_labels, expected_row, expected_label in group_cases:
                page = await browser.new_page()
                await page.set_content(WORLD_CUP_GROUP_MULTI_COUNTRY_HTML)
                keywords = PolymtradeExecutor._extract_market_keywords(slug, title)
                assert expected_row in keywords, (title, keywords)
                result = await page.evaluate(
                    PolymtradeExecutor._select_outcome_script(),
                    [outcome, side_labels, keywords],
                )
                clicked_labels = await page.evaluate("window.clickedLabels")
                assert result["clicked"] is True, (title, result)
                assert expected_row in result["rowText"], (title, result)
                assert expected_label in result["label"], (title, result)
                assert clicked_labels == [result["label"]], (title, clicked_labels, result)

            remaining_country_cases = [
                (
                    "fifwc-bra-hai-2026-06-19",
                    "Will Haiti win on 2026-06-19?",
                    "No",
                    ["否", "No"],
                    "海地",
                    "否",
                ),
                (
                    "will-curacao-win-group-e-in-the-2026-fifa-world-cup",
                    "Will Curaçao win Group E in the 2026 FIFA World Cup?",
                    "No",
                    ["否", "No"],
                    "库拉索",
                    "否",
                ),
                (
                    "will-cape-verde-reach-the-2026-fifa-world-cup-final",
                    "Will Cape Verde reach the 2026 FIFA World Cup final?",
                    "No",
                    ["否", "No"],
                    "佛得角",
                    "否",
                ),
                (
                    "will-scotland-win-group-c-in-the-2026-fifa-world-cup",
                    "Will Scotland win Group C in the 2026 FIFA World Cup?",
                    "No",
                    ["否", "No"],
                    "苏格兰",
                    "否",
                ),
                (
                    "will-usa-reach-the-2026-fifa-world-cup-final",
                    "Will USA reach the 2026 FIFA World Cup final?",
                    "No",
                    ["否", "No"],
                    "美国",
                    "No",
                ),
                (
                    "will-usa-win-group-d-in-the-2026-fifa-world-cup",
                    "Will USA win Group D in the 2026 FIFA World Cup?",
                    "No",
                    ["否", "No"],
                    "美国",
                    "No",
                ),
            ]
            executor = PolymtradeExecutor()
            for slug, title, outcome, side_labels, expected_row, expected_label in remaining_country_cases:
                page = await browser.new_page()
                await page.set_content(WORLD_CUP_REMAINING_COUNTRY_HTML)
                keywords = executor._extract_market_keywords(slug, title)
                assert expected_row in keywords, (title, keywords)
                if "Haiti" in title:
                    assert "brazil" not in keywords, keywords
                    assert "巴西" not in keywords, keywords
                result = await page.evaluate(
                    PolymtradeExecutor._select_outcome_script(),
                    [outcome, side_labels, keywords],
                )
                clicked_labels = await page.evaluate("window.clickedLabels")
                assert result["clicked"] is True, (title, result)
                assert expected_row in result["rowText"], (title, result)
                assert expected_label in result["label"], (title, result)
                assert clicked_labels == [result["label"]], (title, clicked_labels, result)

            page = await browser.new_page()
            await page.set_content(WORLD_CUP_FINAL_HTML)
            mexico_keywords = executor._extract_market_keywords(
                "will-mexico-reach-the-2026-fifa-world-cup-final",
                "Will Mexico reach the 2026 FIFA World Cup final?",
            )
            assert "mexico" in mexico_keywords, mexico_keywords
            assert "墨西哥" in mexico_keywords, mexico_keywords
            result = await page.evaluate(
                PolymtradeExecutor._select_outcome_script(),
                ["No", ["否", "No"], mexico_keywords],
            )
            clicked_labels = await page.evaluate("window.clickedLabels")
            assert result["clicked"] is True, result
            assert "Mexico" in result["rowText"], result
            assert result["label"] == "No 88¢", result
            assert clicked_labels == ["No 88¢"], clicked_labels

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

            # Political candidate page: generic words like presidential/election
            # must not dominate the row match; the candidate name should anchor it.
            page = await browser.new_page()
            await page.set_content(POLITICAL_CANDIDATE_HTML)
            keywords = PolymtradeExecutor._extract_market_keywords(
                "will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election",
                "Will Abelardo de la Espriella win the 2026 Colombian presidential election?",
            )
            assert keywords == ["abelardo", "espriella", "colombian"], keywords
            result = await page.evaluate(
                PolymtradeExecutor._select_outcome_script(),
                ["Yes", ["是", "Yes", "Buy Yes", "Long"], keywords],
            )
            clicked_labels = await page.evaluate("window.clickedLabels")
            assert result["clicked"] is True, result
            assert result["label"] == "Yes 99¢", result
            assert "Abelardo" in result["rowText"], result
            assert clicked_labels == [result["label"]], clicked_labels

            # Esports team page: event-level terms like Team/IEM/Major are too
            # generic; the selector should anchor to the distinctive team name.
            page = await browser.new_page()
            await page.set_content(ESPORTS_TEAM_HTML)
            keywords = PolymtradeExecutor._extract_market_keywords(
                "will-team-spirit-win-iem-cologne-major-2026",
                "Will Team Spirit win IEM Cologne Major 2026?",
            )
            assert keywords == ["spirit"], keywords
            result = await page.evaluate(
                PolymtradeExecutor._select_outcome_script(),
                ["Yes", ["是", "Yes"], keywords],
            )
            clicked_labels = await page.evaluate("window.clickedLabels")
            assert result["clicked"] is True, result
            assert result["label"] == "Yes 27¢", result
            assert "Team Spirit" in result["rowText"], result
            assert "Team Vitality" not in result["rowText"], result
            assert clicked_labels == [result["label"]], clicked_labels

            esports_cases = [
                (
                    "counter-strike-vitality-vs-team-falcons-bo3-iem-cologne-major-playoffs",
                    "Counter-Strike: Vitality vs Team Falcons (BO3) - IEM Cologne Major Playoffs",
                    "Vitality",
                    "Vitality",
                    "是 57¢",
                ),
                (
                    "counter-strike-vitality-vs-team-falcons-map-1-winner",
                    "Counter-Strike: Vitality vs Team Falcons - Map 1 Winner",
                    "Vitality",
                    "Vitality",
                    "是 57¢",
                ),
                (
                    "counter-strike-spirit-vs-g2-bo3-iem-cologne-major-playoffs",
                    "Counter-Strike: Spirit vs G2 (BO3) - IEM Cologne Major Playoffs",
                    "G2",
                    "G2",
                    "是 51¢",
                ),
                (
                    "map-handicap-vit-1pt5-vs-team-falcons-plus-1pt5",
                    "Map Handicap: VIT (-1.5) vs Team Falcons (+1.5)",
                    "Team Falcons",
                    "Team Falcons",
                    "是 44¢",
                ),
            ]
            for slug, title, outcome, expected_row, expected_label in esports_cases:
                page = await browser.new_page()
                await page.set_content(ESPORTS_MATCH_MARKET_HTML)
                executor = PolymtradeExecutor()
                executor.page = page
                await executor._select_polymtrade_outcome(
                    outcome,
                    market_slug=slug,
                    market_title=title,
                    max_attempts=1,
                )
                clicked_labels = await page.evaluate("window.clickedLabels")
                assert clicked_labels == [expected_label], (title, clicked_labels)
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


CONTENTEDITABLE_BUY_FORM_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section class="trade-panel">
      <h2>Will Canada win the 2026 FIFA World Cup?</h2>
      <div>Buy Yes</div>
      <label>Amount</label>
      <div
        class="amount trade-input"
        role="textbox"
        aria-label="Amount USDC"
        contenteditable="true"
      ></div>
      <button>确认买入</button>
    </section>
  </main>
</body>
</html>
"""


TEXT_USDC_BUY_FORM_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section class="trade-panel" data-testid="trade-ticket">
      <h2>Will Mexico reach the 2026 FIFA World Cup final?</h2>
      <div>Buy No</div>
      <label for="amount-text">USDC</label>
      <input id="amount-text" type="text" aria-label="USDC" autocomplete="off" />
      <button>确认买入</button>
    </section>
  </main>
</body>
</html>
"""


SPINBUTTON_BUY_FORM_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section role="dialog" aria-label="Buy">
      <h2>Will Canada win the 2026 FIFA World Cup?</h2>
      <div>Buy Yes</div>
      <input role="spinbutton" aria-label="Amount" />
      <button>确认买入</button>
    </section>
  </main>
</body>
</html>
"""


CHINESE_ARIA_AMOUNT_BUY_FORM_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section class="trade-panel" data-testid="trade-ticket">
      <h2>Will Spain win Group H in the 2026 FIFA World Cup?</h2>
      <div>买入 否</div>
      <label for="amount-cn">金额</label>
      <input id="amount-cn" type="text" aria-label="金额 USDC" autocomplete="off" />
      <button>确认买入</button>
    </section>
  </main>
</body>
</html>
"""


CUSTOM_SPINBUTTON_BUY_FORM_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section role="dialog" aria-label="Buy">
      <h2>Will Canada win the 2026 FIFA World Cup?</h2>
      <div>Buy Yes</div>
      <div
        role="spinbutton"
        tabindex="0"
        aria-label="金额 USDC"
        aria-valuenow=""
        class="amount-control"
        style="display: inline-block; min-width: 120px; min-height: 28px;"
      >0</div>
      <button>确认买入</button>
    </section>
  </main>
</body>
</html>
"""


PORTFOLIO_WITH_PM_BUY_HTML = """
<!doctype html>
<html>
<body>
  <main>
    <section class="wallet-card">
      <div>余额 0 PM</div>
      <button>卖出 $PM</button>
      <button>买入 $PM</button>
      <div>Solana钱包地址 217m...5y9x</div>
    </section>
    <section class="positions">
      <h2>持仓 历史</h2>
      <article>
        <h3>Will Mexico reach the 2026 FIFA World Cup final?</h3>
        <div>No - 0.38 份</div>
      </article>
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


DELAYED_ROLE_SELL_CONFIRM_DIALOG_HTML = """
<!doctype html>
<html>
<body>
  <div role="dialog" class="trade-modal">
    <h2>卖出 Belgium No</h2>
    <input name="soldAmount" inputmode="decimal" value="2.0" />
    <div role="button" aria-disabled="true" id="confirm-sell-role" class="cursor-pointer disabled">
      <span>确认卖出</span>
    </div>
  </div>
  <script>
    window.clickedIds = [];
    setTimeout(() => {
      const btn = document.getElementById('confirm-sell-role');
      btn.setAttribute('aria-disabled', 'false');
      btn.className = 'cursor-pointer';
    }, 250);
    document.addEventListener("click", (event) => {
      window.clickedIds.push(event.target.id || event.target.closest('[role="button"]')?.id || (event.target.innerText || "").trim());
    });
  </script>
</body>
</html>
"""


ATTRIBUTE_ONLY_SELL_CONFIRM_DIALOG_HTML = """
<!doctype html>
<html>
<body>
  <form role="dialog" class="order-modal">
    <h2>卖出 Argentina Yes</h2>
    <input name="soldAmount" inputmode="decimal" value="2.4691" />
    <button type="button" id="cancel">取消</button>
    <button type="submit" data-testid="sell-submit" aria-label="确认卖出"></button>
  </form>
  <script>
    window.clickedIds = [];
    document.addEventListener("click", (event) => {
      window.clickedIds.push(event.target.id || event.target.getAttribute('data-testid') || (event.target.innerText || "").trim());
      event.preventDefault();
    });
  </script>
</body>
</html>
"""


ICON_ONLY_SELL_CONFIRM_DIALOG_HTML = """
<!doctype html>
<html>
<body>
  <div role="dialog" class="trade-modal">
    <h2>卖出 Belgium No</h2>
    <input name="soldAmount" inputmode="decimal" value="2.11" />
    <button aria-label="确认卖出" data-test="confirm-sell">
      <svg aria-hidden="true"></svg>
    </button>
  </div>
  <script>
    window.clickedIds = [];
    document.addEventListener("click", (event) => {
      window.clickedIds.push(event.target.id || event.target.closest('button')?.getAttribute('data-test') || (event.target.innerText || "").trim());
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

            await page.set_content(CONTENTEDITABLE_BUY_FORM_HTML)
            is_open = await executor._is_buy_dialog_open(timeout=0.5)
            assert is_open is True, "Contenteditable amount textbox should count as buy dialog"
            await executor._enter_amount(2.0)
            value = await page.eval_on_selector("[contenteditable='true']", "el => el.textContent")
            assert value == "2.0", value

            await page.set_content(TEXT_USDC_BUY_FORM_HTML)
            is_open = await executor._is_buy_dialog_open(timeout=0.5)
            assert is_open is True, "Text USDC input should count as buy dialog"
            await executor._enter_amount(2.0)
            value = await page.eval_on_selector("#amount-text", "el => el.value")
            assert value == "2.0", value

            await page.set_content(SPINBUTTON_BUY_FORM_HTML)
            is_open = await executor._is_buy_dialog_open(timeout=0.5)
            assert is_open is True, "role=spinbutton amount input should count as buy dialog"
            await executor._enter_amount(2.0)
            value = await page.eval_on_selector("[role='spinbutton']", "el => el.value")
            assert value == "2.0", value

            await page.set_content(CHINESE_ARIA_AMOUNT_BUY_FORM_HTML)
            is_open = await executor._is_buy_dialog_open(timeout=0.5)
            assert is_open is True, "Chinese aria-label amount input should count as buy dialog"
            await executor._enter_amount(2.0)
            value = await page.eval_on_selector("#amount-cn", "el => el.value")
            assert value == "2.0", value

            await page.set_content(CUSTOM_SPINBUTTON_BUY_FORM_HTML)
            is_open = await executor._is_buy_dialog_open(timeout=0.5)
            assert is_open is True, "Custom role=spinbutton amount control should count as buy dialog"
            await executor._enter_amount(2.0)
            value = await page.eval_on_selector(
                "[role='spinbutton']",
                "el => el.textContent || el.getAttribute('aria-valuenow') || el.getAttribute('data-bridge-filled-value')",
            )
            assert value == "2.0", value

            await page.set_content(PORTFOLIO_WITH_PM_BUY_HTML)
            is_open = await executor._is_buy_dialog_open(timeout=0.5)
            assert is_open is False, "Portfolio PM buy button must not count as an open buy dialog"

            await page.set_content(SELL_POSITION_WITH_PM_WALLET_HTML)
            is_open = await executor._is_sell_dialog_open(timeout=0.5)
            assert is_open is False, "Portfolio sell buttons must not count as an open sell dialog"
            try:
                await executor._click_sell_button()
                raise AssertionError("Expected _click_sell_button to reject missing sell dialog")
            except RuntimeError as exc:
                assert "Sell dialog disappeared before submit" in str(exc), exc
            clicked_ids = await page.evaluate("window.clickedIds")
            assert clicked_ids == [], clicked_ids

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

            await page.set_content(DELAYED_ROLE_SELL_CONFIRM_DIALOG_HTML)
            await executor._click_sell_button()
            clicked_ids = await page.evaluate("window.clickedIds")
            assert "confirm-sell-role" in clicked_ids, clicked_ids

            await page.set_content(ATTRIBUTE_ONLY_SELL_CONFIRM_DIALOG_HTML)
            await executor._click_sell_button()
            clicked_ids = await page.evaluate("window.clickedIds")
            assert "sell-submit" in clicked_ids, clicked_ids

            await page.set_content(ICON_ONLY_SELL_CONFIRM_DIALOG_HTML)
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
