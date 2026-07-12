CREATE TABLE IF NOT EXISTS portfolio_risk_reservation (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    correlation_id VARCHAR(100) NOT NULL,
    account_id BIGINT NOT NULL,
    amount DECIMAL(20,8) NOT NULL,
    market_id VARCHAR(100) NULL,
    event_slug VARCHAR(200) NULL,
    leader_address VARCHAR(100) NULL,
    category VARCHAR(50) NULL,
    status VARCHAR(20) NOT NULL,
    expires_at BIGINT NOT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL,
    completed_at BIGINT NULL,
    CONSTRAINT uk_portfolio_risk_correlation UNIQUE (correlation_id),
    INDEX idx_portfolio_risk_reservation_account_status (account_id, status, expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='G3 BUY 并发资金预占';
