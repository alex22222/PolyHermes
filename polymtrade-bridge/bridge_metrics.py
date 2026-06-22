"""Light-weight in-memory metrics for the Polymtrade Bridge.

Exposes a JSON /metrics endpoint and simple counters for observability.
No external dependencies are required.
"""

from dataclasses import dataclass, field
from typing import Dict


@dataclass
class BridgeMetrics:
    """In-memory counters for bridge health and trade execution."""

    # Signal lifecycle
    signals_received: int = 0
    signals_filtered: int = 0
    signals_executed: int = 0
    signals_failed: int = 0

    # Trade outcomes
    trades_buy_total: int = 0
    trades_buy_success: int = 0
    trades_buy_failed: int = 0
    trades_sell_total: int = 0
    trades_sell_success: int = 0
    trades_sell_failed: int = 0

    # Gamma API
    gamma_api_requests: int = 0
    gamma_api_failures: int = 0

    # Modal / page interactions
    modal_blocks: int = 0
    modal_dismissals: int = 0

    # Portfolio endpoint
    portfolio_requests: int = 0
    portfolio_errors: int = 0

    # Outcome/amount interaction failures
    outcome_selection_failures: int = 0
    amount_input_failures: int = 0

    def to_dict(self) -> Dict[str, int]:
        return {
            "signals_received": self.signals_received,
            "signals_filtered": self.signals_filtered,
            "signals_executed": self.signals_executed,
            "signals_failed": self.signals_failed,
            "trades_buy_total": self.trades_buy_total,
            "trades_buy_success": self.trades_buy_success,
            "trades_buy_failed": self.trades_buy_failed,
            "trades_sell_total": self.trades_sell_total,
            "trades_sell_success": self.trades_sell_success,
            "trades_sell_failed": self.trades_sell_failed,
            "gamma_api_requests": self.gamma_api_requests,
            "gamma_api_failures": self.gamma_api_failures,
            "modal_blocks": self.modal_blocks,
            "modal_dismissals": self.modal_dismissals,
            "portfolio_requests": self.portfolio_requests,
            "portfolio_errors": self.portfolio_errors,
            "outcome_selection_failures": self.outcome_selection_failures,
            "amount_input_failures": self.amount_input_failures,
        }


# Singleton metrics instance used across the bridge.
metrics = BridgeMetrics()
