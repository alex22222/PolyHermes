-- 清理 wallet_address 为空的旧快照，避免后续按钱包查询时干扰
DELETE FROM bridge_position_snapshot WHERE wallet_address = '' OR wallet_address IS NULL;
