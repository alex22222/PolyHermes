import asyncio
import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent))

from future_btc5m_assistant import Assistant, ClobMarketQuotes, CLOB_BOOKS, GAMMA, iso, validate_hourly_market
from future_btc5m_bridge import FutureBridge, PreparationConflict
from future_btc5m_series import (hourly_slug, market_url_round, preparation_id, series_of_preparation_id,
                                 series_of_slug)


S = 1791705600  # a 15m and 1h boundary
assert S % 3600 == 0


def signal15(at, current=83001):
    return {"id": f"15m:{S}", "slug": f"btc-updown-15m-{S}", "series": "15m", "period_start": S,
            "period_end": S + 900, "side": "Up" if current > 83000 else "Down", "open_price": 83000,
            "current_price": current, "open_price_source": "polymarket_crypto_price_fifteen_twap60_openPrice",
            "twap_lookback_seconds": 60, "price_source": "chainlink", "price_observed_at": at}


def hour_quote(at, up=40, down=61, start=S):
    return {"schemaVersion": 1, "source": "polymarket_clob_book", "periodStart": start, "slug": hourly_slug(start),
            "upAskCents": up, "downAskCents": down, "upBidCents": None, "downBidCents": None, "observedAt": at}


def source15(at, hour=True, **hour_changes):
    return {"schema_version": 1, "mode": "ASSIST_ONLY", "live_enabled": False, "amount_usd": 1,
            "server_time": at, "period_start": S, "round_series": "15m", "series": "15m",
            "status": "OBSERVING", "feed_status": "CURRENT", "future_eligibility": {"status": "UNKNOWN"},
            "signal": signal15(at), "hour_quote": hour_quote(at, **hour_changes) if hour else None}


def browser15(at, **changes):
    return {"schemaVersion": 2, "marketUrl": f"https://future.news/zh/event/btc-updown-15m-{S}",
            "pagePeriodStart": S, "checkedAt": at, "navigation": "CURRENT", "ticketStatus": "PASS",
            "amountUsd": None, "selectedSide": "Down", "buyButtonEnabled": False,
            "upQuoteCents": 66, "downQuoteCents": 35, **changes}


class SeriesTest(unittest.TestCase):
    def test_slugs_ids_and_market_urls_name_their_series_and_period(self):
        self.assertEqual(("15m", S), series_of_slug(f"btc-updown-15m-{S}"))
        self.assertEqual(("5m", S + 300), series_of_slug(f"btc-updown-5m-{S + 300}"))
        self.assertIsNone(series_of_slug(f"btc-updown-15m-{S + 300}"), "not a 15m boundary")
        self.assertEqual(f"future-btc15m-prepare:{S}", preparation_id(S, "15m"))
        self.assertEqual(("15m", S), series_of_preparation_id(f"future-btc15m-prepare:{S}"))
        self.assertIsNone(series_of_preparation_id(f"future-btc15m-prepare:0{S}"))
        self.assertEqual(("15m", S), market_url_round(f"https://future.news/zh/event/btc-updown-15m-{S}/"))
        for url in (f"https://future.news/zh/event/btc-updown-15m-{S}?x=1", f"http://future.news/event/btc-updown-15m-{S}",
                    f"https://future.news.evil/event/btc-updown-15m-{S}", f"https://future.news/event/btc-updown-1h-{S}"):
            self.assertIsNone(market_url_round(url), url)

    def test_hourly_slug_follows_polymarket_et_naming(self):
        noon = int(datetime(2026, 10, 15, 16, tzinfo=timezone.utc).timestamp())
        self.assertEqual("bitcoin-up-or-down-october-15-2026-12pm-et", hourly_slug(noon))
        self.assertEqual("bitcoin-up-or-down-october-16-2026-12am-et", hourly_slug(noon + 12 * 3600))
        self.assertEqual("bitcoin-up-or-down-october-15-2026-8pm-et", hourly_slug(noon + 8 * 3600))
        self.assertEqual("bitcoin-up-or-down-october-15-2026-9am-et", hourly_slug(noon - 3 * 3600))


class FifteenMinuteBridgeTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.clock = S + 140
        self.source = source15(S + 140)
        self.bridge = FutureBridge(self.dir, lambda: self.source, lambda: self.clock)
        self.bridge.set_strategy("btc15m_counter_1h")
        self.bridge.control(True)

    def at(self, t, report=True, **source_changes):
        self.clock = S + t
        self.source = source15(S + t, **source_changes)
        if report:
            self.bridge.report_preflight(browser15(S + t))
        return self.bridge.observe()

    def decisions(self):
        path = self.dir / "strategy_decisions.jsonl"
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_strategy_is_persisted_validated_and_reported(self):
        status = self.bridge.status()
        self.assertEqual(("btc15m_counter_1h", "15m"), (status["strategy"], status["series"]))
        self.assertEqual("btc15m_counter_1h", json.loads((self.dir / "control.json").read_text())["strategy"])
        with self.assertRaises(ValueError):
            self.bridge.set_strategy("btc1h")
        restarted = FutureBridge(self.dir, lambda: self.source, lambda: self.clock)
        self.assertEqual("btc15m_counter_1h", restarted.strategy)
        self.assertFalse(restarted.requested_enabled, "a restart never resumes trading")
        self.bridge.set_strategy("btc5m_favorite")
        self.assertEqual("5m", FutureBridge(self.dir, lambda: self.source, lambda: self.clock).series)

    def test_nothing_happens_before_the_150s_entry(self):
        status = self.at(120)
        self.assertEqual({}, self.bridge.preparations)
        self.assertEqual("WAITING_SIGNAL", status["preparation"]["state"])

    def test_15m_favorite_against_the_1h_favorite_is_prepared_once(self):
        status = self.at(151)
        record = self.bridge.preparations[f"future-btc15m-prepare:{S}"]
        self.assertEqual(("PENDING", "Up", S + 900, S + 170, f"btc-updown-15m-{S}"),
                         (record["state"], record["side"], record["periodEnd"], record["expiresAt"], record["slug"]))
        self.assertEqual("polymarket_crypto_price_fifteen_twap60_openPrice", record["openPriceSource"])
        self.assertEqual("PENDING", status["preparation"]["state"])
        [decision] = self.decisions()
        self.assertEqual(("PREPARE", "Up", "Down", 40, 61), (decision["decision"], decision["buttonSide"],
                         decision["hourSide"], decision["hourUpAskCents"], decision["hourDownAskCents"]))
        self.at(152, up=61, down=40)
        self.assertEqual(1, len(self.decisions()), "one decision per round")

    def test_same_direction_as_the_1h_favorite_skips_the_round_for_good(self):
        status = self.at(151, up=70, down=31)
        self.assertEqual({}, self.bridge.preparations)
        self.assertEqual(["SAME_AS_1H_FAVORITE"], status["preparation"]["reasons"])
        self.assertEqual("SKIP_SAME_AS_1H", self.decisions()[0]["decision"])
        status = self.at(155, up=30, down=71)
        self.assertEqual({}, self.bridge.preparations, "a later flip in the window does not reopen the round")
        restarted = FutureBridge(self.dir, lambda: self.source, lambda: self.clock)
        self.assertEqual("SKIP_SAME_AS_1H", restarted.decisions[("15m", S)])

    def test_a_missing_stale_tied_or_wrong_hour_quote_never_decides(self):
        for changes, label in [({"hour": False}, "missing"), ({"up": 50, "down": 50}, "tied"),
                               ({"start": S - 3600}, "previous hour")]:
            with self.subTest(label):
                status = self.at(151, **changes)
                self.assertEqual(["HOUR_QUOTE_UNAVAILABLE"], status["preparation"]["reasons"])
        self.clock = S + 151
        self.source = {**source15(S + 151), "hour_quote": hour_quote(S + 145)}
        self.bridge.report_preflight(browser15(S + 151))
        self.assertEqual(["HOUR_QUOTE_UNAVAILABLE"], self.bridge.observe()["preparation"]["reasons"], "stale")
        self.assertEqual([], self.decisions())
        self.assertEqual({}, self.bridge.preparations)

    def test_a_5m_page_or_a_5m_signal_is_not_current_for_the_15m_strategy(self):
        self.clock = S + 151
        self.source = source15(S + 151)
        self.bridge.report_preflight({**browser15(S + 151), "marketUrl": f"https://future.news/zh/event/btc-updown-5m-{S}",
                                      "pagePeriodStart": S})
        self.assertEqual(["MARKET_NOT_CURRENT"], self.bridge.observe()["preparation"]["reasons"])
        self.source = {**source15(S + 151), "round_series": "5m"}
        self.bridge.report_preflight(browser15(S + 151))
        self.assertEqual(["WAITING_CURRENT_SIGNAL"], self.bridge.observe()["preparation"]["reasons"])
        self.assertEqual({}, self.bridge.preparations)

    def test_claim_ready_and_buy_audit_complete_on_the_15m_round(self):
        self.at(151)
        id = f"future-btc15m-prepare:{S}"
        claimed = self.bridge.claim_preparation({"schemaVersion": 1, "id": id})
        token = claimed["preparation"]["lastAttempt"]["claimToken"]
        self.clock = S + 153
        self.source = source15(S + 153)
        self.bridge.report_preflight(browser15(S + 153, amountUsd=1, selectedSide="Up", buyButtonEnabled=True))
        url = f"https://future.news/zh/event/btc-updown-15m-{S}"
        ready = self.bridge.report_preparation({"schemaVersion": 1, "id": id, "claimToken": token, "checkedAt": S + 153,
                                                "status": "READY", "marketUrl": url, "amountUsd": 1,
                                                "selectedSide": "Up", "reason": None, "noSubmission": True})
        self.assertEqual("READY", ready["preparation"]["state"])
        self.assertEqual(("btc15m_counter_1h", "15m"), (ready["preparation"]["strategy"], ready["preparation"]["series"]))
        audit = {"schemaVersion": 2, "auditId": f"{id}:{(S + 154) * 1000}", "id": id, "claimToken": token,
                 "periodStart": S, "side": "Up", "amountUsd": 1, "state": "CLICK_ATTEMPTED",
                 "reason": "PLATFORM_RESULT_UNKNOWN", "armedAt": S + 100, "attemptedAt": S + 154, "marketUrl": url,
                 "upQuoteCents": 66, "downQuoteCents": 35, "selectedSide": "Up", "ticketAmountUsd": 1,
                 "extensionVersion": "0.7.0", "marketUpAskCents": 66, "marketDownAskCents": 35,
                 "marketQuoteObservedAt": S + 153.5}
        self.assertTrue(self.bridge.report_buy_attempt(audit)["stored"])
        with self.assertRaises(ValueError):
            self.bridge.report_buy_attempt({**audit, "auditId": f"{id}:{(S + 155) * 1000}", "attemptedAt": S + 155,
                                            "marketUrl": f"https://future.news/zh/event/btc-updown-5m-{S}"})
        restarted = FutureBridge(self.dir, lambda: self.source, lambda: self.clock)
        self.assertEqual("READY", restarted.preparations[id]["state"], "15m ledger lines reload")

    def test_switching_strategy_revokes_an_unfinished_ticket_and_hides_the_old_round(self):
        self.at(151)
        status = self.bridge.set_strategy("btc5m_favorite")
        self.assertEqual("REVOKED", self.bridge.preparations[f"future-btc15m-prepare:{S}"]["state"])
        self.assertEqual("5m", status["series"])
        self.assertNotEqual("PENDING", status["preparation"]["state"])
        with self.assertRaises(PreparationConflict):
            self.bridge.claim_preparation({"schemaVersion": 1, "id": f"future-btc15m-prepare:{S}"})


