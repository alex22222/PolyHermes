ALTER TABLE leader_research_candidate
    MODIFY COLUMN source VARCHAR(255) NOT NULL DEFAULT 'UNKNOWN' COMMENT '主来源/多来源列表';
