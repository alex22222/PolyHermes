"""Upstream access failures must remain unknown holdings, with bounded reads."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

import main
from polymtrade_executor import PolymtradeExecutor


def blocked_executor(status=403):
    executor = PolymtradeExecutor()
    executor._logged_in = True
    page = SimpleNamespace(
        goto=AsyncMock(return_value=SimpleNamespace(status=status)),
        inner_text=AsyncMock(return_value="This request was blocked\n403 FORBIDDEN"),
        evaluate=AsyncMock(return_value={"positions": [], "hasErrorBanner": False}),
        close=AsyncMock(),
        is_closed=lambda: False,
    )
    executor.page = page
    executor._ensure_portfolio_page = AsyncMock(return_value=page)
    executor._schedule_portfolio_page_idle_close = lambda: None
    executor._wait_for_portfolio_rows = AsyncMock(return_value=False)
    executor._scroll_portfolio_until_stable = AsyncMock()
    executor.get_wallet_address = AsyncMock(return_value=None)
    executor.refresh_login_state = AsyncMock(return_value=True)
    return executor, page


@pytest.mark.parametrize("status", [401, 403, 429])
async def test_access_denial_fails_before_scraping_or_recreating_page(status):
    executor, page = blocked_executor(status)

    result = await executor.fetch_portfolio_positions(force_refresh=True)

    assert result["portfolio_complete"] is False
    assert result["empty_state_confirmed"] is False
    assert result["upstream_http_status"] == status
    assert f"HTTP {status}" in result["error"]
    executor._wait_for_portfolio_rows.assert_not_awaited()
    executor._scroll_portfolio_until_stable.assert_not_awaited()
    executor._ensure_portfolio_page.assert_awaited_once()
    page.close.assert_not_awaited()
    assert executor._logged_in is True


async def test_forced_reads_cannot_bypass_access_failure_cooldown_or_use_stale_holdings():
    executor, page = blocked_executor()
    executor._cache_portfolio_snapshot({"positions": [{"quantity": 8}], "portfolio_complete": True})
    with patch("polymtrade_executor.time.monotonic", return_value=100):
        first = await executor.fetch_portfolio_positions(force_refresh=True)
    with patch("polymtrade_executor.time.monotonic", return_value=101):
        forced = await executor.fetch_portfolio_positions(force_refresh=True)
        normal = await executor.fetch_portfolio_positions()

    assert first["portfolio_complete"] is False
    assert forced["portfolio_complete"] is False
    assert normal["portfolio_complete"] is False
    assert normal["positions"] == []
    assert executor._portfolio_snapshot_cache is None
    page.goto.assert_awaited_once()


async def test_access_failure_retries_only_after_cooldown_and_can_recover():
    executor, page = blocked_executor()
    with patch("polymtrade_executor.time.monotonic", return_value=100):
        await executor.fetch_portfolio_positions(force_refresh=True)
    executor._fetch_portfolio_positions_on_active_page = AsyncMock(return_value={
        "positions": [{"marketTitle": "Recovered", "quantity": 2}], "portfolio_complete": True,
    })
    with patch("polymtrade_executor.time.monotonic", return_value=401):
        result = await executor.fetch_portfolio_positions(force_refresh=True)

    assert result["portfolio_complete"] is True
    executor._fetch_portfolio_positions_on_active_page.assert_awaited_once()
    page.close.assert_not_awaited()


async def test_access_denial_cannot_be_interpreted_as_zero_live_quantity():
    executor, _ = blocked_executor()
    executor.is_ready = lambda: True
    with patch.object(main, "executor", executor), patch.object(main, "ensure_login_state", AsyncMock(return_value=True)):
        with pytest.raises(RuntimeError, match="HTTP 403"):
            await main._get_live_position_quantity(market_id="market", market_title="Market", outcome="Yes")
