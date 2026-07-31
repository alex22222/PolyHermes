import unittest
import time
from unittest.mock import AsyncMock, call, patch

from polymtrade_executor import LastMilePriceDriftError, PolymtradeExecutor


class TestNavigationWaits(unittest.IsolatedAsyncioTestCase):
    def test_extracts_probability_from_outcome_button_label(self):
        self.assertEqual(0.66, PolymtradeExecutor._extract_quoted_price("Up 66¢"))
        self.assertEqual(0.42, PolymtradeExecutor._extract_quoted_price("Yes $0.42"))
        self.assertIsNone(PolymtradeExecutor._extract_quoted_price("Up"))

    async def test_last_mile_price_drift_does_not_pollute_executor_last_error(self):
        executor = PolymtradeExecutor()
        executor._logged_in = True

        with (
            patch.object(executor, "is_ready", return_value=True),
            patch.object(executor, "_resolve_event", AsyncMock(return_value=("", "btc-updown-5m-1"))),
            patch.object(
                executor,
                "_execute_buy",
                AsyncMock(side_effect=LastMilePriceDriftError(0.45, 0.50, 0.03)),
            ),
        ):
            with self.assertRaises(LastMilePriceDriftError):
                await executor.execute_trade(
                    market_slug="btc-updown-5m-1",
                    side="BUY",
                    outcome="Up",
                    amount_usdc=1.0,
                    signal_price=0.45,
                    max_price_drift=0.03,
                )

        self.assertIsNone(executor.last_error)

    async def test_successful_trade_clears_stale_last_error(self):
        executor = PolymtradeExecutor()
        executor._logged_in = True
        executor.last_error = "Target market content never appeared"

        with (
            patch.object(executor, "is_ready", return_value=True),
            patch.object(executor, "_resolve_event", AsyncMock(return_value=("", "btc-updown-5m-1"))),
            patch.object(
                executor,
                "_execute_buy",
                AsyncMock(return_value={"baseline": {}, "submitted_quote": 0.5}),
            ),
        ):
            result = await executor.execute_trade(
                market_slug="btc-updown-5m-1",
                side="BUY",
                outcome="Up",
                amount_usdc=1.0,
                verify=False,
            )

        self.assertIsNone(executor.last_error)
        self.assertIsNone(result["verified"])

    async def test_buy_submit_button_respects_overall_timeout(self):
        class SlowMissingButtonPage:
            def __init__(self):
                self.timeouts = []

            async def click(self, selector, timeout):
                self.timeouts.append(timeout)
                await __import__("asyncio").sleep(timeout / 1000)
                raise TimeoutError(selector)

            async def screenshot(self, path):
                return None

        executor = PolymtradeExecutor()
        executor.page = SlowMissingButtonPage()

        with (
            patch.object(executor, "_click_trade_submit_button", AsyncMock(return_value=False)),
            patch.object(executor, "_capture_trade_submit_diagnostics", AsyncMock()),
        ):
            started_at = time.perf_counter()
            with self.assertRaisesRegex(RuntimeError, "Could not click buy button"):
                await executor._click_buy_button(timeout=0.05)
            elapsed = time.perf_counter() - started_at

        self.assertLess(elapsed, 0.25)
        self.assertLessEqual(max(executor.page.timeouts), 50)

    async def test_sell_submit_button_respects_overall_timeout(self):
        class SlowMissingButtonPage:
            def __init__(self):
                self.timeouts = []

            async def click(self, selector, timeout):
                self.timeouts.append(timeout)
                await __import__("asyncio").sleep(timeout / 1000)
                raise TimeoutError(selector)

            async def screenshot(self, path):
                return None

        executor = PolymtradeExecutor()
        executor.page = SlowMissingButtonPage()

        with (
            patch.object(executor, "_is_sell_dialog_open", AsyncMock(return_value=True)),
            patch.object(executor, "_click_trade_submit_button", AsyncMock(return_value=False)),
            patch.object(executor, "_capture_trade_submit_diagnostics", AsyncMock()),
        ):
            started_at = time.perf_counter()
            with self.assertRaisesRegex(RuntimeError, "Could not click sell button"):
                await executor._click_sell_button(timeout=0.05)
            elapsed = time.perf_counter() - started_at

        self.assertLess(elapsed, 0.25)
        self.assertLessEqual(max(executor.page.timeouts), 50)

    async def test_confirmation_returns_without_fixed_wait_when_dialog_is_closed(self):
        executor = PolymtradeExecutor()
        executor.page = type(
            "ClosedDialogPage",
            (),
            {"query_selector": AsyncMock(return_value=None)},
        )()

        with patch("polymtrade_executor.asyncio.sleep", new=AsyncMock()) as sleep:
            await executor._confirm_trade()

        sleep.assert_not_awaited()

    async def test_buy_does_not_use_fixed_three_second_navigation_wait(self):
        executor = PolymtradeExecutor()
        goto = AsyncMock()
        with (
            patch.object(executor, "_goto_with_retry", goto),
            patch.object(executor, "_wait_for_page_ready", AsyncMock(return_value=True)) as wait_ready,
            patch.object(executor, "_get_usdc_balance", AsyncMock(return_value=100)),
            patch.object(executor, "_is_target_event_visible", AsyncMock(return_value=True)) as target_visible,
            patch.object(
                executor,
                "_select_polymtrade_outcome",
                AsyncMock(return_value={"label": "Up 50¢"}),
            ),
            patch.object(executor, "_is_network_modal_open", AsyncMock(return_value=False)),
            patch.object(executor, "_is_buy_dialog_open", AsyncMock(return_value=True)) as is_buy_dialog_open,
            patch.object(executor, "_capture_buy_baseline", AsyncMock(return_value={})),
            patch.object(executor, "_enter_amount", AsyncMock()),
            patch.object(executor, "_click_buy_button", AsyncMock()) as click_buy_button,
            patch.object(executor, "_confirm_trade", AsyncMock()) as confirm_trade,
            patch("polymtrade_executor.asyncio.sleep", new=AsyncMock()) as sleep,
        ):
            result = await executor._execute_buy_on_page(
                "1",
                "event",
                "Up",
                1.0,
                market_slug="btc-updown-15m-1",
                market_title="BTC Up or Down",
            )

        self.assertNotIn(call(3), sleep.await_args_list)
        self.assertEqual(0.5, result["submitted_quote"])
        goto.assert_awaited_once_with(
            "https://polym.trade/portfolio?eventId=1&eventSlug=event&eventSource=polymarket",
            wait_until="commit",
        )
        wait_ready.assert_awaited_once_with(
            timeout=1.5,
            market_title="BTC Up or Down",
            event_id="1",
            market_slug="btc-updown-15m-1",
            outcome="Up",
        )
        target_visible.assert_awaited_once_with(
            "Up",
            market_slug="btc-updown-15m-1",
            market_title="BTC Up or Down",
            event_id="1",
            event_slug="event",
            timeout=2.5,
        )
        is_buy_dialog_open.assert_awaited_once_with(timeout=1.25)
        click_buy_button.assert_awaited_once_with(timeout=2.0)
        confirm_trade.assert_awaited_once_with(timeout=1.25)

    async def test_sell_does_not_use_fixed_three_second_navigation_wait(self):
        executor = PolymtradeExecutor()
        goto = AsyncMock()
        with (
            patch.object(executor, "_goto_with_retry", goto),
            patch.object(executor, "_wait_for_page_ready", AsyncMock(return_value=True)) as wait_ready,
            patch.object(executor, "_wait_for_event_url", AsyncMock(return_value=True)) as wait_event_url,
            patch.object(executor, "_is_network_modal_open", AsyncMock(return_value=False)),
            patch.object(executor, "_open_sell_dialog", AsyncMock()),
            patch.object(executor, "_is_sell_dialog_open", AsyncMock(return_value=True)) as is_sell_dialog_open,
            patch.object(
                executor,
                "_capture_sell_baseline",
                AsyncMock(return_value={"position_quantity": 2.0}),
            ),
            patch.object(executor, "_enter_sell_shares", AsyncMock(return_value=True)),
            patch.object(executor, "_click_sell_button", AsyncMock()) as click_sell_button,
            patch.object(executor, "_confirm_trade", AsyncMock()) as confirm_trade,
            patch("polymtrade_executor.asyncio.sleep", new=AsyncMock()) as sleep,
        ):
            await executor._execute_sell(
                "1",
                "event",
                "Up",
                0,
                size_shares=1,
                market_slug="btc-updown-15m-1",
                market_title="BTC Up or Down",
            )

        self.assertNotIn(call(3), sleep.await_args_list)
        goto.assert_awaited_once_with(
            "https://polym.trade/portfolio?eventId=1&eventSlug=event&eventSource=polymarket",
            wait_until="commit",
        )
        wait_ready.assert_awaited_once_with(
            timeout=6.0,
            market_title="BTC Up or Down",
            event_id="1",
            market_slug="btc-updown-15m-1",
            outcome="Up",
        )
        self.assertIn(call("1", timeout=2.0), wait_event_url.await_args_list)
        is_sell_dialog_open.assert_awaited_once_with(timeout=1.25)
        click_sell_button.assert_awaited_once_with(timeout=2.0)
        confirm_trade.assert_awaited_once_with(timeout=1.25)

    async def test_non_short_cycle_markets_keep_default_navigation_waits(self):
        executor = PolymtradeExecutor()

        self.assertEqual(15.0, executor._page_ready_timeout_for_market("fed-decision-in-july-181"))
        self.assertEqual(15.0, executor._buy_page_ready_timeout_for_market("fed-decision-in-july-181"))
        self.assertEqual(0.5, executor._page_ready_poll_seconds_for_market("fed-decision-in-july-181"))
        self.assertEqual(8.0, executor._target_visible_timeout_for_market("fed-decision-in-july-181"))
        self.assertEqual(0.3, executor._target_visible_poll_seconds_for_market("fed-decision-in-july-181"))
        self.assertEqual(6.0, executor._event_url_timeout_for_market("fed-decision-in-july-181", 6.0))
        self.assertEqual(3.0, executor._dialog_detect_timeout_for_market("fed-decision-in-july-181"))
        self.assertEqual(15.0, executor._confirm_timeout_for_market("fed-decision-in-july-181"))
        self.assertEqual(10.0, executor._submit_button_timeout_for_market("fed-decision-in-july-181"))

    async def test_short_cycle_markets_use_tight_target_visible_budget(self):
        executor = PolymtradeExecutor()

        self.assertEqual(2.5, executor._target_visible_timeout_for_market("btc-updown-5m-1"))
        self.assertEqual(2.5, executor._target_visible_timeout_for_market("btc-updown-15m-1"))
        self.assertEqual(0.8, executor._post_outcome_settle_seconds_for_market("fed-decision-in-july-181"))
        self.assertEqual(1.0, executor._retry_navigation_settle_seconds_for_market("fed-decision-in-july-181"))
        self.assertEqual(1.5, executor._portfolio_row_settle_seconds_for_market("fed-decision-in-july-181"))
        self.assertEqual(6, executor._buy_attempts_for_market("fed-decision-in-july-181"))
        self.assertEqual(5, executor._sell_dialog_attempts_for_market("fed-decision-in-july-181"))
        self.assertEqual("domcontentloaded", executor._navigation_wait_until_for_market("fed-decision-in-july-181"))

    async def test_short_cycle_markets_use_tight_dialog_and_confirmation_budgets(self):
        executor = PolymtradeExecutor()

        self.assertEqual(6.0, executor._page_ready_timeout_for_market("btc-updown-5m-1"))
        self.assertEqual(1.5, executor._buy_page_ready_timeout_for_market("btc-updown-5m-1"))
        self.assertEqual(1.25, executor._dialog_detect_timeout_for_market("btc-updown-5m-1"))
        self.assertEqual(1.25, executor._confirm_timeout_for_market("btc-updown-15m-1"))
        self.assertEqual(0.15, executor._page_ready_poll_seconds_for_market("btc-updown-5m-1"))
        self.assertEqual(0.15, executor._target_visible_poll_seconds_for_market("btc-updown-5m-1"))
        self.assertEqual(0.15, executor._target_visible_poll_seconds_for_market("btc-updown-15m-1"))
        self.assertEqual(2.0, executor._submit_button_timeout_for_market("btc-updown-5m-1"))
        self.assertEqual(2.0, executor._submit_button_timeout_for_market("btc-updown-15m-1"))
        self.assertEqual(0.15, executor._post_outcome_settle_seconds_for_market("btc-updown-5m-1"))
        self.assertEqual(0.25, executor._retry_navigation_settle_seconds_for_market("btc-updown-5m-1"))
        self.assertEqual(0.35, executor._portfolio_row_settle_seconds_for_market("btc-updown-5m-1"))
        self.assertEqual("commit", executor._navigation_wait_until_for_market("btc-updown-5m-1"))
        self.assertEqual("commit", executor._navigation_wait_until_for_market("btc-updown-15m-1"))
        self.assertEqual("5m", executor._latency_bucket_for_market("btc-updown-5m-1"))
        self.assertEqual("15m", executor._latency_bucket_for_market("btc-updown-15m-1"))
        self.assertEqual("other", executor._latency_bucket_for_market("fed-decision-in-july-181"))

    async def test_dialog_detection_respects_overall_deadline_across_selectors(self):
        class TimeoutPage:
            async def wait_for_selector(self, selector, timeout):
                await __import__("asyncio").sleep(timeout / 1000)
                raise TimeoutError(selector)

        executor = PolymtradeExecutor()
        executor.page = TimeoutPage()

        with patch.object(executor, "_find_trade_input", AsyncMock(return_value=None)):
            started_at = time.perf_counter()
            result = await executor._is_buy_dialog_open(timeout=0.6)
            elapsed = time.perf_counter() - started_at

        self.assertFalse(result)
        self.assertLess(elapsed, 0.9)

    async def test_short_cycle_buy_uses_reduced_retry_budget(self):
        executor = PolymtradeExecutor()
        executor.page = type("Page", (), {"url": "https://polym.trade/portfolio"})()
        goto = AsyncMock()

        with (
            patch.object(executor, "_goto_with_retry", goto),
            patch.object(executor, "_wait_for_page_ready", AsyncMock(return_value=True)),
            patch.object(executor, "_get_usdc_balance", AsyncMock(return_value=100)),
            patch.object(executor, "_is_target_event_visible", AsyncMock(return_value=False)) as target_visible,
            patch.object(executor, "_open_target_market_from_portfolio_row", AsyncMock(return_value=False)),
            patch("polymtrade_executor.asyncio.sleep", new=AsyncMock()) as sleep,
        ):
            with self.assertRaisesRegex(RuntimeError, "Target market content never appeared"):
                await executor._execute_buy_on_page(
                    "1",
                    "event",
                    "Up",
                    1.0,
                    market_slug="btc-updown-15m-1",
                    market_title="BTC Up or Down",
                )

        self.assertEqual(3, target_visible.await_count)
        for awaited in goto.await_args_list:
            self.assertEqual("commit", awaited.kwargs.get("wait_until"))
        self.assertIn(call(0.25), sleep.await_args_list)
        self.assertNotIn(call(1.0), sleep.await_args_list)

    async def test_target_market_missing_retries_once_with_verified_canonical_slug(self):
        executor = PolymtradeExecutor()
        executor.page = type("Page", (), {"url": "https://polym.trade/portfolio"})()
        goto = AsyncMock()
        canonical_slug = "us-announces-end-of-iranian-blockade-by-august-15"

        with (
            patch.object(executor, "_goto_with_retry", goto),
            patch.object(executor, "_wait_for_page_ready", AsyncMock(return_value=True)),
            patch.object(executor, "_get_usdc_balance", AsyncMock(return_value=100)),
            patch.object(executor, "_is_target_event_visible", AsyncMock(return_value=False)) as target_visible,
            patch.object(executor, "_open_target_market_from_portfolio_row", AsyncMock(return_value=False)),
            patch.object(
                executor,
                "_canonical_market_slug_for_condition",
                AsyncMock(return_value=canonical_slug),
            ) as canonical_lookup,
            patch.object(executor, "_capture_target_market_diagnostics", AsyncMock()) as capture_diagnostics,
            patch("polymtrade_executor.asyncio.sleep", new=AsyncMock()),
        ):
            with self.assertRaisesRegex(RuntimeError, "Target market content never appeared"):
                await executor._execute_buy_on_page(
                    "123",
                    "iran-blockade-event",
                    "No",
                    1.0,
                    market_slug="us-announces-end-of-iranian-blockade-byptptpt-20260713152715080",
                    market_title="US announces end of Iranian blockade by August 15, 2026?",
                    condition_id="0xa055",
                )

        self.assertEqual(8, target_visible.await_count)
        canonical_lookup.assert_awaited_once_with("0xa055")
        self.assertTrue(
            any(canonical_slug in awaited.args[0] for awaited in goto.await_args_list)
        )
        capture_diagnostics.assert_awaited_once()

    async def test_grouped_market_missing_retries_on_root_event_route(self):
        executor = PolymtradeExecutor()
        executor.page = type("Page", (), {"url": "https://polym.trade/portfolio"})()
        goto = AsyncMock()

        with (
            patch.object(executor, "_goto_with_retry", goto),
            patch.object(executor, "_wait_for_page_ready", AsyncMock(return_value=True)),
            patch.object(executor, "_get_usdc_balance", AsyncMock(return_value=100)),
            patch.object(
                executor,
                "_is_target_event_visible",
                AsyncMock(side_effect=[False] * 6 + [True]),
            ) as target_visible,
            patch.object(executor, "_open_target_market_from_portfolio_row", AsyncMock(return_value=False)),
            patch.object(
                executor,
                "_select_polymtrade_outcome",
                AsyncMock(return_value={"label": "No 47¢"}),
            ),
            patch.object(executor, "_is_network_modal_open", AsyncMock(return_value=False)),
            patch.object(executor, "_is_buy_dialog_open", AsyncMock(return_value=True)),
            patch.object(executor, "_capture_buy_baseline", AsyncMock(return_value={})),
            patch.object(executor, "_enter_amount", AsyncMock()),
            patch.object(executor, "_click_buy_button", AsyncMock()),
            patch.object(executor, "_confirm_trade", AsyncMock()),
            patch("polymtrade_executor.asyncio.sleep", new=AsyncMock()),
        ):
            await executor._execute_buy_on_page(
                "216716",
                "will-russia-capture-all-of-kostyantynivka-by",
                "No",
                1.0,
                market_slug="will-russia-capture-all-of-kostyantynivka-by-december-31-2026-372-718",
                market_title="Will Russia capture all of Kostyantynivka by December 31, 2026?",
                condition_id="0x627ed3",
            )

        self.assertEqual(7, target_visible.await_count)
        self.assertTrue(
            any(
                awaited.args[0]
                == (
                    "https://polym.trade/?eventId=216716"
                    "&eventSlug=will-russia-capture-all-of-kostyantynivka-by"
                    "&eventSource=polymarket"
                )
                for awaited in goto.await_args_list
            )
        )

    async def test_short_cycle_buy_uses_reduced_portfolio_row_settle(self):
        executor = PolymtradeExecutor()
        executor.page = type("Page", (), {"url": "https://polym.trade/portfolio"})()

        with (
            patch.object(executor, "_goto_with_retry", AsyncMock()),
            patch.object(executor, "_wait_for_page_ready", AsyncMock(return_value=True)),
            patch.object(executor, "_get_usdc_balance", AsyncMock(return_value=100)),
            patch.object(executor, "_is_target_event_visible", AsyncMock(return_value=False)),
            patch.object(executor, "_open_target_market_from_portfolio_row", AsyncMock(return_value=True)),
            patch("polymtrade_executor.asyncio.sleep", new=AsyncMock()) as sleep,
        ):
            with self.assertRaisesRegex(RuntimeError, "Target market content never appeared"):
                await executor._execute_buy_on_page(
                    "1",
                    "event",
                    "Up",
                    1.0,
                    market_slug="btc-updown-15m-1",
                    market_title="BTC Up or Down",
                )

        self.assertIn(call(0.35), sleep.await_args_list)
        self.assertNotIn(call(1.5), sleep.await_args_list)

    async def test_short_cycle_buy_can_navigate_without_event_id(self):
        executor = PolymtradeExecutor()
        goto = AsyncMock()

        with (
            patch.object(executor, "_goto_with_retry", goto),
            patch.object(executor, "_wait_for_page_ready", AsyncMock(return_value=True)),
            patch.object(executor, "_get_usdc_balance", AsyncMock(return_value=100)),
            patch.object(executor, "_is_target_event_visible", AsyncMock(return_value=True)),
            patch.object(
                executor,
                "_select_polymtrade_outcome",
                AsyncMock(return_value={"label": "Up 50¢"}),
            ),
            patch.object(executor, "_is_network_modal_open", AsyncMock(return_value=False)),
            patch.object(executor, "_is_buy_dialog_open", AsyncMock(return_value=True)),
            patch.object(executor, "_capture_buy_baseline", AsyncMock(return_value={})),
            patch.object(executor, "_enter_amount", AsyncMock()),
            patch.object(executor, "_click_buy_button", AsyncMock()),
            patch.object(executor, "_confirm_trade", AsyncMock()),
            patch("polymtrade_executor.asyncio.sleep", new=AsyncMock()) as sleep,
        ):
            await executor._execute_buy_on_page(
                "",
                "btc-updown-5m-1784131200",
                "Up",
                1.0,
                market_slug="btc-updown-5m-1784131200",
                market_title="BTC Up or Down",
            )

        goto.assert_awaited_once_with(
            "https://polym.trade/portfolio?eventSlug=btc-updown-5m-1784131200&eventSource=polymarket",
            wait_until="commit",
        )
        self.assertIn(call(0.15), sleep.await_args_list)
        self.assertNotIn(call(0.8), sleep.await_args_list)

    async def test_buy_blocks_price_drift_before_entering_amount(self):
        executor = PolymtradeExecutor()
        with (
            patch.object(executor, "_goto_with_retry", AsyncMock()),
            patch.object(executor, "_wait_for_page_ready", AsyncMock(return_value=True)),
            patch.object(executor, "_get_usdc_balance", AsyncMock(return_value=100)),
            patch.object(executor, "_is_target_event_visible", AsyncMock(return_value=True)),
            patch.object(
                executor,
                "_select_polymtrade_outcome",
                AsyncMock(return_value={"label": "Up 64¢"}),
            ),
            patch.object(executor, "_is_network_modal_open", AsyncMock(return_value=False)),
            patch.object(executor, "_is_buy_dialog_open", AsyncMock(return_value=True)),
            patch.object(executor, "_capture_buy_baseline", AsyncMock()) as capture_baseline,
            patch.object(executor, "_enter_amount", AsyncMock()) as enter_amount,
            patch.object(executor, "_click_buy_button", AsyncMock()) as click_buy_button,
            patch("polymtrade_executor.asyncio.sleep", new=AsyncMock()),
        ):
            with self.assertRaisesRegex(RuntimeError, "Last-mile price drift blocked BUY before submit"):
                await executor._execute_buy_on_page(
                    "1",
                    "event",
                    "Up",
                    1.0,
                    market_slug="btc-updown-5m-1",
                    market_title="BTC Up or Down",
                    signal_price=0.5175,
                    max_price_drift=0.03,
                )

        capture_baseline.assert_not_awaited()
        enter_amount.assert_not_awaited()
        click_buy_button.assert_not_awaited()

    async def test_short_cycle_sell_uses_reduced_dialog_retry_budget(self):
        executor = PolymtradeExecutor()

        with (
            patch.object(executor, "_goto_with_retry", AsyncMock()),
            patch.object(executor, "_wait_for_page_ready", AsyncMock(return_value=True)),
            patch.object(executor, "_wait_for_event_url", AsyncMock(return_value=False)) as wait_event_url,
            patch.object(executor, "_is_network_modal_open", AsyncMock(return_value=False)),
            patch("polymtrade_executor.asyncio.sleep", new=AsyncMock()),
        ):
            with self.assertRaisesRegex(RuntimeError, "URL never appeared"):
                await executor._execute_sell(
                    "1",
                    "event",
                    "Up",
                    0,
                    size_shares=1,
                    market_slug="btc-updown-15m-1",
                    market_title="BTC Up or Down",
                )

        self.assertEqual(3, wait_event_url.await_count)

    async def test_short_cycle_sell_can_navigate_without_event_id(self):
        executor = PolymtradeExecutor()
        goto = AsyncMock()
        wait_event_url = AsyncMock(return_value=False)

        with (
            patch.object(executor, "_goto_with_retry", goto),
            patch.object(executor, "_wait_for_page_ready", AsyncMock(return_value=True)),
            patch.object(executor, "_wait_for_event_url", wait_event_url),
            patch.object(executor, "_is_network_modal_open", AsyncMock(return_value=False)),
            patch.object(executor, "_open_sell_dialog", AsyncMock()),
            patch.object(executor, "_is_sell_dialog_open", AsyncMock(return_value=True)),
            patch.object(
                executor,
                "_capture_sell_baseline",
                AsyncMock(return_value={"position_quantity": 2.0}),
            ),
            patch.object(executor, "_enter_sell_shares", AsyncMock(return_value=True)),
            patch.object(executor, "_click_sell_button", AsyncMock()),
            patch.object(executor, "_confirm_trade", AsyncMock()),
            patch("polymtrade_executor.asyncio.sleep", new=AsyncMock()),
        ):
            await executor._execute_sell(
                "",
                "btc-updown-5m-1784131200",
                "Up",
                0,
                size_shares=1,
                market_slug="btc-updown-5m-1784131200",
                market_title="BTC Up or Down",
            )

        goto.assert_awaited_once_with(
            "https://polym.trade/portfolio?eventSlug=btc-updown-5m-1784131200&eventSource=polymarket",
            wait_until="commit",
        )
        wait_event_url.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
