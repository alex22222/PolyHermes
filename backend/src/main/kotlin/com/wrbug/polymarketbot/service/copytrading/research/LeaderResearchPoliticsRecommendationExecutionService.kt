package com.wrbug.polymarketbot.service.copytrading.research

import com.fasterxml.jackson.core.type.TypeReference
import com.fasterxml.jackson.databind.ObjectMapper
import com.wrbug.polymarketbot.entity.LeaderResearchRecommendationExecution
import com.wrbug.polymarketbot.dto.LeaderResearchActivityScoreRequest
import com.wrbug.polymarketbot.dto.LeaderResearchActivityScoreResponse
import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPaperProcessCandidateDto
import com.wrbug.polymarketbot.dto.LeaderResearchPaperProcessResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPaperPromotionRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPaperPromotionResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPaperScoreResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationActionPlanDto
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationExecutionSnapshotDto
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationExecuteRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationExecuteResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceDiagnoseRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceRecommendationDto
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderResearchRecommendationExecutionRepository
import org.springframework.data.domain.PageRequest
import org.springframework.stereotype.Service
import java.math.BigDecimal

@Service
class LeaderResearchPoliticsRecommendationExecutionService(
    private val diagnoseService: LeaderResearchPoliticsSourceDiagnoseService,
    private val activitySourceImportService: LeaderResearchActivitySourceImportService,
    private val activityScoringService: LeaderResearchActivityScoringService,
    private val paperPromotionService: LeaderResearchPaperPromotionService,
    private val paperTradingService: LeaderPaperTradingService,
    private val researchService: LeaderResearchService,
    private val scoringService: LeaderResearchScoringService,
    private val executionRepository: LeaderResearchRecommendationExecutionRepository,
    private val objectMapper: ObjectMapper
) {
    fun execute(request: LeaderResearchPoliticsRecommendationExecuteRequest): LeaderResearchPoliticsRecommendationExecuteResponse {
        val startedAt = System.currentTimeMillis()
        val category = normalizeCategory(request.diagnose.category)
        return try {
            val response = executeInternal(request, category)
            saveExecutionSnapshot(request, response, category, startedAt)
            response
        } catch (e: Exception) {
            saveExecutionFailure(request, category, startedAt, e)
            throw e
        }
    }

    fun executePrimaryCategoryDryRuns(): List<LeaderResearchPoliticsRecommendationExecuteResponse> {
        return PRIMARY_CATEGORIES.map { category ->
            execute(
                LeaderResearchPoliticsRecommendationExecuteRequest(
                    dryRun = true,
                    diagnose = LeaderResearchPoliticsSourceDiagnoseRequest(category = category)
                )
            )
        }
    }

    fun latestPoliticsExecution(): LeaderResearchPoliticsRecommendationExecutionSnapshotDto? {
        return latestExecution(POLITICS_CATEGORY)
    }

    fun recentPoliticsExecutions(limit: Int = 5): List<LeaderResearchPoliticsRecommendationExecutionSnapshotDto> {
        return recentExecutions(POLITICS_CATEGORY, limit)
    }

    fun latestPrimaryCategoryExecutions(): List<LeaderResearchPoliticsRecommendationExecutionSnapshotDto> {
        return PRIMARY_CATEGORIES.mapNotNull { category -> latestExecution(category) }
            .sortedByDescending { it.startedAt }
    }

    fun recentPrimaryCategoryExecutions(limitPerCategory: Int = 5): List<LeaderResearchPoliticsRecommendationExecutionSnapshotDto> {
        return PRIMARY_CATEGORIES.flatMap { category -> recentExecutions(category, limitPerCategory) }
            .sortedByDescending { it.startedAt }
    }

    private fun latestExecution(category: String): LeaderResearchPoliticsRecommendationExecutionSnapshotDto? {
        return executionRepository.findTopByCategoryOrderByStartedAtDesc(normalizeCategory(category))?.toDto()
    }

    private fun recentExecutions(category: String, limit: Int = 5): List<LeaderResearchPoliticsRecommendationExecutionSnapshotDto> {
        return executionRepository.findByCategoryOrderByStartedAtDesc(
            normalizeCategory(category),
            PageRequest.of(0, limit.coerceIn(1, MAX_RECENT_EXECUTIONS))
        ).content.map { it.toDto() }
    }

    private fun executeInternal(
        request: LeaderResearchPoliticsRecommendationExecuteRequest,
        category: String
    ): LeaderResearchPoliticsRecommendationExecuteResponse {
        val effectiveDryRun = request.dryRun || category != POLITICS_CATEGORY
        val diagnose = diagnoseService.diagnose(request.diagnose.copy(category = category))
        val recommendations = diagnose.recommendations
        val enabledActions = request.actions.map { it.uppercase() }.toSet()
        val recommendationCounts = recommendations.groupingBy { it.recommendation }.eachCount().toSortedMap()

        val importWallets = recommendations
            .filterAction("IMPORT_NOW", enabledActions)
            .map { it.wallet }
            .distinct()
            .take(request.maxImport.coerceIn(0, MAX_ACTION_ITEMS))
        val scoreRefreshCandidateIds = recommendations
            .filterAction("SCORE_REFRESH", enabledActions)
            .mapNotNull { it.candidateId }
            .distinct()
            .take(request.maxScoreRefresh.coerceIn(0, MAX_ACTION_ITEMS))
        val paperProcessCandidateIds = recommendations
            .filterAction("PAPER_PROCESS", enabledActions)
            .mapNotNull { it.candidateId }
            .distinct()
            .take(request.maxPaperProcess.coerceIn(0, MAX_ACTION_ITEMS))
        val fastWatchReviewCandidateIds = recommendations
            .filterAction("FAST_WATCH_REVIEW", enabledActions)
            .mapNotNull { it.candidateId }
            .distinct()
            .take(MAX_ACTION_ITEMS)
        val trialReadyCandidateIds = recommendations
            .filterAction("FAST_WATCH_REVIEW", enabledActions)
            .filter { it.currentState == LeaderResearchState.TRIAL_READY.name }
            .mapNotNull { it.candidateId }
            .distinct()
            .take(MAX_ACTION_ITEMS)

        val importResult = if (importWallets.isNotEmpty()) {
            activitySourceImportService.importFromActivitySource(
                LeaderResearchActivitySourceImportRequest(
                    dryRun = effectiveDryRun,
                    categories = listOf(category),
                    wallets = importWallets,
                    limitPerCategory = request.maxImport.coerceIn(1, MAX_ACTION_ITEMS),
                    lookbackDays = request.diagnose.lookbackDays,
                    minEvents = request.diagnose.minEvents,
                    minDistinctMarkets = request.diagnose.minDistinctMarkets,
                    minBuyEvents = request.diagnose.minBuyEvents,
                    minSellEvents = request.diagnose.minSellEvents,
                    minSafePriceRatio = request.diagnose.minSafePriceRatio,
                    maxTailPriceRatio = request.diagnose.maxTailPriceRatio
                )
            )
        } else {
            null
        }

        val activityScoreResult = if (!effectiveDryRun && scoreRefreshCandidateIds.isNotEmpty()) {
            activityScoringService.scoreActivityPrescreen(
                LeaderResearchActivityScoreRequest(
                    states = listOf(LeaderResearchState.DISCOVERED.name, LeaderResearchState.CANDIDATE.name),
                    force = true,
                    candidateIds = scoreRefreshCandidateIds
                )
            )
        } else {
            null
        }

        val promotionResult = if (scoreRefreshCandidateIds.isNotEmpty()) {
            paperPromotionService.promote(
                LeaderResearchPaperPromotionRequest(
                    minScore = request.promotionMinScore,
                    politicsLimit = if (category == POLITICS_CATEGORY) request.maxScoreRefresh.coerceIn(0, MAX_ACTION_ITEMS) else 0,
                    financeLimit = if (category == FINANCE_CATEGORY) request.maxScoreRefresh.coerceIn(0, MAX_ACTION_ITEMS) else 0,
                    sportsLimit = 0,
                    cryptoLimit = 0,
                    dryRun = effectiveDryRun,
                    candidateIds = scoreRefreshCandidateIds
                )
            )
        } else {
            null
        }

        val paperProcessResult = if (!effectiveDryRun && paperProcessCandidateIds.isNotEmpty()) {
            val effectiveBatchSize = request.paperProcessBatchSize.coerceIn(
                1,
                LeaderPaperTradingService.MANUAL_MAX_PROCESSING_BATCH_SIZE
            )
            val result = paperTradingService.processPaperCandidates(
                runId = null,
                batchSize = effectiveBatchSize,
                candidateIds = paperProcessCandidateIds
            )
            result.toResponse(
                requestedBatchSize = request.paperProcessBatchSize,
                effectiveBatchSize = effectiveBatchSize,
                truncated = request.paperProcessBatchSize != effectiveBatchSize
            )
        } else {
            null
        }

        val paperScoreResult = if (!effectiveDryRun && paperProcessCandidateIds.isNotEmpty()) {
            scorePaperCandidates(paperProcessCandidateIds)
        } else {
            null
        }

        return LeaderResearchPoliticsRecommendationExecuteResponse(
            dryRun = effectiveDryRun,
            generatedAt = System.currentTimeMillis(),
            recommendationCounts = recommendationCounts,
            plannedActions = listOf(
                actionPlan(
                    action = "IMPORT_NOW",
                    wallets = importWallets,
                    executed = importResult != null && !effectiveDryRun,
                    dryRun = effectiveDryRun,
                    actionEnabled = "IMPORT_NOW" in enabledActions
                ),
                actionPlan(
                    action = "SCORE_REFRESH",
                    candidateIds = scoreRefreshCandidateIds,
                    executed = activityScoreResult != null && !effectiveDryRun,
                    dryRun = effectiveDryRun,
                    actionEnabled = "SCORE_REFRESH" in enabledActions
                ),
                actionPlan(
                    action = "PAPER_PROCESS",
                    candidateIds = paperProcessCandidateIds,
                    executed = paperProcessResult != null && !effectiveDryRun,
                    dryRun = effectiveDryRun,
                    actionEnabled = "PAPER_PROCESS" in enabledActions
                ),
                actionPlan(
                    action = "FAST_WATCH_REVIEW",
                    candidateIds = fastWatchReviewCandidateIds,
                    executed = false,
                    dryRun = effectiveDryRun,
                    actionEnabled = "FAST_WATCH_REVIEW" in enabledActions,
                    skippedReason = if (fastWatchReviewCandidateIds.isEmpty()) "no_candidates" else "manual_review_required"
                )
            ),
            recommendations = recommendations,
            importResult = importResult,
            activityScoreResult = activityScoreResult,
            promotionResult = promotionResult,
            paperProcessResult = paperProcessResult,
            paperScoreResult = paperScoreResult,
            fastWatchReviewCandidateIds = fastWatchReviewCandidateIds,
            trialReadyCandidateIds = trialReadyCandidateIds
        )
    }

    private fun saveExecutionSnapshot(
        request: LeaderResearchPoliticsRecommendationExecuteRequest,
        response: LeaderResearchPoliticsRecommendationExecuteResponse,
        category: String,
        startedAt: Long
    ) {
        val finishedAt = System.currentTimeMillis()
        executionRepository.save(
            LeaderResearchRecommendationExecution(
                category = category,
                status = "SUCCESS",
                dryRun = response.dryRun,
                actionsJson = toJson(request.actions.map { it.uppercase() }),
                recommendationCountsJson = toJson(response.recommendationCounts),
                plannedActionsJson = toJson(response.plannedActions),
                resultSummaryJson = toJson(resultSummary(response)),
                requestJson = toJson(request),
                startedAt = startedAt,
                finishedAt = finishedAt,
                durationMs = finishedAt - startedAt
            )
        )
    }

    private fun saveExecutionFailure(
        request: LeaderResearchPoliticsRecommendationExecuteRequest,
        category: String,
        startedAt: Long,
        error: Exception
    ) {
        val finishedAt = System.currentTimeMillis()
        executionRepository.save(
            LeaderResearchRecommendationExecution(
                category = category,
                status = "FAILED",
                dryRun = request.dryRun || category != POLITICS_CATEGORY,
                actionsJson = toJson(request.actions.map { it.uppercase() }),
                requestJson = toJson(request),
                errorMessage = error.message,
                startedAt = startedAt,
                finishedAt = finishedAt,
                durationMs = finishedAt - startedAt
            )
        )
    }

    private fun resultSummary(response: LeaderResearchPoliticsRecommendationExecuteResponse): Map<String, Any?> {
        return linkedMapOf(
            "importSelected" to response.importResult?.selectedTotal,
            "importCreated" to response.importResult?.createdTotal,
            "importUpdated" to response.importResult?.updatedTotal,
            "activityScored" to response.activityScoreResult?.scoredCount,
            "promotionSelected" to response.promotionResult?.selectedTotal,
            "promotionPromoted" to response.promotionResult?.promotedTotal,
            "paperProcessed" to response.paperProcessResult?.processed,
            "paperFiltered" to response.paperProcessResult?.filtered,
            "paperFailed" to response.paperProcessResult?.failed,
            "paperScored" to response.paperScoreResult?.scoredCount,
            "fastWatchReviewCandidates" to response.fastWatchReviewCandidateIds.size,
            "trialReadyCandidates" to response.trialReadyCandidateIds.size
        )
    }

    private fun LeaderResearchRecommendationExecution.toDto(): LeaderResearchPoliticsRecommendationExecutionSnapshotDto {
        val plannedActions = readJson(
            plannedActionsJson,
            object : TypeReference<List<LeaderResearchPoliticsRecommendationActionPlanDto>>() {},
            emptyList()
        )
        val reviewCandidateIds = plannedActions
            .filter { it.action == "FAST_WATCH_REVIEW" }
            .flatMap { it.candidateIds }
            .distinct()
        val reviewCandidates = if (reviewCandidateIds.isEmpty()) {
            emptyList()
        } else {
            researchService.funnelCandidatesByIds(reviewCandidateIds)
        }
        return LeaderResearchPoliticsRecommendationExecutionSnapshotDto(
            id = id ?: 0,
            category = category,
            status = status,
            dryRun = dryRun,
            actions = readJson(actionsJson, object : TypeReference<List<String>>() {}, emptyList()),
            recommendationCounts = readJson(recommendationCountsJson, object : TypeReference<Map<String, Int>>() {}, emptyMap()),
            plannedActions = plannedActions,
            resultSummary = readJson(resultSummaryJson, object : TypeReference<Map<String, Any?>>() {}, emptyMap()),
            errorMessage = errorMessage,
            startedAt = startedAt,
            finishedAt = finishedAt,
            durationMs = durationMs,
            reviewCandidates = reviewCandidates
        )
    }

    private fun scorePaperCandidates(candidateIds: Collection<Long>): LeaderResearchPaperScoreResponse {
        val requestedIds = candidateIds.distinct().filter { it > 0 }
        val states = listOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY)
        val candidates = researchService.findCandidatesByIds(requestedIds)
            .filter { it.researchState in states }
        val scored = candidates.map { scoringService.scoreCandidate(it, runId = null) }
        val foundIds = candidates.mapNotNull { it.id }.toSet()
        return LeaderResearchPaperScoreResponse(
            scoredCount = scored.size,
            states = states.map { it.name },
            scoreVersion = LeaderResearchScoringService.SCORE_VERSION,
            targeted = true,
            requestedCandidateIds = requestedIds,
            missingCandidateIds = requestedIds.filter { it !in foundIds },
            effectiveCandidateCount = candidates.size,
            maxCandidates = requestedIds.size,
            truncated = false
        )
    }

    private fun actionPlan(
        action: String,
        candidateIds: List<Long> = emptyList(),
        wallets: List<String> = emptyList(),
        executed: Boolean,
        dryRun: Boolean,
        actionEnabled: Boolean,
        skippedReason: String? = null
    ): LeaderResearchPoliticsRecommendationActionPlanDto {
        val selectedCount = candidateIds.size + wallets.size
        return LeaderResearchPoliticsRecommendationActionPlanDto(
            action = action,
            selectedCount = selectedCount,
            candidateIds = candidateIds,
            wallets = wallets,
            executed = executed,
            skippedReason = skippedReason ?: when {
                !actionEnabled -> "action_disabled"
                selectedCount == 0 -> "no_candidates"
                dryRun -> "dry_run"
                !executed -> "not_executed"
                else -> null
            }
        )
    }

    private fun LeaderPaperProcessingResult.toResponse(
        requestedBatchSize: Int,
        effectiveBatchSize: Int,
        truncated: Boolean
    ): LeaderResearchPaperProcessResponse {
        return LeaderResearchPaperProcessResponse(
            processed = processed,
            filtered = filtered,
            failed = failed,
            requestedBatchSize = requestedBatchSize,
            effectiveBatchSize = effectiveBatchSize,
            maxBatchSize = LeaderPaperTradingService.MANUAL_MAX_PROCESSING_BATCH_SIZE,
            truncated = truncated,
            candidateSummaries = candidateSummaries.map { item ->
                LeaderResearchPaperProcessCandidateDto(
                    candidateId = item.candidateId,
                    wallet = item.wallet,
                    processed = item.processed,
                    filtered = item.filtered,
                    failed = item.failed,
                    beforeTradeCount = item.beforeTradeCount,
                    afterTradeCount = item.afterTradeCount,
                    tradeCountDelta = item.afterTradeCount - item.beforeTradeCount,
                    beforeFilteredCount = item.beforeFilteredCount,
                    afterFilteredCount = item.afterFilteredCount,
                    filteredCountDelta = item.afterFilteredCount - item.beforeFilteredCount,
                    beforeCopyablePnl = item.beforeCopyablePnl.strip(),
                    afterCopyablePnl = item.afterCopyablePnl.strip(),
                    copyablePnlDelta = item.afterCopyablePnl.subtract(item.beforeCopyablePnl).strip()
                )
            }
        )
    }

    private fun List<LeaderResearchPoliticsSourceRecommendationDto>.filterAction(
        action: String,
        enabledActions: Set<String>
    ): List<LeaderResearchPoliticsSourceRecommendationDto> {
        if (action !in enabledActions) return emptyList()
        return filter { it.recommendation == action }
    }

    private fun BigDecimal.strip(): String = stripTrailingZeros().toPlainString()

    private fun toJson(value: Any?): String? {
        return runCatching { objectMapper.writeValueAsString(value) }.getOrNull()
    }

    private fun <T> readJson(json: String?, type: TypeReference<T>, defaultValue: T): T {
        if (json.isNullOrBlank()) return defaultValue
        return runCatching { objectMapper.readValue(json, type) }.getOrDefault(defaultValue)
    }

    private fun normalizeCategory(category: String): String {
        val normalized = category.trim().lowercase()
        return if (normalized in PRIMARY_CATEGORIES) normalized else POLITICS_CATEGORY
    }

    companion object {
        private const val MAX_ACTION_ITEMS = 100
        private const val MAX_RECENT_EXECUTIONS = 20
        private const val POLITICS_CATEGORY = "politics"
        private const val FINANCE_CATEGORY = "finance"
        private val PRIMARY_CATEGORIES = listOf(POLITICS_CATEGORY, FINANCE_CATEGORY)
    }
}
