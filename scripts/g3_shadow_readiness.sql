-- G3 Phase 6 read-only Shadow readiness checklist.
-- Run against the polyhermes database; it only executes SET and SELECT.

SET @account_id = 2;
SET @since_ms = UNIX_TIMESTAMP(UTC_TIMESTAMP() - INTERVAL 3 DAY) * 1000;

SELECT
    'three_day_daily_snapshot' AS metric,
    COUNT(*) AS complete_snapshot_count,
    SUM(snapshot_type = 'MIDNIGHT') AS midnight_snapshot_count,
    MIN(day_start_at) AS first_day_start_at,
    MAX(day_start_at) AS last_day_start_at
FROM daily_asset_snapshot d
JOIN wallet_accounts a ON BINARY LOWER(a.wallet_address) = BINARY LOWER(d.wallet_address)
WHERE a.id = @account_id
  AND d.day_start_at >= @since_ms
  AND d.valuation_status = 'COMPLETE'
  AND d.total_assets IS NOT NULL;

SELECT
    'three_day_scoped_bridge_terminal' AS metric,
    side,
    status,
    COUNT(*) AS total
FROM bridge_trade_record
WHERE created_at >= @since_ms
  AND JSON_VALID(raw_payload) = 1
  AND CAST(JSON_UNQUOTE(JSON_EXTRACT(raw_payload, '$.copyTradingAccountId')) AS UNSIGNED) = @account_id
GROUP BY side, status
ORDER BY side, status;

SELECT
    'three_day_unscoped_bridge' AS metric,
    COUNT(*) AS total
FROM bridge_trade_record
WHERE created_at >= @since_ms
  AND (
      raw_payload IS NULL
      OR JSON_VALID(raw_payload) = 0
      OR JSON_EXTRACT(raw_payload, '$.copyTradingAccountId') IS NULL
  );

SELECT
    'three_day_risk_snapshot' AS metric,
    COUNT(*) AS decisions,
    SUM(input_snapshot_json IS NOT NULL) AS input_snapshots,
    SUM(JSON_UNQUOTE(JSON_EXTRACT(input_snapshot_json, '$.request.stage')) = 'FINAL') AS final_decisions,
    SUM(JSON_EXTRACT(input_snapshot_json, '$.request.correlationId') IS NOT NULL) AS correlated_decisions
FROM portfolio_risk_decision
WHERE account_id = @account_id
  AND created_at >= @since_ms;
