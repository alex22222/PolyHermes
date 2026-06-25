#!/usr/bin/env python3
"""Tests for short-cycle market execution guards."""

import sys
from pathlib import Path
from decimal import Decimal

sys.path.insert(0, str(Path(__file__).resolve().parent))
import main as bridge_main  # noqa: E402
from main import (  # noqa: E402
    _short_cycle_daily_limit_buy_reason,
    _short_cycle_duplicate_buy_reason,
    _short_cycle_global_buy_reason,
    _short_cycle_market_stale_reason,
    _short_cycle_price_band_buy_reason,
)


class FakeRecorder:
    def __init__(self, has_prior=False, has_any_prior=False, daily_usage=(0, Decimal("0"))):
        self.has_prior = has_prior
        self.has_any_prior = has_any_prior
        self.daily_usage = daily_usage
        self.calls = []
        self.any_calls = []
        self.daily_calls = []

    def has_prior_short_cycle_buy(self, market_id, market_slug, leader_address):
        self.calls.append((market_id, market_slug, leader_address))
        return self.has_prior

    def has_any_prior_short_cycle_buy(self, market_id, market_slug):
        self.any_calls.append((market_id, market_slug))
        return self.has_any_prior

    def btc_5m_success_buy_usage_since(self, since_ms):
        self.daily_calls.append(since_ms)
        return self.daily_usage


def test_btc_updown_5m_buy_is_skipped_near_close():
    slug = "btc-updown-5m-1782304500"

    early = _short_cycle_market_stale_reason(slug, "BUY", now_seconds=1782304709)
    assert early is None, early

    near_close = _short_cycle_market_stale_reason(slug, "BUY", now_seconds=1782304710)
    assert near_close is not None, near_close
    assert "Short-cycle market stale" in near_close
    assert "buffer=90s" in near_close

    sell = _short_cycle_market_stale_reason(slug, "SELL", now_seconds=1782304770)
    assert sell is None, sell


def test_btc_updown_5m_duplicate_buy_guard():
    original = bridge_main.recorder
    try:
        bridge_main.recorder = FakeRecorder(False)
        first = _short_cycle_duplicate_buy_reason(
            market_slug="btc-updown-5m-1782309300",
            market_id="0xmarket",
            leader_address="0xLeader",
        )
        assert first is None, first
        assert bridge_main.recorder.calls == [("0xmarket", "btc-updown-5m-1782309300", "0xLeader")]

        bridge_main.recorder = FakeRecorder(True)
        duplicate = _short_cycle_duplicate_buy_reason(
            market_slug="btc-updown-5m-1782309300",
            market_id="0xmarket",
            leader_address="0xLeader",
        )
        assert duplicate is not None, duplicate
        assert "Duplicate short-cycle market BUY skipped" in duplicate

        non_btc = _short_cycle_duplicate_buy_reason(
            market_slug="will-someone-win",
            market_id="0xmarket",
            leader_address="0xLeader",
        )
        assert non_btc is None, non_btc
    finally:
        bridge_main.recorder = original


def test_btc_updown_5m_price_band_buy_guard():
    slug = "btc-updown-5m-1782309300"

    allowed = _short_cycle_price_band_buy_reason(slug, "BUY", Decimal("0.65"))
    assert allowed is None, allowed

    low_price = _short_cycle_price_band_buy_reason(slug, "BUY", Decimal("0.1999"))
    assert low_price is not None, low_price
    assert "BTC 5M low-price BUY skipped" in low_price
    assert "min=0.20" in low_price

    high_price = _short_cycle_price_band_buy_reason(slug, "BUY", Decimal("0.6501"))
    assert high_price is not None, high_price
    assert "BTC 5M high-price BUY skipped" in high_price
    assert "max=0.65" in high_price

    sell = _short_cycle_price_band_buy_reason(slug, "SELL", Decimal("0.99"))
    assert sell is None, sell

    non_btc = _short_cycle_price_band_buy_reason("will-someone-win", "BUY", Decimal("0.99"))
    assert non_btc is None, non_btc


def test_btc_updown_5m_global_buy_guard():
    original = bridge_main.recorder
    try:
        bridge_main.recorder = FakeRecorder(has_any_prior=False)
        first = _short_cycle_global_buy_reason(
            market_slug="btc-updown-5m-1782309300",
            market_id="0xmarket",
        )
        assert first is None, first
        assert bridge_main.recorder.any_calls == [("0xmarket", "btc-updown-5m-1782309300")]

        bridge_main.recorder = FakeRecorder(has_any_prior=True)
        duplicate = _short_cycle_global_buy_reason(
            market_slug="btc-updown-5m-1782309300",
            market_id="0xmarket",
        )
        assert duplicate is not None, duplicate
        assert "BTC 5M global market BUY skipped" in duplicate

        non_btc = _short_cycle_global_buy_reason(
            market_slug="will-someone-win",
            market_id="0xmarket",
        )
        assert non_btc is None, non_btc
    finally:
        bridge_main.recorder = original


def test_btc_updown_5m_daily_limit_guard():
    original = bridge_main.recorder
    try:
        slug = "btc-updown-5m-1782309300"
        bridge_main.recorder = FakeRecorder(daily_usage=(49, Decimal("49.00")))
        allowed = _short_cycle_daily_limit_buy_reason(
            slug,
            "BUY",
            Decimal("1.00"),
            now_seconds=1782312000,
        )
        assert allowed is None, allowed
        assert len(bridge_main.recorder.daily_calls) == 1

        bridge_main.recorder = FakeRecorder(daily_usage=(50, Decimal("50.00")))
        count_limited = _short_cycle_daily_limit_buy_reason(
            slug,
            "BUY",
            Decimal("0.50"),
            now_seconds=1782312000,
        )
        assert count_limited is not None, count_limited
        assert "BTC 5M daily BUY count limit skipped" in count_limited
        assert "max=50" in count_limited

        sell = _short_cycle_daily_limit_buy_reason(slug, "SELL", Decimal("10"), now_seconds=1782312000)
        assert sell is None, sell
    finally:
        bridge_main.recorder = original


def main() -> int:
    test_btc_updown_5m_buy_is_skipped_near_close()
    test_btc_updown_5m_duplicate_buy_guard()
    test_btc_updown_5m_price_band_buy_guard()
    test_btc_updown_5m_global_buy_guard()
    test_btc_updown_5m_daily_limit_guard()
    print("short-cycle market guard tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
