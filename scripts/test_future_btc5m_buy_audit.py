import json
import math
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent))

from future_btc5m_assistant import make_server
from future_btc5m_bridge import FutureBridge, PreparationConflict
from test_future_btc5m_bridge import START, browser_report, source


class FutureBuyAuditTest(unittest.TestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name)
        self.clock = START + 10.0
        self.source = source()
        self.bridge = FutureBridge(self.path, lambda: self.source, lambda: self.clock)

    def ready(self):
        self.bridge.control(True)
        self.clock = START + 60
        self.source["server_time"] = self.clock
        self.bridge.report_preflight(browser_report(amountUsd=3, selectedSide="Down"))
        intent = self.bridge.observe()["preparation"]["intent"]
        intent = self.bridge.claim_preparation({"schemaVersion": 1, "id": intent["id"]})["preparation"]["intent"]
        self.bridge.report_preflight(browser_report())
        self.bridge.report_preparation({"schemaVersion": 1, "id": intent["id"], "claimToken": intent["claimToken"],
                                        "checkedAt": self.clock, "status": "READY",
                                        "marketUrl": browser_report()["marketUrl"], "amountUsd": 1,
                                        "selectedSide": intent["side"], "reason": None, "noSubmission": True})
        return self.bridge.preparations[intent["id"]]

    def audit(self, record, **changes):
        attempted = changes.pop("attemptedAt", record["updatedAt"] + 0.5)
        value = {"schemaVersion": 1, "auditId": f"{record['id']}:{math.floor(attempted * 1000)}",
                 "id": record["id"], "claimToken": record["claimToken"], "periodStart": record["periodStart"],
                 "side": record["side"], "amountUsd": 1, "state": "CLICK_ATTEMPTED",
                 "reason": "PLATFORM_RESULT_UNKNOWN", "armedAt": START + 30.0, "attemptedAt": attempted,
                 "marketUrl": browser_report()["marketUrl"], "upQuoteCents": 88, "downQuoteCents": 12,
                 "selectedSide": record["side"], "ticketAmountUsd": 1, "extensionVersion": "0.4.1"}
        value.update(changes)
        return value

    def audit_v2(self, record, **changes):
        return self.audit(record, **{"schemaVersion": 2, "extensionVersion": "0.5.0", "marketUpAskCents": 88.5,
                                     "marketDownAskCents": 12, "marketQuoteObservedAt": record["updatedAt"] + 0.25,
                                     **changes})

    def ledger(self):
        path = self.path / "buy_attempts.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_click_attempt_is_fsynced_bound_to_ready_and_survives_restart(self):
        record = self.ready()
        payload = self.audit(record)
        self.clock += 1
        result = self.bridge.report_buy_attempt(payload)
        self.assertEqual({"bridgeId": "future-btc5m", "auditId": payload["auditId"], "stored": True,
                          "duplicate": False}, result)
        stored = self.ledger()
        self.assertEqual(1, len(stored))
        self.assertEqual({**payload, "receivedAt": self.clock}, stored[0])
        restarted = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        self.assertIsNone(restarted.buy_audit_error)
        self.assertEqual(stored[0], restarted.buy_audits[payload["auditId"]])
        self.assertTrue(restarted.report_buy_attempt(payload)["duplicate"], "outbox resends are idempotent")
        self.assertEqual(1, len(self.ledger()))

    def test_audits_remain_accepted_after_switch_off_and_round_end_and_record_refusals(self):
        record = self.ready()
        self.bridge.control(False)
        self.clock = START + 3600
        blocked = self.audit(record, state="BLOCKED", reason="FINAL_CHECK_FAILED", attemptedAt=record["updatedAt"] + 1)
        self.assertFalse(self.bridge.report_buy_attempt(blocked)["duplicate"])
        clicked = self.audit(record, attemptedAt=record["updatedAt"] + 2)
        self.assertFalse(self.bridge.report_buy_attempt(clicked)["duplicate"])
        self.assertEqual(["BLOCKED", "CLICK_ATTEMPTED"], [item["state"] for item in self.ledger()])

    def test_unbound_malformed_or_reused_audits_are_rejected_without_writing(self):
        with self.assertRaises(PreparationConflict):
            self.bridge.report_buy_attempt(self.audit({"id": f"future-btc5m-prepare:{START}", "claimToken": "a" * 32,
                                                       "periodStart": START, "side": "Up", "updatedAt": START + 61}))
        record = self.ready()
        for change in [{"claimToken": "0" * 32}, {"side": "Down" if record["side"] == "Up" else "Up"},
                       {"attemptedAt": record["expiresAt"] + 6}, {"attemptedAt": record["createdAt"] - 4}]:
            with self.subTest(change=change), self.assertRaises(PreparationConflict):
                self.bridge.report_buy_attempt(self.audit(record, **change))
        payload = self.audit(record)
        for change in [{"extra": 1}, {"schemaVersion": True}, {"amountUsd": 2}, {"state": "FILLED"},
                       {"reason": "raw DOM text"}, {"state": "BLOCKED", "reason": "PLATFORM_RESULT_UNKNOWN"},
                       {"auditId": payload["auditId"] + "0"}, {"marketUrl": payload["marketUrl"] + "?account=x"},
                       {"upQuoteCents": 101}, {"ticketAmountUsd": float("nan")}, {"extensionVersion": "dev"},
                       {"armedAt": payload["attemptedAt"] + 1}, {"periodStart": START + 300}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.bridge.report_buy_attempt({**payload, **change})
        self.bridge.report_buy_attempt(payload)
        with self.assertRaises(PreparationConflict):
            self.bridge.report_buy_attempt({**payload, "upQuoteCents": 87})
        self.assertEqual(1, len(self.ledger()))

    def test_schema2_market_quote_audit_is_stored_beside_v1_and_reloads_mixed(self):
        record = self.ready()
        v1 = self.audit(record, state="BLOCKED", reason="FINAL_CHECK_FAILED")
        v2 = self.audit_v2(record, attemptedAt=record["updatedAt"] + 1)
        self.clock += 1
        for payload in (v1, v2):
            self.assertFalse(self.bridge.report_buy_attempt(payload)["duplicate"])
        stored = self.ledger()
        self.assertEqual([{**v1, "receivedAt": self.clock}, {**v2, "receivedAt": self.clock}], stored)
        restarted = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        self.assertIsNone(restarted.buy_audit_error)
        self.assertEqual({v1["auditId"]: stored[0], v2["auditId"]: stored[1]}, restarted.buy_audits)
        for payload in (v1, v2):
            self.assertTrue(restarted.report_buy_attempt(payload)["duplicate"], "outbox resends are idempotent")
        # The same auditId with another market ask or under the other schema is a reuse, not a resend.
        as_v1 = {**{field: value for field, value in v2.items() if not field.startswith("market")},
                 "schemaVersion": 1, "marketUrl": v2["marketUrl"]}
        as_v2 = {**v1, "schemaVersion": 2, "marketUpAskCents": None, "marketDownAskCents": None,
                 "marketQuoteObservedAt": None}
        for changed in ({**v2, "marketUpAskCents": 88}, {**v2, "marketQuoteObservedAt": None}, as_v1, as_v2):
            with self.subTest(changed=changed), self.assertRaises(PreparationConflict):
                restarted.report_buy_attempt(changed)
        self.assertEqual(2, len(self.ledger()))

    def test_price_gate_refusals_are_blocked_reasons_for_both_schemas_only(self):
        record = self.ready()
        reasons = ("PRICE_BELOW_MIN", "MARKET_QUOTE_UNAVAILABLE", "MARKET_QUOTE_MISMATCH", "PRICE_ABOVE_MAX")
        for index, reason in enumerate(reasons):
            for version in (1, 2):
                with self.subTest(reason=reason, version=version):
                    attempted = record["updatedAt"] + 1 + (2 * index + version) * 0.01
                    if version == 1:
                        payload = self.audit(record, state="BLOCKED", reason=reason, attemptedAt=attempted)
                    elif reason == "MARKET_QUOTE_UNAVAILABLE":
                        payload = self.audit_v2(record, state="BLOCKED", reason=reason, attemptedAt=attempted,
                                                marketUpAskCents=None, marketDownAskCents=None,
                                                marketQuoteObservedAt=None)
                    else:
                        payload = self.audit_v2(record, state="BLOCKED", reason=reason, attemptedAt=attempted)
                    with self.assertRaises(ValueError):
                        self.bridge.report_buy_attempt({**payload, "state": "CLICK_ATTEMPTED"})
                    self.assertFalse(self.bridge.report_buy_attempt(payload)["duplicate"])
        self.assertEqual([(reason, version) for reason in reasons for version in (1, 2)],
                         [(item["reason"], item["schemaVersion"]) for item in self.ledger()])

    def test_malformed_schema2_market_fields_are_rejected_without_writing(self):
        record = self.ready()
        payload = self.audit_v2(record)
        for change in [{"marketUpAskCents": 101}, {"marketUpAskCents": -1}, {"marketDownAskCents": 12.345},
                       {"marketDownAskCents": True}, {"marketUpAskCents": "88"}, {"marketUpAskCents": float("nan")},
                       {"marketDownAskCents": float("inf")}, {"marketQuoteObservedAt": float("nan")},
                       {"marketQuoteObservedAt": float("-inf")}, {"marketQuoteObservedAt": "now"},
                       {"marketQuoteObservedAt": True}, {"marketQuoteObservedAt": [1]},
                       {"schemaVersion": 3}, {"schemaVersion": 2.0}, {"schemaVersion": True}, {"schemaVersion": "2"},
                       {"schemaVersion": None}, {"schemaVersion": 1}, {"extra": 1},
                       {"state": "BLOCKED", "reason": "PRICE_TOO_HIGH"}]:
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.bridge.report_buy_attempt({**payload, **change})
        for field in ("marketUpAskCents", "marketDownAskCents", "marketQuoteObservedAt"):
            with self.subTest(missing=field), self.assertRaises(ValueError):
                self.bridge.report_buy_attempt({key: value for key, value in payload.items() if key != field})
            with self.subTest(v1_with=field), self.assertRaises(ValueError):
                self.bridge.report_buy_attempt({**self.audit(record), field: None})
        for value in ([], "x", None, 2):
            with self.subTest(payload=value), self.assertRaises(ValueError):
                self.bridge.report_buy_attempt(value)
        self.assertEqual([], self.ledger())

    def test_ledger_lines_must_carry_exactly_their_own_schema_fields(self):
        record = self.ready()
        v1 = {**self.audit(record), "receivedAt": self.clock}
        v2 = {**self.audit_v2(record, attemptedAt=record["updatedAt"] + 1), "receivedAt": self.clock}
        for line in ({**v2, "schemaVersion": 1}, {**v1, "schemaVersion": 2},
                     {field: value for field, value in v2.items() if field != "marketQuoteObservedAt"},
                     {field: value for field, value in v2.items() if field != "receivedAt"},
                     {**v2, "marketDownAskCents": 100.5}, {**v2, "schemaVersion": 3}):
            with self.subTest(line=line):
                (self.path / "buy_attempts.jsonl").write_text(json.dumps(v1) + "\n" + json.dumps(line) + "\n")
                self.assertEqual("BUY_AUDIT_LEDGER_INVALID",
                                 FutureBridge(self.path, lambda: self.source, lambda: self.clock).buy_audit_error)

    def test_a_corrupt_ledger_blocks_new_audits_instead_of_overwriting_history(self):
        (self.path / "buy_attempts.jsonl").write_text("{not json\n")
        bridge = FutureBridge(self.path, lambda: self.source, lambda: self.clock)
        self.assertEqual("BUY_AUDIT_LEDGER_INVALID", bridge.buy_audit_error)
        self.bridge = bridge
        record = self.ready()
        with self.assertRaises(OSError):
            bridge.report_buy_attempt(self.audit(record))
        self.assertEqual("{not json\n", (self.path / "buy_attempts.jsonl").read_text())


class FutureBuyAuditHttpTest(FutureBuyAuditTest):
    def post(self, payload, **headers):
        server = make_server(type("S", (), {"status": lambda self: {}})(), ("127.0.0.1", 0), bridge=self.bridge)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            request = urllib.request.Request(f"http://127.0.0.1:{server.server_port}/bridge/preparation/buy-audit",
                                             data=json.dumps(payload).encode(), headers={
                                                 "Content-Type": "application/json", **headers})
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            try:
                with opener.open(request, timeout=2) as response:
                    return response.status, json.loads(response.read())
            except urllib.error.HTTPError as error:
                error.close()
                return error.code, None
        finally:
            server.shutdown()
            server.server_close()

    def test_extension_route_requires_the_preparation_header_and_rejects_websites(self):
        record = self.ready()
        payload = self.audit(record)
        self.assertEqual(403, self.post(payload)[0])
        self.assertEqual(403, self.post(payload, **{"X-PolyHermes-Future-Preparation": "1",
                                                    "Origin": "https://future.news"})[0])
        status, body = self.post(payload, **{"X-PolyHermes-Future-Preparation": "1",
                                             "Origin": "chrome-extension://" + "a" * 32})
        self.assertEqual((200, False), (status, body["duplicate"]))
        self.assertEqual(400, self.post({**payload, "state": "FILLED"},
                                        **{"X-PolyHermes-Future-Preparation": "1"})[0])

    def test_schema2_audit_fits_the_route_body_limit(self):
        record = self.ready()
        payload = self.audit_v2(record, state="BLOCKED", reason="MARKET_QUOTE_MISMATCH",
                                upQuoteCents=99.99, downQuoteCents=10.01, marketUpAskCents=99.99,
                                marketDownAskCents=10.01, marketQuoteObservedAt=record["updatedAt"] + 0.123456789,
                                ticketAmountUsd=1234.56, extensionVersion="100.100.100")
        self.assertLess(len(json.dumps(payload).encode()), 1500)
        status, body = self.post(payload, **{"X-PolyHermes-Future-Preparation": "1"})
        self.assertEqual((200, False), (status, body["duplicate"]))
        self.assertEqual(2, self.ledger()[0]["schemaVersion"])


if __name__ == "__main__":
    unittest.main()
