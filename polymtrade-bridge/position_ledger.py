import logging
import os
from decimal import Decimal
from typing import Optional

import pymysql
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class PositionLedger:
    """Maintain a simple on-chain position view from bridge_trade_record.

    Since Bridge trades through a browser session, we cannot easily query the
    backend's wallet account positions (they may be different accounts). Instead,
    we derive the Bridge account's net position per market/outcome from the
    SUCCESS records that Bridge itself has written.

    This prevents SELL signals from being executed when there is no corresponding
    BUY position.
    """

    def __init__(self):
        self.host = os.getenv("COPY_TRADING_DB_HOST", "127.0.0.1")
        self.port = int(os.getenv("COPY_TRADING_DB_PORT", "3307"))
        self.user = os.getenv("COPY_TRADING_DB_USER", "root")
        self.password = os.getenv("COPY_TRADING_DB_PASSWORD", "")
        self.database = os.getenv("COPY_TRADING_DB_NAME", "polyhermes")
        self.bridge_id = os.getenv("BRIDGE_ID", "polymtrade-bridge")

    def _connect(self):
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database=self.database,
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
        )

    def get_net_quantity(
        self,
        market_id: str,
        outcome: Optional[str],
        outcome_index: Optional[int],
    ) -> Decimal:
        """Return net owned quantity for a given market/outcome.

        Net = SUM(BUY quantity) - SUM(SELL quantity) from SUCCESS records.
        """
        sql = """
        SELECT side, quantity
        FROM bridge_trade_record
        WHERE bridge_id = %s
          AND market_id = %s
          AND status = 'SUCCESS'
          AND (%s IS NULL OR outcome = %s)
          AND (%s IS NULL OR outcome_index = %s)
        """
        params = (
            self.bridge_id,
            market_id,
            outcome,
            outcome,
            outcome_index,
            outcome_index,
        )

        net = Decimal("0")
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    for row in cur.fetchall():
                        side = (row.get("side") or "").upper()
                        qty = Decimal(str(row.get("quantity") or 0))
                        if side == "BUY":
                            net += qty
                        elif side == "SELL":
                            net -= qty
        except Exception as e:
            logger.exception(f"Failed to query position ledger: {e}")
            # Be conservative: if we cannot verify, assume zero so we don't sell.
            return Decimal("0")

        return net

    def has_sufficient_position(
        self,
        market_id: str,
        outcome: Optional[str],
        outcome_index: Optional[int],
        sell_quantity: Decimal,
    ) -> bool:
        """Check whether there are enough shares to sell."""
        net = self.get_net_quantity(market_id, outcome, outcome_index)
        sufficient = net >= sell_quantity
        if not sufficient:
            logger.info(
                f"Insufficient position for {market_id} {outcome}: "
                f"net={net}, required={sell_quantity}"
            )
        return sufficient
