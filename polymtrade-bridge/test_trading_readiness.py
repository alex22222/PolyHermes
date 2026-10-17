"""A live browser is not proof that fresh protected trading is available."""
import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

import main
from polymtrade_executor import PolymtradeExecutor
from upstream_cooldown import UpstreamAccessDeferred, UpstreamCooldown


@pytest.fixture
def executor(tmp_path, monkeypatch):
    monkeypatch.setenv("BROWSER_PROFILE_DIR", str(tmp_path))
    value = PolymtradeExecutor()
    value._ready = value._logged_in = True
    value.page = SimpleNamespace(is_closed=lambda: False, goto=AsyncMock())
    value.context = SimpleNamespace(pages=[value.page])
    value._last_portfolio_synced_at = 1000000
    return value


def test_fresh_complete_runtime_is_trading_ready(executor):
    with patch("polymtrade_executor.time.time", return_value=1100):
        status = executor.trading_readiness()
    assert status["trading_ready"] is True
    assert status["trading_block_reasons"] == []


@pytest.mark.parametrize("synced_at,reason", [(0, "portfolio_missing"), (600000, "portfolio_stale")])
def test_missing_or_stale_holdings_are_not_healthy(executor, synced_at, reason):
    executor._last_portfolio_synced_at = synced_at
    with patch("polymtrade_executor.time.time", return_value=1100):
        status = executor.trading_readiness()
    assert status["trading_ready"] is False
    assert reason in status["trading_block_reasons"]
    assert executor.is_ready() is True
    assert executor.is_logged_in() is True
    executor.page.goto.assert_not_awaited()


def test_active_denial_blocks_even_with_fresh_holdings(executor):
    executor._upstream_cooldown.entries["polym.trade"] = {"status": 429, "retry_at": 1400, "failures": 8}
    with patch("polymtrade_executor.time.time", return_value=1100):
        status = executor.trading_readiness()
    assert status["trading_ready"] is False
    assert "upstream_http_429" in status["trading_block_reasons"]
    assert status["upstream_restrictions"][0]["retry_at"] == 1400
    assert executor._logged_in is True


def test_expired_cooldown_cannot_make_stale_holdings_ready(executor):
    executor._last_portfolio_synced_at = 500000
    executor._upstream_cooldown.entries["polym.trade"] = {"status": 429, "retry_at": 1000, "failures": 8}
    with patch("polymtrade_executor.time.time", return_value=1100):
        status = executor.trading_readiness()
    assert status["upstream_restrictions"] == []
    assert status["trading_ready"] is False


def test_trade_warning_does_not_create_process_or_trading_outage(executor):
    executor.last_error = "Insufficient balance for a previous BUY"
    with patch("polymtrade_executor.time.time", return_value=1100):
        assert executor.trading_readiness()["trading_ready"] is True


def test_health_is_degraded_but_liveness_stays_up(executor, monkeypatch):
    executor._last_portfolio_synced_at = 0
    monkeypatch.setattr(main, "executor", executor)
    with pytest.raises(HTTPException) as failure:
        asyncio.run(main.health())
    assert failure.value.status_code == 503
    assert failure.value.detail["trading_ready"] is False
    assert asyncio.run(main.liveness())["executor_ready"] is True
    assert main.bridge_runtime_status()["ready"] is False
    assert main.bridge_runtime_status()["executor_ready"] is True
    assert "portfolio_missing" in main.bridge_runtime_status()["last_error"]


def test_persistent_429_backoff_grows_past_hour_and_survives_restart(tmp_path):
    path = tmp_path / "cooldowns.json"
    url = "https://polym.trade/portfolio"
    guard = UpstreamCooldown(path)
    now = 1000
    delays = []
    for _ in range(10):
        with patch("upstream_cooldown.time.time", return_value=now):
            guard.record(url, 429)
            retry_at = guard.entries["polym.trade"]["retry_at"]
            delays.append(retry_at - now)
        now = retry_at + 1
        guard = UpstreamCooldown(path)
    assert delays == [300, 600, 1200, 2400, 4800, 9600, 19200, 21600, 21600, 21600]


def test_challenge_is_not_misclassified_as_short_quota_retry(tmp_path):
    path = tmp_path / "cooldowns.json"
    guard = UpstreamCooldown(path)
    with patch("upstream_cooldown.time.time", return_value=1000):
        guard.record("https://polym.trade/portfolio", 429, {
            "x-vercel-mitigated": "challenge", "x-vercel-challenge-token": "PRIVATE_TOKEN",
        })
    saved = path.read_text()
    assert "PRIVATE_TOKEN" not in saved
    restarted = UpstreamCooldown(path)
    assert restarted.entries["polym.trade"]["mitigation"] == "challenge"
    with patch("upstream_cooldown.time.time", return_value=1301):
        with pytest.raises(UpstreamAccessDeferred):
            restarted.check("https://polym.trade/portfolio")


def test_denial_diagnostic_retains_classification_but_no_credentials(executor, caplog):
    response = SimpleNamespace(status=429, headers={
        "x-vercel-mitigated": "challenge", "content-type": "text/html",
        "x-vercel-id": "support-request-id", "set-cookie": "PRIVATE_COOKIE",
        "x-vercel-challenge-token": "PRIVATE_TOKEN", "authorization": "PRIVATE_AUTH",
    }, from_service_worker=False)
    with pytest.raises(UpstreamAccessDeferred):
        executor._check_navigation_response("https://polym.trade/portfolio?private=PRIVATE_QUERY", response)
    assert "mitigation=challenge" in caplog.text
    assert all(value not in caplog.text for value in ("PRIVATE_COOKIE", "PRIVATE_TOKEN", "PRIVATE_AUTH", "PRIVATE_QUERY"))
