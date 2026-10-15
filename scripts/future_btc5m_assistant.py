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
import subprocess
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
from future_btc5m_series import HOUR, SERIES, entry_bounds, hourly_slug, round_start_of, slug_for
from future_btc5m_runtime import start_runtime_server


STATE_DIR = Path(__file__).resolve().parents[1] / "reports/future-btc5m-assistant"
GAMMA = "https://gamma-api.polymarket.com/events"
CRYPTO_PRICE = "https://polymarket.com/api/crypto/crypto-price"
GEOBLOCK = "https://polymarket.com/api/geoblock"
RTDS = "wss://ws-live-data.polymarket.com"
CLOB_BOOKS = "https://clob.polymarket.com/books"
# Read or change whether rounds outside the US-Eastern weekend are traded (extension panel).
SCHEDULE_PATH = "/bridge/preparation/schedule"
LOCAL_ADDRESS = ("127.0.0.1", 8766)
MARKET_QUOTE_PATH = "/bridge/preparation/market-quote"
MARKET_QUOTE_FIELDS = {"schemaVersion", "source", "periodStart", "slug", "upAskCents", "downAskCents",
                       "upBidCents", "downBidCents", "observedAt", "serverTime"}
MARKET_QUOTE_ERRORS = {"HTTP_SOURCE_TIMEOUT", "HTTP_SOURCE_UNAVAILABLE", "INVALID_MARKET_QUOTE",
                       "CLOB_BOOKS_MISMATCH", "CLOB_BOOK_TIME_INVALID", "ROUND_CHANGED_DURING_READ",
                       "INVALID_BOOK", "INVALID_BOOK_LEVEL", "WRONG_MARKET_PRICE_CONFIG", "MARKET_NOT_UNIQUE",
                       "WRONG_OR_INACTIVE_EVENT", "WRONG_OR_INACTIVE_MARKET", "WRONG_MARKET_PERIOD",
                       "INVALID_OUTCOME_TOKENS"}


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


