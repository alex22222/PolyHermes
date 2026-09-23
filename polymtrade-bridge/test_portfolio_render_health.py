import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

from polymtrade_executor import PolymtradeExecutor


def _live_executor() -> PolymtradeExecutor:
    executor = PolymtradeExecutor()
    executor._ready = True
    executor.page = SimpleNamespace(is_closed=lambda: False)
    executor.context = SimpleNamespace(pages=[executor.page])
    return executor


def test_repeated_portfolio_shell_render_does_not_latch_executor_unhealthy():
    executor = _live_executor()

    executor._record_portfolio_render_result(False)
    assert executor.is_ready() is True
    executor._record_portfolio_render_result(False)
    assert executor.is_ready() is True
    assert executor.browser_diagnostics()["portfolio_render_failures"] == 2


def test_successful_portfolio_render_resets_failure_count():
    executor = _live_executor()

    executor._record_portfolio_render_result(False)
    executor._record_portfolio_render_result(True)

    assert executor.is_ready() is True


def test_portfolio_shell_discards_page_and_retries_with_fresh_page():
    executor = _live_executor()
    stale_page = SimpleNamespace(is_closed=lambda: False, close=AsyncMock())
    fresh_page = SimpleNamespace(is_closed=lambda: False, close=AsyncMock())
    executor.portfolio_page = stale_page
    executor._ensure_portfolio_page = AsyncMock(side_effect=[stale_page, fresh_page])
    executor._fetch_portfolio_positions_on_active_page = AsyncMock(
        side_effect=[
            {"positions": [], "portfolio_complete": False},
            {"positions": [{"marketTitle": "Recovered"}], "portfolio_complete": True},
        ]
    )
    executor._schedule_portfolio_page_idle_close = lambda: None

    result = asyncio.run(executor.fetch_portfolio_positions())

    assert result["portfolio_complete"] is True
    assert executor._ensure_portfolio_page.await_count == 2
    stale_page.close.assert_awaited_once()


def test_repeated_incomplete_portfolio_refreshes_live_login_state():
    executor = _live_executor()
    stale_page = SimpleNamespace(is_closed=lambda: False, close=AsyncMock())
    fresh_page = SimpleNamespace(is_closed=lambda: False, close=AsyncMock())
    executor.portfolio_page = stale_page
    executor._ensure_portfolio_page = AsyncMock(side_effect=[stale_page, fresh_page])
    executor._fetch_portfolio_positions_on_active_page = AsyncMock(
        side_effect=[
            {"positions": [], "portfolio_complete": False},
            {"positions": [], "portfolio_complete": False},
        ]
    )
    executor.refresh_login_state = AsyncMock(return_value=False)
    executor._schedule_portfolio_page_idle_close = lambda: None

    result = asyncio.run(executor.fetch_portfolio_positions())

    assert result["portfolio_complete"] is False
    executor.refresh_login_state.assert_awaited_once()


def test_complete_portfolio_snapshot_is_cached_without_reloading_page():
    executor = _live_executor()
    page = SimpleNamespace(is_closed=lambda: False)
    executor._portfolio_snapshot_cache_ttl_seconds = 60
    executor._ensure_portfolio_page = AsyncMock(return_value=page)
    executor._fetch_portfolio_positions_on_active_page = AsyncMock(
        return_value={"positions": [{"marketTitle": "Cached"}], "portfolio_complete": True}
    )
    executor._schedule_portfolio_page_idle_close = lambda: None

    first = asyncio.run(executor.fetch_portfolio_positions())
    first["positions"][0]["marketTitle"] = "Mutated by caller"
    second = asyncio.run(executor.fetch_portfolio_positions())

    assert second["positions"][0]["marketTitle"] == "Cached"
    assert executor._fetch_portfolio_positions_on_active_page.await_count == 1


def test_cached_wallet_address_does_not_navigate_portfolio_page():
    executor = PolymtradeExecutor()
    executor._cached_wallet_address = "0xabc"
    executor._cached_wallet_at = int(__import__("time").time() * 1000)

    assert asyncio.run(executor.get_wallet_address()) == "0xabc"
