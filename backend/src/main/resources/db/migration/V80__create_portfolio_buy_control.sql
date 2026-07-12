CREATE TABLE portfolio_buy_control (
    account_id BIGINT NOT NULL PRIMARY KEY,
    paused BOOLEAN NOT NULL DEFAULT FALSE,
    reason VARCHAR(500) NULL,
    updated_by VARCHAR(100) NOT NULL,
    updated_at BIGINT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE portfolio_buy_control_audit (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    account_id BIGINT NOT NULL,
    action VARCHAR(20) NOT NULL,
    reason VARCHAR(500) NULL,
    actor VARCHAR(100) NOT NULL,
    created_at BIGINT NOT NULL,
    INDEX idx_buy_control_audit_account_created (account_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
