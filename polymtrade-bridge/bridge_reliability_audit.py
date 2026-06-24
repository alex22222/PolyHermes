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
import unicodedata
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


FAILURE_BUCKET_PRIORITY = {
    "select_outcome": 100,
    "buy_dialog_open": 95,
    "amount_input": 90,
    "sell_dialog_open": 88,
    "click_submit": 85,
    "sell_post_submit_no_effect": 82,
    "target_market_missing": 80,
    "target_event_url_missing": 75,
    "executor_js_error": 70,
    "navigation_race": 60,
    "navigation_network": 50,
    "resolve_event": 45,
    "network_or_token_modal": 40,
    "live_position_insufficient": 20,
    "insufficient_balance": 15,
    "market_stale": 14,
    "duplicate_short_cycle_buy": 14,
    "read_only_account": 12,
    "insufficient_position": 10,
    "test_or_incomplete_record": 2,
    "other": 1,
}


FAILURE_BUCKET_ACTIONABILITY = {
    "select_outcome": "code_selector",
    "buy_dialog_open": "code_selector",
    "amount_input": "code_selector",
    "sell_dialog_open": "code_selector",
    "click_submit": "code_selector",
    "sell_post_submit_no_effect": "sell_verification",
    "target_market_missing": "code_navigation",
    "target_event_url_missing": "code_navigation",
    "executor_js_error": "code_selector",
    "navigation_race": "code_navigation",
    "navigation_network": "infra_retry",
    "resolve_event": "data_resolution",
    "network_or_token_modal": "account_setup_or_modal",
    "live_position_insufficient": "state_or_risk",
    "insufficient_balance": "state_or_risk",
    "market_stale": "state_or_risk",
    "duplicate_short_cycle_buy": "state_or_risk",
    "read_only_account": "account_setup_or_config",
    "insufficient_position": "state_or_risk",
    "test_or_incomplete_record": "historical_test_data",
    "other": "needs_triage",
}


FAILURE_BUCKET_NEXT_ACTION = {
    "select_outcome": "Add/extend selector fixture for the market shape, then improve outcome row matching.",
    "buy_dialog_open": "Inspect outcome click result and strengthen buy form detection/opening.",
    "amount_input": "Inspect screenshot/DOM and extend trade input detection.",
    "sell_dialog_open": "Inspect sell position card matching and strengthen sell dialog opening.",
    "click_submit": "Inspect dialog screenshot/DOM and extend submit button detection.",
    "sell_post_submit_no_effect": "Inspect SELL submit/verification flow; add retry or reconcile live portfolio delay.",
    "target_market_missing": "Improve target event visibility/navigation fallback and add market fixture.",
    "target_event_url_missing": "Remove URL-only gating or add content-based fallback for this event shape.",
    "executor_js_error": "Inspect executor JavaScript exception and add regression coverage for the affected selector path.",
    "navigation_race": "Wrap page evaluation around navigation retry and page-ready checks.",
    "navigation_network": "Treat as transient network failure; add retry/backoff if recurring.",
    "resolve_event": "Improve Gamma/CLOB slug and conditionId event resolution.",
    "network_or_token_modal": "Improve modal handling or account default network/token setup.",
    "live_position_insufficient": "Verify ledger/live portfolio drift; do not retry UI sell without real position.",
    "insufficient_balance": "Fund account or lower copy amount; not a browser reliability bug.",
    "market_stale": "Expected skip for short-cycle markets that are already closed or too close to close.",
    "duplicate_short_cycle_buy": "Expected skip: only the first BUY is copied for the same leader and BTC 5M market.",
    "read_only_account": "Enable a writable Bridge account or disable live trading for this account; not a browser reliability bug.",
    "insufficient_position": "Expected risk skip unless ledger drift is suspected.",
    "test_or_incomplete_record": "Historical/manual test or incomplete metadata; exclude from code-fix queue.",
    "other": "Inspect the raw error and add a new classifier when repeated.",
}


