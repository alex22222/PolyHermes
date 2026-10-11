import http.client
import json
import socketserver
import sys
import threading
import unittest
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent))

from future_btc5m_relay import MAX_RESPONSE_BYTES, make_server


class UnixHttpServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True


class FutureRelayTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.socket_path = str(Path(directory.name) / "assistant.sock")
        self.requests = []
        test = self

        class Upstream(BaseHTTPRequestHandler):
            def do_GET(self):
                self.respond()

            def do_POST(self):
                self.respond()

            def respond(self):
                body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
                test.requests.append({"method": self.command, "path": self.path,
                                      "headers": dict(self.headers), "body": body})
                if test.response_kind == "disconnect":
                    self.connection.close()
                    return
                payload = b"x" * (MAX_RESPONSE_BYTES + 1) if test.response_kind == "oversize" else json.dumps({
                    "mode": "ASSIST_ONLY", "requestedEnabled": False, "effectiveEnabled": False}).encode()
                self.send_response(503 if test.response_kind == "unavailable" else 200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                if test.response_kind == "truncated":
                    self.send_header("X-Fixture-Truncated", "1")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Set-Cookie", "fixture=value")
                self.end_headers()
                try:
                    self.wfile.write(payload[:5] if test.response_kind == "truncated" else payload)
                except (BrokenPipeError, ConnectionResetError):
                    pass

            def log_message(self, *args):
                pass

        self.response_kind = "normal"
        self.upstream = UnixHttpServer(self.socket_path, Upstream)
        threading.Thread(target=self.upstream.serve_forever, daemon=True).start()
        self.addCleanup(self.upstream.server_close)
        self.addCleanup(self.upstream.shutdown)
        self.relay = make_server(self.socket_path, ("127.0.0.1", 0))
        threading.Thread(target=self.relay.serve_forever, daemon=True).start()
        self.addCleanup(self.relay.server_close)
        self.addCleanup(self.relay.shutdown)
        self.host = f"127.0.0.1:{self.relay.server_port}"

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection("127.0.0.1", self.relay.server_port, timeout=3)
        self.addCleanup(connection.close)
        connection.request(method, path, body, headers or {})
        response = connection.getresponse()
        return response.status, response.read(), dict(response.headers)

    def post(self, path, body=b"{}", headers=None):
        header = "X-PolyHermes-Future-Preflight" if path == "/bridge/preflight" else "X-PolyHermes-Future-Control"
        return self.request("POST", path, body, {
            "Content-Type": "application/json", header: "1", **(headers or {})})

    def test_fixed_upstream_host_and_no_browser_auth_headers(self):
        code, body, headers = self.request("GET", "/bridge/status", headers={
            "Cookie": "fixture-cookie", "Authorization": "Bearer fixture-token"})
        self.assertEqual(200, code)
        self.assertFalse(json.loads(body)["effectiveEnabled"])
        upstream = self.requests[0]
        self.assertEqual("127.0.0.1:8766", upstream["headers"]["Host"])
        self.assertNotIn("Cookie", upstream["headers"])
        self.assertNotIn("Authorization", upstream["headers"])
        self.assertNotIn("Access-Control-Allow-Origin", headers)
        self.assertNotIn("Set-Cookie", headers)
        self.assertEqual("no-store", headers["Cache-Control"])

    def test_only_expected_get_paths_and_queries_are_forwarded(self):
        paths = ("/status", "/draft", "/bridge/status", "/bridge/orders",
                 "/bridge/orders?page=1&size=20&status=SKIPPED",
                 "/bridge/orders/future-btc5m%3A1791706800")
        for path in paths:
            with self.subTest(path=path):
                self.assertEqual(200, self.request("GET", path)[0])
                self.assertEqual(path, self.requests[-1]["path"])

    def test_control_and_preflight_preserve_json_bytes_and_required_header(self):
        for path, body in (("/bridge/control", b'{"enabled":false}'),
                           ("/bridge/preflight", b'{"prepare":true}')):
            with self.subTest(path=path):
                self.assertEqual(200, self.post(path, body)[0])
                upstream = self.requests[-1]
                self.assertEqual("POST", upstream["method"])
                self.assertEqual(body, upstream["body"])
                required = "X-PolyHermes-Future-Preflight" if path == "/bridge/preflight" else "X-PolyHermes-Future-Control"
                other = "X-PolyHermes-Future-Control" if path == "/bridge/preflight" else "X-PolyHermes-Future-Preflight"
                self.assertEqual("1", upstream["headers"][required])
                self.assertNotIn(other, upstream["headers"])
                self.assertEqual("application/json", upstream["headers"]["Content-Type"])

    def test_wrong_host_and_browser_origin_never_reach_upstream(self):
        self.assertEqual(403, self.request("GET", "/status", headers={"Host": "attacker.invalid"})[0])
        self.assertEqual(403, self.post("/bridge/control", headers={"Origin": "https://future.news"})[0])
        self.assertEqual(403, self.request("GET", "/status", headers={"Origin": "null"})[0])
        self.assertEqual([], self.requests)

    def test_submit_and_arbitrary_targets_never_reach_upstream(self):
        for path in ("/submit", "/bridge/orders/other", "/bridge/status?target=http://example.com",
                     "http://example.com/status", "//example.com/status", "/status#fragment",
                     "/bridge/orders/future-btc5m%3A1%2Fsubmit", "/bridge/orders?url=attacker"):
            with self.subTest(path=path):
                self.assertIn(self.request("GET", path, headers={"Host": self.host})[0], (400, 404))
                self.assertIn(self.post(path, headers={"Host": self.host})[0], (400, 404))
        self.assertEqual([], self.requests)

    def test_other_methods_are_rejected(self):
        for method in ("PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"):
            with self.subTest(method=method):
                self.assertEqual(405, self.request(method, "/bridge/status")[0])
        self.assertEqual([], self.requests)

    def test_missing_control_header_bad_json_and_body_limits(self):
        self.assertEqual(403, self.request("POST", "/bridge/control", b"{}", {
            "Content-Type": "application/json"})[0])
        self.assertEqual(415, self.request("POST", "/bridge/control", b"{}", {
            "X-PolyHermes-Future-Control": "1"})[0])
        for body in (b"", b"{", b"x" * 1501, b"[]"):
            with self.subTest(body=body[:20]):
                self.assertEqual(400, self.post("/bridge/preflight", body)[0])
        self.assertEqual([], self.requests)

    def test_preflight_accepts_current_report_cap_and_rejects_control_header(self):
        body = json.dumps({"fixture": "x" * 1300}).encode()
        self.assertEqual(200, self.post("/bridge/preflight", body)[0])
        self.assertEqual(body, self.requests[-1]["body"])
        before = len(self.requests)
        self.assertEqual(403, self.request("POST", "/bridge/preflight", b"{}", {
            "Content-Type": "application/json", "X-PolyHermes-Future-Control": "1"})[0])
        self.assertEqual(400, self.post("/bridge/control", b'{"fixture":"' + b"x" * 300 + b'"}')[0])
        self.assertEqual(before, len(self.requests))

    def test_duplicate_query_and_get_body_rejected(self):
        self.assertEqual(400, self.request("GET", "/bridge/orders?page=1&page=2")[0])
        self.assertEqual(400, self.request("GET", "/bridge/status", b"{}")[0])
        self.assertEqual([], self.requests)

    def test_chunked_and_duplicate_critical_headers_rejected(self):
        self.assertEqual(400, self.post("/bridge/control", headers={"Transfer-Encoding": "chunked"})[0])
        connection = http.client.HTTPConnection("127.0.0.1", self.relay.server_port, timeout=3)
        self.addCleanup(connection.close)
        connection.putrequest("POST", "/bridge/control", skip_host=True)
        connection.putheader("Host", self.host)
        connection.putheader("Host", self.host)
        connection.putheader("Content-Length", "2")
        connection.putheader("Content-Type", "application/json")
        connection.putheader("X-PolyHermes-Future-Control", "1")
        connection.endheaders(b"{}")
        self.assertEqual(403, connection.getresponse().status)
        self.assertEqual([], self.requests)

    def test_missing_socket_is_explicit_503(self):
        Path(self.socket_path).unlink()
        code, body, _ = self.request("GET", "/bridge/status")
        self.assertEqual(503, code)
        self.assertEqual("FUTURE_TUNNEL_UNAVAILABLE", json.loads(body)["error"])
        self.assertEqual([], self.requests)

    def test_disconnected_upstream_is_503(self):
        self.response_kind = "disconnect"
        self.assertEqual(503, self.request("GET", "/status")[0])

    def test_oversized_upstream_response_is_503(self):
        self.response_kind = "oversize"
        self.assertEqual(503, self.request("GET", "/status")[0])

    def test_truncated_upstream_response_is_503(self):
        self.response_kind = "truncated"
        self.assertEqual(503, self.request("GET", "/status")[0])

    def test_upstream_http_failure_is_preserved(self):
        self.response_kind = "unavailable"
        self.assertEqual(503, self.request("GET", "/status")[0])

    def test_public_bind_is_rejected(self):
        with self.assertRaises(ValueError):
            make_server(self.socket_path, ("0.0.0.0", 0))


if __name__ == "__main__":
    unittest.main()
