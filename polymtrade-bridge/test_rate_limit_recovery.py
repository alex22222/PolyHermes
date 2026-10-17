"""Rate-limit recovery must reduce requests, never shorten platform protection."""
import asyncio
from email.utils import formatdate
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from polymtrade_executor import PolymtradeExecutor
from upstream_cooldown import UpstreamAccessDeferred, UpstreamCooldown


def test_repeated_429_backs_off_and_survives_restart(tmp_path):
    path = tmp_path / "cooldowns.json"
    guard = UpstreamCooldown(path)
    with patch("upstream_cooldown.time.time", return_value=1000):
        guard.record("https://polym.trade/portfolio", 429)
    with patch("upstream_cooldown.time.time", return_value=1301):
        restarted = UpstreamCooldown(path)
        restarted.record("https://polym.trade/event/example", 429)
    assert restarted.entries["polym.trade"]["retry_at"] == 1901


def test_retry_after_http_date_is_respected(tmp_path):
    guard = UpstreamCooldown(tmp_path / "cooldowns.json")
    with patch("upstream_cooldown.time.time", return_value=1000):
        guard.record("https://polym.trade/portfolio", 429,
                     {"Retry-After": formatdate(2200, usegmt=True)})
    assert guard.entries["polym.trade"]["retry_at"] == 2200


def test_late_429_cannot_shorten_or_replace_active_403(tmp_path):
    guard = UpstreamCooldown(tmp_path / "cooldowns.json")
    with patch("upstream_cooldown.time.time", return_value=1000):
        guard.record("https://polym.trade/portfolio", 403)
        guard.record("https://polym.trade/event/example", 429)
    assert guard.entries["polym.trade"]["retry_at"] >= 2800
    assert guard.entries["polym.trade"]["status"] == 403


def test_inflight_denials_do_not_extend_active_retry_window(tmp_path):
    guard = UpstreamCooldown(tmp_path / "cooldowns.json")
    with patch("upstream_cooldown.time.time", return_value=1000):
        guard.record("https://polym.trade/portfolio", 429)
    with patch("upstream_cooldown.time.time", return_value=1001):
        guard.record("https://polym.trade/event/example", 429)
    assert guard.entries["polym.trade"]["retry_at"] == 1300
    assert guard.entries["polym.trade"]["failures"] == 1


def test_late_retry_after_can_only_extend_existing_protection(tmp_path):
    guard = UpstreamCooldown(tmp_path / "cooldowns.json")
    with patch("upstream_cooldown.time.time", return_value=1000):
        guard.record("https://polym.trade/portfolio", 429, {"retry-after": "1200"})
        guard.record("https://polym.trade/event/a", 429, {"retry-after": "300"})
        assert guard.entries["polym.trade"]["retry_at"] == 2200
        guard.record("https://polym.trade/event/b", 429, {"retry-after": "2400"})
    assert guard.entries["polym.trade"]["retry_at"] == 3400
    assert guard.entries["polym.trade"]["failures"] == 1


@pytest.mark.parametrize("value", ["bad date", "NaN", "inf", "-100"])
def test_invalid_retry_after_cannot_relax_default_delay(tmp_path, value):
    guard = UpstreamCooldown(tmp_path / "cooldowns.json")
    with patch("upstream_cooldown.time.time", return_value=1000):
        guard.record("https://polym.trade/portfolio", 429, {"retry-after": value})
    assert guard.entries["polym.trade"]["retry_at"] == 1300


