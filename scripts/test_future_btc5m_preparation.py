import json
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

from future_btc5m_bridge import FutureBridge, PreparationConflict
from test_future_btc5m_bridge import START, browser_report, source


class FuturePreparationTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.clock = START + 10.0
        self.source = source()
        self.source["geoblock"] = {"blocked": True}
        self.bridge = FutureBridge(self.path, lambda: self.source, lambda: self.clock)

    def offer(self):
        self.bridge.control(True)
        self.clock = START + 60
        self.source["server_time"] = self.clock
        self.bridge.report_preflight(browser_report(amountUsd=3, selectedSide="Down"))
        return self.bridge.observe()["preparation"]

    def claim(self):
        intent = self.offer()["intent"]
        result = self.bridge.claim_preparation({"schemaVersion": 1, "id": intent["id"]})
        self.assertEqual("CLAIMED", result["preparation"]["state"])
        return result["preparation"]["intent"]

    def acknowledgement(self, intent, **changes):
        return {"schemaVersion": 1, "id": intent["id"], "claimToken": intent["claimToken"],
                "checkedAt": self.clock, "status": "READY", "marketUrl": browser_report()["marketUrl"],
                "amountUsd": 1, "selectedSide": "Up", "reason": None, "noSubmission": True, **changes}

    def test_default_off_and_reads_never_offer_or_create_order_facts(self):
        result = self.bridge.preparation()
        self.assertEqual("future-btc5m", result["bridgeId"])
        value = result["preparation"]
        self.assertEqual("DISABLED", value["state"])
        self.assertEqual("PREPARE_ONLY", value["mode"])
        self.assertTrue(value["operatorAuthorized"])
        self.assertEqual("USER_REQUEST", value["authorizationSource"])
        self.assertTrue(value["noSubmission"])
        self.assertFalse(value["enabled"])
        self.assertIsNone(value["intent"])
        self.clock = START + 60
        self.bridge.observe()
        self.assertEqual(0, self.bridge.orders()["total"])
        self.assertFalse((self.path / "preparations.jsonl").exists())

    def test_user_authorized_preparation_is_independent_of_legacy_draft_and_geoblock(self):
        before = json.dumps(self.source, sort_keys=True)
        value = self.offer()
        self.assertEqual("PENDING", value["state"])
        intent = value["intent"]
        self.assertEqual(f"future-btc5m-prepare:{START}", intent["id"])
        self.assertEqual(1, intent["amountUsd"])
        self.assertEqual("Up", intent["side"])
        self.assertEqual(START + 80, intent["expiresAt"])
        self.assertEqual("chainlink", intent["priceSource"])
        self.assertEqual(60, intent["twapLookbackSeconds"])
        self.assertIsNone(intent["claimToken"])
        self.assertEqual("UNKNOWN", self.source["future_eligibility"]["status"])
        self.assertEqual(before, json.dumps(self.source, sort_keys=True))
        self.assertEqual(0, self.bridge.orders()["total"])
        self.assertFalse(self.bridge.status()["effectiveEnabled"])
        self.assertFalse(self.bridge.status()["executorReady"])

    def test_intent_is_fsynced_once_per_round_and_only_observe_creates_it(self):
        self.bridge.control(True)
        self.clock = START + 60
        self.bridge.report_preflight(browser_report())
        self.assertIsNone(self.bridge.preparation()["preparation"]["intent"])
        with patch("future_btc5m_bridge.os.fsync") as fsync:
            self.bridge.observe()
            self.assertGreaterEqual(fsync.call_count, 1)
        threads = [threading.Thread(target=self.bridge.observe) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, len((self.path / "preparations.jsonl").read_text().splitlines()))
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_current_browser_ticket_is_required_but_amount_and_direction_need_not_match_yet(self):
        self.bridge.control(True)
        self.clock = START + 60
        self.assertEqual("WAITING_BROWSER", self.bridge.observe()["preparation"]["state"])
        self.bridge.report_preflight(browser_report(ticketStatus="FAIL"))
        self.assertIsNone(self.bridge.observe()["preparation"]["intent"])
        self.bridge.report_preflight(browser_report(amountUsd=0, selectedSide="Down", buyButtonEnabled=False))
        self.assertEqual("PENDING", self.bridge.observe()["preparation"]["state"])

    def test_frozen_wrong_source_wrong_direction_and_out_of_window_signals_never_offer(self):
        for index, change in enumerate([
            {"feed_status": "UNAVAILABLE"}, {"server_time": START + 56},
            {"signal": {**source()["signal"], "price_observed_at": START + 54}},
            {"signal": {**source()["signal"], "side": "Down"}},
            {"signal": {**source()["signal"], "open_price_source": "legacy"}},
            {"period_start": START - 300},
        ]):
            with self.subTest(change=change):
                current = {**source(), **change}
                clock = [START + 10]
                bridge = FutureBridge(self.path / str(index), lambda: current, lambda: clock[0])
                bridge.control(True)
                clock[0] = START + 60
                bridge.report_preflight(browser_report())
                self.assertIsNone(bridge.observe()["preparation"]["intent"])
        self.clock = START + 80
        self.bridge.control(True)
        self.bridge.report_preflight(browser_report(self.clock))
        self.assertIsNone(self.bridge.observe()["preparation"]["intent"])

    def test_first_claim_returns_one_write_permit_and_repeated_claim_never_reissues_it(self):
        intent = self.claim()
        self.assertRegex(intent["claimToken"], r"^[0-9a-f]{32}$")
        payload = {"schemaVersion": 1, "id": intent["id"]}
        with self.assertRaises(ValueError):
            self.bridge.claim_preparation(payload)
        self.assertEqual(intent, self.bridge.preparation()["preparation"]["intent"])
        self.assertEqual(2, len((self.path / "preparations.jsonl").read_text().splitlines()))

    def test_concurrent_claims_produce_only_one_permit(self):
        intent = self.offer()["intent"]
        successes = []
        failures = []

        def claim():
            try:
                successes.append(self.bridge.claim_preparation({"schemaVersion": 1, "id": intent["id"]}))
            except ValueError:
                failures.append(True)

        threads = [threading.Thread(target=claim) for _ in range(8)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        self.assertEqual(1, len(successes))
        self.assertEqual(7, len(failures))

    def test_claim_rechecks_signal_browser_stop_and_disabled_control(self):
        intent = self.offer()["intent"]
        self.clock = START + 65.001
        self.source["server_time"] = self.clock
        with self.assertRaises(ValueError):
            self.bridge.claim_preparation({"schemaVersion": 1, "id": intent["id"]})
        self.clock = START + 60
        self.source["server_time"] = self.clock
        self.bridge.control(False)
        with self.assertRaises(ValueError):
            self.bridge.claim_preparation({"schemaVersion": 1, "id": intent["id"]})
        self.bridge.control(True)
        self.bridge.report_preflight(browser_report())
        self.assertIsNone(self.bridge.observe()["preparation"]["intent"])

    def test_stop_revokes_pending_and_claimed_intents_without_recovery_writes(self):
        intent = self.claim()
        (self.path / "STOP").touch()
        value = self.bridge.status()["preparation"]
        self.assertFalse(value["enabled"])
        self.assertIsNone(value["intent"])
        self.assertEqual("REVOKED", value["lastAttempt"]["state"])
        with self.assertRaises(ValueError):
            self.bridge.report_preparation(self.acknowledgement(intent))
        (self.path / "STOP").unlink()
        self.bridge.control(True)
        self.assertIsNone(self.bridge.observe()["preparation"]["intent"])

    def test_restart_defaults_off_and_never_restores_an_old_pending_or_claimed_permit(self):
        intent = self.claim()
        restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        value = restored.preparation()["preparation"]
        self.assertFalse(value["enabled"])
        self.assertIsNone(value["intent"])
        restored.control(True)
        restored.report_preflight(browser_report())
        self.assertIsNone(restored.observe()["preparation"]["intent"])
        with self.assertRaises(ValueError):
            restored.claim_preparation({"schemaVersion": 1, "id": intent["id"]})
        with self.assertRaises(ValueError):
            restored.report_preparation(self.acknowledgement(intent))

    def test_expired_or_unknown_claim_receipt_is_not_reissued_or_an_order(self):
        intent = self.claim()
        self.clock = START + 80
        self.source["server_time"] = self.clock
        self.source["signal"]["price_observed_at"] = self.clock
        value = self.bridge.observe()["preparation"]
        self.assertEqual("RECEIPT_UNKNOWN", value["state"])
        self.assertIsNone(value["intent"])
        with self.assertRaises(ValueError):
            self.bridge.report_preparation(self.acknowledgement(intent))
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_ready_receipt_requires_claim_token_exact_fields_current_ticket_and_time(self):
        intent = self.claim()
        self.bridge.report_preflight(browser_report())
        for change in [
            {"claimToken": "0" * 32}, {"extra": "field"}, {"schemaVersion": True},
            {"noSubmission": False}, {"amountUsd": 2}, {"amountUsd": True},
            {"amountUsd": float("nan")}, {"selectedSide": "Down"},
            {"marketUrl": browser_report()["marketUrl"] + "?account=x"},
            {"checkedAt": START + 64}, {"status": "FILLED"}, {"reason": "raw DOM text"},
        ]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.bridge.report_preparation(self.acknowledgement(intent, **change))
        self.bridge.report_preflight(browser_report(selectedSide="Down"))
        with self.assertRaises(ValueError):
            self.bridge.report_preparation(self.acknowledgement(intent))

    def test_ready_receipt_is_preparation_history_and_never_submission_or_fill(self):
        intent = self.claim()
        self.bridge.report_preflight(browser_report())
        value = self.bridge.report_preparation(self.acknowledgement(intent))["preparation"]
        self.assertEqual("READY", value["state"])
        self.assertIsNone(value["intent"])
        self.assertEqual("READY", value["lastAttempt"]["state"])
        self.assertEqual(1, value["lastAttempt"]["receipt"]["amountUsd"])
        self.assertTrue(value["lastAttempt"]["noSubmission"])
        self.assertEqual(0, self.bridge.orders()["total"])
        self.assertFalse((self.path / "orders.jsonl").exists())
        with self.assertRaises(ValueError):
            self.bridge.report_preparation(self.acknowledgement(intent))
        self.bridge.report_preflight(browser_report(amountUsd=2))
        value = self.bridge.preparation()["preparation"]
        self.assertNotEqual("READY", value["state"])
        self.assertEqual("READY", value["lastAttempt"]["state"])

    def test_fresh_new_sample_cannot_extend_the_original_intent_or_ready_receipt(self):
        intent = self.claim()
        self.clock = START + 65.001
        self.source["server_time"] = self.clock
        self.source["signal"]["price_observed_at"] = self.clock
        self.bridge.report_preflight(browser_report(self.clock))
        with self.assertRaises(ValueError):
            self.bridge.report_preparation(self.acknowledgement(intent))
        value = self.bridge.preparation()["preparation"]
        self.assertEqual("WAITING_SIGNAL", value["state"])
        self.assertIsNone(value["intent"])
        self.assertEqual(START + 60, value["lastAttempt"]["priceObservedAt"])

    def test_ready_history_remains_but_current_ready_expires_with_original_sample(self):
        intent = self.claim()
        self.bridge.report_preflight(browser_report())
        self.bridge.report_preparation(self.acknowledgement(intent))
        self.clock = START + 65.001
        self.source["server_time"] = self.clock
        self.source["signal"]["price_observed_at"] = self.clock
        self.bridge.report_preflight(browser_report(self.clock))
        value = self.bridge.preparation()["preparation"]
        self.assertEqual("WAITING_SIGNAL", value["state"])
        self.assertEqual("READY", value["lastAttempt"]["state"])

    def test_direction_change_revokes_current_permission_and_ready_confirmation(self):
        intent = self.claim()
        self.source["signal"].update(side="Down", current_price=82999)
        self.bridge.report_preflight(browser_report())
        with self.assertRaises(ValueError):
            self.bridge.report_preparation(self.acknowledgement(intent))
        value = self.bridge.preparation()["preparation"]
        self.assertEqual("WAITING_SIGNAL", value["state"])
        self.assertIsNone(value["intent"])

    def test_ready_requires_a_new_preflight_received_after_the_claim(self):
        intent = self.offer()["intent"]
        self.bridge.report_preflight(browser_report())
        self.clock = START + 61
        self.source["server_time"] = self.clock
        intent = self.bridge.claim_preparation({"schemaVersion": 1, "id": intent["id"]})["preparation"]["intent"]
        with self.assertRaises(ValueError):
            self.bridge.report_preparation(self.acknowledgement(intent))
        self.bridge.report_preflight(browser_report(self.clock))
        self.assertEqual("READY", self.bridge.report_preparation(self.acknowledgement(intent))["preparation"]["state"])

    def test_failed_and_expired_reports_finish_the_attempt_without_retry(self):
        intent = self.claim()
        value = self.bridge.report_preparation(self.acknowledgement(
            intent, status="FAILED", amountUsd=None, selectedSide=None, reason="UNSAFE_DIRECTION_CONTROL"))["preparation"]
        self.assertEqual("FAILED", value["state"])
        self.assertIsNone(value["intent"])
        self.assertIsNone(self.bridge.observe()["preparation"]["intent"])
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_invalid_reason_types_are_rejected_as_invalid_reports(self):
        intent = self.claim()
        for reason in ([], {}, True, 1):
            with self.subTest(reason=reason), self.assertRaises(ValueError):
                self.bridge.report_preparation(self.acknowledgement(intent, status="FAILED", reason=reason))
        self.assertEqual("CLAIMED", self.bridge.preparation()["preparation"]["lastAttempt"]["state"])

    def test_pending_expiry_and_expired_ack_never_restore_a_write_permit(self):
        intent = self.offer()["intent"]
        self.clock = START + 80
        value = self.bridge.observe()["preparation"]
        self.assertEqual("EXPIRED", value["state"])
        self.assertEqual("INTENT_EXPIRED", value["lastAttempt"]["reason"])
        self.assertIsNone(value["lastAttempt"]["claimToken"])
        with self.assertRaises(ValueError):
            self.bridge.claim_preparation({"schemaVersion": 1, "id": intent["id"]})

    def test_premature_expired_ack_is_rejected_and_late_ack_cannot_replace_unknown_receipt(self):
        intent = self.claim()
        with self.assertRaises(ValueError):
            self.bridge.report_preparation(self.acknowledgement(intent, status="EXPIRED", reason="INTENT_EXPIRED"))
        self.assertEqual("CLAIMED", self.bridge.preparation()["preparation"]["lastAttempt"]["state"])
        self.clock = START + 80
        with self.assertRaises(PreparationConflict):
            self.bridge.report_preparation(self.acknowledgement(intent, status="EXPIRED", reason="INTENT_EXPIRED"))
        value = self.bridge.preparation()["preparation"]
        self.assertEqual("RECEIPT_UNKNOWN", value["state"])
        self.assertEqual("PREPARATION_RECEIPT_UNKNOWN", value["lastAttempt"]["reason"])
        self.assertEqual(START + 80, value["lastAttempt"]["updatedAt"])
        self.assertIsNone(value["intent"])
        self.assertIsNone(self.bridge.observe()["preparation"]["intent"])
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_restart_revokes_an_unclaimed_intent_and_next_round_can_offer_once(self):
        intent = self.offer()["intent"]
        restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        self.assertEqual("PROCESS_RESTARTED", restored.preparation()["preparation"]["lastAttempt"]["reason"])
        restored.control(True)
        restored.report_preflight(browser_report())
        self.assertIsNone(restored.observe()["preparation"]["intent"])
        second = START + 300
        self.clock = second + 60
        self.source = source(self.clock)
        self.source["period_start"] = second
        self.source["signal"].update(id=f"5m:{second}", slug=f"btc-updown-5m-{second}",
                                     period_start=second, period_end=second + 300)
        restored.report_preflight(browser_report(self.clock, marketUrl=f"https://future.news/event/btc-updown-5m-{second}",
                                                pagePeriodStart=second))
        value = restored.observe()["preparation"]
        self.assertEqual("PENDING", value["state"])
        self.assertNotEqual(intent["id"], value["intent"]["id"])
        self.assertEqual(0, restored.orders()["total"])

    def test_bad_preparation_ledger_blocks_only_preparation_and_preserves_bytes(self):
        ledger = self.path / "preparations.jsonl"
        ledger.write_text('{"broken":')
        original = ledger.read_bytes()
        restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        restored.control(True)
        self.assertEqual("BLOCKED", restored.preparation()["preparation"]["state"])
        self.assertIn("PREPARATION_LEDGER_INVALID", restored.preparation()["preparation"]["reasons"])
        self.assertIsNone(restored.storage_error)
        self.assertEqual(0, restored.orders()["total"])
        self.assertEqual(original, ledger.read_bytes())

    def test_preflight_write_failure_blocks_ready_even_when_the_browser_report_was_received(self):
        intent = self.claim()
        with patch("future_btc5m_bridge.os.fsync", side_effect=OSError("disk failure")):
            status = self.bridge.report_preflight(browser_report())
        self.assertEqual("BLOCKED", status["preflight"]["result"])
        with self.assertRaises(ValueError):
            self.bridge.report_preparation(self.acknowledgement(intent))
        value = self.bridge.preparation()["preparation"]
        self.assertEqual("BLOCKED", value["state"])
        self.assertEqual(["PREFLIGHT_LEDGER_WRITE_FAILED"], value["reasons"])
        self.assertEqual("CLAIMED", value["lastAttempt"]["state"])
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_corrupt_preflight_history_never_offers_a_preparation_or_rewrites_history(self):
        ledger = self.path / "preflight.jsonl"
        ledger.write_text('{"broken":')
        original = ledger.read_bytes()
        self.bridge = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        value = self.offer()
        self.assertEqual("BLOCKED", value["state"])
        self.assertEqual(["PREFLIGHT_LEDGER_INVALID"], value["reasons"])
        self.assertIsNone(value["intent"])
        self.assertEqual(original, ledger.read_bytes())
        self.assertFalse((self.path / "preparations.jsonl").exists())

    def test_duplicate_or_forged_preparation_events_are_not_replayed(self):
        self.offer()
        ledger = self.path / "preparations.jsonl"
        row = json.loads(ledger.read_text())
        for rows in ([row, row], [{**row, "state": "READY"}], [{**row, "claimToken": "0" * 32}]):
            with self.subTest(rows=rows):
                ledger.write_text("".join(json.dumps(item) + "\n" for item in rows))
                restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
                self.assertEqual("BLOCKED", restored.preparation()["preparation"]["state"])

    def test_ledger_cannot_inject_a_claim_during_revocation_or_extend_freshness(self):
        self.offer()
        ledger = self.path / "preparations.jsonl"
        row = json.loads(ledger.read_text())
        forged_claim = {**row, "state": "CLAIMED", "claimToken": "0" * 32,
                        "claimedAt": START + 66, "updatedAt": START + 66}
        forged_revoke = {**row, "state": "REVOKED", "reason": "PREPARATION_REVOKED",
                         "claimToken": "0" * 32, "claimedAt": START + 60}
        premature_expiry = {**row, "state": "EXPIRED", "reason": "INTENT_EXPIRED"}
        for rows in ([row, forged_claim], [row, forged_revoke], [row, premature_expiry]):
            with self.subTest(rows=rows):
                ledger.write_text("".join(json.dumps(item) + "\n" for item in rows))
                restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
                self.assertEqual("BLOCKED", restored.preparation()["preparation"]["state"])

    def test_failed_preparation_fsync_does_not_return_a_write_permit_or_corrupt_orders(self):
        intent = self.offer()["intent"]
        with patch("future_btc5m_bridge.os.fsync", side_effect=OSError("disk failure")):
            with self.assertRaises(OSError):
                self.bridge.claim_preparation({"schemaVersion": 1, "id": intent["id"]})
        value = self.bridge.preparation()["preparation"]
        self.assertEqual("BLOCKED", value["state"])
        self.assertIn("PREPARATION_LEDGER_WRITE_FAILED", value["reasons"])
        self.assertIsNone(value["intent"])
        self.assertIsNone(self.bridge.storage_error)
        self.assertEqual(0, self.bridge.orders()["total"])


if __name__ == "__main__":
    unittest.main()
