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

    fun inferMarketCategory(vararg values: String?): String? {
        values.asSequence()
            .mapNotNull { it?.lowercase() }
            .flatMap { sequenceOf(it, it.replace("-", " ").replace("_", " ")) }
            .forEach { text ->
                normalizeCategory(text)?.let { return it }

                if (
                    text.contains("trump") || text.contains("biden") ||
                    text.contains("election") || text.contains("president") ||
                    text.contains("congress") || text.contains("senate") ||
                    text.contains("supreme court") || text.contains("tariff") ||
                    text.contains("taiwan") || text.contains("china") ||
                    text.contains("israel") || text.contains("iran") ||
                    text.contains("ukraine") || text.contains("russia")
                ) {
                    return "politics"
                }

                if (
                    text.contains("world cup") || text.contains("fifa") ||
                    text.contains("nba") || text.contains("nfl") ||
                    text.contains("mlb") || text.contains("nhl") ||
                    text.contains("ufc") || text.contains("tennis") ||
                    text.contains("soccer") || text.contains("football") ||
                    text.contains("baseball") || text.contains("basketball") ||
                    text.contains("golf") || text.contains("championship") ||
                    text.contains("premier league") ||
                    text.contains("esports") || text.contains("e sports") ||
                    text.contains("电竞") || text.contains("电子竞技") ||
                    text.contains("counter strike") || text.contains("cs2") ||
                    text.contains("csgo") || text.contains("valorant") ||
                    text.contains("dota") || text.contains("league of legends") ||
                    text.contains(" lol ") || text.contains("overwatch") ||
                    text.contains("starcraft") || text.contains("bo3") ||
                    text.contains("bo5") || text.contains("iem ") ||
                    text.contains("major stage") || text.contains("natus vincere") ||
                    text.contains(" navi ") || text.contains(" g2 ") ||
                    text.contains("faze") || text.contains("vitality") ||
                    text.contains("over/under") || text.contains(" o/u ")
                ) {
                    return "sports"
                }

                if (
                    text.contains("bitcoin") || text.contains("btc") ||
                    text.contains("ethereum") || text.contains("eth") ||
                    text.contains("solana") || text.contains("sol ") ||
                    text.contains("xrp") || text.contains("doge") ||
                    text.contains("token") || text.contains("airdrop") ||
                    text.contains("stablecoin") || text.contains("crypto")
                ) {
                    return "crypto"
                }

                if (
                    text.contains("fed") || text.contains("interest rate") ||
                    text.contains("inflation") || text.contains("cpi") ||
                    text.contains("recession") || text.contains("nasdaq") ||
                    text.contains("s&p") || text.contains("stock") ||
                    text.contains("ipo") || text.contains("gdp") ||
                    text.contains("treasury") || text.contains("oil price")
                ) {
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
