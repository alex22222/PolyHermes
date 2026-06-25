ALTER TABLE bridge_trade_record
    ADD COLUMN notification_status VARCHAR(30) NOT NULL DEFAULT 'PENDING' COMMENT 'Bridge 通知状态: PENDING/SENDING/SENT/FAILED/SKIPPED' AFTER raw_payload,
    ADD COLUMN notification_sent_at BIGINT DEFAULT NULL COMMENT 'Bridge 通知发送时间' AFTER notification_status,
    ADD COLUMN notification_error TEXT DEFAULT NULL COMMENT 'Bridge 通知错误' AFTER notification_sent_at,
    ADD INDEX idx_bridge_trade_record_notification_status (notification_status, status, updated_at);

UPDATE bridge_trade_record
SET notification_status = 'SKIPPED'
WHERE notification_status = 'PENDING';
