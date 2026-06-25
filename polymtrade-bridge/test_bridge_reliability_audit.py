#!/usr/bin/env python3
"""Tests for Bridge reliability audit failure bucketing."""

from bridge_reliability_audit import (
    actionable_failure_buckets,
    build_monitor_status,
    build_reconciliation_suggestions,
    build_success_mismatch_metric_counts,
    classify_failure,
    classify_failure_row,
    filter_records_since,
    failure_coverage_hint,
    failure_bucket_summary,
    latest_record_time_ms,
    strict_actionable_issue_count,
)


def test_classify_failure_messages():
    cases = {
        "Could not select outcome: Yes (['是', 'Yes'])": "select_outcome",
        "Could not open buy dialog after outcome click": "buy_dialog_open",
        "Could not enter trade amount: Page.wait_for_selector: Timeout": "amount_input",
        "Could not open sell dialog for outcome: NO": "sell_dialog_open",
        "Sell dialog disappeared before submit": "sell_dialog_open",
        "SELL post-submit verification failed: live portfolio quantity did not decrease": "sell_post_submit_no_effect",
        "Could not click sell button": "click_submit",
        "Target market content never appeared for Will Abelardo": "target_market_missing",
        "Target event 34584 URL never appeared": "target_event_url_missing",
        "Page.evaluate: Execution context was destroyed, most likely because of a navigation": "navigation_race",
        "select_outcome.evaluate: navigation race persisted after 3 attempts": "navigation_race",
        "open_sell_dialog.evaluate: page closed during navigation retry": "navigation_race",
        "Page.goto: Navigation to https://polym.trade/?eventId=1 is interrupted by another navigation to https://polym.trade/portfolio": "navigation_race",
        "Page.evaluate: ReferenceError: bestScore is not defined": "executor_js_error",
        "Page.goto: net::ERR_CONNECTION_RESET at https://polym.trade/portfolio": "navigation_network",
        "Could not resolve Polymtrade event for slug=abc": "resolve_event",
        "Network/token modal keeps blocking the trade": "network_or_token_modal",
        "Network/deposit modal keeps blocking the trade. The Bridge account probably has insufficient USDC balance or needs a deposit.": "insufficient_balance",
        "Live portfolio insufficient position, skipped": "live_position_insufficient",
        "Insufficient balance for BUY: available 0.5 USDC": "insufficient_balance",
        "Short-cycle market stale or closing soon, skipped (seconds_to_close=12.0, buffer=45s)": "market_stale",
        "Duplicate short-cycle market BUY skipped: same leader already has a PENDING/SUCCESS BUY for this BTC 5M market": "duplicate_short_cycle_buy",
        "BTC 5M high-price BUY skipped: price=0.90, max=0.65": "btc_5m_high_price_buy",
        "BTC 5M low-price BUY skipped: price=0.10, min=0.20": "btc_5m_low_price_buy",
        "BTC 5M global market BUY skipped: a PENDING/SUCCESS BUY already exists for this BTC 5M market": "btc_5m_global_buy",
        "BTC 5M daily BUY count limit skipped: count=50, max=50": "btc_5m_daily_limit_buy",
        "Bridge read-only account does not support BUY orders": "read_only_account",
        "Insufficient position, skipped": "insufficient_position",
    }
    for message, expected in cases.items():
        actual = classify_failure(message)
        assert actual == expected, f"{message!r}: expected {expected}, got {actual}"


def test_filter_records_since_uses_created_or_updated_time():
    rows = [
        {"id": 1, "created_at": 1000, "updated_at": 1000},
        {"id": 2, "created_at": 1000, "updated_at": 2500},
        {"id": 3, "created_at": 3000, "updated_at": None},
        {"id": 4, "createdAt": 3500, "updatedAt": 3600},
        {"id": 5, "created_at": None, "updated_at": None},
    ]

    filtered = filter_records_since(rows, 2500)
    assert [row["id"] for row in filtered] == [2, 3, 4], filtered
    assert filter_records_since(rows, None) == rows
    assert filter_records_since(rows, 0) == rows


def test_latest_record_time_ms_uses_created_or_updated_time():
    rows = [
        {"created_at": 1000, "updated_at": None},
        {"created_at": 2000, "updated_at": 2500},
        {"created_at": None, "updated_at": 3000},
    ]

    assert latest_record_time_ms(rows) == 3000
    assert latest_record_time_ms([]) is None


def test_build_monitor_status():
    actionable = build_monitor_status(
        {
            "records_checked": 10,
            "recent_failure_count": 2,
            "pending_timeout_count": 0,
            "actionable_failure_bucket_count": 1,
            "latest_raw_record_time_ms": 3000,
            "latest_record_time_ms": 3000,
            "latest_failure_time_ms": 2500,
            "since_ms": 1000,
        },
        [{"bucket": "amount_input"}],
    )
    assert actionable["status"] == "actionable", actionable
    assert actionable["next_action_buckets"] == ["amount_input"], actionable

    no_recent = build_monitor_status(
        {
            "records_checked": 0,
            "recent_failure_count": 0,
            "pending_timeout_count": 0,
            "actionable_failure_bucket_count": 0,
            "latest_raw_record_time_ms": 3000,
            "latest_record_time_ms": None,
            "latest_failure_time_ms": None,
            "since_ms": 4000,
        },
        [],
    )
    assert no_recent["status"] == "no_recent_records", no_recent

    clear = build_monitor_status(
        {
            "records_checked": 10,
            "recent_failure_count": 3,
            "pending_timeout_count": 0,
            "actionable_failure_bucket_count": 0,
            "latest_raw_record_time_ms": 3000,
            "latest_record_time_ms": 3000,
            "latest_failure_time_ms": 2500,
            "since_ms": None,
        },
        [],
    )
    assert clear["status"] == "clear", clear


