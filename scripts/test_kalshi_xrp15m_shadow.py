import math
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from kalshi_xrp15m_shadow import (
    FiveMinuteSample,
    align_five_minute_samples,
    candle_probability,
    evaluate_probabilities,
    validate_chronologically,
)


class KalshiXrp15mShadowTest(unittest.TestCase):
    def test_candle_probability_prefers_executable_midpoint(self):
        candle = {
            "yes_bid": {"close_dollars": "0.3000"},
            "yes_ask": {"close_dollars": "0.5000"},
            "price": {"close_dollars": "0.9000"},
        }

        self.assertEqual(0.4, candle_probability(candle))

    def test_alignment_uses_only_quotes_visible_at_decision_time(self):
        markets = [{"ticker": "K-1800", "close_ts": 1800}]
        candles = {
            "K-1800": [
                {"end_period_ts": 1140, "price": {"close_dollars": "0.30"}},
                {"end_period_ts": 1200, "price": {"close_dollars": "0.40"}},
                {"end_period_ts": 1205, "price": {"close_dollars": "0.95"}},
                {"end_period_ts": 1440, "price": {"close_dollars": "0.60"}},
                {"end_period_ts": 1500, "price": {"close_dollars": "0.70"}},
                {"end_period_ts": 1505, "price": {"close_dollars": "0.05"}},
            ]
        }
        polymarket = {
            1200: {"outcome": 0, "observed_ts": 1204, "probability": 0.55},
            1500: {"outcome": 1, "observed_ts": 1504, "probability": 0.60},
        }

        samples = align_five_minute_samples(markets, candles, polymarket)

        self.assertEqual([1200, 1500], [sample.window_start for sample in samples])
        self.assertEqual([0.4, 0.7], [sample.kalshi_probability for sample in samples])
        self.assertAlmostEqual(0.1, samples[0].kalshi_delta)
        self.assertAlmostEqual(0.1, samples[1].kalshi_delta)
        self.assertTrue(all(sample.quote_ts <= sample.observed_ts for sample in samples))

    def test_alignment_skips_first_segment_and_missing_prior_quote(self):
        markets = [{"ticker": "K-1800", "close_ts": 1800}]
        candles = {
            "K-1800": [
                {"end_period_ts": 1205, "price": {"close_dollars": "0.60"}},
                {"end_period_ts": 1505, "price": {"close_dollars": "0.70"}},
            ]
        }
        polymarket = {
            900: {"outcome": 1, "observed_ts": 904, "probability": 0.50},
            1200: {"outcome": 1, "observed_ts": 1204, "probability": 0.50},
            1500: {"outcome": 1, "observed_ts": 1504, "probability": 0.50},
        }

        samples = align_five_minute_samples(markets, candles, polymarket)

        self.assertEqual([], samples)

    def test_probability_metrics_are_behavioral(self):
        metrics = evaluate_probabilities([0.8, 0.2, 0.6, 0.4], [1, 0, 1, 0])

        self.assertEqual(1.0, metrics["accuracy"])
        self.assertAlmostEqual(0.1, metrics["brier"], places=9)
        self.assertTrue(math.isfinite(metrics["log_loss"]))

    def test_segment_control_is_present_in_both_models(self):
        samples = []
        for index in range(80):
            segment = 2 if index % 2 == 0 else 3
            samples.append(
                FiveMinuteSample(
                    window_start=index * 300,
                    observed_ts=index * 300 + 4,
                    quote_ts=index * 300,
                    segment=segment,
                    outcome=0 if segment == 2 else 1,
                    polymarket_probability=0.5,
                    kalshi_probability=0.2 if index % 4 < 2 else 0.8,
                    kalshi_delta=0.0,
                    kalshi_ticker=f"K-{index}",
                    polymarket_slug=f"P-{index}",
                )
            )

        result = validate_chronologically(samples)

        self.assertAlmostEqual(0.0, result["brier_improvement"], places=4)


if __name__ == "__main__":
    unittest.main()
