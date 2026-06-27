#!/usr/bin/env python3
"""Tests for proportional-risk Bridge execution guards."""

import sys
import unittest
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent))

import main
from copy_trading_config import COPY_MODE_PROPORTIONAL_RISK


class FakeRecorder:
    def __init__(self):
        self.pending = []
        self.updates = []
        self.leader_sell_size = Decimal("0")
        self.success_sell_size = Decimal("0")

    def exists(self, external_trade_id):
        return False

    def record_pending(self, **kwargs):
        self.pending.append(kwargs)
        return len(self.pending)

    def update_status(self, record_id, status, error_message=None):
        self.updates.append((record_id, status, error_message))

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


class FakeLedger:
    def get_net_quantity(self, **kwargs):
        return Decimal("0")

    def has_sufficient_position(self, **kwargs):
        raise AssertionError("proportional-risk SELL should not use stale ledger pre-check")


class TestProportionalRiskBridge(unittest.IsolatedAsyncioTestCase):
    def _config(self):
        return SimpleNamespace(
            id=7,
            copy_mode=COPY_MODE_PROPORTIONAL_RISK,
        )

    def _signal(self, side="SELL", size=4):
        return main.LeaderTradeSignal(
            timestamp=1,
            leaderAddress="0xLeader",
            transactionHash="0xTx",
            conditionId="condition-1",
            marketSlug="market-slug",
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

        with (
            patch.object(main, "rule_engine", FakeRuleEngine(cfg)),
            patch.object(main, "recorder", recorder),
            patch.object(main, "position_ledger", FakeLedger()),
            patch.object(main, "executor", executor),
            patch.object(main, "_get_live_position_quantity", AsyncMock(return_value=Decimal("3"))),
            patch.object(main, "_wait_for_live_position_decrease", AsyncMock(return_value=Decimal("1"))),
            patch.object(main, "_short_cycle_market_stale_reason", MagicMock(return_value=None)),
        ):
            await main.handle_signal(self._signal())

        executor.execute_trade.assert_awaited_once()
        _, kwargs = executor.execute_trade.await_args
        self.assertEqual(kwargs["side"], "SELL")
        self.assertEqual(kwargs["size_shares"], 2.0)
        self.assertEqual(recorder.updates[-1][1], "SUCCESS")


if __name__ == "__main__":
    unittest.main()