def test_stale_success_mismatches_are_not_active_or_strict_actionable():
    counts = build_success_mismatch_metric_counts(
        total=13,
        fresh=0,
        stale=13,
        reconciled=0,
    )

    assert counts["success_position_mismatch_count"] == 13, counts
    assert counts["stale_success_position_mismatch_count"] == 13, counts
    assert counts["unresolved_success_position_mismatch_count"] == 13, counts
    assert counts["active_success_position_mismatch_count"] == 0, counts
    assert strict_actionable_issue_count(
        {
            **counts,
            "pending_timeout_count": 0,
            "actionable_failure_bucket_count": 0,
            "unexpected_portfolio_position_count": 1,
        }
    ) == 0

    status = build_monitor_status(
        {
            **counts,
            "records_checked": 0,
            "recent_failure_count": 0,
            "pending_timeout_count": 0,
            "actionable_failure_bucket_count": 0,
            "latest_raw_record_time_ms": 3000,
            "latest_record_time_ms": None,
            "latest_failure_time_ms": None,
            "since_ms": 4000,
        },
        [],
    )
    assert status["status"] == "no_recent_records", status
    assert status["actionable_issue_count"] == 0, status


def test_fresh_success_mismatch_is_active_and_strict_actionable():
    counts = build_success_mismatch_metric_counts(
        total=2,
        fresh=1,
        stale=1,
        reconciled=0,
    )

    assert counts["active_success_position_mismatch_count"] == 1, counts
    assert counts["unresolved_success_position_mismatch_count"] == 2, counts
    assert strict_actionable_issue_count(
        {
            **counts,
            "pending_timeout_count": 0,
            "actionable_failure_bucket_count": 0,
        }
    ) == 1

    status = build_monitor_status(
        {
            **counts,
            "records_checked": 0,
            "recent_failure_count": 0,
            "pending_timeout_count": 0,
            "actionable_failure_bucket_count": 0,
            "latest_raw_record_time_ms": 3000,
            "latest_record_time_ms": None,
            "latest_failure_time_ms": None,
            "since_ms": 4000,
        },
        [],
    )
    assert status["status"] == "actionable", status
    assert status["active_success_position_mismatch_count"] == 1, status
    assert status["actionable_issue_count"] == 1, status


def test_reconciliation_suggestions_only_include_unreconciled_stale_mismatches():
    stale = {
        "bucket": "stale_success_position_mismatch",
        "market_id": "0xabc",
        "market_title": "will example resolve?",
        "outcome": "no",
        "outcome_index": 1,
        "reconciliation_key": "polymtrade-bridge|0xabc|will example resolve?|no|1",
        "expected_quantity": "2.5",
        "actual_quantity": "0",
        "latest_record_id": 10,
        "latest_record_updated_at": 1000,
        "age_ms": 3600000,
        "is_stale": True,
        "is_reconciled": False,
        "contributing_record_ids": [8, 10],
    }
    fresh = {
        **stale,
        "bucket": "success_position_mismatch",
        "reconciliation_key": "fresh",
        "is_stale": False,
        "age_ms": 1000,
    }
    reconciled = {
        **stale,
        "reconciliation_key": "reconciled",
        "is_reconciled": True,
    }

    suggestions = build_reconciliation_suggestions([fresh, stale, reconciled])

    assert len(suggestions) == 1, suggestions
    suggestion = suggestions[0]
    assert suggestion["key"] == stale["reconciliation_key"], suggestion
    assert suggestion["status"] == "accepted_stale", suggestion
    assert suggestion["confidence"] == "high", suggestion
    assert suggestion["contributing_record_ids"] == [8, 10], suggestion
    assert suggestion["annotation_payload"]["status"] == "accepted_stale", suggestion
    assert suggestion["annotation_payload"]["market_id"] == "0xabc", suggestion
    assert suggestion["annotation_payload"]["actor"] == "audit_suggestion", suggestion


def test_reconciliation_suggestions_mark_partial_stale_as_medium_confidence():
    suggestions = build_reconciliation_suggestions(
        [
            {
                "bucket": "stale_success_position_mismatch",
                "market_id": "0xpartial",
                "market_title": "will partial remain?",
                "outcome": "yes",
                "outcome_index": 0,
                "reconciliation_key": "partial-key",
                "expected_quantity": "10",
                "actual_quantity": "3",
                "latest_record_id": 20,
                "latest_record_updated_at": 1000,
                "age_ms": 3600000,
                "is_stale": True,
                "is_reconciled": False,
            }
        ]
    )

    assert suggestions[0]["confidence"] == "medium", suggestions
    assert "less than the expected ledger quantity" in suggestions[0]["annotation_payload"]["note"]


