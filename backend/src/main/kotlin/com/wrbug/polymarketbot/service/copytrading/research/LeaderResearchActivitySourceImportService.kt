package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceCategoryDto
import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceMetricRefreshCategoryDto
import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceMetricRefreshRequest
import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceMetricRefreshResponse
import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourcePreviewItemDto
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderCandidateProvenance
import com.wrbug.polymarketbot.enums.LeaderResearchEventType
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderActivityEventRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.repository.LeaderResearchActivitySourceProjection
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.util.CategoryValidator
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.scheduling.annotation.Scheduled
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal
import java.math.RoundingMode
import java.util.concurrent.atomic.AtomicBoolean

@Service
class LeaderResearchActivitySourceImportService(
    private val activityEventRepository: LeaderActivityEventRepository,
    private val candidateRepository: LeaderResearchCandidateRepository,
    private val leaderRepository: LeaderRepository,
    private val eventService: LeaderResearchEventService,
    @Value("\${leader.research.activity-source.metrics-refresh.enabled:false}") private val metricsRefreshScheduledEnabled: Boolean = false,
    @Value("\${leader.research.activity-source.metrics-refresh.categories:politics,finance}") private val metricsRefreshCategories: String = "politics,finance",
    @Value("\${leader.research.activity-source.metrics-refresh.lookback-days:14}") private val metricsRefreshLookbackDays: Int = 14
) {
    private val logger = LoggerFactory.getLogger(LeaderResearchActivitySourceImportService::class.java)
    private val metricsRefreshRunning = AtomicBoolean(false)

    @Scheduled(fixedDelayString = "\${leader.research.activity-source.metrics-refresh.fixed-delay-ms:3600000}")
    fun scheduledMetricsRefresh() {
        if (!metricsRefreshScheduledEnabled) {
            return
        }
        if (!metricsRefreshRunning.compareAndSet(false, true)) {
            logger.info("Leader activity-source metrics refresh skipped because previous refresh is still running")
            return
        }
        try {
            val request = LeaderResearchActivitySourceMetricRefreshRequest(
                categories = metricsRefreshCategories
                    .split(",")
                    .map { it.trim() }
                    .filter { it.isNotBlank() },
                lookbackDays = metricsRefreshLookbackDays
            )
            val result = refreshMetrics(request)
            logger.info(
                "Leader activity-source metrics refresh completed: categories={}, lookbackDays={}, refreshedTotal={}, details={}",
                result.requestedCategories.joinToString(","),
                result.lookbackDays,
                result.refreshedTotal,
                result.categories.joinToString(";") { "${it.category}:${it.refreshedCount}/${it.durationMs}ms" }
            )
        } catch (e: Exception) {
            logger.warn("Leader activity-source metrics refresh failed: {}", e.message, e)
        } finally {
            metricsRefreshRunning.set(false)
        }
    }

    @Transactional
    fun importFromActivitySource(request: LeaderResearchActivitySourceImportRequest): LeaderResearchActivitySourceImportResponse {
        val categories = request.categories
            .mapNotNull { CategoryValidator.normalizeCategory(it) }
            .filter { LeaderResearchMarketCategoryPatterns.contains(it) }
            .distinct()
            .ifEmpty { listOf("politics", "finance") }
        val limit = request.limitPerCategory.coerceIn(1, MAX_IMPORT_PER_CATEGORY)
        val since = System.currentTimeMillis() - request.lookbackDays.coerceIn(1, 365).toLong() * DAY_MS
        val minSafePriceRatio = request.minSafePriceRatio.toBigDecimalOrDefault(BigDecimal("0.25"))
        val maxTailPriceRatio = request.maxTailPriceRatio.toBigDecimalOrDefault(BigDecimal("0.45"))
        val targetWallets = request.wallets
            .map { it.trim().lowercase() }
            .filter { WALLET_REGEX.matches(it) }
            .distinct()
        val previewItems = mutableListOf<LeaderResearchActivitySourcePreviewItemDto>()
        val selectedWallets = mutableSetOf<String>()
        val metricsBackedCategories = mutableListOf<String>()
        val categoryResults = mutableListOf<LeaderResearchActivitySourceCategoryDto>()
        var selectedTotal = 0
        var createdTotal = 0
        var updatedTotal = 0
        var skippedExistingTotal = 0
        var skippedLockedTotal = 0

        categories.forEach { category ->
            val marketPattern = LeaderResearchMarketCategoryPatterns.patternFor(category)
            val minEvents = request.minEvents.coerceIn(1, 1000)
            val minDistinctMarkets = request.minDistinctMarkets.coerceIn(1, 1000)
            val minBuyEvents = request.minBuyEvents.coerceIn(1, 1000)
            val minSellEvents = request.minSellEvents.coerceIn(1, 1000)
            val discovered = if (targetWallets.isEmpty()) {
                val metricsCount = activityEventRepository.countActivityWalletMetrics(category, request.lookbackDays.coerceIn(1, 365))
                if (metricsCount > 0) {
                    metricsBackedCategories += category
                    activityEventRepository.discoverWalletsFromActivitySourceMetrics(
                        category = category,
                        lookbackDays = request.lookbackDays.coerceIn(1, 365),
                        minEvents = minEvents,
                        minDistinctMarkets = minDistinctMarkets,
                        minBuyEvents = minBuyEvents,
                        minSellEvents = minSellEvents,
                        minSafePriceRatio = minSafePriceRatio,
                        maxTailPriceRatio = maxTailPriceRatio,
                        limit = (limit * OVERSAMPLE_FACTOR).coerceAtMost(MAX_SOURCE_SCAN_PER_CATEGORY)
                    )
                } else {
                    activityEventRepository.discoverWalletsFromActivitySource(
                        since = since,
                        marketPattern = marketPattern,
                        minEvents = minEvents,
                        minDistinctMarkets = minDistinctMarkets,
                        minBuyEvents = minBuyEvents,
                        minSellEvents = minSellEvents,
                        minSafePriceRatio = minSafePriceRatio,
                        maxTailPriceRatio = maxTailPriceRatio,
                        limit = (limit * OVERSAMPLE_FACTOR).coerceAtMost(MAX_SOURCE_SCAN_PER_CATEGORY)
                    )
                }
            } else {
                activityEventRepository.discoverWalletsFromActivitySourceForWallets(
                    wallets = targetWallets,
                    since = since,
                    marketPattern = marketPattern,
                    minEvents = minEvents,
                    minDistinctMarkets = minDistinctMarkets,
                    minBuyEvents = minBuyEvents,
                    minSellEvents = minSellEvents,
                    minSafePriceRatio = minSafePriceRatio,
                    maxTailPriceRatio = maxTailPriceRatio
                )
            }
            val discoveredList = discovered.toList()
            val discoveredWallets = discoveredList
                .map { it.getNormalizedWallet().lowercase() }
                .distinct()
            val existingByWallet = findExistingCandidates(discoveredWallets)
            val leadersByWallet = findLeaders(discoveredWallets)
            val selected = discovered
                .asSequence()
                .filter { selectedWallets.add(it.getNormalizedWallet().lowercase()) }
                .map { source ->
                    val normalizedWallet = source.getNormalizedWallet().lowercase()
                    val sourceEvidence = sourceEvidence(category, source, request.lookbackDays)
                    ActivitySourceSelection(
                        source = source,
                        normalizedWallet = normalizedWallet,
                        sourceEvidence = sourceEvidence,
                        existing = existingByWallet[normalizedWallet],
                        leader = leadersByWallet[normalizedWallet],
                        priority = selectionPriority(existingByWallet[normalizedWallet], sourceEvidence)
                    )
                }
                .sortedBy { it.priority }
                .take(limit)
                .toList()

            var created = 0
            var updated = 0
            var skippedExisting = 0
            var skippedLocked = 0
            selectedTotal += selected.size

            selected.forEachIndexed { index, selection ->
                val source = selection.source
                val normalizedWallet = selection.normalizedWallet
                val sourceEvidence = selection.sourceEvidence
                val existing = selection.existing
                val leader = selection.leader
                val action = when {
                    existing?.locked == true || existing?.provenance == LeaderCandidateProvenance.MANUAL_LOCKED -> {
                        skippedLocked += 1
                        "SKIP_LOCKED"
                    }
                    existing == null -> {
                        created += 1
                        "CREATE"
                    }
                    hasExactEvidence(existing.sourceEvidence, sourceEvidence) &&
                        hasCurrentFreshness(existing, source.getLastEventTime()) -> {
                        skippedExisting += 1
                        "SKIP_EXISTING"
                    }
                    else -> {
                        updated += 1
                        "UPDATE"
                    }
                }

                if (!request.dryRun && action != "SKIP_LOCKED" && action != "SKIP_EXISTING") {
                    val now = System.currentTimeMillis()
                    val sourceSeenAt = source.getLastEventTime() ?: now
                    val saved = if (existing == null) {
                        candidateRepository.save(
                            LeaderResearchCandidate(
                                normalizedWallet = normalizedWallet,
                                leaderId = leader?.id,
                                researchState = LeaderResearchState.DISCOVERED,
                                source = SOURCE_ACTIVITY_SOURCE,
                                sourceRank = index + 1,
                                agentOwned = true,
                                provenance = if (leader == null) {
                                    LeaderCandidateProvenance.AGENT_CREATED
                                } else {
                                    LeaderCandidateProvenance.USER_LEADER
                                },
                                sourceEvidence = sourceEvidence,
                                firstSeenAt = now,
                                lastSourceSeenAt = sourceSeenAt,
                                lastTransitionAt = now,
                                createdAt = now,
                                updatedAt = now
                            )
                        )
                    } else {
                        candidateRepository.save(
                            existing.copy(
                                leaderId = existing.leaderId ?: leader?.id,
                                source = mergeSource(existing.source, SOURCE_ACTIVITY_SOURCE),
                                sourceRank = existing.sourceRank ?: index + 1,
                                provenance = if (existing.provenance == LeaderCandidateProvenance.AGENT_CREATED && leader != null) {
                                    LeaderCandidateProvenance.USER_LEADER
                                } else {
                                    existing.provenance
                                },
                                sourceEvidence = appendEvidence(existing.sourceEvidence, sourceEvidence),
                                lastSourceSeenAt = latestSourceSeenAt(existing.lastSourceSeenAt, sourceSeenAt),
                                updatedAt = now
                            )
                        )
                    }
                    eventService.record(
                        type = if (existing == null) {
                            LeaderResearchEventType.CANDIDATE_DISCOVERED
                        } else {
                            LeaderResearchEventType.CANDIDATE_UPDATED
                        },
                        candidateId = saved.id,
                        reason = "Candidate imported from activity source",
                        payloadSummary = sourceEvidence,
                        dedupeKey = "activity-source-import:$category:$normalizedWallet"
                    )
                }

                if (previewItems.size < PREVIEW_LIMIT) {
                    previewItems += previewItem(category, normalizedWallet, action, source, sourceEvidence)
                }
            }

            createdTotal += created
            updatedTotal += updated
            skippedExistingTotal += skippedExisting
            skippedLockedTotal += skippedLocked
            categoryResults += LeaderResearchActivitySourceCategoryDto(
                category = category,
                selectedCount = selected.size,
                createdCount = created,
                updatedCount = updated,
                skippedExistingCount = skippedExisting,
                skippedLockedCount = skippedLocked
            )
        }

        return LeaderResearchActivitySourceImportResponse(
            dryRun = request.dryRun,
            requestedCategories = categories,
            metricsBackedCategories = metricsBackedCategories.distinct(),
            selectedTotal = selectedTotal,
            createdTotal = createdTotal,
            updatedTotal = updatedTotal,
            skippedExistingTotal = skippedExistingTotal,
            skippedLockedTotal = skippedLockedTotal,
            categories = categoryResults,
            previewItems = previewItems
        )
    }

    private fun findExistingCandidates(wallets: List<String>): Map<String, LeaderResearchCandidate> {
        if (wallets.isEmpty()) {
            return emptyMap()
        }
        val bulk = candidateRepository.findByNormalizedWalletIn(wallets)
        if (bulk.isNotEmpty() || wallets.size > SMALL_LOOKUP_FALLBACK_LIMIT) {
            return bulk.associateBy { it.normalizedWallet.lowercase() }
        }
        return wallets.mapNotNull { wallet ->
            candidateRepository.findByNormalizedWallet(wallet)?.let { wallet to it }
        }.toMap()
    }

    private fun findLeaders(wallets: List<String>): Map<String, com.wrbug.polymarketbot.entity.Leader> {
        if (wallets.isEmpty()) {
            return emptyMap()
        }
        val bulk = leaderRepository.findLatestByLeaderAddressIn(wallets)
        if (bulk.isNotEmpty() || wallets.size > SMALL_LOOKUP_FALLBACK_LIMIT) {
            return bulk.associateBy { it.leaderAddress.lowercase() }
        }
        return wallets.mapNotNull { wallet ->
            leaderRepository.findByLeaderAddress(wallet)?.let { wallet to it }
        }.toMap()
    }

    @Transactional
    fun refreshMetrics(request: LeaderResearchActivitySourceMetricRefreshRequest): LeaderResearchActivitySourceMetricRefreshResponse {
        val categories = request.categories
            .mapNotNull { CategoryValidator.normalizeCategory(it) }
            .filter { LeaderResearchMarketCategoryPatterns.contains(it) }
            .distinct()
            .ifEmpty { listOf("politics", "finance") }
        val lookbackDays = request.lookbackDays.coerceIn(1, 365)
        val since = System.currentTimeMillis() - lookbackDays.toLong() * DAY_MS
        val generatedAt = System.currentTimeMillis()
        val results = categories.map { category ->
            val startedAt = System.currentTimeMillis()
            val marketPattern = LeaderResearchMarketCategoryPatterns.patternFor(category)
            activityEventRepository.deleteActivityWalletMetrics(category, lookbackDays)
            val refreshed = activityEventRepository.insertActivityWalletMetrics(
                category = category,
                lookbackDays = lookbackDays,
                since = since,
                marketPattern = marketPattern,
                generatedAt = generatedAt
            )
            LeaderResearchActivitySourceMetricRefreshCategoryDto(
                category = category,
                lookbackDays = lookbackDays,
                refreshedCount = refreshed,
                generatedAt = generatedAt,
                durationMs = System.currentTimeMillis() - startedAt
            )
        }
        return LeaderResearchActivitySourceMetricRefreshResponse(
            requestedCategories = categories,
            lookbackDays = lookbackDays,
            categories = results,
            refreshedTotal = results.sumOf { it.refreshedCount },
            generatedAt = generatedAt
        )
    }

    private fun previewItem(
        category: String,
        wallet: String,
        action: String,
        source: LeaderResearchActivitySourceProjection,
        sourceEvidence: String
    ): LeaderResearchActivitySourcePreviewItemDto {
        return LeaderResearchActivitySourcePreviewItemDto(
            category = category,
            wallet = wallet,
            action = action,
            totalEvents = source.getTotalEvents(),
            distinctMarkets = source.getDistinctMarkets(),
            buyEvents = source.getBuyEvents(),
            sellEvents = source.getSellEvents(),
            safePriceEvents = source.getSafePriceEvents(),
            tailPriceEvents = source.getTailPriceEvents(),
            avgAmount = source.getAvgAmount().format4(),
            totalAmount = source.getTotalAmount().format4(),
            lastEventTime = source.getLastEventTime(),
            sourceEvidence = sourceEvidence
        )
    }

    private fun sourceEvidence(category: String, source: LeaderResearchActivitySourceProjection, lookbackDays: Int): String {
        val totalEvents = source.getTotalEvents().coerceAtLeast(1)
        val safeRatio = BigDecimal(source.getSafePriceEvents()).divide(BigDecimal(totalEvents), 4, RoundingMode.HALF_UP)
        val tailRatio = BigDecimal(source.getTailPriceEvents()).divide(BigDecimal(totalEvents), 4, RoundingMode.HALF_UP)
        return listOf(
            "activity_source:$category",
            "category:$category",
            "events:${source.getTotalEvents()}",
            "markets:${source.getDistinctMarkets()}",
            "buy_events:${source.getBuyEvents()}",
            "sell_events:${source.getSellEvents()}",
            "safe_price_ratio:$safeRatio",
            "tail_price_ratio:$tailRatio",
            "avg_amount:${source.getAvgAmount().format4()}",
            "total_amount:${source.getTotalAmount().format4()}",
            "activity_window:${lookbackDays.coerceIn(1, 365)}d_trades:${source.getTotalEvents()}",
            "last_event_time:${source.getLastEventTime() ?: 0}"
        ).joinToString(" | ")
    }

    private fun mergeSource(existing: String, incoming: String): String {
        return (existing.split(",") + incoming)
            .map { it.trim() }
            .filter { it.isNotBlank() }
            .distinct()
            .joinToString(",")
    }

    private fun appendEvidence(existing: String?, incoming: String): String {
        val lines = (existing?.lines().orEmpty() + incoming)
            .map { it.trim() }
            .filter { it.isNotBlank() }
            .distinct()
        return lines.takeLast(20).joinToString("\n")
    }

    private fun hasExactEvidence(existing: String?, incoming: String): Boolean {
        return existing.orEmpty()
            .lines()
            .map { it.trim() }
            .any { it == incoming.trim() }
    }

    private fun selectionPriority(existing: LeaderResearchCandidate?, sourceEvidence: String): Int {
        return when {
            existing == null -> 0
            existing.locked || existing.provenance == LeaderCandidateProvenance.MANUAL_LOCKED -> 3
            hasExactEvidence(existing.sourceEvidence, sourceEvidence) -> 2
            else -> 1
        }
    }

    private fun hasCurrentFreshness(existing: LeaderResearchCandidate, lastEventTime: Long?): Boolean {
        return lastEventTime == null || existing.lastSourceSeenAt?.let { it >= lastEventTime } == true
    }

    private fun latestSourceSeenAt(existing: Long?, incoming: Long): Long {
        return maxOf(existing ?: incoming, incoming)
    }

    private fun String.toBigDecimalOrDefault(default: BigDecimal): BigDecimal {
        return runCatching { BigDecimal(this) }.getOrDefault(default)
    }

    private fun BigDecimal?.format4(): String {
        return (this ?: BigDecimal.ZERO).setScale(4, RoundingMode.HALF_UP).toPlainString()
    }

    companion object {
        const val SOURCE_ACTIVITY_SOURCE = "ACTIVITY_SOURCE"
        private const val MAX_IMPORT_PER_CATEGORY = 500
        private const val PREVIEW_LIMIT = 100
        private const val OVERSAMPLE_FACTOR = 20
        private const val MAX_SOURCE_SCAN_PER_CATEGORY = 1000
        private const val SMALL_LOOKUP_FALLBACK_LIMIT = 20
        private const val DAY_MS = 24L * 60 * 60 * 1000
        private val WALLET_REGEX = Regex("^0x[a-f0-9]{40}$")
    }

    private data class ActivitySourceSelection(
        val source: LeaderResearchActivitySourceProjection,
        val normalizedWallet: String,
        val sourceEvidence: String,
        val existing: LeaderResearchCandidate?,
        val leader: com.wrbug.polymarketbot.entity.Leader?,
        val priority: Int
    )
}