FIXTURE_COVERAGE_RULES = [
    {
        "bucket": "select_outcome",
        "match": ["abelardo de la espriella", "colombian presidential election"],
        "coverage_level": "exact",
        "coverage_id": "political_candidate_selector_fixture",
        "note": "Covered by POLITICAL_CANDIDATE_HTML selector fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["netherlands", "group f", "fifa world cup"],
        "coverage_level": "exact",
        "coverage_id": "world_cup_group_selector_fixture",
        "note": "Covered by WORLD_CUP_GROUP_HTML categorical row fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["uruguay", "group h", "fifa world cup"],
        "coverage_level": "exact",
        "coverage_id": "world_cup_group_multi_country_fixture",
        "note": "Covered by WORLD_CUP_GROUP_MULTI_COUNTRY_HTML fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["ecuador", "group e", "fifa world cup"],
        "coverage_level": "exact",
        "coverage_id": "world_cup_group_multi_country_fixture",
        "note": "Covered by WORLD_CUP_GROUP_MULTI_COUNTRY_HTML fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["germany", "group e", "fifa world cup"],
        "coverage_level": "exact",
        "coverage_id": "world_cup_group_multi_country_fixture",
        "note": "Covered by WORLD_CUP_GROUP_MULTI_COUNTRY_HTML fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["belgium", "group g", "fifa world cup"],
        "coverage_level": "exact",
        "coverage_id": "world_cup_group_multi_country_fixture",
        "note": "Covered by WORLD_CUP_GROUP_MULTI_COUNTRY_HTML fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["spain", "group h", "fifa world cup"],
        "coverage_level": "exact",
        "coverage_id": "world_cup_group_multi_country_fixture",
        "note": "Covered by WORLD_CUP_GROUP_MULTI_COUNTRY_HTML fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["haiti", "will haiti win"],
        "coverage_level": "exact",
        "coverage_id": "world_cup_remaining_country_fixture",
        "note": "Covered by WORLD_CUP_REMAINING_COUNTRY_HTML fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["curacao", "group e", "fifa world cup"],
        "coverage_level": "exact",
        "coverage_id": "world_cup_remaining_country_fixture",
        "note": "Covered by WORLD_CUP_REMAINING_COUNTRY_HTML fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["cape verde", "fifa world cup final"],
        "coverage_level": "exact",
        "coverage_id": "world_cup_remaining_country_fixture",
        "note": "Covered by WORLD_CUP_REMAINING_COUNTRY_HTML fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["scotland", "group c", "fifa world cup"],
        "coverage_level": "exact",
        "coverage_id": "world_cup_remaining_country_fixture",
        "note": "Covered by WORLD_CUP_REMAINING_COUNTRY_HTML fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["usa", "fifa world cup final"],
        "coverage_level": "exact",
        "coverage_id": "world_cup_remaining_country_fixture",
        "note": "Covered by WORLD_CUP_REMAINING_COUNTRY_HTML fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["usa", "group d", "fifa world cup"],
        "coverage_level": "exact",
        "coverage_id": "world_cup_select_outcome_cleanup_fixture",
        "note": "Covered by USA Group D selector fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["mexico", "fifa world cup final"],
        "coverage_level": "exact",
        "coverage_id": "world_cup_select_outcome_cleanup_fixture",
        "note": "Covered by Mexico final selector fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["argentina", "fifa world cup final"],
        "coverage_level": "exact",
        "coverage_id": "world_cup_select_outcome_cleanup_fixture",
        "note": "Covered by Argentina final selector fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["toronto tempo", "connecticut sun"],
        "coverage_level": "exact",
        "coverage_id": "wnba_binary_selector_fixture",
        "note": "Covered by WNBA binary outcome fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["bitcoin up or down"],
        "coverage_level": "exact",
        "coverage_id": "btc_updown_binary_portfolio_fixture",
        "note": "Covered by BTC Up/Down binary button and portfolio-row visibility fixtures.",
    },
    {
        "bucket": "buy_dialog_open",
        "match": ["bitcoin up or down"],
        "coverage_level": "exact",
        "coverage_id": "btc_updown_binary_buy_dialog_fixture",
        "note": "Covered by BTC Up/Down binary button selection and BUY dialog-open guard fixtures.",
    },
    {
        "bucket": "select_outcome",
        "match": ["team spirit", "iem cologne major"],
        "coverage_level": "exact",
        "coverage_id": "esports_team_selector_fixture",
        "note": "Covered by ESPORTS_TEAM_HTML selector fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["vitality", "team falcons", "iem cologne major playoffs"],
        "coverage_level": "exact",
        "coverage_id": "esports_match_team_selector_fixture",
        "note": "Covered by ESPORTS_MATCH_MARKET_HTML fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["vitality", "team falcons", "map 1 winner"],
        "coverage_level": "exact",
        "coverage_id": "esports_match_team_selector_fixture",
        "note": "Covered by ESPORTS_MATCH_MARKET_HTML fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["spirit", "g2", "iem cologne major playoffs"],
        "coverage_level": "exact",
        "coverage_id": "esports_match_team_selector_fixture",
        "note": "Covered by ESPORTS_MATCH_MARKET_HTML fixture.",
    },
    {
        "bucket": "select_outcome",
        "match": ["map handicap", "team falcons"],
        "coverage_level": "exact",
        "coverage_id": "esports_match_team_selector_fixture",
        "note": "Covered by ESPORTS_MATCH_MARKET_HTML fixture.",
    },
    {
        "bucket": "amount_input",
        "record_ids": [598, 569, 567, 565, 564, 558, 508, 501, 494, 481, 458, 358, 355, 246],
        "coverage_level": "exact",
        "coverage_id": "buy_dialog_open_guard_fixture",
        "note": "Historical screenshots show portfolio/event page without an open BUY dialog; covered by BUY dialog-open guard.",
    },
    {
        "bucket": "amount_input",
        "match": ["could not enter trade amount"],
        "coverage_level": "partial",
        "coverage_id": "custom_amount_input_fixture",
        "note": "Partially covered by contenteditable, Chinese aria-label, and custom role=spinbutton amount input fixtures.",
    },
    {
        "bucket": "buy_dialog_open",
        "match": ["could not open buy dialog"],
        "coverage_level": "partial",
        "coverage_id": "buy_dialog_open_guard_fixture",
        "note": "Partially covered by portfolio false-positive guard fixture.",
    },
    {
        "bucket": "sell_dialog_open",
        "match": ["ludvig aberg", "could not open sell dialog", "sellbuttons=0"],
        "coverage_level": "exact",
        "coverage_id": "live_sell_position_precheck",
        "note": "Covered by live portfolio SELL precheck before UI sell.",
    },
    {
        "bucket": "click_submit",
        "record_ids": [597],
        "coverage_level": "exact",
        "coverage_id": "robust_sell_submit_button_fixtures",
        "note": "Historical SELL submit sample from before submit hardening; covered by delayed, attribute-only, and icon-only sell submit fixtures.",
    },
    {
        "bucket": "click_submit",
        "match": ["could not click sell button"],
        "coverage_level": "partial",
        "coverage_id": "robust_sell_submit_button_fixtures",
        "note": "Partially covered by delayed, attribute-only, and icon-only sell submit fixtures.",
    },
    {
        "bucket": "navigation_race",
        "record_ids": [581, 547, 472, 350],
        "coverage_level": "exact",
        "coverage_id": "evaluate_navigation_retry_fixture",
        "note": "Historical Page.evaluate context-loss samples covered by evaluate navigation retry fixtures.",
    },
    {
        "bucket": "navigation_race",
        "record_ids": [450],
        "coverage_level": "exact",
        "coverage_id": "goto_interrupted_navigation_retry_fixture",
        "note": "Historical page.goto interrupted-by-portfolio sample covered by goto navigation retry fixtures.",
    },
    {
        "bucket": "navigation_race",
        "match": ["bitcoin up or down", "execution context was destroyed"],
        "coverage_level": "exact",
        "coverage_id": "post_submit_navigation_race_fixture",
        "note": "Covered by serializing portfolio scrapes with trades and treating post-submit navigation context loss as submitted.",
    },
    {
        "bucket": "navigation_race",
        "record_ids": [861],
        "coverage_level": "exact",
        "coverage_id": "shutdown_trade_lock_guard",
        "note": "Historical restart-window trade covered by taking the trade lock before executor shutdown.",
    },
    {
        "bucket": "target_market_missing",
        "record_ids": [865],
        "coverage_level": "exact",
        "coverage_id": "short_cycle_market_stale_guard",
        "note": "Historical BTC 5M market expired while queued; covered by pre-UI short-cycle stale skip guard.",
    },
    {
        "bucket": "navigation_network",
        "record_ids": [559, 542, 473, 439, 372, 365, 235],
        "coverage_level": "exact",
        "coverage_id": "goto_network_retry_fixture",
        "note": "Historical ERR_ABORTED page.goto samples covered by goto network retry fixtures.",
    },
    {
        "bucket": "target_event_url_missing",
        "match": ["abelardo de la espriella", "target event"],
        "coverage_level": "exact",
        "coverage_id": "content_based_event_visibility_fixture",
        "note": "Covered by content-based event visibility/navigation fallback tests.",
    },
    {
        "bucket": "target_market_missing",
        "match": ["abelardo de la espriella", "target market content"],
        "coverage_level": "exact",
        "coverage_id": "content_based_event_visibility_fixture",
        "note": "Covered by content-based target market visibility tests.",
    },
]


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


