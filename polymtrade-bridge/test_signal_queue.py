import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

import main
from bridge_metrics import BridgeMetrics


class TestSignalQueue(unittest.IsolatedAsyncioTestCase):
    def signal(self):
        return main.LeaderTradeSignal(
            timestamp=1,
            leaderAddress="0xleader",
            transactionHash="0xtx",
            conditionId="condition",
            marketSlug="btc-updown-5m-1",
            side="BUY",
            outcome="Up",
            price=0.5,
            size=1.0,
        )

    async def test_receive_signal_returns_before_slow_handler_finishes(self):
        queue = asyncio.Queue(maxsize=2)
        handler_started = asyncio.Event()
        release_handler = asyncio.Event()

        async def slow_handler(signal):
            handler_started.set()
            await release_handler.wait()

        worker = asyncio.create_task(main._signal_worker(0, queue))
        measured = BridgeMetrics()
        try:
            with (
                patch.object(main, "executor", SimpleNamespace(is_ready=lambda: True)),
                patch.object(main, "_signal_queue", queue),
                patch.object(main, "_accepting_signals", True),
                patch.object(main, "handle_signal", AsyncMock(side_effect=slow_handler)),
                patch.object(main, "metrics", measured),
            ):
                result = await asyncio.wait_for(main.receive_signal(self.signal()), timeout=0.05)
                await asyncio.wait_for(handler_started.wait(), timeout=0.05)

                self.assertEqual("accepted", result["status"])
                self.assertLessEqual(result["queue_depth"], 1)

                release_handler.set()
                await asyncio.wait_for(queue.join(), timeout=0.1)
                latency = measured.to_dict()["latency_ms"]
                self.assertIn("webhook_accept_ms", latency)
                self.assertIn("signal_queue_wait_ms", latency)
        finally:
            worker.cancel()
            with self.assertRaises(asyncio.CancelledError):
                await worker

    async def test_receive_signal_rejects_when_queue_is_full(self):
        queue = asyncio.Queue(maxsize=1)
        queue.put_nowait(self.signal())

        with (
            patch.object(main, "executor", SimpleNamespace(is_ready=lambda: True)),
            patch.object(main, "_signal_queue", queue),
            patch.object(main, "_accepting_signals", True),
        ):
            with self.assertRaises(HTTPException) as raised:
                await main.receive_signal(self.signal())

        self.assertEqual(503, raised.exception.status_code)
        self.assertEqual("1", raised.exception.headers["Retry-After"])

    async def test_receive_signal_rejects_while_admission_is_draining(self):
        with (
            patch.object(main, "executor", SimpleNamespace(is_ready=lambda: True)),
            patch.object(main, "_accepting_signals", False),
            patch.object(main, "_signal_drain_reason", "planned_restart"),
        ):
            with self.assertRaises(HTTPException) as raised:
                await main.receive_signal(self.signal())

        self.assertEqual(503, raised.exception.status_code)
        self.assertEqual("10", raised.exception.headers["Retry-After"])
        self.assertEqual("planned_restart", raised.exception.detail["reason"])

    async def test_admin_drain_is_local_only_and_closes_signal_admission(self):
        request = SimpleNamespace(client=SimpleNamespace(host="127.0.0.1"), headers={})

        with (
            patch.dict(main.os.environ, {"BRIDGE_ADMIN_SECRET": ""}, clear=False),
            patch.object(main, "_accepting_signals", True),
            patch.object(main, "_signal_queue", asyncio.Queue()),
        ):
            result = await main.admin_drain(request, reason="planned_restart")

        self.assertEqual("draining", result["status"])
        self.assertFalse(result["accepting_signals"])
        self.assertEqual("planned_restart", result["drain_reason"])

    async def test_admin_drain_rejects_remote_hosts(self):
        request = SimpleNamespace(client=SimpleNamespace(host="10.0.0.5"), headers={})

        with self.assertRaises(HTTPException) as raised:
            await main.admin_drain(request)

        self.assertEqual(403, raised.exception.status_code)


if __name__ == "__main__":
    unittest.main()
