#!/usr/bin/env python3
"""Regression tests for on-chain trade confirmation and market availability."""

import unittest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

import main

from chain_trade_verifier import (
    AVAILABILITY_ACTIVE,
    AVAILABILITY_CLOSED,
    AVAILABILITY_NOT_FOUND,
    AVAILABILITY_UNKNOWN,
    fetch_wallet_trades,
    find_matching_fill,
    get_market_availability,
    reset_availability_cache,
)

CONDITION_ID = "0x" + "ab" * 32
WALLET = "0x4fbcc39221af92397c82b9ccbf88fd0a9695a244"


def _trade(**overrides):
    trade = {
        "condition_id": CONDITION_ID,
        "side": "BUY",
        "outcome": "Yes",
        "price": 0.61,
        "size": 1.5,
        "timestamp": 1_800_000_000,
        "transaction_hash": "0xtx",
    }
    trade.update(overrides)
    return trade


class _FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _fake_client(payload, status_code=200):
    client = AsyncMock(spec=httpx.AsyncClient)
    client.get = AsyncMock(return_value=_FakeResponse(status_code, payload))
    client.is_closed = False
    return client


class TestFindMatchingFill(unittest.TestCase):
    def test_matches_condition_side_outcome_within_window(self):
        fill = find_matching_fill(
            [_trade()],
            condition_id=CONDITION_ID,
            side="BUY",
            outcome="Yes",
            since_epoch_s=1_800_000_000,
        )
        self.assertIsNotNone(fill)
        self.assertEqual("0xtx", fill["transaction_hash"])

    def test_skew_allows_fill_slightly_before_since(self):
        fill = find_matching_fill(
            [_trade(timestamp=1_800_000_000 - 100)],
            condition_id=CONDITION_ID,
            side="BUY",
            outcome="Yes",
            since_epoch_s=1_800_000_000,
            skew_s=180,
        )
        self.assertIsNotNone(fill)

    def test_rejects_fill_older_than_skew_window(self):
        fill = find_matching_fill(
            [_trade(timestamp=1_800_000_000 - 400)],
            condition_id=CONDITION_ID,
            side="BUY",
            outcome="Yes",
            since_epoch_s=1_800_000_000,
        )
        self.assertIsNone(fill)

    def test_rejects_wrong_side_outcome_and_market(self):
        trades = [
            _trade(side="SELL"),
            _trade(outcome="No"),
            _trade(condition_id="0x" + "cd" * 32),
        ]
        for trade in trades:
            self.assertIsNone(
                find_matching_fill(
                    [trade],
                    condition_id=CONDITION_ID,
                    side="BUY",
                    outcome="Yes",
                    since_epoch_s=1_800_000_000,
                )
            )

    def test_returns_earliest_matching_fill(self):
        later = _trade(timestamp=1_800_000_100, transaction_hash="0xlater")
        earlier = _trade(timestamp=1_800_000_010, transaction_hash="0xearlier")
        fill = find_matching_fill(
            [later, earlier],
            condition_id=CONDITION_ID,
            side="BUY",
            outcome="Yes",
            since_epoch_s=1_800_000_000,
        )
        self.assertEqual("0xearlier", fill["transaction_hash"])

    def test_outcome_none_matches_any_outcome(self):
        fill = find_matching_fill(
            [_trade(outcome="No")],
            condition_id=CONDITION_ID,
            side="BUY",
            outcome=None,
            since_epoch_s=1_800_000_000,
        )
        self.assertIsNotNone(fill)