def classify_failure(error_message: Any) -> str:
    text = normalize_text(error_message)
    if not text:
        return "other"
    if "could not select outcome" in text:
        return "select_outcome"
    if "could not open buy dialog" in text:
        return "buy_dialog_open"
    if "enter trade amount" in text or "amount input" in text:
        return "amount_input"
    if "could not open sell dialog" in text or "sell dialog disappeared before submit" in text:
        return "sell_dialog_open"
    if "sell post-submit verification failed" in text or "sell verification could not confirm" in text:
        return "sell_post_submit_no_effect"
    if "could not click sell button" in text or "could not click buy button" in text:
        return "click_submit"
    if "target market content never appeared" in text:
        return "target_market_missing"
    if "target event" in text and "url never appeared" in text:
        return "target_event_url_missing"
    if (
        "execution context was destroyed" in text
        or "target page, context or browser has been closed" in text
        or "navigation race persisted" in text
        or "page closed during navigation retry" in text
        or "interrupted by another navigation" in text
    ):
        return "navigation_race"
    if "referenceerror" in text or "is not defined" in text and "page.evaluate" in text:
        return "executor_js_error"
    if "net::" in text or "err_connection" in text or ("timeout" in text and "goto" in text):
        return "navigation_network"
    if "could not resolve polymtrade event" in text or "resolve event" in text:
        return "resolve_event"
    if "live portfolio insufficient" in text or "no live position available" in text:
        return "live_position_insufficient"
    if (
        "insufficient balance" in text
        or "insufficient usdc balance" in text
        or "needs a deposit" in text
        or "余额不足" in text
    ):
        return "insufficient_balance"
    if "short-cycle market stale" in text or "market stale or closing soon" in text:
        return "market_stale"
    if "duplicate short-cycle market buy skipped" in text:
        return "duplicate_short_cycle_buy"
    if ("network" in text and "modal" in text) or "deposit modal" in text or ("token" in text and "modal" in text):
        return "network_or_token_modal"
    if "read-only account" in text or "read only account" in text or "does not support buy orders" in text:
        return "read_only_account"
    if "insufficient position" in text:
        return "insufficient_position"
    return "other"


