-- ============================================
-- V58: 清理因市场分类错误而产生的 stale crypto leader 和候选池记录
-- 在 V57 修正 markets.category 后，之前大量体育/政治市场被错误标为 crypto，
-- 导致 copy_trading_leaders 和 leader_scanner_candidate_pool 中积累了错误的 crypto 记录。
-- 本迁移删除这些 stale 记录，让 LeaderScannerService 在下次扫描时基于正确的分类重新发现。
-- ============================================

-- 1. 删除没有被 copy_trading 引用的 stale crypto leader
--    保留已被跟单配置引用的 leader，避免破坏现有配置
DELETE l FROM copy_trading_leaders l
LEFT JOIN copy_trading ct ON ct.leader_id = l.id
WHERE l.category = 'crypto' AND ct.id IS NULL;

-- 2. 删除错误的 crypto 候选池记录
--    这些候选主要来源于被错误分类为 crypto 的 FIFA/GTA 等市场
--    discoverOnly 会在下次运行时根据正确的 marketIds 重新发现
DELETE FROM leader_scanner_candidate_pool WHERE category = 'crypto';
