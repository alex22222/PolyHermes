-- ============================================
-- V47: 为 Leader 表添加智能扫描分析字段
-- 用于存储扫链发现的活跃 Leader 的聪明钱分析数据
-- ============================================

ALTER TABLE copy_trading_leaders
    ADD COLUMN total_trades INT DEFAULT NULL COMMENT '总交易数（扫描统计）',
    ADD COLUMN win_rate DECIMAL(5,2) DEFAULT NULL COMMENT '胜率（百分比 0-100）',
    ADD COLUMN total_pnl VARCHAR(50) DEFAULT NULL COMMENT '总盈亏（USDC）',
    ADD COLUMN total_volume VARCHAR(50) DEFAULT NULL COMMENT '总交易量（USDC）',
    ADD COLUMN avg_trade_size VARCHAR(50) DEFAULT NULL COMMENT '平均交易规模（USDC）',
    ADD COLUMN last_trade_at BIGINT DEFAULT NULL COMMENT '最后交易时间（毫秒时间戳）',
    ADD COLUMN activity_score DECIMAL(5,2) DEFAULT NULL COMMENT '活跃度评分（0-100）',
    ADD COLUMN smart_money_rank INT DEFAULT NULL COMMENT '聪明钱排名（按类别）',
    ADD COLUMN scan_source VARCHAR(20) DEFAULT NULL COMMENT '扫描来源：auto_scan, manual',
    ADD COLUMN scanned_at BIGINT DEFAULT NULL COMMENT '最后扫描时间（毫秒时间戳）',
    ADD INDEX idx_scan_source (scan_source),
    ADD INDEX idx_scanned_at (scanned_at),
    ADD INDEX idx_smart_money_rank (smart_money_rank),
    ADD INDEX idx_activity_score (activity_score);
