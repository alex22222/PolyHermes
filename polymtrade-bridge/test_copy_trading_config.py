#!/usr/bin/env python3
"""Tests for CopyTradingRuleEngine secondary risk controls."""

import sys
import time
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))
from copy_trading_config import (
    CopyTradingConfig,
    CopyTradingRuleEngine,
    infer_market_category,
    is_category_allowed,
)


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
            leader_research_tag=None,
            leader_research_risk_flags=None,
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

    def test_normalize_account_id(self):
        self.assertIsNone(CopyTradingRuleEngine.normalize_account_id(None))
        self.assertIsNone(CopyTradingRuleEngine.normalize_account_id(""))
        self.assertIsNone(CopyTradingRuleEngine.normalize_account_id("0"))
        self.assertIsNone(CopyTradingRuleEngine.normalize_account_id("-1"))
        self.assertIsNone(CopyTradingRuleEngine.normalize_account_id("abc"))
        self.assertEqual(CopyTradingRuleEngine.normalize_account_id("2"), 2)
        self.assertEqual(CopyTradingRuleEngine.normalize_account_id(3), 3)

    def test_set_account_id_normalizes_and_forces_reload(self):
        self.engine.account_id = None
        self.engine._last_refresh = time.time()
        self.engine.set_account_id("2")
        self.assertEqual(self.engine.active_account_id, 2)
        self.assertEqual(self.engine._last_refresh, 0.0)

        self.engine._last_refresh = 123.0
        self.engine.set_account_id(2)
        self.assertEqual(self.engine._last_refresh, 123.0)

        self.engine.set_account_id("0")
        self.assertEqual(self.engine.active_account_id, 1)
        self.assertEqual(self.engine._last_refresh, 0.0)

    def test_active_account_id_infers_single_config_account(self):
        self.engine.account_id = None
        self.engine._configs = [
            self._base_config(account_id=2),
            self._base_config(id=2, account_id=2),
        ]
        self.assertEqual(self.engine.active_account_id, 2)

    def test_active_account_id_does_not_infer_mixed_accounts(self):
        self.engine.account_id = None
        self.engine._configs = [
            self._base_config(account_id=2),
            self._base_config(id=2, account_id=3),
        ]
        self.assertIsNone(self.engine.active_account_id)

    def test_resolve_wallet_address_by_account_id(self):
        class FakeCursor:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def execute(self, sql, params):
                self.sql = sql
                self.params = params

            def fetchone(self):
                return {"wallet_address": "0xAbC0000000000000000000000000000000000001"}

        class FakeConnection:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def cursor(self):
                return FakeCursor()

        with patch.object(self.engine, "_connect", return_value=FakeConnection()):
            self.assertEqual(
                self.engine.resolve_wallet_address_by_account_id(2),
                "0xabc0000000000000000000000000000000000001",
            )

    def test_resolve_wallet_address_by_account_id_ignores_invalid_id(self):
        with patch.object(self.engine, "_connect") as connect:
            self.assertIsNone(self.engine.resolve_wallet_address_by_account_id("0"))
            connect.assert_not_called()

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

    def test_research_risky_leader_buy_is_filtered(self):
        cfg = self._base_config(
            leader_category="finance",
            leader_research_tag="RISKY",
            leader_research_risk_flags="negative_pnl,zero_win_rate",
        )
        reason = self.engine._check_filters(
            cfg,
            side="BUY",
            title="Fed rate decision",
            price=Decimal("0.5"),
            market_end_date_ms=None,
            signal_timestamp_ms=None,
            market_category="finance",
        )
        self.assertEqual(reason, "leader research tag RISKY")

    def test_research_risky_sports_buy_is_allowed(self):
        cfg = self._base_config(
            leader_research_tag="RISKY",
            leader_research_risk_flags="negative_pnl,zero_win_rate",
        )
        reason = self.engine._check_filters(
            cfg,
            side="BUY",
            title="WTA Rome match",
            price=Decimal("0.5"),
            market_end_date_ms=None,
            signal_timestamp_ms=None,
            market_category="sports",
        )
        self.assertIsNone(reason)

    def test_research_risky_leader_sell_is_not_filtered(self):
        cfg = self._base_config(
            leader_research_tag="RISKY",
            leader_research_risk_flags="negative_pnl,zero_win_rate",
        )
        reason = self.engine._check_filters(
            cfg,
            side="SELL",
            title="NBA Finals",
            price=Decimal("0.5"),
            market_end_date_ms=None,
            signal_timestamp_ms=None,
            market_category="sports",
        )
        self.assertIsNone(reason)

    def test_research_hard_risk_flag_buy_is_filtered(self):
        cfg = self._base_config(
            leader_category="finance",
            leader_research_risk_flags="buy_only_no_exit",
        )
        reason = self.engine._check_filters(
            cfg,
            side="BUY",
            title="Fed rate decision",
            price=Decimal("0.5"),
            market_end_date_ms=None,
            signal_timestamp_ms=None,
            market_category="finance",
        )
        self.assertEqual(reason, "leader research risk flags: buy_only_no_exit")

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

    def test_primary_category_cross_match_passes(self):
        cfg = self._base_config(leader_category="politics")
        reason = self.engine._check_filters(
            cfg,
            side="BUY",
            title="Fed interest rate decision",
            price=Decimal("0.5"),
            market_end_date_ms=None,
            signal_timestamp_ms=None,
            market_category="finance",
        )
        self.assertIsNone(reason)

    @patch.dict("os.environ", {"COPY_TRADING_ALLOW_PRIMARY_TO_CRYPTO": "false"})
    def test_primary_category_does_not_allow_crypto(self):
        cfg = self._base_config(leader_category="politics")
        reason = self.engine._check_filters(
            cfg,
            side="BUY",
            title="Bitcoin ETF approval",
            price=Decimal("0.5"),
            market_end_date_ms=None,
            signal_timestamp_ms=None,
            market_category="crypto",
        )
        self.assertIsNotNone(reason)
        self.assertIn("category mismatch", reason)

    def test_primary_category_allows_clear_sports_market(self):
        self.assertTrue(is_category_allowed("politics", "sports"))
        self.assertTrue(is_category_allowed("finance", "sports"))

        cfg = self._base_config(leader_category="politics")
        self.engine._configs = [cfg]
        matches = self.engine.get_matching_configs(
            "0xabc",
            "BUY",
            "Counter-Strike: Bushido Wildcats vs MOUZ NXT (BO3) - ESL Challenger League",
            Decimal("0.60"),
        )
        self.assertEqual(matches, [(cfg, None)])

    @patch.dict("os.environ", {"COPY_TRADING_ALLOW_PRIMARY_TO_CRYPTO": "true"})
    def test_primary_category_allows_crypto_when_temporarily_enabled(self):
        self.assertTrue(is_category_allowed("politics", "crypto"))
        self.assertTrue(is_category_allowed("finance", "crypto"))

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

    def test_proportional_risk_buy_uses_leader_value_and_caps_max_order(self):
        cfg = self._base_config(
            copy_mode="PROPORTIONAL_RISK",
            copy_ratio=Decimal("0.50"),
            min_order_size=Decimal("1"),
            max_order_size=Decimal("2"),
        )
        amount = self.engine.compute_buy_quantity(
            cfg, leader_price=Decimal("0.50"), leader_size=Decimal("10")
        )
        self.assertEqual(amount, Decimal("2.00"))

    def test_proportional_risk_buy_below_min_records_reason(self):
        cfg = self._base_config(
            copy_mode="PROPORTIONAL_RISK",
            copy_ratio=Decimal("0.10"),
            min_order_size=Decimal("1"),
        )
        amount = self.engine.compute_buy_quantity(
            cfg, leader_price=Decimal("0.50"), leader_size=Decimal("10")
        )
        reason = self.engine.buy_skip_reason(
            cfg, leader_price=Decimal("0.50"), leader_size=Decimal("10")
        )
        self.assertIsNone(amount)
        self.assertIn("Below min_order_size", reason)

    def test_fixed_buy_cannot_amplify_small_leader_notional(self):
        cfg = self._base_config(
            copy_mode="FIXED",
            fixed_amount=Decimal("1"),
            min_order_size=Decimal("1"),
        )
        amount = self.engine.compute_buy_quantity(
            cfg, leader_price=Decimal("0.50"), leader_size=Decimal("1")
        )
        reason = self.engine.buy_skip_reason(
            cfg, leader_price=Decimal("0.50"), leader_size=Decimal("1")
        )
        self.assertIsNone(amount)
        self.assertIn("Leader notional amplification skipped", reason)

    def test_fixed_buy_allows_leader_notional_at_least_local_amount(self):
        cfg = self._base_config(
            copy_mode="FIXED",
            fixed_amount=Decimal("1"),
            min_order_size=Decimal("1"),
        )
        amount = self.engine.compute_buy_quantity(
            cfg, leader_price=Decimal("0.50"), leader_size=Decimal("2")
        )
        self.assertEqual(amount, Decimal("1.00"))

    def test_proportional_risk_sell_uses_leader_size_ratio(self):
        cfg = self._base_config(
            copy_mode="PROPORTIONAL_RISK",
            copy_ratio=Decimal("0.25"),
            min_order_size=Decimal("1"),
            max_order_size=Decimal("100"),
        )
        shares = self.engine.compute_sell_shares(
            cfg, leader_price=Decimal("0.50"), leader_size=Decimal("20")
        )
        self.assertEqual(shares, Decimal("5.0000"))

    def test_sell_below_min_order_size_is_allowed_for_risk_reduction(self):
        cfg = self._base_config(
            copy_mode="PROPORTIONAL_RISK",
            copy_ratio=Decimal("1"),
            min_order_size=Decimal("1"),
        )
        shares = self.engine.compute_sell_shares(
            cfg, leader_price=Decimal("0.56"), leader_size=Decimal("0.8")
        )
        reason = self.engine.sell_skip_reason(
            cfg, leader_price=Decimal("0.56"), leader_size=Decimal("0.8")
        )
        self.assertEqual(shares, Decimal("0.8000"))
        self.assertIsNone(reason)


if __name__ == "__main__":
    unittest.main()
