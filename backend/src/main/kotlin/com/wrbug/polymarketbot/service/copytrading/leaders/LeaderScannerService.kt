package com.wrbug.polymarketbot.service.copytrading.leaders

import com.google.gson.Gson
import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.wrbug.polymarketbot.api.PolymarketDataApi
import com.wrbug.polymarketbot.api.PositionResponse
import com.wrbug.polymarketbot.api.UserActivityResponse
import com.wrbug.polymarketbot.dto.LeaderScanBatchResponse
import com.wrbug.polymarketbot.dto.LeaderScanPreviewResponse
import com.wrbug.polymarketbot.dto.LeaderScanResultItem
import com.wrbug.polymarketbot.entity.Leader
import com.wrbug.polymarketbot.entity.LeaderScannerCandidatePool
import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import com.wrbug.polymarketbot.repository.LeaderActivityEventRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.repository.LeaderScannerCandidatePoolRepository
import com.wrbug.polymarketbot.repository.MarketRepository
import com.wrbug.polymarketbot.repository.SystemConfigRepository
import com.wrbug.polymarketbot.service.common.MarketService
import com.wrbug.polymarketbot.util.CategoryValidator
import com.wrbug.polymarketbot.util.RetrofitFactory
import kotlinx.coroutines.async
import kotlinx.coroutines.awaitAll
import kotlinx.coroutines.delay
import kotlinx.coroutines.runBlocking
import kotlinx.coroutines.sync.Semaphore
import kotlinx.coroutines.sync.withPermit
import org.slf4j.LoggerFactory
import org.springframework.data.domain.PageRequest
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Propagation
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal
import java.math.RoundingMode
import java.util.concurrent.atomic.AtomicInteger

/**
 * Leader 扫描服务（两层扫描版）
 *
 * 第一层（廉价发现）：从 activity events、bridge records、seed wallets、热门市场、现有 leader 等来源
 * 持续发现候选钱包，沉淀到 leader_scanner_candidate_pool，不调用 Data API。
 *
 * 第二层（昂贵分析）：从 candidate_pool 中读取 PENDING 候选，按 discovery_score 排序，
 * 最多分析 MAX_WALLETS_PER_CATEGORY 个，计算 PnL/胜率/活跃度，Top N 写入 copy_trading_leaders。
 *
 * 这样可以把候选池从“系统已见过的钱包”扩展到几十/几百个，同时控制 Data API 调用量。
 */
