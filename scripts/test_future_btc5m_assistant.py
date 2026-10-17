import asyncio
import json
import ssl
import subprocess
import sys
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

sys.path.insert(0, str(Path(__file__).parent))

from future_btc5m_assistant import (Assistant, CLOB_BOOKS, ChainlinkFeed, ClobMarketQuotes, GAMMA, GEOBLOCK,
                                    MARKET_QUOTE_FIELDS, curl_json, iso, is_et_weekend, make_server, round_start)
import future_btc5m_assistant


START = int(datetime(2026, 10, 10, 12, 0, tzinfo=timezone.utc).timestamp())


def market(start=START):
    slug = f"btc-updown-5m-{start}"
    return [{
        "slug": slug, "active": True, "closed": False, "endDate": iso(start + 300),
        "markets": [{
            "slug": slug, "active": True, "closed": False, "acceptingOrders": True,
            "endDate": iso(start + 300), "eventStartTime": iso(start),
            "startDate": iso(start - 86400), "conditionId": "0xabc",
            "cryptoMarketConfig": {"asset": "btc", "duration": "5m",
                                   "twapEnabled": True, "twapLookbackSeconds": 60},
            "outcomes": '["Down", "Up"]', "clobTokenIds": '["222", "111"]',
        }],
    }]


def round_tokens(start):
    # Distinct per round, so a stale token cache would show up as a book mismatch.
    return str(start) + "1", str(start) + "2"


def round_market(start):
    events = market(start)
    up, down = round_tokens(start)
    events[0]["markets"][0]["clobTokenIds"] = json.dumps([down, up])
    return events


def book(token, asks=(), bids=(), timestamp=None):
    # A None timestamp is stamped by FakeClob with the test clock (the CLOB's server time).
    return {"market": "0xabc", "asset_id": token, "timestamp": timestamp, "hash": "h",
            "asks": [{"price": price, "size": size} for price, size in asks],
            "bids": [{"price": price, "size": size} for price, size in bids]}


DEFAULT_BOOKS = object()


class FakeClob:
    """Stands in for Gamma and CLOB /books; no network I/O."""

    def __init__(self, test):
        self.test = test
        self.calls = []
        self.events = round_market
        self.books = DEFAULT_BOOKS

    def __call__(self, url, body=None):
        self.calls.append((url, body))
        if url.startswith(GAMMA + "?slug=btc-updown-5m-"):
            self.test.assertIsNone(body)
            return self.events(int(url.rsplit("-", 1)[1]))
        self.test.assertEqual(CLOB_BOOKS, url)
        if self.books is not DEFAULT_BOOKS:
            return self.stamped(self.books)
        up, down = body[0]["token_id"], body[1]["token_id"]
        # CLOB sorts asks high-to-low and bids low-to-high; return the Down book first.
        return self.stamped([book(down, asks=[("0.47", "10"), ("0.45", "3")], bids=[("0.40", "5"), ("0.43", "2")]),
                             book(up, asks=[("0.62", "10"), ("0.6", "5"), ("0.57", "1")],
                                  bids=[("0.5", "1"), ("0.55", "4")])])

    def stamped(self, books):
        if not isinstance(books, list):
            return books
        stamp = str(round(getattr(self.test, "clock", START) * 1000))
        return [{**item, "timestamp": stamp} if isinstance(item, dict) and item.get("timestamp") is None else item
                for item in books]

    def urls(self):
        return [url for url, _ in self.calls]


def verified_future_eligibility():
    # Isolated fixture for the unfinished official-provider path, never runtime input.
    return {"status": "VERIFIED", "venue": "future.news", "operation": "PREPARE_USD_BUY_AMOUNT",
            "source_url": "https://future.news/__test_only__/amount-preparation-eligibility"}


