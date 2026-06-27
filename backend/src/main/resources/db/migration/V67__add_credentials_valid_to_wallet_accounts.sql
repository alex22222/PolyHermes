ALTER TABLE wallet_accounts
    ADD COLUMN credentials_valid TINYINT(1) NOT NULL DEFAULT 1 COMMENT '加密凭证是否可用（解密失败时自动标记为 false）';

-- 初始状态：所有历史账户默认凭证有效，由应用启动后自行校验并更新
