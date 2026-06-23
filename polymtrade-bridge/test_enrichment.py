#!/usr/bin/env python3
"""Tests for portfolio position enrichment and Gamma API retry logic."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from playwright.async_api import async_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
from polymtrade_executor import PolymtradeExecutor  # noqa: E402


async def test_enrich_position_via_market_slug():
    executor = PolymtradeExecutor()
    executor.proxy = None

    mock_markets = [
        {
            "question": "Will France win the 2026 FIFA World Cup?",
            "slug": "will-france-win-the-2026-fifa-world-cup",
            "conditionId": "0xabc123",
            "events": [{"slug": "2026-fifa-world-cup-winner", "id": 12345}],
        }
    ]

    market_slug_search = AsyncMock(return_value=mock_markets)
    with patch.object(executor, "_search_gamma_markets_by_slug", new=market_slug_search):
        result = await executor._enrich_position(
            {
                "marketTitle": "Will France win the 2026 FIFA World Cup?",
                "marketSlug": "will-france-win-the-2026-fifa-world-cup",
            }
        )

    assert result["conditionId"] == "0xabc123"
    assert result["marketSlug"] == "will-france-win-the-2026-fifa-world-cup"
    assert result["eventSlug"] == "2026-fifa-world-cup-winner"
    market_slug_search.assert_awaited_once_with("will-france-win-the-2026-fifa-world-cup")
    print("test_enrich_position_via_market_slug passed")


async def test_enrich_position_via_title_search():
    executor = PolymtradeExecutor()
    executor.proxy = None

    mock_markets = [
        {
            "question": "Will Belgium win Group G in the 2026 FIFA World Cup?",
            "slug": "will-belgium-win-group-g-in-the-2026-fifa-world-cup",
            "conditionId": "0xbelgium",
            "events": [{"slug": "world-cup-group-g-winner", "id": 99999}],
        }
    ]

    with patch.object(executor, "_search_gamma_events_by_slug", new=AsyncMock(return_value=[])):
        with patch.object(executor, "_search_gamma_markets_by_slug", new=AsyncMock(return_value=[])):
            with patch.object(executor, "_search_gamma_markets_by_title", new=AsyncMock(return_value=mock_markets)):
                result = await executor._enrich_position(
                    {"marketTitle": "Will Belgium win Group G in the 2026 FIFA World Cup?"}
                )

    assert result["conditionId"] == "0xbelgium"
    assert result["marketSlug"] == "will-belgium-win-group-g-in-the-2026-fifa-world-cup"
    assert result["eventSlug"] == "world-cup-group-g-winner"
    print("test_enrich_position_via_title_search passed")


async def test_enrich_position_no_match():
    executor = PolymtradeExecutor()
    executor.proxy = None

    with patch.object(executor, "_search_gamma_markets_by_slug", new=AsyncMock(return_value=[])):
        with patch.object(executor, "_search_gamma_markets_by_title", new=AsyncMock(return_value=[])):
            with patch.object(executor, "_search_gamma_events_by_title", new=AsyncMock(return_value=[])):
                result = await executor._enrich_position({"marketTitle": "Unknown Market"})

    assert result == {}
    print("test_enrich_position_no_match passed")


async def test_gamma_request_with_retry_success():
    executor = PolymtradeExecutor()

    mock_resp = MagicMock()
    mock_resp.json.return_value = {"result": "ok"}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    result = await executor._gamma_request_with_retry(
        mock_client, "https://example.com/api", {"q": "test"}
    )
    assert result == {"result": "ok"}
    assert mock_client.get.call_count == 1
    print("test_gamma_request_with_retry_success passed")


async def test_gamma_request_with_retry_transient():
    executor = PolymtradeExecutor()

    # First call fails with ConnectError, second succeeds.
    mock_resp = MagicMock()
    mock_resp.json.return_value = {"result": "ok"}
    mock_resp.raise_for_status = MagicMock()

    mock_client = MagicMock()
    mock_client.get = AsyncMock(
        side_effect=[
            Exception("ConnectError"),
            mock_resp,
        ]
    )

    result = await executor._gamma_request_with_retry(
        mock_client, "https://example.com/api", {"q": "test"}, max_retries=3, base_delay=0.01
    )
    assert result == {"result": "ok"}
    assert mock_client.get.call_count == 2
    print("test_gamma_request_with_retry_transient passed")


async def test_gamma_request_with_retry_exhausted():
    executor = PolymtradeExecutor()

    mock_client = MagicMock()
    mock_client.get = AsyncMock(side_effect=Exception("ConnectError"))

    try:
        await executor._gamma_request_with_retry(
            mock_client, "https://example.com/api", {"q": "test"}, max_retries=2, base_delay=0.01
        )
        assert False, "Expected exception"
    except Exception as e:
        assert "ConnectError" in str(e)
    assert mock_client.get.call_count == 2
    print("test_gamma_request_with_retry_exhausted passed")


async def test_extract_href_from_portfolio_card():
    """Verify that href with eventSlug is parsed into event_slug."""
    executor = PolymtradeExecutor()
    executor.proxy = None

    mock_events = [
        {
            "title": "World Cup Group D Winner",
            "slug": "world-cup-group-d-winner",
            "id": 22222,
            "markets": [
                {
                    "question": "Will USA win Group D?",
                    "slug": "will-usa-win-group-d",
                    "conditionId": "0xusa",
                }
            ],
        }
    ]

    with patch.object(executor, "_search_gamma_events_by_slug", new=AsyncMock(return_value=mock_events)):
        result = await executor._enrich_position(
            {
                "marketTitle": "Will USA win Group D?",
                "href": "/portfolio?eventId=22222&eventSlug=world-cup-group-d-winner&eventSource=polymarket",
            }
        )

    assert result["conditionId"] == "0xusa"
    assert result["eventSlug"] == "world-cup-group-d-winner"
    print("test_extract_href_from_portfolio_card passed")


async def test_wrong_href_event_slug_falls_back_to_title_search():
    """A stale/current carousel href must not contaminate portfolio metadata."""
    executor = PolymtradeExecutor()
    executor.proxy = None

    wrong_events = [
        {
            "title": "New Rhianna Album Before GTA VI?",
            "slug": "new-rhianna-album-before-gta-vi-926",
            "id": 11111,
            "markets": [
                {
                    "question": "Will Abelardo de la Espriella win the 2026 Colombian presidential election?",
                    "slug": "will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election",
                    "conditionId": "0xwrong",
                }
            ],
        }
    ]
    correct_markets = [
        {
            "question": "Will Spain win Group H in the 2026 FIFA World Cup?",
            "slug": "will-spain-win-group-h-in-the-2026-fifa-world-cup",
            "conditionId": "0xspain",
            "events": [{"slug": "world-cup-group-h-winner", "id": 98287}],
        }
    ]

    with patch.object(executor, "_search_gamma_events_by_slug", new=AsyncMock(return_value=wrong_events)):
        with patch.object(executor, "_search_gamma_markets_by_slug", new=AsyncMock(return_value=[])):
            with patch.object(executor, "_search_gamma_markets_by_title", new=AsyncMock(return_value=correct_markets)):
                result = await executor._enrich_position(
                    {
                        "marketTitle": "Will Spain win Group H in the 2026 FIFA World Cup?",
                        "href": "/portfolio?eventId=11111&eventSlug=new-rhianna-album-before-gta-vi-926&eventSource=polymarket",
                    }
                )

    assert result["conditionId"] == "0xspain"
    assert result["marketSlug"] == "will-spain-win-group-h-in-the-2026-fifa-world-cup"
    assert result["eventSlug"] == "world-cup-group-h-winner"
    print("test_wrong_href_event_slug_falls_back_to_title_search passed")


async def test_title_search_without_exact_match_does_not_use_first_result():
    executor = PolymtradeExecutor()
    executor.proxy = None

    wrong_markets = [
        {
            "question": "Will Abelardo de la Espriella win the 2026 Colombian presidential election?",
            "slug": "will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election",
            "conditionId": "0xwrong",
            "events": [{"slug": "what-will-happen-before-gta-vi", "id": 11111}],
        }
    ]

    with patch.object(executor, "_search_gamma_markets_by_slug", new=AsyncMock(return_value=[])):
        with patch.object(executor, "_search_gamma_markets_by_title", new=AsyncMock(return_value=wrong_markets)):
            with patch.object(executor, "_search_gamma_events_by_slug", new=AsyncMock(return_value=[])):
                with patch.object(executor, "_search_gamma_events_by_title", new=AsyncMock(return_value=[])):
                    result = await executor._enrich_position(
                        {"marketTitle": "Will Belgium win Group G in the 2026 FIFA World Cup?"}
                    )

    assert result == {}
    print("test_title_search_without_exact_match_does_not_use_first_result passed")


async def test_world_cup_group_title_uses_derived_event_slug():
    executor = PolymtradeExecutor()
    executor.proxy = None

    group_h_event = [
        {
            "title": "World Cup Group H Winner",
            "slug": "world-cup-group-h-winner",
            "id": 98287,
            "markets": [
                {
                    "question": "Will Cape Verde win Group H in the 2026 FIFA World Cup?",
                    "slug": "will-cape-verde-win-group-h-in-the-2026-fifa-world-cup",
                    "conditionId": "0xcapeverde",
                },
                {
                    "question": "Will Spain win Group H in the 2026 FIFA World Cup?",
                    "slug": "will-spain-win-group-h-in-the-2026-fifa-world-cup",
                    "conditionId": "0xspain",
                },
            ],
        }
    ]
    wrong_title_search = AsyncMock(
        return_value=[
            {
                "question": "New Rihanna Album before GTA VI?",
                "slug": "new-rhianna-album-before-gta-vi-926",
                "conditionId": "0xwrong",
                "events": [{"slug": "what-will-happen-before-gta-vi", "id": 11111}],
            }
        ]
    )

    with patch.object(executor, "_search_gamma_events_by_slug", new=AsyncMock(return_value=group_h_event)) as event_search:
        with patch.object(executor, "_search_gamma_markets_by_title", new=wrong_title_search):
            result = await executor._enrich_position(
                {"marketTitle": "Will Spain win Group H in the 2026 FIFA World Cup?"}
            )

    assert result["conditionId"] == "0xspain"
    assert result["marketSlug"] == "will-spain-win-group-h-in-the-2026-fifa-world-cup"
    assert result["eventSlug"] == "world-cup-group-h-winner"
    event_search.assert_awaited_once_with("world-cup-group-h-winner")
    wrong_title_search.assert_not_awaited()
    print("test_world_cup_group_title_uses_derived_event_slug passed")


async def test_political_title_uses_derived_market_slug():
    executor = PolymtradeExecutor()
    executor.proxy = None

    abelardo_markets = [
        {
            "question": "Will Abelardo de la Espriella  win the 2026 Colombian presidential election?",
            "slug": "will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election",
            "conditionId": "0xfbe852",
            "events": [{"slug": "colombia-presidential-election", "id": 34584}],
        }
    ]
    market_slug_search = AsyncMock(return_value=abelardo_markets)

    with patch.object(executor, "_search_gamma_events_by_slug", new=AsyncMock(return_value=[])):
        with patch.object(executor, "_search_gamma_markets_by_slug", new=market_slug_search):
            with patch.object(
                executor,
                "_search_gamma_markets_by_title",
                new=AsyncMock(side_effect=AssertionError("title search should not be needed")),
            ):
                result = await executor._enrich_position(
                    {
                        "marketTitle": (
                            "Will Abelardo de la Espriella win the 2026 "
                            "Colombian presidential election?"
                        )
                    }
                )

    assert result["conditionId"] == "0xfbe852"
    assert result["marketSlug"] == "will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election"
    assert result["eventSlug"] == "colombia-presidential-election"
    market_slug_search.assert_awaited_once_with(
        "will-abelardo-de-la-espriella-win-the-2026-colombian-presidential-election"
    )
    print("test_political_title_uses_derived_market_slug passed")


async def test_enrichment_does_not_click_portfolio_cards():
    executor = PolymtradeExecutor()
    executor.proxy = None
    executor.page = MagicMock()
    executor.page.url = "https://polym.trade/portfolio"
    executor.page.eval_on_selector_all = AsyncMock(side_effect=AssertionError("must not click portfolio"))

    with patch.object(executor, "_search_gamma_markets_by_slug", new=AsyncMock(return_value=[])):
        with patch.object(executor, "_search_gamma_markets_by_title", new=AsyncMock(return_value=[])):
            with patch.object(executor, "_search_gamma_events_by_title", new=AsyncMock(return_value=[])):
                result = await executor._enrich_position(
                    {"marketTitle": "Will Argentina reach the 2026 FIFA World Cup final?"}
                )

    assert result == {}
    executor.page.eval_on_selector_all.assert_not_called()
    print("test_enrichment_does_not_click_portfolio_cards passed")


async def test_wait_for_portfolio_rows_waits_for_delayed_render():
    html = """
    <!doctype html>
    <html>
    <body>
      <main>
        <div>投资组合</div>
        <div>持仓</div>
        <ul id="positions"></ul>
      </main>
      <script>
        setTimeout(() => {
          const li = document.createElement('li');
          li.className = 'flex px-4 py-2 border-b text-xs items-center cursor-pointer';
          li.textContent = 'Will Spain win Group H in the 2026 FIFA World Cup?\\n$2\\nNo• 14.8 份';
          document.querySelector('#positions').appendChild(li);
        }, 250);
      </script>
    </body>
    </html>
    """
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(html)
            executor = PolymtradeExecutor()
            executor.page = page
            rendered = await executor._wait_for_portfolio_rows(timeout=3.0)
            assert rendered is True
        finally:
            await browser.close()
    print("test_wait_for_portfolio_rows_waits_for_delayed_render passed")


def main() -> int:
    tests = [
        test_enrich_position_via_market_slug,
        test_enrich_position_via_title_search,
        test_enrich_position_no_match,
        test_gamma_request_with_retry_success,
        test_gamma_request_with_retry_transient,
        test_gamma_request_with_retry_exhausted,
        test_extract_href_from_portfolio_card,
        test_wrong_href_event_slug_falls_back_to_title_search,
        test_title_search_without_exact_match_does_not_use_first_result,
        test_world_cup_group_title_uses_derived_event_slug,
        test_political_title_uses_derived_market_slug,
        test_enrichment_does_not_click_portfolio_cards,
        test_wait_for_portfolio_rows_waits_for_delayed_render,
    ]
    for test in tests:
        asyncio.run(test())
    print("all enrichment tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