class FutureBtc5mAssistantTest(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.eligibility_patch = patch("future_btc5m_assistant.future_eligibility",
                                       return_value=verified_future_eligibility())
        self.eligibility_patch.start()
        self.addCleanup(self.eligibility_patch.stop)
        self.path = Path(self.directory.name)
        self.clock = START + 10.0
        self.quote = {"price": 83001, "observed_at": START + 60.0, "received_at": START + 60.0}
        self.events = market()
        self.opening = {"openPrice": 83000}
        self.geo = {"blocked": False}
        self.calls = []
        self.assistant = Assistant(self.path, lambda: self.quote, lambda: self.clock)

    async def http(self, url):
        self.calls.append(url)
        if url == GEOBLOCK:
            if isinstance(self.geo, Exception):
                raise self.geo
            return self.geo
        if "/events?" in url:
            return self.events
        return self.opening

    async def evaluate(self, at=60):
        self.clock = START + at
        self.quote = {**self.quote, "observed_at": self.clock, "received_at": self.clock}
        return await self.assistant.poll(self.http)

    async def test_weekday_rounds_run_only_after_weekend_only_is_turned_off_and_restart_restores_it(self):
        monday = START + 2 * 86400
        self.assertEqual({"weekendOnly": True}, self.assistant.schedule())
        self.clock = monday + 30
        status = await self.assistant.poll(self.http)
        self.assertEqual(("SKIPPED", "NOT_ET_WEEKEND"), (status["status"], status["reason"]))
        self.assertEqual({"weekendOnly": False}, self.assistant.set_schedule(False))
        status = await self.assistant.poll(self.http)
        self.assertNotEqual("NOT_ET_WEEKEND", status["reason"])
        self.assertEqual(monday, status["period_start"])
        for value in (0, 1, "false", None):
            with self.assertRaises(ValueError):
                self.assistant.set_schedule(value)
        self.assertEqual({"weekendOnly": False}, self.assistant.schedule())
        restarted = Assistant(self.path, lambda: self.quote, lambda: self.clock)
        self.assertEqual({"weekendOnly": True}, restarted.schedule())

    def test_round_alignment_and_et_weekend_cover_dst_boundaries(self):
        for timestamp, expected in [
            ("2026-10-10T03:59:59+00:00", False),
            ("2026-10-10T04:00:00+00:00", True),
            ("2026-10-12T03:59:59+00:00", True),
            ("2026-10-12T04:00:00+00:00", False),
            ("2026-11-07T04:59:59+00:00", False),
            ("2026-11-07T05:00:00+00:00", True),
            ("2026-03-07T04:59:59+00:00", False),
            ("2026-03-07T05:00:00+00:00", True),
            ("2026-03-09T04:00:00+00:00", False),
        ]:
            with self.subTest(timestamp=timestamp):
                self.assertEqual(expected, is_et_weekend(datetime.fromisoformat(timestamp).timestamp()))
        self.assertEqual(START, round_start(START + 299.999))
        self.assertEqual(START + 300, round_start(START + 300))

    async def test_up_draft_is_one_dollar_exact_round_and_requires_manual_submit(self):
        status = await self.evaluate()
        draft = status["draft"]
        self.assertEqual("READY", status["status"])
        self.assertEqual("ASSIST_ONLY", status["mode"])
        self.assertFalse(status["live_enabled"])
        self.assertEqual(1, draft["amount_usd"])
        self.assertEqual("111", draft["token_id"])
        self.assertEqual("Up", draft["side"])
        self.assertEqual(START + 80, draft["expires_at"])
        self.assertTrue(draft["manual_submit_required"])
        self.assertTrue(draft["platform_amount_validation_required"])
        self.assertTrue(draft["trade_ready"])
        opening_url = next(url for url in self.calls if "crypto-price?" in url)
        params = urllib.parse.parse_qs(urllib.parse.urlsplit(opening_url).query)
        self.assertEqual(["fiveminute"], params["variant"])
        self.assertEqual([iso(START)], params["eventStartTime"])
        self.assertEqual([iso(START + 300)], params["endDate"])
        self.assertFalse(any("binance" in url or "/book" in url for url in self.calls))

    async def test_down_and_tie(self):
        self.quote["price"] = 82999
        status = await self.evaluate()
        self.assertEqual("Down", status["draft"]["side"])
        self.assertEqual("222", status["draft"]["token_id"])
        other = Assistant(self.path / "flat", lambda: self.quote, lambda: self.clock, observe_only=True)
        self.quote["price"] = 83000
        status = await other.poll(self.http)
        self.assertEqual("PRICE_FLAT", status["reason"])
        self.assertIsNone(status["draft"])

    async def test_twap_query_matches_page_reference_and_prevents_reversed_signal(self):
        self.quote["price"] = 82981.96147108926

        async def reference_http(url):
            if "crypto-price?" in url:
                self.calls.append(url)
                params = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query)
                twap = params.get("twapEnabled") == ["true"] and params.get("twapLookbackSeconds") == ["60"]
                # Same round's official page/API A/B values. The default reverses the side.
                return {"openPrice": 82980.01481629249 if twap else 82981.98681761073}
            return await self.http(url)

        self.clock = START + 60
        status = await self.assistant.poll(reference_http)
        self.assertEqual("Up", status["signal"]["side"])
        self.assertEqual(82980.01481629249, status["signal"]["open_price"])
        self.assertEqual("polymarket_crypto_price_fiveminute_twap60_openPrice", status["signal"]["open_price_source"])
        self.assertEqual(60, status["draft"]["twap_lookback_seconds"])

    async def test_missing_or_different_twap_market_config_rejects_signal_and_draft(self):
        good = market()[0]["markets"][0]["cryptoMarketConfig"]
        configs = [None, {}, {**good, "asset": "eth"}, {**good, "duration": "15m"},
                   {**good, "twapEnabled": False}, {**good, "twapEnabled": "true"},
                   {**good, "twapLookbackSeconds": 30}]
        for index, config in enumerate(configs):
            with self.subTest(config=config):
                self.clock = START + 10
                self.events = market()
                self.events[0]["markets"][0]["cryptoMarketConfig"] = config
                assistant = Assistant(self.path / str(index), lambda: self.quote, lambda: self.clock)
                self.clock = START + 60
                status = await assistant.poll(self.http)
                self.assertEqual("WRONG_MARKET_PRICE_CONFIG", status["reason"])
                self.assertIsNone(status["signal"])
                self.assertIsNone(status["draft"])

    async def test_entry_boundaries_no_early_or_late_read(self):
        status = await self.evaluate(59.999)
        self.assertEqual("WAITING", status["status"])
        self.assertEqual([], self.calls)
        status = await self.evaluate(79.999)
        self.assertEqual("READY", status["status"])
        self.clock = START + 80
        self.assertEqual("DRAFT_EXPIRED", self.assistant.status()["reason"])
        self.assertIsNone(self.assistant.status()["draft"])
        late = Assistant(self.path / "late", lambda: self.quote, lambda: self.clock)
        status = await late.poll(self.http)
        self.assertEqual("ENTRY_WINDOW_MISSED", status["reason"])
        self.assertIsNone(status["draft"])

    async def test_feed_unavailability_is_visible_even_before_entry(self):
        self.quote = None
        status = await self.assistant.poll(self.http)
        self.assertEqual("WAITING", status["status"])
        self.assertEqual("UNAVAILABLE", status["feed_status"])
        self.assertEqual([], self.calls)
        self.quote = {"price": 83001, "observed_at": self.clock, "received_at": self.clock}
        self.assertEqual("CURRENT", self.assistant.status()["feed_status"])

    async def test_missing_proxy_dependency_is_exposed_without_changing_route(self):
        feed = ChainlinkFeed()
        with patch("future_btc5m_assistant.websockets.connect", side_effect=ImportError("python-socks")) as connect:
            with patch("future_btc5m_assistant.asyncio.sleep", side_effect=asyncio.CancelledError):
                with self.assertRaises(asyncio.CancelledError):
                    await feed.run()
        self.assertEqual("CHAINLINK_FEED_PROXY_DEPENDENCY_UNAVAILABLE", feed.error)
        self.assertIsNone(feed.quote)
        self.assertNotIn("proxy", connect.call_args.kwargs)

    async def test_once_feed_failure_finishes_without_starting_another_handshake(self):
        for error in [ImportError("python-socks"), TimeoutError("opening handshake")]:
            feed = ChainlinkFeed()
            with patch("future_btc5m_assistant.websockets.connect", side_effect=error) as connect:
                await asyncio.wait_for(feed.run(single_attempt=True), timeout=0.2)
            self.assertEqual(1, connect.call_count)
            self.assertIsNone(feed.quote)
            self.assertIsNotNone(feed.error)

    async def test_feed_uses_verified_tls_and_compact_chainlink_filter(self):
        sent = []

        class Socket:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def send(self, message):
                sent.append(json.loads(message))

            async def recv(self):
                raise ConnectionResetError("disconnected")

        with patch("future_btc5m_assistant.websockets.connect", return_value=Socket()) as connect:
            await ChainlinkFeed().run(single_attempt=True)
        context = connect.call_args.kwargs["ssl"]
        self.assertEqual(ssl.CERT_REQUIRED, context.verify_mode)
        self.assertTrue(context.check_hostname)
        self.assertNotIn("proxy", connect.call_args.kwargs)
        self.assertEqual({"action": "subscribe", "subscriptions": [{
            "topic": "crypto_prices_chainlink", "type": "*",
            "filters": '{"symbol":"btc/usd"}',
        }]}, sent[0])

    async def test_tls_and_handshake_timeout_have_distinct_reasons(self):
        for error, reason in [
            (ssl.SSLCertVerificationError("issuer missing"), "CHAINLINK_FEED_TLS_CERTIFICATE_VERIFY_FAILED"),
            (TimeoutError("opening handshake"), "CHAINLINK_FEED_CONNECTION_TIMEOUT"),
        ]:
            with self.subTest(reason=reason):
                feed = ChainlinkFeed()
                with patch("future_btc5m_assistant.websockets.connect", side_effect=error):
                    await feed.run(single_attempt=True)
                self.assertEqual(reason, feed.error)
                self.assertIsNone(feed.quote)

    async def test_socket_disconnect_clears_last_quote_before_reconnect_delay(self):
        feed = ChainlinkFeed()

        class Socket:
            messages = 0

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def send(self, message):
                pass

            async def recv(self):
                self.messages += 1
                if self.messages == 1:
                    return json.dumps({"topic": "crypto_prices_chainlink", "payload": {
                        "symbol": "btc/usd", "value": 83001, "timestamp": (START + 60) * 1000,
                    }})
                assert feed.quote is not None
                raise ConnectionResetError("disconnected")

        with patch("future_btc5m_assistant.websockets.connect", return_value=Socket()):
            with patch("future_btc5m_assistant.time.time", return_value=START + 60):
                await feed.run(single_attempt=True)
        self.assertIsNone(feed.quote)
        self.assertEqual("CHAINLINK_FEED_CONNECTION_UNAVAILABLE", feed.error)

    async def test_round_is_rechecked_after_network_reads(self):
        async def slow_http(url):
            result = await self.http(url)
            self.clock = START + 80.1
            return result

        self.clock = START + 79
        status = await self.assistant.poll(slow_http)
        self.assertEqual("ENTRY_WINDOW_EXPIRED_DURING_READ", status["reason"])
        self.assertIsNone(status["draft"])

    async def test_missing_stale_future_or_nonfinite_prices_never_create_draft(self):
        for quote in [
            None,
            {"price": 83001, "observed_at": START + 54.999, "received_at": START + 60},
            {"price": 83001, "observed_at": START + 60.001, "received_at": START + 60},
            {"price": 83001, "observed_at": START + 60, "received_at": START + 60.001},
            {"price": float("nan"), "observed_at": START + 60, "received_at": START + 60},
        ]:
            with self.subTest(quote=quote):
                self.clock = START + 10
                assistant = Assistant(self.path / str(len(self.calls)), lambda: quote, lambda: self.clock)
                self.clock = START + 60
                status = await assistant.poll(self.http)
                self.assertIsNone(status["draft"])
                self.assertIsNone(status["signal"])
        self.clock = START + 10
        assistant = Assistant(self.path / "five", lambda: {
            "price": 83001, "observed_at": START + 55, "received_at": START + 55,
        }, lambda: self.clock)
        self.clock = START + 60
        self.assertEqual("READY", (await assistant.poll(self.http))["status"])

    async def test_missing_open_price_is_not_replaced_by_another_price_source(self):
        self.opening = {"closePrice": 83000}
        status = await self.evaluate()
        self.assertIsNone(status["draft"])
        self.assertEqual("INVALID_SOURCE_RESPONSE", status["reason"])
        self.assertEqual(3, len(self.calls))

    async def test_invalid_market_identity_period_status_and_tokens_fail_closed(self):
        mutations = [
            ("event", "slug", f"btc-updown-15m-{START}"),
            ("event", "active", False),
            ("event", "closed", True),
            ("market", "slug", f"btc-updown-5m-{START - 300}"),
            ("market", "endDate", iso(START + 900)),
            ("market", "eventStartTime", iso(START - 300)),
            ("market", "acceptingOrders", False),
            ("market", "outcomes", '["Yes", "No"]'),
            ("market", "clobTokenIds", '["111", "111"]'),
        ]
        for index, (level, key, value) in enumerate(mutations):
            with self.subTest(key=key, value=value):
                self.clock = START + 10
                self.events = market()
                target = self.events[0] if level == "event" else self.events[0]["markets"][0]
                target[key] = value
                assistant = Assistant(self.path / str(index), lambda: self.quote, lambda: self.clock)
                self.clock = START + 60
                self.assertIsNone((await assistant.poll(self.http))["draft"])

    async def test_geo_blocked_missing_and_failure_leave_only_observation(self):
        for index, geo in enumerate([{"blocked": True}, {}, {"blocked": "false"}, RuntimeError("HTTP 503")]):
            with self.subTest(geo=geo):
                self.clock = START + 10
                assistant = Assistant(self.path / str(index), lambda: self.quote, lambda: self.clock)
                self.clock = START + 60
                self.geo = geo
                status = await assistant.poll(self.http)
                self.assertEqual("OBSERVING", status["status"])
                self.assertEqual("Up", status["signal"]["side"])
                self.assertIsNone(status["draft"])

    async def test_polymarket_false_cannot_verify_future_amount_preparation(self):
        self.eligibility_patch.stop()
        status = await self.evaluate()
        self.assertEqual("OBSERVING", status["status"])
        self.assertEqual("FUTURE_ELIGIBILITY_UNKNOWN", status["reason"])
        self.assertIsNone(status["draft"])
        self.assertEqual({"blocked": False, "source_url": GEOBLOCK}, status["geoblock"])
        self.assertEqual({"status": "UNKNOWN", "venue": "future.news",
                          "operation": "PREPARE_USD_BUY_AMOUNT", "source_url": None},
                         status["future_eligibility"])
        self.assertEqual("Up", status["signal"]["side"])
        self.assertEqual("chainlink", status["signal"]["price_source"])

    async def test_unknown_restricted_missing_or_wrong_future_evidence_rejects_draft(self):
        good = verified_future_eligibility()
        evidence = [
            (None, "UNVERIFIED"), ({}, "UNVERIFIED"),
            ({**good, "status": "UNKNOWN"}, "UNKNOWN"),
            ({**good, "status": "RESTRICTED"}, "RESTRICTED"),
            ({**good, "venue": "polymarket.com"}, "UNVERIFIED"),
            ({**good, "operation": "SUBMIT_BUY_ORDER"}, "UNVERIFIED"),
            ({**good, "source_url": None}, "UNVERIFIED"),
            ({**good, "source_url": 1}, "UNVERIFIED"),
            ({**good, "source_url": ""}, "UNVERIFIED"),
            ({**good, "source_url": "https://polymarket.com/api/geoblock"}, "UNVERIFIED"),
            ({**good, "source_url": "http://future.news/eligibility"}, "UNVERIFIED"),
            ({**good, "source_url": "https://future.news.evil.test/eligibility"}, "UNVERIFIED"),
            ({**good, "source_url": "https://future.news"}, "UNVERIFIED"),
            ({**good, "source_url": "https://future.news/"}, "UNVERIFIED"),
            ({**good, "source_url": "https://user:pass@future.news/eligibility"}, "UNVERIFIED"),
            ({**good, "source_url": "https://future.news:444/eligibility"}, "UNVERIFIED"),
            ({**good, "source_url": "https://future.news:invalid/eligibility"}, "UNVERIFIED"),
        ]
        for index, (eligibility, reason) in enumerate(evidence):
            with self.subTest(eligibility=eligibility):
                self.clock = START + 10
                assistant = Assistant(self.path / str(index), lambda: self.quote, lambda: self.clock)
                self.clock = START + 60
                with patch("future_btc5m_assistant.future_eligibility", return_value=eligibility):
                    status = await assistant.poll(self.http)
                self.assertEqual("OBSERVING", status["status"])
                self.assertEqual("FUTURE_ELIGIBILITY_" + reason, status["reason"])
                self.assertIsNone(status["draft"])
                self.assertEqual("Up", status["signal"]["side"])
                self.assertEqual("chainlink", status["signal"]["price_source"])

    async def test_future_evidence_is_in_every_state_and_rechecked_before_draft_read(self):
        waiting = self.assistant.status()
        self.assertEqual(verified_future_eligibility(), waiting["future_eligibility"])
        self.assertEqual({"blocked": None, "source_url": GEOBLOCK}, waiting["geoblock"])
        ready = await self.evaluate()
        self.assertEqual(verified_future_eligibility(), ready["future_eligibility"])
        self.assertIsNotNone(ready["draft"])
        self.assistant.state.pop("future_eligibility")  # Legacy in-memory state lacks the new metadata.
        self.eligibility_patch.stop()
        rejected = self.assistant.status()
        self.assertEqual("FUTURE_ELIGIBILITY_UNKNOWN", rejected["reason"])
        self.assertIsNone(rejected["draft"])

    async def test_stop_cancels_existing_draft_and_never_restores_it(self):
        self.assertIsNotNone((await self.evaluate())["draft"])
        (self.path / "STOP").touch()
        self.assertEqual("STOPPED", self.assistant.status()["status"])
        self.assertIsNone(self.assistant.status()["draft"])
        (self.path / "STOP").unlink()
        self.assertIsNone((await self.assistant.poll(self.http))["draft"])
        self.assertEqual(3, len(self.calls))

    async def test_stop_before_or_during_read_prohibits_drafts(self):
        (self.path / "STOP").touch()
        status = await self.evaluate()
        self.assertEqual("STOPPED", status["status"])
        self.assertEqual([], self.calls)
        (self.path / "STOP").unlink()

        async def stopping_http(url):
            result = await self.http(url)
            (self.path / "STOP").touch()
            return result

        status = await self.assistant.poll(stopping_http)
        self.assertEqual("STOPPED", status["status"])
        self.assertIsNone(status["draft"])

    async def test_draft_also_expires_when_signal_quote_is_over_five_seconds_old(self):
        await self.evaluate()
        self.clock = START + 65.001
        self.assertEqual("CHAINLINK_SIGNAL_SAMPLE_EXPIRED", self.assistant.status()["reason"])
        self.assertIsNone(self.assistant.status()["draft"])

    async def test_feed_disconnect_immediately_invalidates_existing_draft(self):
        self.assertIsNotNone((await self.evaluate())["draft"])
        self.quote = None
        status = self.assistant.status()
        self.assertEqual("UNAVAILABLE", status["feed_status"])
        self.assertIsNone(status["draft"])

    async def test_restart_and_repeat_deduplicate_without_restoring_draft(self):
        await self.evaluate()
        self.assistant.save_state()
        self.assertEqual(1, len((self.path / "rounds.jsonl").read_text().splitlines()))
        await self.assistant.poll(self.http)
        restarted = Assistant(self.path, lambda: self.quote, lambda: self.clock)
        status = await restarted.poll(self.http)
        self.assertEqual("ROUND_ALREADY_PROCESSED", status["reason"])
        self.assertIsNone(status["draft"])
        self.assertEqual(3, len(self.calls))

    async def test_starting_after_trigger_does_not_catch_up(self):
        self.clock = START + 61
        restarted = Assistant(self.path, lambda: self.quote, lambda: self.clock)
        status = await restarted.poll(self.http)
        self.assertEqual("STARTED_AFTER_ENTRY", status["reason"])
        self.assertEqual([], self.calls)
        self.assertIsNone(status["draft"])

    async def test_once_observes_without_a_draft_or_consuming_round(self):
        self.clock = START + 60
        assistant = Assistant(self.path, lambda: self.quote, lambda: self.clock, observe_only=True)
        status = await assistant.poll(self.http)
        self.assertEqual("ONCE_OBSERVATION_ONLY", status["reason"])
        self.assertEqual("Up", status["signal"]["side"])
        self.assertIsNone(status["draft"])
        self.assertFalse((self.path / "rounds.jsonl").exists())

    async def test_request_failure_is_recorded_without_replaying_the_round_or_fabricating_signal(self):
        async def failing_http(url):
            self.calls.append(url)
            raise ConnectionResetError("connection reset")

        self.clock = START + 60
        status = await self.assistant.poll(failing_http)
        self.assertEqual("SOURCE_REQUEST_FAILED", status["reason"])
        self.assertIsNone(status["draft"])
        self.assertIsNone(status["signal"])
        await self.assistant.poll(self.http)
        self.assertEqual(7, len(self.calls), "critical reads retry twice; geoblock is read once")

    async def test_request_failure_names_the_failed_sources_without_private_error_text(self):
        async def failing_http(url):
            if url.startswith(GAMMA):
                raise RuntimeError("HTTP_SOURCE_CONNECTION_RESET")
            if url == GEOBLOCK:
                return self.geo
            raise TimeoutError("private proxy detail")

        self.clock = START + 60
        status = await self.assistant.poll(failing_http)
        self.assertEqual("SOURCE_REQUEST_FAILED", status["reason"])
        self.assertEqual({"GAMMA": "HTTP_SOURCE_CONNECTION_RESET", "OPENING_PRICE": "HTTP_SOURCE_TIMEOUT"},
                         status["source_errors"])
        self.assertIsNone(status["signal"])
        self.assertIsNone(status["draft"])
        self.assertNotIn("private", json.dumps(status))

    async def test_server_only_exposes_get_and_stop_is_effective_on_next_read(self):
        await self.evaluate()
        server = make_server(self.assistant, ("127.0.0.1", 0))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        url = f"http://127.0.0.1:{server.server_port}"
        local = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with local.open(url + "/draft") as response:
                self.assertEqual(1, json.load(response)["draft"]["amount_usd"])
            (self.path / "STOP").touch()
            with local.open(url + "/status") as response:
                self.assertIsNone(json.load(response)["draft"])
            for request, code in [
                (urllib.request.Request(url + "/submit", data=b"{}", method="POST"), 501),
                (urllib.request.Request(url + "/status", headers={"Host": "evil.example"}), 403),
            ]:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    local.open(request)
                self.assertEqual(code, error.exception.code)
                error.exception.close()
        finally:
            await asyncio.to_thread(server.shutdown)
            server.server_close()
            thread.join(timeout=2)


