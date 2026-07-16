#!/usr/bin/env python3
"""Evaluate persisted Bridge latency and supervisor evidence."""

import argparse
import json
import math
import os
import re
import time
from pathlib import Path
from typing import Any


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = (len(ordered) - 1) * quantile
    lower = math.floor(index)
    upper = min(lower + 1, len(ordered) - 1)
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (index - lower)


def evaluate_latency(
    events: list[dict[str, Any]],
    metric: str,
    *,
    min_samples: int,
    p50_max_ms: float,
    p95_max_ms: float,
) -> dict[str, Any]:
    values = [
        float(event["duration_ms"])
        for event in events
        if event.get("metric") == metric and event.get("duration_ms") is not None
    ]
    if not values:
        return {"status": "pending", "count": 0, "required_count": min_samples}
    p50 = percentile(values, 0.50)
    p95 = percentile(values, 0.95)
    enough_samples = len(values) >= min_samples
    within_target = p50 <= p50_max_ms and p95 <= p95_max_ms
    status = "pass" if enough_samples and within_target else "fail" if enough_samples else "pending"
    return {
        "status": status,
        "count": len(values),
        "required_count": min_samples,
        "p50_ms": round(p50, 3),
        "p95_ms": round(p95, 3),
        "max_ms": round(max(values), 3),
        "target_p50_max_ms": p50_max_ms,
        "target_p95_max_ms": p95_max_ms,
        "would_fail_current_sample": not within_target,
    }


def evaluate_health(events: list[dict[str, Any]], now_seconds: int) -> dict[str, Any]:
    starts = [int(event["timestamp"]) for event in events if event.get("event") == "service_start"]
    if not starts:
        return {"status": "pending", "observation_days": 0, "threshold_restarts": 0}
    restart_timestamps = [
        int(event.get("timestamp") or 0)
        for event in events
        if event.get("event") == "restart_threshold"
    ]
    last_restart = max(restart_timestamps) if restart_timestamps else None
    eligible_starts = [
        timestamp for timestamp in starts
        if last_restart is None or timestamp > last_restart
    ]
    observation_start = min(eligible_starts) if eligible_starts else max(starts)
    restarts_in_window = [
        timestamp for timestamp in restart_timestamps
        if timestamp >= observation_start
    ]
    observation_days = max(0.0, (now_seconds - observation_start) / 86400)
    if restarts_in_window:
        status = "fail"
    elif observation_days >= 7:
        status = "pass"
    else:
        status = "pending"
    return {
        "status": status,
        "observation_start": observation_start,
        "observation_days": round(observation_days, 3),
        "required_days": 7,
        "threshold_restarts": len(restarts_in_window),
        "historical_threshold_restarts": len(restart_timestamps),
        "last_threshold_restart": last_restart,
        "health_ok_heartbeats": sum(event.get("event") == "health_ok" for event in events),
    }


def health_observation_start(events: list[dict[str, Any]]) -> int | None:
    starts = [int(event["timestamp"]) for event in events if event.get("event") == "service_start"]
    if not starts:
        return None
    restart_timestamps = [
        int(event.get("timestamp") or 0)
        for event in events
        if event.get("event") == "restart_threshold"
    ]
    last_restart = max(restart_timestamps) if restart_timestamps else None
    eligible_starts = [
        timestamp for timestamp in starts
        if last_restart is None or timestamp > last_restart
    ]
    return min(eligible_starts) if eligible_starts else max(starts)


def code_fingerprint_window_start(
    events: list[dict[str, Any]],
    code_fingerprint: str | None = None,
) -> int | None:
    service_starts = [
        (int(event["timestamp"]), str(event["code_fingerprint"]))
        for event in events
        if event.get("event") == "service_start" and event.get("code_fingerprint")
    ]
    if not service_starts:
        return None
    service_starts.sort()
    target_fingerprint = code_fingerprint or service_starts[-1][1]
    matching_timestamps = [
        timestamp for timestamp, fingerprint in service_starts
        if fingerprint == target_fingerprint
    ]
    if not matching_timestamps:
        return None
    latest_matching = max(matching_timestamps)
    previous_different = [
        timestamp for timestamp, fingerprint in service_starts
        if timestamp < latest_matching and fingerprint != target_fingerprint
    ]
    boundary = max(previous_different) if previous_different else -1
    return min(
        timestamp for timestamp, fingerprint in service_starts
        if timestamp > boundary and fingerprint == target_fingerprint
    )


