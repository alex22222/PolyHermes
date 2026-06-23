ALTER TABLE copy_trading_leaders
    ADD COLUMN conviction_score DECIMAL(8, 4) DEFAULT NULL COMMENT 'Leader 信念评分 (0-100)',
    ADD COLUMN zombie_risk_score DECIMAL(8, 4) DEFAULT NULL COMMENT '僵尸单/未平仓亏损风险评分 (0-100, 越高越危险)',
    ADD COLUMN category_score DECIMAL(8, 4) DEFAULT NULL COMMENT '分领域适配评分 (0-100)',
    ADD COLUMN execution_score DECIMAL(8, 4) DEFAULT NULL COMMENT '执行链路适配评分 (0-100)',
    ADD INDEX idx_copy_trading_leaders_conviction_score (conviction_score),
    ADD INDEX idx_copy_trading_leaders_zombie_risk_score (zombie_risk_score),
    ADD INDEX idx_copy_trading_leaders_category_score (category_score),
    ADD INDEX idx_copy_trading_leaders_execution_score (execution_score);