class ChainlinkFeedTest(unittest.TestCase):
    def test_empty_default_ca_store_loads_existing_system_bundle(self):
        for ca_count in (0, 1):
            with self.subTest(ca_count=ca_count):
                context = Mock(spec=ssl.SSLContext)
                context.cert_store_stats.return_value = {"x509_ca": ca_count}
                with patch("future_btc5m_assistant.ssl.create_default_context", return_value=context):
                    with patch("future_btc5m_assistant.Path.is_file", return_value=True):
                        self.assertIs(context, future_btc5m_assistant.feed_ssl_context())
                if ca_count == 0:
                    context.load_verify_locations.assert_called_once_with(cafile="/etc/ssl/cert.pem")
                else:
                    context.load_verify_locations.assert_not_called()

    def test_a_rejected_frame_cannot_clear_feed_diagnostic(self):
        feed = ChainlinkFeed()
        feed.error = "CHAINLINK_FEED_WAITING_FOR_PRICE"
        self.assertFalse(feed.ingest({"topic": "crypto_prices", "type": "subscribe", "payload": {
            "symbol": "btc/usd", "data": [{"value": 83001, "timestamp": (START + 60) * 1000}],
        }}, START + 60))
        self.assertEqual("CHAINLINK_FEED_WAITING_FOR_PRICE", feed.error)
        self.assertTrue(feed.ingest({"topic": "crypto_prices_chainlink", "payload": {
            "symbol": "btc/usd", "value": 83001, "timestamp": (START + 60) * 1000,
        }}, START + 60))
        self.assertIsNone(feed.error)

    def test_feed_requires_exact_source_symbol_timestamp_and_positive_price(self):
        for topic, payload in [
            ("crypto_prices", {"symbol": "btcusdt", "value": 83001, "timestamp": (START + 60) * 1000}),
            ("crypto_prices_chainlink", {"symbol": "eth/usd", "value": 83001, "timestamp": (START + 60) * 1000}),
            ("crypto_prices_chainlink", {"symbol": "btc/usd", "value": 83001}),
            ("crypto_prices_chainlink", {"symbol": "btc/usd", "value": 83001, "timestamp": (START + 61) * 1000}),
            ("crypto_prices_chainlink", {"symbol": "btc/usd", "value": 0, "timestamp": (START + 60) * 1000}),
        ]:
            with self.subTest(topic=topic, payload=payload):
                feed = ChainlinkFeed()
                self.assertFalse(feed.ingest({"topic": topic, "payload": payload}, START + 60))
                self.assertIsNone(feed.quote)

    def test_feed_uses_latest_fresh_history_point_and_rejects_out_of_order_update(self):
        feed = ChainlinkFeed()
        message = {"topic": "crypto_prices_chainlink", "payload": {"symbol": "btc/usd", "data": [
            {"value": 83001, "timestamp": (START + 60) * 1000},
            {"value": 80000, "timestamp": (START + 54) * 1000},
            {"value": 83000, "timestamp": (START + 59) * 1000},
        ]}}
        self.assertTrue(feed.ingest(json.dumps(message), START + 60))
        self.assertEqual(83001, feed.quote["price"])
        self.assertFalse(feed.ingest({"topic": "crypto_prices_chainlink", "payload": {
            "symbol": "btc/usd", "value": 82999, "timestamp": (START + 59) * 1000,
        }}, START + 60))
        self.assertEqual(83001, feed.quote["price"])
        self.assertFalse(feed.ingest("PONG", START + 60))