def test_failure_bucket_summary_and_next_actions():
    rows = [
        {
            "id": 1,
            "market_title": "Will Abelardo win?",
            "error_message": "Could not select outcome: Yes",
            "created_at": 1000,
        },
        {
            "id": 2,
            "market_title": "Will Uruguay win Group H?",
            "error_message": "Could not select outcome: No",
            "created_at": 2000,
        },
        {
            "id": 3,
            "market_title": "Will Canada win?",
            "quantity": "10",
            "amount": "2.0",
            "error_message": "Could not enter trade amount: Page.wait_for_selector",
            "created_at": 3000,
        },
        {
            "id": 4,
            "market_title": "Will Argentina win?",
            "error_message": "Live portfolio insufficient position, skipped",
            "created_at": 4000,
        },
    ]

    summary = failure_bucket_summary(rows)
    assert summary[0]["bucket"] == "select_outcome", summary
    assert summary[0]["count"] == 2, summary
    assert summary[0]["sample_record_ids"] == [1, 2], summary
    assert summary[0]["actionability"] == "code_selector", summary

    candidates = actionable_failure_buckets(summary)
    candidate_buckets = [item["bucket"] for item in candidates]
    assert "select_outcome" in candidate_buckets, candidates
    assert "amount_input" in candidate_buckets, candidates
    assert "live_position_insufficient" not in candidate_buckets, candidates


def test_select_outcome_test_or_incomplete_records_are_not_actionable():
    rows = [
        {
            "id": 80,
            "market_title": None,
            "external_trade_id": "0xabc",
            "outcome": "No",
            "quantity": "2.0",
            "amount": "2.0",
            "error_message": "Could not select outcome: No",
            "created_at": 1000,
        },
        {
            "id": 81,
            "market_title": "Mbappe goal test",
            "external_trade_id": "manual-test",
            "outcome": "Yes",
            "quantity": "0",
            "amount": "0",
            "error_message": "Could not select outcome: Yes",
            "created_at": 2000,
        },
        {
            "id": 82,
            "market_title": None,
            "external_trade_id": "0xdef",
            "outcome": "No",
            "quantity": "2.0",
            "amount": "2.0",
            "error_message": "Could not enter trade amount",
            "created_at": 3000,
        },
        {
            "id": 83,
            "market_title": "Will Kylian Mbappe be the top goalscorer test",
            "external_trade_id": "manual-test",
            "outcome": "No",
            "quantity": "0",
            "amount": "0",
            "error_message": "Could not enter trade amount",
            "created_at": 4000,
        },
        {
            "id": 84,
            "market_title": None,
            "external_trade_id": "0xghi",
            "outcome": "No",
            "quantity": "2.0",
            "amount": "2.0",
            "error_message": "Page.evaluate: ReferenceError: bestScore is not defined",
            "created_at": 5000,
        },
        {
            "id": 85,
            "market_title": "Will Kylian Mbappe be the top goalscorer at the 2026 FIFA World Cup?",
            "external_trade_id": "manual-zero-amount",
            "outcome": "No",
            "quantity": "0",
            "amount": "0",
            "error_message": "Could not enter trade amount",
            "created_at": 6000,
        },
        {
            "id": 574,
            "market_title": "Will Mexico reach the 2026 FIFA World Cup final?",
            "external_trade_id": "manual-30267200-72ad-4233-982d-fac23fdd7af2",
            "outcome": "NO",
            "quantity": "2.12",
            "price": "0",
            "amount": "0",
            "error_message": "Page.query_selector: Target page, context or browser has been closed",
            "created_at": 7000,
        },
        {
            "id": 592,
            "market_title": "Will Abelardo de la Espriella win the 2026 Colombian presidential election?",
            "external_trade_id": "manual-c0c4792a-3017-4240-89f1-2297a5929c53",
            "outcome": "Yes",
            "quantity": "0",
            "price": "0",
            "amount": "0",
            "error_message": "Page.goto: net::ERR_CONNECTION_RESET at https://polym.trade/portfolio?eventId=34584",
            "created_at": 8000,
        },
    ]

    for row in rows:
        assert classify_failure_row(row) == "test_or_incomplete_record", row

    summary = failure_bucket_summary(rows)
    assert summary[0]["bucket"] == "test_or_incomplete_record", summary
    assert summary[0]["count"] == 8, summary
    assert actionable_failure_buckets(summary) == [], summary


