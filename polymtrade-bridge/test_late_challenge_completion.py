"""A completed official document must not stay latched after its listener ends."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from playwright.async_api import async_playwright

from polymtrade_executor import PolymtradeExecutor
from upstream_cooldown import UpstreamAccessDeferred


def completed_document(**overrides):
    return {"url": "https://polym.trade/portfolio", "status": 200,
            "started_at": 1002.0, "transfer_size": 17912,
            "main_frame": True, "from_service_worker": False,
            "checkpoint_visible": False, **overrides}


def executor_with_challenge(tmp_path, monkeypatch, proof=None, headers=None):
    monkeypatch.setenv("BROWSER_PROFILE_DIR", str(tmp_path))
    executor = PolymtradeExecutor()
    executor._logged_in = True
    with patch("upstream_cooldown.time.time", return_value=1000):
        executor._upstream_cooldown.record("https://polym.trade/portfolio", 429,
            {"x-vercel-mitigated": "challenge", **(headers or {})})
    executor.portfolio_page = SimpleNamespace(is_closed=lambda: False,
        evaluate=AsyncMock(return_value=proof or completed_document()), goto=AsyncMock())
    executor.page = SimpleNamespace(goto=AsyncMock())
    executor._ensure_portfolio_page = AsyncMock(return_value=executor.portfolio_page)
    executor._schedule_portfolio_page_idle_close = lambda: None
    executor._fetch_portfolio_positions_on_active_page = AsyncMock(return_value={
        "positions": [{"marketTitle": "Fresh", "quantity": 2}], "portfolio_complete": True,
    })
    return executor


@pytest.mark.parametrize("now", [1030, 8200])
async def test_late_official_completion_requires_a_new_complete_holdings_read(tmp_path, monkeypatch, now):
    executor = executor_with_challenge(tmp_path, monkeypatch)
    executor._portfolio_access_error = {"error": "old denial", "portfolio_complete": False}
    executor._portfolio_access_retry_at = float("inf")
    executor._portfolio_snapshot_cache = {"positions": [{"marketTitle": "Old"}], "portfolio_complete": True}
    with patch("time.time", return_value=now):
        result = await executor.fetch_portfolio_positions()
    assert result["portfolio_complete"] is True
    assert result["positions"][0]["marketTitle"] == "Fresh"
    executor._fetch_portfolio_positions_on_active_page.assert_awaited_once()
    executor.portfolio_page.goto.assert_not_awaited()
    executor.page.goto.assert_not_awaited()
    assert executor._logged_in is True
    assert executor._upstream_cooldown.entries["polym.trade"]["failures"] == 1


@pytest.mark.parametrize("overrides", [
    {"status": 429}, {"url": "https://polym.trade/"}, {"started_at": 999},
    {"main_frame": False}, {"from_service_worker": True}, {"transfer_size": 0},
    {"checkpoint_visible": True},
])
async def test_incomplete_or_unrelated_document_keeps_protection(tmp_path, monkeypatch, overrides):
    executor = executor_with_challenge(tmp_path, monkeypatch, completed_document(**overrides))
    with patch("time.time", return_value=1030):
        result = await executor.fetch_portfolio_positions(force_refresh=True)
    assert result["portfolio_complete"] is False
    executor._fetch_portfolio_positions_on_active_page.assert_not_awaited()
    assert executor._upstream_cooldown.entries["polym.trade"]["retry_at"] == 22600


async def test_provider_retry_after_is_never_shortened(tmp_path, monkeypatch):
    executor = executor_with_challenge(tmp_path, monkeypatch, headers={"retry-after": "9000"})
    with patch("time.time", return_value=8200):
        result = await executor.fetch_portfolio_positions(force_refresh=True)
    assert result["portfolio_complete"] is False
    executor._fetch_portfolio_positions_on_active_page.assert_not_awaited()
    assert executor._upstream_cooldown.entries["polym.trade"]["provider_retry_at"] == 10000


@pytest.mark.parametrize("status,headers", [(403, {}), (429, {})])
async def test_plain_denials_do_not_inspect_or_accept_old_documents(tmp_path, monkeypatch, status, headers):
    executor = executor_with_challenge(tmp_path, monkeypatch)
    executor._upstream_cooldown.entries.clear()
    with patch("time.time", return_value=1000):
        executor._upstream_cooldown.record("https://polym.trade/portfolio", status, headers)
    with patch("time.time", return_value=1030):
        result = await executor.fetch_portfolio_positions(force_refresh=True)
    assert result["portfolio_complete"] is False
    executor.portfolio_page.evaluate.assert_not_awaited()
    executor._fetch_portfolio_positions_on_active_page.assert_not_awaited()


async def test_unavailable_document_does_not_clear_or_extend_pause(tmp_path, monkeypatch):
    executor = executor_with_challenge(tmp_path, monkeypatch)
    executor.portfolio_page.evaluate.side_effect = RuntimeError("page is navigating")
    with patch("time.time", return_value=1030):
        result = await executor.fetch_portfolio_positions(force_refresh=True)
    assert result["portfolio_complete"] is False
    assert executor._upstream_cooldown.entries["polym.trade"]["retry_at"] == 22600


async def test_completed_document_does_not_make_an_incomplete_portfolio_ready(tmp_path, monkeypatch):
    executor = executor_with_challenge(tmp_path, monkeypatch)
    executor._fetch_portfolio_positions_on_active_page.return_value = {
        "error": "Fresh holdings API unavailable", "portfolio_complete": False, "positions": [],
    }
    with patch("time.time", return_value=1030):
        result = await executor.fetch_portfolio_positions(force_refresh=True)
    assert result["portfolio_complete"] is False
    assert executor.trading_readiness()["trading_ready"] is False


async def test_real_browser_completion_is_read_without_a_second_navigation(tmp_path, monkeypatch):
    requests = []

    async def serve(reader, writer):
        await reader.readuntil(b"\r\n\r\n")
        requests.append(1)
        body = b"<html><title>Portfolio</title><div>Positions</div></html>"
        writer.write(("HTTP/1.1 200 OK\r\nContent-Type: text/html\r\nCache-Control: no-store\r\n"
                      f"Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode() + body)
        await writer.drain(); writer.close(); await writer.wait_closed()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/portfolio"
    monkeypatch.setenv("BROWSER_PROFILE_DIR", str(tmp_path))
    executor = PolymtradeExecutor()
    executor.base_url = url.removesuffix("/portfolio")
    executor._upstream_cooldown.record(url, 429, {"x-vercel-mitigated": "challenge"})
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.goto(url)
            executor.portfolio_page = page
            page.goto = AsyncMock(wraps=page.goto)
            with pytest.raises(UpstreamAccessDeferred):
                executor._upstream_cooldown.check(url)
            await executor._complete_retained_portfolio_challenge()
            executor._upstream_cooldown.check(url)
            page.goto.assert_not_awaited()
            assert len(requests) == 1
        finally:
            await browser.close()
            server.close(); await server.wait_closed()
