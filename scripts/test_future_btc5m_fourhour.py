import asyncio
import json
import math
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent))

from future_btc5m_assistant import Assistant, ClobMarketQuotes, FourHourModel, GAMMA, iso, validate_market
from future_btc5m_bridge import FutureBridge, PreparationConflict
from future_btc5m_fourhour import MODEL, evaluate, kline_urls, model_state, up_probability
from test_future_btc5m_strategy import conditions15
from future_btc5m_series import (CHECKPOINT_MINUTES, STRATEGY_SERIES, checkpoint_window, entry_bounds,
                                 market_url_round, series_of_preparation_id)


S4 = 1792252800  # Saturday 2026-10-17 12:00 ET: a 4h, 1h and 15m boundary
WEEKDAY = S4 - 4 * 86400  # Tuesday
assert S4 % 14400 == 0 and WEEKDAY % 14400 == 0
T5 = S4 + 300  # the minute-5 checkpoint


def model(at, p_up=0.99, checkpoint=T5, start=S4):
    return {"source": "binance_btcusdt_1m", "periodStart": start, "checkpointAt": checkpoint,
            "minute": (checkpoint - start) // 60, "openPrice": 80000.0, "price": 80600.0, "sigma": 0.0005,
            "z": 3.0, "pUp": p_up, "observedAt": at}


def quote4(at, up=90, down=11, start=S4):
    return {"schemaVersion": 1, "source": "polymarket_clob_book", "periodStart": start, "slug": f"btc-updown-4h-{start}",
            "upAskCents": up, "downAskCents": down, "upBidCents": None, "downBidCents": None, "observedAt": at}


def signal4(at, start=S4, current=80600):
    return {"id": f"4h:{start}", "slug": f"btc-updown-4h-{start}", "series": "4h", "period_start": start,
            "period_end": start + 14400, "side": "Up" if current > 80000 else "Down", "open_price": 80000,
            "current_price": current, "open_price_source": "polymarket_crypto_price_fourhour_twap60_openPrice",
            "twap_lookback_seconds": 60, "price_source": "chainlink", "price_observed_at": at}