def test_navigation_race_historical_records_are_exact_covered():
    rows = [
        {
            "id": 581,
            "market_title": "Will Abelardo de la Espriella  win the 2026 Colombian presidential election?",
            "outcome": "Yes",
            "quantity": "2.01612903",
            "amount": "2.0",
            "error_message": "Page.evaluate: Execution context was destroyed, most likely because of a navigation",
            "created_at": 4000,
        },
        {
            "id": 547,
            "market_title": "Will Netherlands win Group F in the 2026 FIFA World Cup?",
            "outcome": "No",
            "quantity": "3.57142850",
            "amount": "2.0",
            "error_message": "Page.evaluate: Execution context was destroyed, most likely because of a navigation",
            "created_at": 3000,
        },
        {
            "id": 472,
            "market_title": "Will Mexico reach the 2026 FIFA World Cup final?",
            "outcome": "No",
            "quantity": "2.13447171",
            "amount": "2.0",
            "error_message": "Page.evaluate: Execution context was destroyed, most likely because of a navigation",
            "created_at": 2000,
        },
        {
            "id": 350,
            "market_title": "Will USA win Group D in the 2026 FIFA World Cup?",
            "outcome": "No",
            "quantity": "6.66666667",
            "amount": "2.0",
            "error_message": "Page.evaluate: Execution context was destroyed, most likely because of a navigation",
            "created_at": 1000,
        },
        {
            "id": 450,
            "market_title": "Counter-Strike: Vitality vs Team Falcons (BO3) - IEM Cologne Major Playoffs",
            "outcome": "Vitality",
            "quantity": "2.98507431",
            "amount": "2.0",
            "error_message": 'Page.goto: Navigation to "https://polym.trade/?eventId=598793" is interrupted by another navigation to "https://polym.trade/portfolio"',
            "created_at": 1500,
        },
    ]

    for row in rows:
        hint = failure_coverage_hint(row)
        assert hint["covered"] is True, (row, hint)
        assert hint["coverage_id"] in {
            "evaluate_navigation_retry_fixture",
            "goto_interrupted_navigation_retry_fixture",
        }, (row, hint)

    summary = failure_bucket_summary(rows)
    assert summary[0]["bucket"] == "navigation_race", summary
    assert summary[0]["covered_count"] == 5, summary
    assert summary[0]["uncovered_count"] == 0, summary
    assert set(summary[0]["coverage_ids"]) == {
        "evaluate_navigation_retry_fixture",
        "goto_interrupted_navigation_retry_fixture",
    }, summary
    assert actionable_failure_buckets(summary) == [], summary


def test_navigation_network_historical_records_are_exact_covered():
    rows = [
        {
            "id": 559,
            "market_title": "Will Spain win Group H in the 2026 FIFA World Cup?",
            "outcome": "No",
            "quantity": "7.69230769",
            "amount": "2.0",
            "error_message": "Page.goto: net::ERR_ABORTED at https://polym.trade/?eventId=98287&eventSlug=world-cup-group-h-winner&eventSource=polymarket",
            "created_at": 7000,
        },
        {
            "id": 542,
            "market_title": "Will Netherlands win Group F in the 2026 FIFA World Cup?",
            "outcome": "No",
            "quantity": "2.26785636",
            "amount": "1.27",
            "error_message": "Page.goto: net::ERR_ABORTED at https://polym.trade/?eventId=98272&eventSlug=world-cup-group-f-winner&eventSource=polymarket",
            "created_at": 6000,
        },
        {
            "id": 473,
            "market_title": "Will USA reach the 2026 FIFA World Cup final?",
            "outcome": "No",
            "quantity": "2.15749730",
            "amount": "2.0",
            "error_message": "Page.goto: net::ERR_ABORTED at https://polym.trade/?eventId=414457&eventSlug=world-cup-nation-to-reach-final&eventSource=polymarket",
            "created_at": 5000,
        },
        {
            "id": 439,
            "market_title": "Counter-Strike: Vitality vs Team Falcons (BO3) - IEM Cologne Major Playoffs",
            "outcome": "Vitality",
            "quantity": "2.98507462",
            "amount": "2.0",
            "error_message": "Page.goto: net::ERR_ABORTED at https://polym.trade/?eventId=598793&eventSlug=cs2-vit-fal2-2026-06-19&eventSource=polymarket",
            "created_at": 4000,
        },
        {
            "id": 372,
            "market_title": "Counter-Strike: Vitality vs Team Falcons (BO3) - IEM Cologne Major Playoffs",
            "outcome": "Vitality",
            "quantity": "2.94117647",
            "amount": "2.0",
            "error_message": "Page.goto: net::ERR_ABORTED at https://polym.trade/?eventId=598793&eventSlug=cs2-vit-fal2-2026-06-19&eventSource=polymarket",
            "created_at": 3000,
        },
        {
            "id": 365,
            "market_title": "Will USA win Group D in the 2026 FIFA World Cup?",
            "outcome": "No",
            "quantity": "6.66666667",
            "amount": "2.0",
            "error_message": "Page.goto: net::ERR_ABORTED at https://polym.trade/?eventId=98266&eventSlug=world-cup-group-d-winner&eventSource=polymarket",
            "created_at": 2000,
        },
        {
            "id": 235,
            "market_title": "Map Handicap: VIT (-1.5) vs Team Falcons (+1.5)",
            "outcome": "Team Falcons",
            "quantity": "3.57142857",
            "amount": "2.0",
            "error_message": "Page.goto: net::ERR_ABORTED at https://polym.trade/?eventId=598793&eventSlug=cs2-vit-fal2-2026-06-19&eventSource=polymarket",
            "created_at": 1000,
        },
    ]

    for row in rows:
        hint = failure_coverage_hint(row)
        assert hint["covered"] is True, (row, hint)
        assert hint["coverage_id"] == "goto_network_retry_fixture", (row, hint)

    summary = failure_bucket_summary(rows)
    assert summary[0]["bucket"] == "navigation_network", summary
    assert summary[0]["covered_count"] == 7, summary
    assert summary[0]["uncovered_count"] == 0, summary
    assert summary[0]["coverage_ids"] == ["goto_network_retry_fixture"], summary
    assert actionable_failure_buckets(summary) == [], summary


