UPDATE markets
SET category = CASE
    WHEN LOWER(CONCAT_WS(' ', title, slug, event_slug, description)) REGEXP 'trump|biden|election|president|congress|senate|supreme court|tariff|taiwan|china|israel|iran|ukraine|russia'
        THEN 'politics'
    WHEN LOWER(CONCAT_WS(' ', title, slug, event_slug, description)) REGEXP 'world cup|fifa|nba|nfl|mlb|nhl|ufc|tennis|soccer|football|baseball|basketball|golf|championship|premier league'
        THEN 'sports'
    WHEN LOWER(CONCAT_WS(' ', title, slug, event_slug, description)) REGEXP 'bitcoin|btc|ethereum|eth|solana|xrp|doge|token|airdrop|stablecoin|crypto'
        THEN 'crypto'
    WHEN LOWER(CONCAT_WS(' ', title, slug, event_slug, description)) REGEXP 'fed|interest rate|inflation|cpi|recession|nasdaq|s&p|stock|ipo|gdp|treasury|oil price'
        THEN 'finance'
    ELSE category
END
WHERE category IS NULL OR category NOT IN ('politics', 'sports', 'crypto', 'finance');
