-- 为 bridge_position_snapshot 增加钱包地址和可用余额字段，
-- 使多个 Bridge 只读账户可以分别保存各自的持仓快照。
ALTER TABLE bridge_position_snapshot
    ADD COLUMN wallet_address VARCHAR(42) NOT NULL DEFAULT '' AFTER bridge_id,
    ADD COLUMN available_balance DECIMAL(20, 8) NULL AFTER percent_pnl;

-- 添加按钱包地址查询的索引
CREATE INDEX idx_bridge_wallet ON bridge_position_snapshot (bridge_id, wallet_address);

-- 调整唯一索引，按钱包地址区分不同账户的同一市场持仓
ALTER TABLE bridge_position_snapshot
    DROP INDEX uk_bridge_position_snapshot,
    ADD UNIQUE INDEX uk_bridge_position_snapshot (bridge_id, wallet_address, market_title, side);

-- 清理无钱包地址的旧快照，由后续同步按实际 Bridge 登录钱包重新生成
DELETE FROM bridge_position_snapshot WHERE wallet_address = '' OR wallet_address IS NULL;