def source(at, series="15m", start=S4, four=True, p_up=0.99, up=90, down=11, checkpoint=T5):
    """The assistant status: polling `series`, with the 4h checkpoint inputs when `four`."""
    period = {"15m": 900, "4h": 14400}[series]
    round_start = int(at // period) * period
    value = {"schema_version": 1, "mode": "ASSIST_ONLY", "live_enabled": False, "amount_usd": 1,
             "server_time": at, "period_start": round_start, "round_series": series, "series": series,
             "status": "OBSERVING", "feed_status": "CURRENT", "future_eligibility": {"status": "UNKNOWN"},
             "signal": signal4(at, start) if series == "4h" else None, "hour_quote": None,
             "four_hour": model(at, p_up, checkpoint, start) if four else None,
             "four_hour_quote": quote4(at, up, down, start) if four else None}
    return value


def browser4(at, start=S4, **changes):
    return {"schemaVersion": 2, "marketUrl": f"https://future.news/zh/event/btc-updown-4h-{start}",
            "pagePeriodStart": start, "checkedAt": at, "navigation": "CURRENT", "ticketStatus": "PASS",
            "amountUsd": None, "selectedSide": "Down", "buyButtonEnabled": False,
            "upQuoteCents": 91, "downQuoteCents": 10, **changes}


class CheckpointTest(unittest.TestCase):
    def test_checkpoints_avoid_minute_0_of_every_quarter_and_open_two_minute_windows(self):
        self.assertEqual(32, len(CHECKPOINT_MINUTES))
        self.assertTrue(all(minute % 15 in (5, 10) for minute in CHECKPOINT_MINUTES))
        self.assertEqual((S4 + 300, S4 + 420), checkpoint_window(S4, S4 + 300))
        self.assertEqual((S4 + 300, S4 + 420), checkpoint_window(S4, S4 + 419.9))
        self.assertEqual((S4 + 14100, S4 + 14220), checkpoint_window(S4, S4 + 14150), "minute 235")
        for at in (S4, S4 + 299, S4 + 420, S4 + 900, S4 + 1000, S4 + 1950, S4 + 14400 - 1):
            self.assertIsNone(checkpoint_window(S4, at), at - S4)
        # The 15m entry window (+150..170 s of each quarter) never falls in a 4h window.
        for quarter in range(16):
            for second in range(150, 171):
                self.assertIsNone(checkpoint_window(S4, S4 + quarter * 900 + second))
        self.assertEqual((S4 + 300, S4 + 420), entry_bounds(S4, "4h", S4 + 301))
        self.assertIsNone(entry_bounds(S4, "4h"))
        self.assertEqual((S4 + 150, S4 + 170), entry_bounds(S4, "15m", S4 + 301), "static series ignore the time")

    def test_4h_urls_ids_and_strategy_series(self):
        self.assertEqual(("4h", S4), market_url_round(f"https://future.news/zh/event/btc-updown-4h-{S4}"))
        self.assertIsNone(market_url_round(f"https://future.news/zh/event/btc-updown-4h-{S4 + 900}"))
        self.assertEqual(("4h", S4), series_of_preparation_id(f"future-btc4h-prepare:{S4}"))
        self.assertEqual(("15m", "4h"), STRATEGY_SERIES["btc15m_plus_4h"])


def klines(start, checkpoint, path):
    """Consecutive 1m klines from 61 minutes before the round to the checkpoint; path(i) is the close
    of the candle opening at start + 60 * i."""
    rows = []
    for i in range(-61, (checkpoint - start) // 60):
        open_ = path(i - 1)
        rows.append([(start + 60 * i) * 1000, str(open_), str(open_), str(open_), str(path(i))])
    return rows


class ModelTest(unittest.TestCase):
    def test_model_matches_the_backtest_formula(self):
        closes = [80000 * math.exp(0.0003 * math.sin(i)) for i in range(61)]
        p, z, sigma = up_probability(79900, closes, 100)
        returns = [math.log(closes[i] / closes[i - 1]) for i in range(1, 61)]
        mean = sum(returns) / 60
        expected_sigma = math.sqrt(sum((r - mean) ** 2 for r in returns) / 59)
        expected_z = math.log(closes[-1] / 79900) / (expected_sigma * math.sqrt(100))
        a, b = MODEL[3][1], MODEL[3][2]  # 60-120 minutes left
        self.assertAlmostEqual(expected_sigma, sigma)
        self.assertAlmostEqual(expected_z, z)
        self.assertAlmostEqual(1 / (1 + math.exp(-(a + b * expected_z))), p)
        # Bucket edges: 15 minutes left still uses the (0,15] coefficients.
        self.assertAlmostEqual(1 / (1 + math.exp(-(MODEL[0][1] + MODEL[0][2] * up_probability(79900, closes, 15)[1]))),
                               up_probability(79900, closes, 15)[0])

    def test_model_state_reads_the_round_open_and_the_61_closes_before_the_checkpoint(self):
        checkpoint = S4 + 125 * 60
        self.assertIn(125, CHECKPOINT_MINUTES)
        path = lambda i: 80000 + 3 * i + (7 if i % 2 else 0)
        rows = klines(S4, checkpoint, path)
        state = model_state(S4, checkpoint, rows)
        self.assertEqual((125, float(path(-1)), float(path(124))), (state["minute"], state["openPrice"], state["price"]))
        closes = [float(path(i)) for i in range(124 - 60, 125)]
        self.assertAlmostEqual(up_probability(path(-1), closes, 115)[0], state["pUp"])
        with self.assertRaises(ValueError):
            model_state(S4, checkpoint, [row for row in rows if row[0] != (checkpoint - 600) * 1000])
        with self.assertRaises(ValueError):
            model_state(S4, S4 + 120 * 60, rows)  # minute 120 is not a checkpoint
        first, window = kline_urls(S4, checkpoint)
        self.assertIn(f"startTime={S4 * 1000}&limit=1", first)
        self.assertIn(f"endTime={(checkpoint - 1) * 1000}&limit=61", window)

    def test_the_rule_needs_a_weekend_95pct_model_side_favorite_in_range_and_3c_edge(self):
        m = model(T5, 0.99)
        self.assertEqual(("PREPARE", "Up", None), evaluate(S4, m, quote4(T5, 90, 11)))
        self.assertEqual(("PREPARE", "Down", None), evaluate(S4, model(T5, 0.02), quote4(T5, 8, 94)))
        self.assertEqual("PREPARE", evaluate(S4, m, quote4(T5, 96, 5))[0], "exactly 3c of edge qualifies")
        cases = [(WEEKDAY, m, quote4(T5, 90, 11), "NOT_ET_WEEKEND"),
                 (S4, model(T5, 0.94), quote4(T5, 80, 21), "MODEL_BELOW_THRESHOLD"),
                 (S4, m, quote4(T5, 97, 5), "EDGE_TOO_SMALL"),
                 (S4, m, quote4(T5, 40, 61), "MODEL_SIDE_NOT_FAVORITE"),
                 (S4, m, quote4(T5, None, 11), "ASK_UNAVAILABLE"),
                 (S4, model(T5, 0.999), quote4(T5, 98, 3), "ASK_OUT_OF_RANGE")]
        for start, value, book, reason in cases:
            with self.subTest(reason):
                self.assertEqual(("SKIP", reason), (evaluate(start, value, book)[0], evaluate(start, value, book)[2]))


class CombinedBridgeTest(unittest.TestCase):
    def setUp(self):
        directory = TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.dir = Path(directory.name)
        self.clock = S4 + 200
        self.source = source(S4 + 200)
        self.bridge = FutureBridge(self.dir, lambda: self.source, lambda: self.clock)
        self.bridge.set_strategy("btc15m_plus_4h")
        self.bridge.control(True)

    def tick(self, t, **changes):
        self.clock = S4 + t
        self.source = source(S4 + t, **changes)
        return self.bridge.observe()

    def lines(self, name):
        path = self.dir / name
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def decide(self):
        status = self.tick(301)
        self.assertEqual("4h", status["series"])
        return status

    def test_combined_strategy_reports_both_series_and_stays_on_15m_by_default(self):
        status = self.tick(200)
        self.assertEqual(("btc15m_plus_4h", "15m", ["15m", "4h"]),
                         (status["strategy"], status["series"], status["strategySeries"]))
        self.assertEqual("15m", json.loads((self.dir / "control.json").read_text())["series"])
        self.assertEqual({"periodStart": S4, "weekend": True, "decision": None, "lastEvaluation": None}, status["fourHour"])

    def test_a_qualifying_checkpoint_hands_the_next_two_minutes_to_the_4h_page(self):
        status = self.decide()
        [decision] = self.lines("strategy_decisions.jsonl")
        self.assertEqual(("4h", S4, T5, 5, "Up", "PREPARE", 90, 11),
                         (decision["series"], decision["periodStart"], decision["checkpointAt"], decision["minute"],
                          decision["side"], decision["decision"], decision["upAskCents"], decision["downAskCents"]))
        self.assertEqual({"checkpointAt": T5, "side": "Up"}, status["fourHour"]["decision"])
        self.assertEqual(1, len(self.lines("four_hour_evaluations.jsonl")))
        self.assertEqual("4h", self.tick(419)["series"])
        self.assertEqual("15m", self.tick(420)["series"], "the window closes after 2 minutes")
        self.assertEqual("15m", self.tick(601)["series"], "one PREPARE per round")
        self.assertEqual(1, len(self.lines("four_hour_evaluations.jsonl")), "no later evaluation in the round")

    def test_the_4h_ticket_is_prepared_claimed_readied_and_audited_inside_the_window(self):
        self.decide()
        self.clock = S4 + 305
        self.source = source(S4 + 305, series="4h")
        self.bridge.report_preflight(browser4(S4 + 305))
        status = self.bridge.observe()
        id = f"future-btc4h-prepare:{S4}"
        record = self.bridge.preparations[id]
        self.assertEqual(("PENDING", "Up", S4 + 14400, S4 + 420, f"btc-updown-4h-{S4}", "polymarket_crypto_price_fourhour_twap60_openPrice"),
                         (record["state"], record["side"], record["periodEnd"], record["expiresAt"], record["slug"],
                          record["openPriceSource"]))
        self.assertEqual(("PENDING", "4h"), (status["preparation"]["state"], status["preparation"]["series"]))
        claimed = self.bridge.claim_preparation({"schemaVersion": 1, "id": id})
        token = claimed["preparation"]["lastAttempt"]["claimToken"]
        self.clock = S4 + 307
        self.source = source(S4 + 307, series="4h")
        self.bridge.report_preflight(browser4(S4 + 307, amountUsd=1, selectedSide="Up", buyButtonEnabled=True))
        url = f"https://future.news/zh/event/btc-updown-4h-{S4}"
        ready = self.bridge.report_preparation({"schemaVersion": 1, "id": id, "claimToken": token, "checkedAt": S4 + 307,
                                                "status": "READY", "marketUrl": url, "amountUsd": 1,
                                                "selectedSide": "Up", "reason": None, "noSubmission": True})
        self.assertEqual(("READY", "btc15m_plus_4h", "4h"), (ready["preparation"]["state"], ready["preparation"]["strategy"],
                                                            ready["preparation"]["series"]))
        audit = {"schemaVersion": 2, "auditId": f"{id}:{(S4 + 308) * 1000}", "id": id, "claimToken": token,
                 "periodStart": S4, "side": "Up", "amountUsd": 1, "state": "CLICK_ATTEMPTED",
                 "reason": "PLATFORM_RESULT_UNKNOWN", "armedAt": S4 + 100, "attemptedAt": S4 + 308, "marketUrl": url,
                 "upQuoteCents": 91, "downQuoteCents": 10, "selectedSide": "Up", "ticketAmountUsd": 1,
                 "extensionVersion": "0.8.0", "marketUpAskCents": 91, "marketDownAskCents": 10,
                 "marketQuoteObservedAt": S4 + 307.5}
        self.assertTrue(self.bridge.report_buy_attempt(audit)["stored"])
        restarted = FutureBridge(self.dir, lambda: self.source, lambda: self.clock)
        self.assertEqual("READY", restarted.preparations[id]["state"], "4h ledger lines reload and validate")
        self.assertEqual((T5, "Up"), restarted.four_hour[S4])
        # After the window the 4h record is history and the 15m page is current again.
        status = self.tick(421)
        self.assertEqual(("15m", id), (status["preparation"]["series"], status["preparation"]["lastAttempt"]["id"]))
        self.assertNotEqual("READY", status["preparation"]["state"])

    def test_a_4h_page_favoring_the_other_side_is_not_prepared(self):
        self.decide()
        self.clock = S4 + 305
        self.source = source(S4 + 305, series="4h")
        self.bridge.report_preflight(browser4(S4 + 305, upQuoteCents=40, downQuoteCents=61))
        self.assertEqual(["FOUR_HOUR_SIDE_MISMATCH"], self.bridge.observe()["preparation"]["reasons"])
        self.assertEqual({}, self.bridge.preparations)

    def test_a_15m_page_is_not_current_during_the_4h_window(self):
        self.decide()
        self.clock = S4 + 305
        self.source = source(S4 + 305, series="4h")
        self.bridge.report_preflight({**browser4(S4 + 305), "marketUrl": f"https://future.news/zh/event/btc-updown-15m-{S4}"})
        self.assertEqual(["MARKET_NOT_CURRENT"], self.bridge.observe()["preparation"]["reasons"])

    def test_below_threshold_is_logged_and_a_later_checkpoint_may_still_decide(self):
        status = self.tick(301, p_up=0.9)
        self.assertEqual("15m", status["series"])
        self.assertEqual([], self.lines("strategy_decisions.jsonl"))
        [skip] = self.lines("four_hour_evaluations.jsonl")
        self.assertEqual(("SKIP", "MODEL_BELOW_THRESHOLD"), (skip["decision"], skip["reason"]))
        self.assertEqual(skip, status["fourHour"]["lastEvaluation"])
        self.tick(305, p_up=0.99)
        self.assertEqual(1, len(self.lines("four_hour_evaluations.jsonl")), "one evaluation per checkpoint")
        status = self.tick(601, checkpoint=S4 + 600)
        self.assertEqual(("4h", S4 + 600), (status["series"], status["fourHour"]["decision"]["checkpointAt"]))

    def test_late_stale_weekday_disabled_or_single_strategy_checkpoints_never_decide(self):
        self.tick(331)  # 30 s after the checkpoint
        self.clock = S4 + 302
        for label, changes in [("stale book", {"four_hour_quote": quote4(S4 + 295)}),
                               ("model before the checkpoint", {"four_hour": model(S4 + 299)}),
                               ("another checkpoint", {"four_hour": {**model(S4 + 302), "checkpointAt": S4 + 600}}),
                               ("another round's book", {"four_hour_quote": quote4(S4 + 302, start=S4 - 14400)})]:
            self.source = {**source(S4 + 302), **changes}
            self.bridge.observe()
            self.assertEqual([], self.lines("four_hour_evaluations.jsonl"), label)
        self.assertEqual([], self.lines("four_hour_evaluations.jsonl"))
        self.bridge.control(False)
        self.tick(302)
        self.bridge.control(True)
        self.bridge.set_strategy("btc15m_counter_1h")
        self.tick(303)
        self.assertEqual([], self.lines("four_hour_evaluations.jsonl"))
        self.assertIsNone(self.bridge.status()["fourHour"])
        self.bridge.set_strategy("btc15m_plus_4h")
        self.clock = WEEKDAY + 301
        self.source = source(WEEKDAY + 301, start=WEEKDAY, checkpoint=WEEKDAY + 300)
        status = self.bridge.observe()
        self.assertEqual(("15m", False), (status["series"], status["fourHour"]["weekend"]))
        self.assertEqual([], self.lines("four_hour_evaluations.jsonl"))

    def test_a_restart_inside_the_window_keeps_the_4h_page_current(self):
        self.decide()
        restarted = FutureBridge(self.dir, lambda: self.source, lambda: self.clock)
        self.assertEqual("4h", restarted.series)
        self.clock = S4 + 421
        self.assertEqual("15m", restarted.series)

    def test_the_15m_entry_still_runs_under_the_combined_strategy(self):
        self.decide()
        self.clock = S4 + 900 + 151
        hour = {"schemaVersion": 1, "source": "polymarket_clob_book", "periodStart": S4, "slug": "x",
                "upAskCents": 40, "downAskCents": 61, "upBidCents": None, "downBidCents": None, "observedAt": self.clock}
        self.source = {**source(self.clock, four=False), "hour_quote": hour, "round_conditions": conditions15(start=S4 + 900),
                       "signal": {"id": f"15m:{S4 + 900}", "slug": f"btc-updown-15m-{S4 + 900}", "series": "15m",
                                  "period_start": S4 + 900, "period_end": S4 + 1800, "side": "Up", "open_price": 83000,
                                  "current_price": 83001, "open_price_source": "polymarket_crypto_price_fifteen_twap60_openPrice",
                                  "twap_lookback_seconds": 60, "price_source": "chainlink", "price_observed_at": self.clock}}
        self.bridge.report_preflight({"schemaVersion": 2, "marketUrl": f"https://future.news/zh/event/btc-updown-15m-{S4 + 900}",
                                      "pagePeriodStart": S4 + 900, "checkedAt": self.clock, "navigation": "CURRENT",
                                      "ticketStatus": "PASS", "amountUsd": None, "selectedSide": "Down",
                                      "buyButtonEnabled": False, "upQuoteCents": 66, "downQuoteCents": 35})
        self.bridge.observe()
        self.assertEqual("PENDING", self.bridge.preparations[f"future-btc15m-prepare:{S4 + 900}"]["state"])
        with self.assertRaises(PreparationConflict):
            self.bridge.claim_preparation({"schemaVersion": 1, "id": f"future-btc4h-prepare:{S4}"})


def gamma4(start):
    slug = f"btc-updown-4h-{start}"
    return [{"slug": slug, "active": True, "closed": False, "endDate": iso(start + 14400), "markets": [{
        "slug": slug, "active": True, "closed": False, "acceptingOrders": True, "endDate": iso(start + 14400),
        "eventStartTime": iso(start), "conditionId": "0x4h",
        "cryptoMarketConfig": {"id": "btc-4h-twap-60", "asset": "btc", "duration": "4h", "twapEnabled": True,
                               "twapLookbackSeconds": 60},
        "outcomes": '["Up", "Down"]', "clobTokenIds": '["401", "402"]'}]}]


class FourHourAssistantTest(unittest.TestCase):
    def test_4h_market_validates_and_its_book_is_read(self):
        self.assertEqual({"Up": "401", "Down": "402"}, validate_market(gamma4(S4), S4, "4h")["tokens"])
        clock = [S4 + 301]

        def fetch(url, body=None):
            if url.startswith(GAMMA):
                return gamma4(S4)
            stamp = str(round(clock[0] * 1000))
            return [{"asset_id": "401", "timestamp": stamp, "asks": [{"price": "0.90", "size": "10"}], "bids": []},
                    {"asset_id": "402", "timestamp": stamp, "asks": [{"price": "0.11", "size": "10"}], "bids": []}]

        book = ClobMarketQuotes(fetch, lambda: clock[0], series_fn=lambda: "4h")
        self.assertEqual((S4, 90, 11), (book.quote()["periodStart"], book.quote()["upAskCents"], book.quote()["downAskCents"]))
        self.assertTrue(book.warm(), "inside a checkpoint window the default warm refreshes the book")
        clock[0] = S4 + 200
        self.assertFalse(book.warm(), "tokens cached; outside a window the default warm does not refresh")

    def test_model_is_computed_once_per_weekend_checkpoint_inside_its_window(self):
        clock = [S4 + 302]
        path = lambda i: 80000 + 10 * i
        rows = klines(S4, T5, path)
        calls = []

        def fetch(url):
            calls.append(url)
            return rows

        four = FourHourModel(fetch, lambda: clock[0])
        self.assertTrue(four.warm())
        for _ in range(100):
            if not four.busy:
                break
            asyncio.run(asyncio.sleep(0.01))
        state = four.latest()
        self.assertEqual((S4, T5, 5), (state["periodStart"], state["checkpointAt"], state["minute"]))
        self.assertEqual(2, len(calls))
        self.assertFalse(four.warm(), "computed once")
        clock[0] = S4 + 421
        self.assertIsNone(four.latest(), "only inside the window")
        clock[0] = WEEKDAY + 302
        self.assertFalse(FourHourModel(fetch, lambda: clock[0]).warm(), "weekend only")

    def test_4h_poll_claims_only_inside_a_checkpoint_window_with_the_fourhour_open_price(self):
        with TemporaryDirectory() as directory:
            clock = [S4 + 200]
            calls = []
            assistant = Assistant(Path(directory), lambda: {"price": 80600, "observed_at": clock[0], "received_at": clock[0]},
                                  lambda: clock[0])
            assistant.boot_time = S4 - 1
            assistant.series_fn = lambda: "4h"

            async def http(url):
                calls.append(url)
                if url.startswith(GAMMA):
                    return gamma4(S4)
                if "crypto-price" in url:
                    return {"openPrice": 80000}
                return {"blocked": False}

            status = asyncio.run(assistant.poll(http))
            self.assertEqual(("WAITING", "OUTSIDE_CHECKPOINT_WINDOW", S4, "4h"),
                             (status["status"], status["reason"], status["period_start"], status["round_series"]))
            self.assertEqual([], calls)
            clock[0] = S4 + 302
            status = asyncio.run(assistant.poll(http))
            self.assertIn("variant=fourhour", calls[1])
            self.assertEqual((f"btc-updown-4h-{S4}", "Up", "polymarket_crypto_price_fourhour_twap60_openPrice"),
                             (status["signal"]["slug"], status["signal"]["side"], status["signal"]["open_price_source"]))
            self.assertEqual(S4 + 420, status["draft"]["expires_at"] if status["draft"] else S4 + 420)
            claims = [json.loads(line) for line in (Path(directory) / "rounds.jsonl").read_text().splitlines()]
            self.assertEqual([("4h", S4)], [(claim["series"], claim["period_start"]) for claim in claims])


if __name__ == "__main__":
    unittest.main()
