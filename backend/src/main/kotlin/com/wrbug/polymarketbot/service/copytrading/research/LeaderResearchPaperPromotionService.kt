package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchPaperPromotionCategoryDto
import com.wrbug.polymarketbot.dto.LeaderResearchPaperPromotionItemDto
import com.wrbug.polymarketbot.dto.LeaderResearchPaperPromotionRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPaperPromotionResponse
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal

@Service
class LeaderResearchPaperPromotionService(
    private val candidateRepository: LeaderResearchCandidateRepository,
    private val stateMachine: LeaderResearchStateMachine
) {
    @Transactional
    fun promote(request: LeaderResearchPaperPromotionRequest): LeaderResearchPaperPromotionResponse {
        val minScore = request.minScore.toBigDecimalOrNull() ?: BigDecimal("80")
        val candidates = candidateRepository.findByResearchStateIn(
            listOf(LeaderResearchState.DISCOVERED, LeaderResearchState.CANDIDATE)
        )
        val plans = listOf(
            "politics" to request.politicsLimit,
            "finance" to request.financeLimit,
            "sports" to request.sportsLimit,
            "crypto" to request.cryptoLimit
        ).map { (category, limit) -> category to limit.coerceIn(0, MAX_PROMOTE_PER_CATEGORY) }

        val categories = mutableListOf<LeaderResearchPaperPromotionCategoryDto>()
        val items = mutableListOf<LeaderResearchPaperPromotionItemDto>()
        val effectiveTotalLimit = if (request.dryRun) Int.MAX_VALUE else LIVE_PROMOTE_BATCH_LIMIT
        var remainingLivePromotions = effectiveTotalLimit
        var requestedSelectedTotal = 0
        var selectedTotal = 0
        var promotedTotal = 0
        var skippedRiskTotal = 0

        plans.forEach { (category, limit) ->
            if (limit <= 0) {
                categories += LeaderResearchPaperPromotionCategoryDto(category, limit, 0, 0, 0)
                return@forEach
            }

            val categoryCandidates = candidates
                .asSequence()
                .filter { inferCategory(it) == category }
                .filter { (it.score ?: BigDecimal.ZERO) >= minScore }
                .filter { it.scoreVersion == LeaderResearchActivityScoringService.SCORE_VERSION }
                .sortedWith(
                    compareByDescending<LeaderResearchCandidate> { it.score ?: BigDecimal.ZERO }
                        .thenByDescending { it.lastScoredAt ?: 0L }
                )
                .toList()

            val safe = categoryCandidates.filter { isPromotableRisk(it.riskFlagsList()) }
            val requestedSelected = safe.take(limit)
            val selected = if (request.dryRun) {
                requestedSelected
            } else {
                requestedSelected.take(remainingLivePromotions.coerceAtLeast(0))
            }
            requestedSelectedTotal += requestedSelected.size
            selectedTotal += selected.size
            skippedRiskTotal += (categoryCandidates.size - safe.size).coerceAtLeast(0)
            if (!request.dryRun) {
                remainingLivePromotions = (remainingLivePromotions - selected.size).coerceAtLeast(0)
            }

            var promoted = 0
            selected.forEach { candidate ->
                val previousState = candidate.researchState
                val next = if (request.dryRun) {
                    candidate
                } else {
                    val once = stateMachine.advance(candidate, runId = null)
                    if (once.researchState == LeaderResearchState.CANDIDATE) {
                        stateMachine.advance(once, runId = null)
                    } else {
                        once
                    }
                }
                if (!request.dryRun && next.researchState == LeaderResearchState.PAPER && previousState != LeaderResearchState.PAPER) {
                    promoted += 1
                }
                items += LeaderResearchPaperPromotionItemDto(
                    candidateId = candidate.id ?: 0,
                    wallet = candidate.normalizedWallet,
                    category = category,
                    score = (candidate.score ?: BigDecimal.ZERO).toPlainString(),
                    previousState = previousState.name,
                    nextState = if (request.dryRun) expectedNextState(candidate).name else next.researchState.name,
                    riskFlags = candidate.riskFlagsList()
                )
            }

            promotedTotal += promoted
            categories += LeaderResearchPaperPromotionCategoryDto(
                category = category,
                requestedLimit = limit,
                selectedCount = selected.size,
                promotedCount = promoted,
                skippedRiskCount = (categoryCandidates.size - safe.size).coerceAtLeast(0)
            )
        }

        return LeaderResearchPaperPromotionResponse(
            dryRun = request.dryRun,
            minScore = minScore.toPlainString(),
            selectedTotal = selectedTotal,
            promotedTotal = promotedTotal,
            skippedRiskTotal = skippedRiskTotal,
            categories = categories,
            items = items.take(PREVIEW_LIMIT),
            requestedSelectedTotal = requestedSelectedTotal,
            effectiveSelectedLimit = if (request.dryRun) requestedSelectedTotal else LIVE_PROMOTE_BATCH_LIMIT,
            truncated = !request.dryRun && requestedSelectedTotal > selectedTotal
        )
    }

    private fun expectedNextState(candidate: LeaderResearchCandidate): LeaderResearchState {
        return when (candidate.researchState) {
            LeaderResearchState.DISCOVERED,
            LeaderResearchState.CANDIDATE -> LeaderResearchState.PAPER
            else -> candidate.researchState
        }
    }

    private fun isPromotableRisk(flags: List<String>): Boolean {
        return flags.none { it in HARD_EXCLUDE_FLAGS }
    }

    private fun LeaderResearchCandidate.riskFlagsList(): List<String> {
        return riskFlags.orEmpty()
            .split(",")
            .map { it.trim() }
            .filter { it.isNotBlank() }
            .distinct()
    }

    private fun inferCategory(candidate: LeaderResearchCandidate): String {
        return LeaderResearchCategoryEvidenceClassifier.classify(candidate.sourceEvidence, candidate.source).category
    }

    companion object {
        private const val MAX_PROMOTE_PER_CATEGORY = 100
        private const val LIVE_PROMOTE_BATCH_LIMIT = 8
        private const val PREVIEW_LIMIT = 100
        private val HARD_EXCLUDE_FLAGS = setOf(
            "tail_price_spray",
            "buy_only_no_exit",
            "low_safe_price_ratio",
            "no_activity_sample",
            "unknown_category",
            "mixed_category_evidence"
        )
    }
}
