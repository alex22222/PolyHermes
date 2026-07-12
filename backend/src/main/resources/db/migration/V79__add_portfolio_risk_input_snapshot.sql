ALTER TABLE portfolio_risk_decision
    ADD COLUMN input_snapshot_json LONGTEXT NULL AFTER rules_json;
