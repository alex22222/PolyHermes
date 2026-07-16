import asyncio
import unittest
from contextlib import asynccontextmanager
from unittest.mock import AsyncMock, patch

from polymtrade_executor import PolymtradeExecutor


class TestMetadataCache(unittest.IsolatedAsyncioTestCase):
    async def test_short_cycle_slug_resolves_without_network_probe(self):
        executor = PolymtradeExecutor()
        market_slug = "btc-updown-15m-1784131200"

        result = await executor._resolve_event_uncached(market_slug, "condition")

        self.assertEqual(("", market_slug), result)

    async def test_http_client_is_reused_and_closed(self):
        executor = PolymtradeExecutor()
        executor.proxy = None

        async with executor._http_client_context() as first:
            async with executor._http_client_context() as second:
                self.assertIs(first, second)

        await executor._close_http_client()
        self.assertTrue(first.is_closed)

    async def test_concurrent_position_enrichment_is_singleflight_and_cached(self):
        executor = PolymtradeExecutor()
        position = {"marketTitle": "BTC Up or Down"}
        metadata = {
            "conditionId": "condition",
            "marketSlug": "btc-updown-15m-1",
            "eventSlug": "btc-updown-15m-1",
        }
        resolver = AsyncMock(return_value=metadata)

        with patch.object(executor, "_resolve_position_metadata", resolver):
            first, second = await asyncio.gather(
                executor._enrich_position(position),
                executor._enrich_position(position),
            )
            third = await executor._enrich_position(position)

        self.assertEqual(metadata, first)
        self.assertEqual(metadata, second)
        self.assertEqual(metadata, third)
        self.assertEqual(1, resolver.await_count)

    async def test_event_resolution_is_singleflight_and_cached(self):
        executor = PolymtradeExecutor()
        resolver = AsyncMock(return_value=("123", "btc-updown-15m-1"))

        with patch.object(executor, "_resolve_event_uncached", resolver):
            first, second = await asyncio.gather(
                executor._resolve_event("btc-updown-15m-1", "condition"),
                executor._resolve_event("btc-updown-15m-1", "condition"),
            )
            third = await executor._resolve_event("btc-updown-15m-1", "condition")

        self.assertEqual(("123", "btc-updown-15m-1"), first)
        self.assertEqual(first, second)
        self.assertEqual(first, third)
        self.assertEqual(1, resolver.await_count)


if __name__ == "__main__":
    unittest.main()
