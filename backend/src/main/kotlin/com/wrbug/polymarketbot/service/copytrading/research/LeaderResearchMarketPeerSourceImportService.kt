package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchMarketPeerSourceCategoryDto
import com.wrbug.polymarketbot.dto.LeaderResearchMarketPeerSourceImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchMarketPeerSourceImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchMarketPeerSourcePreviewItemDto
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderCandidateProvenance
import com.wrbug.polymarketbot.enums.LeaderResearchEventType
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderActivityEventRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.repository.LeaderResearchMarketPeerSourceProjection
import com.wrbug.polymarketbot.util.CategoryValidator
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal
import java.math.RoundingMode

@Service
class LeaderResearchMarketPeerSourceImportService(
    private val activityEventRepository: LeaderActivityEventRepository,
    private val candidateRepository: LeaderResearchCandidateRepository,
    private val leaderRepository: LeaderRepository,
    private val eventService: LeaderResearchEventService
) {
    @Transactional
    fun importFromMarketPeerSource(request: LeaderResearchMarketPeerSourceImportRequest): LeaderResearchMarketPeerSourceImportResponse {
        val categories = request.categories
            .mapNotNull { CategoryValidator.normalizeCategory(it) }
            .filter { LeaderResearchMarketCategoryPatterns.contains(it) }
            .distinct()
            .ifEmpty { listOf("politics", "finance") }
        val limit = request.limitPerCategory.coerceIn(1, MAX_IMPORT_PER_CATEGORY)
        val since = System.currentTimeMillis() - request.lookbackDays.coerceIn(1, 365).toLong() * DAY_MS
        val minSafePriceRatio = request.minSafePriceRatio.toBigDecimalOrDefault(BigDecimal("0.20"))
        val maxTailPriceRatio = request.maxTailPriceRatio.toBigDecimalOrDefault(BigDecimal("0.50"))
        val selectedWallets = mutableSetOf<String>()
        val categoryResults = mutableListOf<LeaderResearchMarketPeerSourceCategoryDto>()
        val previewItems = mutableListOf<LeaderResearchMarketPeerSourcePreviewItemDto>()
        var selectedTotal = 0
        var createdTotal = 0
        var updatedTotal = 0
        var skippedExistingTotal = 0
        var skippedLockedTotal = 0

        categories.forEach { category ->
            val selected = activityEventRepository.discoverWalletsFromMarketPeerSource(
                since = since,
                marketPattern = LeaderResearchMarketCategoryPatterns.patternFor(category),
                hotMarketLimit = request.hotMarketLimit.coerceIn(1, MAX_HOT_MARKET_LIMIT),
                minMarketEvents = request.minMarketEvents.coerceIn(1, 5000),
                minMarketWallets = request.minMarketWallets.coerceIn(1, 5000),
                minEvents = request.minEvents.coerceIn(1, 1000),
                minDistinctMarkets = request.minDistinctMarkets.coerceIn(1, 1000),
                minBuyEvents = request.minBuyEvents.coerceIn(0, 1000),
                minSellEvents = request.minSellEvents.coerceIn(0, 1000),
                minSafePriceRatio = minSafePriceRatio,
                maxTailPriceRatio = maxTailPriceRatio,
                limit = (limit * OVERSAMPLE_FACTOR).coerceAtMost(MAX_SOURCE_SCAN_PER_CATEGORY)
            )
                .asSequence()
                .filter { selectedWallets.add(it.getNormalizedWallet().lowercase()) }
                .map { source ->
                    val normalizedWallet = source.getNormalizedWallet().lowercase()
                    val sourceEvidence = sourceEvidence(category, source)
                    val existing = candidateRepository.findByNormalizedWallet(normalizedWallet)
                    MarketPeerSourceSelection(
                        source = source,
                        normalizedWallet = normalizedWallet,
                        sourceEvidence = sourceEvidence,
                        priority = selectionPriority(existing, sourceEvidence)
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
                val normalizedWallet = selection.normalizedWallet
                val sourceEvidence = selection.sourceEvidence
                val existing = candidateRepository.findByNormalizedWallet(normalizedWallet)
                val leader = leaderRepository.findByLeaderAddress(normalizedWallet)
                val action = when {
                    existing?.locked == true || existing?.provenance == LeaderCandidateProvenance.MANUAL_LOCKED -> {
                        skippedLocked += 1
                        "SKIP_LOCKED"
                    }
                    existing == null -> {
                        created += 1
                        "CREATE"
                    }
                    hasExactEvidence(existing.sourceEvidence, sourceEvidence) -> {
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
                    val saved = if (existing == null) {
                        candidateRepository.save(
                            LeaderResearchCandidate(
                                normalizedWallet = normalizedWallet,
                                leaderId = leader?.id,
                                researchState = LeaderResearchState.DISCOVERED,
                                source = SOURCE_MARKET_PEER_SOURCE,
                                sourceRank = index + 1,
                                agentOwned = true,
                                provenance = if (leader == null) {
                                    LeaderCandidateProvenance.AGENT_CREATED
                                } else {
                                    LeaderCandidateProvenance.USER_LEADER
                                },
                                sourceEvidence = sourceEvidence,
                                firstSeenAt = now,
                                lastSourceSeenAt = now,
                                lastTransitionAt = now,
                                createdAt = now,
                                updatedAt = now
                            )
                        )
                    } else {
                        candidateRepository.save(
                            existing.copy(
                                leaderId = existing.leaderId ?: leader?.id,
                                source = mergeSource(existing.source, SOURCE_MARKET_PEER_SOURCE),
                                sourceRank = existing.sourceRank ?: index + 1,
                                provenance = if (existing.provenance == LeaderCandidateProvenance.AGENT_CREATED && leader != null) {
                                    LeaderCandidateProvenance.USER_LEADER
                                } else {
                                    existing.provenance
                                },
                                sourceEvidence = appendEvidence(existing.sourceEvidence, sourceEvidence),
                                lastSourceSeenAt = now,
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
                        reason = "Candidate imported from market peer source",
                        payloadSummary = sourceEvidence,
                        dedupeKey = "market-peer-source-import:$category:$normalizedWallet"
                    )
                }

                if (previewItems.size < PREVIEW_LIMIT) {
                    previewItems += previewItem(category, normalizedWallet, action, selection.source, sourceEvidence)
                }
            }

            createdTotal += created
            updatedTotal += updated
            skippedExistingTotal += skippedExisting
            skippedLockedTotal += skippedLocked
            categoryResults += LeaderResearchMarketPeerSourceCategoryDto(
                category = category,
                selectedCount = selected.size,
                createdCount = created,
                updatedCount = updated,
                skippedExistingCount = skippedExisting,
                skippedLockedCount = skippedLocked
            )
        }

        return LeaderResearchMarketPeerSourceImportResponse(
            dryRun = request.dryRun,
            requestedCategories = categories,
            selectedTotal = selectedTotal,
            createdTotal = createdTotal,
            updatedTotal = updatedTotal,
            skippedExistingTotal = skippedExistingTotal,
            skippedLockedTotal = skippedLockedTotal,
            categories = categoryResults,
            previewItems = previewItems
        )
    }

    private fun previewItem(
        category: String,
        wallet: String,
        action: String,
        source: LeaderResearchMarketPeerSourceProjection,
        sourceEvidence: String
    ): LeaderResearchMarketPeerSourcePreviewItemDto {
        return LeaderResearchMarketPeerSourcePreviewItemDto(
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
            topMarkets = topMarkets(source),
            sourceEvidence = sourceEvidence
        )
    }

    private fun sourceEvidence(category: String, source: LeaderResearchMarketPeerSourceProjection): String {
        val totalEvents = source.getTotalEvents().coerceAtLeast(1)
        val safeRatio = BigDecimal(source.getSafePriceEvents()).divide(BigDecimal(totalEvents), 4, RoundingMode.HALF_UP)
        val tailRatio = BigDecimal(source.getTailPriceEvents()).divide(BigDecimal(totalEvents), 4, RoundingMode.HALF_UP)
        return listOf(
            "market_peer_source:$category",
            "category:$category",
            "events:${source.getTotalEvents()}",
            "markets:${source.getDistinctMarkets()}",
            "buy_events:${source.getBuyEvents()}",
            "sell_events:${source.getSellEvents()}",
            "safe_price_ratio:$safeRatio",
            "tail_price_ratio:$tailRatio",
            "avg_amount:${source.getAvgAmount().format4()}",
            "total_amount:${source.getTotalAmount().format4()}",
            "top_markets:${topMarkets(source).joinToString(",")}",
            "last_event_time:${source.getLastEventTime() ?: 0}"
        ).joinToString(" | ")
    }

    private fun topMarkets(source: LeaderResearchMarketPeerSourceProjection): List<String> {
        return source.getTopMarkets()
            ?.split(",")
            ?.map { it.trim() }
            ?.filter { it.isNotBlank() }
            ?.distinct()
            ?.take(5)
            .orEmpty()
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

    private fun String.toBigDecimalOrDefault(default: BigDecimal): BigDecimal {
        return runCatching { BigDecimal(this) }.getOrDefault(default)
    }

    private fun BigDecimal?.format4(): String {
        return (this ?: BigDecimal.ZERO).setScale(4, RoundingMode.HALF_UP).toPlainString()
    }

    companion object {
        const val SOURCE_MARKET_PEER_SOURCE = "MARKET_PEER_SOURCE"
        private const val MAX_IMPORT_PER_CATEGORY = 500
        private const val MAX_HOT_MARKET_LIMIT = 200
        private const val PREVIEW_LIMIT = 100
        private const val OVERSAMPLE_FACTOR = 20
        private const val MAX_SOURCE_SCAN_PER_CATEGORY = 1000
        private const val DAY_MS = 24L * 60 * 60 * 1000
    }

    private data class MarketPeerSourceSelection(
        val source: LeaderResearchMarketPeerSourceProjection,
        val normalizedWallet: String,
        val sourceEvidence: String,
        val priority: Int
    )
}
