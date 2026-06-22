-- ============================================
-- V57: 修复市场分类推断错误
-- 解决大量体育/政治市场被错误标记为 crypto 的问题
-- ============================================

-- 重新推断 markets.category，覆盖以下情况：
-- 1. category 为空或不合法
-- 2. category='crypto' 但 slug/标题明显属于 sports/politics
--
-- 推断优先级（与 CategoryValidator.inferMarketCategory 保持一致）：
-- 1. 体育联赛/赛事 slug 前缀（最高优先级）
-- 2. 政治/法律关键词
-- 3. 体育术语关键词
-- 4. 加密货币关键词
-- 5. 金融关键词
-- 6. 保持原值
UPDATE markets
SET category = CASE
    WHEN LOWER(slug) REGEXP '^(fifwc|fifa|mlb|nba|wnba|nfl|nhl|ufc|atp|wta|ipl|pga|lpl|lck|cs2|csgo|dota2|valorant|overwatch|epl|wcq|es2|esports)'
        THEN 'sports'
    WHEN LOWER(CONCAT_WS(' ', title, slug, event_slug, description)) REGEXP
        'trump|biden|election|president|congress|senate|supreme court|tariff|taiwan|china|israel|iran|ukraine|russia|putin|weinstein|prison|sentenced|sentence|court|trial|judge|verdict|lawsuit|attorney|prosecutor|defendant|guilty|convicted|criminal|justice|senators|representatives|house|bill'
        THEN 'politics'
    WHEN LOWER(CONCAT_WS(' ', title, slug, event_slug, description)) REGEXP
        'world cup|fifa|nba|nfl|mlb|nhl|ufc|tennis|soccer|football|baseball|basketball|golf|championship|premier league|esports|e-sports|e sports|counter-strike|counter strike|cs2|csgo|valorant|dota|league of legends|overwatch|starcraft|bo3|bo5|iem |major stage|natus vincere| navi | g2 |faze|vitality|over/under| o/u |spread|exact score|halftime|draw|win on|btts|team total|total|leading at|clean sheet|first goal|red card|penalty|overtime|full time|match winner|moneyline|points'
        THEN 'sports'
    WHEN LOWER(CONCAT_WS(' ', title, slug, event_slug, description)) REGEXP
        'bitcoin|btc|ethereum|eth|solana|sol|xrp|doge|dogecoin|airdrop|stablecoin|crypto|blockchain|defi|nft|altcoin|memecoin|layer2|rollup|token|tokens'
        THEN 'crypto'
    WHEN LOWER(CONCAT_WS(' ', title, slug, event_slug, description)) REGEXP
        'fed|interest rate|inflation|cpi|recession|nasdaq|s&p|stock|ipo|gdp|treasury|oil price|unemployment|payroll|nfp|earnings|revenue|quarter|q1|q2|q3|q4|gross domestic product|spx'
        THEN 'finance'
    ELSE category
END
WHERE category IS NULL
   OR category NOT IN ('politics', 'sports', 'crypto', 'finance')
   OR (category = 'crypto' AND (
        LOWER(slug) REGEXP '^(fifwc|fifa|mlb|nba|wnba|nfl|nhl|ufc|atp|wta|ipl|pga|lpl|lck|cs2|csgo|dota2|valorant|overwatch|epl|wcq|es2|esports)'
        OR LOWER(CONCAT_WS(' ', title, slug, event_slug, description)) REGEXP
            'world cup|fifa|nba|nfl|mlb|nhl|ufc|tennis|soccer|football|baseball|basketball|golf|championship|premier league|esports|e-sports|e sports|counter-strike|counter strike|cs2|csgo|valorant|dota|league of legends|overwatch|starcraft|bo3|bo5|iem |major stage|natus vincere| navi | g2 |faze|vitality|over/under| o/u |spread|exact score|halftime|draw|win on|btts|team total|total|leading at|clean sheet|first goal|red card|penalty|overtime|full time|match winner|moneyline|points|trump|biden|election|president|congress|senate|supreme court|tariff|taiwan|china|israel|iran|ukraine|russia|putin|weinstein|prison|sentenced|sentence|court|trial|judge|verdict|lawsuit|attorney|prosecutor|defendant|guilty|convicted|criminal|justice|senators|representatives|house|bill'
   ));