def gamma15(start):
    slug = f"btc-updown-15m-{start}"
    return [{"slug": slug, "active": True, "closed": False, "endDate": iso(start + 900), "markets": [{
        "slug": slug, "active": True, "closed": False, "acceptingOrders": True, "endDate": iso(start + 900),
        "eventStartTime": iso(start), "conditionId": "0xabc",
        "cryptoMarketConfig": {"asset": "btc", "duration": "15m", "twapEnabled": True, "twapLookbackSeconds": 60},
        "outcomes": '["Up", "Down"]', "clobTokenIds": '["151", "152"]'}]}]


def gamma1h(start):
    slug = hourly_slug(start)
    return [{"slug": slug, "active": True, "closed": False, "markets": [{
        "slug": slug, "active": True, "closed": False, "acceptingOrders": True, "endDate": iso(start + 3600),
        "eventStartTime": iso(start), "conditionId": "0xdef", "outcomes": '["Up", "Down"]',
        "clobTokenIds": '["601", "602"]'}]}]


class FifteenMinuteAssistantTest(unittest.TestCase):
    def test_15m_series_polls_its_own_market_window_and_open_price(self):
        with TemporaryDirectory() as directory:
            clock = [S + 151]
            calls = []
            assistant = Assistant(Path(directory), lambda: {"price": 83001, "observed_at": clock[0], "received_at": clock[0]},
                                  lambda: clock[0])
            assistant.boot_time = S - 1
            assistant.weekend_only = False
            assistant.series_fn = lambda: "15m"

            async def http(url):
                calls.append(url)
                if url.startswith(GAMMA):
                    return gamma15(S)
                if "crypto-price" in url:
                    return {"openPrice": 83000}
                return {"blocked": False}

            status = asyncio.run(assistant.poll(http))
            self.assertEqual(f"{GAMMA}?slug=btc-updown-15m-{S}", calls[0])
            self.assertIn("variant=fifteen", calls[1])
            self.assertIn(f"endDate={iso(S + 900)}".replace(":", "%3A"), calls[1])
            self.assertEqual(signal15(S + 151)["slug"], status["signal"]["slug"])
            self.assertEqual(("15m", S + 900, "polymarket_crypto_price_fifteen_twap60_openPrice"),
                             (status["signal"]["series"], status["signal"]["period_end"], status["signal"]["open_price_source"]))
            self.assertEqual(("15m", S), (status["round_series"], status["period_start"]))
            claims = [json.loads(line) for line in (Path(directory) / "rounds.jsonl").read_text().splitlines()]
            self.assertEqual([{"period_start": S, "series": "15m"}], [{k: c[k] for k in ("period_start", "series")} for c in claims])
            # The same start as a 5m round is a different round.
            assistant.series_fn = lambda: "5m"
            clock[0] = S + 61
            self.assertNotEqual("ROUND_ALREADY_PROCESSED", asyncio.run(assistant.poll(http))["reason"])

    def test_15m_and_1h_books_use_their_own_markets(self):
        clock = [S + 151]

        def fetch(url, body=None):
            if url.startswith(GAMMA):
                return gamma15(S) if "btc-updown-15m" in url else gamma1h(S)
            self.assertEqual(CLOB_BOOKS, url)
            stamp = str(round(clock[0] * 1000))
            if body[0]["token_id"] == "601":
                return [{"asset_id": "601", "timestamp": stamp, "asks": [{"price": "0.40", "size": "10"}], "bids": []},
                        {"asset_id": "602", "timestamp": stamp, "asks": [{"price": "0.61", "size": "10"}], "bids": []}]
            return [{"asset_id": "151", "timestamp": stamp, "asks": [{"price": "0.66", "size": "10"}], "bids": []},
                    {"asset_id": "152", "timestamp": stamp, "asks": [{"price": "0.35", "size": "10"}], "bids": []}]

        fifteen = ClobMarketQuotes(fetch, lambda: clock[0], series_fn=lambda: "15m").quote()
        self.assertEqual((S, f"btc-updown-15m-{S}", 66, 35),
                         (fifteen["periodStart"], fifteen["slug"], fifteen["upAskCents"], fifteen["downAskCents"]))
        hours = ClobMarketQuotes(fetch, lambda: clock[0], series_fn=lambda: "1h")
        hour = hours.quote()
        self.assertEqual((S, hourly_slug(S), 40, 61), (hour["periodStart"], hour["slug"], hour["upAskCents"], hour["downAskCents"]))
        self.assertEqual(61, hours.latest(5)["downAskCents"])
        clock[0] += 6
        self.assertIsNone(hours.latest(5), "a book older than 5 s is not offered to the bridge")

    def test_hourly_market_validation_is_strict(self):
        self.assertEqual({"Up": "601", "Down": "602"}, validate_hourly_market(gamma1h(S), S)["tokens"])
        for mutate in (lambda e: e[0].update(slug="x"), lambda e: e[0]["markets"][0].update(acceptingOrders=False),
                       lambda e: e[0]["markets"][0].update(endDate=iso(S + 900)),
                       lambda e: e[0]["markets"][0].update(clobTokenIds='["601", "601"]')):
            events = gamma1h(S)
            mutate(events)
            with self.assertRaises(ValueError):
                validate_hourly_market(events, S)


if __name__ == "__main__":
    unittest.main()
