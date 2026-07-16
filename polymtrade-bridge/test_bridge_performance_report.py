import unittest

from bridge_performance_report import (
    build_report,
    code_fingerprint_window_start,
    evaluate_latency,
    filter_performance_events,
    metric_counts,
    summarize_execution_records,
)


class TestBridgePerformanceReport(unittest.TestCase):
    def test_latency_is_pending_until_sample_floor_then_passes(self):
        events = [
            {"metric": "buy_5m_signal_to_submit_ms", "duration_ms": 8000}
            for _ in range(20)
        ]

        result = evaluate_latency(
            events,
            "buy_5m_signal_to_submit_ms",
            min_samples=20,
            p50_max_ms=10000,
            p95_max_ms=20000,
        )

        self.assertEqual("pass", result["status"])
        self.assertEqual(8000, result["p95_ms"])

    def test_report_stays_pending_before_seven_day_health_window(self):
        now = 1_000_000
        report = build_report([], [{"timestamp": now - 86400, "event": "service_start"}], now)

        self.assertEqual("pending", report["status"])
        self.assertEqual("pending", report["checks"]["health_stability"]["status"])

    def test_latency_outlier_before_sample_floor_is_pending_with_warning(self):
        result = evaluate_latency(
            [{"metric": "webhook_accept_ms", "duration_ms": 475.0}],
            "webhook_accept_ms",
            min_samples=100,
            p50_max_ms=100,
            p95_max_ms=200,
        )

        self.assertEqual("pending", result["status"])
        self.assertTrue(result["would_fail_current_sample"])

    def test_health_window_restarts_after_threshold_restart(self):
        events = [
            {"timestamp": 1000, "event": "service_start"},
            {"timestamp": 2000, "event": "restart_threshold"},
            {"timestamp": 3000, "event": "service_start"},
            {"timestamp": 3600, "event": "health_ok"},
        ]

        report = build_report([], events, 3000 + 86400)
        health = report["checks"]["health_stability"]

        self.assertEqual("pending", health["status"])
        self.assertEqual(3000, health["observation_start"])
        self.assertEqual(0, health["threshold_restarts"])
        self.assertEqual(1, health["historical_threshold_restarts"])

    def test_report_can_filter_performance_events_by_since_ms(self):
        events = [
            {"timestamp_ms": 1000, "metric": "buy_5m_signal_to_submit_ms", "duration_ms": 40000},
            {"timestamp_ms": 2000, "metric": "buy_5m_signal_to_submit_ms", "duration_ms": 8000},
            {"timestamp_ms": 2000, "metric": "webhook_accept_ms", "duration_ms": 1},
        ]

        filtered = filter_performance_events(events, since_ms=2000)
        report = build_report(
            events,
            [{"timestamp": 1, "event": "service_start"}],
            2,
            since_ms=2000,
        )

        self.assertEqual(events[1:], filtered)
        self.assertEqual(3, report["sample_window"]["performance_events_total"])
        self.assertEqual(2, report["sample_window"]["performance_events_evaluated"])
        self.assertEqual(
            {"buy_5m_signal_to_submit_ms": 1, "webhook_accept_ms": 1},
            report["sample_window"]["metric_counts"],
        )
        self.assertEqual(8000, report["checks"]["buy_5m"]["p50_ms"])

    def test_metric_counts_ignores_events_without_metric(self):
        self.assertEqual(
            {"webhook_accept_ms": 2},
            metric_counts([
                {"metric": "webhook_accept_ms"},
                {"metric": "webhook_accept_ms"},
                {"duration_ms": 1},
            ]),
        )

    def test_code_fingerprint_window_uses_latest_contiguous_code_load(self):
        health_events = [
            {"timestamp": 1000, "event": "service_start", "code_fingerprint": "old"},
            {"timestamp": 2000, "event": "service_start", "code_fingerprint": "new"},
            {"timestamp": 3000, "event": "service_start", "code_fingerprint": "new"},
        ]

        self.assertEqual(2000, code_fingerprint_window_start(health_events))
        self.assertEqual(1000, code_fingerprint_window_start(health_events, "old"))
        self.assertIsNone(code_fingerprint_window_start(health_events, "missing"))

    def test_report_can_explain_missing_submit_samples_from_execution_records(self):
        records = [
            {
                "created_at": 2000,
                "market_slug": "btc-updown-15m-1784184300",
                "side": "BUY",
                "status": "FAILED",
                "error_message": "price 0.70 > max_price 0.55000000",
            },
            {
                "created_at": 2000,
                "market_slug": "xrp-updown-5m-1784184300",
                "side": "SELL",
                "status": "FAILED",
                "error_message": "Insufficient position, skipped",
            },
        ]

        report = build_report(
            [],
            [{"timestamp": 1, "event": "service_start"}],
            2,
            since_ms=2000,
            execution_records=records,
        )
        summary = report["sample_window"]["execution_records"]

        self.assertEqual(2, summary["count"])
        self.assertIn(
            {"keys": ["BUY", "FAILED"], "count": 1},
            summary["status_counts"],
        )
        self.assertIn(
            {"keys": ["15m", "BUY", "FAILED"], "count": 1},
            summary["market_window_counts"],
        )
        self.assertIn(
            {
                "keys": [
                    "SELL",
                    "FAILED",
                    "Insufficient position, skipped",
                ],
                "count": 1,
            },
            summary["reason_counts"],
        )

    def test_execution_summary_respects_since_window(self):
        summary = summarize_execution_records(
            [
                {"created_at": 1000, "side": "BUY", "status": "SUCCESS"},
                {"created_at": 2000, "side": "SELL", "status": "FAILED"},
            ],
            since_ms=2000,
        )

        self.assertEqual(1, summary["count"])
        self.assertEqual(
            [{"keys": ["SELL", "FAILED"], "count": 1}],
            summary["status_counts"],
        )


if __name__ == "__main__":
    unittest.main()
