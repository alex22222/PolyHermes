#!/usr/bin/env python3
"""Tests for CopyTradingRuleEngine secondary risk controls."""

import sys
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from copy_trading_config import CopyTradingConfig, CopyTradingRuleEngine, infer_market_category


class TestInferMarketCategory(unittest.TestCase):
    def test_politics_keywords(self):
        self.assertEqual(infer_market_category("Will Trump win the 2024 election?"), "politics")
        self.assertEqual(infer_market_category("US-China tariff policy"), "politics")

    def test_legal_case_as_politics(self):
        self.assertEqual(
            infer_market_category("Will Harvey Weinstein be sentenced to prison?"),
            "politics",
        )

    def test_sports_keywords(self):
        self.assertEqual(infer_market_category("NBA Finals MVP"), "sports")
        self.assertEqual(infer_market_category("CS2 Major Stage"), "sports")

    def test_sports_terms_outrank_crypto_token(self):
        # A sports market whose title happens to contain generic "token" should still be sports
        self.assertEqual(infer_market_category("Baseball Token Market"), "sports")
        self.assertEqual(infer_market_category("Spread: Netherlands (-1.5)"), "sports")

    def test_crypto_keywords(self):
        self.assertEqual(infer_market_category("Bitcoin ETF approval"), "crypto")
        self.assertEqual(infer_market_category("Solana airdrop"), "crypto")

    def test_finance_keywords(self):
        self.assertEqual(infer_market_category("Fed interest rate decision"), "finance")
        self.assertEqual(infer_market_category("S&P 500 all-time high"), "finance")

    def test_unknown_returns_none(self):
        self.assertIsNone(infer_market_category("Random unrelated title"))
        self.assertIsNone(infer_market_category(""))
        self.assertIsNone(infer_market_category(None))


class TestCopyTradingRuleEngineFilters(unittest.TestCase):
    def _base_config(self, **overrides) -> CopyTradingConfig:
        defaults = dict(
            id=1,
            account_id=1,
            leader_id=1,
            leader_address="0xabc",
            leader_category="sports",
            copy_mode="RATIO",
            copy_ratio=Decimal("1"),
            fixed_amount=None,
            max_order_size=Decimal("1000"),
            min_order_size=Decimal("1"),
            max_daily_loss=None,
            max_daily_orders=100,
            price_tolerance=Decimal("5"),
            delay_seconds=0,
            support_sell=True,
            min_order_depth=None,
            max_spread=None,
            min_price=None,
            max_price=None,
            max_position_value=None,
            max_price_deviation=None,
            max_delay_seconds=None,
            keyword_filter_mode="DISABLED",
            keywords=None,
            max_market_end_date=None,
            push_failed_orders=False,
        )
        defaults.update(overrides)
        return CopyTradingConfig(**defaults)

    def setUp(self):
        self.engine = CopyTradingRuleEngine(refresh_interval=3600)
        self.engine._configs = [self._base_config()]
        self.engine._last_refresh = time.time()  # prevent DB refresh during tests

    def test_category_match_passes(self):
        reason = self.engine._check_filters(
            self.engine._configs[0],
            side="BUY",
            title="NBA Finals",
            price=Decimal("0.5"),
            market_end_date_ms=None,
            signal_timestamp_ms=None,
            market_category="sports",
        )
        self.assertIsNone(reason)

    def test_category_mismatch_filters(self):
        reason = self.engine._check_filters(
            self.engine._configs[0],
            side="BUY",
            title="Trump election",
            price=Decimal("0.5"),
            market_end_date_ms=None,
            signal_timestamp_ms=None,
            market_category="politics",
        )
        self.assertIsNotNone(reason)
        self.assertIn("category mismatch", reason)

    def test_sports_title_with_token_inferred_as_sports(self):
        # The leader is configured for sports; the market title contains "token" but is clearly sports
        matches = self.engine.get_matching_configs(
            trader_address="0xabc",
            side="BUY",
            title="Baseball Token Market",
            price=Decimal("0.5"),
            signal_timestamp_ms=int(time.time() * 1000) - 1_000,
        )
        self.assertEqual(len(matches), 1)
        cfg, reason = matches[0]
        self.assertIsNone(reason)

    def test_delay_within_threshold_passes(self):
        now_ms = int(time.time() * 1000)
        cfg = self._base_config(max_delay_seconds=60)
        reason = self.engine._check_filters(
            cfg,
            side="BUY",
            title="NBA Finals",
            price=Decimal("0.5"),
            market_end_date_ms=None,
            signal_timestamp_ms=now_ms - 10_000,  # 10s ago
            market_category="sports",
        )
        self.assertIsNone(reason)

    def test_delay_exceeds_threshold_filters(self):
        now_ms = int(time.time() * 1000)
        cfg = self._base_config(max_delay_seconds=5)
        reason = self.engine._check_filters(
            cfg,
            side="BUY",
            title="NBA Finals",
            price=Decimal("0.5"),
            market_end_date_ms=None,
            signal_timestamp_ms=now_ms - 60_000,  # 60s ago
            market_category="sports",
        )
        self.assertIsNotNone(reason)
        self.assertIn("signal delay", reason)

    def test_get_matching_configs_uses_inferred_category(self):
        self.engine._configs = [self._base_config(leader_category="politics")]
        matches = self.engine.get_matching_configs(
            trader_address="0xabc",
            side="BUY",
            title="Trump election odds",
            price=Decimal("0.5"),
            signal_timestamp_ms=int(time.time() * 1000) - 1_000,
        )
        self.assertEqual(len(matches), 1)
        cfg, reason = matches[0]
        self.assertIsNone(reason)

    def test_get_matching_configs_filters_by_delay(self):
        self.engine._configs = [self._base_config(max_delay_seconds=5)]
        matches = self.engine.get_matching_configs(
            trader_address="0xabc",
            side="BUY",
            title="NBA Finals",
            price=Decimal("0.5"),
            signal_timestamp_ms=int(time.time() * 1000) - 60_000,
        )
        self.assertEqual(len(matches), 1)
        cfg, reason = matches[0]
        self.assertIsNotNone(reason)
        self.assertIn("signal delay", reason)


if __name__ == "__main__":
    unittest.main()