def classify_failure_row(row: dict[str, Any]) -> str:
    """Classify a failed bridge row, using metadata when the raw error is ambiguous."""
    bucket = classify_failure(row.get("error_message") or row.get("errorMessage"))
    if bucket in {
        "select_outcome",
        "amount_input",
        "buy_dialog_open",
        "click_submit",
        "executor_js_error",
        "navigation_race",
        "navigation_network",
        "target_market_missing",
        "target_event_url_missing",
        "sell_post_submit_no_effect",
        "live_position_insufficient",
    }:
        title = normalize_text(row.get("market_title") or row.get("marketTitle"))
        external_id = normalize_text(row.get("external_trade_id") or row.get("externalTradeId"))
        amount = decimal_value(row.get("amount"))
        price = decimal_value(row.get("price"))
        quantity = decimal_value(row.get("quantity"))
        if not title:
            return "test_or_incomplete_record"
        if bucket in {"amount_input", "buy_dialog_open", "click_submit"} and (amount <= 0 or quantity <= 0):
            return "test_or_incomplete_record"
        if bucket in {"navigation_race", "navigation_network"} and external_id.startswith("manual-") and (
            amount <= 0 or price <= 0
        ):
            return "test_or_incomplete_record"
        if bucket in {"sell_post_submit_no_effect", "live_position_insufficient"} and external_id.startswith(
            "manual-"
        ) and (amount <= 0 or price <= 0):
            return "test_or_incomplete_record"
        if "test" in title and (amount <= 0 or quantity <= 0 or external_id.startswith("manual-")):
            return "test_or_incomplete_record"
    return bucket


