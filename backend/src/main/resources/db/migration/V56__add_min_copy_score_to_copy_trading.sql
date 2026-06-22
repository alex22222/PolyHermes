-- ============================================
-- V56: 添加最小 copy_score 阈值字段
-- 用于统一跟单评分门控，只有 copy_score 超过该阈值才允许下单
-- ============================================

-- 添加最小 copy_score 字段到跟单配置表
ALTER TABLE copy_trading
    ADD COLUMN min_copy_score DECIMAL(5, 2) NULL COMMENT '最小 copy_score 阈值（0-100），NULL 表示不启用统一评分门控';

-- 添加最小 copy_score 字段到跟单模板表
ALTER TABLE copy_trading_templates
    ADD COLUMN min_copy_score DECIMAL(5, 2) NULL COMMENT '最小 copy_score 阈值（0-100），NULL 表示不启用统一评分门控';
