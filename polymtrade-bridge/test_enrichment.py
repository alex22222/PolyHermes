#!/usr/bin/env python3
"""Tests for portfolio position enrichment and Gamma API retry logic."""

import asyncio
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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

    with patch.object(executor, "_search_gamma_markets_by_title", new=AsyncMock(return_value=mock_markets)):
        result = await executor._enrich_position(
            {"marketTitle": "Will France win the 2026 FIFA World Cup?"}
        )

    assert result["conditionId"] == "0xabc123"
    assert result["marketSlug"] == "will-france-win-the-2026-fifa-world-cup"
    assert result["eventSlug"] == "2026-fifa-world-cup-winner"
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

    with patch.object(executor, "_search_gamma_events_by_title", new=AsyncMock(return_value=mock_events)):
        result = await executor._enrich_position(
            {
                "marketTitle": "Will USA win Group D?",
                "href": "/portfolio?eventId=22222&eventSlug=world-cup-group-d-winner&eventSource=polymarket",
            }
        )

    assert result["conditionId"] == "0xusa"
    assert result["eventSlug"] == "world-cup-group-d-winner"
    print("test_extract_href_from_portfolio_card passed")


def main() -> int:
    tests = [
        test_enrich_position_via_market_slug,
        test_enrich_position_via_title_search,
        test_enrich_position_no_match,
        test_gamma_request_with_retry_success,
        test_gamma_request_with_retry_transient,
        test_gamma_request_with_retry_exhausted,
        test_extract_href_from_portfolio_card,
    ]
    for test in tests:
        asyncio.run(test())
    print("all enrichment tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
