import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).parent))

from jev_shadow_monitor import collect_snapshot, save_snapshot, select_markets


NOW = datetime(2026, 9, 24, 0, 0, tzinfo=timezone.utc)


def market(question, slug, tokens):
    return {
        "question": question,
        "slug": slug,
        "conditionId": "0xabc",
        "description": "Resolves Yes if the event occurs.",
        "active": True,
        "closed": False,
        "acceptingOrders": True,
        "outcomes": '["Yes", "No"]',
        "clobTokenIds": json.dumps(tokens),
        "feesEnabled": True,
        "feeSchedule": {"rate": 0.05, "exponent": 1},
        "volume24hr": 1000,
    }


class JevShadowMonitorTest(unittest.TestCase):
    def test_select_markets_limits_scope_and_requires_yes_no(self):
        btc = market("Will Bitcoin reach $90,000?", "btc-market", ["yes", "no"])
        political = market("Will the election change?", "political-market", ["p-yes", "p-no"])
        finance = market("Will the Fed cut interest rates?", "fed-market", ["f-yes", "f-no"])
        crypto_finance = market("Will Bitcoin ETF inflows rise?", "btc-etf", ["c-yes", "c-no"])
        crypto_politics = market("Will Congress pass a crypto bill?", "crypto-bill", ["cp-yes", "cp-no"])
        sports = market("Will the Lakers win?", "sports-market", ["s-yes", "s-no"])
        up_down = {**btc, "slug": "up-down", "outcomes": '["Up", "Down"]'}

        self.assertEqual([political, finance], select_markets([
            btc, political, finance, crypto_finance, crypto_politics, sports, up_down,
        ]))

    def test_collect_snapshot_uses_fresh_depth_and_fees(self):
        btc = market("Will the Fed cut interest rates?", "fed-market", ["yes", "no"])
        book = {
            "timestamp": str(int(NOW.timestamp() * 1000)),
            "min_order_size": "5",
            "asks": [{"price": "0.40", "size": "20"}],
        }

        def fake_http(url):
            return [btc] if "/markets?" in url else book

        snapshot = collect_snapshot(NOW, pages=1, http_fn=fake_http, quote_now_fn=lambda: NOW)

        self.assertEqual(5, snapshot["schema_version"])
        self.assertEqual("politics_finance_ex_crypto", snapshot["market_scope"])
        self.assertEqual(1, snapshot["eligible_markets"])
        self.assertEqual(1, snapshot["fresh_pairs"])
        self.assertEqual(1, snapshot["positive_pairs"])
        self.assertEqual(Decimal("0.176000"), snapshot["rows"][0]["pair_edge_per_share"])
        self.assertEqual(Decimal("0.40"), snapshot["rows"][0]["quotes"]["Yes"]["vwap"])
        self.assertTrue(snapshot["paper_only"])

    def test_stale_book_is_recorded_as_a_gap_not_an_edge(self):
        btc = market("Will the Fed cut interest rates?", "fed-market", ["yes", "no"])

        def fake_http(url):
            if "/markets?" in url:
                return [btc]
            return {
                "timestamp": str(int(NOW.timestamp() * 1000) - 60000),
                "min_order_size": "5",
                "asks": [{"price": "0.40", "size": "20"}],
            }

        snapshot = collect_snapshot(NOW, pages=1, http_fn=fake_http, quote_now_fn=lambda: NOW)

        self.assertEqual(0, snapshot["fresh_pairs"])
        self.assertEqual(0, snapshot["positive_pairs"])
        self.assertEqual("stale or future order book", snapshot["skipped"]["fed-market"])

    def test_later_book_uses_its_fetch_time_not_batch_start(self):
        btc = market("Will the Fed cut interest rates?", "fed-market", ["yes", "no"])
        quote_time = NOW + timedelta(seconds=20)

        def fake_http(url):
            if "/markets?" in url:
                return [btc]
            return {
                "timestamp": str(int(quote_time.timestamp() * 1000)),
                "min_order_size": "5",
                "asks": [{"price": "0.40", "size": "20"}],
            }

        snapshot = collect_snapshot(NOW, pages=1, http_fn=fake_http, quote_now_fn=lambda: quote_time)

        self.assertEqual(1, snapshot["fresh_pairs"])

    def test_transient_book_connection_reset_is_retried(self):
        btc = market("Will the Fed cut interest rates?", "fed-market", ["yes", "no"])
        calls = {"book": 0}

        def fake_http(url):
            if "/markets?" in url:
                return [btc]
            calls["book"] += 1
            if calls["book"] == 1:
                raise ConnectionResetError("connection reset by peer")
            return {
                "timestamp": str(int(NOW.timestamp() * 1000)),
                "min_order_size": "5",
                "asks": [{"price": "0.40", "size": "20"}],
            }

        snapshot = collect_snapshot(NOW, pages=1, http_fn=fake_http, quote_now_fn=lambda: NOW)

        self.assertEqual(1, snapshot["fresh_pairs"])
        self.assertEqual(3, calls["book"])

    def test_save_snapshot_deduplicates_six_hour_window(self):
        snapshot = {"observed_at": NOW.isoformat(), "window_start": "2026-09-24T00:00:00+00:00", "schema_version": 4}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            self.assertTrue(save_snapshot(path, snapshot))
            self.assertFalse(save_snapshot(path, snapshot))
            self.assertEqual(1, len(path.read_text(encoding="utf-8").splitlines()))

    def test_corrected_snapshot_preserves_earlier_version(self):
        old = {"window_start": "2026-09-24T00:00:00+00:00", "schema_version": 4}
        corrected = {**old, "schema_version": 5}
        with TemporaryDirectory() as directory:
            path = Path(directory) / "observations.jsonl"
            self.assertTrue(save_snapshot(path, old))
            self.assertTrue(save_snapshot(path, corrected))
            self.assertEqual(2, len(path.read_text(encoding="utf-8").splitlines()))


if __name__ == "__main__":
    unittest.main()
