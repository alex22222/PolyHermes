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


if __name__ == "__main__":
    unittest.main()