def test_amount_input_portfolio_screenshot_records_are_exact_covered():
    rows = [
        {
            "id": 598,
            "market_title": "Will Canada win the 2026 FIFA World Cup?",
            "outcome": "Yes",
            "quantity": "500",
            "amount": "2.0",
            "error_message": "Could not enter trade amount: Page.wait_for_selector: Timeout 1500ms exceeded.",
            "created_at": 1000,
        },
        {
            "id": 569,
            "market_title": "Will Spain win Group H in the 2026 FIFA World Cup?",
            "outcome": "No",
            "quantity": "7.69",
            "amount": "2.0",
            "error_message": "Could not enter trade amount",
            "created_at": 2000,
        },
    ]

    for row in rows:
        hint = failure_coverage_hint(row)
        assert hint["covered"] is True, (row, hint)
        assert hint["coverage_id"] == "buy_dialog_open_guard_fixture", (row, hint)

    summary = failure_bucket_summary(rows)
    assert summary[0]["bucket"] == "amount_input", summary
    assert summary[0]["covered_count"] == 2, summary
    assert summary[0]["uncovered_count"] == 0, summary
    assert actionable_failure_buckets(summary) == [], summary


def test_other_samples_are_split_into_specific_buckets():
    rows = [
        {
            "id": 450,
            "market_title": "Counter-Strike: Vitality vs Team Falcons (BO3) - IEM Cologne Major Playoffs",
            "error_message": 'Page.goto: Navigation to "https://polym.trade/?eventId=598793" is interrupted by another navigation to "https://polym.trade/portfolio"',
            "created_at": 3000,
        },
        {
            "id": 183,
            "market_title": None,
            "error_message": "Bridge read-only account does not support BUY orders",
            "created_at": 2000,
        },
        {
            "id": 184,
            "market_title": "Will Canada win?",
            "error_message": "Page.evaluate: ReferenceError: bestScore is not defined",
            "created_at": 1000,
        },
    ]

    assert [classify_failure_row(row) for row in rows] == [
        "navigation_race",
        "read_only_account",
        "executor_js_error",
    ]
    summary = failure_bucket_summary(rows)
    buckets = {item["bucket"] for item in summary}
    assert buckets == {"navigation_race", "read_only_account", "executor_js_error"}, summary
    candidates = actionable_failure_buckets(summary)
    candidate_buckets = [item["bucket"] for item in candidates]
    assert "read_only_account" not in candidate_buckets, candidates


def test_failure_coverage_hints_and_uncovered_counts():
    covered = {
        "id": 10,
        "market_title": "Will Team Spirit win IEM Cologne Major 2026?",
        "outcome": "Yes",
        "error_message": "Could not select outcome: Yes",
        "created_at": 1000,
    }
    uncovered = {
        "id": 11,
        "market_title": "Will Norway win Group I in the 2026 FIFA World Cup?",
        "outcome": "No",
        "error_message": "Could not select outcome: No",
        "created_at": 2000,
    }

    hint = failure_coverage_hint(covered)
    assert hint["covered"] is True, hint
    assert hint["coverage_id"] == "esports_team_selector_fixture", hint

    summary = failure_bucket_summary([covered, uncovered])
    assert summary[0]["bucket"] == "select_outcome", summary
    assert summary[0]["covered_count"] == 1, summary
    assert summary[0]["uncovered_count"] == 1, summary
    assert summary[0]["uncovered_sample_record_ids"] == [11], summary
    assert "esports_team_selector_fixture" in summary[0]["coverage_ids"], summary

    all_covered_summary = failure_bucket_summary([covered])
    assert all_covered_summary[0]["covered_count"] == 1, all_covered_summary
    assert all_covered_summary[0]["uncovered_count"] == 0, all_covered_summary
    assert actionable_failure_buckets(all_covered_summary) == [], all_covered_summary


def test_btc_updown_select_outcome_coverage():
    row = {
        "id": 844,
        "market_title": "Bitcoin Up or Down - June 24, 7:15AM-7:20AM ET",
        "outcome": "Up",
        "error_message": "Could not select outcome: Up",
        "created_at": 1000,
    }

    hint = failure_coverage_hint(row)
    assert hint["covered"] is True, hint
    assert hint["coverage_id"] == "btc_updown_binary_portfolio_fixture", hint

    summary = failure_bucket_summary([row])
    assert summary[0]["covered_count"] == 1, summary
    assert summary[0]["uncovered_count"] == 0, summary
    assert actionable_failure_buckets(summary) == [], summary