def failure_coverage_hint(row: dict[str, Any]) -> dict[str, Any]:
    bucket = row.get("failure_bucket") or classify_failure_row(row)
    haystack = " ".join(
        str(row.get(key) or "")
        for key in ("market_title", "marketTitle", "error_message", "errorMessage", "outcome")
    ).lower()
    haystack = unicodedata.normalize("NFKD", haystack)
    haystack = "".join(c for c in haystack if not unicodedata.combining(c))
    for rule in FIXTURE_COVERAGE_RULES:
        if rule["bucket"] != bucket:
            continue
        record_ids = rule.get("record_ids")
        if record_ids is not None and row.get("id") not in record_ids:
            continue
        match = rule.get("match")
        if record_ids is not None or all(part in haystack for part in match):
            coverage_level = rule.get("coverage_level", "exact")
            return {
                "covered": coverage_level == "exact",
                "coverage_level": coverage_level,
                "coverage_id": rule["coverage_id"],
                "note": rule["note"],
            }
    return {
        "covered": False,
        "coverage_level": "none",
        "coverage_id": None,
        "note": "No explicit regression fixture coverage matched this historical failure.",
    }


def failure_bucket_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for row in rows:
        bucket = classify_failure_row(row)
        coverage = failure_coverage_hint({**row, "failure_bucket": bucket})
        item = buckets.setdefault(
            bucket,
            {
                "bucket": bucket,
                "count": 0,
                "covered_count": 0,
                "uncovered_count": 0,
                "priority": FAILURE_BUCKET_PRIORITY.get(bucket, 1),
                "actionability": FAILURE_BUCKET_ACTIONABILITY.get(bucket, "needs_triage"),
                "next_action": FAILURE_BUCKET_NEXT_ACTION.get(bucket, FAILURE_BUCKET_NEXT_ACTION["other"]),
                "sample_record_ids": [],
                "sample_markets": [],
                "uncovered_sample_record_ids": [],
                "uncovered_sample_markets": [],
                "coverage_ids": [],
                "latest_created_at": None,
            },
        )
        item["count"] += 1
        coverage_id = coverage.get("coverage_id")
        if coverage_id and coverage_id not in item["coverage_ids"]:
            item["coverage_ids"].append(coverage_id)
        if coverage.get("covered"):
            item["covered_count"] += 1
        else:
            item["uncovered_count"] += 1
            if len(item["uncovered_sample_record_ids"]) < 5:
                item["uncovered_sample_record_ids"].append(row.get("id"))
            market_title = row.get("market_title") or row.get("marketTitle")
            if (
                market_title
                and len(item["uncovered_sample_markets"]) < 5
                and market_title not in item["uncovered_sample_markets"]
            ):
                item["uncovered_sample_markets"].append(market_title)
        if len(item["sample_record_ids"]) < 5:
            item["sample_record_ids"].append(row.get("id"))
        market_title = row.get("market_title") or row.get("marketTitle")
        if market_title and len(item["sample_markets"]) < 5 and market_title not in item["sample_markets"]:
            item["sample_markets"].append(market_title)
        created_at = row.get("created_at") or row.get("createdAt")
        if created_at is not None and (
            item["latest_created_at"] is None or int(created_at) > int(item["latest_created_at"])
        ):
            item["latest_created_at"] = int(created_at)

    return sorted(
        buckets.values(),
        key=lambda item: (-item["count"], -item["priority"], -(item["latest_created_at"] or 0), item["bucket"]),
    )


