"""Execution confirmation must not use cached or unavailable holdings."""

from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import main
from polymtrade_executor import PolymtradeExecutor


async def test_forced_portfolio_read_bypasses_pre_trade_snapshot():
    executor = PolymtradeExecutor()
    executor._cache_portfolio_snapshot({"positions": [], "portfolio_complete": True})
    fresh = {"positions": [{"quantity": 2}], "portfolio_complete": True}
    executor._ensure_portfolio_page = AsyncMock(return_value=object())
    executor._fetch_portfolio_positions_on_active_page = AsyncMock(return_value=fresh)
    executor._schedule_portfolio_page_idle_close = lambda: None

    assert await executor.fetch_portfolio_positions(force_refresh=True) == fresh
    assert await executor.fetch_portfolio_positions() == fresh
    executor._fetch_portfolio_positions_on_active_page.assert_awaited_once()


@pytest.mark.parametrize("portfolio", [
    {"error": "render failed"},
    {"positions": [], "portfolio_complete": False},
    {"positions": []},
])
async def test_unavailable_portfolio_cannot_confirm_sell(portfolio):
    executor = SimpleNamespace(is_ready=lambda: True,
                               fetch_portfolio_positions=AsyncMock(return_value=portfolio))
    with patch.object(main, "executor", executor), patch.object(main, "ensure_login_state", AsyncMock(return_value=True)):
        with pytest.raises(RuntimeError, match="portfolio"):
            await main._wait_for_live_position_decrease(
                market_id="market", market_title="Market", outcome="Yes",
                before_quantity=Decimal("2"), poll_attempts=1,
            )


async def test_live_confirmation_requests_fresh_complete_snapshot():
    executor = SimpleNamespace(is_ready=lambda: True, fetch_portfolio_positions=AsyncMock(return_value={
        "positions": [{"marketId": "market", "side": "Yes", "quantity": 2}],
        "portfolio_complete": True,
    }))
    with patch.object(main, "executor", executor), patch.object(main, "ensure_login_state", AsyncMock(return_value=True)):
        assert await main._wait_for_live_position_increase(
            market_id="market", market_title="Market", outcome="Yes",
            before_quantity=Decimal("0"), poll_attempts=1,
        ) == Decimal("2")
    executor.fetch_portfolio_positions.assert_awaited_once_with(force_refresh=True)


async def test_logged_out_is_unknown_not_zero():
    with patch.object(main, "executor", None):
        with pytest.raises(RuntimeError, match="portfolio"):
            await main._get_live_position_quantity(market_id="market", market_title="Market", outcome="Yes")


async def test_unknown_buy_baseline_never_confirms_existing_position():
    record = AsyncMock()
    wait = AsyncMock(return_value=Decimal("5"))
    with patch.object(main, "recorder", MagicMock()), patch.object(main, "_recorder_call", record), patch.object(main, "_wait_for_live_position_increase", wait):
        await main._verify_submitted_buy(record_id=1, market_id="market", market_title="Market", outcome="Yes", before_quantity=None)
    wait.assert_not_awaited()
    assert record.await_args.args[2] == main.STATUS_SUBMITTED_UNVERIFIED


async def test_partial_parse_is_not_a_complete_portfolio():
    executor = PolymtradeExecutor()
    executor.page = SimpleNamespace(evaluate=AsyncMock(return_value=[
        {"marketTitle": "Valid", "side": "Yes", "quantity": 2},
        {"marketTitle": "Not parsed", "side": "Yes", "quantity": None},
    ]))
    executor._goto_with_retry = AsyncMock()
    executor._wait_for_portfolio_rows = AsyncMock(return_value=True)
    executor._scroll_portfolio_until_stable = AsyncMock()
    executor._enrich_position = AsyncMock(return_value={})
    executor.get_wallet_address = AsyncMock(return_value=None)
    result = await executor._fetch_portfolio_positions_on_active_page()
    assert len(result["positions"]) == 1
    assert result["portfolio_complete"] is False
