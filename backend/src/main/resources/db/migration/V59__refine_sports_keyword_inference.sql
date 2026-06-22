-- ============================================
-- V59:  refine sports keyword inference
-- 移除过于通用的体育关键词（total/team/home/away/side），
-- 这些词作为子串会命中 "conside red" / "total supply" 等非体育市场，
-- 导致真正的 crypto/finance 市场被误判为 sports。
-- 本迁移基于精简后的关键词列表重新推断所有市场分类。
-- ============================================

UPDATE markets
SET category = CASE
    WHEN LOWER(slug) REGEXP '^(fifwc|fifa|mlb|nba|wnba|nfl|nhl|ufc|atp|wta|ipl|pga|lpl|lck|cs2|csgo|dota2|valorant|overwatch|epl|wcq|es2|esports)'
        THEN 'sports'
    WHEN LOWER(CONCAT_WS(' ', title, slug, event_slug, description)) REGEXP
        'trump|biden|election|president|congress|senate|supreme court|tariff|taiwan|china|israel|iran|ukraine|russia|putin|weinstein|prison|sentenced|sentence|court|trial|judge|verdict|lawsuit|attorney|prosecutor|defendant|guilty|convicted|criminal|justice|senators|representatives|house|bill'
        THEN 'politics'
    WHEN LOWER(CONCAT_WS(' ', title, slug, event_slug, description)) REGEXP
        'world cup|fifa|nba|nfl|mlb|nhl|ufc|tennis|soccer|football|baseball|basketball|golf|championship|premier league|esports|e-sports|e sports|counter-strike|counter strike|cs2|csgo|valorant|dota|league of legends|overwatch|starcraft|bo3|bo5|iem |major stage|natus vincere| navi | g2 |faze|vitality|over/under| o/u |spread|exact score|halftime|draw|win on|btts|team total|leading at|clean sheet|first goal|red card|penalty|overtime|full time|match winner|moneyline|points|score|winner'
        THEN 'sports'
    WHEN LOWER(CONCAT_WS(' ', title, slug, event_slug, description)) REGEXP
        'bitcoin|btc|ethereum|eth|solana|sol|xrp|doge|dogecoin|airdrop|stablecoin|crypto|blockchain|defi|nft|altcoin|memecoin|layer2|rollup|token|tokens'
        THEN 'crypto'
    WHEN LOWER(CONCAT_WS(' ', title, slug, event_slug, description)) REGEXP
        'fed|interest rate|inflation|cpi|recession|nasdaq|s&p|stock|ipo|gdp|treasury|oil price|unemployment|payroll|nfp|earnings|revenue|quarter|q1|q2|q3|q4|gross domestic product|spx'
        THEN 'finance'
    ELSE category
END;
