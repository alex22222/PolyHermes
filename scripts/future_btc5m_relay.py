"""Loopback-only HTTP relay to the private Future assistant SSH Unix socket."""

import argparse
import http.client
import json
import re
import socket
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


LOCAL_ADDRESS = ("127.0.0.1", 8766)
UPSTREAM_HOST = "127.0.0.1:8766"
TIMEOUT_SECONDS = 2
MAX_REQUEST_BYTES = 256
MAX_PREFLIGHT_BYTES = 1500
MAX_RESPONSE_BYTES = 1024 * 1024


class UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, socket_path):
        super().__init__("127.0.0.1", timeout=TIMEOUT_SECONDS)
        self.socket_path = socket_path

    def connect(self):
        connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        connection.settimeout(self.timeout)
        try:
            connection.connect(self.socket_path)
        except OSError:
            connection.close()
            raise
        self.sock = connection


def make_server(socket_path, address=LOCAL_ADDRESS):
    if address[0] != "127.0.0.1":
        raise ValueError("RELAY_REQUIRES_LOOPBACK")

    class Handler(BaseHTTPRequestHandler):
        server_version = "FutureRelay"
        sys_version = ""

        def setup(self):
            super().setup()
            self.connection.settimeout(TIMEOUT_SECONDS)

        def fail(self, code, error):
            self.reply(code, json.dumps({"error": error}).encode(), "application/json")

        def reply(self, code, body, content_type):
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Connection", "close")
            self.end_headers()
            self.close_connection = True
            try:
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def validate(self):
            hosts = self.headers.get_all("Host", [])
            if hosts != [f"{address[0]}:{self.server.server_port}"] or self.headers.get("Origin") is not None:
                self.fail(403, "RELAY_REQUEST_FORBIDDEN")
                return False
            if self.headers.get("Transfer-Encoding") is not None:
                self.fail(400, "TRANSFER_ENCODING_NOT_SUPPORTED")
                return False
            if any(len(self.headers.get_all(name, [])) > 1 for name in
                   ("Content-Length", "Content-Type", "X-PolyHermes-Future-Control", "X-PolyHermes-Future-Preflight")):
                self.fail(400, "DUPLICATE_REQUEST_HEADER")
                return False
            return True

        def allowed_path(self):
            if len(self.path) > 512:
                self.fail(400, "REQUEST_PATH_TOO_LONG")
                return False
            url = urllib.parse.urlsplit(self.path)
            if url.scheme or url.netloc or url.fragment or not self.path.startswith("/"):
                self.fail(404, "RELAY_PATH_NOT_ALLOWED")
                return False
            if self.command == "POST":
                allowed = url.path in ("/bridge/control", "/bridge/preflight") and not url.query
            elif url.path == "/bridge/orders":
                params = urllib.parse.parse_qs(url.query, keep_blank_values=True)
                if set(params) - {"page", "size", "status"}:
                    self.fail(404, "RELAY_PATH_NOT_ALLOWED")
                    return False
                if any(len(values) != 1 for values in params.values()):
                    self.fail(400, "DUPLICATE_QUERY_PARAMETER")
                    return False
                allowed = True
            else:
                allowed = not url.query and (
                    url.path in ("/status", "/draft", "/bridge/status")
                    or re.fullmatch(r"/bridge/orders/future-btc5m:[0-9]{1,15}", urllib.parse.unquote(url.path))
                )
            if not allowed:
                self.fail(404, "RELAY_PATH_NOT_ALLOWED")
            return bool(allowed)

        def forward(self, body=b""):
            upstream = UnixHTTPConnection(str(socket_path))
            try:
                headers = {"Host": UPSTREAM_HOST, "Accept": "application/json", "Connection": "close"}
                if self.command == "POST":
                    headers["Content-Type"] = "application/json"
                    headers[self.control_header()] = "1"
                upstream.request(self.command, self.path, body if self.command == "POST" else None, headers)
                response = upstream.getresponse()
                content = response.read(MAX_RESPONSE_BYTES + 1)
                if len(content) > MAX_RESPONSE_BYTES or response.length not in (None, 0):
                    raise ValueError("UPSTREAM_RESPONSE_TOO_LARGE")
                code = response.status
                content_type = response.getheader("Content-Type", "application/json")
            except (OSError, http.client.HTTPException, ValueError):
                self.fail(503, "FUTURE_TUNNEL_UNAVAILABLE")
                return
            finally:
                upstream.close()
            self.reply(code, content, content_type)

        def do_GET(self):
            if not self.validate() or not self.allowed_path():
                return
            if self.headers.get("Content-Length", "0") != "0":
                self.fail(400, "GET_BODY_NOT_ALLOWED")
                return
            self.forward()

        def do_POST(self):
            if not self.validate() or not self.allowed_path():
                return
            if self.headers.get(self.control_header()) != "1":
                self.fail(403, "CONTROL_HEADER_REQUIRED")
                return
            if self.headers.get_content_type() != "application/json":
                self.fail(415, "JSON_BODY_REQUIRED")
                return
            try:
                size = self.headers.get("Content-Length", "0")
                limit = MAX_PREFLIGHT_BYTES if self.path == "/bridge/preflight" else MAX_REQUEST_BYTES
                if not size.isdigit() or not 0 < int(size) <= limit:
                    raise ValueError("INVALID_BODY_SIZE")
                body = self.rfile.read(int(size))
                if len(body) != int(size) or type(json.loads(body)) is not dict:
                    raise ValueError("INVALID_JSON_BODY")
            except (ValueError, UnicodeError):
                self.fail(400, "INVALID_JSON_BODY")
                return
            except OSError:
                self.fail(408, "REQUEST_BODY_TIMEOUT")
                return
            self.forward(body)

        def control_header(self):
            return "X-PolyHermes-Future-Preflight" if self.path == "/bridge/preflight" else "X-PolyHermes-Future-Control"

        def unsupported(self):
            self.fail(405, "RELAY_METHOD_NOT_ALLOWED")

        do_PUT = unsupported
        do_DELETE = unsupported
        do_PATCH = unsupported
        do_OPTIONS = unsupported
        do_HEAD = unsupported

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(address, Handler)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", default="/bridge/assistant.sock")
    args = parser.parse_args()
    server = make_server(args.socket)
    print("Future relay listening on 127.0.0.1:8766; private Unix socket upstream", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