class ClobMarketQuotesTest(unittest.TestCase):
    def setUp(self):
        self.clock = START + 61.25
        self.clob = FakeClob(self)
        self.quotes = ClobMarketQuotes(self.clob, lambda: self.clock)

    def test_pre_click_read_shares_the_inflight_background_book_fetch(self):
        self.quotes.prefetch_tokens()
        entered, release, duplicate = threading.Event(), threading.Event(), threading.Event()
        calls, replies, failures = [], [], []

        def slow(url, body=None):
            if url == CLOB_BOOKS:
                calls.append(url)
                if len(calls) > 1:
                    duplicate.set()
                entered.set()
                if not release.wait(2):
                    raise TimeoutError("test did not release the read")
            return self.clob(url, body)

        def read():
            try:
                replies.append(self.quotes.quote())
            except Exception as error:
                failures.append(error)

        self.quotes.fetch_json = slow
        self.quotes.warm()
        self.assertTrue(entered.wait(1))
        reader = threading.Thread(target=read)
        reader.start()
        try:
            duplicate.wait(0.2)
        finally:
            release.set()
            reader.join(2)
        self.assertFalse(reader.is_alive())
        self.assertEqual([], failures)
        self.assertEqual([CLOB_BOOKS], calls, "the pre-click read must reuse the warming request")
        self.assertEqual(self.clock, replies[0]["observedAt"])

    def test_prefetched_tokens_leave_only_the_book_read_for_the_pre_click_quote(self):
        self.clock = START + 3
        self.quotes.prefetch_tokens()
        self.assertEqual([f"{GAMMA}?slug=btc-updown-5m-{START}"], self.clob.urls())
        self.clock = START + 61.25
        self.quotes.quote()
        self.assertEqual([f"{GAMMA}?slug=btc-updown-5m-{START}", CLOB_BOOKS], self.clob.urls())

    def test_warm_starts_one_background_prefetch_per_round_and_retries_failures_after_10s(self):
        started = []
        real_thread = threading.Thread

        class InlineThread:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args
                started.append(daemon)

            def start(self):
                self.target(*self.args)

        threading.Thread = InlineThread
        self.addCleanup(setattr, threading, "Thread", real_thread)
        self.clock = START + 2
        self.clob.events = lambda start: []  # Gamma not listing the round yet
        self.assertTrue(self.quotes.warm())
        self.assertIsNone(self.quotes.tokens)
        self.assertFalse(self.quotes.warming)
        self.clock = START + 11.9
        self.assertFalse(self.quotes.warm(), "a failed prefetch waits 10 s before retrying")
        self.clob.events = round_market
        self.clock = START + 12
        self.assertTrue(self.quotes.warm())
        self.assertEqual(("5m", START), self.quotes.tokens[0])
        self.clock = START + 40
        self.assertFalse(self.quotes.warm(), "the round's tokens are already cached")
        self.clock = START + 300 + 1
        self.assertTrue(self.quotes.warm(), "a new round prefetches its own tokens")
        self.assertEqual(("5m", START + 300), self.quotes.tokens[0])
        self.assertEqual([True, True, True], started)
        self.assertNotIn(CLOB_BOOKS, self.clob.urls(), "warming never reads books")

    def test_dust_and_thin_asks_never_set_the_price_and_an_unfillable_side_is_null(self):
        up, down = round_tokens(START)
        self.clob.books = [book(up, asks=[("0.60", "0.2"), ("0.70", "500")]),
                           book(down, asks=[("0.30", "1"), ("0.31", "1")])]
        quote = self.quotes.quote()
        self.assertEqual((70, None), (quote["upAskCents"], quote["downAskCents"]))

    def test_observed_at_is_the_books_server_time_not_the_local_receive_time(self):
        up, down = round_tokens(START)
        self.clob.books = [book(up, asks=[("0.6", "5")], timestamp=str(round((self.clock - 0.9) * 1000))),
                           book(down, asks=[("0.4", "5")], timestamp=str(round((self.clock - 0.4) * 1000)))]
        self.assertAlmostEqual(self.clock - 0.9, self.quotes.quote()["observedAt"], places=3)

    def test_warm_keeps_books_fresh_in_the_entry_window_so_the_read_needs_no_upstream_call(self):
        real_thread = threading.Thread

        class InlineThread:
            def __init__(self, target, args, daemon):
                self.target, self.args = target, args

            def start(self):
                self.target(*self.args)

        threading.Thread = InlineThread
        self.addCleanup(setattr, threading, "Thread", real_thread)
        self.clock = START + 30
        self.quotes.warm()
        self.assertEqual([f"{GAMMA}?slug=btc-updown-5m-{START}"], self.clob.urls(), "no book refresh before +55 s")
        self.clock = START + 56
        self.assertTrue(self.quotes.warm())
        self.assertEqual(2, len(self.clob.calls))
        self.clock = START + 56.6
        self.assertAlmostEqual(START + 56, self.quotes.quote()["observedAt"], places=3)
        self.assertEqual(2, len(self.clob.calls), "served from the refreshed snapshot")
        self.clock = START + 80
        self.assertFalse(self.quotes.warm(), "no refresh after the entry window")

    def test_the_ask_is_the_level_completing_a_1_dollar_buy_and_the_bid_is_the_max(self):
        quote = self.quotes.quote()
        up, down = round_tokens(START)
        self.assertEqual(MARKET_QUOTE_FIELDS, set(quote))
        # Up: 0.57 x 1 share is only $0.57, so $1 completes on the 0.60 level. Down: 0.45 x 3 = $1.35.
        self.assertEqual({"schemaVersion": 1, "source": "polymarket_clob_book", "periodStart": START,
                          "slug": f"btc-updown-5m-{START}", "upAskCents": 60, "downAskCents": 45,
                          "upBidCents": 55, "downBidCents": 43, "observedAt": self.clock,
                          "serverTime": self.clock}, quote)
        self.assertEqual([(f"{GAMMA}?slug=btc-updown-5m-{START}", None),
                          (CLOB_BOOKS, [{"token_id": up}, {"token_id": down}])], self.clob.calls)
        json.dumps(quote, allow_nan=False)

    def test_zero_size_levels_are_ignored_and_an_empty_side_is_null(self):
        up, down = round_tokens(START)
        self.clob.books = [book(up, asks=[("0.5", "0"), ("0.7", "3"), (0.65, 0)], bids=[("0.6", "0"), (0.3, 2.5)]),
                           book(down, asks=[("0.4", "0")], bids=[])]
        quote = self.quotes.quote()
        self.assertEqual((70, 30, None, None), (quote["upAskCents"], quote["upBidCents"],
                                                quote["downAskCents"], quote["downBidCents"]))

    def test_mismatched_or_malformed_books_raise_and_leave_no_snapshot(self):
        up, down = round_tokens(START)
        good = lambda token: book(token, asks=[("0.6", "1")], bids=[("0.4", "1")])
        cases = [{}, None, "[]", [], [good(up)], [good(up), good(down), good(down)], [good(up), good(up)],
                 [good(up), good("999")], [good(up), "book"], [good(up), {**good(down), "asks": None}],
                 [good(up), {**good(down), "bids": {"price": "0.4", "size": "1"}}],
                 [good(up), {**good(down), "asks": ["0.6"]}], [good(up), {**good(down), "asks": [{"price": "0.6"}]}]]
        cases += [[good(up), book(down, asks=[(price, "1")])]
                  for price in ("0", "1", "1.2", "-0.1", "nan", "inf", "abc", "", None, True, [0.5], 0, 1)]
        cases += [[good(up), book(down, bids=[("0.4", size)])] for size in ("-1", "nan", "inf", None, True, -0.5)]
        for books in cases:
            with self.subTest(books=books):
                self.clob.books = books
                with self.assertRaises(ValueError):
                    self.quotes.quote()
                self.assertIsNone(self.quotes.snapshot)
        for stamps in (["abc", None], [str(round((self.clock + 1.5) * 1000))] * 2, [True, True]):
            with self.subTest(stamps=stamps):
                self.clob.books = [book(up, asks=[("0.6", "2")], timestamp=stamps[0]),
                                   book(down, asks=[("0.4", "3")], timestamp=stamps[1] or "x")]
                with self.assertRaises(ValueError):
                    self.quotes.quote()
                self.assertIsNone(self.quotes.snapshot)
        self.clob.books = DEFAULT_BOOKS
        self.assertEqual(60, self.quotes.quote()["upAskCents"])

    def test_gamma_market_is_validated_before_any_book_read(self):
        def not_accepting(start):
            events = round_market(start)
            events[0]["markets"][0]["acceptingOrders"] = False
            return events

        for events, reason in [(not_accepting, "WRONG_OR_INACTIVE_MARKET"),
                               (lambda start: round_market(start + 300), "WRONG_OR_INACTIVE_EVENT"),
                               (lambda start: [], "MARKET_NOT_UNIQUE")]:
            with self.subTest(reason=reason):
                self.clob.calls.clear()
                self.clob.events = events
                with self.assertRaisesRegex(ValueError, reason):
                    self.quotes.quote()
                self.assertNotIn(CLOB_BOOKS, self.clob.urls())
                self.assertIsNone(self.quotes.tokens)

    def test_tokens_are_cached_for_the_round_and_snapshot_reuse_keeps_observed_at(self):
        first = self.quotes.quote()
        observed = self.clock
        self.clock += 0.5
        second = self.quotes.quote()
        self.assertEqual(2, len(self.clob.calls), "a snapshot within ttl needs no upstream read")
        self.assertEqual((observed, self.clock), (second["observedAt"], second["serverTime"]))
        self.assertEqual({**first, "serverTime": self.clock}, second)
        self.clock += 0.5
        third = self.quotes.quote()
        self.assertEqual([f"{GAMMA}?slug=btc-updown-5m-{START}", CLOB_BOOKS, CLOB_BOOKS], self.clob.urls(),
                         "an expired snapshot rereads books but not the round's tokens")
        self.assertEqual((self.clock, self.clock), (third["observedAt"], third["serverTime"]))

    def test_a_new_round_reads_gamma_and_books_again_even_within_ttl(self):
        self.clock = START + 299.9
        self.assertEqual(START, self.quotes.quote()["periodStart"])
        self.clock = START + 300.1
        quote = self.quotes.quote()
        up, down = round_tokens(START + 300)
        self.assertEqual((START + 300, f"btc-updown-5m-{START + 300}"), (quote["periodStart"], quote["slug"]))
        self.assertAlmostEqual(self.clock, quote["observedAt"], places=3)
        self.assertEqual([(f"{GAMMA}?slug=btc-updown-5m-{START + 300}", None),
                          (CLOB_BOOKS, [{"token_id": up}, {"token_id": down}])], self.clob.calls[2:])
        self.assertEqual(("5m", START + 300), self.quotes.tokens[0])

    def test_a_read_that_crosses_the_round_boundary_fails(self):
        self.clock = START + 299.8

        def slow(url, body=None):
            result = self.clob(url, body)
            if body is not None:
                self.clock = START + 300.2
            return result

        quotes = ClobMarketQuotes(slow, lambda: self.clock)
        with self.assertRaisesRegex(ValueError, "ROUND_CHANGED_DURING_READ"):
            quotes.quote()
        self.assertIsNone(quotes.snapshot)

    def test_upstream_failures_propagate_and_are_never_served_from_a_stale_cache(self):
        def failing(url, body=None):
            self.clob.calls.append((url, body))
            raise RuntimeError("HTTP_SOURCE_UNAVAILABLE")

        quotes = ClobMarketQuotes(failing, lambda: self.clock)
        for _ in range(2):
            with self.assertRaises(RuntimeError):
                quotes.quote()
        self.assertEqual([f"{GAMMA}?slug=btc-updown-5m-{START}"] * 2, self.clob.urls())
        self.assertIsNone(quotes.tokens)
        self.quotes.quote()
        self.clock += 1
        self.quotes.fetch_json = failing
        with self.assertRaises(RuntimeError):
            self.quotes.quote()


