import json
import sys
import threading
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parent))

from future_btc5m_bridge import FutureBridge, PreparationConflict
from test_future_btc5m_bridge import START, browser_report, legacy_browser_report, source


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

    def offer_quotes(self, up=12, down=88, **changes):
        self.bridge.control(True)
        self.clock = START + 60
        self.source["server_time"] = self.clock
        self.bridge.report_preflight(browser_report(schemaVersion=2, upQuoteCents=up, downQuoteCents=down, **changes))
        return self.bridge.observe()["preparation"]

    def test_higher_down_button_price_wins_even_when_chainlink_direction_is_up(self):
        value = self.offer_quotes()
        intent = value["intent"]
        self.assertEqual("PENDING", value["state"])
        self.assertEqual(2, intent["schemaVersion"])
        self.assertEqual("Down", intent["side"])
        self.assertEqual((12, 88, START + 60, "HIGHER_BUTTON_PRICE"), tuple(intent[field] for field in (
            "upQuoteCents", "downQuoteCents", "quoteObservedAt", "selectionSource")))
        intent = self.bridge.claim_preparation({"schemaVersion": 1, "id": intent["id"]})["preparation"]["intent"]
        status = self.bridge.report_preflight(browser_report(schemaVersion=2, upQuoteCents=12, downQuoteCents=88,
                                                           selectedSide="Down"))
        self.assertEqual("Up", status["preflight"]["signalSide"])
        self.assertEqual("Down", status["preflight"]["preferredSide"])
        self.assertTrue(status["preflight"]["sideMatches"])
        self.assertEqual("READ_ONLY_READY", status["preflight"]["result"])
        value = self.bridge.report_preparation(self.acknowledgement(intent, selectedSide="Down"))["preparation"]
        self.assertEqual("READY", value["state"])
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_higher_up_button_price_wins_even_when_chainlink_direction_is_down(self):
        self.source["signal"].update(side="Down", current_price=82999)
        self.assertEqual("Up", self.offer_quotes(up=88.5, down=13)["intent"]["side"])

    def test_flat_chainlink_is_health_reference_and_does_not_choose_the_button_side(self):
        self.source["signal"].update(side=None, current_price=83000)
        value = self.offer_quotes(selectedSide="Down")
        self.assertEqual("Down", value["intent"]["side"])
        self.assertEqual("READ_ONLY_READY", self.bridge.status()["preflight"]["result"])
        self.assertIsNone(self.bridge.status()["preflight"]["signalSide"])

    def test_missing_chainlink_direction_is_not_an_explicit_flat_reference(self):
        self.source["signal"]["current_price"] = self.source["signal"]["open_price"]
        del self.source["signal"]["side"]
        value = self.offer_quotes(selectedSide="Down")
        self.assertIsNone(value["intent"])
        self.assertEqual(["WAITING_CURRENT_SIGNAL"], value["reasons"])

    def test_legacy_preflight_without_button_quotes_cannot_fallback_to_chainlink(self):
        self.bridge.control(True)
        self.clock = START + 60
        self.bridge.report_preflight(legacy_browser_report())
        value = self.bridge.observe()["preparation"]
        self.assertIsNone(value["intent"])
        self.assertEqual(["BUTTON_QUOTES_UNAVAILABLE"], value["reasons"])
        self.assertIsNone(self.bridge.status()["preflight"]["preferredSide"])

    def test_tied_or_missing_button_quotes_never_offer_a_permission(self):
        for index, (up, down, reason) in enumerate([
            (50, 50, "BUTTON_QUOTES_TIED"), (None, 88, "BUTTON_QUOTES_UNAVAILABLE"),
            (12, None, "BUTTON_QUOTES_UNAVAILABLE"), (None, None, "BUTTON_QUOTES_UNAVAILABLE"),
        ]):
            with self.subTest(up=up, down=down):
                self.bridge = FutureBridge(self.path / str(index), lambda: self.source, lambda: self.clock)
                value = self.offer_quotes(up, down)
                self.assertIsNone(value["intent"])
                self.assertEqual([reason], value["reasons"])

    def test_higher_side_reversal_blocks_claim_and_ready_without_replacing_the_intent(self):
        intent = self.offer_quotes()["intent"]
        self.bridge.report_preflight(browser_report(schemaVersion=2, upQuoteCents=89, downQuoteCents=11))
        with self.assertRaises(ValueError):
            self.bridge.claim_preparation({"schemaVersion": 1, "id": intent["id"]})
        self.assertEqual(["HIGHER_BUTTON_SIDE_CHANGED"], self.bridge.preparation()["preparation"]["reasons"])
        self.bridge.report_preflight(browser_report(schemaVersion=2, upQuoteCents=12, downQuoteCents=88))
        intent = self.bridge.claim_preparation({"schemaVersion": 1, "id": intent["id"]})["preparation"]["intent"]
        self.bridge.report_preflight(browser_report(schemaVersion=2, upQuoteCents=89, downQuoteCents=11, selectedSide="Down"))
        with self.assertRaises(ValueError):
            self.bridge.report_preparation(self.acknowledgement(intent, selectedSide="Down"))
        self.assertEqual("Down", self.bridge.preparation()["preparation"]["lastAttempt"]["side"])
        self.assertIsNone(self.bridge.observe()["preparation"]["intent"])

    def test_fresh_reports_cannot_extend_original_quote_freshness(self):
        intent = self.offer_quotes()["intent"]
        self.clock = START + 65.001
        self.source["server_time"] = self.clock
        self.source["signal"]["price_observed_at"] = self.clock
        self.bridge.report_preflight(browser_report(self.clock, schemaVersion=2, upQuoteCents=12, downQuoteCents=88))
        with self.assertRaises(ValueError):
            self.bridge.claim_preparation({"schemaVersion": 1, "id": intent["id"]})
        value = self.bridge.preparation()["preparation"]
        self.assertIsNone(value["intent"])
        self.assertEqual(["BUTTON_QUOTES_NOT_FRESH"], value["reasons"])

    def test_button_quote_types_bounds_and_required_schema_fields_are_strict(self):
        self.clock = START + 60
        for field in ("upQuoteCents", "downQuoteCents"):
            for value in (True, "88", -0.1, 100.1, float("nan"), float("inf"), [], {}):
                with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                    self.bridge.report_preflight(browser_report(**{field: value}))
        for changes in ({"selectionSource": "HIGHER_BUTTON_PRICE"}, {"schemaVersion": 1}, {"schemaVersion": 3}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                self.bridge.report_preflight(browser_report(**changes))
        report = browser_report()
        del report["upQuoteCents"]
        with self.assertRaises(ValueError):
            self.bridge.report_preflight(report)
        value = self.offer_quotes(up=0, down=100)
        self.assertEqual("Down", value["intent"]["side"])

    def test_button_quotes_allow_at_most_two_decimal_places_without_rounding_inputs(self):
        self.clock = START + 60
        for quote in (0.001, 12.345, 88.251, 99.999):
            with self.subTest(quote=quote), self.assertRaises(ValueError):
                self.bridge.report_preflight(browser_report(upQuoteCents=quote))
        for quote in (0.1, 12.5, 88.25):
            with self.subTest(quote=quote):
                value = self.bridge.report_preflight(browser_report(upQuoteCents=quote))["preflight"]
                self.assertEqual(quote, value["upQuoteCents"])

    def test_button_failure_ack_codes_are_terminal_and_remain_valid_after_restart(self):
        for reason in ("BUTTON_QUOTES_UNAVAILABLE", "BUTTON_QUOTES_TIED", "BUTTON_QUOTES_NOT_FRESH", "HIGHER_BUTTON_SIDE_CHANGED"):
            with self.subTest(reason=reason):
                self.bridge = FutureBridge(self.path / reason, lambda: self.source, lambda: self.clock)
                intent = self.claim()
                value = self.bridge.report_preparation(self.acknowledgement(
                    intent, status="FAILED", amountUsd=None, selectedSide=None, reason=reason))["preparation"]
                self.assertEqual("FAILED", value["state"])
                self.assertEqual(reason, value["lastAttempt"]["reason"])
                self.assertIsNone(value["intent"])
                self.assertIsNone(self.bridge.observe()["preparation"]["intent"])
                restored = FutureBridge(self.path / reason, lambda: self.source, lambda: self.clock)
                self.assertIsNone(restored.preparation_error)
                self.assertEqual(reason, restored.preparation()["preparation"]["lastAttempt"]["reason"])
                self.assertEqual(0, restored.orders()["total"])

    def test_quote_observation_time_uses_server_receipt_and_accepts_legal_browser_clock_skew(self):
        value = self.offer_quotes(checkedAt=START + 63)
        self.assertEqual(START + 60, value["intent"]["quoteObservedAt"])
        self.assertEqual(START + 63, self.bridge.status()["preflight"]["checkedAt"])
        intent = self.bridge.claim_preparation({"schemaVersion": 1, "id": value["intent"]["id"]})["preparation"]["intent"]
        self.bridge.report_preflight(browser_report(START + 63, upQuoteCents=12, downQuoteCents=88, selectedSide="Down"))
        value = self.bridge.report_preparation(self.acknowledgement(intent, checkedAt=START + 63, selectedSide="Down"))["preparation"]
        self.assertEqual("READY", value["state"])

    def test_ready_ack_requires_the_postclaim_read_only_check_to_have_passed(self):
        value = self.offer_quotes(checkedAt=START + 59, selectedSide="Down")
        intent = self.bridge.claim_preparation({"schemaVersion": 1, "id": value["intent"]["id"]})["preparation"]["intent"]
        status = self.bridge.report_preflight(browser_report(START + 59, upQuoteCents=12, downQuoteCents=88,
                                                           selectedSide="Down"))
        self.assertEqual("BLOCKED", status["preflight"]["result"])
        self.assertIn("BROWSER_CHECK_OUTSIDE_ENTRY", status["preflight"]["reasons"])
        with self.assertRaises(ValueError):
            self.bridge.report_preparation(self.acknowledgement(intent, selectedSide="Down"))

    def test_schema1_preparation_history_is_valid_but_never_an_active_quote_permission(self):
        self.offer()
        pending = json.loads((self.path / "preparations.jsonl").read_text())
        pending["schemaVersion"] = 1
        for field in ("upQuoteCents", "downQuoteCents", "quoteObservedAt", "selectionSource"):
            del pending[field]
        claimed = {**pending, "state": "CLAIMED", "claimToken": "0" * 32, "claimedAt": START + 60}
        ready = {**claimed, "state": "READY", "receipt": {"checkedAt": START + 60,
                 "marketUrl": browser_report()["marketUrl"], "amountUsd": 1, "selectedSide": "Up"}}
        for state, rows in (("PENDING", [pending]), ("CLAIMED", [pending, claimed]), ("READY", [pending, claimed, ready])):
            with self.subTest(state=state):
                directory = self.path / state
                directory.mkdir()
                ledger = directory / "preparations.jsonl"
                ledger.write_text("".join(json.dumps(row) + "\n" for row in rows))
                restored = FutureBridge(directory, lambda: self.source, lambda: self.clock)
                restored.control(True)
                restored.report_preflight(browser_report())
                value = restored.observe()["preparation"]
                self.assertNotEqual("READY", value["state"])
                self.assertIsNone(value["intent"])
                self.assertEqual(1, value["lastAttempt"]["schemaVersion"])
                self.assertIsNone(restored.preparation_error)
                with self.assertRaises(PreparationConflict):
                    restored.claim_preparation({"schemaVersion": 1, "id": pending["id"]})
                with self.assertRaises(PreparationConflict):
                    restored.report_preparation(self.acknowledgement(claimed))
                self.assertEqual(0, restored.orders()["total"])

    def test_schema2_history_rejects_mismatched_or_mutated_quote_evidence(self):
        self.offer_quotes()
        ledger = self.path / "preparations.jsonl"
        pending = json.loads(ledger.read_text())
        for changes in ({"side": "Up"}, {"selectionSource": "CHAINLINK"}, {"upQuoteCents": True}, {"upQuoteCents": 12.345},
                        {"downQuoteCents": 101}, {"quoteObservedAt": START + 54}, {"quoteObservedAt": START + 61}):
            with self.subTest(changes=changes):
                ledger.write_text(json.dumps({**pending, **changes}) + "\n")
                restored = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
                self.assertEqual("PREPARATION_LEDGER_INVALID", restored.preparation_error)

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
        self.source["signal"]["price_observed_at"] = START + 58.5
        intent = self.claim()
        self.clock = START + 64
        self.source["server_time"] = self.clock
        self.source["signal"]["price_observed_at"] = self.clock
        self.bridge.report_preflight(browser_report(self.clock))
        with self.assertRaises(ValueError):
            self.bridge.report_preparation(self.acknowledgement(intent))
        value = self.bridge.preparation()["preparation"]
        self.assertEqual("WAITING_SIGNAL", value["state"])
        self.assertIsNone(value["intent"])
        self.assertEqual(START + 58.5, value["lastAttempt"]["priceObservedAt"])

    def test_ready_history_remains_but_current_ready_expires_with_original_sample(self):
        self.source["signal"]["price_observed_at"] = START + 58.5
        intent = self.claim()
        self.bridge.report_preflight(browser_report())
        self.bridge.report_preparation(self.acknowledgement(intent))
        self.clock = START + 64
        self.source["server_time"] = self.clock
        self.source["signal"]["price_observed_at"] = self.clock
        self.bridge.report_preflight(browser_report(self.clock))
        value = self.bridge.preparation()["preparation"]
        self.assertEqual("WAITING_SIGNAL", value["state"])
        self.assertEqual("READY", value["lastAttempt"]["state"])

    def test_chainlink_direction_change_does_not_override_higher_button_side(self):
        intent = self.claim()
        self.source["signal"].update(side="Down", current_price=82999)
        self.bridge.report_preflight(browser_report())
        value = self.bridge.report_preparation(self.acknowledgement(intent))["preparation"]
        self.assertEqual("READY", value["state"])
        self.assertEqual("Up", value["lastAttempt"]["side"])
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
