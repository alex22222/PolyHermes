import json
import logging
import os
import time
from decimal import Decimal
from typing import Optional

import pymysql
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)


class BridgeTradeRecorder:
    """Persist Bridge trade executions to PolyHermes bridge_trade_record table."""

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

    def record_pending(
        self,
        external_trade_id: Optional[str],
        market_id: str,
        market_title: Optional[str],
        side: str,
        outcome: Optional[str],
        outcome_index: Optional[int],
        quantity: Decimal,
        price: Decimal,
        amount: Decimal,
        raw_payload: Optional[dict] = None,
    ) -> int:
        """Insert a PENDING record and return its id."""
        now = int(time.time() * 1000)
        sql = """
        INSERT INTO bridge_trade_record
        (bridge_id, external_trade_id, market_id, market_title, side, outcome, outcome_index,
         quantity, price, amount, status, raw_payload, executed_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        self.bridge_id,
                        external_trade_id,
                        market_id,
                        market_title,
                        side.upper(),
                        outcome,
                        outcome_index,
                        quantity,
                        price,
                        amount,
                        "PENDING",
                        json.dumps(raw_payload, ensure_ascii=False, default=str) if raw_payload else None,
                        now,
                        now,
                        now,
                    ),
                )
                conn.commit()
                record_id = cur.lastrowid
        logger.info(f"Recorded PENDING bridge trade {record_id} for {external_trade_id}")
        return record_id

    def update_status(self, record_id: int, status: str, error_message: Optional[str] = None):
        """Update record status to SUCCESS or FAILED."""
        now = int(time.time() * 1000)
        sql = """
        UPDATE bridge_trade_record
        SET status = %s, error_message = %s, updated_at = %s
        WHERE id = %s
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(sql, (status, error_message, now, record_id))
                conn.commit()
        logger.info(f"Updated bridge trade {record_id} to {status}")

    def record_result(
        self,
        external_trade_id: Optional[str],
        market_id: str,
        market_title: Optional[str],
        side: str,
        outcome: Optional[str],
        outcome_index: Optional[int],
        quantity: Decimal,
        price: Decimal,
        amount: Decimal,
        status: str,
        error_message: Optional[str] = None,
        raw_payload: Optional[dict] = None,
    ) -> int:
        """One-shot insert a completed record (used for manual /execute)."""
        now = int(time.time() * 1000)
        sql = """
        INSERT INTO bridge_trade_record
        (bridge_id, external_trade_id, market_id, market_title, side, outcome, outcome_index,
         quantity, price, amount, status, error_message, raw_payload, executed_at, created_at, updated_at)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """
        with self._connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    sql,
                    (
                        self.bridge_id,
                        external_trade_id,
                        market_id,
                        market_title,
                        side.upper(),
                        outcome,
                        outcome_index,
                        quantity,
                        price,
                        amount,
                        status,
                        error_message,
                        json.dumps(raw_payload, ensure_ascii=False, default=str) if raw_payload else None,
                        now,
                        now,
                        now,
                    ),
                )
                conn.commit()
                record_id = cur.lastrowid
        logger.info(f"Recorded {status} bridge trade {record_id} for {external_trade_id}")
        return record_id
