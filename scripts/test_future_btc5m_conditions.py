import math
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from future_btc5m_assistant import RoundConditions
from future_btc5m_conditions import VOLATILITY_MAX_BP, kline_url, round_conditions


S = 1791705600  # a 15m boundary


def candles(start=S, drop=None, closes_at=None, overrides=None):
    """The 62 Binance 1m rows opening at start - 3600 .. start + 60: price rises 1 per minute from
    80000, each candle closes 2 above its open on odd minutes and 1 below on even minutes."""
    rows = []
    for i in range(62):
        opened = start - 3600 + 60 * i
        if opened == drop:
            continue
        open_ = 80000.0 + i
        close = open_ + (2 if i % 2 else -1)
        row = [opened * 1000, str(open_), str(open_ + 3), str(open_ - 3), str(close), "10.0",
               (opened + 60) * 1000 - 1, "0", 100, "6.0", "0", "0"]
        rows.append((overrides or {}).get(opened, row))
    if closes_at is not None:
        rows[-1][6] = closes_at
    return rows


class ConditionsTest(unittest.TestCase):
    def test_values_follow_the_backtest_formulas(self):
        value = round_conditions(S, candles(), S + 121)
        returns = [math.log((80000 + i + (2 if i % 2 else -1)) / (80000 + i)) for i in range(2, 62)]
        mean = sum(returns) / 60
        expected = math.sqrt(sum((r - mean) ** 2 for r in returns) / 59) * 1e4
        self.assertAlmostEqual(expected, value["volatilityBp"], places=9)
        self.assertAlmostEqual(math.log(80060 / 80045) * 1e4, value["trend15Bp"], places=9)
        self.assertAlmostEqual(math.log(80060 / 80000) * 1e4, value["trend60Bp"], places=9)
        self.assertAlmostEqual(0.2, value["takerFlow"], places=9)
        self.assertEqual(("binance_btcusdt_1m", S, S + 60, S + 121, VOLATILITY_MAX_BP),
                         (value["source"], value["periodStart"], value["lastCandleOpen"], value["observedAt"],
                          value["volatilityMaxBp"]))
        self.assertEqual(4.16, VOLATILITY_MAX_BP)

    def test_missing_unclosed_or_invalid_candles_are_rejected(self):
        for rows, error, label in [
            (candles(drop=S - 1800), "KLINES_INCOMPLETE", "gap"),
            (candles(drop=S + 60), "KLINES_INCOMPLETE", "last candle missing"),
            (candles(closes_at=(S + 121) * 1000), "KLINES_INCOMPLETE", "last candle not closed yet"),
            (candles(overrides={S: [S * 1000, "0", "1", "0", "1", "1", 0, "0", 1, "1"]}), "INVALID_KLINE", "zero open"),
            (candles(overrides={S: [S * 1000, "nan", "1", "0", "1", "1", 0, "0", 1, "1"]}), "INVALID_KLINE", "nan"),
            (candles() + [[S * 1000, "1", "1", "1", "1"]], "INVALID_KLINE", "short row"),
            ([row[:5] + ["0"] + row[6:] if int(row[0]) >= (S - 780) * 1000 else row for row in candles()],
             "INVALID_KLINE", "no volume"),
        ]:
            with self.subTest(label), self.assertRaisesRegex(ValueError, error):
                round_conditions(S, rows, S + 121)

    def test_the_url_requests_exactly_the_62_closed_candles(self):
        self.assertEqual("https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1m"
                         f"&startTime={(S - 3600) * 1000}&endTime={(S + 60) * 1000}&limit=62", kline_url(S))


class RoundConditionsTest(unittest.TestCase):
    def wait(self, conditions):
        for _ in range(200):
            if not conditions.busy:
                return
            time.sleep(0.005)

    def test_fetched_once_after_second_121_and_retried_until_the_window_ends(self):
        clock, calls, fail = [S + 120], [], [True]

        def fetch(url):
            calls.append(url)
            if fail[0]:
                raise OSError("down")
            return candles()

        conditions = RoundConditions(fetch, lambda: clock[0])
        self.assertFalse(conditions.warm(), "the start + 60 candle has not closed")
        clock[0] = S + 121
        self.assertTrue(conditions.warm())
        self.wait(conditions)
        self.assertEqual(("CONDITIONS_SOURCE_UNAVAILABLE", None), (conditions.error, conditions.latest()))
        self.assertFalse(conditions.warm(), "one attempt per 5 s")
        clock[0] = S + 126
        fail[0] = False
        self.assertTrue(conditions.warm())
        self.wait(conditions)
        self.assertEqual(S, conditions.latest()["periodStart"])
        clock[0] = S + 131
        self.assertFalse(conditions.warm(), "fetched once per round")
        self.assertEqual([kline_url(S)] * 2, calls)
        clock[0] = S + 900
        self.assertIsNone(conditions.latest(), "only for its own round")
        clock[0] = S + 900 + 170
        self.assertFalse(conditions.warm(), "never after the entry window")


if __name__ == "__main__":
    unittest.main()