def test_btc_updown_buy_dialog_and_navigation_race_coverage():
    rows = [
        {
            "id": 857,
            "market_title": "Bitcoin Up or Down - June 24, 7:50AM-7:55AM ET",
            "outcome": "Down",
            "quantity": "0.89552239",
            "price": "0.67",
            "amount": "0.6",
            "error_message": "Page.query_selector: Execution context was destroyed, most likely because of a navigation",
            "created_at": 1000,
        },
        {
            "id": 858,
            "market_title": "Bitcoin Up or Down - June 24, 7:50AM-7:55AM ET",
            "outcome": "Down",
            "quantity": "0.66666667",
            "price": "0.90",
            "amount": "0.6",
            "error_message": "Could not open buy dialog after outcome click",
            "created_at": 2000,
        },
    ]

    expected = {
        857: "post_submit_navigation_race_fixture",
        858: "btc_updown_binary_buy_dialog_fixture",
    }
    for row in rows:
        hint = failure_coverage_hint(row)
        assert hint["covered"] is True, (row, hint)
        assert hint["coverage_id"] == expected[row["id"]], (row, hint)

    summary = failure_bucket_summary(rows)
    assert {item["bucket"] for item in summary} == {"navigation_race", "buy_dialog_open"}, summary
    assert all(item["uncovered_count"] == 0 for item in summary), summary
    assert actionable_failure_buckets(summary) == [], summary


def test_btc_updown_restart_and_stale_market_coverage():
    rows = [
        {
            "id": 861,
            "market_title": "Bitcoin Up or Down - June 24, 7:55AM-8:00AM ET",
            "outcome": "Down",
            "quantity": "0.86956467",
            "price": "0.69000043",
            "amount": "0.6",
            "error_message": "BrowserContext.new_page: Target page, context or browser has been closed",
            "created_at": 1000,
        },
        {
            "id": 865,
            "market_title": "Bitcoin Up or Down - June 24, 8:35AM-8:40AM ET",
            "outcome": "Up",
            "quantity": "0.64516129",
            "price": "0.93",
            "amount": "0.6",
            "error_message": "Target market content never appeared for Bitcoin Up or Down - June 24, 8:35AM-8:40AM ET",
            "created_at": 2000,
        },
    ]

    expected = {
        861: "shutdown_trade_lock_guard",
        865: "short_cycle_market_stale_guard",
    }
    for row in rows:
        hint = failure_coverage_hint(row)
        assert hint["covered"] is True, (row, hint)
        assert hint["coverage_id"] == expected[row["id"]], (row, hint)

    summary = failure_bucket_summary(rows)
    assert all(item["uncovered_count"] == 0 for item in summary), summary
    assert actionable_failure_buckets(summary) == [], summary


def test_world_cup_group_multi_country_coverage():
    rows = [
        {
            "id": 20,
            "market_title": "Will Uruguay win Group H in the 2026 FIFA World Cup?",
            "outcome": "No",
            "error_message": "Could not select outcome: No",
            "created_at": 1000,
        },
        {
            "id": 21,
            "market_title": "Will Ecuador win Group E in the 2026 FIFA World Cup?",
            "outcome": "Yes",
            "error_message": "Could not select outcome: Yes",
            "created_at": 2000,
        },
        {
            "id": 22,
            "market_title": "Will Germany win Group E in the 2026 FIFA World Cup?",
            "outcome": "No",
            "error_message": "Could not select outcome: No",
            "created_at": 3000,
        },
        {
            "id": 23,
            "market_title": "Will Belgium win Group G in the 2026 FIFA World Cup?",
            "outcome": "No",
            "error_message": "Could not select outcome: No",
            "created_at": 4000,
        },
        {
            "id": 24,
            "market_title": "Will Spain win Group H in the 2026 FIFA World Cup?",
            "outcome": "No",
            "error_message": "Could not select outcome: No",
            "created_at": 5000,
        },
    ]

    for row in rows:
        hint = failure_coverage_hint(row)
        assert hint["covered"] is True, (row, hint)
        assert hint["coverage_id"] == "world_cup_group_multi_country_fixture", (row, hint)

    summary = failure_bucket_summary(rows)
    assert summary[0]["covered_count"] == 5, summary
    assert summary[0]["uncovered_count"] == 0, summary
    assert summary[0]["coverage_ids"] == ["world_cup_group_multi_country_fixture"], summary


def test_world_cup_remaining_country_coverage():
    rows = [
        {
            "id": 30,
            "market_title": "Will Haiti win on 2026-06-19?",
            "outcome": "No",
            "error_message": "Could not select outcome: No",
            "created_at": 1000,
        },
        {
            "id": 31,
            "market_title": "Will Curaçao win Group E in the 2026 FIFA World Cup?",
            "outcome": "No",
            "error_message": "Could not select outcome: No",
            "created_at": 2000,
        },
        {
            "id": 32,
            "market_title": "Will Cape Verde reach the 2026 FIFA World Cup final?",
            "outcome": "No",
            "error_message": "Could not select outcome: No",
            "created_at": 3000,
        },
        {
            "id": 33,
            "market_title": "Will Scotland win Group C in the 2026 FIFA World Cup?",
            "outcome": "No",
            "error_message": "Could not select outcome: No",
            "created_at": 4000,
        },
        {
            "id": 34,
            "market_title": "Will USA reach the 2026 FIFA World Cup final?",
            "outcome": "No",
            "error_message": "Could not select outcome: No",
            "created_at": 5000,
        },
    ]

    for row in rows:
        hint = failure_coverage_hint(row)
        assert hint["covered"] is True, (row, hint)
        assert hint["coverage_id"] == "world_cup_remaining_country_fixture", (row, hint)

    summary = failure_bucket_summary(rows)
    assert summary[0]["covered_count"] == 5, summary
    assert summary[0]["uncovered_count"] == 0, summary
    assert summary[0]["coverage_ids"] == ["world_cup_remaining_country_fixture"], summary