def actionable_failure_buckets(summary: list[dict[str, Any]], limit: int = 5) -> list[dict[str, Any]]:
    return [
        item
        for item in sorted(
            summary,
            key=lambda row: (
                -row["priority"],
                -row.get("uncovered_count", row["count"]),
                -row["count"],
                -(row["latest_created_at"] or 0),
                row["bucket"],
            ),
        )
        if row_is_actionable(item)
    ][:limit]


def row_is_actionable(item: dict[str, Any]) -> bool:
    if item.get("count", 0) > 0 and item.get("uncovered_count", item.get("count", 0)) <= 0:
        return False
    return item.get("actionability") in {
        "code_selector",
        "code_navigation",
        "infra_retry",
        "data_resolution",
        "needs_triage",
    }


def latest_record_time_ms(rows: list[dict[str, Any]]) -> int | None:
    timestamps = [
        int(value)
        for row in rows
        for value in (row.get("updated_at"), row.get("created_at"))
        if value is not None
    ]
    return max(timestamps) if timestamps else None


def filter_records_since(records: list[dict[str, Any]], since_ms: int | None) -> list[dict[str, Any]]:
    """Filter recent audit rows by created/updated time without affecting ledger checks."""
    if since_ms is None or since_ms <= 0:
        return records
    filtered = []
    for row in records:
        timestamps = [
            int(value)
            for value in (
                row.get("created_at"),
                row.get("createdAt"),
                row.get("updated_at"),
                row.get("updatedAt"),
            )
            if value is not None
        ]
        if timestamps and max(timestamps) >= since_ms:
            filtered.append(row)
    return filtered


def build_monitor_status(metrics: dict[str, Any], next_action_candidates: list[dict[str, Any]]) -> dict[str, Any]:
    """Build a compact status object for post-fix audit loops and dashboards."""
    actionable_failure_count = int(metrics.get("actionable_failure_bucket_count") or len(next_action_candidates))
    records_checked = int(metrics.get("records_checked") or 0)
    recent_failure_count = int(metrics.get("recent_failure_count") or 0)
    pending_timeout_count = int(metrics.get("pending_timeout_count") or 0)
    active_mismatch_count = int(metrics.get("active_success_position_mismatch_count") or 0)
    actionable_issue_count = strict_actionable_issue_count(
        {
            **metrics,
            "actionable_failure_bucket_count": actionable_failure_count,
            "pending_timeout_count": pending_timeout_count,
            "active_success_position_mismatch_count": active_mismatch_count,
        }
    )

    if actionable_issue_count > 0:
        status = "actionable"
        message = "Actionable Bridge failures need investigation."
    elif records_checked <= 0:
        status = "no_recent_records"
        message = "No PENDING/FAILED records in the selected audit window."
    else:
        status = "clear"
        message = "No actionable Bridge failures in the selected audit window."

    return {
        "status": status,
        "message": message,
        "actionable_failure_bucket_count": actionable_failure_count,
        "actionable_issue_count": actionable_issue_count,
        "pending_timeout_count": pending_timeout_count,
        "recent_failure_count": recent_failure_count,
        "active_success_position_mismatch_count": active_mismatch_count,
        "latest_raw_record_time_ms": metrics.get("latest_raw_record_time_ms"),
        "latest_record_time_ms": metrics.get("latest_record_time_ms"),
        "latest_failure_time_ms": metrics.get("latest_failure_time_ms"),
        "since_ms": metrics.get("since_ms"),
        "next_action_buckets": [item.get("bucket") for item in next_action_candidates],
    }


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