@Service
class LeaderScannerService(
    private val leaderRepository: LeaderRepository,
    private val marketRepository: MarketRepository,
    private val candidateRepository: LeaderResearchCandidateRepository,
    private val activityEventRepository: LeaderActivityEventRepository,
    private val bridgeTradeRecordRepository: BridgeTradeRecordRepository,
    private val systemConfigRepository: SystemConfigRepository,
    private val marketService: MarketService,
    private val candidatePoolRepository: LeaderScannerCandidatePoolRepository,
    private val hotMarketTraderDiscoveryService: HotMarketTraderDiscoveryService,
    private val gson: Gson,
    private val retrofitFactory: RetrofitFactory
) {

    private val logger = LoggerFactory.getLogger(LeaderScannerService::class.java)

    // 并发控制：同时最多 5 个 Data API 请求，避免限流
    private val apiSemaphore = Semaphore(5)

    // 每类扫描钱包上限（第二层昂贵分析）
    private val MAX_WALLETS_PER_CATEGORY = 50

    // 每类最终保留 Top N
    private val TOP_N_PER_CATEGORY = 10

    // 候选池每类最大 PENDING 数量，防止无限膨胀
    private val MAX_PENDING_PER_CATEGORY = 500

    // 胜率排名最低样本数，避免 1 笔交易 100% 胜率误占榜首
    private val MIN_TRADES_FOR_RANK = 5

    private val SCAN_CATEGORIES = listOf("politics", "sports", "crypto", "finance")

    // Data API 调用间隔（毫秒）
    private val API_CALL_DELAY_MS = 300L

    // 分析时间窗口：默认 30 天，可通过 SystemConfig leader_scanner.analysis_window_days 覆盖
    private val DEFAULT_ANALYSIS_WINDOW_DAYS = 30L

    private fun getAnalysisWindowMs(): Long {
        return try {
            val config = systemConfigRepository.findByConfigKey("leader_scanner.analysis_window_days")
            val days = config?.configValue?.toLongOrNull() ?: DEFAULT_ANALYSIS_WINDOW_DAYS
            days * 24 * 60 * 60 * 1000
        } catch (e: Exception) {
            DEFAULT_ANALYSIS_WINDOW_DAYS * 24 * 60 * 60 * 1000
        }
    }

    // 扫描状态（简单内存标记，如需持久化可扩展）
    @Volatile
    private var scanRunning = false

    @Volatile
    private var lastScanAt: Long? = null

    @Volatile
    private var lastScanDurationMs: Long? = null

    @Volatile
    private var lastScanResult: String? = null

    /**
     * 获取当前扫描状态
     */
    fun getStatus(): Triple<Boolean, Long?, Long?> = Triple(scanRunning, lastScanAt, lastScanDurationMs)

    /**
     * 执行批量扫描（全部类别或指定类别）= 发现 + 分析
     * @param targetCategory 指定类别，null 表示 politics/sports/crypto/finance 全部 4 类
     * @param dryRun true 只返回预览，不写入数据库
     * @return 扫描结果
     */
    @Transactional
    fun scan(targetCategory: String? = null, dryRun: Boolean = false): LeaderScanBatchResponse {
        val startTime = System.currentTimeMillis()
        if (scanRunning) {
            return LeaderScanBatchResponse(
                success = false,
                message = "扫描任务正在运行中，请稍后再试"
            )
        }

        scanRunning = true
        try {
            val categories = normalizeCategories(targetCategory)
            val createdCount = AtomicInteger(0)
            val updatedCount = AtomicInteger(0)
            val allPreviews = mutableListOf<LeaderScanPreviewResponse>()

            for (category in categories) {
                try {
                    // 1) 先执行廉价发现，把候选沉淀到 candidate_pool
                    val discoveredCount = discoverOnly(category)
                    // 2) 再执行昂贵分析，从 pool 中读取并分析
                    val preview = analyzeOnly(category, dryRun)
                    allPreviews += preview
                    if (!dryRun) {
                        val (created, updated) = persistTopLeaders(category, preview.candidates)
                        createdCount.addAndGet(created)
                        updatedCount.addAndGet(updated)
                    }
                    logger.info(
                        "类别 {} 扫描完成: 新发现 {}, 分析 {}, Top {}",
                        category, discoveredCount, preview.analyzedWalletCount, preview.candidates.size
                    )
                } catch (e: Exception) {
                    logger.error("扫描类别 {} 失败: {}", category, e.message, e)
                }
            }

            val duration = System.currentTimeMillis() - startTime
            lastScanAt = startTime
            lastScanDurationMs = duration
            lastScanResult = if (dryRun) "preview" else "created=${createdCount.get()}, updated=${updatedCount.get()}"

            return LeaderScanBatchResponse(
                success = true,
                message = if (dryRun) {
                    "扫描预览完成，共 ${categories.size} 个类别，候选 ${allPreviews.sumOf { it.candidates.size }} 个"
                } else {
                    "扫描完成，候选 ${allPreviews.sumOf { it.candidates.size }} 个，新建 ${createdCount.get()} 个，更新 ${updatedCount.get()} 个"
                },
                createdCount = if (dryRun) 0 else createdCount.get(),
                updatedCount = if (dryRun) 0 else updatedCount.get(),
                categories = categories,
                previews = allPreviews,
                totalCandidateCount = allPreviews.sumOf { it.candidates.size },
                totalAnalyzedWalletCount = allPreviews.sumOf { it.analyzedWalletCount },
                durationMs = duration
            )
        } catch (e: Exception) {
            logger.error("扫描任务异常", e)
            return LeaderScanBatchResponse(
                success = false,
                message = "扫描失败: ${e.message}"
            )
        } finally {
            scanRunning = false
        }
    }

    /**
     * 仅执行廉价发现层：把候选钱包写入 candidate_pool，不调用 Data API。
     * 适合高频调度（如每小时一次）。
     * @return 本次新发现（写入或更新）的候选数量
     */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    fun discoverOnly(targetCategory: String? = null): Int {
        val categories = normalizeCategories(targetCategory)
        var totalDiscovered = 0
        for (category in categories) {
            try {
                val marketIds = resolveMarketIds(category)
                if (marketIds.isEmpty()) {
                    logger.warn("类别 {} 没有可用市场 ID，跳过发现", category)
                    continue
                }
                val discovered = discoverCandidatesToPool(category, marketIds)
                totalDiscovered += discovered
                logger.info("类别 {} 发现层完成，写入/更新 {} 个候选", category, discovered)
            } catch (e: Exception) {
                logger.error("类别 {} 发现层失败: {}", category, e.message, e)
            }
        }
        return totalDiscovered
    }

    /**
     * 仅执行昂贵分析层：从 candidate_pool 读取 PENDING 候选，调用 Data API 分析，
     * 返回预览结果（dryRun=true 时不写入 Leader 表）。
     */
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    fun analyzeOnly(targetCategory: String? = null, dryRun: Boolean = false): LeaderScanPreviewResponse {
        val category = normalizeCategories(targetCategory).firstOrNull()
            ?: throw IllegalArgumentException("必须指定单一类别进行分析")
        return runBlocking {
            val marketIds = resolveMarketIds(category)
            if (marketIds.isEmpty()) {
                logger.warn("类别 {} 没有可用市场 ID，跳过分析", category)
                return@runBlocking LeaderScanPreviewResponse(
                    category = category,
                    candidates = emptyList(),
                    marketCount = 0,
                    analyzedWalletCount = 0
                )
            }

            // 从 candidate_pool 读取 PENDING 候选，按 discovery_score 排序
            var pendingCandidates = readPendingCandidatesFromPool(category)

            // 如果池子为空，回退到旧的内存发现源（兼容首次部署或数据为空的情况）
            if (pendingCandidates.isEmpty()) {
                logger.warn("类别 {} 候选池为空，回退到内存发现源", category)
                val fallbackWallets = discoverWalletsLegacy(category, marketIds)
                pendingCandidates = fallbackWallets.map {
                    LeaderScannerCandidatePool(
                        category = category,
                        normalizedWallet = it,
                        source = "FALLBACK",
                        discoveryScore = 1
                    )
                }
            }

            // 限制分析数量
            val walletsToAnalyze = pendingCandidates.take(MAX_WALLETS_PER_CATEGORY)
            logger.info("类别 {} 分析层将处理 {} 个候选钱包", category, walletsToAnalyze.size)

            // 对每个候选做 API 分析
            val analyzed = walletsToAnalyze.mapIndexed { index, candidate ->
                async {
                    delay(index * API_CALL_DELAY_MS)
                    analyzeWalletAndUpdatePool(candidate, marketIds)
                }
            }.awaitAll().filterNotNull()

            // 评分排序
            val scored = scoreAndRank(analyzed, category)
            val topN = scored.take(TOP_N_PER_CATEGORY)

            logger.info("类别 {} 分析完成，Top {}: {}", category, topN.size, topN.map { it.leaderAddress.take(8) + "..." })

            LeaderScanPreviewResponse(
                category = category,
                candidates = topN,
                marketCount = marketIds.size,
                analyzedWalletCount = analyzed.size
            )
        }
    }

    private fun normalizeCategories(targetCategory: String?): List<String> {
        return if (targetCategory != null) {
            listOf(CategoryValidator.normalizeCategory(targetCategory) ?: targetCategory)
        } else {
            SCAN_CATEGORIES
        }
    }

    /**
     * 解析某类别下的活跃市场 ID
     */
    private fun resolveMarketIds(category: String): Set<String> {
        var markets = marketRepository.findByCategoryAndActiveTrueAndClosedFalse(category)
        val marketIds = if (markets.isNotEmpty()) {
            markets.map { it.marketId }.toSet()
        } else {
            logger.warn("类别 {} 的 markets 表为空，尝试从 Gamma API 同步活跃市场", category)
            val syncedCount = runBlocking { marketService.fetchAndSaveActiveMarkets() }
            if (syncedCount > 0) {
                markets = marketRepository.findByCategoryAndActiveTrueAndClosedFalse(category)
                if (markets.isNotEmpty()) {
                    markets.map { it.marketId }.toSet()
                } else {
                    logger.warn("类别 {} 同步后仍无匹配市场，将分析所有数据（不限制 category）", category)
                    emptySet()
                }
            } else {
                logger.warn("类别 {} 同步活跃市场失败，将分析所有数据（不限制 category）", category)
                emptySet()
            }
        }
        return if (marketIds.isNotEmpty()) {
            marketIds
        } else {
            inferMarketIdsFromActivityEvents(category)
        }
    }

    private fun inferMarketIdsFromActivityEvents(category: String): Set<String> {
        return try {
            activityEventRepository.findAll()
                .filter { event ->
                    CategoryValidator.inferMarketCategory(event.marketTitle, event.marketSlug) == category
                }
                .mapNotNull { it.marketId?.takeIf { marketId -> marketId.isNotBlank() } }
                .toSet()
                .also { logger.info("类别 {} 从 activity events 推断 {} 个 marketId", category, it.size) }
        } catch (e: Exception) {
            logger.warn("类别 {} 从 activity events 推断 marketId 失败: {}", category, e.message)
            emptySet()
        }
    }

    /**
     * 从 candidate_pool 读取 PENDING 候选，按 discovery_score 降序
     */
    private fun readPendingCandidatesFromPool(category: String): List<LeaderScannerCandidatePool> {
        return try {
            candidatePoolRepository.findByCategoryAndAnalysisStateOrderByDiscoveryScoreDesc(
                category,
                "PENDING",
                PageRequest.of(0, MAX_WALLETS_PER_CATEGORY)
            ).content
        } catch (e: Exception) {
            logger.warn("读取候选池失败: {}", e.message)
            emptyList()
        }
    }

    /**
     * 多源发现候选钱包并写入 candidate_pool
     */
    private fun discoverCandidatesToPool(category: String, marketIds: Set<String>): Int {
        val now = System.currentTimeMillis()
        val discoveredWallets = mutableMapOf<String, Pair<String, String?>>()

        // 源 0: bridge_trade_record
        try {
            bridgeTradeRecordRepository.findByRawPayloadIsNotNull()
                .flatMap { extractWalletsFromPayload(it.rawPayload) }
                .forEach { discoveredWallets[it.lowercase()] = "BRIDGE_RECORD" to null }
        } catch (e: Exception) {
            logger.warn("Bridge trade record 查询失败: {}", e.message)
        }

        // 源 1: activity events
        try {
            val events = if (marketIds.isNotEmpty()) {
                activityEventRepository.findAll().filter { it.marketId in marketIds }
            } else {
                activityEventRepository.findAll().filter {
                    CategoryValidator.inferMarketCategory(it.marketTitle, it.marketSlug) == category
                }
            }
            events.forEach { event ->
                val wallet = event.normalizedWallet?.lowercase() ?: return@forEach
                discoveredWallets[wallet] = "ACTIVITY_EVENT" to (event.marketSlug ?: event.marketId)
            }
        } catch (e: Exception) {
            logger.warn("Activity event 查询失败: {}", e.message)
        }

        // 源 2: 现有 Leader
        try {
            leaderRepository.findByCategory(category)
                .map { it.leaderAddress.lowercase() }
                .forEach { discoveredWallets[it] = "EXISTING_LEADER" to null }
        } catch (e: Exception) {
            logger.warn("Leader 查询失败: {}", e.message)
        }

        // 源 3: research candidate
        try {
            candidateRepository.findAll()
                .mapNotNull { it.normalizedWallet?.lowercase() }
                .forEach { discoveredWallets[it] = "RESEARCH_CANDIDATE" to null }
        } catch (e: Exception) {
            logger.warn("Research candidate 查询失败: {}", e.message)
        }

        // 源 4: 按类别 seed wallets
        try {
            val seedConfig = systemConfigRepository.findByConfigKey("leader_scanner.seed_wallets.$category")?.configValue
            if (!seedConfig.isNullOrBlank()) {
                seedConfig.split(",", "\n", ";", " ", "\t")
                    .map { it.trim().lowercase() }
                    .filter { it.matches(Regex("^0x[a-f0-9]{40}$")) }
                    .forEach { discoveredWallets[it] = "SEED_WALLET" to category }
            }
        } catch (e: Exception) {
            logger.warn("Seed config 读取失败: {}", e.message)
        }

        // 源 5: 通用 seed wallets
        try {
            val generalSeed = systemConfigRepository.findByConfigKey("leader_scanner.seed_wallets")?.configValue
            if (!generalSeed.isNullOrBlank()) {
                generalSeed.split(",", "\n", ";", " ", "\t")
                    .map { it.trim().lowercase() }
                    .filter { it.matches(Regex("^0x[a-f0-9]{40}$")) }
                    .forEach { discoveredWallets[it] = "SEED_WALLET" to "general" }
            }
        } catch (e: Exception) {
            logger.warn("通用 seed config 读取失败: {}", e.message)
        }

        // 源 6: 热门市场交易者
        try {
            val hotMarketWallets = hotMarketTraderDiscoveryService.discoverTradersFromHotMarkets(
                category = category,
                marketIds = marketIds,
                lookbackDays = 7,
                topMarkets = 20
            )
            hotMarketWallets.forEach { (wallet, marketSlug) ->
                discoveredWallets[wallet] = "HOT_MARKET" to marketSlug
            }
        } catch (e: Exception) {
            logger.warn("热门市场交易者发现失败: {}", e.message)
        }

        // 过滤无效地址
        val invalidWallets = setOf("0x2791bca1f2de4661ed88a30c99a7a9449aa84174")
        val filtered = discoveredWallets.filterKeys { it !in invalidWallets }

        // 写入/更新 candidate_pool
        var upsertCount = 0
        val existing = candidatePoolRepository.findByCategoryOrderByDiscoveryScoreDesc(category)
            .associateBy { it.normalizedWallet }

        // 如果已有 PENDING 超过上限，只更新已存在的，不新增，避免无限膨胀
        val pendingCount = candidatePoolRepository.countByCategoryAndAnalysisState(category, "PENDING")
        val allowNew = pendingCount < MAX_PENDING_PER_CATEGORY

        filtered.forEach { (wallet, sourceInfo) ->
            val (source, detail) = sourceInfo
            val existingItem = existing[wallet]
            if (existingItem != null) {
                // 若已分析/拒绝超过 7 天未更新，重置为 PENDING 以便重新分析
                val oneWeek = 7 * 24 * 60 * 60 * 1000L
                val shouldRefresh = existingItem.analysisState in setOf("ANALYZED", "REJECTED")
                        && (now - existingItem.updatedAt) > oneWeek
                candidatePoolRepository.save(
                    existingItem.copy(
                        discoveryScore = existingItem.discoveryScore + 1,
                        lastSeenAt = now,
                        updatedAt = now,
                        analysisState = if (shouldRefresh) "PENDING" else existingItem.analysisState,
                        sourceDetail = detail ?: existingItem.sourceDetail
                    )
                )
                upsertCount++
            } else if (allowNew) {
                candidatePoolRepository.save(
                    LeaderScannerCandidatePool(
                        category = category,
                        normalizedWallet = wallet,
                        source = source,
                        sourceDetail = detail,
                        discoveryScore = if (source == "SEED_WALLET") 100 else 1,
                        firstDiscoveredAt = now,
                        lastSeenAt = now,
                        analysisState = "PENDING",
                        createdAt = now,
                        updatedAt = now
                    )
                )
                upsertCount++
            }
        }

        logger.info(
            "类别 {} 多源发现完成: {} 个来源钱包, {} 个写入/更新到候选池, 当前 PENDING 约 {}",
            category, filtered.size, upsertCount, pendingCount
        )
        return upsertCount
    }

    /**
     * 旧的内存发现源，作为候选池为空时的 fallback。
     */
    private fun discoverWalletsLegacy(category: String, marketIds: Set<String>): List<String> {
        val categoryWallets = linkedSetOf<String>()
        val genericWallets = linkedSetOf<String>()

        try {
            bridgeTradeRecordRepository.findByRawPayloadIsNotNull()
                .forEach { record ->
                    extractWalletsFromPayload(record.rawPayload).forEach { genericWallets.add(it.lowercase()) }
                }
        } catch (e: Exception) {
            logger.warn("Bridge trade record fallback 失败: {}", e.message)
        }

        try {
            val allEvents = activityEventRepository.findAll()
            val filteredEvents = if (marketIds.isNotEmpty()) {
                allEvents.filter { it.marketId in marketIds }
            } else {
                emptyList()
            }
            filteredEvents.mapNotNull { it.normalizedWallet }
                .forEach { categoryWallets.add(it.lowercase()) }
        } catch (e: Exception) {
            logger.warn("Activity event fallback 失败: {}", e.message)
        }

        try {
            leaderRepository.findByCategory(category)
                .map { it.leaderAddress.lowercase() }
                .forEach { categoryWallets.add(it) }
            leaderRepository.findAll()
                .map { it.leaderAddress.lowercase() }
                .forEach { genericWallets.add(it) }
        } catch (e: Exception) {
            logger.warn("Leader fallback 失败: {}", e.message)
        }

        try {
            candidateRepository.findAll()
                .mapNotNull { it.normalizedWallet?.lowercase() }
                .forEach { genericWallets.add(it) }
        } catch (e: Exception) {
            logger.warn("Candidate fallback 失败: {}", e.message)
        }

        try {
            val seedConfig = systemConfigRepository.findByConfigKey("leader_scanner.seed_wallets.$category")?.configValue
            if (!seedConfig.isNullOrBlank()) {
                seedConfig.split(",", "\n", ";", " ", "\t")
                    .map { it.trim().lowercase() }
                    .filter { it.matches(Regex("^0x[a-f0-9]{40}$")) }
                    .forEach { categoryWallets.add(it) }
            }
            val generalSeed = systemConfigRepository.findByConfigKey("leader_scanner.seed_wallets")?.configValue
            if (!generalSeed.isNullOrBlank()) {
                generalSeed.split(",", "\n", ";", " ", "\t")
                    .map { it.trim().lowercase() }
                    .filter { it.matches(Regex("^0x[a-f0-9]{40}$")) }
                    .forEach { genericWallets.add(it) }
            }
        } catch (e: Exception) {
            logger.warn("Seed fallback 失败: {}", e.message)
        }

        val invalidWallets = setOf("0x2791bca1f2de4661ed88a30c99a7a9449aa84174")
        return (categoryWallets + genericWallets)
            .filterNot { it in invalidWallets }
            .distinct()
            .take(MAX_WALLETS_PER_CATEGORY)
    }

    /**
     * 从 bridge_trade_record raw_payload JSON 中提取钱包地址
     */
    private fun extractWalletsFromPayload(rawPayload: String?): List<String> {
        if (rawPayload.isNullOrBlank()) return emptyList()
        return try {
            val jsonElement = gson.fromJson(rawPayload, JsonElement::class.java)
            val wallets = mutableListOf<String>()
            extractAddressesFromJson(jsonElement, wallets)
            wallets.distinct()
        } catch (e: Exception) {
            Regex("0x[a-f0-9]{40}", RegexOption.IGNORE_CASE)
                .findAll(rawPayload)
                .map { it.value.lowercase() }
                .distinct()
                .toList()
        }
    }

    private fun extractAddressesFromJson(element: JsonElement?, wallets: MutableList<String>) {
        if (element == null || element.isJsonNull) return
        when {
            element.isJsonObject -> {
                element.asJsonObject.entrySet().forEach { (_, value) ->
                    if (value.isJsonPrimitive && value.asJsonPrimitive.isString) {
                        val str = value.asString
                        if (str.matches(Regex("^0x[a-fA-F0-9]{40}$"))) {
                            wallets.add(str.lowercase())
                        }
                    } else {
                        extractAddressesFromJson(value, wallets)
                    }
                }
            }
            element.isJsonArray -> {
                element.asJsonArray.forEach { extractAddressesFromJson(it, wallets) }
            }
            else -> { /* primitive scalar, ignore */ }
        }
    }

    /**
     * 分析单个钱包，并更新 candidate_pool 状态。
     */
    private suspend fun analyzeWalletAndUpdatePool(
        candidate: LeaderScannerCandidatePool,
        marketIds: Set<String>
    ): LeaderScanResultItem? {
        val wallet = candidate.normalizedWallet
        val category = candidate.category
        val now = System.currentTimeMillis()

        val result = analyzeWallet(wallet, category, marketIds)

        // 更新候选池状态（兼容 fallback 创建的临时对象：先查数据库再更新）
        try {
            val state = if (result != null) "ANALYZED" else "REJECTED"
            val resultJson = result?.let {
                mapOf(
                    "totalTrades" to it.totalTrades,
                    "winRate" to it.winRate,
                    "totalPnl" to it.totalPnl,
                    "totalVolume" to it.totalVolume,
                    "avgTradeSize" to it.avgTradeSize,
                    "lastTradeAt" to it.lastTradeAt,
                    "activityScore" to it.activityScore
                )
            }
            val dbCandidate = candidate.id?.let { candidatePoolRepository.findById(it).orElse(null) }
                ?: candidatePoolRepository.findByCategoryAndNormalizedWallet(category, wallet)
            val toSave = if (dbCandidate != null) {
                dbCandidate.copy(
                    analysisState = state,
                    analyzedAt = now,
                    lastAnalysisResult = resultJson?.let { gson.toJson(it) },
                    updatedAt = now
                )
            } else {
                candidate.copy(
                    analysisState = state,
                    analyzedAt = now,
                    lastAnalysisResult = resultJson?.let { gson.toJson(it) },
                    updatedAt = now
                )
            }
            candidatePoolRepository.save(toSave)
        } catch (e: Exception) {
            logger.warn("更新候选池状态失败 {}: {}", wallet, e.message)
        }

        return result
    }

    /**
     * 分析单个钱包在指定类别下的表现
     */
    private suspend fun analyzeWallet(
        wallet: String,
        category: String,
        marketIds: Set<String>
    ): LeaderScanResultItem? {
        return apiSemaphore.withPermit {
            try {
                val dataApi = retrofitFactory.createDataApi()

                val positionsResponse = dataApi.getPositions(
                    user = wallet,
                    limit = 100
                )
                val positions = if (positionsResponse.isSuccessful) positionsResponse.body().orEmpty() else emptyList()

                val analysisWindowMs = getAnalysisWindowMs()
                val startSeconds = (System.currentTimeMillis() - analysisWindowMs) / 1000
                val endSeconds = System.currentTimeMillis() / 1000
                val activityResponse = dataApi.getUserActivity(
                    user = wallet,
                    type = listOf("TRADE"),
                    start = startSeconds,
                    end = endSeconds,
                    limit = 200,
                    sortBy = "TIMESTAMP",
                    sortDirection = "DESC"
                )
                val activities = if (activityResponse.isSuccessful) activityResponse.body().orEmpty() else emptyList()

                val metrics = calculateMetrics(wallet, positions, activities, marketIds)

                if (metrics.totalTrades == 0 && metrics.totalPnl.isNullOrBlank()) {
                    null
                } else {
                    LeaderScanResultItem(
                        leaderAddress = wallet,
                        leaderName = activities.firstOrNull()?.pseudonym ?: activities.firstOrNull()?.name,
                        category = category,
                        totalTrades = metrics.totalTrades,
                        winRate = metrics.winRate,
                        totalPnl = metrics.totalPnl,
                        totalVolume = metrics.totalVolume,
                        avgTradeSize = metrics.avgTradeSize,
                        lastTradeAt = metrics.lastTradeAt,
                        activityScore = metrics.activityScore,
                        smartMoneyRank = null,
                        source = candidateSourceToDisplay(candidatePoolRepository.findByCategoryAndNormalizedWallet(category, wallet)?.source ?: "auto_scan")
                    )
                }
            } catch (e: Exception) {
                logger.warn("分析钱包 {} 失败: {}", wallet, e.message)
                null
            }
        }
    }

    private fun candidateSourceToDisplay(source: String): String {
        return when (source) {
            "SEED_WALLET" -> "seed_scan"
            "HOT_MARKET" -> "hot_market_scan"
            "BRIDGE_RECORD" -> "bridge_scan"
            "ACTIVITY_EVENT" -> "activity_scan"
            else -> "auto_scan"
        }
    }

    /**
     * 计算钱包指标
     */
    private fun calculateMetrics(
        wallet: String,
        positions: List<PositionResponse>,
        activities: List<UserActivityResponse>,
        marketIds: Set<String>
    ): WalletMetrics {
        val categoryPositions = if (marketIds.isEmpty()) positions else positions.filter { it.conditionId in marketIds }
        val categoryActivities = if (marketIds.isEmpty()) activities else activities.filter { it.conditionId in marketIds }

        val totalTrades = categoryActivities.size
        val totalVolume = categoryActivities.mapNotNull { it.usdcSize }.sum()
        val avgTradeSize = if (totalTrades > 0) totalVolume / totalTrades else 0.0

        val totalCashPnl = categoryPositions.mapNotNull { it.cashPnl }.sum()
        val totalRealizedPnl = categoryPositions.mapNotNull { it.realizedPnl }.sum()
        val totalPnl = totalCashPnl + totalRealizedPnl

        val closedPositions = categoryPositions.filter {
            (it.realizedPnl ?: 0.0) != 0.0 || (it.totalBought ?: 0.0) > 0
        }
        val winningClosed = closedPositions.count { (it.realizedPnl ?: 0.0) > 0 }

        val winRate = if (closedPositions.isNotEmpty()) {
            (winningClosed.toDouble() / closedPositions.size * 100).let {
                BigDecimal(it).setScale(2, RoundingMode.HALF_UP).toDouble()
            }
        } else {
            val activePositions = categoryPositions.filter { (it.currentValue ?: 0.0) > 0 }
            if (activePositions.isNotEmpty()) {
                val profitableActive = activePositions.count { (it.cashPnl ?: 0.0) > 0 }
                (profitableActive.toDouble() / activePositions.size * 100).let {
                    BigDecimal(it).setScale(2, RoundingMode.HALF_UP).toDouble()
                }
            } else null
        }

        val lastTradeAtSeconds = categoryActivities.maxOfOrNull { it.timestamp }
        // Polymarket API 返回的时间戳可能是秒级或毫秒级，统一归一化为毫秒
        val lastTradeAt = lastTradeAtSeconds?.let { normalizeTimestampToMillis(it) }

        val activityScore = if (totalTrades > 0) {
            val recencyScore = if (lastTradeAt != null) {
                val hoursAgo = (System.currentTimeMillis() - lastTradeAt) / (1000 * 60 * 60)
                (100 - hoursAgo).coerceIn(0, 100).toDouble()
            } else 0.0
            val freqScore = (totalTrades * 2.0).coerceAtMost(50.0)
            val positionScore = (categoryPositions.size * 5.0).coerceAtMost(30.0)
            BigDecimal(recencyScore + freqScore + positionScore).setScale(2, RoundingMode.HALF_UP).toDouble()
                .coerceAtMost(100.0)
        } else null

        return WalletMetrics(
            totalTrades = totalTrades,
            winRate = winRate,
            totalPnl = if (totalPnl != 0.0) BigDecimal(totalPnl).setScale(4, RoundingMode.HALF_UP).toPlainString() else null,
            totalVolume = if (totalVolume > 0) BigDecimal(totalVolume).setScale(4, RoundingMode.HALF_UP).toPlainString() else null,
            avgTradeSize = if (avgTradeSize > 0) BigDecimal(avgTradeSize).setScale(4, RoundingMode.HALF_UP).toPlainString() else null,
            lastTradeAt = lastTradeAt,
            activityScore = activityScore
        )
    }

    /**
     * 将秒级或毫秒级时间戳统一归一化为毫秒。
     * 阈值 1e12 毫秒约等于 2001-09-09，早于该时间则视为秒级。
     */
    private fun normalizeTimestampToMillis(ts: Long): Long {
        return if (ts < 1_000_000_000_000L) ts * 1000L else ts
    }

    /**
     * 评分并排序
     */
    private fun scoreAndRank(items: List<LeaderScanResultItem>, category: String): List<LeaderScanResultItem> {
        if (items.isEmpty()) return emptyList()

        val pnlValues = items.mapNotNull { it.totalPnl?.toDoubleOrNull() }
        val maxPnl = pnlValues.maxOrNull() ?: 1.0
        val minPnl = pnlValues.minOrNull() ?: 0.0
        val pnlRange = (maxPnl - minPnl).coerceAtLeast(1.0)

        val scored = items.map { item ->
            val pnlScore = item.totalPnl?.toDoubleOrNull()?.let {
                ((it - minPnl) / pnlRange * 100).coerceIn(0.0, 100.0)
            } ?: 0.0
            val winRateScore = item.winRate ?: 0.0
            val activityScore = item.activityScore ?: 0.0

            val sampleScore = if ((item.totalTrades ?: 0) >= MIN_TRADES_FOR_RANK) 100.0 else 0.0
            val totalScore = winRateScore * 1000 + sampleScore * 10 + pnlScore + activityScore * 0.1

            item to totalScore
        }

        return scored.sortedByDescending { it.second }
            .mapIndexed { index, (item, _) ->
                item.copy(smartMoneyRank = index + 1)
            }
    }

    /**
     * 将 Top 结果持久化到 Leader 表
     */
    private fun persistTopLeaders(category: String, topCandidates: List<LeaderScanResultItem>): Pair<Int, Int> {
        var created = 0
        var updated = 0
        val now = System.currentTimeMillis()

        for (candidate in topCandidates) {
            val existing = leaderRepository.findByLeaderAddressAndCategory(candidate.leaderAddress, category)
            if (existing == null) {
                val newLeader = Leader(
                    leaderAddress = candidate.leaderAddress,
                    leaderName = candidate.leaderName,
                    category = category,
                    website = "https://polymarket.com/profile/${candidate.leaderAddress}",
                    totalTrades = candidate.totalTrades,
                    winRate = candidate.winRate?.let { BigDecimal.valueOf(it) },
                    totalPnl = candidate.totalPnl,
                    totalVolume = candidate.totalVolume,
                    avgTradeSize = candidate.avgTradeSize,
                    lastTradeAt = candidate.lastTradeAt,
                    activityScore = candidate.activityScore?.let { BigDecimal.valueOf(it) },
                    smartMoneyRank = candidate.smartMoneyRank,
                    scanSource = candidate.source,
                    scannedAt = now
                )
                leaderRepository.save(newLeader)
                created++
            } else {
                val updatedLeader = existing.copy(
                    leaderName = existing.leaderName ?: candidate.leaderName,
                    category = category,
                    totalTrades = candidate.totalTrades,
                    winRate = candidate.winRate?.let { BigDecimal.valueOf(it) },
                    totalPnl = candidate.totalPnl,
                    totalVolume = candidate.totalVolume,
                    avgTradeSize = candidate.avgTradeSize,
                    lastTradeAt = candidate.lastTradeAt,
                    activityScore = candidate.activityScore?.let { BigDecimal.valueOf(it) },
                    smartMoneyRank = candidate.smartMoneyRank,
                    scanSource = if (existing.scanSource == null) candidate.source else existing.scanSource,
                    scannedAt = now,
                    updatedAt = now
                )
                leaderRepository.save(updatedLeader)
                updated++
            }

            // 标记候选池中的对应行 PROMOTED
            try {
                candidatePoolRepository.findByCategoryAndNormalizedWallet(category, candidate.leaderAddress.lowercase())
                    ?.let { poolItem ->
                        candidatePoolRepository.save(
                            poolItem.copy(
                                analysisState = "PROMOTED",
                                promotedAt = now,
                                updatedAt = now
                            )
                        )
                    }
            } catch (e: Exception) {
                logger.warn("标记候选为 PROMOTED 失败: {}", e.message)
            }
        }

        return created to updated
    }

    /**
     * 获取预览结果（不写入数据库）
     */
    fun preview(category: String? = null): List<LeaderScanPreviewResponse> {
        val categories = normalizeCategories(category)
        return categories.map { cat ->
            analyzeOnly(cat, dryRun = true)
        }
    }

    // ========== 内部数据类 ==========

    private data class WalletMetrics(
        val totalTrades: Int,
        val winRate: Double?,
        val totalPnl: String?,
        val totalVolume: String?,
        val avgTradeSize: String?,
        val lastTradeAt: Long?,
        val activityScore: Double?
    )
}
