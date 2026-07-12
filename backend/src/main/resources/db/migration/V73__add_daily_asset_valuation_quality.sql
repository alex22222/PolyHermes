ALTER TABLE daily_asset_snapshot
    MODIFY COLUMN total_assets DECIMAL(20, 8) NULL,
    ADD COLUMN unknown_position_count INT NOT NULL DEFAULT 0 AFTER total_assets,
    ADD COLUMN valuation_status VARCHAR(20) NOT NULL DEFAULT 'COMPLETE' AFTER unknown_position_count,
    ADD COLUMN snapshot_type VARCHAR(32) NOT NULL DEFAULT 'DAILY_FIRST_SUCCESS' AFTER valuation_status;
