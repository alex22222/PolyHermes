-- Expand finance market inference so leader discovery can find business,
-- macro, equity, and commodity markets beyond the small Gamma category slice.
UPDATE markets
SET category = 'finance'
WHERE active = 1
  AND closed = 0
  AND LOWER(CONCAT_WS(' ', title, slug, description)) REGEXP
      'fed|interest rate|inflation|cpi|recession|nasdaq|s&p|s&p 500|stock|ipo|gdp|treasury|oil price|unemployment|payroll|nfp|earnings|revenue|quarter|gross domestic product|spx|dow jones|russell 2000|vix|bond|bonds|yield|rate cut|rate hike|fomc|jobless claims|pce|ppi|mortgage|market cap|valuation|valued|sales|profit|eps|guidance|dividend|buyback|bankruptcy|acquisition|merger|sec|etf|gold|silver|copper|crude oil|brent|wti|natural gas|tesla|tsla|nvidia|nvda|apple|aapl|microsoft|msft|meta|amazon|amzn|google|alphabet|googl|openai|anthropic|spacex|waymo|stripe|databricks|palantir|pltr';
