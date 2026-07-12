CREATE TABLE portfolio_reduction_draft (
    draft_id VARCHAR(36) PRIMARY KEY,
    account_id BIGINT NOT NULL,
    position_key VARCHAR(700) NOT NULL,
    quantity DECIMAL(20, 8) NOT NULL,
    status VARCHAR(20) NOT NULL,
    snapshot_json LONGTEXT NOT NULL,
    created_by VARCHAR(100) NOT NULL,
    expires_at BIGINT NOT NULL,
    created_at BIGINT NOT NULL,
    updated_at BIGINT NOT NULL
);

CREATE INDEX idx_portfolio_reduction_draft_account_created
    ON portfolio_reduction_draft(account_id, created_at);

CREATE INDEX idx_portfolio_reduction_draft_status_expires
    ON portfolio_reduction_draft(status, expires_at);
