"""A denial pauses the host, including other queries and process restarts."""
import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from polymtrade_executor import PolymtradeExecutor
from bridge_metrics import metrics


@pytest.fixture
def executor(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_PROFILE_DIR", str(tmp_path))
    return PolymtradeExecutor()


async def test_gamma_denial_stops_different_queued_queries_and_survives_restart(executor):
    calls = []
    failures_before = metrics.gamma_api_failures

    async def handler(request):
        calls.append(request)
        await asyncio.sleep(0)
        return httpx.Response(403)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        results = await asyncio.gather(*(
            executor._gamma_request_with_retry(client, "https://gamma-api.polymarket.com/public-search", {"q": str(i)})
            for i in range(12)
        ), return_exceptions=True)
        assert all(isinstance(result, Exception) for result in results)
        assert len(calls) == 1
        assert metrics.gamma_api_failures - failures_before == 1
        restarted = PolymtradeExecutor()
        with pytest.raises(RuntimeError, match="cooldown"):
            await restarted._gamma_request_with_retry(client, "https://gamma-api.polymarket.com/events", {"slug": "other"})
        assert len(calls) == 1
    saved = json.loads((Path(executor.profile_dir) / ".polyhermes-upstream-cooldowns.json").read_text())
    assert set(saved) == {"gamma-api.polymarket.com"}
    assert set(saved["gamma-api.polymarket.com"]) == {"status", "retry_at", "failures"}


async def test_polymtrade_denial_blocks_other_navigation_without_clearing_login(executor):
    executor._logged_in = True
    executor.page = SimpleNamespace(goto=AsyncMock(return_value=SimpleNamespace(status=403, headers={})))
    executor._clear_stale_app_caches = AsyncMock()
    with pytest.raises(RuntimeError, match="HTTP 403"):
        await executor._goto_with_retry("https://polym.trade/portfolio")
    with pytest.raises(RuntimeError, match="cooldown"):
        await executor._goto_with_retry("https://polym.trade/")
    executor.page.goto.assert_awaited_once()
    executor._clear_stale_app_caches.assert_not_awaited()
    assert executor._logged_in is True


async def test_gamma_requests_are_serial_and_paced(executor):
    active = 0
    max_active = 0
    starts = []

    async def handler(_request):
        nonlocal active, max_active
        active += 1
        max_active = max(max_active, active)
        starts.append(asyncio.get_running_loop().time())
        await asyncio.sleep(0.01)
        active -= 1
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await asyncio.gather(*(
            executor._gamma_request_with_retry(client, "https://gamma-api.polymarket.com/events", {"slug": str(i)})
            for i in range(3)
        ))
    assert max_active == 1
    assert all(right - left >= 0.24 for left, right in zip(starts, starts[1:]))


async def test_rate_limit_retry_after_is_honored_across_routes(executor):
    now = [100.0]
    executor.page = SimpleNamespace(goto=AsyncMock(return_value=SimpleNamespace(status=429, headers={"retry-after": "900"})))
    with patch("time.time", side_effect=lambda: now[0]):
        with pytest.raises(RuntimeError, match="HTTP 429"):
            await executor._goto_with_retry("https://polym.trade/portfolio")
        now[0] += 301
        with pytest.raises(RuntimeError, match="cooldown"):
            await executor._goto_with_retry("https://polym.trade/")
        executor.page.goto.assert_awaited_once()