def build_success_mismatch_metric_counts(
    total: int,
    fresh: int,
    stale: int,
    reconciled: int,
) -> dict[str, int]:
    """Return success-position mismatch metrics with fresh-only active semantics.

    Stale mismatches are useful reconciliation evidence, but they usually mean
    a historical/manual close is possible. They should not keep the post-fix
    loop in an actionable state unless a fresh SUCCESS row is missing from the
    live portfolio.
    """
    return {
        "success_position_mismatch_count": total,
        "active_success_position_mismatch_count": fresh,
        "fresh_success_position_mismatch_count": fresh,
        "stale_success_position_mismatch_count": stale,
        "reconciled_success_position_mismatch_count": reconciled,
        "unresolved_success_position_mismatch_count": fresh + stale,
    }


def strict_actionable_issue_count(metrics: dict[str, Any]) -> int:
    """Count only issues that should make strict audit fail."""
    return (
        int(metrics.get("pending_timeout_count") or 0)
        + int(metrics.get("actionable_failure_bucket_count") or 0)
        + int(metrics.get("active_success_position_mismatch_count") or 0)
    )


def build_reconciliation_suggestions(
    success_position_mismatches: list[dict[str, Any]],
    *,
    limit: int = 20,
) -> list[dict[str, Any]]:
    """Suggest safe operator annotations for stale, unreconciled mismatches.

    The suggestions are intentionally read-only. They give the UI or operator
    enough data to POST an annotation later, but audit never writes
    reconciliation files by itself.
    """
    suggestions: list[dict[str, Any]] = []
    for item in success_position_mismatches:
        if len(suggestions) >= limit:
            break
        if item.get("is_reconciled") or not item.get("is_stale"):
            continue
        if item.get("bucket") != "stale_success_position_mismatch":
            continue

        actual_qty = decimal_value(item.get("actual_quantity"))
        expected_qty = decimal_value(item.get("expected_quantity"))
        confidence = "high" if actual_qty <= Decimal("0") else "medium"
        status = "accepted_stale"
        note = (
            "Live portfolio no longer shows the expected position; likely "
            "historical/manual/external close. Verify before accepting."
        )
        if actual_qty > Decimal("0") and expected_qty > Decimal("0"):
            note = (
                "Live portfolio has less than the expected ledger quantity; "
                "likely partial external/manual close. Verify before accepting."
            )

        suggestions.append(
            {
                "key": item.get("reconciliation_key"),
                "status": status,
                "confidence": confidence,
                "reason": "stale_success_position_missing_from_live_portfolio",
                "market_id": item.get("market_id"),
                "market_title": item.get("market_title"),
                "outcome": item.get("outcome"),
                "outcome_index": item.get("outcome_index"),
                "expected_quantity": item.get("expected_quantity"),
                "actual_quantity": item.get("actual_quantity"),
                "latest_record_id": item.get("latest_record_id"),
                "latest_record_updated_at": item.get("latest_record_updated_at"),
                "age_ms": item.get("age_ms"),
                "contributing_record_ids": item.get("contributing_record_ids") or [],
                "annotation_payload": {
                    "status": status,
                    "note": note,
                    "actor": "audit_suggestion",
                    "market_id": item.get("market_id"),
                    "market_title": item.get("market_title"),
                    "outcome": item.get("outcome"),
                    "outcome_index": item.get("outcome_index"),
                },
            }
        )
    return suggestions


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
    raw_records = fetch_records(config, args.limit)
    since_ms = getattr(args, "since_ms", None)
    records = filter_records_since(raw_records, since_ms)
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
            item = record_summary(row)
            bucket = classify_failure_row(item)
            item["failure_bucket"] = bucket
            item["failure_actionability"] = FAILURE_BUCKET_ACTIONABILITY.get(bucket, "needs_triage")
            item["failure_next_action"] = FAILURE_BUCKET_NEXT_ACTION.get(bucket, FAILURE_BUCKET_NEXT_ACTION["other"])
            item["coverage_hint"] = failure_coverage_hint(item)
            recent_failures.append(item)

    failure_buckets = failure_bucket_summary(recent_failures)
    next_action_candidates = actionable_failure_buckets(failure_buckets)

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

    reconciliation_suggestions = build_reconciliation_suggestions(
        success_position_mismatches,
        limit=args.reconciliation_suggestion_limit,
    )

    metrics = {
        "records_checked": len(records),
        "raw_records_checked": len(raw_records),
        "since_ms": since_ms,
        "latest_raw_record_time_ms": latest_record_time_ms(raw_records),
        "latest_record_time_ms": latest_record_time_ms(records),
        "latest_failure_time_ms": latest_record_time_ms(recent_failures),
        "success_ledger_rows_checked": len(success_rows),
        "portfolio_position_count": len(positions),
        "pending_timeout_count": len(pending_timeouts),
        **build_success_mismatch_metric_counts(
            total=len(success_position_mismatches),
            fresh=fresh_success_position_mismatches,
            stale=stale_success_position_mismatches,
            reconciled=reconciled_success_position_mismatches,
        ),
        "unexpected_portfolio_position_count": len(unexpected_portfolio_positions),
        "recent_failure_count": len(recent_failures),
        "failure_bucket_count": len(failure_buckets),
        "actionable_failure_bucket_count": len(next_action_candidates),
        "reconciliation_suggestion_count": len(reconciliation_suggestions),
    }

    return {
        "bridge_id": config.bridge_id,
        "portfolio_url": args.portfolio_url,
        "synced_at": portfolio_payload.get("synced_at"),
        "metrics": metrics,
        "monitor_status": build_monitor_status(metrics, next_action_candidates),
        "failure_buckets": failure_buckets,
        "next_action_candidates": next_action_candidates,
        "pending_timeouts": pending_timeouts,
        "success_position_mismatches": success_position_mismatches,
        "reconciliation_suggestions": reconciliation_suggestions,
        "unexpected_portfolio_positions": unexpected_portfolio_positions,
        "recent_failures": recent_failures[: args.failure_limit],
        "portfolio_positions": portfolio_position_summaries,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit Bridge records against live portfolio.")
    parser.add_argument("--limit", type=int, default=100, help="recent records to inspect")
    parser.add_argument(
        "--since-ms",
        type=int,
        default=None,
        help="only include recent PENDING/FAILED rows created or updated at/after this timestamp",
    )
    parser.add_argument("--ledger-limit", type=int, default=1000, help="SUCCESS rows used to compute expected open positions")
    parser.add_argument("--failure-limit", type=int, default=20, help="FAILED records to include in output")
    parser.add_argument("--pending-timeout-ms", type=int, default=120000, help="PENDING age threshold")
    parser.add_argument("--stale-mismatch-ms", type=int, default=1800000, help="SUCCESS mismatch age threshold for historical/stale classification")
    parser.add_argument("--reconciliation-file", default=str(reconciliation_file_path()), help="JSON file with operator reconciliation annotations")
    parser.add_argument("--reconciliation-suggestion-limit", type=int, default=20, help="stale mismatch reconciliation suggestions to include")
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
    actionable = strict_actionable_issue_count(result["metrics"])
    return 1 if args.strict and actionable else 0


if __name__ == "__main__":
    raise SystemExit(main())
