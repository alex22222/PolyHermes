import json
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent))

from future_btc5m_assistant import make_server
from future_btc5m_bridge import FutureBridge
from test_future_btc5m_bridge import START, browser_report, source


class Source:
    def status(self):
        return {"mode": "ASSIST_ONLY", "status": "WAITING", "feed_status": "CURRENT"}


class FutureBridgeHttpTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.bridge = FutureBridge(Path(directory.name), Source().status)
        self.server = make_server(Source(), ("127.0.0.1", 0), bridge=self.bridge)
        thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.url = f"http://127.0.0.1:{self.server.server_port}"
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def request(self, path, body=None, headers=None):
        request = urllib.request.Request(self.url + path, data=body, headers=headers or {})
        try:
            with self.opener.open(request, timeout=2) as response:
                return response.status, json.loads(response.read()), dict(response.headers)
        except urllib.error.HTTPError as error:
            try:
                return error.code, None, dict(error.headers)
            finally:
                error.close()

    def control(self, payload, **headers):
        return self.request("/bridge/control", json.dumps(payload).encode(), {
            "Content-Type": "application/json", "X-PolyHermes-Future-Control": "1", **headers})

    def preflight(self, payload=None, **headers):
        import time
        now = time.time()
        start = int(now // 300) * 300
        payload = payload if payload is not None else {
            "schemaVersion": 1, "marketUrl": f"https://future.news/zh/event/btc-updown-5m-{start}",
            "pagePeriodStart": start, "checkedAt": now, "navigation": "CURRENT",
            "ticketStatus": "PASS", "amountUsd": 1, "selectedSide": "Up", "buyButtonEnabled": True,
        }
        return self.request("/bridge/preflight", json.dumps(payload).encode(), {
            "Content-Type": "application/json", "X-PolyHermes-Future-Preflight": "1", **headers})

    def preparation(self, path="/bridge/preparation", payload=None, **headers):
        return self.request(path, None if payload is None else json.dumps(payload).encode(), {
            "Content-Type": "application/json", "X-PolyHermes-Future-Preparation": "1", **headers})

    def test_status_and_orders_are_real_disabled_empty_state(self):
        code, status, headers = self.request("/bridge/status")
        self.assertEqual(200, code)
        self.assertFalse(status["requestedEnabled"])
        self.assertFalse(status["effectiveEnabled"])
        self.assertEqual("no-store", headers["Cache-Control"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertEqual({"list": [], "total": 0, "page": 1, "size": 20}, self.request("/bridge/orders")[1])

    def test_control_requires_header_and_rejects_browser_origin(self):
        self.assertEqual(403, self.request("/bridge/control", b'{"enabled":true}', {"Content-Type": "application/json"})[0])
        self.assertEqual(403, self.control({"enabled": True}, Origin="https://future.news")[0])
        self.assertFalse(self.bridge.status()["requestedEnabled"])

    def test_exact_boolean_only_and_fixed_amount(self):
        for payload in ({}, {"enabled": "true"}, {"enabled": 1}, {"enabled": None},
                        {"enabled": True, "amountUsd": 2}, [True]):
            with self.subTest(payload=payload):
                self.assertEqual(400, self.control(payload)[0])
        self.assertFalse(self.bridge.status()["requestedEnabled"])
        status = self.control({"enabled": True})[1]
        self.assertTrue(status["requestedEnabled"])
        self.assertFalse(status["effectiveEnabled"])
        self.assertEqual("BLOCKED", status["mode"])
        self.assertEqual(1, status["amountUsd"])
        self.assertFalse(self.control({"enabled": False})[1]["requestedEnabled"])

    def test_limits_invalid_json_and_host(self):
        headers = {"Content-Type": "application/json", "X-PolyHermes-Future-Control": "1"}
        self.assertEqual(400, self.request("/bridge/control", b"{", headers)[0])
        self.assertEqual(400, self.request("/bridge/control", b"x" * 257, headers)[0])
        self.assertEqual(415, self.request("/bridge/control", b'{"enabled":true}', {"X-PolyHermes-Future-Control": "1"})[0])
        self.assertEqual(403, self.request("/bridge/status", headers={"Host": "attacker.invalid"})[0])
        self.assertEqual(403, self.control({"enabled": True}, Host="attacker.invalid")[0])
        self.assertFalse(self.bridge.status()["requestedEnabled"])

    def test_list_query_validation_and_unknown_detail(self):
        for query in ("page=0", "size=101", "page=x", "page=1&page=2", "status=OTHER", "amount=2"):
            with self.subTest(query=query):
                self.assertEqual(400, self.request("/bridge/orders?" + query)[0])
        self.assertEqual(200, self.request("/bridge/orders?page=1&size=10&status=SKIPPED")[0])
        self.assertEqual(404, self.request("/bridge/orders/future-btc5m%3A1791706800")[0])
        self.bridge.storage_error = "ORDER_LEDGER_INVALID"
        self.assertEqual(503, self.request("/bridge/orders")[0])
        self.assertEqual(503, self.request("/bridge/orders/future-btc5m%3A1791706800")[0])
        self.assertEqual("ORDER_LEDGER_INVALID", self.request("/bridge/status")[1]["reason"])

    def test_no_trade_submit_and_existing_read_routes_still_work(self):
        self.assertEqual(404, self.request("/submit", b"{}")[0])
        self.assertEqual("ASSIST_ONLY", self.request("/status")[1]["mode"])
        self.assertEqual(404, self.request("/unknown")[0])

    def test_preflight_accepts_extension_origin_or_no_origin_with_fixed_header(self):
        for headers in ({}, {"Origin": "chrome-extension://" + "a" * 32}):
            with self.subTest(headers=headers):
                code, status, response_headers = self.preflight(**headers)
                self.assertEqual(200, code)
                self.assertTrue(status["preflight"]["browserConnected"])
                self.assertTrue(status["preflight"]["noSubmission"])
                self.assertFalse(status["requestedEnabled"])
                self.assertFalse(status["effectiveEnabled"])
                self.assertEqual("no-store", response_headers["Cache-Control"])
                self.assertNotIn("Access-Control-Allow-Origin", response_headers)
        self.assertEqual(0, self.bridge.orders()["total"])

    def test_preflight_rejects_web_origins_bad_extension_id_and_wrong_host(self):
        for origin in ("https://future.news", "https://attacker.invalid", "null",
                       "chrome-extension://" + "z" * 32, "chrome-extension://" + "a" * 31,
                       "chrome-extension://" + "a" * 32 + "/page"):
            with self.subTest(origin=origin):
                self.assertEqual(403, self.preflight(Origin=origin)[0])
        self.assertEqual(403, self.preflight(Host="attacker.invalid")[0])
        self.assertFalse(self.bridge.status()["preflight"]["browserConnected"])
        self.assertEqual(403, self.control({"enabled": True}, Origin="chrome-extension://" + "a" * 32)[0])

    def test_preflight_requires_own_header_json_and_body_limit(self):
        headers = {"Content-Type": "application/json", "X-PolyHermes-Future-Preflight": "1"}
        self.assertEqual(403, self.request("/bridge/preflight", b"{}", {"Content-Type": "application/json"})[0])
        self.assertEqual(415, self.request("/bridge/preflight", b"{}", {"X-PolyHermes-Future-Preflight": "1"})[0])
        self.assertEqual(400, self.request("/bridge/preflight", b"{", headers)[0])
        self.assertEqual(400, self.request("/bridge/preflight", b"x" * 1501, headers)[0])
        self.assertEqual(400, self.preflight({"schemaVersion": 1})[0])
        self.assertFalse(self.bridge.status()["preflight"]["browserConnected"])

    def test_preflight_rejects_duplicate_json_fields(self):
        import time
        now = time.time()
        start = int(now // 300) * 300
        payload = {"schemaVersion": 1, "marketUrl": f"https://future.news/event/btc-updown-5m-{start}",
                   "pagePeriodStart": start, "checkedAt": now, "navigation": "CURRENT",
                   "ticketStatus": "PASS", "amountUsd": 1, "selectedSide": "Up", "buyButtonEnabled": True}
        body = (json.dumps(payload)[:-1] + ', "schemaVersion": 1}').encode()
        self.assertEqual(400, self.request("/bridge/preflight", body, {
            "Content-Type": "application/json", "X-PolyHermes-Future-Preflight": "1"})[0])
        self.assertFalse(self.bridge.status()["preflight"]["browserConnected"])

    def test_preparation_read_and_atomic_claim_ack_never_add_order_facts(self):
        result = self.preparation()
        self.assertEqual(200, result[0])
        self.assertEqual("DISABLED", result[1]["preparation"]["state"])
        self.assertTrue(result[1]["preparation"]["noSubmission"])
        self.assertNotIn("Access-Control-Allow-Origin", result[2])
        current = source()
        clock = [START + 10]
        self.bridge.status_fn = lambda: current
        self.bridge.now_fn = lambda: clock[0]
        self.assertEqual(200, self.control({"enabled": True})[0])
        clock[0] = START + 60
        self.preflight(browser_report())
        intent = self.bridge.observe()["preparation"]["intent"]
        payload = {"schemaVersion": 1, "id": intent["id"]}
        claimed = self.preparation("/bridge/preparation/claim", payload)
        self.assertEqual(200, claimed[0])
        self.assertEqual(409, self.preparation("/bridge/preparation/claim", payload)[0])
        token = claimed[1]["preparation"]["intent"]["claimToken"]
        ack = {"schemaVersion": 1, "id": intent["id"], "claimToken": token, "checkedAt": clock[0],
               "status": "READY", "marketUrl": browser_report()["marketUrl"], "amountUsd": 1,
               "selectedSide": "Up", "reason": None, "noSubmission": True}
        self.assertEqual(400, self.preparation("/bridge/preparation/ack", {
            **ack, "status": "EXPIRED", "reason": "INTENT_EXPIRED"})[0])
        self.assertEqual("CLAIMED", self.preparation()[1]["preparation"]["state"])
        self.preflight(browser_report())
        ready = self.preparation("/bridge/preparation/ack", ack)
        self.assertEqual(200, ready[0])
        self.assertEqual("READY", ready[1]["preparation"]["state"])
        self.assertEqual(0, self.bridge.orders()["total"])
        self.assertFalse((self.bridge.state_dir / "orders.jsonl").exists())

    def test_preparation_requires_fixed_header_origin_host_and_exact_paths(self):
        self.assertEqual(403, self.request("/bridge/preparation")[0])
        for path in ("/bridge/preparation", "/bridge/preparation/claim", "/bridge/preparation/ack"):
            payload = None if path == "/bridge/preparation" else {"schemaVersion": 1, "id": "unknown"}
            for origin in ("https://future.news", "null", "chrome-extension://" + "z" * 32):
                with self.subTest(path=path, origin=origin):
                    self.assertEqual(403, self.preparation(path, payload, Origin=origin)[0])
            self.assertEqual(403, self.preparation(path, payload, Host="attacker.invalid")[0])
            self.assertEqual(404, self.preparation(path + "?url=attacker", payload)[0])
        self.assertEqual(200, self.preparation(Origin="chrome-extension://" + "a" * 32)[0])

    def test_preparation_rejects_duplicate_json_headers_and_coerced_claim_fields(self):
        headers = {"Content-Type": "application/json", "X-PolyHermes-Future-Preparation": "1"}
        path = "/bridge/preparation/claim"
        for body in (b'{"schemaVersion":1,"id":"x","id":"y"}', b'{"schemaVersion":true,"id":"x"}',
                     b'{"schemaVersion":1,"id":"x","submit":true}', b"x" * 257):
            with self.subTest(body=body[:40]):
                self.assertEqual(400, self.request(path, body, headers)[0])
        self.assertEqual(400, self.request(path, b"{}", {**headers, "Transfer-Encoding": "chunked"})[0])
        import http.client
        connection = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        self.addCleanup(connection.close)
        connection.putrequest("GET", "/bridge/preparation", skip_host=True)
        connection.putheader("Host", f"127.0.0.1:{self.server.server_port}")
        connection.putheader("X-PolyHermes-Future-Preparation", "1")
        connection.putheader("X-PolyHermes-Future-Preparation", "1")
        connection.endheaders()
        self.assertEqual(400, connection.getresponse().status)

    def test_preparation_get_refuses_body_and_server_never_binds_public_address(self):
        self.assertEqual(400, self.preparation(**{"Content-Length": "1"})[0])
        for address in (("0.0.0.0", 0), ("localhost", 0), ("::1", 0)):
            with self.subTest(address=address), self.assertRaisesRegex(ValueError, "ASSISTANT_REQUIRES_LOOPBACK"):
                make_server(Source(), address, self.bridge)

    def test_preparation_ack_rejects_non_string_reason_duplicate_fields_and_oversize_body(self):
        headers = {"Content-Type": "application/json", "X-PolyHermes-Future-Preparation": "1"}
        ack = {"schemaVersion": 1, "id": f"future-btc5m-prepare:{START}", "claimToken": "0" * 32,
               "checkedAt": START + 60, "status": "FAILED", "marketUrl": browser_report()["marketUrl"],
               "amountUsd": None, "selectedSide": None, "reason": [], "noSubmission": True}
        path = "/bridge/preparation/ack"
        self.assertEqual(400, self.preparation(path, ack)[0])
        self.assertEqual(400, self.request(path, b'{"id":"x","id":"y"}', headers)[0])
        self.assertEqual(400, self.request(path, b"x" * 1501, headers)[0])

    def test_schema2_higher_button_side_crosses_http_claim_and_ready_with_manual_submit_only(self):
        current = source()
        clock = [START + 10]
        self.bridge.status_fn = lambda: current
        self.bridge.now_fn = lambda: clock[0]
        self.assertEqual(200, self.control({"enabled": True})[0])
        clock[0] = START + 60
        report = browser_report(upQuoteCents=12, downQuoteCents=88)
        self.assertEqual(200, self.preflight(report)[0])
        intent = self.bridge.observe()["preparation"]["intent"]
        self.assertEqual((2, "Down", 1), (intent["schemaVersion"], intent["side"], intent["amountUsd"]))
        claim = self.preparation("/bridge/preparation/claim", {"schemaVersion": 1, "id": intent["id"]})
        self.assertEqual(200, claim[0])
        report["selectedSide"] = "Down"
        status = self.preflight(report)
        self.assertEqual(200, status[0])
        self.assertEqual("Up", status[1]["preflight"]["signalSide"])
        self.assertEqual("Down", status[1]["preflight"]["preferredSide"])
        ack = {"schemaVersion": 1, "id": intent["id"], "claimToken": claim[1]["preparation"]["intent"]["claimToken"],
               "checkedAt": clock[0], "status": "READY", "marketUrl": report["marketUrl"], "amountUsd": 1,
               "selectedSide": "Down", "reason": None, "noSubmission": True}
        ready = self.preparation("/bridge/preparation/ack", ack)
        self.assertEqual(200, ready[0])
        self.assertEqual("READY", ready[1]["preparation"]["state"])
        self.assertTrue(ready[1]["preparation"]["noSubmission"])
        self.assertEqual(0, self.request("/bridge/orders")[1]["total"])

    def test_schema2_preflight_quote_whitelist_types_and_legacy_read_compatibility(self):
        current = source()
        self.bridge.status_fn = lambda: current
        self.bridge.now_fn = lambda: START + 60
        report = browser_report()
        for changes in ({"upQuoteCents": True}, {"downQuoteCents": "88"}, {"upQuoteCents": -1},
                        {"downQuoteCents": 101}, {"selectionSource": "HIGHER_BUTTON_PRICE"}, {"schemaVersion": 1}):
            with self.subTest(changes=changes):
                self.assertEqual(400, self.preflight({**report, **changes})[0])
        legacy = {field: value for field, value in report.items() if field not in ("upQuoteCents", "downQuoteCents")}
        legacy["schemaVersion"] = 1
        code, status, _ = self.preflight(legacy)
        self.assertEqual(200, code)
        self.assertIsNone(status["preflight"]["preferredSide"])
        self.assertIsNone(status["preflight"]["selectionSource"])
        self.assertIn("BUTTON_QUOTES_UNAVAILABLE", status["preflight"]["reasons"])


if __name__ == "__main__":
    unittest.main()
