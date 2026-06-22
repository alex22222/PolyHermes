package com.wrbug.polymarketbot.util

/**
 * 分类验证工具类
 * 用于验证分类参数是否符合项目要求（politics/sports/crypto/finance）
 */
object CategoryValidator {
    
    /**
     * 支持的分类列表
     */
    private val SUPPORTED_CATEGORIES = setOf("sports", "crypto", "finance", "politics")
    
    /**
     * 分类名称映射（将 Polymarket API 返回的分类名称映射到标准分类）
     */
    private val CATEGORY_MAPPING = mapOf(
        "sports" to "sports",
        "crypto" to "crypto",
        "cryptocurrency" to "crypto",
        "cryptocurrencies" to "crypto",
        "finance" to "finance",
        "financial" to "finance",
        "politics" to "politics",
        "political" to "politics"
    )
    
    /**
     * 验证分类是否有效（支持精确匹配和关键字匹配）
     * @param category 分类名称
     * @return 是否有效
     */
    fun isValid(category: String?): Boolean {
        if (category == null) {
            return false
        }
        
        val categoryLower = category.lowercase()
        
        // 精确匹配
        if (categoryLower in SUPPORTED_CATEGORIES) {
            return true
        }
        
        // 映射匹配
        if (categoryLower in CATEGORY_MAPPING.keys) {
            return true
        }
        
        // 关键字匹配
        if (categoryLower.contains("sport")) {
            return true
        }
        if (categoryLower.contains("crypto")) {
            return true
        }
        if (categoryLower.contains("finance") || categoryLower.contains("financial")) {
            return true
        }
        if (categoryLower.contains("politic") || categoryLower.contains("election")) {
            return true
        }
        
        return false
    }
    
    /**
     * 标准化分类名称
     * @param category 原始分类名称
     * @return 标准化后的分类名称（politics/sports/crypto/finance）
     */
    fun normalizeCategory(category: String?): String? {
        if (category == null) {
            return null
        }
        
        val categoryLower = category.lowercase()
        
        // 映射匹配
        CATEGORY_MAPPING[categoryLower]?.let {
            return it
        }
        
        // 关键字匹配
        if (categoryLower.contains("sport")) {
            return "sports"
        }
        if (categoryLower.contains("crypto")) {
            return "crypto"
        }
        if (categoryLower.contains("finance") || categoryLower.contains("financial")) {
            return "finance"
        }
        if (categoryLower.contains("politic") || categoryLower.contains("election")) {
            return "politics"
        }
        
        return null
    }


    /**
     * 体育联赛/赛事 slug 前缀识别
     */
    private fun isSportsLeagueSlug(text: String): Boolean {
        val sportsPrefixes = listOf(
            "fifwc ", "fifa ", "mlb ", "nba ", "wnba ", "nfl ", "nhl ", "ufc ",
            "atp ", "wta ", "ipl ", "pga ", "lpl ", "lck ", "cs2 ", "csgo ",
            "dota2 ", "valorant ", "overwatch ", "premier league", "champions league",
            "bundesliga", "laliga", "serie a", "ligue 1", "eredivisie", "es2 ",
            "epl ", "wcq ", "olympic", "olympics", "world cup", "esports"
        )
        return sportsPrefixes.any { prefix ->
            text.startsWith(prefix) ||
            text.contains(" $prefix") ||
            text.contains("-$prefix")
        }
    }

    /**
     * 政治/法律相关文本识别
     */
    private fun isPoliticsText(text: String): Boolean {
        val politicsKeywords = listOf(
            "trump", "biden", "election", "president", "congress", "senate",
            "supreme court", "tariff", "taiwan", "china", "israel", "iran",
            "ukraine", "russia", "putin", "weinstein", "prison", "sentenced",
            "sentence", "court", "trial", "judge", "verdict", "lawsuit",
            "attorney", "prosecutor", "defendant", "guilty",
            "convicted", "criminal", "justice",
            "senators", "representatives", "house", "bill"
        )
        return politicsKeywords.any { text.contains(it) }
    }

