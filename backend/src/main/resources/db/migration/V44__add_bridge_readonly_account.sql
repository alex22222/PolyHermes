-- 支持 Bridge 关联的只读账户（Magic 邮箱账户无需导入私钥即可查看仓位）

-- 私钥对只读账户不再是必须的
ALTER TABLE wallet_accounts MODIFY COLUMN private_key VARCHAR(500) NULL COMMENT '私钥（加密存储）';

-- 标识是否为只读账户（Bridge 关联账户没有私钥，不能卖出/赎回）
ALTER TABLE wallet_accounts ADD COLUMN read_only BOOLEAN NOT NULL DEFAULT FALSE COMMENT '是否只读（Bridge 关联账户无私钥）' AFTER is_enabled;
