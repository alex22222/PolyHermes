-- G4 Phase 1 read-only label coverage report.
-- Run inside the polyhermes database. This script never mutates data.

SELECT 'processed_trade' metric, COUNT(*) total,
       COUNT(DISTINCT CONCAT(leader_id, '|', leader_trade_id)) distinct_keys
FROM processed_trade;

SELECT 'bridge_status' metric, side, status, COUNT(*) total
FROM bridge_trade_record GROUP BY side, status ORDER BY side, status;

SELECT 'bridge_failure_taxonomy' metric,
       CASE
           WHEN error_message LIKE 'category mismatch:%' OR error_message LIKE 'keyword whitelist%' THEN 'POLICY_FILTER'
           WHEN error_message LIKE '%BUY skipped:%' OR error_message LIKE 'price %' OR error_message LIKE 'Low-price %' THEN 'RISK_FILTER'
           WHEN error_message LIKE 'Insufficient position%' OR error_message LIKE 'Live portfolio insufficient%' THEN 'SELL_SAFETY_SKIP'
           WHEN error_message LIKE 'Insufficient balance%' OR error_message LIKE '%deposit%' THEN 'ACCOUNT_FUNDING'
           WHEN error_message LIKE 'Could not select outcome:%' OR error_message LIKE 'Could not enter trade amount%' THEN 'UI_EXECUTION_FAILURE'
           WHEN error_message IS NULL THEN 'UNKNOWN'
           ELSE 'OTHER_EXECUTION_OR_FILTER'
       END label_class,
       COUNT(*) total
FROM bridge_trade_record
WHERE status = 'FAILED'
GROUP BY label_class ORDER BY total DESC;

SELECT 'bridge_key_coverage' metric,
       COUNT(*) total,
       SUM(external_trade_id IS NOT NULL) external_trade_id,
       SUM(raw_payload IS NOT NULL AND JSON_VALID(raw_payload)) valid_payload,
       SUM(JSON_EXTRACT(raw_payload, '$.copyTradingId') IS NOT NULL) copy_trading_id,
       SUM(JSON_EXTRACT(raw_payload, '$.copyTradingAccountId') IS NOT NULL) account_id,
       SUM(JSON_EXTRACT(raw_payload, '$.portfolioRiskCorrelationId') IS NOT NULL) risk_correlation_id
FROM bridge_trade_record;

SELECT 'risk_decision_coverage' metric,
       COUNT(*) total,
       SUM(input_snapshot_json IS NOT NULL) input_snapshot,
       SUM(JSON_UNQUOTE(JSON_EXTRACT(input_snapshot_json, '$.request.stage')) = 'FINAL') final_stage,
       SUM(JSON_EXTRACT(input_snapshot_json, '$.request.correlationId') IS NOT NULL) correlation_id
FROM portfolio_risk_decision;

SELECT 'paper_label_coverage' metric,
       COUNT(*) total,
       SUM(filter_result = 'PASSED') passed,
       SUM(filter_result <> 'PASSED') filtered,
       SUM(realized_pnl IS NOT NULL) realized_pnl,
       SUM(valuation_status = 'CONFIRMED_ZERO') confirmed_zero,
       SUM(valuation_status = 'UNKNOWN') unknown_valuation
FROM leader_paper_trade;

SELECT 'paper_key_and_leakage' metric,
       COUNT(*) total,
       SUM(activity_event_id IS NOT NULL) activity_event_id,
       COUNT(DISTINCT CONCAT(candidate_id, '|', leader_trade_id)) distinct_candidate_trade,
       SUM(quote_timestamp IS NULL) quote_timestamp_missing,
       SUM(quote_timestamp > event_time) quote_after_event,
       SUM(quote_timestamp <= event_time) quote_available_at_event
FROM leader_paper_trade;

SELECT 'paper_label_conflicts' metric, COUNT(*) conflicting_keys
FROM (
    SELECT candidate_id, leader_trade_id
    FROM leader_paper_trade
    GROUP BY candidate_id, leader_trade_id
    HAVING COUNT(DISTINCT CONCAT(valuation_status, '|', COALESCE(CAST(realized_pnl AS CHAR), 'NULL'))) > 1
) conflicts;

SELECT 'settlement_coverage' metric,
       (SELECT COUNT(*) FROM bridge_trade_record WHERE side = 'BUY' AND status = 'SUCCESS') real_buy_success,
       0 real_buy_with_realized_pnl,
       (SELECT COUNT(*) FROM crypto_tail_strategy_trigger) crypto_tail_total,
       (SELECT COUNT(*) FROM crypto_tail_strategy_trigger WHERE resolved = TRUE AND realized_pnl IS NOT NULL) crypto_tail_settled,
       (SELECT COUNT(*) FROM leader_paper_trade WHERE filter_result = 'PASSED') paper_passed,
       (SELECT COUNT(*) FROM leader_paper_trade WHERE filter_result = 'PASSED' AND realized_pnl IS NOT NULL) paper_labeled;

SELECT 'model_candidate_coverage' metric,
       COUNT(*) total,
       COUNT(DISTINCT CONCAT(leader_id, '|', leader_trade_id, '|', copy_trading_id, '|', account_id)) distinct_grain,
       SUM(event_time IS NOT NULL) event_time,
       SUM(market_id IS NOT NULL) market_id
FROM model_trade_candidate;

SELECT 'model_candidate_downstream_links' metric,
       (SELECT COUNT(*) FROM model_trade_candidate) candidates,
       (SELECT COUNT(*) FROM filtered_order WHERE model_candidate_id IS NOT NULL) filtered_orders,
       (SELECT COUNT(*) FROM copy_order_tracking WHERE model_candidate_id IS NOT NULL) direct_success_orders,
       (SELECT COUNT(*) FROM bridge_trade_record
        WHERE JSON_EXTRACT(raw_payload, '$.modelCandidateId') IS NOT NULL) bridge_records,
       (SELECT COUNT(*) FROM portfolio_risk_decision
        WHERE JSON_EXTRACT(input_snapshot_json, '$.request.modelCandidateId') IS NOT NULL) risk_decisions;
