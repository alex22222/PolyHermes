package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchScannerPoolImportCategoryDto
import com.wrbug.polymarketbot.dto.LeaderResearchScannerPoolImportPreviewItemDto
import com.wrbug.polymarketbot.dto.LeaderResearchScannerPoolImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchScannerPoolImportResponse
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.entity.LeaderScannerCandidatePool
import com.wrbug.polymarketbot.enums.LeaderCandidateProvenance
import com.wrbug.polymarketbot.enums.LeaderResearchEventType
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.repository.LeaderActivityEventRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.repository.LeaderScannerCandidatePoolRepository
import com.wrbug.polymarketbot.util.CategoryValidator
import org.springframework.data.domain.PageRequest
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal
import java.math.RoundingMode

@Service
class LeaderResearchScannerPoolImportService(
    private val scannerPoolRepository: LeaderScannerCandidatePoolRepository,
    private val candidateRepository: LeaderResearchCandidateRepository,
    private val leaderRepository: LeaderRepository,
    private val activityEventRepository: LeaderActivityEventRepository,
    private val eventService: LeaderResearchEventService
) {
    @Transactional
    fun importFromScannerPool(request: LeaderResearchScannerPoolImportRequest): LeaderResearchScannerPoolImportResponse {
        val plans = listOf(
            "politics" to request.politicsLimit,
            "finance" to request.financeLimit,
            "sports" to request.sportsLimit,
            "crypto" to request.cryptoLimit
        ).map { (category, limit) -> category to limit.coerceIn(0, MAX_IMPORT_PER_CATEGORY) }

        val categoryResults = mutableListOf<LeaderResearchScannerPoolImportCategoryDto>()
        val previews = mutableListOf<LeaderResearchScannerPoolImportPreviewItemDto>()
        var createdTotal = 0
        var updatedTotal = 0
        var skippedLockedTotal = 0
        var skippedExistingTotal = 0
        var selectedTotal = 0
        val selectedWallets = mutableSetOf<String>()

        for ((category, limit) in plans) {
            if (limit <= 0) {
                categoryResults += LeaderResearchScannerPoolImportCategoryDto(category, limit, 0, 0, 0, 0, 0)
                continue
            }

            val selected = selectCandidates(category, limit, request)
                .filter { selectedWallets.add(it.normalizedWallet.lowercase()) }
            selectedTotal += selected.size
            var created = 0
            var updated = 0
            var skippedLocked = 0
            var skippedExisting = 0

            selected.forEachIndexed { index, poolCandidate ->
                val normalizedWallet = poolCandidate.normalizedWallet.lowercase()
                val sourceEvidence = sourceEvidence(poolCandidate)
                val existing = candidateRepository.findByNormalizedWallet(normalizedWallet)
                val leader = leaderRepository.findByLeaderAddress(normalizedWallet)
                val action = when {
                    existing?.locked == true || existing?.provenance == LeaderCandidateProvenance.MANUAL_LOCKED -> {
                        skippedLocked++
                        "SKIP_LOCKED"
                    }
                    existing == null -> {
                        created++
                        "CREATE"
                    }
                    existing.sourceEvidence?.contains("scanner_pool:${poolCandidate.id}") == true -> {
                        skippedExisting++
                        "SKIP_EXISTING"
                    }
                    else -> {
                        updated++
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
                                source = SOURCE_SCANNER_POOL,
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
                                source = mergeSource(existing.source, SOURCE_SCANNER_POOL),
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
                    poolCandidate.id?.let {
                        scannerPoolRepository.markPromoted(it, now, now)
                    }
                    eventService.record(
                        type = if (existing == null) {
                            LeaderResearchEventType.CANDIDATE_DISCOVERED
                        } else {
                            LeaderResearchEventType.CANDIDATE_UPDATED
                        },
                        candidateId = saved.id,
                        reason = "Candidate imported from scanner pool",
                        payloadSummary = sourceEvidence,
                        dedupeKey = "scanner-pool-import:${poolCandidate.id}:${saved.id}"
                    )
                }

                if (previews.size < PREVIEW_LIMIT) {
                    previews += LeaderResearchScannerPoolImportPreviewItemDto(
                        category = category,
                        wallet = normalizedWallet,
                        source = poolCandidate.source,
                        discoveryScore = poolCandidate.discoveryScore,
                        action = action,
                        sourceEvidence = sourceEvidence
                    )
                }
            }

            createdTotal += created
            updatedTotal += updated
            skippedLockedTotal += skippedLocked
            skippedExistingTotal += skippedExisting
            categoryResults += LeaderResearchScannerPoolImportCategoryDto(
                category = category,
                requestedLimit = limit,
                selectedCount = selected.size,
                createdCount = created,
                updatedCount = updated,
                skippedLockedCount = skippedLocked,
                skippedExistingCount = skippedExisting
            )
        }

        return LeaderResearchScannerPoolImportResponse(
            dryRun = request.dryRun,
            requestedTotal = plans.sumOf { it.second },
            selectedTotal = selectedTotal,
            createdTotal = createdTotal,
            updatedTotal = updatedTotal,
            skippedLockedTotal = skippedLockedTotal,
            skippedExistingTotal = skippedExistingTotal,
            categories = categoryResults,
            previewItems = previews
        )
    }

    private fun selectCandidates(
        category: String,
        limit: Int,
        request: LeaderResearchScannerPoolImportRequest
    ): List<LeaderScannerCandidatePool> {
        val normalizedCategory = CategoryValidator.normalizeCategory(category) ?: category
        val raw = if (request.onlyPending) {
            scannerPoolRepository.findByCategoryAndAnalysisStateOrderByDiscoveryScoreDesc(
                normalizedCategory,
                "PENDING",
                PageRequest.of(0, limit * OVERSAMPLE_FACTOR)
            ).content
        } else {
            scannerPoolRepository.findByCategoryOrderByDiscoveryScoreDesc(normalizedCategory)
                .take(limit * OVERSAMPLE_FACTOR)
        }
        return raw.asSequence()
            .filter { it.normalizedWallet.matches(WALLET_REGEX) }
            .filter { request.minDiscoveryScore == null || it.discoveryScore >= request.minDiscoveryScore }
            .distinctBy { it.normalizedWallet.lowercase() }
            .let { candidates ->
                if (request.requireActivityQuality) {
                    applyActivityQualityFilter(candidates.toList(), request).asSequence()
                } else {
                    candidates
                }
            }
            .take(limit)
            .toList()
    }

    private fun applyActivityQualityFilter(
        candidates: List<LeaderScannerCandidatePool>,
        request: LeaderResearchScannerPoolImportRequest
    ): List<LeaderScannerCandidatePool> {
        if (candidates.isEmpty()) return emptyList()
        val wallets = candidates.map { it.normalizedWallet.lowercase() }.distinct()
        val metricsByWallet = activityEventRepository.aggregateDiscoveryMetricsForWallets(wallets)
            .associateBy { it.getNormalizedWallet().lowercase() }
        val minSafePriceRatio = request.minActivitySafePriceRatio.toBigDecimalOrNull() ?: BigDecimal("0.30")
        val maxTailPriceRatio = request.maxActivityTailPriceRatio.toBigDecimalOrNull() ?: BigDecimal("0.45")
        return candidates.filter { candidate ->
            val metrics = metricsByWallet[candidate.normalizedWallet.lowercase()] ?: return@filter false
            metrics.getTotalEvents() >= request.minActivityEvents &&
                metrics.getDistinctMarkets() >= request.minActivityDistinctMarkets &&
                metrics.getBuyEvents() >= request.minActivityBuyEvents &&
                metrics.getSellEvents() >= request.minActivitySellEvents &&
                ratio(metrics.getSafePriceEvents(), metrics.getTotalEvents()) >= minSafePriceRatio &&
                ratio(metrics.getTailPriceEvents(), metrics.getTotalEvents()) <= maxTailPriceRatio
        }
    }

    private fun ratio(numerator: Long, denominator: Long): BigDecimal {
        if (denominator <= 0) return BigDecimal.ZERO
        return BigDecimal(numerator).divide(BigDecimal(denominator), 8, RoundingMode.HALF_UP)
    }

    private fun sourceEvidence(poolCandidate: LeaderScannerCandidatePool): String {
        return listOfNotNull(
            "scanner_pool:${poolCandidate.id ?: "transient"}",
            "category:${poolCandidate.category}",
            "source:${poolCandidate.source}",
            "discovery_score:${poolCandidate.discoveryScore}",
            poolCandidate.sourceDetail?.takeIf { it.isNotBlank() }?.let { "detail:$it" }
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

    companion object {
        const val SOURCE_SCANNER_POOL = "SCANNER_POOL"
        private const val MAX_IMPORT_PER_CATEGORY = 1000
        private const val PREVIEW_LIMIT = 100
        private const val OVERSAMPLE_FACTOR = 3
        private val WALLET_REGEX = Regex("^0x[a-f0-9]{40}$")
    }
}
