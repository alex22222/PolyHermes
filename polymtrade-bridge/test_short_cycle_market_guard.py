#!/usr/bin/env python3
"""Tests for short-cycle market execution guards."""

import sys
from pathlib import Path
from decimal import Decimal
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parent))
import main as bridge_main  # noqa: E402
from main import (  # noqa: E402
    _high_confidence_buy_reason,
    _generic_repeat_buy_reason,
    _crypto_exit_shadow_decision,
    _leader_event_activity_buy_reason,
    _near_expiry_news_buy_reason,
    _short_cycle_daily_limit_buy_reason,
    _short_cycle_duplicate_buy_reason,
    _short_cycle_global_buy_reason,
    _short_cycle_market_stale_reason,
    _short_cycle_price_band_buy_reason,
    _tail_risk_low_price_buy_reason,
)


class FakeRecorder:
    def __init__(
        self,
        has_prior=False,
        has_any_prior=False,
        daily_usage=(0, Decimal("0")),
        recent_records=None,
        market_end_date=None,
    ):
        self.has_prior = has_prior
        self.has_any_prior = has_any_prior
        self.daily_usage = daily_usage
        self.recent_records = recent_records or []
        self.market_end_date = market_end_date
        self.calls = []
        self.any_calls = []
        self.daily_calls = []
        self.recent_calls = []
        self.end_date_calls = []

    def has_prior_short_cycle_buy(self, market_id, market_slug, leader_address):
        self.calls.append((market_id, market_slug, leader_address))
        return self.has_prior

    def has_any_prior_short_cycle_buy(self, market_id, market_slug):
        self.any_calls.append((market_id, market_slug))
        return self.has_any_prior

    def btc_5m_success_buy_usage_since(self, since_ms):
        self.daily_calls.append(since_ms)
        return self.daily_usage

    def recent_leader_records_since(self, leader_address, since_ms, limit=200):
        self.recent_calls.append((leader_address, since_ms, limit))
        return self.recent_records

    def get_market_end_date(self, market_id):
        self.end_date_calls.append(market_id)
        return self.market_end_date


def test_btc_updown_5m_buy_is_skipped_near_close():
    slug = "btc-updown-5m-1782304500"

    early = _short_cycle_market_stale_reason(slug, "BUY", now_seconds=1782304709)
    assert early is None, early

    near_close = _short_cycle_market_stale_reason(slug, "BUY", now_seconds=1782304710)
    assert near_close is not None, near_close
    assert "Short-cycle market stale" in near_close
    assert "buffer=90s" in near_close

    sell = _short_cycle_market_stale_reason(slug, "SELL", now_seconds=1782304770)
    assert sell is not None, sell
    assert "Short-cycle market stale" in sell


def test_crypto_updown_15m_buy_and_sell_are_skipped_near_close():
    slug = "xrp-updown-15m-1782304500"

    early_buy = _short_cycle_market_stale_reason(slug, "BUY", now_seconds=1782305339)
    assert early_buy is None, early_buy

    near_close_buy = _short_cycle_market_stale_reason(slug, "BUY", now_seconds=1782305340)
    assert near_close_buy is not None, near_close_buy
    assert "buffer=60s" in near_close_buy

    near_close_sell = _short_cycle_market_stale_reason(slug, "SELL", now_seconds=1782305340)
    assert near_close_sell is not None, near_close_sell
    assert "Short-cycle market stale" in near_close_sell

    non_short_cycle = _short_cycle_market_stale_reason(
        "fed-decision-in-july-181",
        "SELL",
        now_seconds=1782305340,
    )
    assert non_short_cycle is None, non_short_cycle


def test_eth_updown_5m_buy_is_skipped_in_last_minute():
    slug = "eth-updown-5m-1782304500"

    early = _short_cycle_market_stale_reason(slug, "BUY", now_seconds=1782304739)
    assert early is None, early

    near_close = _short_cycle_market_stale_reason(slug, "BUY", now_seconds=1782304740)
    assert near_close is not None, near_close
    assert "Short-cycle market stale" in near_close
    assert "buffer=60s" in near_close


def test_crypto_exit_shadow_take_profit_and_stop_loss():
    take_profit = _crypto_exit_shadow_decision(
        market_slug="xrp-updown-5m-1782304500",
        market_title="XRP Up or Down - test",
        entry_price=Decimal("0.50"),
        current_price=Decimal("0.80"),
        entry_created_at_ms=1782304500000,
        now_seconds=1782304550,
    )
    assert take_profit is not None
    assert take_profit["action"] == "TAKE_PROFIT", take_profit
    assert take_profit["trigger"] == "take_profit", take_profit

    stop_loss = _crypto_exit_shadow_decision(
        market_slug="xrp-updown-5m-1782304500",
        market_title="XRP Up or Down - test",
        entry_price=Decimal("0.50"),
        current_price=Decimal("0.25"),
        entry_created_at_ms=1782304500000,
        now_seconds=1782304550,
    )
    assert stop_loss is not None
    assert stop_loss["action"] == "STOP_LOSS", stop_loss
    assert stop_loss["trigger"] == "stop_loss", stop_loss


