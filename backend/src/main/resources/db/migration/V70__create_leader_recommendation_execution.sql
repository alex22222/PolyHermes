CREATE TABLE IF NOT EXISTS leader_research_recommendation_execution (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    category VARCHAR(50) NOT NULL COMMENT '推荐闭环分类',
    status VARCHAR(30) NOT NULL COMMENT '执行状态',
    dry_run BOOLEAN NOT NULL DEFAULT TRUE COMMENT '是否 dry-run',
    actions_json TEXT NULL COMMENT '请求动作列表',
    recommendation_counts_json TEXT NULL COMMENT '推荐动作计数',
    planned_actions_json TEXT NULL COMMENT '执行计划快照',
    result_summary_json TEXT NULL COMMENT '执行结果摘要',
    request_json TEXT NULL COMMENT '请求快照',
    error_message TEXT NULL COMMENT '失败信息',
    started_at BIGINT NOT NULL COMMENT '开始时间',
    finished_at BIGINT NULL COMMENT '结束时间',
    duration_ms BIGINT NULL COMMENT '耗时',
    created_at BIGINT NOT NULL COMMENT '创建时间',
    INDEX idx_leader_recommendation_execution_category_started (category, started_at),
    INDEX idx_leader_recommendation_execution_status_started (status, started_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Leader 推荐闭环执行/预演快照';
