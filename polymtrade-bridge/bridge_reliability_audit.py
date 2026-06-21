#!/usr/bin/env python3
"""Read-only reliability audit for Polymtrade Bridge executions.

The audit compares bridge_trade_record with the live /portfolio endpoint and
reports records that need human/code investigation. It never places trades.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
import pymysql
from dotenv import load_dotenv


SCRIPT_DIR = Path(__file__).resolve().parent
load_dotenv(SCRIPT_DIR / ".env")
load_dotenv()
DEFAULT_RECONCILIATION_FILE = SCRIPT_DIR / "audit_reconciliations.json"


@dataclass(frozen=True)
class DbConfig:
    host: str
    port: int
    user: str
    password: str
    database: str
    bridge_id: str


def decimal_value(value: Any) -> Decimal:
    if value is None:
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return Decimal("0")


def normalize_text(value: Any) -> str:
    return str(value or "").strip().lower()


def normalize_id(value: Any) -> str:
    return normalize_text(value)


def normalize_outcome(value: Any) -> str:
    text = normalize_text(value)
    mapping = {
        "yes": "yes",
        "y": "yes",
        "是": "yes",
        "no": "no",
        "n": "no",
        "否": "no",
    }
    return mapping.get(text, text)


def record_summary(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": row.get("id"),
        "external_trade_id": row.get("external_trade_id"),
        "market_id": row.get("market_id"),
        "market_title": row.get("market_title"),
        "side": row.get("side"),
        "outcome": row.get("outcome"),
        "outcome_index": row.get("outcome_index"),
        "quantity": str(row.get("quantity")),
        "price": str(row.get("price")),
        "amount": str(row.get("amount")),
        "status": row.get("status"),
        "error_message": row.get("error_message"),
        "created_at": row.get("created_at"),
        "updated_at": row.get("updated_at"),
    }


def latest_record_time_ms(rows: list[dict[str, Any]]) -> int | None:
    timestamps = [
        int(value)
        for row in rows
        for value in (row.get("updated_at"), row.get("created_at"))
        if value is not None
    ]
    return max(timestamps) if timestamps else None


def reconciliation_key(
    *,
    bridge_id: str,
    market_id: Any,
    market_title: Any,
    outcome: Any,
    outcome_index: Any = None,
) -> str:
    parts = [
        normalize_text(bridge_id),
        normalize_id(market_id),
        normalize_text(market_title),
        normalize_outcome(outcome),
        "" if outcome_index is None else str(outcome_index),
    ]
    return "|".join(parts)


def reconciliation_file_path(value: Any = None) -> Path:
    raw_path = value or os.getenv("BRIDGE_AUDIT_RECONCILIATION_FILE")
    return Path(raw_path).expanduser() if raw_path else DEFAULT_RECONCILIATION_FILE


def load_reconciliations(path: Path | None = None) -> dict[str, Any]:
    file_path = reconciliation_file_path(path)
    if not file_path.exists():
        return {}
    try:
        data = json.loads(file_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    annotations = data.get("annotations", data)
    return annotations if isinstance(annotations, dict) else {}


def save_reconciliations(annotations: dict[str, Any], path: Path | None = None) -> Path:
    file_path = reconciliation_file_path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": 1,
        "updated_at": int(time.time() * 1000),
        "annotations": annotations,
    }
    temp_path = file_path.with_suffix(file_path.suffix + ".tmp")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    temp_path.replace(file_path)
    return file_path


def db_config() -> DbConfig:
    return DbConfig(
        host=os.getenv("COPY_TRADING_DB_HOST", "127.0.0.1"),
        port=int(os.getenv("COPY_TRADING_DB_PORT", "3307")),
        user=os.getenv("COPY_TRADING_DB_USER", "root"),
        password=os.getenv("COPY_TRADING_DB_PASSWORD", ""),
        database=os.getenv("COPY_TRADING_DB_NAME", "polyhermes"),
        bridge_id=os.getenv("BRIDGE_ID", "polymtrade-bridge"),
    )


def connect(config: DbConfig):
    return pymysql.connect(
        host=config.host,
        port=config.port,
        user=config.user,
        password=config.password,
        database=config.database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )


def fetch_records(config: DbConfig, limit: int) -> list[dict[str, Any]]:
    sql = """
    SELECT id, external_trade_id, market_id, market_title, side, outcome,
           outcome_index, quantity, price, amount, status, error_message,
           executed_at, created_at, updated_at
    FROM bridge_trade_record
    WHERE bridge_id = %s
    ORDER BY created_at DESC
    LIMIT %s
    """
    with connect(config) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (config.bridge_id, limit))
            return list(cur.fetchall())


def fetch_success_ledger(config: DbConfig, max_rows: int) -> list[dict[str, Any]]:
    sql = """
    SELECT id, external_trade_id, market_id, market_title, side, outcome,
           outcome_index, quantity, price, amount, status, error_message,
           executed_at, created_at, updated_at
    FROM bridge_trade_record
    WHERE bridge_id = %s
      AND status = 'SUCCESS'
    ORDER BY created_at DESC
    LIMIT %s
    """
    with connect(config) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, (config.bridge_id, max_rows))
            return list(cur.fetchall())


def fetch_portfolio(url: str, timeout: float) -> dict[str, Any]:
    with httpx.Client(timeout=timeout) as client:
        response = client.get(url)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("portfolio endpoint returned a non-object payload")
        return data


def position_key(position: dict[str, Any]) -> tuple[str, str, str]:
    condition_id = position.get("conditionId") or position.get("marketId")
    title = position.get("marketTitle")
    return (
        normalize_id(condition_id),
        normalize_text(title),
        normalize_outcome(position.get("side")),
    )


def record_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return (
        normalize_id(row.get("market_id")),
        normalize_text(row.get("market_title")),
        normalize_outcome(row.get("outcome")),
    )


def build_portfolio_index(
    positions: list[dict[str, Any]],
) -> dict[tuple[str, str, str], Decimal]:
    index: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    for position in positions:
        key = position_key(position)
        qty = decimal_value(position.get("quantity"))
        if qty > 0:
            index[key] += qty
    return dict(index)


def find_actual_quantity(
    portfolio_index: dict[tuple[str, str, str], Decimal],
    market_id: str,
    market_title: str,
    outcome: str,
) -> Decimal:
    actual = Decimal("0")
    if market_id:
        for pos_market_id, _, pos_outcome in portfolio_index:
            if pos_market_id == market_id and pos_outcome == outcome:
                actual += portfolio_index[(pos_market_id, _, pos_outcome)]
    if actual > 0:
        return actual
    if market_title:
        for _, pos_title, pos_outcome in portfolio_index:
            if pos_title == market_title and pos_outcome == outcome:
                actual += portfolio_index[(_, pos_title, pos_outcome)]
    return actual


def build_expected_positions(
    success_rows: list[dict[str, Any]],
) -> tuple[dict[tuple[str, str, str, Any], Decimal], dict[tuple[str, str, str, Any], list[dict[str, Any]]]]:
    expected: dict[tuple[str, str, str, Any], Decimal] = defaultdict(Decimal)
    contributing_records: dict[tuple[str, str, str, Any], list[dict[str, Any]]] = defaultdict(list)

    for row in reversed(success_rows):
        side = normalize_text(row.get("side")).upper()
        qty = decimal_value(row.get("quantity"))
        key = (*record_key(row), row.get("outcome_index"))
        if side == "BUY":
            expected[key] += qty
            contributing_records[key].append(row)
        elif side == "SELL":
            expected[key] -= qty
            contributing_records[key].append(row)

    return dict(expected), dict(contributing_records)


def audit(args: argparse.Namespace) -> dict[str, Any]:
    config = db_config()
    now_ms = int(time.time() * 1000)
    records = fetch_records(config, args.limit)
    success_rows = fetch_success_ledger(config, args.ledger_limit)
    portfolio_payload = fetch_portfolio(args.portfolio_url, args.portfolio_timeout)
    positions = portfolio_payload.get("positions") or []
    if not isinstance(positions, list):
        raise ValueError("portfolio positions is not a list")

    portfolio_index = build_portfolio_index(positions)
    reconciliations = load_reconciliations(args.reconciliation_file)
    pending_timeouts = []
    recent_failures = []
    for row in records:
        status = normalize_text(row.get("status")).upper()
        age_ms = now_ms - int(row.get("created_at") or row.get("updated_at") or now_ms)
        if status == "PENDING" and age_ms >= args.pending_timeout_ms:
            item = record_summary(row)
            item["age_ms"] = age_ms
            pending_timeouts.append(item)
        elif status == "FAILED":
            recent_failures.append(record_summary(row))

    expected, contributing_records = build_expected_positions(success_rows)
    expected_index: dict[tuple[str, str, str], Decimal] = defaultdict(Decimal)
    success_position_mismatches = []
    fresh_success_position_mismatches = 0
    stale_success_position_mismatches = 0
    reconciled_success_position_mismatches = 0
    for key, expected_qty in expected.items():
        market_id, market_title, outcome, outcome_index = key
        if expected_qty <= args.quantity_tolerance:
            continue
        expected_index[(market_id, market_title, outcome)] += expected_qty
        actual_qty = find_actual_quantity(portfolio_index, market_id, market_title, outcome)
        min_expected = expected_qty * Decimal(str(args.min_quantity_ratio))
        if actual_qty + args.quantity_tolerance < min_expected:
            source_records = contributing_records.get(key, [])
            latest_time = latest_record_time_ms(source_records)
            age_ms = now_ms - latest_time if latest_time is not None else None
            is_stale = age_ms is not None and age_ms >= args.stale_mismatch_ms
            annotation_key = reconciliation_key(
                bridge_id=config.bridge_id,
                market_id=market_id,
                market_title=market_title,
                outcome=outcome,
                outcome_index=outcome_index,
            )
            reconciliation = reconciliations.get(annotation_key)
            is_reconciled = isinstance(reconciliation, dict)
            if is_reconciled:
                reconciled_success_position_mismatches += 1
            elif is_stale:
                stale_success_position_mismatches += 1
            else:
                fresh_success_position_mismatches += 1
            success_position_mismatches.append(
                {
                    "bucket": (
                        "reconciled_success_position_mismatch"
                        if is_reconciled
                        else "stale_success_position_mismatch"
                        if is_stale
                        else "success_position_mismatch"
                    ),
                    "market_id": market_id,
                    "market_title": market_title,
                    "outcome": outcome,
                    "outcome_index": outcome_index,
                    "reconciliation_key": annotation_key,
                    "expected_quantity": str(expected_qty),
                    "actual_quantity": str(actual_qty),
                    "latest_record_id": source_records[-1].get("id") if source_records else None,
                    "latest_record_updated_at": latest_time,
                    "age_ms": age_ms,
                    "is_stale": is_stale,
                    "is_reconciled": is_reconciled,
                    "stale_after_ms": args.stale_mismatch_ms,
                    "mismatch_reason": (
                        "operator_reconciled"
                        if is_reconciled
                        else "historical_or_external_close_possible"
                        if is_stale
                        else "fresh_success_record_not_in_live_portfolio"
                    ),
                    "reconciliation": reconciliation if is_reconciled else None,
                    "contributing_record_ids": [row.get("id") for row in source_records[-5:]],
                }
            )

    unexpected_portfolio_positions = []
    portfolio_position_summaries = [
        {
            "market_id": position.get("conditionId") or position.get("marketId"),
            "market_title": position.get("marketTitle"),
            "outcome": position.get("side"),
            "quantity": position.get("quantity"),
            "current_value": position.get("currentValue"),
            "market_slug": position.get("marketSlug"),
        }
        for position in positions
    ]
    for position in positions:
        market_id, market_title, outcome = position_key(position)
        actual_qty = decimal_value(position.get("quantity"))
        expected_qty = find_actual_quantity(expected_index, market_id, market_title, outcome)
        if actual_qty > args.quantity_tolerance and expected_qty <= args.quantity_tolerance:
            unexpected_portfolio_positions.append(
                {
                    "bucket": "unexpected_portfolio_position",
                    "market_id": position.get("conditionId") or position.get("marketId"),
                    "market_title": position.get("marketTitle"),
                    "outcome": position.get("side"),
                    "actual_quantity": str(actual_qty),
                    "expected_quantity": str(expected_qty),
                    "market_slug": position.get("marketSlug"),
                }
            )

    return {
        "bridge_id": config.bridge_id,
        "portfolio_url": args.portfolio_url,
        "synced_at": portfolio_payload.get("synced_at"),
        "metrics": {
            "records_checked": len(records),
            "success_ledger_rows_checked": len(success_rows),
            "portfolio_position_count": len(positions),
            "pending_timeout_count": len(pending_timeouts),
            "success_position_mismatch_count": len(success_position_mismatches),
            "active_success_position_mismatch_count": fresh_success_position_mismatches + stale_success_position_mismatches,
            "fresh_success_position_mismatch_count": fresh_success_position_mismatches,
            "stale_success_position_mismatch_count": stale_success_position_mismatches,
            "reconciled_success_position_mismatch_count": reconciled_success_position_mismatches,
            "unexpected_portfolio_position_count": len(unexpected_portfolio_positions),
            "recent_failure_count": len(recent_failures),
        },
        "pending_timeouts": pending_timeouts,
        "success_position_mismatches": success_position_mismatches,
        "unexpected_portfolio_positions": unexpected_portfolio_positions,
        "recent_failures": recent_failures[: args.failure_limit],
        "portfolio_positions": portfolio_position_summaries,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit Bridge records against live portfolio.")
    parser.add_argument("--limit", type=int, default=100, help="recent records to inspect")
    parser.add_argument("--ledger-limit", type=int, default=1000, help="SUCCESS rows used to compute expected open positions")
    parser.add_argument("--failure-limit", type=int, default=20, help="FAILED records to include in output")
    parser.add_argument("--pending-timeout-ms", type=int, default=120000, help="PENDING age threshold")
    parser.add_argument("--stale-mismatch-ms", type=int, default=1800000, help="SUCCESS mismatch age threshold for historical/stale classification")
    parser.add_argument("--reconciliation-file", default=str(reconciliation_file_path()), help="JSON file with operator reconciliation annotations")
    parser.add_argument("--portfolio-url", default=os.getenv("BRIDGE_PORTFOLIO_URL", "http://127.0.0.1:8080/portfolio"))
    parser.add_argument("--portfolio-timeout", type=float, default=90.0)
    parser.add_argument("--min-quantity-ratio", type=Decimal, default=Decimal("0.5"))
    parser.add_argument("--quantity-tolerance", type=Decimal, default=Decimal("0.05"))
    parser.add_argument("--strict", action="store_true", help="exit 1 when actionable issues are found")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        result = audit(args)
    except Exception as exc:
        print(json.dumps({"error": str(exc)}, ensure_ascii=False, indent=2), file=sys.stderr)
        return 2

    print(json.dumps(result, ensure_ascii=False, indent=2, default=str))
    actionable = (
        result["metrics"]["pending_timeout_count"]
        + result["metrics"]["active_success_position_mismatch_count"]
        + result["metrics"]["unexpected_portfolio_position_count"]
    )
    return 1 if args.strict and actionable else 0


if __name__ == "__main__":
    raise SystemExit(main())
