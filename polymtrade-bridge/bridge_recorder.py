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

    def exists(self, external_trade_id: str) -> bool:
        """Check whether a record with the given external trade id already exists."""
        sql = """
        SELECT 1 FROM bridge_trade_record
        WHERE bridge_id = %s AND external_trade_id = %s
        LIMIT 1
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (self.bridge_id, external_trade_id))
                    return cur.fetchone() is not None
        except Exception as e:
            logger.warning(f"Failed to check existing bridge trade: {e}")
            return False

    def has_prior_short_cycle_buy(
        self,
        market_id: str,
        market_slug: Optional[str],
        leader_address: Optional[str],
    ) -> bool:
        """Return True if this leader already has an active/success BUY on the market."""
        if not leader_address:
            return False
        leader = leader_address.lower()
        sql = """
        SELECT 1 FROM bridge_trade_record
        WHERE bridge_id = %s
          AND side = 'BUY'
          AND status IN ('PENDING', 'SUCCESS')
          AND (
            market_id = %s
            OR (%s IS NOT NULL AND raw_payload LIKE %s)
          )
          AND LOWER(raw_payload) LIKE %s
        LIMIT 1
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        sql,
                        (
                            self.bridge_id,
                            market_id,
                            market_slug,
                            f'%"{market_slug}"%' if market_slug else None,
                            f"%{leader}%",
                        ),
                    )
                    return cur.fetchone() is not None
        except Exception as e:
            logger.warning(f"Failed to check prior short-cycle BUY: {e}")
            return False

    def has_any_prior_short_cycle_buy(
        self,
        market_id: str,
        market_slug: Optional[str],
    ) -> bool:
        """Return True if any leader already has an active/success BUY on the market."""
        sql = """
        SELECT 1 FROM bridge_trade_record
        WHERE bridge_id = %s
          AND side = 'BUY'
          AND status IN ('PENDING', 'SUCCESS')
          AND (
            market_id = %s
            OR (%s IS NOT NULL AND raw_payload LIKE %s)
          )
        LIMIT 1
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        sql,
                        (
                            self.bridge_id,
                            market_id,
                            market_slug,
                            f'%"{market_slug}"%' if market_slug else None,
                        ),
                    )
                    return cur.fetchone() is not None
        except Exception as e:
            logger.warning(f"Failed to check any prior short-cycle BUY: {e}")
            return False

    def btc_5m_success_buy_usage_since(self, since_ms: int) -> tuple[int, Decimal]:
        """Return count and amount of successful BTC 5M BUYs since a timestamp."""
        sql = """
        SELECT COUNT(*) AS buy_count, COALESCE(SUM(amount), 0) AS buy_amount
        FROM bridge_trade_record
        WHERE bridge_id = %s
          AND side = 'BUY'
          AND status = 'SUCCESS'
          AND created_at >= %s
          AND raw_payload LIKE %s
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (self.bridge_id, since_ms, '%btc-updown-5m-%'))
                    row = cur.fetchone() or {}
                    return int(row.get("buy_count") or 0), Decimal(str(row.get("buy_amount") or "0"))
        except Exception as e:
            logger.warning(f"Failed to check BTC 5M daily BUY usage: {e}")
            return 0, Decimal("0")

    def recent_success_sell_size(
        self,
        market_id: str,
        market_slug: Optional[str],
        outcome: Optional[str],
        outcome_index: Optional[int],
        leader_address: Optional[str],
        since_ms: int,
    ) -> Decimal:
        """Return summed leader SELL size for the same leader/market/outcome since a timestamp."""
        if not leader_address:
            return Decimal("0")
        leader = leader_address.lower()
        sql = """
        SELECT COALESCE(SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(raw_payload, '$.size')) AS DECIMAL(20,8))), 0) AS leader_size
        FROM bridge_trade_record
        WHERE bridge_id = %s
          AND side = 'SELL'
          AND status = 'SUCCESS'
          AND created_at >= %s
          AND (
            market_id = %s
            OR (%s IS NOT NULL AND raw_payload LIKE %s)
          )
          AND (%s IS NULL OR outcome = %s)
          AND (%s IS NULL OR outcome_index = %s)
          AND LOWER(raw_payload) LIKE %s
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        sql,
                        (
                            self.bridge_id,
                            since_ms,
                            market_id,
                            market_slug,
                            f'%"{market_slug}"%' if market_slug else None,
                            outcome,
                            outcome,
                            outcome_index,
                            outcome_index,
                            f"%{leader}%",
                        ),
                    )
                    row = cur.fetchone() or {}
                    return Decimal(str(row.get("leader_size") or "0"))
        except Exception as e:
            logger.warning(f"Failed to query recent sell size: {e}")
            return Decimal("0")

    def recent_leader_sell_size(
        self,
        market_id: str,
        market_slug: Optional[str],
        outcome: Optional[str],
        outcome_index: Optional[int],
        leader_address: Optional[str],
        since_ms: int,
    ) -> Decimal:
        """Return summed leader-side SELL size from webhook logs since a timestamp.

        This uses the signal source of truth instead of local execution results,
        so a failed/skipped local SELL can still protect a later tiny BUY-back.
        """
        if not leader_address:
            return Decimal("0")
        leader = leader_address.lower()
        sql = """
        SELECT COALESCE(SUM(CAST(JSON_UNQUOTE(JSON_EXTRACT(request_body, '$.size')) AS DECIMAL(20,8))), 0) AS leader_size
        FROM bridge_webhook_log
        WHERE bridge_id = %s
          AND side = 'SELL'
          AND created_at >= %s
          AND LOWER(leader_address) = %s
          AND (
            condition_id = %s
            OR (%s IS NOT NULL AND market_slug = %s)
            OR (%s IS NOT NULL AND request_body LIKE %s)
          )
          AND (%s IS NULL OR outcome = %s)
          AND (
            %s IS NULL
            OR (
              request_body IS NOT NULL
              AND JSON_VALID(request_body) = 1
              AND CAST(JSON_UNQUOTE(JSON_EXTRACT(request_body, '$.outcomeIndex')) AS SIGNED) = %s
            )
          )
          AND request_body IS NOT NULL
          AND JSON_VALID(request_body) = 1
          AND COALESCE(status, '') <> 'SKIPPED'
        """
        try:
            with self._connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        sql,
                        (
                            self.bridge_id,
                            since_ms,
                            leader,
                            market_id,
                            market_slug,
                            market_slug,
                            market_slug,
                            f'%"{market_slug}"%' if market_slug else None,
                            outcome,
                            outcome,
                            outcome_index,
                            outcome_index,
                        ),
                    )
                    row = cur.fetchone() or {}
                    return Decimal(str(row.get("leader_size") or "0"))
        except Exception as e:
            logger.warning(f"Failed to query recent leader sell size: {e}")
            return Decimal("0")

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
