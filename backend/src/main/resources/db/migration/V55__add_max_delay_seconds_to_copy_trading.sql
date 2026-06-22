-- ============================================
-- V55: 添加 Leader 信号最大延迟字段
-- 用于测量 Leader 交易发生时间到系统处理时间的延迟
-- 超过阈值则拒绝跟单，避免延迟侵蚀收益
-- ============================================

-- 添加最大延迟字段到跟单配置表
ALTER TABLE copy_trading
    ADD COLUMN max_delay_seconds INT NULL COMMENT '最大信号延迟秒数，NULL 表示不限制';

-- 添加最大延迟字段到跟单模板表
ALTER TABLE copy_trading_templates
    ADD COLUMN max_delay_seconds INT NULL COMMENT '最大信号延迟秒数，NULL 表示不限制';
