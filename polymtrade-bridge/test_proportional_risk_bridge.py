#!/usr/bin/env python3
"""Tests for proportional-risk Bridge execution guards."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import ANY, AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import main
from copy_trading_config import COPY_MODE_PROPORTIONAL_RISK
from bridge_metrics import BridgeMetrics
from portfolio_risk_client import PortfolioRiskCheck


class FakeRecorder:
    def __init__(self):
        self.pending = []
        self.updates = []
        self.results = []
        self.leader_sell_size = Decimal("0")
        self.success_sell_size = Decimal("0")

    def exists(self, external_trade_id):
        return False

    def record_pending(self, **kwargs):
        self.pending.append(kwargs)
        return len(self.pending)

    def update_status(self, record_id, status, error_message=None):
        self.updates.append((record_id, status, error_message))

    def record_result(self, **kwargs):
        self.results.append(kwargs)
        return len(self.results)

    def recent_leader_sell_size(self, **kwargs):
        return self.leader_sell_size

    def recent_success_sell_size(self, **kwargs):
        return self.success_sell_size


class FakeRuleEngine:
    def __init__(self, cfg):
        self.cfg = cfg

    def get_matching_configs(self, **kwargs):
        return [(self.cfg, None)]

    async def sleep_delay(self, cfg):
        return None

    def compute_sell_shares(self, cfg, price, leader_size):
        return Decimal("2.0000")

    def sell_skip_reason(self, cfg, price, leader_size):
        return None


class FakeBuyRuleEngine(FakeRuleEngine):
    def compute_buy_quantity(self, cfg, price, leader_size):
        return Decimal("1.25")

    def buy_skip_reason(self, cfg, price, leader_size):
        return None


class FakeLedger:
    def get_net_quantity(self, **kwargs):
        return Decimal("0")

    def has_sufficient_position(self, **kwargs):
        raise AssertionError("proportional-risk SELL should not use stale ledger pre-check")


class InsufficientLedger:
    def has_sufficient_position(self, **kwargs):
        return False


class TestProportionalRiskBridge(unittest.IsolatedAsyncioTestCase):
    def _config(self):
        return SimpleNamespace(
            id=7,
            account_id=2,
            copy_mode=COPY_MODE_PROPORTIONAL_RISK,
        )

    def _signal(self, side="SELL", size=4, market_slug="market-slug"):
        return main.LeaderTradeSignal(
            timestamp=1,
            leaderAddress="0xLeader",
            transactionHash="0xTx",
            modelCandidateId="candidate-1",
            conditionId="condition-1",
            marketSlug=market_slug,
            title="Test Market",
            side=side,
            outcome="Yes",
            outcomeIndex=0,
            price=0.5,
            size=size,
        )

    def test_small_buyback_uses_leader_webhook_sell_before_local_success(self):
        recorder = FakeRecorder()
        recorder.leader_sell_size = Decimal("10")
        recorder.success_sell_size = Decimal("0")
        cfg = self._config()

        with patch.object(main, "recorder", recorder):
            reason = main._proportional_risk_small_buyback_reason(
                cfg=cfg,
                signal=self._signal(side="BUY", size=2),
                side="BUY",
                leader_size=Decimal("2"),
                now_ms=1_000_000,
            )

        self.assertIsNotNone(reason)
        self.assertIn("Small buyback", reason)

    async def test_sell_uses_live_fallback_when_local_ledger_is_empty(self):
        cfg = self._config()
        recorder = FakeRecorder()
        executor = SimpleNamespace(
            execute_trade=AsyncMock(return_value={"verified": True}),
        )

        risk_check = AsyncMock()
        with (
            patch.object(main, "rule_engine", FakeRuleEngine(cfg)),
            patch.object(main, "recorder", recorder),
            patch.object(main, "position_ledger", FakeLedger()),
            patch.object(main, "executor", executor),
            patch.object(main, "_get_live_position_quantity", AsyncMock(return_value=Decimal("3"))),
            patch.object(main, "_wait_for_live_position_decrease", AsyncMock(return_value=Decimal("1"))),
            patch.object(main, "_short_cycle_market_stale_reason", MagicMock(return_value=None)),
            patch.object(main, "_evaluate_portfolio_buy_risk", risk_check),
        ):
            await main.handle_signal(self._signal())
            await main._stop_verification_tasks()

        executor.execute_trade.assert_awaited_once()
        _, kwargs = executor.execute_trade.await_args
        self.assertEqual(kwargs["side"], "SELL")
        self.assertEqual(kwargs["size_shares"], 2.0)
        self.assertFalse(kwargs["verify"])
        self.assertEqual(recorder.updates[-1][1], "SUCCESS")
        risk_check.assert_not_awaited()

    async def test_stale_sell_skips_before_live_portfolio_or_ui(self):
        cfg = self._config()
        recorder = FakeRecorder()
        executor = SimpleNamespace(
            execute_trade=AsyncMock(return_value={"verified": True}),
        )
        live_quantity = AsyncMock(return_value=Decimal("3"))

        with (
            patch.object(main, "rule_engine", FakeRuleEngine(cfg)),
            patch.object(main, "recorder", recorder),
            patch.object(main, "position_ledger", FakeLedger()),
            patch.object(main, "executor", executor),
            patch.object(main, "_get_live_position_quantity", live_quantity),
            patch.object(
                main,
                "_short_cycle_market_stale_reason",
                MagicMock(return_value="Short-cycle market stale or closing soon, skipped"),
            ),
        ):
            await main.handle_signal(self._signal())

        live_quantity.assert_not_awaited()
        executor.execute_trade.assert_not_awaited()
        self.assertEqual("FAILED", recorder.results[-1]["status"])
        self.assertIn("Short-cycle market stale", recorder.results[-1]["error_message"])

    async def test_insufficient_position_sell_does_not_count_as_executed(self):
        cfg = SimpleNamespace(id=13, account_id=2, copy_mode="RATIO")
        recorder = FakeRecorder()
        executor = SimpleNamespace(
            execute_trade=AsyncMock(return_value={"verified": True}),
        )
        measured = BridgeMetrics()

        with (
            patch.object(main, "rule_engine", FakeRuleEngine(cfg)),
            patch.object(main, "recorder", recorder),
            patch.object(main, "position_ledger", InsufficientLedger()),
            patch.object(main, "executor", executor),
            patch.object(main, "metrics", measured),
            patch.object(main, "_get_live_position_quantity", AsyncMock(return_value=Decimal("3"))),
            patch.object(main, "_short_cycle_market_stale_reason", MagicMock(return_value=None)),
        ):
            await main.handle_signal(self._signal())

        executor.execute_trade.assert_not_awaited()
        self.assertEqual("FAILED", recorder.results[-1]["status"])
        self.assertEqual("Insufficient position, skipped", recorder.results[-1]["error_message"])
        snapshot = measured.to_dict()
        self.assertEqual(0, snapshot["signals_executed"])
        self.assertEqual(0, snapshot["trades_sell_total"])

    async def test_buy_runs_shadow_risk_with_actual_amount_at_precheck_and_final(self):
        cfg = self._config()
        recorder = FakeRecorder()
        executor = SimpleNamespace(
            execute_trade=AsyncMock(
                return_value={"verified": True, "submitted_quote": 0.54}
            )
        )
        risk_check = AsyncMock(return_value=PortfolioRiskCheck(True, True, "d", "WOULD_BLOCK", "SHADOW"))
        risk_complete = AsyncMock()
        verify_buy = AsyncMock()
        measured = BridgeMetrics()
        signal = self._signal(side="BUY", size=4)
        signal._bridge_received_monotonic = main.time.perf_counter()

        with (
            patch.object(main, "rule_engine", FakeBuyRuleEngine(cfg)),
            patch.object(main, "recorder", recorder),
            patch.object(main, "position_ledger", None),
            patch.object(main, "executor", executor),
            patch.object(main, "_evaluate_portfolio_buy_risk", risk_check),
            patch.object(main, "_complete_portfolio_buy_risk", risk_complete),
            patch.object(main, "_verify_submitted_buy", verify_buy, create=True),
            patch.object(main, "metrics", measured),
            patch.object(main, "_tail_risk_low_price_buy_reason", return_value=None),
            patch.object(main, "_high_confidence_buy_reason", return_value=None),
            patch.object(main, "_generic_repeat_buy_reason", return_value=None),
            patch.object(main, "_near_expiry_news_buy_reason", return_value=None),
            patch.object(main, "_leader_event_activity_buy_reason", return_value=None),
            patch.object(main, "_short_cycle_price_band_buy_reason", return_value=None),
            patch.object(main, "_short_cycle_global_buy_reason", return_value=None),
            patch.object(main, "_short_cycle_daily_limit_buy_reason", return_value=None),
            patch.object(main, "_short_cycle_duplicate_buy_reason", return_value=None),
            patch.object(main, "_proportional_risk_small_buyback_reason", return_value=None),
            patch.object(main, "_short_cycle_market_stale_reason", return_value=None),
        ):
            await main.handle_signal(signal)
            await main._stop_verification_tasks()

        executor.execute_trade.assert_awaited_once()
        self.assertFalse(executor.execute_trade.await_args.kwargs["verify"])
        verify_buy.assert_awaited_once()
        latency = measured.to_dict()["latency_ms"]
        self.assertIn("trade_lock_wait_ms", latency)
        self.assertIn("buy_other_ui_submit_ms", latency)
        self.assertIn("buy_other_signal_to_submit_ms", latency)
        self.assertIn("buy_other_quote_drift", measured.to_dict()["measurements"])
        self.assertEqual(1, measured.last_mile_price_drift_would_block)
        self.assertEqual(risk_check.await_count, 2)
        self.assertEqual([call.kwargs["stage"] for call in risk_check.await_args_list], ["precheck", "final"])
        self.assertTrue(all(call.kwargs["amount"] == Decimal("1.25") for call in risk_check.await_args_list))
        risk_complete.assert_awaited_once_with(cfg, ANY, "SUCCESS")
        self.assertEqual(recorder.pending[-1]["raw_payload"]["copyTradingAccountId"], 2)
        self.assertEqual(recorder.pending[-1]["raw_payload"]["copyTradingId"], 7)
        self.assertEqual(recorder.pending[-1]["raw_payload"]["modelCandidateId"], "candidate-1")
        self.assertEqual(recorder.pending[-1]["raw_payload"]["portfolioRiskCorrelationId"], "bridge:0xTx:7")

    async def test_short_cycle_buy_skips_when_trade_lock_is_busy(self):
        cfg = self._config()
        recorder = FakeRecorder()
        executor = SimpleNamespace(
            execute_trade=AsyncMock(
                return_value={"verified": True, "submitted_quote": 0.54}
            )
        )
        risk_check = AsyncMock(return_value=PortfolioRiskCheck(True, True, "d", "ALLOW", "SHADOW"))
        risk_complete = AsyncMock()
        measured = BridgeMetrics()
        signal = self._signal(
            side="BUY",
            size=4,
            market_slug="xrp-updown-5m-1784274000",
        )
        signal._bridge_received_monotonic = main.time.perf_counter()

        await main._trade_lock.acquire()
        try:
            with (
                patch.object(main, "SHORT_CYCLE_TRADE_LOCK_TIMEOUT_SECONDS", 0.01),
                patch.object(main, "rule_engine", FakeBuyRuleEngine(cfg)),
                patch.object(main, "recorder", recorder),
                patch.object(main, "position_ledger", None),
                patch.object(main, "executor", executor),
                patch.object(main, "_evaluate_portfolio_buy_risk", risk_check),
                patch.object(main, "_complete_portfolio_buy_risk", risk_complete),
                patch.object(main, "metrics", measured),
                patch.object(main, "_tail_risk_low_price_buy_reason", return_value=None),
                patch.object(main, "_high_confidence_buy_reason", return_value=None),
                patch.object(main, "_generic_repeat_buy_reason", return_value=None),
                patch.object(main, "_near_expiry_news_buy_reason", return_value=None),
                patch.object(main, "_leader_event_activity_buy_reason", return_value=None),
                patch.object(main, "_short_cycle_price_band_buy_reason", return_value=None),
                patch.object(main, "_short_cycle_global_buy_reason", return_value=None),
                patch.object(main, "_short_cycle_daily_limit_buy_reason", return_value=None),
                patch.object(main, "_short_cycle_duplicate_buy_reason", return_value=None),
                patch.object(main, "_proportional_risk_small_buyback_reason", return_value=None),
                patch.object(main, "_short_cycle_market_stale_reason", return_value=None),
            ):
                await main.handle_signal(signal)
        finally:
            main._trade_lock.release()

        executor.execute_trade.assert_not_awaited()
        self.assertEqual("FAILED", recorder.updates[-1][1])
        self.assertIn("Short-cycle UI lane busy", recorder.updates[-1][2])
        latency = measured.to_dict()["latency_ms"]
        self.assertIn("trade_lock_wait_ms", latency)
        self.assertNotIn("buy_5m_signal_to_submit_ms", latency)
        self.assertEqual(1, measured.to_dict()["signals_trade_lock_timeout"])
        risk_complete.assert_awaited_once_with(cfg, ANY, "FAILED")

    async def test_model_candidate_id_is_forwarded_to_portfolio_risk(self):
        cfg = self._config()
        evaluate = AsyncMock(return_value=PortfolioRiskCheck(True, True, "d", "ALLOW", "SHADOW"))

        with patch.object(main.portfolio_risk_client, "evaluate_buy", evaluate):
            await main._evaluate_portfolio_buy_risk(
                cfg=cfg,
                signal=self._signal(side="BUY", market_slug="btc-updown-5m-1784184900"),
                amount=Decimal("1.25"),
                stage="precheck",
            )

        self.assertEqual(evaluate.await_args.args[0]["modelCandidateId"], "candidate-1")

    async def test_short_cycle_shadow_portfolio_risk_uses_short_timeout(self):
        cfg = self._config()
        evaluate = AsyncMock(return_value=PortfolioRiskCheck(True, True, "d", "ALLOW", "SHADOW"))

        with (
            patch.object(main.portfolio_risk_client, "evaluate_buy", evaluate),
            patch.object(main.portfolio_risk_client, "enforcement_mode", "SHADOW"),
        ):
            await main._evaluate_portfolio_buy_risk(
                cfg=cfg,
                signal=self._signal(side="BUY", market_slug="btc-updown-5m-1784184900"),
                amount=Decimal("1.25"),
                stage="precheck",
            )

        self.assertEqual(main.SHORT_CYCLE_PORTFOLIO_RISK_TIMEOUT_SECONDS, evaluate.await_args.kwargs["timeout_seconds"])
        self.assertEqual(0.35, evaluate.await_args.kwargs["timeout_seconds"])

    async def test_enforced_portfolio_risk_keeps_default_timeout(self):
        cfg = self._config()
        evaluate = AsyncMock(return_value=PortfolioRiskCheck(True, True, "d", "ALLOW", "ENFORCED"))

        with (
            patch.object(main.portfolio_risk_client, "evaluate_buy", evaluate),
            patch.object(main.portfolio_risk_client, "enforcement_mode", "ENFORCED"),
        ):
            await main._evaluate_portfolio_buy_risk(
                cfg=cfg,
                signal=self._signal(side="BUY"),
                amount=Decimal("1.25"),
                stage="precheck",
            )

        self.assertIsNone(evaluate.await_args.kwargs["timeout_seconds"])

    async def test_failed_signal_records_account_and_configuration_context(self):
        cfg = self._config()
        recorder = FakeRecorder()

        with (
            patch.object(main, "recorder", recorder),
            patch.object(main, "rule_engine", FakeBuyRuleEngine(cfg)),
        ):
            await main._record_failed_signal(
                signal=self._signal(side="BUY"),
                cfg=cfg,
                side="BUY",
                quantity=Decimal("1"),
                price=Decimal("0.5"),
                amount=Decimal("0.5"),
                reason="BUY skipped: test",
            )

        payload = recorder.results[-1]["raw_payload"]
        self.assertEqual(2, payload["copyTradingAccountId"])
        self.assertEqual(7, payload["copyTradingId"])
        self.assertEqual("FAILED", recorder.results[-1]["status"])
        self.assertEqual("BUY skipped: test", recorder.results[-1]["error_message"])

    async def test_live_position_quantity_does_not_match_other_yes_position(self):
        executor = SimpleNamespace(
            is_ready=MagicMock(return_value=True),
            is_logged_in=MagicMock(return_value=True),
            fetch_portfolio_positions=AsyncMock(return_value={
                "positions": [
                    {
                        "marketTitle": "Will MrBeast hit 508 million subscribers by July 31?",
                        "side": "Yes",
                        "quantity": 1.02,
                    },
                ],
            }),
        )

        with patch.object(main, "executor", executor):
            quantity = await main._get_live_position_quantity(
                market_id="0xaf08e614fbd4b5b7d8b5b1f2a0c7d9e1f4a6b8c0",
                market_title="Will there be no change in Fed interest rates after the July 2026 meeting?",
                outcome="Yes",
            )

        self.assertEqual(quantity, Decimal("0"))

    async def test_live_position_quantity_rejects_mismatched_condition_id_even_with_same_title(self):
        executor = SimpleNamespace(
            is_ready=MagicMock(return_value=True),
            is_logged_in=MagicMock(return_value=True),
            fetch_portfolio_positions=AsyncMock(return_value={
                "positions": [
                    {
                        "conditionId": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
                        "marketTitle": "Will there be no change in Fed interest rates after the July 2026 meeting?",
                        "side": "Yes",
                        "quantity": 1.02,
                    },
                ],
            }),
        )

        with patch.object(main, "executor", executor):
            quantity = await main._get_live_position_quantity(
                market_id="0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
                market_title="Will there be no change in Fed interest rates after the July 2026 meeting?",
                outcome="Yes",
            )

        self.assertEqual(quantity, Decimal("0"))


if __name__ == "__main__":
    unittest.main()
