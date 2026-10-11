#!/usr/bin/env python3
"""Observe weekend BTC 5m signals and serve $1 drafts; never submit an order."""

from __future__ import annotations

import argparse
import asyncio
import copy
import fcntl
import json
import math
import os
import re
import ssl
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from zoneinfo import ZoneInfo

import websockets
from future_btc5m_bridge import FutureBridge, PreparationConflict, strict_json_object


STATE_DIR = Path(__file__).resolve().parents[1] / "reports/future-btc5m-assistant"
GAMMA = "https://gamma-api.polymarket.com/events"
CRYPTO_PRICE = "https://polymarket.com/api/crypto/crypto-price"
GEOBLOCK = "https://polymarket.com/api/geoblock"
RTDS = "wss://ws-live-data.polymarket.com"
LOCAL_ADDRESS = ("127.0.0.1", 8766)


def iso(timestamp):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat().replace("+00:00", "Z")


def round_start(timestamp):
    return int(timestamp // 300) * 300


def is_et_weekend(timestamp):
    return datetime.fromtimestamp(timestamp, ZoneInfo("America/New_York")).weekday() >= 5


def positive_number(value):
    if isinstance(value, bool):
        raise ValueError("INVALID_PRICE")
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise ValueError("INVALID_PRICE")
    return number


def parse_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("MARKET_TIMEZONE_MISSING")
    return parsed.timestamp()


def validate_market(events, start):
    slug = f"btc-updown-5m-{start}"
    if not isinstance(events, list) or len(events) != 1:
        raise ValueError("MARKET_NOT_UNIQUE")
    event = events[0]
    if event.get("slug") != slug or event.get("active") is not True or event.get("closed") is not False:
        raise ValueError("WRONG_OR_INACTIVE_EVENT")
    markets = event.get("markets")
    if not isinstance(markets, list) or len(markets) != 1:
        raise ValueError("MARKET_NOT_UNIQUE")
    market = markets[0]
    if (market.get("slug") != slug or market.get("active") is not True
            or market.get("closed") is not False or market.get("acceptingOrders") is not True):
        raise ValueError("WRONG_OR_INACTIVE_MARKET")
    # Gamma startDate is the listing time. The exact slug identifies the period start.
    if parse_time(market["endDate"]) != start + 300 or parse_time(event["endDate"]) != start + 300:
        raise ValueError("WRONG_MARKET_PERIOD")
    if market.get("eventStartTime") and parse_time(market["eventStartTime"]) != start:
        raise ValueError("WRONG_MARKET_PERIOD")
    price_config = market.get("cryptoMarketConfig")
    if (not isinstance(price_config, dict) or price_config.get("asset") != "btc"
            or price_config.get("duration") != "5m" or price_config.get("twapEnabled") is not True
            or price_config.get("twapLookbackSeconds") != 60):
        raise ValueError("WRONG_MARKET_PRICE_CONFIG")
    outcomes = market["outcomes"]
    tokens = market["clobTokenIds"]
    outcomes = json.loads(outcomes) if isinstance(outcomes, str) else outcomes
    tokens = json.loads(tokens) if isinstance(tokens, str) else tokens
    if (not isinstance(outcomes, list) or len(outcomes) != 2 or set(outcomes) != {"Up", "Down"}
            or not isinstance(tokens, list) or len(tokens) != 2
            or any(not isinstance(token, str) or not token.isdigit() for token in tokens)
            or tokens[0] == tokens[1] or not market.get("conditionId")):
        raise ValueError("INVALID_OUTCOME_TOKENS")
    return {"slug": slug, "condition_id": market["conditionId"], "tokens": dict(zip(outcomes, tokens))}


def validate_quote(quote, now):
    if not quote:
        raise ValueError("CHAINLINK_PRICE_UNAVAILABLE")
    price = positive_number(quote["price"])
    observed = float(quote["observed_at"])
    received = float(quote["received_at"])
    if not all(math.isfinite(value) and 0 <= now - value <= 5 for value in (observed, received)):
        raise ValueError("CHAINLINK_PRICE_STALE_OR_FUTURE")
    return price, observed


def feed_ssl_context():
    context = ssl.create_default_context()
    # Framework Python on macOS may have no installed OpenSSL CA bundle.
    # Add the existing system roots; retain hostname and certificate validation.
    if context.cert_store_stats()["x509_ca"] == 0 and Path("/etc/ssl/cert.pem").is_file():
        context.load_verify_locations(cafile="/etc/ssl/cert.pem")
    return context


class ChainlinkFeed:
    def __init__(self):
        self.quote = None
        self.error = "CHAINLINK_FEED_NOT_CONNECTED"

    def ingest(self, message, received_at):
        """Accept only timestamped Chainlink btc/usd payloads, never a proxy price."""
        try:
            message = json.loads(message) if isinstance(message, (str, bytes)) else message
            payload = message.get("payload") or {}
            if message.get("topic") != "crypto_prices_chainlink" or payload.get("symbol") != "btc/usd":
                return False
            points = [payload] if "value" in payload else payload.get("data", [])
            candidates = []
            for point in points:
                try:
                    price = positive_number(point["value"])
                    timestamp = float(point["timestamp"]) / 1000
                    if math.isfinite(timestamp) and 0 <= received_at - timestamp <= 5:
                        candidates.append({"price": price, "observed_at": timestamp, "received_at": received_at})
                except (KeyError, TypeError, ValueError):
                    continue
            if not candidates:
                return False
            newest = max(candidates, key=lambda quote: quote["observed_at"])
            if self.quote and newest["observed_at"] < self.quote["observed_at"]:
                return False
            self.quote = newest
            self.error = None
            return True
        except (AttributeError, TypeError, ValueError):
            return False

    async def run(self, single_attempt=False):
        # This is the documented strategy's legacy feed. If it no longer emits
        # this exact source, the assistant remains unavailable; no source switch.
        while True:
            self.quote = None
            try:
                async with websockets.connect(RTDS, ssl=feed_ssl_context(), open_timeout=5 if single_attempt else 8, close_timeout=2, ping_interval=None) as socket:
                    await socket.send(json.dumps({"action": "subscribe", "subscriptions": [{
                        "topic": "crypto_prices_chainlink", "type": "*",
                        # This legacy endpoint currently requires compact filter JSON.
                        "filters": json.dumps({"symbol": "btc/usd"}, separators=(",", ":")),
                    }]}))
                    self.error = "CHAINLINK_FEED_WAITING_FOR_PRICE"

                    async def keep_alive():
                        while True:
                            await asyncio.sleep(5)
                            await socket.send("PING")

                    ping = asyncio.create_task(keep_alive())
                    try:
                        while True:
                            raw = await asyncio.wait_for(socket.recv(), timeout=30)
                            self.ingest(raw, time.time())
                    finally:
                        self.quote = None
                        ping.cancel()
                        await asyncio.gather(ping, return_exceptions=True)
            except ImportError:
                self.quote = None
                self.error = "CHAINLINK_FEED_PROXY_DEPENDENCY_UNAVAILABLE"
                if single_attempt:
                    return
                await asyncio.sleep(2)
            except (OSError, TimeoutError, websockets.WebSocketException) as error:
                self.quote = None
                if isinstance(error, ssl.SSLCertVerificationError):
                    self.error = "CHAINLINK_FEED_TLS_CERTIFICATE_VERIFY_FAILED"
                elif isinstance(error, TimeoutError):
                    self.error = "CHAINLINK_FEED_CONNECTION_TIMEOUT"
                else:
                    self.error = "CHAINLINK_FEED_CONNECTION_UNAVAILABLE"
                if single_attempt:
                    return
                await asyncio.sleep(2)


def future_eligibility():
    """Amount-preparation eligibility remains unknown until an official source is verified."""
    return {"status": "UNKNOWN", "venue": "future.news", "operation": "PREPARE_USD_BUY_AMOUNT",
            "source_url": None}


def future_eligibility_rejection(eligibility):
    if isinstance(eligibility, dict):
        if eligibility.get("status") == "UNKNOWN":
            return "FUTURE_ELIGIBILITY_UNKNOWN"
        if eligibility.get("status") == "RESTRICTED":
            return "FUTURE_ELIGIBILITY_RESTRICTED"
        source_url = eligibility.get("source_url")
        if (eligibility.get("status") == "VERIFIED" and eligibility.get("venue") == "future.news"
                and eligibility.get("operation") == "PREPARE_USD_BUY_AMOUNT" and isinstance(source_url, str)):
            try:
                source = urllib.parse.urlsplit(source_url)
                if (source.scheme == "https" and source.hostname == "future.news"
                        and source.port in (None, 443) and source.username is None and source.password is None
                        and source.path not in ("", "/")):
                    return None
            except ValueError:
                pass
    return "FUTURE_ELIGIBILITY_UNVERIFIED"


def empty_status(now):
    return {
        "schema_version": 1, "mode": "ASSIST_ONLY", "live_enabled": False, "amount_usd": 1,
        "status": "WAITING", "reason": "WAITING_FOR_ENTRY", "updated_at": iso(now),
        "server_time": now, "geoblock": {"blocked": None, "source_url": GEOBLOCK},
        "future_eligibility": future_eligibility(), "feed_status": "UNAVAILABLE",
        "signal": None, "draft": None,
    }


class Assistant:
    def __init__(self, state_dir, quote_fn, now_fn=time.time, observe_only=False):
        self.state_dir = Path(state_dir)
        self.quote_fn = quote_fn
        self.now_fn = now_fn
        self.observe_only = observe_only
        self.boot_time = now_fn()
        self.lock = threading.RLock()
        self.state = empty_status(self.boot_time)
        self.seen = set()
        ledger = self.state_dir / "rounds.jsonl"
        if ledger.exists():
            for line in ledger.read_text(encoding="utf-8").splitlines():
                self.seen.add(json.loads(line)["period_start"])

    def status(self):
        with self.lock:
            result = copy.deepcopy(self.state)
            now = self.now_fn()
            result["future_eligibility"] = future_eligibility()
            self.state["future_eligibility"] = copy.deepcopy(result["future_eligibility"])
            try:
                validate_quote(self.quote_fn(), now)
                result["feed_status"] = "CURRENT"
            except (KeyError, TypeError, ValueError):
                result["feed_status"] = "UNAVAILABLE"
            if (self.state_dir / "STOP").exists():
                result.update(status="STOPPED", reason="STOP_FILE_PRESENT", draft=None)
                self.state = copy.deepcopy(result)
            elif result["draft"]:
                draft = result["draft"]
                eligibility_reason = future_eligibility_rejection(result["future_eligibility"])
                if eligibility_reason:
                    result.update(status="OBSERVING", reason=eligibility_reason, draft=None)
                    self.state = copy.deepcopy(result)
                elif now >= draft["expires_at"] or round_start(now) != draft["period_start"]:
                    result.update(status="EXPIRED", reason="DRAFT_EXPIRED", draft=None)
                    self.state = copy.deepcopy(result)
                elif not 0 <= now - draft["price_observed_at"] <= 5:
                    result.update(status="EXPIRED", reason="CHAINLINK_SIGNAL_SAMPLE_EXPIRED", draft=None)
                    self.state = copy.deepcopy(result)
                elif result["feed_status"] != "CURRENT":
                    result.update(status="EXPIRED", reason="CHAINLINK_FEED_UNAVAILABLE", draft=None)
                    self.state = copy.deepcopy(result)
            result.update(server_time=now, updated_at=iso(now))
            return result

    def save_state(self):
        if self.observe_only:
            return
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_dir / "status.json.tmp"
        temporary.write_text(json.dumps(self.status(), ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(self.state_dir / "status.json")

    def claim_round(self, start):
        self.seen.add(start)
        if not self.observe_only:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            with (self.state_dir / "rounds.jsonl").open("a", encoding="utf-8") as ledger:
                ledger.write(json.dumps({"period_start": start, "claimed_at": iso(self.now_fn())}) + "\n")
                ledger.flush()
                # Claim before network I/O: a crash must never create a second draft.
                os.fsync(ledger.fileno())

    async def poll(self, http_fn):
        now = self.now_fn()
        start = round_start(now)
        with self.lock:
            if (self.state_dir / "STOP").exists():
                return self.status()
            if start in self.seen:
                if self.state.get("period_start") != start:
                    self.state.update(status="SKIPPED", reason="ROUND_ALREADY_PROCESSED", draft=None)
                return self.status()
            self.state = empty_status(now)
            self.state["period_start"] = start
            if not is_et_weekend(start):
                self.state.update(status="SKIPPED", reason="NOT_ET_WEEKEND")
                return self.status()
            if now < start + 60:
                return self.status()
            self.claim_round(start)
            if now >= start + 80:
                self.state.update(status="SKIPPED", reason="ENTRY_WINDOW_MISSED")
                return self.status()
            if not self.observe_only and self.boot_time >= start + 60:
                self.state.update(status="SKIPPED", reason="STARTED_AFTER_ENTRY")
                return self.status()
        parameters = urllib.parse.urlencode({
            "symbol": "BTC", "eventStartTime": iso(start), "variant": "fiveminute", "endDate": iso(start + 300),
            "twapEnabled": "true", "twapLookbackSeconds": 60,
        })
        try:
            values = await asyncio.gather(
                http_fn(f"{GAMMA}?slug=btc-updown-5m-{start}"),
                http_fn(f"{CRYPTO_PRICE}?{parameters}"), http_fn(GEOBLOCK),
                return_exceptions=True,
            )
            now = self.now_fn()  # Network time is part of the +60..+80 window.
            if (self.state_dir / "STOP").exists():
                return self.status()
            if round_start(now) != start or not start + 60 <= now < start + 80:
                raise ValueError("ENTRY_WINDOW_EXPIRED_DURING_READ")
            events, opening, geo = values
            if isinstance(events, Exception) or isinstance(opening, Exception):
                raise ValueError("SOURCE_REQUEST_FAILED")
            market = validate_market(events, start)
            opening_price = positive_number(opening["openPrice"])
            current_price, observed = validate_quote(self.quote_fn(), now)
            blocked = geo.get("blocked") if isinstance(geo, dict) else None
            blocked = blocked if isinstance(blocked, bool) else None
            side = "Up" if current_price > opening_price else "Down" if current_price < opening_price else None
            signal = {
                "id": f"5m:{start}", "slug": market["slug"], "series": "5m",
                "period_start": start, "period_end": start + 300, "side": side,
                "open_price": opening_price, "current_price": current_price,
                "open_price_source": "polymarket_crypto_price_fiveminute_twap60_openPrice",
                "twap_lookback_seconds": 60,
                "price_source": "chainlink", "price_observed_at": observed,
            }
            with self.lock:
                eligibility = future_eligibility()
                eligibility_reason = future_eligibility_rejection(eligibility)
                self.state.update(signal=signal, geoblock={"blocked": blocked, "source_url": GEOBLOCK},
                                  future_eligibility=eligibility, feed_status="CURRENT")
                if side is None:
                    self.state.update(status="SKIPPED", reason="PRICE_FLAT", draft=None)
                elif blocked is not False:
                    self.state.update(status="OBSERVING", reason="GEOBLOCK_BLOCKED" if blocked else "GEOBLOCK_UNKNOWN", draft=None)
                elif self.observe_only:
                    self.state.update(status="OBSERVING", reason="ONCE_OBSERVATION_ONLY", draft=None)
                elif eligibility_reason:
                    self.state.update(status="OBSERVING", reason=eligibility_reason, draft=None)
                else:
                    self.state.update(status="READY", reason="MANUAL_REVIEW_REQUIRED", draft={
                        **signal, "condition_id": market["condition_id"], "token_id": market["tokens"][side],
                        "amount_usd": 1, "created_at": now, "expires_at": start + 80,
                        "trade_ready": True, "manual_submit_required": True,
                        "platform_amount_validation_required": True,
                    })
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            with self.lock:
                reason = str(error) if isinstance(error, ValueError) else "INVALID_SOURCE_RESPONSE"
                self.state.update(status="SKIPPED", reason=reason, draft=None)
        return self.status()


def make_server(assistant, address=LOCAL_ADDRESS, bridge=None):
    if address[0] != "127.0.0.1":
        raise ValueError("ASSISTANT_REQUIRES_LOOPBACK")

    class Handler(BaseHTTPRequestHandler):
        def valid_host(self):
            if self.headers.get("Host") != f"{address[0]}:{self.server.server_port}":
                self.send_error(403)
                return False
            return True

        def reply(self, value):
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def preparation_access(self):
            critical = ("Host", "Origin", "Content-Length", "Content-Type", "X-PolyHermes-Future-Preparation")
            if (any(len(self.headers.get_all(name, [])) > 1 for name in critical)
                    or self.headers.get("Transfer-Encoding") is not None):
                self.send_error(400)
                return False
            origin = self.headers.get("Origin")
            if (self.headers.get("X-PolyHermes-Future-Preparation") != "1"
                    or origin is not None and re.fullmatch(r"chrome-extension://[a-p]{32}", origin) is None):
                self.send_error(403)
                return False
            return True

        def do_GET(self):
            if not self.valid_host():
                return
            if self.path in ("/status", "/draft"):
                self.reply(assistant.status())
                return
            if bridge is None:
                self.send_error(404)
                return
            url = urllib.parse.urlsplit(self.path)
            try:
                if url.path == "/bridge/status" and not url.query:
                    self.reply(bridge.status())
                elif self.path == "/bridge/preparation":
                    if not self.preparation_access():
                        return
                    if self.headers.get("Content-Length", "0") != "0":
                        raise ValueError("GET_BODY_NOT_ALLOWED")
                    self.reply(bridge.preparation())
                elif url.path == "/bridge/orders":
                    params = urllib.parse.parse_qs(url.query, keep_blank_values=True)
                    if set(params) - {"page", "size", "status"} or any(len(values) != 1 for values in params.values()):
                        raise ValueError("INVALID_QUERY")
                    status = params.get("status", [None])[0]
                    if status is not None and status not in {"PENDING", "SKIPPED", "FAILED", "SUBMITTED_UNVERIFIED", "FILLED"}:
                        raise ValueError("INVALID_STATUS")
                    self.reply(bridge.orders(int(params.get("page", ["1"])[0]), int(params.get("size", ["20"])[0]), status))
                elif url.path.startswith("/bridge/orders/") and not url.query:
                    record = bridge.detail(urllib.parse.unquote(url.path[len("/bridge/orders/"):]))
                    if record is None:
                        self.send_error(404)
                    else:
                        self.reply(record)
                else:
                    self.send_error(404)
            except ValueError:
                self.send_error(400)
            except OSError:
                self.send_error(503)

        def do_POST(self):
            if bridge is None:
                self.send_error(501)
                return
            if not self.valid_host():
                return
            preparation = self.path in ("/bridge/preparation/claim", "/bridge/preparation/ack")
            if self.path not in ("/bridge/control", "/bridge/preflight") and not preparation:
                self.send_error(404)
                return
            if preparation and not self.preparation_access():
                return
            preflight = self.path == "/bridge/preflight"
            origin = self.headers.get("Origin")
            header = "X-PolyHermes-Future-Preparation" if preparation else (
                "X-PolyHermes-Future-Preflight" if preflight else "X-PolyHermes-Future-Control")
            # A service worker may report only read-only browser facts. Ordinary
            # website origins remain rejected; controls still accept no Origin.
            allowed_origin = origin is None or (preflight or preparation) and re.fullmatch(r"chrome-extension://[a-p]{32}", origin) is not None
            if self.headers.get(header) != "1" or not allowed_origin:
                self.send_error(403)
                return
            if self.headers.get_content_type() != "application/json":
                self.send_error(415)
                return
            try:
                raw_length = self.headers.get("Content-Length", "0")
                if preparation and (not raw_length.isascii() or not raw_length.isdigit()):
                    raise ValueError("INVALID_BODY_SIZE")
                length = int(raw_length)
                limit = 1500 if preflight or self.path == "/bridge/preparation/ack" else 256
                if not 0 < length <= limit or self.headers.get("Transfer-Encoding") is not None:
                    raise ValueError("INVALID_BODY_SIZE")
                self.connection.settimeout(2)
                body = self.rfile.read(length)
                if preparation and len(body) != length:
                    raise ValueError("INCOMPLETE_BODY")
                payload = json.loads(body, object_pairs_hook=strict_json_object if preflight or preparation else None)
                if self.path == "/bridge/preparation/claim":
                    self.reply(bridge.claim_preparation(payload))
                elif self.path == "/bridge/preparation/ack":
                    self.reply(bridge.report_preparation(payload))
                elif preflight:
                    self.reply(bridge.report_preflight(payload))
                else:
                    if type(payload) is not dict or set(payload) != {"enabled"} or type(payload["enabled"]) is not bool:
                        raise ValueError("ENABLED_MUST_BE_BOOLEAN")
                    self.reply(bridge.control(payload["enabled"]))
            except PreparationConflict:
                self.send_error(409)
            except (ValueError, UnicodeError):
                self.send_error(400)
            except OSError:
                self.send_error(503)

        def log_message(self, *args):
            pass

    return ThreadingHTTPServer(address, Handler)


async def run(args):
    feed = ChainlinkFeed()
    assistant = Assistant(args.state_dir, lambda: feed.quote, observe_only=args.once)

    async def get_json(url):
        # curl supports the existing macOS SOCKS proxy without new Python packages.
        # Inherit the configured route; never disable TLS or override the proxy.
        process = await asyncio.create_subprocess_exec(
            "curl", "--fail", "--silent", "--show-error", "--max-time", "6",
            "--max-filesize", "1000000", "--user-agent", "PolyHermes-BTC5m-Assistant/1.0",
            "--header", "Accept: application/json", "--url", url,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )
        output, _ = await process.communicate()
        if process.returncode:
            raise RuntimeError("HTTP_SOURCE_UNAVAILABLE")
        return json.loads(output)

    feed_task = asyncio.create_task(feed.run(single_attempt=args.once))
    server = None
    try:
        if args.once:
            # A bounded, read-only probe. No daemon and no persisted round claim.
            deadline = time.monotonic() + 8
            while feed.quote is None and not feed_task.done() and time.monotonic() < deadline:
                await asyncio.sleep(0.1)
            snapshot = await assistant.poll(get_json)
            snapshot["feed_reason"] = feed.error
            print(json.dumps(snapshot, ensure_ascii=False))
            return
        bridge = FutureBridge(args.state_dir / "bridge", assistant.status)
        server = make_server(assistant, bridge=bridge)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        print("ASSIST_ONLY http://127.0.0.1:8766/status; no order submission. STOP: " + str(args.state_dir / "STOP"), flush=True)
        while True:
            await assistant.poll(get_json)
            assistant.state["feed_reason"] = feed.error
            assistant.save_state()
            bridge.observe()
            await asyncio.sleep(0.5)
    finally:
        feed_task.cancel()
        await asyncio.gather(feed_task, return_exceptions=True)
        if server:
            server.shutdown()
            server.server_close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--once", action="store_true", help="one bounded observation; no draft")
    action.add_argument("--watch", action="store_true", help="observe and serve drafts until interrupted")
    action.add_argument("--status", action="store_true", help="read local assistant status")
    parser.add_argument("--state-dir", type=Path, default=STATE_DIR)
    args = parser.parse_args()
    if args.status:
        try:
            local = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            with local.open("http://127.0.0.1:8766/status", timeout=2) as response:
                print(response.read().decode("utf-8"))
        except OSError:
            state = empty_status(time.time())
            state.update(status="STOPPED" if (args.state_dir / "STOP").exists() else "OFFLINE",
                         reason="STOP_FILE_PRESENT" if (args.state_dir / "STOP").exists() else "ASSISTANT_NOT_RUNNING")
            print(json.dumps(state, ensure_ascii=False))
        return
    args.state_dir.mkdir(parents=True, exist_ok=True)
    with (args.state_dir / "assistant.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            parser.error("another assistant is using this state directory")
        try:
            asyncio.run(run(args))
        except KeyboardInterrupt:
            pass


if __name__ == "__main__":
    main()
