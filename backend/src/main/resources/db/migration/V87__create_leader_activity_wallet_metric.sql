CREATE TABLE IF NOT EXISTS leader_activity_wallet_metric (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(50) NOT NULL,
    lookback_days INT NOT NULL,
    normalized_wallet VARCHAR(42) NOT NULL,
    total_events BIGINT NOT NULL,
    distinct_markets BIGINT NOT NULL,
    buy_events BIGINT NOT NULL,
    sell_events BIGINT NOT NULL,
    safe_price_events BIGINT NOT NULL,
    tail_price_events BIGINT NOT NULL,
    avg_amount DECIMAL(20,8) NULL,
    total_amount DECIMAL(20,8) NOT NULL DEFAULT 0.00000000,
    last_event_time BIGINT NULL,
    generated_at BIGINT NOT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    UNIQUE KEY uk_leader_activity_wallet_metric_category_wallet (category, lookback_days, normalized_wallet),
    INDEX idx_leader_activity_wallet_metric_rank (
        category,
        lookback_days,
        sell_events,
        safe_price_events,
        distinct_markets,
        total_amount
    ),
    INDEX idx_leader_activity_wallet_metric_generated (category, lookback_days, generated_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Pre-aggregated wallet metrics for leader activity source discovery';
