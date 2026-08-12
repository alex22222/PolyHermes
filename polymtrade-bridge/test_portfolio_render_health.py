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


def test_repeated_portfolio_shell_render_marks_executor_unhealthy():
    executor = _live_executor()

    executor._record_portfolio_render_result(False)
    assert executor.is_ready() is True
    executor._record_portfolio_render_result(False)
    assert executor.is_ready() is False


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
