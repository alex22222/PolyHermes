import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from future_btc5m_paper_regime import MIN_TREND60_BP, record, resolve, summary


S = 1791705600  # a 15m boundary


def kline(start, open_, close):
    return [start * 1000, str(open_), str(max(open_, close)), str(min(open_, close)), str(close), "10.0",
            (start + 900) * 1000 - 1, "0", 100, "6.0", "0", "0"]


class PaperRegimeTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.state = Path(self.dir.name)

    def tearDown(self):
        self.dir.cleanup()

    def add(self, start, side="Up", price=64.0, trend60=20.0, now=1000.0):
        record(self.state, period_start=start, side=side, price_cents=price,
               trend60_bp=trend60, volatility_bp=3.0, now=now)

    def test_record_is_idempotent_per_round(self):
        self.add(S)
        self.add(S, trend60=-30.0)
        rows = [json.loads(line) for line in (self.state / "paper_regime.jsonl").open()]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["trend60Bp"], 20.0)
        self.assertTrue(rows[0]["g1Eligible"])
        self.assertEqual(rows[0]["state"], "PENDING")

    def test_g1_threshold(self):
        self.add(S, trend60=MIN_TREND60_BP - 0.01)
        rows = [json.loads(line) for line in (self.state / "paper_regime.jsonl").open()]
        self.assertFalse(rows[0]["g1Eligible"])
        self.add(S + 900, trend60=-MIN_TREND60_BP)
        rows = [json.loads(line) for line in (self.state / "paper_regime.jsonl").open()]
        self.assertTrue(rows[1]["g1Eligible"])

    def test_resolve_waits_for_round_end(self):
        self.add(S)
        fetch = lambda url: [kline(S, 100.0, 101.0)]
        self.assertEqual(resolve(self.state, fetch, S + 900 + 59), 0)
        self.assertEqual(resolve(self.state, fetch, S + 900 + 60), 1)
        rows = [json.loads(line) for line in (self.state / "paper_regime.jsonl").open()]
        self.assertEqual(rows[0]["state"], "RESOLVED")
        self.assertEqual(rows[0]["outcome"], "Up")
        self.assertTrue(rows[0]["win"])
        self.assertAlmostEqual(rows[0]["roi"], (100 - 64.0) / 64.0)

    def test_resolve_loss_and_flat(self):
        self.add(S, side="Up", price=70.0)          # Down round -> loss
        self.add(S + 900, side="Down", price=60.0)  # flat round -> excluded from settled stats
        fetch = lambda url: [kline(S, 100.0, 99.0), kline(S + 900, 100.0, 100.0)]
        self.assertEqual(resolve(self.state, fetch, S + 2 * 900 + 60), 2)
        result = summary(self.state, S + 2 * 900 + 60)
        self.assertEqual(result["baseline"]["trades"], 2)
        self.assertEqual(result["baseline"]["settled"], 1)
        self.assertEqual(result["baseline"]["wins"], 0)
        self.assertAlmostEqual(result["baseline"]["totalUsd"], -1.0)

    def test_summary_splits_baseline_and_filtered(self):
        self.add(S, trend60=20.0)        # eligible, wins
        self.add(S + 900, trend60=5.0)   # not eligible, loses
        fetch = lambda url: [kline(S, 100.0, 101.0), kline(S + 900, 100.0, 99.0)]
        resolve(self.state, fetch, S + 2 * 900 + 60)
        result = summary(self.state, S + 2 * 900 + 60)
        self.assertEqual(result["rule"], "G1 |trend60|>=15bp")
        self.assertEqual(result["baseline"]["settled"], 2)
        self.assertEqual(result["baseline"]["wins"], 1)
        self.assertEqual(result["filtered"]["settled"], 1)
        self.assertEqual(result["filtered"]["wins"], 1)
        self.assertEqual(len(result["recent"]), 2)
        self.assertEqual(result["recent"][0]["periodStart"], S + 900)

    def test_summary_empty_without_ledger(self):
        self.assertIsNone(summary(self.state, 0))


if __name__ == "__main__":
    unittest.main()