class CurlJsonTest(unittest.TestCase):
    def test_fast_connection_reset_retries_once_with_the_remaining_read_budget(self):
        failed = Mock(returncode=35, stdout=b"", stderr=b"private proxy detail")
        good = Mock(returncode=0, stdout=b'{"ok":true}')
        with patch("future_btc5m_assistant.time.monotonic", side_effect=[100, 100.25]), \
                patch("future_btc5m_assistant.subprocess.run", side_effect=[failed, good]) as run:
            self.assertEqual({"ok": True}, curl_json(GAMMA))
        self.assertEqual(2, run.call_count)
        retry = run.call_args.args[0]
        self.assertNotIn("--http1.1", run.call_args_list[0].args[0])
        self.assertIn("--http1.1", retry, "retry the supported protocol that passed the live TLS handshake probe")
        self.assertEqual("3.75", retry[retry.index("--max-time") + 1])
        self.assertEqual(4.75, run.call_args.kwargs["timeout"])

    def test_reset_budget_exhaustion_never_starts_a_second_request(self):
        with patch("future_btc5m_assistant.time.monotonic", side_effect=[100, 104]), \
                patch("future_btc5m_assistant.subprocess.run", return_value=Mock(returncode=56, stdout=b"")) as run:
            with self.assertRaisesRegex(RuntimeError, "^HTTP_SOURCE_TIMEOUT$"):
                curl_json(GAMMA)
        self.assertEqual(1, run.call_count)

    def test_repeated_resets_are_bounded_and_http_or_certificate_denials_are_not_retried(self):
        for code, calls, reason in [(56, 2, "HTTP_SOURCE_CONNECTION_RESET"),
                                    (22, 1, "HTTP_SOURCE_UNAVAILABLE"), (60, 1, "HTTP_SOURCE_TLS_ERROR")]:
            with self.subTest(code=code), patch("future_btc5m_assistant.subprocess.run",
                                               return_value=Mock(returncode=code, stdout=b"")) as run:
                with self.assertRaisesRegex(RuntimeError, "^" + reason + "$"):
                    curl_json(GAMMA)
                self.assertEqual(calls, run.call_count)

    def test_async_observation_uses_the_same_bounded_transport_with_its_six_second_budget(self):
        with patch("future_btc5m_assistant.curl_json", return_value={"ok": True}) as read:
            self.assertEqual({"ok": True}, asyncio.run(future_btc5m_assistant.get_json(GAMMA)))
        read.assert_called_once_with(GAMMA, timeout=6)

    def test_quote_transport_allows_measured_three_second_source_latency(self):
        with patch("future_btc5m_assistant.subprocess.run", return_value=Mock(returncode=0, stdout=b'[]')) as run:
            curl_json(CLOB_BOOKS, [{"token_id": "1"}, {"token_id": "2"}])
        command = run.call_args.args[0]
        self.assertEqual("4", command[command.index("--max-time") + 1])
        self.assertEqual(5, run.call_args.kwargs["timeout"])

    def test_source_timeouts_have_a_specific_safe_reason(self):
        cases = [Mock(returncode=28, stdout=b""),
                 subprocess.TimeoutExpired(["curl"], 5, stderr="private proxy error")]
        for result in cases:
            with self.subTest(result=result):
                kwargs = {"side_effect": result} if isinstance(result, Exception) else {"return_value": result}
                with patch("future_btc5m_assistant.subprocess.run", **kwargs):
                    with self.assertRaisesRegex(RuntimeError, "^HTTP_SOURCE_TIMEOUT$"):
                        curl_json(CLOB_BOOKS)

    def test_get_and_post_keep_tls_and_inherited_proxy_with_bounded_time(self):
        completed = Mock(returncode=0, stdout=b'[{"ok": 1}]')
        gamma = f"{GAMMA}?slug=btc-updown-5m-{START}"
        with patch("future_btc5m_assistant.subprocess.run", return_value=completed) as run:
            self.assertEqual([{"ok": 1}], curl_json(gamma))
            self.assertEqual([{"ok": 1}], curl_json(CLOB_BOOKS, [{"token_id": "1"}, {"token_id": "2"}]))
        (get, get_kwargs), (post, post_kwargs) = ((call.args[0], call.kwargs) for call in run.call_args_list)
        for command, kwargs in ((get, get_kwargs), (post, post_kwargs)):
            self.assertEqual("curl", command[0])
            self.assertEqual(5, kwargs["timeout"])
            self.assertEqual("4", command[command.index("--max-time") + 1])
            self.assertIn("--fail", command)
            self.assertIn("Accept: application/json", command)
            for flag in ("-k", "--insecure", "-x", "--proxy", "--noproxy"):
                self.assertNotIn(flag, command)
            self.assertFalse({"env", "shell"} & set(kwargs))
        self.assertEqual(["--url", gamma], get[-2:])
        self.assertNotIn("--data-binary", get)
        self.assertEqual(["--url", CLOB_BOOKS], post[-2:])
        self.assertIn("Content-Type: application/json", post)
        self.assertEqual('[{"token_id":"1"},{"token_id":"2"}]', post[post.index("--data-binary") + 1])
        with patch("future_btc5m_assistant.subprocess.run", return_value=Mock(returncode=22, stdout=b"")):
            with self.assertRaisesRegex(RuntimeError, "HTTP_SOURCE_UNAVAILABLE"):
                curl_json(gamma)


if __name__ == "__main__":
    unittest.main()
