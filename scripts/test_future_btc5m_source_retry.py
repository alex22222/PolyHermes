import asyncio
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

from future_btc5m_assistant import Assistant, GAMMA, GEOBLOCK
from future_btc5m_bridge import FutureBridge
from test_future_btc5m_strategy import S, browser15, gamma15, hour_quote


class SourceRetryTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name)
        self.clock = S + 140
        self.calls = []
        self.failures = [RuntimeError("HTTP_SOURCE_CONNECTION_RESET")]
        self.quote = lambda: {"price": 83001, "observed_at": self.clock, "received_at": self.clock}
        self.assistant = Assistant(self.path, lambda: self.quote(), lambda: self.clock)
        self.assistant.series_fn = lambda: "15m"
        self.assistant.weekend_only = False
        self.assistant.hour_quote_fn = lambda: hour_quote(self.clock)
        self.real_sleep = asyncio.sleep
        self.sleep_patch = patch("future_btc5m_assistant.asyncio.sleep", new=self.delay)
        self.sleep_patch.start()
        self.addCleanup(self.sleep_patch.stop)

    async def delay(self, seconds):
        self.clock += seconds
        await self.real_sleep(0)

    async def http(self, url):
        self.calls.append(url)
        if url.startswith(GAMMA):
            if self.failures:
                raise self.failures.pop(0)
            return gamma15(S)
        return {"blocked": False} if url == GEOBLOCK else {"openPrice": 83000}

    def gamma_calls(self):
        return [url for url in self.calls if url.startswith(GAMMA)]

    async def test_reset_recovers_in_the_same_claim_and_creates_only_one_15m_ticket(self):
        bridge = FutureBridge(self.path / "bridge", self.assistant.status, lambda: self.clock)
        bridge.set_strategy("btc15m_counter_1h")
        bridge.control(True)
        self.clock = S + 151
        status = await self.assistant.poll(self.http)
        self.assertIsNotNone(status["signal"], "a transient Gamma reset must not consume the whole entry")
        self.assertEqual({}, status["source_errors"])
        self.assertEqual(2, len(self.gamma_calls()))
        self.assertEqual(4, len(self.calls), "retry only the failed read")
        bridge.report_preflight(browser15(self.clock))
        bridge.observe()
        bridge.observe()
        self.assertEqual(1, len(bridge.preparations))
        self.assertEqual("PENDING", next(iter(bridge.preparations.values()))["state"])
        self.assertEqual(1, len((self.path / "rounds.jsonl").read_text().splitlines()))
        await self.assistant.poll(self.http)
        restarted = Assistant(self.path, self.quote, lambda: self.clock)
        restarted.series_fn = lambda: "15m"
        restarted.weekend_only = False
        self.assertEqual("ROUND_ALREADY_PROCESSED", (await restarted.poll(self.http))["reason"])
        self.assertEqual(4, len(self.calls), "neither polling nor restarting may replay the round")

    async def test_exhausted_retries_are_bounded_and_keep_the_actual_error(self):
        self.failures *= 4
        self.clock = S + 151
        status = await self.assistant.poll(self.http)
        self.assertEqual(3, len(self.gamma_calls()))
        self.assertEqual("SOURCE_REQUEST_FAILED", status["reason"])
        self.assertEqual({"GAMMA": "HTTP_SOURCE_CONNECTION_RESET"}, status["source_errors"])
        self.assertIsNone(status["signal"])
        self.assertEqual(1, len((self.path / "rounds.jsonl").read_text().splitlines()))
        await self.assistant.poll(self.http)
        self.assertEqual(3, len(self.gamma_calls()))

    async def test_retry_diagnostics_are_visible_while_waiting_and_after_recovery(self):
        observed = []

        async def inspecting_delay(seconds):
            observed.append(self.assistant.status())
            await self.delay(seconds)

        self.clock = S + 151
        with patch("future_btc5m_assistant.asyncio.sleep", new=inspecting_delay):
            status = await self.assistant.poll(self.http)
        self.assertEqual("SOURCE_REQUEST_RETRYING", observed[0]["reason"])
        self.assertEqual({"GAMMA": "HTTP_SOURCE_CONNECTION_RESET"}, observed[0]["source_errors"])
        gamma_reads = [read for read in status["source_reads"] if read["source"] == "GAMMA"]
        self.assertEqual(["HTTP_SOURCE_CONNECTION_RESET", None], [read["error"] for read in gamma_reads])

    async def test_stop_or_strategy_change_during_backoff_prevents_another_read(self):
        for changed in ("stop", "strategy"):
            with self.subTest(changed=changed):
                self.clock = S + 140
                assistant = Assistant(self.path / changed, self.quote, lambda: self.clock)
                assistant.series_fn = lambda: "15m"
                assistant.weekend_only = False
                self.failures = [RuntimeError("HTTP_SOURCE_CONNECTION_RESET")]
                self.calls.clear()

                async def changed_delay(seconds):
                    if changed == "stop":
                        assistant.state_dir.mkdir(exist_ok=True)
                        (assistant.state_dir / "STOP").touch()
                    else:
                        assistant.series_fn = lambda: "5m"
                    await self.delay(seconds)

                self.clock = S + 151
                with patch("future_btc5m_assistant.asyncio.sleep", new=changed_delay):
                    status = await assistant.poll(self.http)
                self.assertEqual(1, len(self.gamma_calls()))
                self.assertIsNone(status["signal"])
                self.assertIn(status["reason"], ("STOP_FILE_PRESENT", "ENTRY_WINDOW_EXPIRED_DURING_READ"))

    async def test_no_retry_can_start_at_or_after_the_170_second_deadline(self):
        self.clock = S + 169.75
        status = await self.assistant.poll(self.http)
        self.assertEqual(1, len(self.gamma_calls()))
        self.assertIsNone(status["signal"])

    async def test_a_hanging_read_cannot_extend_the_entry_window(self):
        async def hanging_http(url):
            if url.startswith(GAMMA):
                await asyncio.Future()
            return await self.http(url)

        self.clock = S + 169.98
        status = await asyncio.wait_for(self.assistant.poll(hanging_http), timeout=0.5)
        self.assertEqual("ENTRY_WINDOW_EXPIRED_DURING_READ", status["reason"])
        self.assertIsNone(status["signal"])

    async def test_only_the_timed_out_opening_price_is_retried(self):
        self.failures = []

        async def timeout_http(url):
            value = await self.http(url)
            if "crypto-price" in url and self.calls.count(url) == 1:
                raise TimeoutError("private transport detail")
            return value

        self.clock = S + 151
        status = await self.assistant.poll(timeout_http)
        self.assertIsNotNone(status["signal"])
        self.assertEqual(1, len(self.gamma_calls()))
        self.assertEqual(4, len(self.calls))
        self.assertNotIn("private", str(status))

    async def test_concurrent_poll_cannot_start_another_read_for_the_same_round(self):
        entered, release = asyncio.Event(), asyncio.Event()

        async def held_http(url):
            if url.startswith(GAMMA):
                entered.set()
                await release.wait()
            return await self.http(url)

        self.clock = S + 151
        task = asyncio.create_task(self.assistant.poll(held_http))
        await entered.wait()
        await self.assistant.poll(self.http)
        release.set()
        status = await task
        self.assertIsNotNone(status["signal"])
        self.assertEqual(4, len(self.calls))
        self.assertEqual(1, len((self.path / "rounds.jsonl").read_text().splitlines()))

    async def test_recovery_still_rejects_a_stale_chainlink_price(self):
        self.clock = S + 151
        self.quote = lambda: {"price": 83001, "observed_at": S + 145, "received_at": S + 145}
        status = await self.assistant.poll(self.http)
        self.assertEqual(2, len(self.gamma_calls()))
        self.assertEqual("CHAINLINK_PRICE_STALE_OR_FUTURE", status["reason"])
        self.assertIsNone(status["signal"])

    async def test_http_denials_certificate_errors_and_invalid_market_are_not_retried(self):
        for code in ("HTTP_SOURCE_UNAVAILABLE", "HTTP_SOURCE_TLS_ERROR"):
            with self.subTest(code=code):
                self.clock = S + 140
                assistant = Assistant(self.path / code, self.quote, lambda: self.clock)
                assistant.series_fn = lambda: "15m"
                assistant.weekend_only = False
                self.clock = S + 151
                self.failures = [RuntimeError(code)]
                self.calls.clear()
                status = await assistant.poll(self.http)
                self.assertEqual(1, len(self.gamma_calls()))
                self.assertIsNone(status["signal"])
        self.clock = S + 151
        self.failures = []
        self.calls.clear()

        async def wrong_market(url):
            value = await self.http(url)
            if url.startswith(GAMMA):
                value[0]["markets"][0]["acceptingOrders"] = False
            return value

        status = await self.assistant.poll(wrong_market)
        self.assertEqual("WRONG_OR_INACTIVE_MARKET", status["reason"])
        self.assertEqual(1, len(self.gamma_calls()))


if __name__ == "__main__":
    unittest.main()
