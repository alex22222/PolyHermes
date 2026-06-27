-- 清理无钱包地址的旧快照，避免多个 Bridge 只读账户互相显示对方的持仓
DELETE FROM bridge_position_snapshot WHERE wallet_address = '' OR wallet_address IS NULL;
