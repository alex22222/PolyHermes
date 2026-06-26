package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportItemDto
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportPreviewItemDto
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportResponse
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderCandidateProvenance
import com.wrbug.polymarketbot.enums.LeaderResearchEventType
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.util.CategoryValidator
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional

@Service
class LeaderResearchExternalAnalyticsImportService(
    private val candidateRepository: LeaderResearchCandidateRepository,
    private val leaderRepository: LeaderRepository,
    private val eventService: LeaderResearchEventService
) {
    @Transactional
    fun importFromExternalAnalytics(request: LeaderResearchExternalAnalyticsImportRequest): LeaderResearchExternalAnalyticsImportResponse {
        val selected = request.items
            .take(request.maxItems.coerceIn(1, MAX_IMPORT_ITEMS))
            .map { normalizeItem(it, request) }
            .distinctBy { it.wallet }

        var created = 0
        var updated = 0
        var skippedInvalid = 0
        var skippedExisting = 0
        var skippedLocked = 0
        val previews = mutableListOf<LeaderResearchExternalAnalyticsImportPreviewItemDto>()

        selected.forEachIndexed { index, item ->
            if (!item.wallet.matches(WALLET_REGEX) || item.category !in ALLOWED_CATEGORIES) {
                skippedInvalid += 1
                if (previews.size < PREVIEW_LIMIT) previews += previewItem(item, "SKIP_INVALID", sourceEvidence(item, index))
                return@forEachIndexed
            }

            val sourceEvidence = sourceEvidence(item, index)
            val existing = candidateRepository.findByNormalizedWallet(item.wallet)
            val leader = leaderRepository.findByLeaderAddress(item.wallet)
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
                            normalizedWallet = item.wallet,
                            leaderId = leader?.id,
                            researchState = LeaderResearchState.DISCOVERED,
                            source = SOURCE_EXTERNAL_ANALYTICS,
                            sourceRank = item.externalRank ?: index + 1,
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
                            source = mergeSource(existing.source, SOURCE_EXTERNAL_ANALYTICS),
                            sourceRank = existing.sourceRank ?: item.externalRank ?: index + 1,
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
                    reason = "Candidate imported from external analytics",
                    payloadSummary = sourceEvidence,
                    dedupeKey = "external-analytics-import:${item.sourceName}:${item.wallet}"
                )
            }

            if (previews.size < PREVIEW_LIMIT) previews += previewItem(item, action, sourceEvidence)
        }

        return LeaderResearchExternalAnalyticsImportResponse(
            dryRun = request.dryRun,
            requestedTotal = request.items.size,
            selectedTotal = selected.size - skippedInvalid,
            createdTotal = created,
            updatedTotal = updated,
            skippedInvalidTotal = skippedInvalid,
            skippedExistingTotal = skippedExisting,
            skippedLockedTotal = skippedLocked,
            previewItems = previews
        )
    }

    private fun normalizeItem(
        item: LeaderResearchExternalAnalyticsImportItemDto,
        request: LeaderResearchExternalAnalyticsImportRequest
    ): NormalizedExternalItem {
        val wallet = item.wallet.trim().lowercase()
        val category = CategoryValidator.normalizeCategory(item.category)
            ?: CategoryValidator.normalizeCategory(request.defaultCategory)
            ?: request.defaultCategory.lowercase()
        val sourceName = item.sourceName.takeIf { it.isNotBlank() } ?: request.defaultSourceName
        return NormalizedExternalItem(
            wallet = wallet,
            category = category,
            sourceName = sourceName.trim().lowercase().replace(Regex("[^a-z0-9_.-]"), "_").take(64),
            externalRank = item.externalRank,
            externalScore = item.externalScore?.trim()?.takeIf { it.isNotBlank() },
            note = item.note?.trim()?.takeIf { it.isNotBlank() }?.take(240)
        )
    }

    private fun sourceEvidence(item: NormalizedExternalItem, index: Int): String {
        return listOfNotNull(
            "external_analytics:${item.sourceName}",
            "category:${item.category}",
            "rank:${item.externalRank ?: index + 1}",
            item.externalScore?.let { "external_score:$it" },
            item.note?.let { "note:$it" }
        ).joinToString(" | ")
    }

    private fun previewItem(
        item: NormalizedExternalItem,
        action: String,
        sourceEvidence: String
    ): LeaderResearchExternalAnalyticsImportPreviewItemDto {
        return LeaderResearchExternalAnalyticsImportPreviewItemDto(
            wallet = item.wallet,
            category = item.category,
            sourceName = item.sourceName,
            action = action,
            externalRank = item.externalRank,
            externalScore = item.externalScore,
            sourceEvidence = sourceEvidence
        )
    }

    private fun mergeSource(existing: String, incoming: String): String {
        val parts = (existing.split(",") + incoming)
            .map { it.trim() }
            .filter { it.isNotBlank() }
            .distinct()
        val merged = mutableListOf<String>()
        parts.forEach { part ->
            val candidate = (merged + part).joinToString(",")
            if (candidate.length <= MAX_SOURCE_LENGTH) {
                merged += part
            }
        }
        return merged.joinToString(",").ifBlank { incoming.take(MAX_SOURCE_LENGTH) }
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

    companion object {
        const val SOURCE_EXTERNAL_ANALYTICS = "EXTERNAL_ANALYTICS_SOURCE"
        private val WALLET_REGEX = Regex("^0x[a-f0-9]{40}$")
        private val ALLOWED_CATEGORIES = setOf("politics", "finance", "sports", "crypto")
        private const val MAX_SOURCE_LENGTH = 50
        private const val MAX_IMPORT_ITEMS = 1000
        private const val PREVIEW_LIMIT = 100
    }

    private data class NormalizedExternalItem(
        val wallet: String,
        val category: String,
        val sourceName: String,
        val externalRank: Int?,
        val externalScore: String?,
        val note: String?
    )
}
