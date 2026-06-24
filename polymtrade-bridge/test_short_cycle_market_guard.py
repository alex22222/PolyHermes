#!/usr/bin/env python3
"""Tests for short-cycle market execution guards."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import main as bridge_main  # noqa: E402
from main import _short_cycle_duplicate_buy_reason, _short_cycle_market_stale_reason  # noqa: E402


class FakeRecorder:
    def __init__(self, has_prior):
        self.has_prior = has_prior
        self.calls = []

    def has_prior_short_cycle_buy(self, market_id, market_slug, leader_address):
        self.calls.append((market_id, market_slug, leader_address))
        return self.has_prior


def test_btc_updown_5m_buy_is_skipped_near_close():
    slug = "btc-updown-5m-1782304500"

    early = _short_cycle_market_stale_reason(slug, "BUY", now_seconds=1782304700)
    assert early is None, early

    near_close = _short_cycle_market_stale_reason(slug, "BUY", now_seconds=1782304770)
    assert near_close is not None, near_close
    assert "Short-cycle market stale" in near_close

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


def main() -> int:
    test_btc_updown_5m_buy_is_skipped_near_close()
    test_btc_updown_5m_duplicate_buy_guard()
    print("short-cycle market guard tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