def test_esports_match_team_coverage():
    rows = [
        {
            "id": 40,
            "market_title": "Counter-Strike: Vitality vs Team Falcons (BO3) - IEM Cologne Major Playoffs",
            "outcome": "Vitality",
            "error_message": "Could not select outcome: Vitality",
            "created_at": 1000,
        },
        {
            "id": 41,
            "market_title": "Counter-Strike: Vitality vs Team Falcons - Map 1 Winner",
            "outcome": "Vitality",
            "error_message": "Could not select outcome: Vitality",
            "created_at": 2000,
        },
        {
            "id": 42,
            "market_title": "Counter-Strike: Spirit vs G2 (BO3) - IEM Cologne Major Playoffs",
            "outcome": "G2",
            "error_message": "Could not select outcome: G2",
            "created_at": 3000,
        },
        {
            "id": 43,
            "market_title": "Map Handicap: VIT (-1.5) vs Team Falcons (+1.5)",
            "outcome": "Team Falcons",
            "error_message": "Could not select outcome: Team Falcons",
            "created_at": 4000,
        },
    ]

    for row in rows:
        hint = failure_coverage_hint(row)
        assert hint["covered"] is True, (row, hint)
        assert hint["coverage_id"] == "esports_match_team_selector_fixture", (row, hint)

    summary = failure_bucket_summary(rows)
    assert summary[0]["covered_count"] == 4, summary
    assert summary[0]["uncovered_count"] == 0, summary
    assert summary[0]["coverage_ids"] == ["esports_match_team_selector_fixture"], summary


def test_world_cup_select_outcome_cleanup_coverage():
    rows = [
        {
            "id": 50,
            "market_title": "Will USA win Group D in the 2026 FIFA World Cup?",
            "outcome": "No",
            "error_message": "Could not select outcome: No",
            "created_at": 1000,
        },
        {
            "id": 51,
            "market_title": "Will Mexico reach the 2026 FIFA World Cup final?",
            "outcome": "No",
            "error_message": "Could not select outcome: No",
            "created_at": 2000,
        },
        {
            "id": 52,
            "market_title": "Will Argentina reach the 2026 FIFA World Cup final?",
            "outcome": "No",
            "error_message": "Could not select outcome: No",
            "created_at": 3000,
        },
    ]

    for row in rows:
        hint = failure_coverage_hint(row)
        assert hint["covered"] is True, (row, hint)
        assert hint["coverage_id"] == "world_cup_select_outcome_cleanup_fixture", (row, hint)

    summary = failure_bucket_summary(rows)
    assert summary[0]["covered_count"] == 3, summary
    assert summary[0]["uncovered_count"] == 0, summary
    assert summary[0]["coverage_ids"] == ["world_cup_select_outcome_cleanup_fixture"], summary


def test_abelardo_target_market_missing_coverage():
    row = {
        "id": 60,
        "market_title": "Will Abelardo de la Espriella  win the 2026 Colombian presidential election?",
        "outcome": "Yes",
        "error_message": "Target market content never appeared for Will Abelardo de la Espriella  win the 2026 Colombian presidential election?",
        "created_at": 1000,
    }

    hint = failure_coverage_hint(row)
    assert hint["covered"] is True, hint
    assert hint["coverage_id"] == "content_based_event_visibility_fixture", hint

    summary = failure_bucket_summary([row])
    assert summary[0]["bucket"] == "target_market_missing", summary
    assert summary[0]["covered_count"] == 1, summary
    assert summary[0]["uncovered_count"] == 0, summary
    assert actionable_failure_buckets(summary) == [], summary


def test_ludvig_sell_dialog_open_covered_by_live_precheck():
    row = {
        "id": 70,
        "market_title": "Will Ludvig Aberg win the 2026 U.S. Open?",
        "outcome": "NO",
        "error_message": "Could not open sell dialog for outcome: NO (keywords=['ludvig', 'aberg', 'open', 'us', 'ludvig aberg', 'ludvig aberg open', 'aberg open'], sellButtons=0)",
        "created_at": 1000,
    }

    hint = failure_coverage_hint(row)
    assert hint["covered"] is True, hint
    assert hint["coverage_id"] == "live_sell_position_precheck", hint

    summary = failure_bucket_summary([row])
    assert summary[0]["bucket"] == "sell_dialog_open", summary
    assert summary[0]["covered_count"] == 1, summary
    assert summary[0]["uncovered_count"] == 0, summary
    assert actionable_failure_buckets(summary) == [], summary


