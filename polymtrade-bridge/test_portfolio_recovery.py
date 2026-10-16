"""Slow hydration and recent rate limits must not cause reload/retry storms."""
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from playwright.async_api import async_playwright

from polymtrade_executor import PolymtradeExecutor
from upstream_cooldown import UpstreamCooldown


def test_successful_response_does_not_erase_recent_429_history(tmp_path):
    path = tmp_path / "cooldowns.json"
    guard = UpstreamCooldown(path)
    with patch("upstream_cooldown.time.time", return_value=1000):
        guard.record("https://polym.trade/portfolio", 429)
    with patch("upstream_cooldown.time.time", return_value=1301):
        guard.record("https://polym.trade/portfolio", 200)
        guard.check("https://polym.trade/portfolio")
    with patch("upstream_cooldown.time.time", return_value=2000):
        restarted = UpstreamCooldown(path)
        restarted.record("https://polym.trade/portfolio", 429)
    assert restarted.entries["polym.trade"]["failures"] == 2
    assert restarted.entries["polym.trade"]["retry_at"] == 2600


def test_pacing_recovers_after_hour_but_backoff_memory_last_six_hours(tmp_path):
    guard = UpstreamCooldown(tmp_path / "cooldowns.json")
    url = "https://polym.trade/portfolio"
    with patch("upstream_cooldown.time.time", return_value=1000):
        guard.record(url, 429)
    with patch("upstream_cooldown.time.time", return_value=4599):
        assert guard.navigation_interval(url) == 30
        guard.record(url, 200)
        assert "polym.trade" in guard.entries
    with patch("upstream_cooldown.time.time", return_value=4601):
        assert guard.navigation_interval(url) == 10
        guard.record(url, 200)
        assert "polym.trade" in guard.entries
    with patch("upstream_cooldown.time.time", return_value=22601):
        guard.record(url, 200)
        assert "polym.trade" not in guard.entries


def test_429_recurring_after_hour_still_uses_longer_backoff(tmp_path):
    guard = UpstreamCooldown(tmp_path / "cooldowns.json")
    url = "https://polym.trade/portfolio"
    with patch("upstream_cooldown.time.time", return_value=1000):
        guard.record(url, 429)
    with patch("upstream_cooldown.time.time", return_value=4700):
        guard.record(url, 200)
        guard.record(url, 429)
    assert guard.entries["polym.trade"]["failures"] == 2
    assert guard.entries["polym.trade"]["retry_at"] == 5300


def test_long_retry_after_still_blocks_beyond_recovery_hour(tmp_path):
    guard = UpstreamCooldown(tmp_path / "cooldowns.json")
    url = "https://polym.trade/portfolio"
    with patch("upstream_cooldown.time.time", return_value=1000):
        guard.record(url, 429, {"retry-after": "7200"})
    with patch("upstream_cooldown.time.time", return_value=5000):
        guard.record(url, 200)
        with pytest.raises(RuntimeError, match="cooldown"):
            guard.check(url)
    assert guard.entries["polym.trade"]["retry_at"] == 8200


async def test_navigation_is_slower_during_recent_429_recovery(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_PROFILE_DIR", str(tmp_path))
    executor = PolymtradeExecutor()
    with patch("upstream_cooldown.time.time", return_value=1000):
        executor._upstream_cooldown.record("https://polym.trade/portfolio", 429)
    now = [100.0]
    waits = []

    async def sleep(delay):
        waits.append(delay)
        now[0] += delay

    with patch("upstream_cooldown.time.time", return_value=1400), \
            patch("polymtrade_executor.time.monotonic", side_effect=lambda: now[0]), \
            patch("polymtrade_executor.asyncio.sleep", side_effect=sleep):
        executor._upstream_cooldown.record("https://polym.trade/portfolio", 200)
        await executor._pace_navigation("https://polym.trade/portfolio")
        await executor._pace_navigation("https://polym.trade/event/example")
    assert waits == [30.0]


async def test_slow_positions_tab_uses_same_navigation_and_remains_bounded():
    tab = SimpleNamespace(click=AsyncMock(), get_attribute=AsyncMock(return_value="cursor-pointer"))

    async def wait(_selector, *, timeout, **_kwargs):
        if timeout < 25000:
            raise TimeoutError("Positions hydration needs 25 seconds")
        assert timeout <= 30000
        return tab

    executor = PolymtradeExecutor()
    executor.page = SimpleNamespace(wait_for_selector=AsyncMock(side_effect=wait), wait_for_function=AsyncMock())
    await executor._select_portfolio_positions()
    tab.click.assert_awaited_once()


async def test_selected_positions_tab_is_not_clicked_again():
    tab = SimpleNamespace(click=AsyncMock(), get_attribute=AsyncMock(return_value="cursor-pointer text-foreground"))
    executor = PolymtradeExecutor()
    executor.page = SimpleNamespace(wait_for_selector=AsyncMock(return_value=tab), wait_for_function=AsyncMock())
    await executor._select_portfolio_positions()
    tab.click.assert_not_awaited()
    executor.page.wait_for_function.assert_awaited_once()


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf"), -1.0])
async def test_nonfinite_or_negative_balance_is_unknown_and_not_logged(value, caplog):
    executor = PolymtradeExecutor()
    executor.page = SimpleNamespace(evaluate=AsyncMock(return_value={"text": "PRIVATE_DOM_SENTINEL", "value": value}))
    assert await executor._get_usdc_balance() is None
    assert "PRIVATE_DOM_SENTINEL" not in caplog.text


@pytest.mark.parametrize("html,expected", [
    ('<div style="display:none">40 pUSD</div>', None),
    ('<div><script>const balance = ",,, pUSD";</script></div>', None),
    ('<div>Balance ,,, pUSD</div>', None),
    ('<div>40.25 pUSD</div>', 40.25),
    ('<div>Balance $0</div>', 0.0),
])
async def test_real_balance_dom_ignores_hidden_and_script_text(html, expected):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=True)
        try:
            page = await browser.new_page()
            await page.set_content(html)
            executor = PolymtradeExecutor()
            executor.page = page
            assert await executor._get_usdc_balance() == expected
        finally:
            await browser.close()
