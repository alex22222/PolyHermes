ALTER TABLE portfolio_reduction_draft
    ADD COLUMN confirmed_by VARCHAR(100),
    ADD COLUMN confirmed_at BIGINT;