@pytest.fixture
def executor(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_PROFILE_DIR", str(tmp_path))
    return PolymtradeExecutor()


async def test_browser_navigation_starts_are_serially_paced(executor):
    now = [100.0]
    waits = []

    async def sleep(delay):
        waits.append(delay)
        now[0] += delay

    with patch("polymtrade_executor.time.monotonic", side_effect=lambda: now[0]), \
            patch("polymtrade_executor.asyncio.sleep", side_effect=sleep):
        await asyncio.gather(*(
            executor._pace_navigation(f"https://polym.trade/{path}")
            for path in ("portfolio", "event/example", "portfolio")
        ))
    assert waits == [10.0, 10.0]


async def test_denial_arriving_during_navigation_wait_blocks_request(executor):
    now = [100.0]
    async def denied_during_wait(_delay):
        executor._upstream_cooldown.record("https://polym.trade/portfolio", 429)
        now[0] += 10

    with patch("polymtrade_executor.time.monotonic", side_effect=lambda: now[0]):
        await executor._pace_navigation("https://polym.trade/portfolio")
        with patch("polymtrade_executor.asyncio.sleep", side_effect=denied_during_wait):
            with pytest.raises(UpstreamAccessDeferred):
                await executor._pace_navigation("https://polym.trade/event/example")


async def test_every_real_navigation_uses_shared_pacing(executor):
    executor.page = SimpleNamespace(goto=AsyncMock(return_value=SimpleNamespace(status=200, headers={})))
    executor._pace_navigation = AsyncMock()
    executor._recover_stale_app_shell = AsyncMock(return_value=False)
    await executor._goto_with_retry("https://polym.trade/portfolio")
    executor._pace_navigation.assert_awaited_once_with("https://polym.trade/portfolio")
    executor.page.goto.assert_awaited_once()


async def test_portfolio_cooldown_honors_full_upstream_retry_after(executor):
    executor._upstream_cooldown.entries["polym.trade"] = {
        "status": 429, "retry_at": 2000, "failures": 1,
    }
    executor._cache_portfolio_snapshot({"positions": [{"quantity": 5}], "portfolio_complete": True})
    executor._ensure_portfolio_page = AsyncMock()
    with patch("upstream_cooldown.time.time", return_value=1000):
        result = await executor.fetch_portfolio_positions()
    assert result["portfolio_complete"] is False
    assert result["upstream_http_status"] == 429
    assert executor._portfolio_snapshot_cache is None
    executor._ensure_portfolio_page.assert_not_awaited()


async def test_portfolio_local_deferrals_do_not_add_extra_cooldown(executor):
    executor._upstream_cooldown.entries["polym.trade"] = {
        "status": 429, "retry_at": 2000, "failures": 1,
    }
    with patch("upstream_cooldown.time.time", return_value=1999), \
            patch("polymtrade_executor.time.monotonic", return_value=100):
        await executor.fetch_portfolio_positions(force_refresh=True)
    fresh = {"positions": [{"quantity": 2}], "portfolio_complete": True}
    executor._ensure_portfolio_page = AsyncMock(return_value=object())
    executor._fetch_portfolio_positions_on_active_page = AsyncMock(return_value=fresh)
    executor._schedule_portfolio_page_idle_close = lambda: None
    with patch("upstream_cooldown.time.time", return_value=2001), \
            patch("polymtrade_executor.time.monotonic", return_value=102):
        assert await executor.fetch_portfolio_positions(force_refresh=True) == fresh
    executor._fetch_portfolio_positions_on_active_page.assert_awaited_once()


async def test_fallback_429_is_not_hidden_as_generic_navigation_failure(executor):
    executor.page = SimpleNamespace(goto=AsyncMock(side_effect=[
        RuntimeError("net::ERR_CONNECTION_RESET"),
        SimpleNamespace(status=429, headers={"retry-after": "900"}),
    ]))
    executor._pace_navigation = AsyncMock()
    executor._navigation_target_reached = lambda _url: False
    with pytest.raises(UpstreamAccessDeferred) as denied:
        await executor._goto_with_retry("https://polym.trade/portfolio", max_retries=1)
    assert denied.value.status == 429
    assert executor.page.goto.await_count == 2


def test_429_diagnostic_excludes_secrets_and_url_query(executor, caplog):
    with pytest.raises(UpstreamAccessDeferred):
        executor._check_navigation_response("https://polym.trade/portfolio?private=secret-query",
            SimpleNamespace(status=429, headers={
                "server": "Vercel", "retry-after": "900", "x-vercel-id": "support-id",
                "set-cookie": "secret-cookie", "authorization": "secret-token",
            }))
    assert "support-id" in caplog.text
    assert "path=/portfolio" in caplog.text
    assert all(secret not in caplog.text for secret in ("secret-query", "secret-cookie", "secret-token"))
