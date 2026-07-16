import asyncio
import unittest
from unittest.mock import patch

import main


class BlockingRecorder:
    def exists(self, external_trade_id: str) -> bool:
        import time

        time.sleep(0.1)
        return external_trade_id == "existing"


class TestAsyncRecorder(unittest.IsolatedAsyncioTestCase):
    async def test_recorder_call_does_not_block_event_loop(self):
        with patch.object(main, "recorder", BlockingRecorder()):
            call = asyncio.create_task(main._recorder_call("exists", "existing"))

            done, _ = await asyncio.wait({call}, timeout=0.02)

            self.assertFalse(done)
            self.assertTrue(await call)


if __name__ == "__main__":
    unittest.main()
