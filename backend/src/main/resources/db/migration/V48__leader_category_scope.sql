-- Allow the same wallet to be tracked independently per category.
SET @leader_address_unique := (
    SELECT constraint_columns.CONSTRAINT_NAME
    FROM (
        SELECT
            tc.CONSTRAINT_NAME,
            GROUP_CONCAT(kcu.COLUMN_NAME ORDER BY kcu.ORDINAL_POSITION) AS columns_csv
        FROM information_schema.TABLE_CONSTRAINTS tc
        JOIN information_schema.KEY_COLUMN_USAGE kcu
          ON tc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
         AND tc.TABLE_NAME = kcu.TABLE_NAME
         AND tc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
        WHERE tc.CONSTRAINT_SCHEMA = DATABASE()
          AND tc.TABLE_NAME = 'copy_trading_leaders'
          AND tc.CONSTRAINT_TYPE = 'UNIQUE'
        GROUP BY tc.CONSTRAINT_NAME
    ) constraint_columns
    WHERE constraint_columns.columns_csv = 'leader_address'
    LIMIT 1
);

SET @drop_leader_address_unique := IF(
    @leader_address_unique IS NOT NULL,
    CONCAT('ALTER TABLE copy_trading_leaders DROP INDEX ', @leader_address_unique),
    'SELECT 1'
);
PREPARE drop_leader_address_unique_stmt FROM @drop_leader_address_unique;
EXECUTE drop_leader_address_unique_stmt;
DEALLOCATE PREPARE drop_leader_address_unique_stmt;

SET @has_leader_address_category := (
    SELECT COUNT(*)
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'copy_trading_leaders'
      AND INDEX_NAME = 'uk_leader_address_category'
);
SET @add_leader_address_category := IF(
    @has_leader_address_category = 0,
    'ALTER TABLE copy_trading_leaders ADD UNIQUE KEY uk_leader_address_category (leader_address, category)',
    'SELECT 1'
);
PREPARE add_leader_address_category_stmt FROM @add_leader_address_category;
EXECUTE add_leader_address_category_stmt;
DEALLOCATE PREPARE add_leader_address_category_stmt;

SET @has_leader_category_rank := (
    SELECT COUNT(*)
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'copy_trading_leaders'
      AND INDEX_NAME = 'idx_leader_category_rank'
);
SET @add_leader_category_rank := IF(
    @has_leader_category_rank = 0,
    'ALTER TABLE copy_trading_leaders ADD INDEX idx_leader_category_rank (category, smart_money_rank)',
    'SELECT 1'
);
PREPARE add_leader_category_rank_stmt FROM @add_leader_category_rank;
EXECUTE add_leader_category_rank_stmt;
DEALLOCATE PREPARE add_leader_category_rank_stmt;

SET @has_leader_category_win_rate := (
    SELECT COUNT(*)
    FROM information_schema.STATISTICS
    WHERE TABLE_SCHEMA = DATABASE()
      AND TABLE_NAME = 'copy_trading_leaders'
      AND INDEX_NAME = 'idx_leader_category_win_rate'
);
SET @add_leader_category_win_rate := IF(
    @has_leader_category_win_rate = 0,
    'ALTER TABLE copy_trading_leaders ADD INDEX idx_leader_category_win_rate (category, win_rate)',
    'SELECT 1'
);
PREPARE add_leader_category_win_rate_stmt FROM @add_leader_category_win_rate;
EXECUTE add_leader_category_win_rate_stmt;
DEALLOCATE PREPARE add_leader_category_win_rate_stmt;

UPDATE markets
SET category = CASE
    WHEN LOWER(category) LIKE '%politic%' OR LOWER(category) LIKE '%election%' THEN 'politics'
    WHEN LOWER(category) LIKE '%sport%' THEN 'sports'
    WHEN LOWER(category) LIKE '%crypto%' THEN 'crypto'
    WHEN LOWER(category) LIKE '%financial%' OR LOWER(category) LIKE '%finance%' THEN 'finance'
    ELSE category
END
WHERE category IS NOT NULL;
