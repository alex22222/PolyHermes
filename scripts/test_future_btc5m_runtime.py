import json
import sys
import unittest
from pathlib import Path

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosedError, InvalidStatus

sys.path.insert(0, str(Path(__file__).parent))
from future_btc5m_runtime import start_runtime_server


class RuntimeServerTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.server = await start_runtime_server(("127.0.0.1", 0))
        self.port = self.server.sockets[0].getsockname()[1]
        self.url = f"ws://127.0.0.1:{self.port}/runtime"
        self.origin = "chrome-extension://" + "a" * 32

    async def asyncTearDown(self):
        self.server.close()
        await self.server.wait_closed()

    async def test_pushes_only_fresh_clock_ticks_without_a_client_poll(self):
        async with connect(self.url, origin=self.origin, proxy=None) as socket:
            first = json.loads(await socket.recv())
            second = json.loads(await socket.recv())
        self.assertEqual({"type", "serverTime"}, set(first))
        self.assertEqual("FUTURE_BTC5M_TICK", first["type"])
        self.assertGreaterEqual(second["serverTime"] - first["serverTime"], 0.45)
        self.assertLess(second["serverTime"] - first["serverTime"], 1)

    async def test_origin_path_and_host_are_checked_before_ticks(self):
        for origin in (None, "https://future.news", "chrome-extension://" + "z" * 32):
            with self.subTest(origin=origin), self.assertRaises(InvalidStatus):
                async with connect(self.url, origin=origin, proxy=None):
                    self.fail("untrusted client connected")
        for path in ("/runtime?submit=1", "/submit", "/runtime/"):
            with self.subTest(path=path), self.assertRaises(InvalidStatus):
                async with connect(self.url.replace("/runtime", path), origin=self.origin, proxy=None):
                    self.fail("wrong path connected")
        with self.assertRaises(InvalidStatus):
            async with connect(self.url, origin=self.origin, proxy=None, additional_headers={"Host": "attacker.invalid"}):
                self.fail("duplicate host connected")

    async def test_any_client_payload_is_closed_and_never_becomes_a_control(self):
        async with connect(self.url, origin=self.origin, proxy=None) as socket:
            await socket.recv()
            await socket.send('{"enabled":true,"amountUsd":1}')
            with self.assertRaises(ConnectionClosedError):
                await socket.recv()
            self.assertEqual(1008, socket.close_code)

    async def test_non_loopback_listener_is_refused(self):
        with self.assertRaisesRegex(ValueError, "LOOPBACK"):
            await start_runtime_server(("0.0.0.0", 8767))


if __name__ == "__main__":
    unittest.main()