def filter_performance_events(
    events: list[dict[str, Any]],
    *,
    since_ms: int | None = None,
) -> list[dict[str, Any]]:
    if since_ms is None:
        return events
    return [
        event for event in events
        if int(event.get("timestamp_ms") or 0) >= since_ms
    ]


def metric_counts(events: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for event in events:
        metric = event.get("metric")
        if not metric:
            continue
        counts[str(metric)] = counts.get(str(metric), 0) + 1
    return dict(sorted(counts.items()))


def _record_market_window(record: dict[str, Any]) -> str:
    slug = str(record.get("market_slug") or "")
    if re.search(r"-5m-\d{10}$", slug, re.IGNORECASE):
        return "5m"
    if re.search(r"-15m-\d{10}$", slug, re.IGNORECASE):
        return "15m"
    return "other"


def _summarize_counts(
    rows: list[tuple[str, ...]],
    *,
    limit: int,
) -> list[dict[str, Any]]:
    counts: dict[tuple[str, ...], int] = {}
    for row in rows:
        counts[row] = counts.get(row, 0) + 1
    return [
        {"keys": list(keys), "count": count}
        for keys, count in sorted(
            counts.items(),
            key=lambda item: (-item[1], item[0]),
        )[:limit]
    ]


def summarize_execution_records(
    records: list[dict[str, Any]],
    *,
    since_ms: int | None = None,
    limit: int = 12,
) -> dict[str, Any]:
    filtered = [
        record for record in records
        if since_ms is None or int(record.get("created_at") or 0) >= since_ms
    ]
    reason_rows = [
        (
            str(record.get("side") or ""),
            str(record.get("status") or ""),
            str(record.get("error_message") or "SUCCESS"),
        )
        for record in filtered
    ]
    status_rows = [
        (
            str(record.get("side") or ""),
            str(record.get("status") or ""),
        )
        for record in filtered
    ]
    window_rows = [
        (
            _record_market_window(record),
            str(record.get("side") or ""),
            str(record.get("status") or ""),
        )
        for record in filtered
    ]
    return {
        "count": len(filtered),
        "status_counts": _summarize_counts(status_rows, limit=limit),
        "market_window_counts": _summarize_counts(window_rows, limit=limit),
        "reason_counts": _summarize_counts(reason_rows, limit=limit),
    }


def _load_env_file(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_execution_records_from_db(
    *,
    since_ms: int | None,
    env_file: Path | None,
    limit: int,
) -> list[dict[str, Any]]:
    if env_file:
        _load_env_file(env_file)
    try:
        import pymysql
    except ImportError as exc:
        raise RuntimeError("pymysql is required for --include-db-records") from exc

    host = os.getenv("COPY_TRADING_DB_HOST", "127.0.0.1")
    port = int(os.getenv("COPY_TRADING_DB_PORT") or os.getenv("MYSQL_PORT") or "3307")
    user = os.getenv("COPY_TRADING_DB_USER") or os.getenv("DB_USERNAME") or "root"
    password = os.getenv("COPY_TRADING_DB_PASSWORD") or os.getenv("DB_PASSWORD") or ""
    database = os.getenv("COPY_TRADING_DB_NAME", "polyhermes")

    where = "WHERE created_at >= %s" if since_ms is not None else ""
    params = (since_ms,) if since_ms is not None else ()
    query = f"""
        SELECT id, external_trade_id, market_title, side, outcome, price, quantity,
               amount, status, error_message, raw_payload, created_at, updated_at
        FROM bridge_trade_record
        {where}
        ORDER BY id DESC
        LIMIT %s
    """
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        database=database,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
    )
    try:
        with conn.cursor() as cursor:
            cursor.execute(query, (*params, limit))
            rows = cursor.fetchall()
    finally:
        conn.close()

    records: list[dict[str, Any]] = []
    for row in rows:
        payload = {}
        try:
            payload = json.loads(row.get("raw_payload") or "{}")
        except json.JSONDecodeError:
            payload = {}
        row.pop("raw_payload", None)
        row["market_slug"] = (
            payload.get("market_slug")
            or payload.get("marketSlug")
            or payload.get("slug")
        )
        records.append(row)
    return records


def build_report(
    performance_events: list[dict[str, Any]],
    health_events: list[dict[str, Any]],
    now_seconds: int,
    *,
    since_ms: int | None = None,
    execution_records: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    filtered_performance_events = filter_performance_events(
        performance_events,
        since_ms=since_ms,
    )
    checks = {
        "webhook_accept": evaluate_latency(
            filtered_performance_events,
            "webhook_accept_ms",
            min_samples=100,
            p50_max_ms=100,
            p95_max_ms=200,
        ),
        "buy_5m": evaluate_latency(
            filtered_performance_events,
            "buy_5m_signal_to_submit_ms",
            min_samples=20,
            p50_max_ms=10000,
            p95_max_ms=20000,
        ),
        "buy_15m": evaluate_latency(
            filtered_performance_events,
            "buy_15m_signal_to_submit_ms",
            min_samples=20,
            p50_max_ms=10000,
            p95_max_ms=20000,
        ),
        "sell_5m": evaluate_latency(
            filtered_performance_events,
            "sell_5m_signal_to_submit_ms",
            min_samples=20,
            p50_max_ms=20000,
            p95_max_ms=20000,
        ),
        "sell_15m": evaluate_latency(
            filtered_performance_events,
            "sell_15m_signal_to_submit_ms",
            min_samples=20,
            p50_max_ms=20000,
            p95_max_ms=20000,
        ),
        "health_stability": evaluate_health(health_events, now_seconds),
    }
    statuses = {check["status"] for check in checks.values()}
    overall = "fail" if "fail" in statuses else "pass" if statuses == {"pass"} else "pending"
    sample_window = {
        "since_ms": since_ms,
        "performance_events_total": len(performance_events),
        "performance_events_evaluated": len(filtered_performance_events),
        "metric_counts": metric_counts(filtered_performance_events),
    }
    if execution_records is not None:
        sample_window["execution_records"] = summarize_execution_records(
            execution_records,
            since_ms=since_ms,
        )
    return {
        "status": overall,
        "sample_window": sample_window,
        "checks": checks,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    base = Path(__file__).resolve().parent
    parser.add_argument(
        "--performance-log",
        type=Path,
        default=base / "logs" / "bridge-performance.jsonl",
    )
    parser.add_argument(
        "--health-log",
        type=Path,
        default=Path("/tmp/polymtrade-health-events.jsonl"),
    )
    parser.add_argument(
        "--since-ms",
        type=int,
        default=None,
        help="Only evaluate performance events at or after this epoch millisecond.",
    )
    parser.add_argument(
        "--since-health-window",
        action="store_true",
        help="Only evaluate performance events from the current post-restart health window.",
    )
    parser.add_argument(
        "--since-latest-code-fingerprint",
        action="store_true",
        help="Only evaluate performance events from the latest loaded Bridge code fingerprint.",
    )
    parser.add_argument(
        "--include-db-records",
        action="store_true",
        help="Include a read-only bridge_trade_record status/reason summary for the sample window.",
    )
    parser.add_argument(
        "--db-env-file",
        type=Path,
        default=base.parent / ".env",
        help="Optional env file for DB connection values used by --include-db-records.",
    )
    parser.add_argument(
        "--db-record-limit",
        type=int,
        default=1000,
        help="Maximum bridge_trade_record rows to read for the execution summary.",
    )
    args = parser.parse_args()
    health_events = load_jsonl(args.health_log)
    since_ms = args.since_ms
    if args.since_health_window:
        observation_start = health_observation_start(health_events)
        if observation_start is not None:
            window_since_ms = observation_start * 1000
            since_ms = max(since_ms, window_since_ms) if since_ms is not None else window_since_ms
    if args.since_latest_code_fingerprint:
        code_start = code_fingerprint_window_start(health_events)
        if code_start is not None:
            window_since_ms = code_start * 1000
            since_ms = max(since_ms, window_since_ms) if since_ms is not None else window_since_ms
    execution_records = None
    if args.include_db_records:
        execution_records = load_execution_records_from_db(
            since_ms=since_ms,
            env_file=args.db_env_file,
            limit=args.db_record_limit,
        )
    report = build_report(
        load_jsonl(args.performance_log),
        health_events,
        int(time.time()),
        since_ms=since_ms,
        execution_records=execution_records,
    )
    print(json.dumps(report, ensure_ascii=True, indent=2, sort_keys=True))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    raise SystemExit(main())
