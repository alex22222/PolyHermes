-- Bridge 真实持仓快照表
-- 由 polymtrade-bridge 抓取 Polymtrade /portfolio 页面并同步到后端，
-- 作为 Bridge 只读账户仓位管理的数据源。

CREATE TABLE IF NOT EXISTS bridge_position_snapshot (
    id              BIGINT AUTO_INCREMENT PRIMARY KEY COMMENT '自增主键',
    bridge_id       VARCHAR(100) NOT NULL COMMENT 'Bridge 标识，如 polymtrade-bridge',
    market_id       VARCHAR(100) NULL COMMENT '市场 condition ID（markets.market_id）',
    market_title    VARCHAR(500) NOT NULL COMMENT '市场标题（question）',
    side            VARCHAR(20)  NOT NULL COMMENT '持仓方向 YES/NO',
    quantity        DECIMAL(20, 8) NOT NULL COMMENT '持仓数量',
    current_value   DECIMAL(20, 8) NULL COMMENT '当前价值（USDC）',
    pnl             DECIMAL(20, 8) NULL COMMENT '未实现盈亏（USDC）',
    percent_pnl     DECIMAL(10, 4) NULL COMMENT '盈亏百分比',
    market_icon     VARCHAR(500) NULL COMMENT '市场图标 URL',
    market_slug     VARCHAR(200) NULL COMMENT '市场 slug（Bridge 导航用）',
    event_slug      VARCHAR(200) NULL COMMENT '事件 slug（前端跳转用）',
    synced_at       BIGINT       NOT NULL COMMENT 'Bridge 抓取时间戳（毫秒）',
    created_at      BIGINT       NOT NULL DEFAULT (UNIX_TIMESTAMP() * 1000) COMMENT '创建时间（毫秒）',
    updated_at      BIGINT       NOT NULL DEFAULT (UNIX_TIMESTAMP() * 1000) COMMENT '更新时间（毫秒）',
    UNIQUE KEY uk_bridge_position_snapshot (bridge_id, market_title, side)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Bridge 真实持仓快照';
