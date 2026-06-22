package com.wrbug.polymarketbot.service.copytrading.leaders

import com.google.gson.Gson
import com.wrbug.polymarketbot.api.MarketResponse
import com.wrbug.polymarketbot.api.TradeResponse
import com.wrbug.polymarketbot.repository.LeaderActivityEventRepository
import com.wrbug.polymarketbot.repository.MarketRepository
import com.wrbug.polymarketbot.util.CategoryValidator
import com.wrbug.polymarketbot.util.RetrofitFactory
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import java.util.concurrent.ConcurrentHashMap

/**
 * 从近期热门市场中发现活跃交易者钱包。
 *
 * 策略：
 * 1. 优先查询本地 leader_activity_event 中最近 N 天且 usable_for_discovery 的事件。
 * 2. 当本地事件不足时，回退到外部 API：
 *    - 从 Gamma /markets 拉取活跃市场并按类别/交易量排序
 *    - 对 Top 热门市场调用 CLOB /data/trades 获取近期成交
 *    - 从成交记录中提取交易者钱包
 *
 * 这解决了候选池先天过小的问题：活跃市场 → 活跃交易者 → 更多候选。
 */
@Service
class HotMarketTraderDiscoveryService(
    private val activityEventRepository: LeaderActivityEventRepository,
    private val marketRepository: MarketRepository,
    private val retrofitFactory: RetrofitFactory,
    private val gson: Gson
) {

    private val logger = LoggerFactory.getLogger(HotMarketTraderDiscoveryService::class.java)

    // Gamma 全量市场缓存（10 分钟）
    private var gammaMarketsCache: List<MarketResponse> = emptyList()
    private var gammaMarketsCacheAt: Long = 0
    private val gammaCacheTtlMs = 10 * 60 * 1000L

    // CLOB trades 缓存：marketConditionId -> (trades, cachedAt)，5 分钟 TTL
    private val clobTradesCache = ConcurrentHashMap<String, Pair<List<TradeResponse>, Long>>()
    private val clobCacheTtlMs = 5 * 60 * 1000L

    /**
     * @param category 目标类别
     * @param marketIds 可选的 marketId 白名单；为空时不限制
     * @param lookbackDays 回溯天数（仅用于本地 activity events）
     * @param topMarkets 取前多少个热门市场
     * @return 钱包地址到来源 market slug 的映射
     */
    fun discoverTradersFromHotMarkets(
        category: String,
        marketIds: Set<String> = emptySet(),
        lookbackDays: Int = 7,
        topMarkets: Int = 20
    ): Map<String, String?> {
        val normalizedCategory = CategoryValidator.normalizeCategory(category) ?: category.lowercase()

        // 1. 本地 activity events 路径（零外部 API 成本）
        val localResult = discoverFromLocalActivityEvents(normalizedCategory, marketIds, lookbackDays, topMarkets)

        // 2. 外部 API 补充路径
        val externalResult = if (localResult.size < topMarkets * 2) {
            try {
                discoverFromExternalHotMarkets(normalizedCategory, marketIds, topMarkets)
            } catch (e: Exception) {
                logger.warn("外部热门市场交易者发现失败: {}", e.message)
                emptyMap()
            }
        } else {
            emptyMap()
        }

        // 合并结果，本地优先
        return localResult + externalResult.filterKeys { it !in localResult }
    }

    /**
     * 从本地 activity events 发现热门市场交易者
     */
    private fun discoverFromLocalActivityEvents(
        category: String,
        marketIds: Set<String>,
        lookbackDays: Int,
        topMarkets: Int
    ): Map<String, String?> {
        val since = System.currentTimeMillis() - lookbackDays * 24 * 60 * 60 * 1000L

        val events = try {
            activityEventRepository.findByUsableForDiscoveryTrueAndEventTimeGreaterThanEqual(since)
        } catch (e: Exception) {
            logger.warn("查询 activity events 失败: {}", e.message)
            return emptyMap()
        }

        val filteredEvents = if (marketIds.isNotEmpty()) {
            events.filter { it.marketId in marketIds }
        } else {
            events.filter {
                CategoryValidator.inferMarketCategory(it.marketTitle, it.marketSlug) == category
            }
        }

        if (filteredEvents.isEmpty()) {
            logger.info("类别 {} 最近 {} 天没有可用本地 activity events", category, lookbackDays)
            return emptyMap()
        }

        val marketActivity = filteredEvents
            .groupBy { it.marketId }
            .mapValues { (_, list) -> list.size }
            .toList()
            .sortedByDescending { it.second }
            .take(topMarkets)
            .toMap()

        val walletToMarketSlug = mutableMapOf<String, String?>()
        val hotMarketIds = marketActivity.keys
        filteredEvents
            .filter { it.marketId in hotMarketIds && !it.normalizedWallet.isNullOrBlank() }
            .forEach { event ->
                val wallet = event.normalizedWallet!!.lowercase()
                if (wallet !in walletToMarketSlug) {
                    walletToMarketSlug[wallet] = event.marketSlug
                }
            }

        logger.info(
            "类别 {} 本地热门市场发现: {} 个热门市场, {} 个活跃钱包",
            category, marketActivity.size, walletToMarketSlug.size
        )
        return walletToMarketSlug
    }

    /**
     * 从 Gamma + CLOB 外部 API 发现热门市场交易者
     */
    private fun discoverFromExternalHotMarkets(
        category: String,
        marketIds: Set<String>,
        topMarkets: Int
    ): Map<String, String?> {
        return runBlocking {
            val gammaMarkets = fetchGammaMarkets()
            if (gammaMarkets.isEmpty()) {
                logger.warn("Gamma 市场列表为空，跳过外部热门市场发现")
                return@runBlocking emptyMap()
            }

            // 按类别过滤并排序
            val categoryMarkets = gammaMarkets
                .filter { market ->
                    if (marketIds.isNotEmpty()) {
                        market.conditionId in marketIds
                    } else {
                        val marketCategory = inferMarketCategory(market)
                        marketCategory == category
                    }
                }
                .filter { it.active == true && it.closed != true }
                .sortedByDescending { parseVolume(it) }
                .take(topMarkets)

            if (categoryMarkets.isEmpty()) {
                logger.info("Gamma 中未找到类别 {} 的活跃市场", category)
                return@runBlocking emptyMap()
            }

            logger.info("类别 {} 从 Gamma 选取 {} 个热门市场", category, categoryMarkets.size)

            val walletToMarketSlug = mutableMapOf<String, String?>()
            val clobApi = retrofitFactory.createClobApiWithoutAuth()

            categoryMarkets.forEachIndexed { index, market ->
                val conditionId = market.conditionId ?: return@forEachIndexed
                val slug = market.slug ?: market.events?.firstOrNull()?.slug

                try {
                    val trades = fetchClobTradesForMarket(conditionId, clobApi)
                    trades.forEach { trade ->
                        val user = trade.user?.lowercase() ?: return@forEach
                        if (user.matches(Regex("^0x[a-f0-9]{40}$")) && user !in walletToMarketSlug) {
                            walletToMarketSlug[user] = slug
                        }
                    }
                    // 简单限流，避免触发 CLOB 限流
                    if (index < categoryMarkets.size - 1) delay(150)
                } catch (e: Exception) {
                    logger.warn("获取市场 {} trades 失败: {}", conditionId, e.message)
                }
            }

            logger.info(
                "类别 {} 外部热门市场发现: {} 个市场, {} 个活跃钱包",
                category, categoryMarkets.size, walletToMarketSlug.size
            )
            walletToMarketSlug
        }
    }

    /**
     * 从 Gamma /markets 拉取活跃市场，带缓存
     */
    private suspend fun fetchGammaMarkets(): List<MarketResponse> {
        val now = System.currentTimeMillis()
        if (gammaMarketsCache.isNotEmpty() && (now - gammaMarketsCacheAt) < gammaCacheTtlMs) {
            return gammaMarketsCache
        }

        val gammaApi = retrofitFactory.createGammaApi()
        val pageSize = 200
        val maxPages = 5
        val markets = mutableListOf<MarketResponse>()

        for (page in 0 until maxPages) {
            val response = gammaApi.listMarkets(
                conditionIds = null,
                includeTag = true,
                active = true,
                closed = false,
                limit = pageSize,
                offset = page * pageSize
            )
            if (!response.isSuccessful) {
                logger.warn("Gamma /markets 请求失败: HTTP {}, page={}", response.code(), page)
                break
            }
            val pageMarkets = response.body().orEmpty()
            if (pageMarkets.isEmpty()) break
            markets += pageMarkets
            if (pageMarkets.size < pageSize) break
            delay(120)
        }

        gammaMarketsCache = markets
        gammaMarketsCacheAt = now
        logger.info("Gamma /markets 刷新: {} 个市场", markets.size)
        return markets
    }

    /**
     * 获取某个市场的 CLOB /data/trades，带缓存
     */
    private suspend fun fetchClobTradesForMarket(
        conditionId: String,
        clobApi: com.wrbug.polymarketbot.api.PolymarketClobApi
    ): List<TradeResponse> {
        val now = System.currentTimeMillis()
        clobTradesCache[conditionId]?.let { (cached, cachedAt) ->
            if ((now - cachedAt) < clobCacheTtlMs) {
                return cached
            }
        }

        val response = clobApi.getTrades(market = conditionId)
        val trades = if (response.isSuccessful) {
            response.body()?.data.orEmpty()
        } else {
            logger.debug("市场 {} CLOB trades 请求失败: HTTP {}", conditionId, response.code())
            emptyList()
        }

        clobTradesCache[conditionId] = trades to now
        return trades
    }

    /**
     * 推断市场类别：优先使用 Gamma 的 category 字段，fallback 到标题/slug 推断
     */
    private fun inferMarketCategory(market: MarketResponse): String? {
        val gammaCategory = market.category?.takeIf { it.isNotBlank() }?.lowercase()
        if (gammaCategory != null) {
            CategoryValidator.normalizeCategory(gammaCategory)?.let { return it }
        }
        return CategoryValidator.inferMarketCategory(market.question, market.slug, market.description)
    }

    private fun parseVolume(market: MarketResponse): Double {
        return market.volumeNum
            ?: market.volume?.toDoubleOrNull()
            ?: market.liquidityNum
            ?: 0.0
    }
}
