"""Native event navigation and fail-closed metadata denial regressions."""
import asyncio
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

import httpx
import pytest
from playwright.async_api import async_playwright

from polymtrade_executor import PolymtradeExecutor
from upstream_cooldown import UpstreamAccessDeferred


@pytest.fixture
def executor(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_PROFILE_DIR", str(tmp_path))
    return PolymtradeExecutor()


@pytest.mark.parametrize("side", ["BUY", "SELL"])
async def test_trade_starts_on_native_event_route_without_any_order_action(executor, side):
    goto = AsyncMock(side_effect=RuntimeError("stop before any trade action"))
    with patch.object(executor, "_goto_with_retry", goto):
        with pytest.raises(RuntimeError, match="stop before any trade action"):
            if side == "BUY":
                await executor._execute_buy_on_page("123", "exact-parent", "Yes", 1,
                                                    market_slug="exact-child")
            else:
                await executor._execute_sell("123", "exact-parent", "Yes", 1,
                                             market_slug="exact-child")
    assert goto.await_args.args[0] == "https://polym.trade/event/exact-parent"


async def test_native_grouped_event_accepts_only_requested_deadline(executor):
    slug = "israel-x-iran-ceasefire-continues-throughptptpt-20260716224448963"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            # The heading and market list are separate, as on the live page.
            await page.route("https://polym.trade/**", lambda route: route.fulfill(
                body="<main><h1>Israel x Iran ceasefire continues through...?</h1>"
                     "<section><article class='market-row'>October 31"
                     "<button>Yes 84¢</button><button>No 17¢</button></article></section></main>",
                content_type="text/html"))
            await page.goto("https://polym.trade/event/" + slug)
            executor.page = page
            target = dict(outcome="Yes", market_slug=slug,
                          market_title="Israel x Iran ceasefire continues through October 31?",
                          event_id="123", event_slug=slug, timeout=0.15)
            assert await executor._is_target_event_visible(**target) is True
            await page.locator("article").evaluate("e => e.firstChild.textContent = 'October 21'")
            assert await executor._is_target_event_visible(**target) is False
        finally:
            await browser.close()


async def test_gamma_denial_does_not_fall_through_to_clob_or_other_routes(executor):
    calls = []
    executor._logged_in = True

    async def handler(request):
        calls.append(str(request.url))
        return httpx.Response(403, text="error code: 1010", headers={"cf-ray": "request-id"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        @asynccontextmanager
        async def context():
            yield client
        with patch.object(executor, "_http_client_context", context):
            with pytest.raises(httpx.HTTPStatusError):
                await executor._resolve_event_uncached("exact-event", "0xcondition")
            with pytest.raises(UpstreamAccessDeferred):
                await executor._resolve_event_uncached("exact-event", "0xcondition")
    assert len(calls) == 1
    assert "gamma-api.polymarket.com/events" in calls[0]
    assert executor._logged_in is True


async def test_clob_denial_is_cooled_down_across_conditions(executor):
    calls = []

    async def handler(request):
        calls.append(str(request.url))
        return httpx.Response(403, text="error code: 1010")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        @asynccontextmanager
        async def context():
            yield client
        with patch.object(executor, "_http_client_context", context):
            with pytest.raises(httpx.HTTPStatusError):
                await executor._canonical_market_slug_for_condition("0xone")
            with pytest.raises(UpstreamAccessDeferred):
                await executor._canonical_market_slug_for_condition("0xtwo")
    assert len(calls) == 1


async def test_concurrent_clob_denial_stops_queued_conditions(executor):
    calls = []

    async def handler(request):
        calls.append(str(request.url))
        await asyncio.sleep(0.01)
        return httpx.Response(403)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        @asynccontextmanager
        async def context():
            yield client
        with patch.object(executor, "_http_client_context", context):
            results = await asyncio.gather(*(
                executor._canonical_market_slug_for_condition("0x" + str(i))
                for i in range(8)
            ), return_exceptions=True)
    assert all(isinstance(result, Exception) for result in results)
    assert len(calls) == 1


async def test_denial_diagnostic_records_public_request_id_not_headers(executor, caplog):
    async def handler(_request):
        return httpx.Response(403, text="error code: 1010", headers={
            "server": "cloudflare", "cf-ray": "support-request-id",
            "set-cookie": "private-cookie-value",
        })
    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with pytest.raises(httpx.HTTPStatusError):
            await executor._gamma_request_with_retry(client,
                "https://gamma-api.polymarket.com/events", {"slug": "exact-event"})
    assert "support-request-id" in caplog.text
    assert "code=1010" in caplog.text
    assert "private-cookie-value" not in caplog.text
