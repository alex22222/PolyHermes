-- 为 copy_trading_leaders 增加 Leader 研究模块评分字段
ALTER TABLE copy_trading_leaders
    ADD COLUMN IF NOT EXISTS research_score DECIMAL(8, 4) DEFAULT NULL COMMENT '研究模块 copyability 评分 (0-100)',
    ADD COLUMN IF NOT EXISTS research_tag VARCHAR(20) DEFAULT NULL COMMENT '研究标签: ELITE/TRADEABLE/CANDIDATE/WATCH/RISKY',
    ADD COLUMN IF NOT EXISTS research_risk_flags VARCHAR(255) DEFAULT NULL COMMENT '风险标记,逗号分隔',
    ADD COLUMN IF NOT EXISTS research_scored_at BIGINT DEFAULT NULL COMMENT '研究评分时间(毫秒时间戳)',
    ADD INDEX IF NOT EXISTS idx_copy_trading_leaders_research_tag (research_tag),
    ADD INDEX IF NOT EXISTS idx_copy_trading_leaders_research_score (research_score DESC);
