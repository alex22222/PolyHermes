SET @idx_exists := (
    SELECT COUNT(1)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'leader_activity_event'
      AND index_name = 'idx_leader_activity_event_discovery_time_market_wallet'
);
SET @ddl := IF(
    @idx_exists = 0,
    'ALTER TABLE leader_activity_event ADD INDEX idx_leader_activity_event_discovery_time_market_wallet (usable_for_discovery, event_time, market_id, normalized_wallet)',
    'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @idx_exists := (
    SELECT COUNT(1)
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'leader_activity_event'
      AND index_name = 'idx_leader_activity_event_market_time_wallet'
);
SET @ddl := IF(
    @idx_exists = 0,
    'ALTER TABLE leader_activity_event ADD INDEX idx_leader_activity_event_market_time_wallet (market_id, event_time, normalized_wallet)',
    'SELECT 1'
);
PREPARE stmt FROM @ddl;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
