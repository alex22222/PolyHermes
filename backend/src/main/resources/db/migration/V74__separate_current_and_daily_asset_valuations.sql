ALTER TABLE daily_asset_snapshot
    ADD COLUMN capture_offset_ms BIGINT NOT NULL DEFAULT 0 AFTER snapshot_type;

UPDATE daily_asset_snapshot
SET capture_offset_ms = GREATEST(captured_at - day_start_at, 0);

CREATE TABLE current_asset_valuation (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    bridge_id VARCHAR(100) NOT NULL,
    wallet_address VARCHAR(42) NOT NULL,
    available_balance DECIMAL(20, 8) NOT NULL,
    positions_value DECIMAL(20, 8) NOT NULL,
    total_assets DECIMAL(20, 8) NULL,
    unknown_position_count INT NOT NULL DEFAULT 0,
    valuation_status VARCHAR(20) NOT NULL DEFAULT 'COMPLETE',
    captured_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    UNIQUE KEY uk_current_asset_wallet (bridge_id, wallet_address),
    KEY idx_current_asset_captured_at (captured_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