def test_crypto_exit_shadow_respects_hold_and_close_windows():
    min_hold = _crypto_exit_shadow_decision(
        market_slug="xrp-updown-5m-1782304500",
        market_title="XRP Up or Down - test",
        entry_price=Decimal("0.50"),
        current_price=Decimal("0.80"),
        entry_created_at_ms=1782304500000,
        now_seconds=1782304510,
    )
    assert min_hold is not None
    assert min_hold["action"] == "HOLD", min_hold
    assert min_hold["blocked_reason"] == "min_hold_seconds=20", min_hold

    near_close = _crypto_exit_shadow_decision(
        market_slug="xrp-updown-5m-1782304500",
        market_title="XRP Up or Down - test",
        entry_price=Decimal("0.50"),
        current_price=Decimal("0.25"),
        entry_created_at_ms=1782304500000,
        now_seconds=1782304770,
    )
    assert near_close is not None
    assert near_close["action"] == "HOLD", near_close
    assert near_close["blocked_reason"] == "no_exit_last_seconds=35", near_close


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


def test_tail_risk_low_price_buy_guard():
    allowed = _tail_risk_low_price_buy_reason("BUY", Decimal("0.10"))
    assert allowed is None, allowed

    low_price = _tail_risk_low_price_buy_reason("BUY", Decimal("0.0999"))
    assert low_price is not None, low_price
    assert "Low-price tail-risk BUY skipped" in low_price
    assert "min=0.10" in low_price

    sell = _tail_risk_low_price_buy_reason("SELL", Decimal("0.006"))
    assert sell is None, sell


def test_high_confidence_buy_guard():
    allowed = _high_confidence_buy_reason(
        "BUY",
        Decimal("0.55"),
        title="XRP Up or Down - July 12, 3:40AM-3:45AM ET",
        market_slug="xrp-updown-5m-1783842000",
    )
    assert allowed is None, allowed

    high_price = _high_confidence_buy_reason(
        "BUY",
        Decimal("0.5501"),
        title="XRP Up or Down - July 12, 3:40AM-3:45AM ET",
        market_slug="xrp-updown-5m-1783842000",
    )
    assert high_price is not None, high_price
    assert "High-price low-upside BUY skipped" in high_price
    assert "max=0.55" in high_price

    finance = _high_confidence_buy_reason(
        "BUY",
        Decimal("0.88"),
        title="Will the Fed decrease interest rates by 25 bps after the July 2026 meeting?",
        market_slug="fed-decision-in-july-181",
    )
    assert finance is None, finance

    sell = _high_confidence_buy_reason(
        "SELL",
        Decimal("0.96"),
        title="XRP Up or Down - July 12, 3:40AM-3:45AM ET",
        market_slug="xrp-updown-5m-1783842000",
    )
    assert sell is None, sell


def test_generic_repeat_same_market_buy_guard():
    original = bridge_main.recorder
    try:
        bridge_main.recorder = FakeRecorder(
            recent_records=[
                {
                    "market_id": "0xmarket",
                    "side": "BUY",
                    "status": "SUCCESS",
                    "raw_payload": '{"marketSlug":"same-market","outcome":"Yes"}',
                }
            ]
        )
        signal = SimpleNamespace(
            leader_address="0xLeader",
            condition_id="0xmarket",
            market_slug="same-market",
        )
        duplicate = _generic_repeat_buy_reason(signal, "BUY", now_ms=1783234800000)
        assert duplicate is not None, duplicate
        assert "Repeat same-market BUY skipped" in duplicate

        sell = _generic_repeat_buy_reason(signal, "SELL", now_ms=1783234800000)
        assert sell is None, sell
    finally:
        bridge_main.recorder = original


def test_near_expiry_small_news_buy_guard():
    signal = SimpleNamespace(
        title="Iran successfully targets shipping on July 8?",
        condition_id="0xiran",
        market_end_date=1783497600000,
    )
    reason = _near_expiry_news_buy_reason(
        signal=signal,
        side="BUY",
        price=Decimal("0.50"),
        leader_size=Decimal("10"),
        now_ms=1783400000000,
    )
    assert reason is not None, reason
    assert "Near-expiry small news-event BUY skipped" in reason

    large = _near_expiry_news_buy_reason(
        signal=signal,
        side="BUY",
        price=Decimal("0.50"),
        leader_size=Decimal("100"),
        now_ms=1783400000000,
    )
    assert large is None, large

    sports = SimpleNamespace(
        title="Will Mexico reach the 2026 FIFA World Cup final?",
        condition_id="0xfifa",
        market_end_date=1783497600000,
    )
    sports_reason = _near_expiry_news_buy_reason(
        signal=sports,
        side="BUY",
        price=Decimal("0.50"),
        leader_size=Decimal("10"),
        now_ms=1783400000000,
    )
    assert sports_reason is None, sports_reason


