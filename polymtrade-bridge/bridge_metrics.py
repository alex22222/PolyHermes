"""Light-weight metrics for the Polymtrade Bridge.

Exposes counters and recent latency percentiles through /metrics. Latency
events are also written by a background thread for cross-restart analysis.
"""

import json
import os
import queue
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class BridgeMetrics:
    """In-memory counters for bridge health and trade execution."""

    # Signal lifecycle
    signals_received: int = 0
    signals_filtered: int = 0
    signals_executed: int = 0
    signals_failed: int = 0
    signals_queue_rejected: int = 0
    signals_trade_lock_timeout: int = 0

    # Trade outcomes
    trades_buy_total: int = 0
    trades_buy_success: int = 0
    trades_buy_failed: int = 0
    trades_buy_submitted: int = 0
    buy_verifications_success: int = 0
    buy_verifications_unconfirmed: int = 0
    trades_sell_total: int = 0
    trades_sell_success: int = 0
    trades_sell_failed: int = 0
    trades_sell_submitted: int = 0
    sell_verifications_success: int = 0
    sell_verifications_unconfirmed: int = 0

    # Gamma API
    gamma_api_requests: int = 0
    gamma_api_failures: int = 0
    gamma_metadata_cache_hits: int = 0
    gamma_metadata_cache_misses: int = 0
    event_cache_hits: int = 0
    event_cache_misses: int = 0

    # Modal / page interactions
    modal_blocks: int = 0
    modal_dismissals: int = 0

    # Portfolio endpoint
    portfolio_requests: int = 0
    portfolio_errors: int = 0

    # Outcome/amount interaction failures
    outcome_selection_failures: int = 0
    amount_input_failures: int = 0

    # Portfolio risk checks
    portfolio_risk_checks: int = 0
    portfolio_risk_unavailable: int = 0
    portfolio_risk_would_block: int = 0
    portfolio_risk_denied: int = 0
    performance_events_dropped: int = 0
    last_mile_quote_observations: int = 0
    last_mile_quote_unavailable: int = 0
    last_mile_price_drift_would_block: int = 0

    performance_event_log: str = field(
        default_factory=lambda: os.getenv(
            "BRIDGE_PERFORMANCE_EVENT_LOG",
            os.path.join(os.path.dirname(os.path.abspath(__file__)), "logs", "bridge-performance.jsonl"),
        )
    )
    _latency_samples: Dict[str, deque] = field(default_factory=dict, init=False, repr=False)
    _measurement_samples: Dict[str, deque] = field(default_factory=dict, init=False, repr=False)
    _latency_sample_limit: int = field(
        default_factory=lambda: max(
            100,
            int(os.getenv("BRIDGE_LATENCY_SAMPLE_LIMIT", "4096")),
        ),
        init=False,
        repr=False,
    )
    _latency_lock: threading.Lock = field(
        default_factory=threading.Lock,
        init=False,
        repr=False,
    )
    _writer_queue: queue.Queue = field(
        default_factory=lambda: queue.Queue(maxsize=10000),
        init=False,
        repr=False,
    )
    _writer_thread: Optional[threading.Thread] = field(default=None, init=False, repr=False)

    @staticmethod
    def _percentile(values: list[float], percentile: float) -> float:
        if not values:
            return 0.0
        index = (len(values) - 1) * percentile
        lower = int(index)
        upper = min(lower + 1, len(values) - 1)
        fraction = index - lower
        return values[lower] + (values[upper] - values[lower]) * fraction

    def start_event_writer(self) -> None:
        if self._writer_thread and self._writer_thread.is_alive():
            return
        event_dir = os.path.dirname(self.performance_event_log)
        if event_dir:
            os.makedirs(event_dir, exist_ok=True)
        self._writer_thread = threading.Thread(
            target=self._write_events,
            name="bridge-performance-writer",
            daemon=True,
        )
        self._writer_thread.start()

    def stop_event_writer(self) -> None:
        thread = self._writer_thread
        if not thread:
            return
        self._writer_queue.put(None)
        thread.join(timeout=5)
        self._writer_thread = None

    def _write_events(self) -> None:
        with open(self.performance_event_log, "a", encoding="utf-8", buffering=1) as output:
            while True:
                event = self._writer_queue.get()
                try:
                    if event is None:
                        return
                    output.write(json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n")
                finally:
                    self._writer_queue.task_done()

    def observe_latency(self, name: str, duration_ms: float, **labels: Any) -> None:
        value = round(max(0.0, float(duration_ms)), 3)
        with self._latency_lock:
            samples = self._latency_samples.get(name)
            if samples is None:
                samples = deque(maxlen=self._latency_sample_limit)
                self._latency_samples[name] = samples
            samples.append(value)

        if not self._writer_thread or not self._writer_thread.is_alive():
            return
        event = {
            "timestamp_ms": int(time.time() * 1000),
            "metric": name,
            "duration_ms": value,
            **labels,
        }
        try:
            self._writer_queue.put_nowait(event)
        except queue.Full:
            self.performance_events_dropped += 1

    def observe_measurement(
        self,
        name: str,
        value: float,
        *,
        unit: str,
        **labels: Any,
    ) -> None:
        measured = round(float(value), 6)
        with self._latency_lock:
            samples = self._measurement_samples.get(name)
            if samples is None:
                samples = deque(maxlen=self._latency_sample_limit)
                self._measurement_samples[name] = samples
            samples.append(measured)

        if not self._writer_thread or not self._writer_thread.is_alive():
            return
        event = {
            "timestamp_ms": int(time.time() * 1000),
            "metric": name,
            "value": measured,
            "unit": unit,
            **labels,
        }
        try:
            self._writer_queue.put_nowait(event)
        except queue.Full:
            self.performance_events_dropped += 1

    def latency_summary(self) -> Dict[str, Dict[str, float | int]]:
        with self._latency_lock:
            snapshots = {
                name: sorted(samples)
                for name, samples in self._latency_samples.items()
                if samples
            }
        return {
            name: {
                "count": len(values),
                "p50": round(self._percentile(values, 0.50), 3),
                "p95": round(self._percentile(values, 0.95), 3),
                "max": round(values[-1], 3),
            }
            for name, values in snapshots.items()
        }

    def measurement_summary(self) -> Dict[str, Dict[str, float | int]]:
        with self._latency_lock:
            snapshots = {
                name: sorted(samples)
                for name, samples in self._measurement_samples.items()
                if samples
            }
        return {
            name: {
                "count": len(values),
                "p50": round(self._percentile(values, 0.50), 6),
                "p95": round(self._percentile(values, 0.95), 6),
                "min": round(values[0], 6),
                "max": round(values[-1], 6),
            }
            for name, values in snapshots.items()
        }

    def to_dict(self) -> Dict[str, Any]:
        return {
            "signals_received": self.signals_received,
            "signals_filtered": self.signals_filtered,
            "signals_executed": self.signals_executed,
            "signals_failed": self.signals_failed,
            "signals_queue_rejected": self.signals_queue_rejected,
            "signals_trade_lock_timeout": self.signals_trade_lock_timeout,
            "trades_buy_total": self.trades_buy_total,
            "trades_buy_success": self.trades_buy_success,
            "trades_buy_failed": self.trades_buy_failed,
            "trades_buy_submitted": self.trades_buy_submitted,
            "buy_verifications_success": self.buy_verifications_success,
            "buy_verifications_unconfirmed": self.buy_verifications_unconfirmed,
            "trades_sell_total": self.trades_sell_total,
            "trades_sell_success": self.trades_sell_success,
            "trades_sell_failed": self.trades_sell_failed,
            "trades_sell_submitted": self.trades_sell_submitted,
            "sell_verifications_success": self.sell_verifications_success,
            "sell_verifications_unconfirmed": self.sell_verifications_unconfirmed,
            "gamma_api_requests": self.gamma_api_requests,
            "gamma_api_failures": self.gamma_api_failures,
            "gamma_metadata_cache_hits": self.gamma_metadata_cache_hits,
            "gamma_metadata_cache_misses": self.gamma_metadata_cache_misses,
            "event_cache_hits": self.event_cache_hits,
            "event_cache_misses": self.event_cache_misses,
            "modal_blocks": self.modal_blocks,
            "modal_dismissals": self.modal_dismissals,
            "portfolio_requests": self.portfolio_requests,
            "portfolio_errors": self.portfolio_errors,
            "outcome_selection_failures": self.outcome_selection_failures,
            "amount_input_failures": self.amount_input_failures,
            "portfolio_risk_checks": self.portfolio_risk_checks,
            "portfolio_risk_unavailable": self.portfolio_risk_unavailable,
            "portfolio_risk_would_block": self.portfolio_risk_would_block,
            "portfolio_risk_denied": self.portfolio_risk_denied,
            "performance_events_dropped": self.performance_events_dropped,
            "last_mile_quote_observations": self.last_mile_quote_observations,
            "last_mile_quote_unavailable": self.last_mile_quote_unavailable,
            "last_mile_price_drift_would_block": self.last_mile_price_drift_would_block,
            "latency_ms": self.latency_summary(),
            "measurements": self.measurement_summary(),
        }


# Singleton metrics instance used across the bridge.
metrics = BridgeMetrics()
