"""Only an official, later same-document network success may finish a challenge."""
import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from playwright.async_api import async_playwright

from polymtrade_executor import PolymtradeExecutor
from upstream_cooldown import UpstreamAccessDeferred, UpstreamCooldown


def proof(**overrides):
    return {"url": "https://polym.trade/portfolio", "status": 200,
            "started_at": 1001.0, "denied_at": 1000.0, "main_frame": True,
            "transfer_size": 500, "from_service_worker": False, **overrides}


def challenged(tmp_path, headers=None):
    guard = UpstreamCooldown(tmp_path / "cooldowns.json")
    with patch("upstream_cooldown.time.time", return_value=1000):
        guard.record("https://polym.trade/portfolio", 429,
                     {"x-vercel-mitigated": "challenge", **(headers or {})})
    return guard


def test_official_success_finishes_only_client_challenge_pause(tmp_path):
    guard = challenged(tmp_path)
    with patch("upstream_cooldown.time.time", return_value=1002):
        assert guard.complete_challenge("https://polym.trade/portfolio", proof()) is True
        guard.check("https://polym.trade/portfolio")
    assert guard.entries["polym.trade"]["failures"] == 1


@pytest.mark.parametrize("overrides", [
    {"status": 429}, {"url": "https://polym.trade/"},
    {"url": "https://other.example/portfolio"}, {"started_at": 999},
    {"denied_at": 999}, {"main_frame": False}, {"transfer_size": 0},
    {"from_service_worker": True},
])
def test_unrelated_cached_old_or_subresource_success_cannot_clear_guard(tmp_path, overrides):
    guard = challenged(tmp_path)
    before = guard.path.read_bytes()
    with patch("upstream_cooldown.time.time", return_value=1002):
        assert guard.complete_challenge("https://polym.trade/portfolio", proof(**overrides)) is False
    assert guard.path.read_bytes() == before


def test_real_retry_after_is_not_cancelled_by_official_success(tmp_path):
    guard = challenged(tmp_path, {"retry-after": "900"})
    with patch("upstream_cooldown.time.time", return_value=1002):
        assert guard.complete_challenge("https://polym.trade/portfolio", proof()) is False
        with pytest.raises(UpstreamAccessDeferred):guard.check("https://polym.trade/portfolio")


@pytest.mark.parametrize("status", [403, 429])
def test_plain_denial_is_never_treated_as_a_completed_challenge(tmp_path, status):
    guard = UpstreamCooldown(tmp_path / "cooldowns.json")
    with patch("upstream_cooldown.time.time", return_value=1000):guard.record("https://polym.trade/portfolio", status)
    with patch("upstream_cooldown.time.time", return_value=1002):
        assert guard.complete_challenge("https://polym.trade/portfolio", proof()) is False


def test_next_plain_429_does_not_inherit_previous_completed_challenge(tmp_path):
    guard = challenged(tmp_path)
    with patch("upstream_cooldown.time.time", return_value=1002):
        assert guard.complete_challenge("https://polym.trade/portfolio", proof())
    with patch("upstream_cooldown.time.time", return_value=1100):guard.record("https://polym.trade/portfolio", 429)
    assert guard.entries["polym.trade"].get("mitigation") is None
    assert guard.entries["polym.trade"]["retry_at"] > 1100


def test_unknown_provider_deadline_cannot_be_assumed_expired(tmp_path):
    guard = challenged(tmp_path)
    guard.entries["polym.trade"].pop("provider_retry_at")
    with patch("upstream_cooldown.time.time", return_value=1002):
        assert guard.complete_challenge("https://polym.trade/portfolio", proof()) is False


async def test_browser_can_finish_its_own_challenge_without_second_goto(tmp_path, monkeypatch):
    requests = []

    async def serve(reader, writer):
        head = await reader.readuntil(b"\r\n\r\n")
        path = head.split(b" ")[1]
        if path != b"/portfolio":
            status, body, extra = "404 Not Found", b"missing", ""
        else:
            requests.append(path)
            if len(requests) == 1:
                status = "429 Too Many Requests"
                body = b"<html><title>Vercel Security Checkpoint</title><script>setTimeout(()=>location.reload(),100)</script></html>"
                extra = "x-vercel-mitigated: challenge\r\n"
            else:
                status, body, extra = "200 OK", b"<html><div class='cursor-pointer text-foreground'>Positions</div></html>", ""
        writer.write((f"HTTP/1.1 {status}\r\nContent-Type: text/html\r\nCache-Control: no-store\r\n{extra}Content-Length: {len(body)}\r\nConnection: close\r\n\r\n").encode()+body)
        await writer.drain(); writer.close(); await writer.wait_closed()

    server = await asyncio.start_server(serve, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    monkeypatch.setenv("BROWSER_PROFILE_DIR", str(tmp_path))
    executor = PolymtradeExecutor()
    executor.base_url = f"http://127.0.0.1:{port}"
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page(); executor.page = page
            original = page.goto
            page.goto = AsyncMock(side_effect=original)
            response = await executor._navigate_once(executor.base_url+"/portfolio", wait_until="domcontentloaded", timeout_ms=10000)
            assert response.status == 200
            page.goto.assert_awaited_once()
            assert len(requests) == 2  # The second is the fixture browser's normal reload.
            executor._upstream_cooldown.check(executor.base_url+"/portfolio")
        finally:await browser.close()
    server.close(); await server.wait_closed()
