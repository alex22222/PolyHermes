ALTER TABLE daily_asset_snapshot
    ADD COLUMN pending_redeem_value DECIMAL(20, 8) NULL DEFAULT 0 AFTER positions_value,
    ADD COLUMN redeemable_position_count INT NULL DEFAULT 0 AFTER pending_redeem_value,
    ADD COLUMN redeem_valuation_status VARCHAR(20) NOT NULL DEFAULT 'COMPLETE' AFTER redeemable_position_count;

ALTER TABLE current_asset_valuation
    ADD COLUMN pending_redeem_value DECIMAL(20, 8) NULL DEFAULT 0 AFTER positions_value,
    ADD COLUMN redeemable_position_count INT NULL DEFAULT 0 AFTER pending_redeem_value,
    ADD COLUMN redeem_valuation_status VARCHAR(20) NOT NULL DEFAULT 'COMPLETE' AFTER redeemable_position_count;
