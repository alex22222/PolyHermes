"""A forbidden metadata search is not an invitation to keep probing it."""
import json
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest

from polymtrade_executor import PolymtradeExecutor


@pytest.fixture
def executor(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_PROFILE_DIR", str(tmp_path))
    monkeypatch.setattr("polymtrade_executor.asyncio.sleep", AsyncMock())
    return PolymtradeExecutor()


async def test_forbidden_search_is_not_retried_after_cooldown_or_restart(executor):
    url = "https://gamma-api.polymarket.com/public-search"
    params = {"q": 'Will Example vote "Yea"?', "limit_per_type": "10"}
    now = [100.0]
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(403)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with patch("upstream_cooldown.time.time", side_effect=lambda: now[0]), patch("polymtrade_executor.time.monotonic", side_effect=lambda: now[0]):
            with pytest.raises(httpx.HTTPStatusError):
                await executor._gamma_request_with_retry(client, url, params)
            original = dict(executor._upstream_cooldown.entries)
            now[0] += 86400
            for instance in (executor, PolymtradeExecutor()):
                with pytest.raises(RuntimeError, match="quarantined"):
                    await instance._gamma_request_with_retry(client, url, params)
            assert len(calls) == 1
            assert executor._upstream_cooldown.entries == original


async def test_search_denial_does_not_relax_host_guard_for_other_requests(executor):
    calls = []
    now = [100.0]

    async def handler(request):
        calls.append(request)
        return httpx.Response(403) if request.url.path == "/public-search" else httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with patch("upstream_cooldown.time.time", side_effect=lambda: now[0]), patch("polymtrade_executor.time.monotonic", side_effect=lambda: now[0]):
            with pytest.raises(httpx.HTTPStatusError):
                await executor._gamma_request_with_retry(client, "https://gamma-api.polymarket.com/public-search", {"q": "denied"})
            with pytest.raises(RuntimeError, match="cooldown"):
                await executor._gamma_request_with_retry(client, "https://gamma-api.polymarket.com/events", {"slug": "allowed"})
            assert len(calls) == 1
            now[0] += 1801
            assert await executor._gamma_request_with_retry(client, "https://gamma-api.polymarket.com/events", {"slug": "allowed"}) == []
            assert len(calls) == 2


async def test_quarantined_enrichment_remains_unresolved_without_alternate_search(executor):
    title = 'Will Example vote "Yea"?'
    calls = []
    now = [100.0]

    async def handler(request):
        calls.append(request)
        return httpx.Response(403) if request.url.path == "/public-search" else httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        @asynccontextmanager
        async def context():
            yield client
        with patch.object(executor, "_http_client_context", context), patch("upstream_cooldown.time.time", side_effect=lambda: now[0]), patch("polymtrade_executor.time.monotonic", side_effect=lambda: now[0]):
            assert await executor._resolve_position_metadata({"marketTitle": title}) == {}
            now[0] += 86400
            assert await executor._resolve_position_metadata({"marketTitle": title}) == {}
    searches = [r for r in calls if r.url.path == "/public-search"]
    assert len(searches) == 1
    assert searches[0].url.params["q"] == title


async def test_corrupt_search_denial_state_fails_closed_only_for_search(executor):
    from pathlib import Path
    path = Path(executor.profile_dir) / ".polyhermes-gamma-search-denials.json"
    path.write_text("not valid json")
    restarted = PolymtradeExecutor()
    calls = []

    async def handler(request):
        calls.append(request)
        return httpx.Response(200, json=[])

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(RuntimeError, match="quarantined"):
            await restarted._gamma_request_with_retry(client, "https://gamma-api.polymarket.com/public-search", {"q": "title"})
        assert await restarted._gamma_request_with_retry(client, "https://gamma-api.polymarket.com/events", {"slug": "exact"}) == []
    assert len(calls) == 1


async def test_search_denial_file_contains_no_title_or_credentials(executor):
    from pathlib import Path
    title = 'private-looking title "Yea"'
    async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(403))) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await executor._gamma_request_with_retry(client, "https://gamma-api.polymarket.com/public-search", {"q": title})
    path = Path(executor.profile_dir) / ".polyhermes-gamma-search-denials.json"
    saved = path.read_text()
    assert title not in saved and "Yea" not in saved
    assert path.stat().st_mode & 0o777 == 0o600
    assert len(json.loads(saved)) == 1