    /**
     * 体育术语关键词识别
     */
    private fun isSportsText(text: String): Boolean {
        val sportsKeywords = listOf(
            "world cup", "fifa", "nba", "nfl", "mlb", "nhl", "ufc", "tennis",
            "soccer", "football", "baseball", "basketball", "golf", "championship",
            "premier league", "esports", "e sports", "counter strike", "cs2", "csgo",
            "valorant", "dota", "league of legends", " lol ", "overwatch",
            "starcraft", "bo3", "bo5", "iem ", "major stage", "natus vincere",
            " navi ", " g2 ", "faze", "vitality", "over/under", " o/u ",
            "spread", "exact score", "halftime", "draw", "win on", "btts",
            "team total", "leading at", "clean sheet", "first goal",
            "red card", "penalty", "overtime", "full time", "match winner",
            "moneyline", "points", "score", "winner"
        )
        return sportsKeywords.any { text.contains(it) }
    }

    /**
     * 加密货币关键词识别
     */
    private fun isCryptoText(text: String): Boolean {
        val cryptoKeywords = listOf(
            "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "xrp", "doge",
            "dogecoin", "airdrop", "stablecoin", "crypto", "blockchain", "defi",
            "nft", "altcoin", "memecoin", "layer2", "rollup", "token", "tokens"
        )
        return cryptoKeywords.any { text.contains(it) }
    }

    /**
     * 金融关键词识别
     */
    private fun isFinanceText(text: String): Boolean {
        val financeKeywords = listOf(
            "fed", "interest rate", "inflation", "cpi", "recession", "nasdaq",
            "s&p", "stock", "ipo", "gdp", "treasury", "oil price", "unemployment",
            "payroll", "nfp", "earnings", "revenue", "quarter", "q1", "q2", "q3",
            "q4", "gross domestic product", "spx", "s&p 500", "dow jones",
            "russell 2000", "vix", "bond", "bonds", "yield", "rate cut",
            "rate hike", "fomc", "jobless claims", "pce", "ppi", "mortgage",
            "market cap", "valuation", "valued", "sales", "profit", "eps",
            "guidance", "dividend", "buyback", "bankruptcy", "acquisition",
            "merger", "sec", "etf", "gold", "silver", "copper", "crude oil",
            "brent", "wti", "natural gas", "tesla", "tsla", "nvidia", "nvda",
            "apple", "aapl", "microsoft", "msft", "meta", "amazon", "amzn",
            "google", "alphabet", "googl", "openai", "anthropic", "spacex",
            "waymo", "stripe", "databricks", "palantir", "pltr"
        )
        return financeKeywords.any { text.contains(it) }
    }

    fun inferMarketCategory(vararg values: String?): String? {
        val texts = values.asSequence()
            .mapNotNull { it?.lowercase() }
            .flatMap { sequenceOf(it, it.replace("-", " ").replace("_", " ")) }
            .toList()

        // 1. API 返回的 category / event category 标准化
        for (text in texts) {
            normalizeCategory(text)?.let { return it }
        }

        // 2. 体育联赛/赛事 slug 前缀（高置信度）
        for (text in texts) {
            if (isSportsLeagueSlug(text)) {
                return "sports"
            }
        }

        // 3. 政治/法律关键词
        for (text in texts) {
            if (isPoliticsText(text)) {
                return "politics"
            }
        }

        // 4. 体育术语关键词
        for (text in texts) {
            if (isSportsText(text)) {
                return "sports"
            }
        }

        // 5. 加密货币关键词
        for (text in texts) {
            if (isCryptoText(text)) {
                return "crypto"
            }
        }

        // 6. 金融关键词
        for (text in texts) {
            if (isFinanceText(text)) {
                return "finance"
            }
        }

        return null
    }
    
    /**
     * 验证分类，如果无效则抛出异常
     * @param category 分类名称
     * @throws IllegalArgumentException 如果分类无效
     */
    fun validate(category: String?) {
        if (!isValid(category)) {
            throw IllegalArgumentException("不支持的分类: $category，仅支持: ${SUPPORTED_CATEGORIES.joinToString(", ")}")
        }
    }
    
    /**
     * 获取所有支持的分类
     * @return 支持的分类列表
     */
    fun getSupportedCategories(): Set<String> {
        return SUPPORTED_CATEGORIES
    }
}