def validate_market(events, start, series="5m"):
    slug = slug_for(start, series)
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
    period = SERIES[series]["period"]
    if parse_time(market["endDate"]) != start + period or parse_time(event["endDate"]) != start + period:
        raise ValueError("WRONG_MARKET_PERIOD")
    if market.get("eventStartTime") and parse_time(market["eventStartTime"]) != start:
        raise ValueError("WRONG_MARKET_PERIOD")
    price_config = market.get("cryptoMarketConfig")
    if (not isinstance(price_config, dict) or price_config.get("asset") != "btc"
            or price_config.get("duration") != series or price_config.get("twapEnabled") is not True
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


def validate_hourly_market(events, start):
    """The ET-hour BTC market (Binance 1H candle) whose favorite filters the 15m strategy."""
    slug = hourly_slug(start)
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
    if (parse_time(market["endDate"]) != start + HOUR or not market.get("eventStartTime")
            or parse_time(market["eventStartTime"]) != start):
        raise ValueError("WRONG_MARKET_PERIOD")
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


def book_number(value):
    # CLOB levels carry decimal strings; numbers are accepted, booleans and other types are not.
    if type(value) not in (int, float, str):
        raise ValueError("INVALID_BOOK_LEVEL")
    number = float(value)
    if not math.isfinite(number):
        raise ValueError("INVALID_BOOK_LEVEL")
    return number


def best_book_cents(levels, best):
    """Best price in cents over levels with size, or None for an empty side. Never assumes order."""
    if not isinstance(levels, list):
        raise ValueError("INVALID_BOOK")
    prices = []
    for level in levels:
        if not isinstance(level, dict):
            raise ValueError("INVALID_BOOK_LEVEL")
        price, size = book_number(level.get("price")), book_number(level.get("size"))
        if not 0 < price < 1 or size < 0:
            raise ValueError("INVALID_BOOK_LEVEL")
        if size > 0:
            prices.append(price)
    return round(best(prices) * 100, 2) if prices else None


def fill_ask_cents(levels, notional=1.0):
    """Price in cents of the ask level that completes a buy of `notional` USD, walking asks from
    the cheapest; None when the side cannot fill it. A dust level never sets the price."""
    if not isinstance(levels, list):
        raise ValueError("INVALID_BOOK")
    asks = []
    for level in levels:
        if not isinstance(level, dict):
            raise ValueError("INVALID_BOOK_LEVEL")
        price, size = book_number(level.get("price")), book_number(level.get("size"))
        if not 0 < price < 1 or size < 0:
            raise ValueError("INVALID_BOOK_LEVEL")
        if size > 0:
            asks.append((price, size))
    spent = 0.0
    for price, size in sorted(asks):
        spent += price * size
        if spent >= notional - 1e-9:
            return round(price * 100, 2)
    return None


class ClobMarketQuotes:
    """Read-only Polymarket CLOB book snapshot of the current round of one series: the active
    strategy's 5m/15m round for the extension's pre-click check, or the ET hour ("1h") whose
    favorite filters the 15m strategy.

    It never places orders. Any source or shape failure raises, and the route answers 503.
    Network reads run outside the lock; the lock only guards the cached tokens and snapshot.
    """

    def __init__(self, fetch_json, now_fn=time.time, ttl=0.8, series_fn=lambda: "5m"):
        self.fetch_json = fetch_json
        self.now_fn = now_fn
        # A reply is served from a snapshot received at most ttl seconds ago.
        self.ttl = ttl
        self.series_fn = series_fn
        self.lock = threading.Lock()
        self.read_lock = threading.Lock()
        self.tokens = None  # ((series, start), tokens)
        self.snapshot = None  # ((series, start), received_at, snapshot)
        self.warming = False
        self.warm_attempted_at = -math.inf
        self.refreshing = False

    def _round(self, now):
        series = self.series_fn()
        period = HOUR if series == "1h" else SERIES[series]["period"]
        return series, int(now // period) * period

    def _slug(self, key):
        series, start = key
        return hourly_slug(start) if series == "1h" else slug_for(start, series)

    def _round_tokens(self, key):
        with self.lock:
            if self.tokens and self.tokens[0] == key:
                return self.tokens[1]
        # Gamma takes ~0.8 s through the operator proxy, so it is validated early by warm().
        series, start = key
        events = self.fetch_json(f"{GAMMA}?slug={self._slug(key)}")
        market = validate_hourly_market(events, start) if series == "1h" else validate_market(events, start, series)
        with self.lock:
            if self._round(self.now_fn()) == key:
                self.tokens = (key, market["tokens"])
        return market["tokens"]

    def prefetch_tokens(self):
        self._round_tokens(self._round(self.now_fn()))

    def warm(self, refresh=None):
        """Called from the main loop: prefetch the round's tokens (a failure retries after 10 s)
        and, while `refresh` holds (by default just before and inside the series' entry window),
        keep refreshing the books so a read is served from a snapshot instead of waiting ~1 s."""
        now = self.now_fn()
        key = self._round(now)
        series, start = key
        if refresh is None:
            first, last = entry_bounds(start, series) if series != "1h" else (start, start)
            refresh = first - 5 <= now < last
        started = False
        if not (self.tokens and self.tokens[0] == key) and not self.warming and now - self.warm_attempted_at >= 10:
            self.warming = True
            self.warm_attempted_at = now
            threading.Thread(target=self._background, args=("warming", self.prefetch_tokens), daemon=True).start()
            started = True
        if refresh and self.tokens and self.tokens[0] == key and not self.refreshing:
            self.refreshing = True
            threading.Thread(target=self._background, args=("refreshing", lambda: self._read(key)), daemon=True).start()
            started = True
        return started

    def _background(self, flag, task):
        try:
            task()
        except Exception:
            pass  # quote() reads again and fails closed with 503.
        finally:
            setattr(self, flag, False)

    def latest(self, max_age=5):
        """The cached snapshot of the current round if its book is at most max_age seconds old."""
        now = self.now_fn()
        with self.lock:
            cached = self.snapshot
        if cached and cached[0] == self._round(now) and 0 <= now - cached[2]["observedAt"] <= max_age:
            return copy.deepcopy(cached[2])
        return None

    def quote(self):
        now = self.now_fn()
        key = self._round(now)
        with self.lock:
            cached = self.snapshot
        if cached and cached[0] == key and 0 <= now - cached[1] <= self.ttl:
            snapshot = cached[2]
        else:
            snapshot = self._read(key)
        replied = self.now_fn()
        if self._round(replied) != key:
            raise ValueError("ROUND_CHANGED_DURING_READ")
        return {**snapshot, "serverTime": replied}

    def _read(self, key):
        # Reuse a background refresh already in flight instead of starting a second slow read.
        with self.read_lock:
            now = self.now_fn()
            if self._round(now) != key:
                raise ValueError("ROUND_CHANGED_DURING_READ")
            with self.lock:
                cached = self.snapshot
            if cached and cached[0] == key and 0 <= now - cached[1] <= self.ttl:
                return cached[2]
            return self._fetch_snapshot(key)

    def _fetch_snapshot(self, key):
        tokens = self._round_tokens(key)
        up, down = tokens["Up"], tokens["Down"]
        books = self.fetch_json(CLOB_BOOKS, [{"token_id": up}, {"token_id": down}])
        received = self.now_fn()
        if (not isinstance(books, list) or len(books) != 2 or any(not isinstance(book, dict) for book in books)
                or {book.get("asset_id") for book in books} != {up, down}):
            raise ValueError("CLOB_BOOKS_MISMATCH")
        if self._round(received) != key:
            raise ValueError("ROUND_CHANGED_DURING_READ")
        # The book's own server timestamp (epoch ms) is its age; the extension's 2 s age gate
        # then bounds the market data, not the local transit.
        stamps = [book_number(book.get("timestamp")) / 1000 for book in books]
        observed = min(stamps)
        if observed > received + 1:
            raise ValueError("CLOB_BOOK_TIME_INVALID")
        by_token = {book["asset_id"]: book for book in books}
        snapshot = {
            "schemaVersion": 1, "source": "polymarket_clob_book", "periodStart": key[1],
            "slug": self._slug(key),
            "upAskCents": fill_ask_cents(by_token[up].get("asks")),
            "downAskCents": fill_ask_cents(by_token[down].get("asks")),
            "upBidCents": best_book_cents(by_token[up].get("bids"), max),
            "downBidCents": best_book_cents(by_token[down].get("bids"), max),
            "observedAt": observed,
        }
        with self.lock:
            if not self.snapshot or self.snapshot[1] <= received:
                self.snapshot = (key, received, snapshot)
        return snapshot


def curl_json(url, body=None):
    """Synchronous JSON read for the market-quote route; a JSON body makes it a POST."""
    # Same route as the async get_json: inherit the configured proxy, never disable TLS.
    command = ["curl", "--fail", "--silent", "--show-error", "--max-time", "4",
               "--max-filesize", "1000000", "--user-agent", "PolyHermes-BTC5m-Assistant/1.0",
               "--header", "Accept: application/json"]
    if body is not None:
        command += ["--header", "Content-Type: application/json",
                    "--data-binary", json.dumps(body, separators=(",", ":"), allow_nan=False)]
    try:
        process = subprocess.run(command + ["--url", url], capture_output=True, timeout=5, check=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError("HTTP_SOURCE_TIMEOUT") from None
    if process.returncode:
        raise RuntimeError("HTTP_SOURCE_TIMEOUT" if process.returncode == 28 else "HTTP_SOURCE_UNAVAILABLE")
    return json.loads(process.stdout)


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
        # The active strategy's series ("5m" or "15m") and, for 15m, the latest fresh 1h CLOB
        # snapshot; the bridge sets both once it exists.
        self.series_fn = lambda: "5m"
        self.hour_quote_fn = lambda: None
        self.seen = set()
        # Every start is weekend-only again, as every start turns the auto-ticket switch off.
        self.weekend_only = True
        ledger = self.state_dir / "rounds.jsonl"
        if ledger.exists():
            for line in ledger.read_text(encoding="utf-8").splitlines():
                claim = json.loads(line)
                # Lines written before the 15m strategy carry no series and are 5m rounds.
                self.seen.add((claim.get("series", "5m"), claim["period_start"]))

    def schedule(self):
        with self.lock:
            return {"weekendOnly": self.weekend_only}

    def set_schedule(self, weekend_only):
        if type(weekend_only) is not bool:
            raise ValueError("WEEKEND_ONLY_MUST_BE_BOOLEAN")
        with self.lock:
            self.weekend_only = weekend_only
        return self.schedule()

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
                elif now >= draft["expires_at"] or round_start_of(now, draft["series"]) != draft["period_start"]:
                    result.update(status="EXPIRED", reason="DRAFT_EXPIRED", draft=None)
                    self.state = copy.deepcopy(result)
                elif not 0 <= now - draft["price_observed_at"] <= 5:
                    result.update(status="EXPIRED", reason="CHAINLINK_SIGNAL_SAMPLE_EXPIRED", draft=None)
                    self.state = copy.deepcopy(result)
                elif result["feed_status"] != "CURRENT":
                    result.update(status="EXPIRED", reason="CHAINLINK_FEED_UNAVAILABLE", draft=None)
                    self.state = copy.deepcopy(result)
            result.update(server_time=now, updated_at=iso(now), series=self.series_fn())
            hour_quote = self.hour_quote_fn()
            result["hour_quote"] = copy.deepcopy(hour_quote) if isinstance(hour_quote, dict) else None
            return result

    def save_state(self):
        if self.observe_only:
            return
        self.state_dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_dir / "status.json.tmp"
        temporary.write_text(json.dumps(self.status(), ensure_ascii=False) + "\n", encoding="utf-8")
        temporary.replace(self.state_dir / "status.json")

    def claim_round(self, start, series="5m"):
        self.seen.add((series, start))
        if not self.observe_only:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            with (self.state_dir / "rounds.jsonl").open("a", encoding="utf-8") as ledger:
                ledger.write(json.dumps({"period_start": start, "series": series, "claimed_at": iso(self.now_fn())}) + "\n")
                ledger.flush()
                # Claim before network I/O: a crash must never create a second draft.
                os.fsync(ledger.fileno())

    async def poll(self, http_fn):
        now = self.now_fn()
        series = self.series_fn()
        period = SERIES[series]["period"]
        start = round_start_of(now, series)
        first, last = entry_bounds(start, series)
        with self.lock:
            if (self.state_dir / "STOP").exists():
                return self.status()
            if (series, start) in self.seen:
                if self.state.get("period_start") != start or self.state.get("round_series") != series:
                    self.state.update(status="SKIPPED", reason="ROUND_ALREADY_PROCESSED", draft=None,
                                      period_start=start, round_series=series)
                return self.status()
            self.state = empty_status(now)
            self.state.update(period_start=start, round_series=series)
            if self.weekend_only and not is_et_weekend(start):
                self.state.update(status="SKIPPED", reason="NOT_ET_WEEKEND")
                return self.status()
            if now < first:
                return self.status()
            self.claim_round(start, series)
            if now >= last:
                self.state.update(status="SKIPPED", reason="ENTRY_WINDOW_MISSED")
                return self.status()
            if not self.observe_only and self.boot_time >= first:
                self.state.update(status="SKIPPED", reason="STARTED_AFTER_ENTRY")
                return self.status()
        parameters = urllib.parse.urlencode({
            "symbol": "BTC", "eventStartTime": iso(start), "variant": SERIES[series]["variant"],
            "endDate": iso(start + period), "twapEnabled": "true", "twapLookbackSeconds": 60,
        })
        try:
            values = await asyncio.gather(
                http_fn(f"{GAMMA}?slug={slug_for(start, series)}"),
                http_fn(f"{CRYPTO_PRICE}?{parameters}"), http_fn(GEOBLOCK),
                return_exceptions=True,
            )
            now = self.now_fn()  # Network time is part of the entry window.
            if (self.state_dir / "STOP").exists():
                return self.status()
            if round_start_of(now, series) != start or not first <= now < last or self.series_fn() != series:
                raise ValueError("ENTRY_WINDOW_EXPIRED_DURING_READ")
            events, opening, geo = values
            if isinstance(events, Exception) or isinstance(opening, Exception):
                raise ValueError("SOURCE_REQUEST_FAILED")
            market = validate_market(events, start, series)
            opening_price = positive_number(opening["openPrice"])
            current_price, observed = validate_quote(self.quote_fn(), now)
            blocked = geo.get("blocked") if isinstance(geo, dict) else None
            blocked = blocked if isinstance(blocked, bool) else None
            side = "Up" if current_price > opening_price else "Down" if current_price < opening_price else None
            signal = {
                "id": f"{series}:{start}", "slug": market["slug"], "series": series,
                "period_start": start, "period_end": start + period, "side": side,
                "open_price": opening_price, "current_price": current_price,
                "open_price_source": SERIES[series]["open_source"],
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
                        "amount_usd": 1, "created_at": now, "expires_at": last,
                        "trade_ready": True, "manual_submit_required": True,
                        "platform_amount_validation_required": True,
                    })
        except (KeyError, TypeError, ValueError, AttributeError) as error:
            with self.lock:
                reason = str(error) if isinstance(error, ValueError) else "INVALID_SOURCE_RESPONSE"
                self.state.update(status="SKIPPED", reason=reason, draft=None)
        return self.status()


def make_server(assistant, address=LOCAL_ADDRESS, bridge=None, market_quote=None):
    if address[0] != "127.0.0.1":
        raise ValueError("ASSISTANT_REQUIRES_LOOPBACK")

    class Handler(BaseHTTPRequestHandler):
        def valid_host(self):
            if self.headers.get("Host") != f"{address[0]}:{self.server.server_port}":
                self.send_error(403)
                return False
            return True

        def reply(self, value, status=200):
            body = json.dumps(value, ensure_ascii=False, allow_nan=False).encode("utf-8")
            self.send_response(status)
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

        def reply_market_quote(self):
            # Same access as the preparation read; the extension compares it before its Buy click.
            if not self.preparation_access():
                return
            if self.path != MARKET_QUOTE_PATH or self.headers.get("Content-Length", "0") != "0":
                self.send_error(400)
                return
            try:
                value = market_quote()
                if type(value) is not dict or set(value) != MARKET_QUOTE_FIELDS:
                    raise ValueError("INVALID_MARKET_QUOTE")
                json.dumps(value, allow_nan=False)
            except Exception as error:
                # Any source, shape or timeout failure: the extension must not click.
                code = str(error) if str(error) in MARKET_QUOTE_ERRORS else "INVALID_MARKET_QUOTE"
                self.reply({"errorCode": code}, status=503)
                return
            self.reply(value)

        def do_GET(self):
            if not self.valid_host():
                return
            if self.path in ("/status", "/draft"):
                self.reply(assistant.status())
                return
            url = urllib.parse.urlsplit(self.path)
            if market_quote is not None and url.path == MARKET_QUOTE_PATH:
                self.reply_market_quote()
                return
            if bridge is None:
                self.send_error(404)
                return
            try:
                if url.path == "/bridge/status" and not url.query:
                    self.reply(bridge.status())
                elif self.path == "/bridge/preparation":
                    if not self.preparation_access():
                        return
                    if self.headers.get("Content-Length", "0") != "0":
                        raise ValueError("GET_BODY_NOT_ALLOWED")
                    self.reply(bridge.preparation())
                elif self.path == SCHEDULE_PATH:
                    if not self.preparation_access():
                        return
                    if self.headers.get("Content-Length", "0") != "0":
                        raise ValueError("GET_BODY_NOT_ALLOWED")
                    self.reply(assistant.schedule())
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
            preparation = self.path in ("/bridge/preparation/claim", "/bridge/preparation/ack", "/bridge/preparation/buy-audit",
                                        SCHEDULE_PATH)
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
                limit = 1500 if preflight or self.path in ("/bridge/preparation/ack", "/bridge/preparation/buy-audit") else 256
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
                elif self.path == "/bridge/preparation/buy-audit":
                    self.reply(bridge.report_buy_attempt(payload))
                elif self.path == SCHEDULE_PATH:
                    if type(payload) is not dict or set(payload) != {"weekendOnly"}:
                        raise ValueError("WEEKEND_ONLY_MUST_BE_BOOLEAN")
                    self.reply(assistant.set_schedule(payload["weekendOnly"]))
                elif preflight:
                    self.reply(bridge.report_preflight(payload))
                else:
                    if type(payload) is dict and set(payload) == {"strategy"} and isinstance(payload["strategy"], str):
                        self.reply(bridge.set_strategy(payload["strategy"]))
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
    runtime_server = None
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
        assistant.series_fn = lambda: bridge.series
        market_quotes = ClobMarketQuotes(curl_json, series_fn=lambda: bridge.series)
        # The 15m strategy trades only against the concurrent ET-hour favorite.
        hour_quotes = ClobMarketQuotes(curl_json, series_fn=lambda: "1h")
        assistant.hour_quote_fn = lambda: hour_quotes.latest(5) if bridge.series == "15m" else None
        server = make_server(assistant, bridge=bridge, market_quote=market_quotes.quote)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        runtime_server = await start_runtime_server()
        print("ASSIST_ONLY http://127.0.0.1:8766/status; no order submission. STOP: " + str(args.state_dir / "STOP"), flush=True)
        while True:
            market_quotes.warm()
            if bridge.series == "15m":
                now = time.time()
                first, last = entry_bounds(round_start_of(now, "15m"), "15m")
                hour_quotes.warm(refresh=first - 10 <= now < last)
            await assistant.poll(get_json)
            assistant.state["feed_reason"] = feed.error
            assistant.save_state()
            bridge.observe()
            await asyncio.sleep(0.5)
    finally:
        feed_task.cancel()
        await asyncio.gather(feed_task, return_exceptions=True)
        if runtime_server:
            runtime_server.close()
            await runtime_server.wait_closed()
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
