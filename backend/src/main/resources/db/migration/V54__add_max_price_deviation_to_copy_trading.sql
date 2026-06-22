-- ============================================
-- V54: 添加 Leader 成交价最大偏离字段
-- 用于实时检查当前 orderbook 价格相比 Leader 成交价的偏离百分比
-- 超过阈值则拒绝跟单，避免高价追单导致负期望
-- ============================================

-- 添加最大价格偏离字段到跟单配置表
ALTER TABLE copy_trading
    ADD COLUMN max_price_deviation DECIMAL(5, 2) NULL COMMENT '最大价格偏离百分比（例如 5.00 表示 5%），NULL 表示不限制';

-- 添加最大价格偏离字段到跟单模板表
ALTER TABLE copy_trading_templates
    ADD COLUMN max_price_deviation DECIMAL(5, 2) NULL COMMENT '最大价格偏离百分比（例如 5.00 表示 5%），NULL 表示不限制';
