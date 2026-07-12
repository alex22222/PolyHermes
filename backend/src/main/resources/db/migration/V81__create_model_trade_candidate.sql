CREATE TABLE model_trade_candidate (
    candidate_id VARCHAR(36) PRIMARY KEY,
    leader_id BIGINT NOT NULL,
    leader_trade_id VARCHAR(100) NOT NULL,
    copy_trading_id BIGINT NOT NULL,
    account_id BIGINT NOT NULL,
    source VARCHAR(50) NOT NULL,
    side VARCHAR(10) NOT NULL,
    market_id VARCHAR(100),
    outcome VARCHAR(50),
    outcome_index INT,
    leader_price DECIMAL(20, 8) NOT NULL,
    leader_size DECIMAL(20, 8) NOT NULL,
    event_time BIGINT,
    observed_at BIGINT NOT NULL,
    CONSTRAINT uk_model_trade_candidate_grain UNIQUE (
        leader_id, leader_trade_id, copy_trading_id, account_id
    )
);

CREATE INDEX idx_model_trade_candidate_observed_at
    ON model_trade_candidate(observed_at);

ALTER TABLE filtered_order
    ADD COLUMN model_candidate_id VARCHAR(36);

CREATE INDEX idx_filtered_order_model_candidate
    ON filtered_order(model_candidate_id);

ALTER TABLE copy_order_tracking
    ADD COLUMN model_candidate_id VARCHAR(36);

CREATE INDEX idx_copy_order_tracking_model_candidate
    ON copy_order_tracking(model_candidate_id);
