ALTER TABLE wallet_accounts
    ADD COLUMN last_bridge_sync_at BIGINT NOT NULL DEFAULT 0 COMMENT '该钱包最后一次被 Bridge 同步持仓的时间戳（毫秒）';