def test_same_event_high_frequency_buy_guard():
    original = bridge_main.recorder
    try:
        recent_records = [
            {
                "side": "BUY",
                "status": "SUCCESS",
                "market_title": "Will the Fed decrease interest rates by 25 bps after the July 2026 meeting?",
                "outcome": "Yes",
                "raw_payload": '{"marketSlug":"will-the-fed-decrease-interest-rates-by-25-bps-after-the-july-2026-meeting","title":"Will the Fed decrease interest rates by 25 bps after the July 2026 meeting?","outcome":"Yes"}',
            }
            for _ in range(5)
        ]
        bridge_main.recorder = FakeRecorder(recent_records=recent_records)
        signal = SimpleNamespace(
            leader_address="0xLeader",
            market_slug="will-the-fed-decrease-interest-rates-by-25-bps-after-the-july-2026-meeting",
            title="Will the Fed decrease interest rates by 25 bps after the July 2026 meeting?",
            outcome="Yes",
        )

        reason = _leader_event_activity_buy_reason(signal, "BUY", now_ms=1783234800000)
        assert reason is not None, reason
        assert "High-frequency same-event leader activity skipped" in reason
    finally:
        bridge_main.recorder = original


def test_same_event_multi_outcome_combo_buy_guard():
    original = bridge_main.recorder
    try:
        recent_records = [
            {
                "side": "BUY",
                "status": "SUCCESS",
                "market_title": "Will there be no change in Fed interest rates after the July 2026 meeting?",
                "outcome": "Yes",
                "raw_payload": '{"marketSlug":"will-there-be-no-change-in-fed-interest-rates-after-the-july-2026-meeting","title":"Will there be no change in Fed interest rates after the July 2026 meeting?","outcome":"Yes"}',
            }
        ]
        bridge_main.recorder = FakeRecorder(recent_records=recent_records)
        signal = SimpleNamespace(
            leader_address="0xLeader",
            market_slug="will-the-fed-decrease-interest-rates-by-25-bps-after-the-july-2026-meeting",
            title="Will the Fed decrease interest rates by 25 bps after the July 2026 meeting?",
            outcome="Yes",
        )

        reason = _leader_event_activity_buy_reason(signal, "BUY", now_ms=1783234800000)
        assert reason is not None, reason
        assert "Multi-outcome same-event leader combo skipped" in reason

        sell = _leader_event_activity_buy_reason(signal, "SELL", now_ms=1783234800000)
        assert sell is None, sell
    finally:
        bridge_main.recorder = original


def test_same_event_combo_ignores_failed_buy_records():
    original = bridge_main.recorder
    try:
        recent_records = [
            {
                "side": "BUY",
                "status": "FAILED",
                "market_title": "XRP Up or Down - July 10, 9:55PM-10:00PM ET",
                "outcome": "Up",
                "raw_payload": '{"marketSlug":"xrp-updown-5m-1783734900","title":"XRP Up or Down - July 10, 9:55PM-10:00PM ET","outcome":"Up"}',
            }
        ]
        bridge_main.recorder = FakeRecorder(recent_records=recent_records)
        signal = SimpleNamespace(
            leader_address="0xLeader",
            market_slug="xrp-updown-5m-1783734900",
            title="XRP Up or Down - July 10, 9:55PM-10:00PM ET",
            outcome="Down",
        )

        reason = _leader_event_activity_buy_reason(signal, "BUY", now_ms=1783735027000)
        assert reason is None, reason
    finally:
        bridge_main.recorder = original


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
    test_crypto_updown_15m_buy_and_sell_are_skipped_near_close()
    test_btc_updown_5m_duplicate_buy_guard()
    test_btc_updown_5m_price_band_buy_guard()
    test_tail_risk_low_price_buy_guard()
    test_high_confidence_buy_guard()
    test_generic_repeat_same_market_buy_guard()
    test_near_expiry_small_news_buy_guard()
    test_same_event_high_frequency_buy_guard()
    test_same_event_multi_outcome_combo_buy_guard()
    test_btc_updown_5m_global_buy_guard()
    test_btc_updown_5m_daily_limit_guard()
    print("short-cycle market guard tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
