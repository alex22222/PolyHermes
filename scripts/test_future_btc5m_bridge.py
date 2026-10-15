import json
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

from future_btc5m_bridge import FutureBridge
import future_btc5m_bridge

# These suites cover the original 5m strategy; the 15m default is tested separately.
future_btc5m_bridge.DEFAULT_STRATEGY = "btc5m_favorite"


START = 1791706800


def source(at=START + 60):
    return {
        "schema_version": 1, "mode": "ASSIST_ONLY", "live_enabled": False,
        "amount_usd": 1, "server_time": at, "period_start": START,
        "status": "OBSERVING", "feed_status": "CURRENT",
        "future_eligibility": {"status": "UNKNOWN"},
        "signal": {
            "id": f"5m:{START}", "slug": f"btc-updown-5m-{START}", "series": "5m",
            "period_start": START, "period_end": START + 300, "side": "Up",
            "open_price": 83000, "current_price": 83001,
            "open_price_source": "polymarket_crypto_price_fiveminute_twap60_openPrice",
            "twap_lookback_seconds": 60, "price_source": "chainlink", "price_observed_at": at,
        },
    }


def browser_report(at=START + 60, **changes):
    return {
        "schemaVersion": 2, "marketUrl": f"https://future.news/zh/event/btc-updown-5m-{START}",
        "pagePeriodStart": START, "checkedAt": at, "navigation": "CURRENT",
        "ticketStatus": "PASS", "amountUsd": 1, "selectedSide": "Up", "buyButtonEnabled": True,
        "upQuoteCents": 53, "downQuoteCents": 48,
        **changes,
    }


def legacy_browser_report(at=START + 60, **changes):
    report = browser_report(at, **changes)
    report["schemaVersion"] = 1
    del report["upQuoteCents"], report["downQuoteCents"]
    return report


def legacy_order(start=START, at=None):
    at = start + 60 if at is None else at
    return {
        "id": f"future-btc5m:{start}", "bridgeId": "future-btc5m", "slug": f"btc-updown-5m-{start}",
        "periodStart": start, "periodEnd": start + 300, "side": "Up", "amountUsd": 1,
        "status": "SKIPPED", "reason": "EXECUTOR_NOT_CONNECTED", "createdAt": at, "updatedAt": at,
        "submittedAt": None, "filledAt": None, "platformOrderId": None, "filledQuantity": None,
        "avgFilledPrice": None, "feeUsd": None,
        "events": [{"stage": "SIGNAL_ACCEPTED", "at": at, "reason": None},
                   {"stage": "EXECUTION_BLOCKED", "at": at, "reason": "EXECUTOR_NOT_CONNECTED"}],
    }


class FutureBridgeTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.clock = START + 10.0
        self.source = source()
        self.bridge = FutureBridge(self.path, lambda: self.source, lambda: self.clock)

    def load_legacy_and_observe(self, at=START + 60):
        (self.path / "orders.jsonl").write_text(json.dumps(legacy_order(at=at)) + "\n")
        self.bridge = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        self.bridge.control(True)
        self.clock = at
        self.source["server_time"] = at
        return self.bridge.observe()

    def enable_and_prepare(self, at=START + 60, **changes):
        self.bridge.control(True)
        self.clock = at
        self.source["server_time"] = at
        self.bridge.report_preflight(browser_report(at, **changes))
        return self.bridge.observe()

    def test_default_off_and_reads_do_not_create_orders(self):
        status = self.bridge.status()
        self.assertFalse(status["requestedEnabled"])
        self.assertFalse(status["effectiveEnabled"])
        self.assertFalse(status["executorReady"])
        self.assertEqual("DISABLED", status["mode"])
        self.assertEqual(1, status["amountUsd"])
        self.assertEqual({"list": [], "total": 0, "page": 1, "size": 20}, self.bridge.orders())
        self.assertIsNone(self.bridge.detail("unknown"))
        self.clock = START + 60
        self.bridge.observe()
        self.assertFalse((self.path / "orders.jsonl").exists())

    def test_control_saves_intent_but_never_marks_execution_ready(self):
        status = self.bridge.control(True)
        self.assertTrue(status["requestedEnabled"])
        self.assertFalse(status["effectiveEnabled"])
        self.assertFalse(status["executorReady"])
        self.assertEqual("BLOCKED", status["mode"])
        self.assertEqual("EXECUTOR_NOT_CONNECTED", status["reason"])
        self.assertTrue(json.loads((self.path / "control.json").read_text())["requestedEnabled"])
        self.assertEqual("UNKNOWN", self.source["future_eligibility"]["status"])

    def test_restart_forces_off_and_retains_order_source_of_truth(self):
        self.load_legacy_and_observe()
        restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        self.assertFalse(restored.status()["requestedEnabled"])
        self.assertFalse(json.loads((self.path / "control.json").read_text())["requestedEnabled"])
        self.assertEqual(1, restored.orders()["total"])
        restored.control(True)
        restored.observe()
        self.assertEqual(1, restored.orders()["total"])

    def test_legacy_skipped_history_has_no_fill_fields_and_observe_creates_no_order(self):
        status = self.load_legacy_and_observe()
        record = self.bridge.orders()["list"][0]
        self.assertEqual(f"future-btc5m:{START}", record["id"])
        self.assertEqual("SKIPPED", record["status"])
        self.assertEqual("EXECUTOR_NOT_CONNECTED", record["reason"])
        self.assertEqual(1, record["amountUsd"])
        for field in ("submittedAt", "filledAt", "platformOrderId", "filledQuantity", "avgFilledPrice", "feeUsd"):
            self.assertIsNone(record[field], field)
        self.assertEqual(["SIGNAL_ACCEPTED", "EXECUTION_BLOCKED"], [event["stage"] for event in record["events"]])
        self.assertEqual({"total": 1, "pending": 0, "submitted": 0, "filled": 0, "failed": 0, "skipped": 1}, status["orderCounts"])
        self.assertEqual(record, json.loads((self.path / "orders.jsonl").read_text()))

    def test_observation_and_concurrent_calls_preserve_legacy_history_without_upgrade(self):
        self.load_legacy_and_observe()
        original = (self.path / "orders.jsonl").read_bytes()
        self.bridge.report_preflight(browser_report())
        threads = [threading.Thread(target=self.bridge.observe) for _ in range(12)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, self.bridge.orders()["total"])
        self.assertEqual(1, len((self.path / "orders.jsonl").read_text().splitlines()))
        self.assertEqual(original, (self.path / "orders.jsonl").read_bytes())
        self.assertIsNone(self.bridge.status()["preparation"]["intent"])

    def test_control_false_and_stop_do_not_create_order(self):
        self.bridge.control(True)
        self.bridge.control(False)
        self.clock = START + 60
        self.bridge.observe()
        self.assertEqual(0, self.bridge.orders()["total"])
        (self.path / "STOP").touch()
        self.assertEqual("STOP_FILE_PRESENT", self.bridge.status()["reason"])
        with self.assertRaisesRegex(ValueError, "STOP_FILE_PRESENT"):
            self.bridge.control(True)
        self.bridge.observe()
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_stop_disables_existing_intent_and_source_stopped_also_blocks(self):
        self.bridge.control(True)
        self.source["status"] = "STOPPED"
        self.clock = START + 60
        status = self.bridge.observe()
        self.assertFalse(status["requestedEnabled"])
        self.assertEqual("STOP_FILE_PRESENT", status["reason"])
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_off_window_stale_future_and_wrong_round_signal_are_rejected(self):
        scenarios = [
            (START + 59.999, {}), (START + 80, {}), (START + 65.001, {}),
            (START + 60, {"price_observed_at": START + 61}),
            (START + 60, {"period_start": START - 300}),
            (START + 60, {"period_end": START + 600}),
            (START + 60, {"slug": f"btc-updown-15m-{START}"}),
            (START + 60, {"side": "Down"}),
            (START + 60, {"side": None}),
            (START + 60, {"price_source": "binance"}),
            (START + 60, {"open_price_source": "unverified"}),
            (START + 60, {"twap_lookback_seconds": 30}),
            (START + 60, {"current_price": float("nan")}),
        ]
        for index, (at, change) in enumerate(scenarios):
            with self.subTest(at=at, change=change):
                current = source()
                current["server_time"] = at
                current["signal"].update(change)
                clock = [START + 10]
                bridge = FutureBridge(self.path / str(index), lambda: current, lambda: clock[0])
                bridge.control(True)
                clock[0] = at
                bridge.observe()
                self.assertEqual(0, bridge.orders()["total"])

    def test_feed_unavailable_or_source_stale_and_bad_schema_are_rejected(self):
        for index, change in enumerate([
            {"feed_status": "UNAVAILABLE"}, {"server_time": START + 56},
            {"schema_version": 2}, {"mode": "LIVE"}, {"live_enabled": True},
            {"period_start": START - 300}, {"amount_usd": 2},
        ]):
            with self.subTest(change=change):
                current = {**source(), **change}
                clock = [START + 10]
                bridge = FutureBridge(self.path / str(index), lambda: current, lambda: clock[0])
                bridge.control(True)
                clock[0] = START + 60
                bridge.observe()
                self.assertEqual(0, bridge.orders()["total"])

    def test_enabling_after_signal_does_not_catch_up_or_create_order(self):
        self.clock = START + 62
        self.source["server_time"] = self.clock
        self.bridge.control(True)
        self.bridge.observe()
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_recent_chainlink_sample_before_entry_is_accepted_like_helper(self):
        self.source["signal"]["price_observed_at"] = START + 58.5
        status = self.enable_and_prepare()
        self.assertEqual("PENDING", status["preparation"]["state"])
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_only_valid_down_signal_can_prepare_down(self):
        self.source["signal"].update(side="Down", current_price=82999)
        status = self.enable_and_prepare(upQuoteCents=12, downQuoteCents=88)
        self.assertEqual("Down", status["preparation"]["intent"]["side"])
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_pagination_filter_detail_and_returned_values_are_copied(self):
        second = START + 300
        (self.path / "orders.jsonl").write_text("".join(json.dumps(legacy_order(start)) + "\n" for start in (START, second)))
        self.bridge = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        self.clock = second + 60
        self.source = source(self.clock)
        self.source["period_start"] = second
        self.source["signal"].update(id=f"5m:{second}", slug=f"btc-updown-5m-{second}",
                                     period_start=second, period_end=second + 300)
        self.bridge.observe()
        page = self.bridge.orders(page=2, size=1, status="SKIPPED")
        self.assertEqual(2, page["total"])
        self.assertEqual(f"future-btc5m:{START}", page["list"][0]["id"])
        self.assertEqual([], self.bridge.orders(status="FILLED")["list"])
        detail = self.bridge.detail(page["list"][0]["id"])
        detail["events"].clear()
        self.assertEqual(2, len(self.bridge.detail(detail["id"])["events"]))
        status = self.bridge.status()
        status["signal"]["side"] = "invalid"
        self.assertEqual("Up", self.source["signal"]["side"])

    def test_invalid_control_and_paging_values_are_rejected(self):
        for value in (1, "true", None):
            with self.assertRaises(ValueError):
                self.bridge.control(value)
        for kwargs in ({"page": 0}, {"size": 0}, {"size": 101}, {"page": True}):
            with self.assertRaises(ValueError):
                self.bridge.orders(**kwargs)

    def test_preparation_ledger_is_fsynced_before_intent_is_visible(self):
        self.bridge.control(True)
        self.clock = START + 60
        self.bridge.report_preflight(browser_report())
        with patch("future_btc5m_bridge.os.fsync") as fsync:
            status = self.bridge.observe()
            self.assertGreaterEqual(fsync.call_count, 1)
        self.assertEqual("PENDING", status["preparation"]["state"])
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_invalid_ledger_reads_are_unavailable_not_empty_history(self):
        (self.path / "orders.jsonl").write_text('{"broken":')
        restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        self.assertTrue(restored.status()["online"])
        self.assertEqual("ORDER_LEDGER_INVALID", restored.status()["reason"])
        for read in (restored.orders, lambda: restored.detail("unknown")):
            with self.assertRaisesRegex(OSError, "ORDER_LEDGER_INVALID"):
                read()

    def test_corrupt_ledger_fails_closed_without_repair_or_overwrite(self):
        self.load_legacy_and_observe()
        ledger = self.path / "orders.jsonl"
        ledger.write_text(ledger.read_text() + '{"broken":')
        original = ledger.read_bytes()
        restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        self.assertEqual("ORDER_LEDGER_INVALID", restored.status()["reason"])
        self.assertFalse(restored.status()["effectiveEnabled"])
        with self.assertRaisesRegex(ValueError, "ORDER_LEDGER_INVALID"):
            restored.control(True)
        for read in (restored.orders, lambda: restored.detail(f"future-btc5m:{START}")):
            with self.assertRaisesRegex(OSError, "ORDER_LEDGER_INVALID"):
                read()
        restored.observe()
        self.assertEqual(original, ledger.read_bytes())

    def test_forged_filled_or_duplicate_ledger_records_are_rejected(self):
        self.load_legacy_and_observe()
        record = self.bridge.orders()["list"][0]
        ledger = self.path / "orders.jsonl"
        for rows in ([{**record, "status": "FILLED"}], [record, record], [{**record, "filledQuantity": 3}]):
            with self.subTest(rows=rows):
                ledger.write_text("".join(json.dumps(row) + "\n" for row in rows))
                restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
                self.assertEqual("ORDER_LEDGER_INVALID", restored.status()["reason"])

    def test_failed_preparation_write_blocks_preparation_and_preserves_legacy_orders(self):
        self.load_legacy_and_observe()
        original = (self.path / "orders.jsonl").read_bytes()
        second = START + 300
        self.clock = second + 60
        self.source = source(self.clock)
        self.source["period_start"] = second
        self.source["signal"].update(id=f"5m:{second}", slug=f"btc-updown-5m-{second}",
                                     period_start=second, period_end=second + 300)
        self.bridge.report_preflight(browser_report(self.clock, marketUrl=f"https://future.news/event/btc-updown-5m-{second}",
                                                   pagePeriodStart=second))
        with patch("future_btc5m_bridge.os.fsync", side_effect=OSError("disk failure")):
            status = self.bridge.observe()
        self.assertEqual("BLOCKED", status["preparation"]["state"])
        self.assertEqual(["PREPARATION_LEDGER_WRITE_FAILED"], status["preparation"]["reasons"])
        self.assertIsNone(self.bridge.storage_error)
        self.assertEqual(1, self.bridge.orders()["total"])
        self.bridge.observe()
        self.assertEqual(original, (self.path / "orders.jsonl").read_bytes())
        self.assertIsNone(self.bridge.status()["preparation"]["intent"])

    def test_source_exception_keeps_control_service_readable(self):
        self.bridge.status_fn = lambda: (_ for _ in ()).throw(OSError("not connected"))
        status = self.bridge.control(True)
        self.assertTrue(status["online"])
        self.assertIsNone(status["signal"])
        self.assertIn("SIGNAL_SOURCE_UNAVAILABLE", status["blockReasons"])
        self.bridge.observe()
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_preflight_waits_for_browser_with_auto_ordering_off(self):
        preflight = self.bridge.status()["preflight"]
        self.assertEqual("READ_ONLY", preflight["mode"])
        self.assertTrue(preflight["noSubmission"])
        self.assertFalse(preflight["browserConnected"])
        self.assertEqual("WAITING_BROWSER", preflight["result"])
        self.assertIsNone(preflight["lastPassed"])

    def test_preflight_can_pass_without_enabling_or_changing_eligibility(self):
        self.clock = START + 60
        original = json.dumps(self.source, sort_keys=True)
        status = self.bridge.report_preflight(browser_report())
        self.assertEqual("READ_ONLY_READY", status["preflight"]["result"])
        self.assertTrue(status["preflight"]["signalFresh"])
        self.assertTrue(status["preflight"]["sideMatches"])
        self.assertFalse(status["requestedEnabled"])
        self.assertFalse(status["effectiveEnabled"])
        self.assertFalse(status["executorReady"])
        self.assertEqual(original, json.dumps(self.source, sort_keys=True))
        self.assertEqual(0, self.bridge.orders()["total"])
        self.assertFalse((self.path / "orders.jsonl").exists())
        record = json.loads((self.path / "preflight.jsonl").read_text())
        self.assertEqual({"periodStart": START, "checkedAt": START + 60,
                          "marketUrl": browser_report()["marketUrl"], "signalSide": "Up",
                          "amountUsd": 1, "noSubmission": True, "schemaVersion": 2,
                          "selectionSource": "HIGHER_BUTTON_PRICE", "upQuoteCents": 53,
                          "downQuoteCents": 48, "preferredSide": "Up"}, record)

    def test_preflight_records_only_once_per_round_and_returns_copies(self):
        self.clock = START + 60
        status = self.bridge.report_preflight(browser_report())
        status["preflight"]["lastPassed"]["amountUsd"] = 999
        threads = [threading.Thread(target=self.bridge.report_preflight, args=(browser_report(),)) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, len((self.path / "preflight.jsonl").read_text().splitlines()))
        self.assertEqual(1, self.bridge.status()["preflight"]["lastPassed"]["amountUsd"])

    def test_preflight_requires_exact_amount_direction_ticket_and_buy_button(self):
        self.clock = START + 60
        for changes, reason in [
            ({"amountUsd": None}, "AMOUNT_NOT_ONE_USD"), ({"amountUsd": 10}, "AMOUNT_NOT_ONE_USD"),
            ({"selectedSide": None}, "SIDE_MISMATCH"), ({"selectedSide": "Down"}, "SIDE_MISMATCH"),
            ({"ticketStatus": "FAIL"}, "TICKET_CHECK_FAILED"), ({"buyButtonEnabled": False}, "BUY_BUTTON_DISABLED"),
            ({"navigation": "MISMATCH"}, "MARKET_NOT_CURRENT"),
        ]:
            with self.subTest(changes=changes):
                preflight = self.bridge.report_preflight(browser_report(**changes))["preflight"]
                self.assertEqual("BLOCKED", preflight["result"])
                self.assertIn(reason, preflight["reasons"])
                self.assertIsNone(preflight["lastPassed"])
        self.assertFalse((self.path / "preflight.jsonl").exists())

    def test_preflight_whitelist_urls_types_and_report_time_are_strict(self):
        self.clock = START + 60
        scenarios = [
            {"schemaVersion": True}, {"schemaVersion": 3}, {"extra": "field"},
            {"marketUrl": f"https://future.news.evil/zh/event/btc-updown-5m-{START}"},
            {"marketUrl": f"http://future.news/zh/event/btc-updown-5m-{START}"},
            {"marketUrl": f"https://user:pass@future.news/zh/event/btc-updown-5m-{START}"},
            {"marketUrl": browser_report()["marketUrl"] + "?account=x"},
            {"marketUrl": browser_report()["marketUrl"] + "#fragment"},
            {"pagePeriodStart": START + 1}, {"pagePeriodStart": START - 300},
            {"checkedAt": START + 64}, {"checkedAt": float("nan")},
            {"checkedAt": 10 ** 500}, {"amountUsd": 10 ** 500},
            {"amountUsd": True}, {"amountUsd": float("inf")}, {"amountUsd": -1},
            {"navigation": "UNKNOWN"}, {"ticketStatus": "UNKNOWN"},
            {"selectedSide": "BUY"}, {"buyButtonEnabled": 1},
        ]
        for changes in scenarios:
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.bridge.report_preflight(browser_report(**changes))
        report = browser_report()
        del report["amountUsd"]
        with self.assertRaises(ValueError):
            self.bridge.report_preflight(report)
        self.assertFalse(self.bridge.status()["preflight"]["browserConnected"])

    def test_preflight_report_expires_and_signal_never_outlives_entry_window(self):
        self.clock = START + 60
        self.bridge.report_preflight(browser_report())
        self.clock = START + 65.001
        self.source["server_time"] = self.clock
        preflight = self.bridge.status()["preflight"]
        self.assertFalse(preflight["browserConnected"])
        self.assertFalse(preflight["signalFresh"])
        self.assertEqual("WAITING_BROWSER", preflight["result"])
        self.clock = START + 80
        self.source["server_time"] = self.clock
        self.source["signal"]["price_observed_at"] = self.clock
        preflight = self.bridge.report_preflight(browser_report(self.clock))["preflight"]
        self.assertFalse(preflight["signalFresh"])
        self.assertEqual("BLOCKED", preflight["result"])
        self.assertIsNotNone(preflight["lastPassed"])

    def test_preflight_rejects_stopped_disconnected_and_wrong_twap_signal(self):
        self.clock = START + 60
        for changes in ({"feed_status": "UNAVAILABLE"}, {"status": "STOPPED"},
                        {"schema_version": 2}, {"live_enabled": True}):
            original = self.source
            self.source = {**source(), **changes}
            preflight = self.bridge.report_preflight(browser_report())["preflight"]
            self.assertEqual("BLOCKED", preflight["result"])
            self.assertIsNone(preflight["lastPassed"])
            self.source = original
        self.source["signal"]["twap_lookback_seconds"] = 30
        self.assertEqual("BLOCKED", self.bridge.report_preflight(browser_report())["preflight"]["result"])
        self.assertFalse((self.path / "preflight.jsonl").exists())

    def test_preflight_restart_clears_browser_but_retains_verified_last_pass(self):
        self.clock = START + 60
        passed = self.bridge.report_preflight(browser_report())["preflight"]["lastPassed"]
        restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        preflight = restored.status()["preflight"]
        self.assertEqual("WAITING_BROWSER", preflight["result"])
        self.assertFalse(preflight["browserConnected"])
        self.assertIsNone(preflight["checkedAt"])
        self.assertEqual(passed, preflight["lastPassed"])
        restored.report_preflight(browser_report())
        self.assertEqual(1, len((self.path / "preflight.jsonl").read_text().splitlines()))

    def test_legacy_preflight_pass_history_keeps_its_original_signal_meaning_and_bytes(self):
        self.clock = START + 60
        legacy = {"periodStart": START, "checkedAt": self.clock, "marketUrl": browser_report()["marketUrl"],
                  "signalSide": "Up", "amountUsd": 1, "noSubmission": True}
        ledger = self.path / "preflight.jsonl"
        ledger.write_text(json.dumps(legacy) + "\n")
        original = ledger.read_bytes()
        restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        status = restored.report_preflight(browser_report(upQuoteCents=12, downQuoteCents=88, selectedSide="Down"))
        self.assertEqual("READ_ONLY_READY", status["preflight"]["result"])
        self.assertEqual("Down", status["preflight"]["preferredSide"])
        self.assertEqual(legacy, status["preflight"]["lastPassed"])
        self.assertEqual(original, ledger.read_bytes())

    def test_new_preflight_pass_quote_proof_is_strict_and_flat_reference_can_be_retained(self):
        self.clock = START + 60
        self.source["signal"].update(side=None, current_price=83000)
        record = self.bridge.report_preflight(browser_report(upQuoteCents=12, downQuoteCents=88,
                                                            selectedSide="Down"))["preflight"]["lastPassed"]
        self.assertIsNone(record["signalSide"])
        restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        self.assertIsNone(restored.preflight_error)
        self.assertEqual(record, restored.status()["preflight"]["lastPassed"])
        ledger = self.path / "preflight.jsonl"
        for changes in ({"preferredSide": "Up"}, {"upQuoteCents": True}, {"downQuoteCents": 101},
                        {"selectionSource": "CHAINLINK"}, {"schemaVersion": True}, {"schemaVersion": 1}):
            with self.subTest(changes=changes):
                ledger.write_text(json.dumps({**record, **changes}) + "\n")
                restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
                self.assertEqual("PREFLIGHT_LEDGER_INVALID", restored.preflight_error)

    def test_preflight_corrupt_ledger_blocks_only_preflight_and_keeps_original_bytes(self):
        self.load_legacy_and_observe()
        ledger = self.path / "preflight.jsonl"
        ledger.write_text('{"broken":')
        original = ledger.read_bytes()
        restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        preflight = restored.report_preflight(browser_report())["preflight"]
        self.assertEqual("BLOCKED", preflight["result"])
        self.assertIn("PREFLIGHT_LEDGER_INVALID", preflight["reasons"])
        self.assertEqual(1, restored.orders()["total"])
        self.assertIsNone(restored.storage_error)
        self.assertEqual(original, ledger.read_bytes())

    def test_preflight_write_is_fsynced_and_failure_cannot_claim_pass(self):
        self.clock = START + 60
        with patch("future_btc5m_bridge.os.fsync", side_effect=OSError("disk failure")):
            preflight = self.bridge.report_preflight(browser_report())["preflight"]
        self.assertEqual("BLOCKED", preflight["result"])
        self.assertIn("PREFLIGHT_LEDGER_WRITE_FAILED", preflight["reasons"])
        self.assertIsNone(preflight["lastPassed"])
        self.assertIsNone(self.bridge.storage_error)
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_preflight_old_market_or_out_of_order_report_cannot_override_current_facts(self):
        self.clock = START + 60
        self.bridge.report_preflight(browser_report())
        with self.assertRaises(ValueError):
            self.bridge.report_preflight(browser_report(START + 59))
        old_url = f"https://future.news/event/btc-updown-5m-{START - 300}"
        preflight = self.bridge.report_preflight(browser_report(
            navigation="ENDED", marketUrl=old_url, pagePeriodStart=START - 300))["preflight"]
        self.assertTrue(preflight["browserConnected"])
        self.assertEqual("BLOCKED", preflight["result"])
        self.assertIn("MARKET_NOT_CURRENT", preflight["reasons"])
        self.assertEqual(1, len((self.path / "preflight.jsonl").read_text().splitlines()))

    def test_preflight_forged_pass_extra_fields_or_duplicate_round_fail_closed(self):
        self.clock = START + 60
        record = self.bridge.report_preflight(browser_report())["preflight"]["lastPassed"]
        ledger = self.path / "preflight.jsonl"
        for rows in ([{**record, "noSubmission": False}], [{**record, "amountUsd": 5}],
                     [{**record, "platformOrderId": "fake"}], [record, record]):
            with self.subTest(rows=rows):
                ledger.write_text("".join(json.dumps(row) + "\n" for row in rows))
                restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
                preflight = restored.report_preflight(browser_report())["preflight"]
                self.assertEqual("BLOCKED", preflight["result"])
                self.assertIn("PREFLIGHT_LEDGER_INVALID", preflight["reasons"])
                self.assertIsNone(preflight["lastPassed"])
                self.assertEqual(0, restored.orders()["total"])

    def test_preflight_signal_appearing_after_report_is_checked_without_restarting_ordering(self):
        self.clock = START + 60
        saved = self.source
        self.source = {**source(), "signal": None}
        self.assertEqual("BLOCKED", self.bridge.report_preflight(browser_report())["preflight"]["result"])
        self.source = saved
        status = self.bridge.observe()
        self.assertEqual("READ_ONLY_READY", status["preflight"]["result"])
        self.assertIsNotNone(status["preflight"]["lastPassed"])
        self.assertFalse(status["requestedEnabled"])
        self.assertEqual(0, self.bridge.orders()["total"])


if __name__ == "__main__":
    unittest.main()
