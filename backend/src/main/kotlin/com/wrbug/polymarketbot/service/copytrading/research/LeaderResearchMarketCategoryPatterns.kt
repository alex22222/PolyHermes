package com.wrbug.polymarketbot.service.copytrading.research

object LeaderResearchMarketCategoryPatterns {
    val patterns: Map<String, String> = mapOf(
        "politics" to "(election|president|senate|congress|parliament|trump|biden|democrat|republican|israel|ukraine|russia|taiwan|military-clash|tariff|war|ceasefire|nato|iran|gaza|minister|court|supreme|nominee|governor|mayor|primary|hezbollah|lebanon|crimea|colombian|diplomatic|netanyahu|white-house|truth-social)",
        "finance" to "(the-fed|fed-rate|feds-upper|rate-cut|rate-cuts|rate-hike|interest-rate|interest-rates|inflation|cpi|ppi|gdp|recession|tariff|dollar|treasury|nasdaq|dow-jones|sp500|s-p-500|spx|stock-market|stock|earnings|revenue|sales|market-cap|market cap|ipo|crude-oil|wti|gold|unemployment|jobs|fomc|yield)",
        "sports" to "(fifwc|fifa|world-cup|world cup|team-to-advance|win on 20[0-9]{2}-[0-9]{2}-[0-9]{2}|end in a draw|top goalscorer|nba|nfl|mlb|nhl|epl|uefa|champions-league|soccer|football|basketball|baseball|hockey|tennis|ufc|esports|e-sports)",
        "crypto" to "(bitcoin|btc|ethereum|eth|solana|sol|xrp|doge|crypto|cryptocurrency|binance|coinbase|usdt|stablecoin)"
    )

    fun contains(category: String): Boolean = category in patterns

    fun patternFor(category: String): String = patterns.getValue(category)

    fun matches(category: String, market: String): Boolean {
        val pattern = patterns[category] ?: return false
        return Regex(pattern).containsMatchIn(market.lowercase())
    }
}
