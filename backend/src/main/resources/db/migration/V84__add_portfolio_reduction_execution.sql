ALTER TABLE portfolio_reduction_draft
    ADD COLUMN execution_requested_by VARCHAR(100),
    ADD COLUMN execution_requested_at BIGINT,
    ADD COLUMN execution_external_trade_id VARCHAR(100),
    ADD COLUMN execution_record_id BIGINT,
    ADD COLUMN execution_error TEXT;

CREATE UNIQUE INDEX uk_portfolio_reduction_execution_external
    ON portfolio_reduction_draft(execution_external_trade_id);
