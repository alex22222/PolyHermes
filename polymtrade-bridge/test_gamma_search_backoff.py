"""Gamma search contract, deduplication, query and host failure cooldown."""

import asyncio
from contextlib import asynccontextmanager
from unittest.mock import patch

import httpx
import pytest

from polymtrade_executor import PolymtradeExecutor


@pytest.fixture(autouse=True)
def isolated_profile(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_PROFILE_DIR", str(tmp_path))


async def test_quoted_title_uses_public_search_and_shares_market_event_result():
    title = 'Will Rand Paul vote “Yea” on the Clarity Act?'
    calls = []

    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0)
        return httpx.Response(200, json={"events": [{"id": "12", "slug": "clarity", "markets": [
            {"question": title, "conditionId": "condition", "slug": "rand-paul"},
        ]}]})

    executor = PolymtradeExecutor()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        @asynccontextmanager
        async def context():
            yield client
        with patch.object(executor, "_http_client_context", context):
            markets, events = await asyncio.gather(executor._search_gamma_markets_by_title(title), executor._search_gamma_events_by_title(title))
            assert (await executor._search_gamma_markets_by_title(title)) == markets
    assert len(calls) == 1
    assert calls[0].url.path == "/public-search"
    assert calls[0].url.params["q"] == title
    assert "title" not in calls[0].url.params
    assert markets[0]["conditionId"] == "condition"
    assert markets[0]["events"][0]["slug"] == "clarity"
    assert events[0]["id"] == "12"


async def test_forbidden_query_is_singleflight_cooled_down_and_backed_off():
    calls = []
    now = [100.0]

    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0)
        return httpx.Response(403)

    executor = PolymtradeExecutor()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        async def query(title="blocked"):
            return await executor._gamma_request_with_retry(client, "https://gamma-api.polymarket.com/events", {"slug": title})

        with patch("polymtrade_executor.time.monotonic", side_effect=lambda: now[0]), patch("upstream_cooldown.time.time", side_effect=lambda: now[0]):
            results = await asyncio.gather(query(), query(), return_exceptions=True)
            assert all(isinstance(result, Exception) for result in results)
            assert len(calls) == 1
            for _ in range(10):
                with pytest.raises(RuntimeError, match="cooldown"):
                    await query()
            assert len(calls) == 1
            with pytest.raises(RuntimeError, match="cooldown"):
                await query("other")
            assert len(calls) == 1
            now[0] += 1801
            with pytest.raises(httpx.HTTPStatusError):
                await query()
            assert len(calls) == 2
            now[0] += 1801
            with pytest.raises(RuntimeError, match="cooldown"):
                await query()
            assert len(calls) == 2


async def test_empty_success_is_cached_and_caller_cannot_mutate_cache():
    count = 0
    async def handler(request):
        nonlocal count
        count += 1
        return httpx.Response(200, json={"events": []})
    executor = PolymtradeExecutor()
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        first = await executor._gamma_request_with_retry(client, "https://gamma-api.polymarket.com/public-search", {"q": "missing"})
        first["events"].append({"bad": True})
        second = await executor._gamma_request_with_retry(client, "https://gamma-api.polymarket.com/public-search", {"q": "missing"})
    assert second == {"events": []}
    assert count == 1


async def test_local_deferral_does_not_extend_query_failure_past_host_deadline():
    executor = PolymtradeExecutor()
    now = [100.0]
    calls = []
    url = "https://gamma-api.polymarket.com/events"

    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with patch("polymtrade_executor.time.monotonic", side_effect=lambda: now[0]), patch("upstream_cooldown.time.time", side_effect=lambda: now[0]):
            executor._upstream_cooldown.record(url, 403)
            for moment in (100.0, 1890.0):
                now[0] = moment
                with pytest.raises(RuntimeError, match="cooldown"):
                    await executor._gamma_request_with_retry(client, url, {"slug": "target"})
                await asyncio.sleep(0)
            assert not calls
            now[0] = 1901.0
            assert await executor._gamma_request_with_retry(client, url, {"slug": "target"}) == []
    assert len(calls) == 1