def test_click_submit_partial_coverage_remains_actionable():
    row = {
        "id": 90,
        "market_title": "Will Argentina win on 2026-06-22?",
        "outcome": "Yes",
        "quantity": "2.4691",
        "amount": "1.9999",
        "error_message": "Could not click sell button",
        "created_at": 1000,
    }

    hint = failure_coverage_hint(row)
    assert hint["covered"] is False, hint
    assert hint["coverage_level"] == "partial", hint
    assert hint["coverage_id"] == "robust_sell_submit_button_fixtures", hint

    summary = failure_bucket_summary([row])
    assert summary[0]["bucket"] == "click_submit", summary
    assert summary[0]["covered_count"] == 0, summary
    assert summary[0]["uncovered_count"] == 1, summary
    assert actionable_failure_buckets(summary)[0]["bucket"] == "click_submit", summary


def test_argentina_sell_submit_historical_record_is_exact_covered():
    row = {
        "id": 597,
        "market_title": "Will Argentina win on 2026-06-22?",
        "outcome": "Yes",
        "quantity": "2.4691",
        "amount": "1.999971",
        "error_message": "Could not click sell button",
        "created_at": 1782150472160,
    }

    hint = failure_coverage_hint(row)
    assert hint["covered"] is True, hint
    assert hint["coverage_level"] == "exact", hint
    assert hint["coverage_id"] == "robust_sell_submit_button_fixtures", hint

    summary = failure_bucket_summary([row])
    assert summary[0]["bucket"] == "click_submit", summary
    assert summary[0]["covered_count"] == 1, summary
    assert summary[0]["uncovered_count"] == 0, summary
    assert actionable_failure_buckets(summary) == [], summary


def test_manual_zero_amount_sell_verification_records_are_not_actionable():
    rows = [
        {
            "id": 572,
            "external_trade_id": "manual-b394ddb9-d45b-4941-a9ad-abaeba854789",
            "market_title": "Will Mexico reach the 2026 FIFA World Cup final?",
            "outcome": "NO",
            "quantity": "2.12",
            "price": "0",
            "amount": "0",
            "error_message": "SELL post-submit verification failed: live portfolio quantity did not decrease (before=2.12, after=2.12)",
            "created_at": 1000,
        },
        {
            "id": 575,
            "external_trade_id": "manual-43c01a3e-db89-48a7-8ecd-684148be6a9e",
            "market_title": "Will Belgium reach the 2026 FIFA World Cup final?",
            "outcome": "NO",
            "quantity": "2.11",
            "price": "0",
            "amount": "0",
            "error_message": "Live portfolio insufficient position, skipped (available=0, required=2.11)",
            "created_at": 2000,
        },
    ]

    assert [classify_failure_row(row) for row in rows] == [
        "test_or_incomplete_record",
        "test_or_incomplete_record",
    ]
    summary = failure_bucket_summary(rows)
    assert summary[0]["bucket"] == "test_or_incomplete_record", summary
    assert summary[0]["count"] == 2, summary
    assert actionable_failure_buckets(summary) == [], summary


def test_real_sell_post_submit_no_effect_remains_actionable_bucket():
    row = {
        "id": 700,
        "external_trade_id": "0xreal",
        "market_title": "Will Mexico reach the 2026 FIFA World Cup final?",
        "outcome": "NO",
        "quantity": "2.12",
        "price": "0.94",
        "amount": "1.99",
        "error_message": "SELL post-submit verification failed: live portfolio quantity did not decrease (before=2.12, after=2.12)",
        "created_at": 1000,
    }

    assert classify_failure_row(row) == "sell_post_submit_no_effect"
    summary = failure_bucket_summary([row])
    assert summary[0]["bucket"] == "sell_post_submit_no_effect", summary
    assert summary[0]["uncovered_count"] == 1, summary


def main() -> int:
    test_classify_failure_messages()
    test_filter_records_since_uses_created_or_updated_time()
    test_latest_record_time_ms_uses_created_or_updated_time()
    test_build_monitor_status()
    test_stale_success_mismatches_are_not_active_or_strict_actionable()
    test_fresh_success_mismatch_is_active_and_strict_actionable()
    test_reconciliation_suggestions_only_include_unreconciled_stale_mismatches()
    test_reconciliation_suggestions_mark_partial_stale_as_medium_confidence()
    test_failure_bucket_summary_and_next_actions()
    test_select_outcome_test_or_incomplete_records_are_not_actionable()
    test_navigation_race_historical_records_are_exact_covered()
    test_navigation_network_historical_records_are_exact_covered()
    test_amount_input_portfolio_screenshot_records_are_exact_covered()
    test_other_samples_are_split_into_specific_buckets()
    test_failure_coverage_hints_and_uncovered_counts()
    test_btc_updown_select_outcome_coverage()
    test_btc_updown_buy_dialog_and_navigation_race_coverage()
    test_btc_updown_restart_and_stale_market_coverage()
    test_world_cup_group_multi_country_coverage()
    test_world_cup_remaining_country_coverage()
    test_esports_match_team_coverage()
    test_world_cup_select_outcome_cleanup_coverage()
    test_abelardo_target_market_missing_coverage()
    test_ludvig_sell_dialog_open_covered_by_live_precheck()
    test_click_submit_partial_coverage_remains_actionable()
    test_argentina_sell_submit_historical_record_is_exact_covered()
    test_manual_zero_amount_sell_verification_records_are_not_actionable()
    test_real_sell_post_submit_no_effect_remains_actionable_bucket()
    print("bridge reliability audit tests passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