class TestFetchWalletTrades(unittest.IsolatedAsyncioTestCase):
    async def test_unwraps_data_list(self):
        client = _fake_client({"data": [_trade()], "pagination": {}})
        trades = await fetch_wallet_trades(WALLET, client=client)
        self.assertEqual(1, len(trades))
        client.get.assert_awaited_once()

    async def test_non_200_returns_empty(self):
        client = _fake_client({}, status_code=500)
        self.assertEqual([], await fetch_wallet_trades(WALLET, client=client))

    async def test_exception_returns_empty(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
        self.assertEqual([], await fetch_wallet_trades(WALLET, client=client))

    async def test_empty_wallet_returns_empty(self):
        self.assertEqual([], await fetch_wallet_trades(""))


class TestMarketAvailability(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        reset_availability_cache()

    async def test_active_market(self):
        client = _fake_client([{"conditionId": CONDITION_ID, "closed": False}])
        status = await get_market_availability(CONDITION_ID, client=client)
        self.assertEqual(AVAILABILITY_ACTIVE, status)

    async def test_closed_market(self):
        client = _fake_client([{"conditionId": CONDITION_ID, "closed": True}])
        status = await get_market_availability(CONDITION_ID, client=client)
        self.assertEqual(AVAILABILITY_CLOSED, status)

    async def test_not_found_market(self):
        client = _fake_client([])
        status = await get_market_availability(CONDITION_ID, client=client)
        self.assertEqual(AVAILABILITY_NOT_FOUND, status)

    async def test_unknown_on_error(self):
        client = AsyncMock(spec=httpx.AsyncClient)
        client.get = AsyncMock(side_effect=httpx.ConnectError("down"))
        status = await get_market_availability(CONDITION_ID, client=client)
        self.assertEqual(AVAILABILITY_UNKNOWN, status)

    async def test_cache_avoids_second_fetch(self):
        client = _fake_client([{"conditionId": CONDITION_ID, "closed": False}])
        await get_market_availability(CONDITION_ID, client=client)
        await get_market_availability(CONDITION_ID, client=client)
        self.assertEqual(1, client.get.await_count)


class TestRecordPreSubmitFailure(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        reset_availability_cache()

    def _patch_recorder(self, updates):
        async def record(method, *args, **kwargs):
            updates.append((method, args, kwargs))
            return None

        return (
            patch.object(main, "recorder", MagicMock()),
            patch.object(main, "_recorder_call", record),
        )

    async def test_not_found_market_downgrades_to_skipped(self):
        updates = []
        rec_patch, call_patch = self._patch_recorder(updates)
        with rec_patch, call_patch, patch.object(
            main, "get_market_availability", AsyncMock(return_value=AVAILABILITY_NOT_FOUND)
        ), patch.object(main, "MARKET_AVAILABILITY_CHECK_ENABLED", True):
            status = await main._record_pre_submit_failure(
                7, "Target market content never appeared for X", CONDITION_ID
            )
        self.assertEqual("SKIPPED", status)
        self.assertEqual("update_status", updates[0][0])
        self.assertEqual("SKIPPED", updates[0][1][1])
        self.assertIn("not listed on Polymarket", updates[0][1][2])

    async def test_closed_market_downgrades_to_skipped(self):
        updates = []
        rec_patch, call_patch = self._patch_recorder(updates)
        with rec_patch, call_patch, patch.object(
            main, "get_market_availability", AsyncMock(return_value=AVAILABILITY_CLOSED)
        ), patch.object(main, "MARKET_AVAILABILITY_CHECK_ENABLED", True):
            status = await main._record_pre_submit_failure(
                7, "Could not click buy button", CONDITION_ID
            )
        self.assertEqual("SKIPPED", status)
        self.assertIn("Market closed", updates[0][1][2])

    async def test_active_market_keeps_failed(self):
        updates = []
        rec_patch, call_patch = self._patch_recorder(updates)
        with rec_patch, call_patch, patch.object(
            main, "get_market_availability", AsyncMock(return_value=AVAILABILITY_ACTIVE)
        ), patch.object(main, "MARKET_AVAILABILITY_CHECK_ENABLED", True):
            status = await main._record_pre_submit_failure(
                7, "Target market content never appeared for X", CONDITION_ID
            )
        self.assertEqual("FAILED", status)
        self.assertEqual("FAILED", updates[0][1][1])

    async def test_non_render_failure_skips_availability_lookup(self):
        updates = []
        rec_patch, call_patch = self._patch_recorder(updates)
        availability = AsyncMock(return_value=AVAILABILITY_NOT_FOUND)
        with rec_patch, call_patch, patch.object(
            main, "get_market_availability", availability
        ), patch.object(main, "MARKET_AVAILABILITY_CHECK_ENABLED", True):
            status = await main._record_pre_submit_failure(
                7, "Live portfolio insufficient position, skipped", CONDITION_ID
            )
        self.assertEqual("FAILED", status)
        availability.assert_not_awaited()

    async def test_non_condition_id_skips_availability_lookup(self):
        updates = []
        rec_patch, call_patch = self._patch_recorder(updates)
        availability = AsyncMock(return_value=AVAILABILITY_NOT_FOUND)
        with rec_patch, call_patch, patch.object(
            main, "get_market_availability", availability
        ), patch.object(main, "MARKET_AVAILABILITY_CHECK_ENABLED", True):
            status = await main._record_pre_submit_failure(
                7, "Target market content never appeared for X", "some-slug"
            )
        self.assertEqual("FAILED", status)
        availability.assert_not_awaited()


class TestOnchainVerificationFallback(unittest.IsolatedAsyncioTestCase):
    def _patch_common(self, updates, trades):
        async def record(method, *args, **kwargs):
            updates.append((method, args, kwargs))
            return None

        executor = MagicMock()
        executor.cached_wallet_address = WALLET
        return (
            patch.object(main, "recorder", MagicMock()),
            patch.object(main, "_recorder_call", record),
            patch.object(main, "executor", executor),
            patch.object(
                main, "fetch_wallet_trades", AsyncMock(return_value=trades)
            ),
            patch.object(main, "CHAIN_VERIFY_ENABLED", True),
        )

    async def test_buy_confirmed_by_chain_when_portfolio_check_fails(self):
        updates = []
        patches = self._patch_common(updates, [_trade()])
        wait = AsyncMock(side_effect=RuntimeError("Live portfolio unavailable"))
        with patches[0], patches[1], patches[2], patches[3], patches[4], patch.object(
            main, "_wait_for_live_position_increase", wait
        ):
            await main._verify_submitted_buy(
                record_id=9,
                market_id=CONDITION_ID,
                market_title="Market",
                outcome="Yes",
                before_quantity=Decimal("0"),
            )
        statuses = [u for u in updates if u[0] == "update_status"]
        self.assertEqual(1, len(statuses))
        self.assertEqual("SUCCESS", statuses[0][1][1])

    async def test_buy_unverified_when_no_chain_fill(self):
        updates = []
        patches = self._patch_common(updates, [])
        wait = AsyncMock(side_effect=RuntimeError("no increase"))
        with patches[0], patches[1], patches[2], patches[3], patches[4], patch.object(
            main, "_wait_for_live_position_increase", wait
        ):
            await main._verify_submitted_buy(
                record_id=9,
                market_id=CONDITION_ID,
                market_title="Market",
                outcome="Yes",
                before_quantity=Decimal("0"),
            )
        statuses = [u for u in updates if u[0] == "update_status"]
        self.assertEqual(1, len(statuses))
        self.assertEqual("SUBMITTED_UNVERIFIED", statuses[0][1][1])

    async def test_sell_confirmed_by_chain_when_portfolio_check_fails(self):
        updates = []
        patches = self._patch_common(updates, [_trade(side="SELL")])
        wait = AsyncMock(side_effect=RuntimeError("Live portfolio unavailable"))
        with patches[0], patches[1], patches[2], patches[3], patches[4], patch.object(
            main, "_wait_for_live_position_decrease", wait
        ):
            await main._verify_submitted_sell(
                record_id=9,
                market_id=CONDITION_ID,
                market_title="Market",
                outcome="Yes",
                before_quantity=Decimal("2"),
            )
        statuses = [u for u in updates if u[0] == "update_status"]
        self.assertEqual("SUCCESS", statuses[0][1][1])

    async def test_portfolio_success_does_not_touch_chain(self):
        updates = []
        patches = self._patch_common(updates, [_trade()])
        fetch_mock = patches[3]
        with patches[0], patches[1], patches[2], fetch_mock, patches[4], patch.object(
            main,
            "_wait_for_live_position_increase",
            AsyncMock(return_value=Decimal("2")),
        ):
            await main._verify_submitted_buy(
                record_id=9,
                market_id=CONDITION_ID,
                market_title="Market",
                outcome="Yes",
                before_quantity=Decimal("0"),
            )
        statuses = [u for u in updates if u[0] == "update_status"]
        self.assertEqual("SUCCESS", statuses[0][1][1])


class TestReconcileUnverifiedTrades(unittest.IsolatedAsyncioTestCase):
    async def test_matched_records_flip_to_success(self):
        updates = []

        async def record(method, *args, **kwargs):
            updates.append((method, args, kwargs))
            if method == "list_records_by_status_since":
                return [
                    {
                        "id": 1,
                        "market_id": CONDITION_ID,
                        "side": "BUY",
                        "outcome": "Yes",
                        "created_at": 1_800_000_000_000,
                    },
                    {
                        "id": 2,
                        "market_id": "0x" + "ff" * 32,
                        "side": "BUY",
                        "outcome": "Yes",
                        "created_at": 1_800_000_000_000,
                    },
                ]
            return None

        executor = MagicMock()
        executor.cached_wallet_address = WALLET
        with (
            patch.object(main, "recorder", MagicMock()),
            patch.object(main, "_recorder_call", record),
            patch.object(main, "executor", executor),
            patch.object(
                main, "fetch_wallet_trades", AsyncMock(return_value=[_trade()])
            ),
            patch.object(main, "CHAIN_VERIFY_ENABLED", True),
        ):
            confirmed = await main._reconcile_unverified_trades_once()

        self.assertEqual(1, confirmed)
        flips = [u for u in updates if u[0] == "update_status"]
        self.assertEqual(1, len(flips))
        self.assertEqual(1, flips[0][1][0])
        self.assertEqual("SUCCESS", flips[0][1][1])
        self.assertIn("on-chain reconciliation", flips[0][1][2])

    async def test_no_wallet_skips_reconciliation(self):
        executor = MagicMock()
        executor.cached_wallet_address = None
        with (
            patch.object(main, "recorder", MagicMock()),
            patch.object(main, "executor", executor),
            patch.object(main, "CHAIN_VERIFY_ENABLED", True),
        ):
            self.assertEqual(0, await main._reconcile_unverified_trades_once())


if __name__ == "__main__":
    unittest.main()
