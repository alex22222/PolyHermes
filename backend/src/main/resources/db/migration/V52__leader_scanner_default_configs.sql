-- Leader Scanner 默认配置
-- seed wallets 初始为空，后续可通过 /api/copy-trading/leaders/scan/config 接口维护
INSERT IGNORE INTO system_config (config_key, config_value, description, created_at, updated_at)
VALUES
    ('leader_scanner.analysis_window_days', '30', 'Leader Scanner 分析窗口天数', UNIX_TIMESTAMP(NOW(3)) * 1000, UNIX_TIMESTAMP(NOW(3)) * 1000),
    ('leader_scanner.seed_wallets.politics', '', 'Leader Scanner politics 类别 seed wallets', UNIX_TIMESTAMP(NOW(3)) * 1000, UNIX_TIMESTAMP(NOW(3)) * 1000),
    ('leader_scanner.seed_wallets.sports', '', 'Leader Scanner sports 类别 seed wallets', UNIX_TIMESTAMP(NOW(3)) * 1000, UNIX_TIMESTAMP(NOW(3)) * 1000),
    ('leader_scanner.seed_wallets.crypto', '', 'Leader Scanner crypto 类别 seed wallets', UNIX_TIMESTAMP(NOW(3)) * 1000, UNIX_TIMESTAMP(NOW(3)) * 1000),
    ('leader_scanner.seed_wallets.finance', '', 'Leader Scanner finance 类别 seed wallets', UNIX_TIMESTAMP(NOW(3)) * 1000, UNIX_TIMESTAMP(NOW(3)) * 1000),
    ('leader_scanner.seed_wallets', '', 'Leader Scanner 通用 seed wallets', UNIX_TIMESTAMP(NOW(3)) * 1000, UNIX_TIMESTAMP(NOW(3)) * 1000);
