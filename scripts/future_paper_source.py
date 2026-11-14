"""Private, GET-only paper source. Never forwards control, wallet or order requests."""
import argparse
import http.client
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import re
import socket
import urllib.request

MAX_BYTES = 1_000_000
FIELDS = {
    '/status': {'schema_version', 'updated_at', 'server_time', 'feed_status', 'round_series',
                'period_start', 'signal', 'round_conditions', 'hour_quote'},
    '/bridge/status': {'bridgeId', 'online', 'serverTime', 'periodStart', 'series', 'strategy',
                       'requestedEnabled', 'feedStatus', 'signal', 'preflight'},
}


def allowed_path(path):
    return path in FIELDS or re.fullmatch(r'/bridge/paper\?page=([1-9]|1[0-9]|20)&size=100', path) is not None


def sanitize(path, value):
    if not allowed_path(path) or not isinstance(value, dict):
        raise ValueError('PAPER_SOURCE_INVALID')
    if path in FIELDS:
        return {k: v for k, v in value.items() if k in FIELDS[path]}
    return {k: v for k, v in value.items() if k in {'list', 'total', 'page', 'size'}}


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('PAPER_SOURCE_REDIRECT_REJECTED')


def read_bridge(path):
    if not allowed_path(path):
        raise ValueError('PAPER_SOURCE_PATH_REJECTED')
    request = urllib.request.Request('http://paper-source:8778' + path, method='GET')
    with urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect()).open(request, timeout=2) as response:
        raw = response.read(MAX_BYTES + 1)
    if len(raw) > MAX_BYTES:
        raise ValueError('PAPER_SOURCE_RESPONSE_TOO_LARGE')
    return sanitize(path, json.loads(raw))


class UnixConnection(http.client.HTTPConnection):
    def __init__(self, path):
        super().__init__('127.0.0.1', timeout=1.5)
        self.path = path

    def connect(self):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        try:
            self.sock.connect(self.path)
        except Exception:
            self.sock.close()
            raise


def make_server(socket_path, address=('0.0.0.0', 8778)):
    class Handler(BaseHTTPRequestHandler):
        def reply(self, code, value):
            body = json.dumps(value, allow_nan=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Connection', 'close')
            self.end_headers()
            self.close_connection = True
            self.wfile.write(body)

        def do_GET(self):
            if self.path == '/health':
                self.reply(200, {'paperOnly': True})
                return
            if not allowed_path(self.path) or self.headers.get('Transfer-Encoding') or self.headers.get('Content-Length') not in (None, '0'):
                self.reply(403, {'error': 'PAPER_SOURCE_PATH_REJECTED'})
                return
            connection = UnixConnection(socket_path)
            try:
                connection.request('GET', self.path, headers={'Host': '127.0.0.1:8766', 'Connection': 'close'})
                response = connection.getresponse()
                raw = response.read(MAX_BYTES + 1)
                if response.status != 200 or len(raw) > MAX_BYTES:
                    raise ValueError('PAPER_SOURCE_UNAVAILABLE')
                value = sanitize(self.path, json.loads(raw))
            except Exception:
                self.reply(503, {'error': 'PAPER_SOURCE_UNAVAILABLE'})
                return
            finally:
                connection.close()
            self.reply(200, value)

        def do_POST(self):
            self.reply(405, {'error': 'PAPER_SOURCE_GET_ONLY'})

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(address, Handler)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--socket', required=True)
    args = parser.parse_args()
    make_server(args.socket).serve_forever()
