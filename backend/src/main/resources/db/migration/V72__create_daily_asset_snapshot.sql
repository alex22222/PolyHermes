CREATE TABLE daily_asset_snapshot (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    bridge_id VARCHAR(100) NOT NULL,
    wallet_address VARCHAR(42) NOT NULL,
    day_start_at BIGINT NOT NULL,
    available_balance DECIMAL(20, 8) NOT NULL,
    positions_value DECIMAL(20, 8) NOT NULL,
    total_assets DECIMAL(20, 8) NOT NULL,
    captured_at BIGINT NOT NULL,
    created_at BIGINT NOT NULL,
    UNIQUE KEY uk_daily_asset_wallet_day (bridge_id, wallet_address, day_start_at),
    KEY idx_daily_asset_day (day_start_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
