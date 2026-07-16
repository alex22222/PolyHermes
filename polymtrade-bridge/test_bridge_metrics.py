import json
import tempfile
import unittest
from pathlib import Path

from bridge_metrics import BridgeMetrics


class TestBridgeMetrics(unittest.TestCase):
    def test_latency_summary_reports_p50_and_p95(self):
        metrics = BridgeMetrics()
        for value in range(1, 101):
            metrics.observe_latency("buy_5m_signal_to_submit_ms", value)

        summary = metrics.to_dict()["latency_ms"]["buy_5m_signal_to_submit_ms"]

        self.assertEqual(100, summary["count"])
        self.assertEqual(50.5, summary["p50"])
        self.assertEqual(95.05, summary["p95"])

    def test_event_writer_persists_latency_without_caller_file_io(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bridge-performance.jsonl"
            metrics = BridgeMetrics(performance_event_log=str(path))

            metrics.start_event_writer()
            metrics.observe_latency(
                "webhook_accept_ms",
                12.5,
                side="BUY",
                market_window="5m",
            )
            metrics.stop_event_writer()

            event = json.loads(path.read_text(encoding="utf-8").strip())
            self.assertEqual("webhook_accept_ms", event["metric"])
            self.assertEqual(12.5, event["duration_ms"])
            self.assertEqual("BUY", event["side"])
            self.assertEqual("5m", event["market_window"])


if __name__ == "__main__":
    unittest.main()
