package com.wrbug.polymarketbot.controller.copytrading.research

import com.wrbug.polymarketbot.dto.ApiResponse
import com.wrbug.polymarketbot.dto.LeaderResearchApprovalRequest
import com.wrbug.polymarketbot.dto.LeaderResearchApprovalResponse
import com.wrbug.polymarketbot.dto.LeaderResearchCandidateDetailDto
import com.wrbug.polymarketbot.dto.LeaderResearchCandidateListRequest
import com.wrbug.polymarketbot.dto.LeaderResearchCandidateListResponse
import com.wrbug.polymarketbot.dto.LeaderResearchEventDto
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchFalconLeaderboardImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchFalconLeaderboardImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchFastWatchRequest
import com.wrbug.polymarketbot.dto.LeaderResearchFastWatchResponse
import com.wrbug.polymarketbot.dto.LeaderResearchFunnelResponse
import com.wrbug.polymarketbot.dto.LeaderResearchMarketPeerSourceImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchMarketPeerSourceImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardDiagnoseRequest
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardDiagnoseResponse
import com.wrbug.polymarketbot.dto.LeaderPaperSessionDto
import com.wrbug.polymarketbot.dto.LeaderResearchActivityScoreRequest
import com.wrbug.polymarketbot.dto.LeaderResearchActivityScoreResponse
import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPaperProcessCandidateDto
import com.wrbug.polymarketbot.dto.LeaderResearchPaperProcessRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPaperProcessResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPaperPromotionRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPaperPromotionResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPaperScoreRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPaperScoreResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationExecuteRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationExecutionSnapshotDto
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationExecuteResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceDiagnoseRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceDiagnoseResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPolymarketAnalyticsCopyTradeImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPolymarketAnalyticsCopyTradeImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPolyburgTelegramImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPolyburgTelegramImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchRunDto
import com.wrbug.polymarketbot.dto.LeaderResearchRunRequest
import com.wrbug.polymarketbot.dto.LeaderResearchScannerPoolImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchScannerPoolImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchSourceStateDto
import com.wrbug.polymarketbot.dto.LeaderResearchSummaryDto
import com.wrbug.polymarketbot.dto.LeaderResearchTrialReadyRecheckRequest
import com.wrbug.polymarketbot.dto.LeaderResearchTrialReadyRecheckResponse
import com.wrbug.polymarketbot.enums.ErrorCode
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.enums.LeaderResearchTriggerType
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchApprovalConfirmRequiredException
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchApprovalService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchActivityScoringService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchActivitySourceImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchCandidateNotReadyException
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchCandidateLockedException
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchDuplicateTrialConfigException
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchExternalAnalyticsImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchFalconLeaderboardImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchJobService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchMapper
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchMarketPeerSourceImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchOfficialLeaderboardImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchOfficialLeaderboardDiagnoseService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchPoliticsRecommendationExecutionService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchPoliticsSourceDiagnoseService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchRealMoneyForbiddenException
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchScannerPoolImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchScoringService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchPaperPromotionService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderPaperTradingService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchPolymarketAnalyticsCopyTradeImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchPolyburgTelegramImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchTrialReadyRecheckService
import org.slf4j.LoggerFactory
import org.springframework.context.MessageSource
import org.springframework.http.ResponseEntity
import org.springframework.web.bind.annotation.PostMapping
import org.springframework.web.bind.annotation.RequestBody
import org.springframework.web.bind.annotation.RequestMapping
import org.springframework.web.bind.annotation.RestController
import java.math.BigDecimal

data class LeaderResearchDetailRequest(val candidateId: Long)
data class LeaderResearchEventsRequest(val page: Int = 0, val size: Int = 50)
data class LeaderResearchPaperSessionsRequest(val candidateId: Long)

@RestController
@RequestMapping("/api/copy-trading/leader-research")
class LeaderResearchController(
    private val jobService: LeaderResearchJobService,
    private val researchService: LeaderResearchService,
    private val scannerPoolImportService: LeaderResearchScannerPoolImportService,
    private val activityScoringService: LeaderResearchActivityScoringService,
    private val activitySourceImportService: LeaderResearchActivitySourceImportService,
    private val marketPeerSourceImportService: LeaderResearchMarketPeerSourceImportService,
    private val externalAnalyticsImportService: LeaderResearchExternalAnalyticsImportService,
    private val falconLeaderboardImportService: LeaderResearchFalconLeaderboardImportService,
    private val polymarketAnalyticsCopyTradeImportService: LeaderResearchPolymarketAnalyticsCopyTradeImportService,
    private val polyburgTelegramImportService: LeaderResearchPolyburgTelegramImportService,
    private val officialLeaderboardImportService: LeaderResearchOfficialLeaderboardImportService,
    private val officialLeaderboardDiagnoseService: LeaderResearchOfficialLeaderboardDiagnoseService,
    private val politicsSourceDiagnoseService: LeaderResearchPoliticsSourceDiagnoseService,
    private val politicsRecommendationExecutionService: LeaderResearchPoliticsRecommendationExecutionService,
    private val paperTradingService: LeaderPaperTradingService,
    private val paperPromotionService: LeaderResearchPaperPromotionService,
    private val trialReadyRecheckService: LeaderResearchTrialReadyRecheckService,
    private val scoringService: LeaderResearchScoringService,
    private val approvalService: LeaderResearchApprovalService,
    private val mapper: LeaderResearchMapper,
    private val messageSource: MessageSource
) {
    private val logger = LoggerFactory.getLogger(LeaderResearchController::class.java)

    companion object {
        private const val PAPER_SCORE_TARGET_MAX = 500
    }

    @PostMapping("/run")
    fun run(@RequestBody request: LeaderResearchRunRequest): ResponseEntity<ApiResponse<LeaderResearchRunDto>> {
        return try {
            val trigger = runCatching { LeaderResearchTriggerType.valueOf(request.triggerType.uppercase()) }
                .getOrDefault(LeaderResearchTriggerType.MANUAL)
            val run = if (request.dryRun || trigger == LeaderResearchTriggerType.PREVIEW) {
                jobService.runOnce(request.dryRun, trigger)
            } else {
                jobService.startAsync(request.dryRun, trigger)
            }
            ResponseEntity.ok(ApiResponse.success(mapper.runDto(run)))
        } catch (e: Exception) {
            logger.error("Leader research run failed", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_LEADER_RESEARCH_RUN_FAILED, e.message, messageSource))
        }
    }

    @PostMapping("/summary")
    fun summary(): ResponseEntity<ApiResponse<LeaderResearchSummaryDto>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) { researchService.summary() }
    }

    @PostMapping("/funnel")
    fun funnel(): ResponseEntity<ApiResponse<LeaderResearchFunnelResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) { researchService.funnel() }
    }

    @PostMapping("/candidates/list")
    fun list(@RequestBody request: LeaderResearchCandidateListRequest): ResponseEntity<ApiResponse<LeaderResearchCandidateListResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) { researchService.listCandidates(request) }
    }

    @PostMapping("/candidates/detail")
    fun detail(@RequestBody request: LeaderResearchDetailRequest): ResponseEntity<ApiResponse<LeaderResearchCandidateDetailDto>> {
        if (request.candidateId <= 0) {
            return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, "candidateId 无效", messageSource))
        }
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) { researchService.detail(request.candidateId) }
    }

    @PostMapping("/paper-sessions")
    fun paperSessions(@RequestBody request: LeaderResearchPaperSessionsRequest): ResponseEntity<ApiResponse<List<LeaderPaperSessionDto>>> {
        if (request.candidateId <= 0) {
            return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, "candidateId 无效", messageSource))
        }
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) { researchService.paperSessions(request.candidateId) }
    }

    @PostMapping("/source-health")
    fun sourceHealth(): ResponseEntity<ApiResponse<List<LeaderResearchSourceStateDto>>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) { researchService.sourceHealth() }
    }

    @PostMapping("/events/list")
    fun events(@RequestBody request: LeaderResearchEventsRequest): ResponseEntity<ApiResponse<List<LeaderResearchEventDto>>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) { researchService.events(request.page, request.size) }
    }

    @PostMapping("/scanner-pool/import")
    fun importScannerPool(
        @RequestBody request: LeaderResearchScannerPoolImportRequest
    ): ResponseEntity<ApiResponse<LeaderResearchScannerPoolImportResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            scannerPoolImportService.importFromScannerPool(request)
        }
    }

    @PostMapping("/activity-score/run")
    fun runActivityScore(
        @RequestBody request: LeaderResearchActivityScoreRequest
    ): ResponseEntity<ApiResponse<LeaderResearchActivityScoreResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            activityScoringService.scoreActivityPrescreen(request)
        }
    }

    @PostMapping("/activity-source/import")
    fun importActivitySource(
        @RequestBody request: LeaderResearchActivitySourceImportRequest
    ): ResponseEntity<ApiResponse<LeaderResearchActivitySourceImportResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            activitySourceImportService.importFromActivitySource(request)
        }
    }

    @PostMapping("/market-peer-source/import")
    fun importMarketPeerSource(
        @RequestBody request: LeaderResearchMarketPeerSourceImportRequest
    ): ResponseEntity<ApiResponse<LeaderResearchMarketPeerSourceImportResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            marketPeerSourceImportService.importFromMarketPeerSource(request)
        }
    }

    @PostMapping("/external-analytics/import")
    fun importExternalAnalytics(
        @RequestBody request: LeaderResearchExternalAnalyticsImportRequest
    ): ResponseEntity<ApiResponse<LeaderResearchExternalAnalyticsImportResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            externalAnalyticsImportService.importFromExternalAnalytics(request)
        }
    }

    @PostMapping("/official-leaderboard/import")
    fun importOfficialLeaderboard(
        @RequestBody request: LeaderResearchOfficialLeaderboardImportRequest
    ): ResponseEntity<ApiResponse<LeaderResearchOfficialLeaderboardImportResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            officialLeaderboardImportService.importFromOfficialLeaderboard(request)
        }
    }

    @PostMapping("/falcon-leaderboard/import")
    fun importFalconLeaderboard(
        @RequestBody request: LeaderResearchFalconLeaderboardImportRequest
    ): ResponseEntity<ApiResponse<LeaderResearchFalconLeaderboardImportResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            falconLeaderboardImportService.importFromFalconLeaderboard(request)
        }
    }

    @PostMapping("/polyburg-telegram/import")
    fun importPolyburgTelegram(
        @RequestBody request: LeaderResearchPolyburgTelegramImportRequest
    ): ResponseEntity<ApiResponse<LeaderResearchPolyburgTelegramImportResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            polyburgTelegramImportService.importFromPolyburgTelegram(request)
        }
    }

    @PostMapping("/polymarket-analytics-copy-trade/import")
    fun importPolymarketAnalyticsCopyTrade(
        @RequestBody request: LeaderResearchPolymarketAnalyticsCopyTradeImportRequest
    ): ResponseEntity<ApiResponse<LeaderResearchPolymarketAnalyticsCopyTradeImportResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            polymarketAnalyticsCopyTradeImportService.importFromCopyTradePage(request)
        }
    }

    @PostMapping("/official-leaderboard/diagnose")
    fun diagnoseOfficialLeaderboard(
        @RequestBody request: LeaderResearchOfficialLeaderboardDiagnoseRequest
    ): ResponseEntity<ApiResponse<LeaderResearchOfficialLeaderboardDiagnoseResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            officialLeaderboardDiagnoseService.diagnose(request)
        }
    }

    @PostMapping("/politics-source/diagnose")
    fun diagnosePoliticsSource(
        @RequestBody request: LeaderResearchPoliticsSourceDiagnoseRequest
    ): ResponseEntity<ApiResponse<LeaderResearchPoliticsSourceDiagnoseResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            politicsSourceDiagnoseService.diagnose(request)
        }
    }

    @PostMapping("/politics-source/execute-recommendations")
    fun executePoliticsRecommendations(
        @RequestBody(required = false) request: LeaderResearchPoliticsRecommendationExecuteRequest?
    ): ResponseEntity<ApiResponse<LeaderResearchPoliticsRecommendationExecuteResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            politicsRecommendationExecutionService.execute(request ?: LeaderResearchPoliticsRecommendationExecuteRequest())
        }
    }

    @PostMapping("/politics-source/recommendation-executions/latest")
    fun latestPoliticsRecommendationExecution(): ResponseEntity<ApiResponse<LeaderResearchPoliticsRecommendationExecutionSnapshotDto?>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            politicsRecommendationExecutionService.latestPoliticsExecution()
        }
    }

    @PostMapping("/politics-source/recommendation-executions/recent")
    fun recentPoliticsRecommendationExecutions(): ResponseEntity<ApiResponse<List<LeaderResearchPoliticsRecommendationExecutionSnapshotDto>>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            politicsRecommendationExecutionService.recentPoliticsExecutions()
        }
    }

    @PostMapping("/primary-source/recommendation-executions/latest")
    fun latestPrimaryCategoryRecommendationExecutions(): ResponseEntity<ApiResponse<List<LeaderResearchPoliticsRecommendationExecutionSnapshotDto>>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            politicsRecommendationExecutionService.latestPrimaryCategoryExecutions()
        }
    }

    @PostMapping("/primary-source/recommendation-executions/recent")
    fun recentPrimaryCategoryRecommendationExecutions(): ResponseEntity<ApiResponse<List<LeaderResearchPoliticsRecommendationExecutionSnapshotDto>>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            politicsRecommendationExecutionService.recentPrimaryCategoryExecutions()
        }
    }

    @PostMapping("/activity-score/promote-paper")
    fun promoteActivityScoreToPaper(
        @RequestBody request: LeaderResearchPaperPromotionRequest
    ): ResponseEntity<ApiResponse<LeaderResearchPaperPromotionResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            paperPromotionService.promote(request)
        }
    }

    @PostMapping("/paper/process")
    fun processPaper(
        @RequestBody request: LeaderResearchPaperProcessRequest
    ): ResponseEntity<ApiResponse<LeaderResearchPaperProcessResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            val effectiveBatchSize = request.batchSize.coerceIn(1, LeaderPaperTradingService.MANUAL_MAX_PROCESSING_BATCH_SIZE)
            val result = paperTradingService.processPaperCandidates(
                runId = null,
                batchSize = effectiveBatchSize,
                candidateIds = request.candidateIds
            )
            LeaderResearchPaperProcessResponse(
                processed = result.processed,
                filtered = result.filtered,
                failed = result.failed,
                requestedBatchSize = request.batchSize,
                effectiveBatchSize = effectiveBatchSize,
                maxBatchSize = LeaderPaperTradingService.MANUAL_MAX_PROCESSING_BATCH_SIZE,
                truncated = request.batchSize != effectiveBatchSize,
                candidateSummaries = result.candidateSummaries.map { item ->
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
    }

    @PostMapping("/paper/score")
    fun scorePaper(
        @RequestBody(required = false) request: LeaderResearchPaperScoreRequest?
    ): ResponseEntity<ApiResponse<LeaderResearchPaperScoreResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            val states = listOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY)
            val requestedIds = request?.candidateIds.orEmpty().distinct().filter { it > 0 }
            val targeted = requestedIds.isNotEmpty()
            val candidates = if (targeted) {
                researchService.findCandidatesByIds(requestedIds)
                    .filter { it.researchState in states }
            } else {
                researchService.findCandidatesForStates(states)
            }
            val maxCandidates = request?.maxCandidates?.coerceIn(1, PAPER_SCORE_TARGET_MAX) ?: PAPER_SCORE_TARGET_MAX
            val selectedCandidates = if (targeted) candidates.take(maxCandidates) else candidates
            val selectedIds = selectedCandidates.mapNotNull { it.id }.toSet()
            val foundIds = candidates.mapNotNull { it.id }.toSet()
            val scored = selectedCandidates
                .map { scoringService.scoreCandidate(it, runId = null) }
            LeaderResearchPaperScoreResponse(
                scoredCount = scored.size,
                states = states.map { it.name },
                scoreVersion = LeaderResearchScoringService.SCORE_VERSION,
                targeted = targeted,
                requestedCandidateIds = requestedIds,
                missingCandidateIds = if (targeted) requestedIds.filter { it !in foundIds } else emptyList(),
                effectiveCandidateCount = selectedIds.size,
                maxCandidates = if (targeted) maxCandidates else null,
                truncated = targeted && candidates.size > selectedCandidates.size
            )
        }
    }

    @PostMapping("/paper/fast-watch")
    fun fastWatch(
        @RequestBody(required = false) request: LeaderResearchFastWatchRequest?
    ): ResponseEntity<ApiResponse<LeaderResearchFastWatchResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            researchService.fastWatch(request ?: LeaderResearchFastWatchRequest())
        }
    }

    @PostMapping("/paper/trial-ready/recheck")
    fun recheckTrialReady(
        @RequestBody(required = false) request: LeaderResearchTrialReadyRecheckRequest?
    ): ResponseEntity<ApiResponse<LeaderResearchTrialReadyRecheckResponse>> {
        return safe(ErrorCode.SERVER_LEADER_RESEARCH_FETCH_FAILED) {
            trialReadyRecheckService.recheck(request ?: LeaderResearchTrialReadyRecheckRequest())
        }
    }

    @PostMapping("/approval/create-disabled-trial-config")
    fun approve(@RequestBody request: LeaderResearchApprovalRequest): ResponseEntity<ApiResponse<LeaderResearchApprovalResponse>> {
        if (request.candidateId <= 0) {
            return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_INVALID, "candidateId 无效", messageSource))
        }
        if (request.accountId <= 0) {
            return ResponseEntity.ok(ApiResponse.error(ErrorCode.PARAM_ACCOUNT_ID_INVALID, messageSource = messageSource))
        }
        return try {
            approvalService.createDisabledTrialConfig(request).fold(
                onSuccess = { ResponseEntity.ok(ApiResponse.success(it)) },
                onFailure = { e -> errorResponse(e, ErrorCode.SERVER_LEADER_RESEARCH_APPROVAL_FAILED) }
            )
        } catch (e: Exception) {
            logger.error("Leader research approval failed", e)
            ResponseEntity.ok(ApiResponse.error(ErrorCode.SERVER_LEADER_RESEARCH_APPROVAL_FAILED, e.message, messageSource))
        }
    }

    private fun <T> safe(errorCode: ErrorCode, block: () -> T): ResponseEntity<ApiResponse<T>> {
        return try {
            ResponseEntity.ok(ApiResponse.success(block()))
        } catch (e: Exception) {
            logger.error("Leader research request failed", e)
            ResponseEntity.ok(ApiResponse.error(errorCode, e.message, messageSource))
        }
    }

    private fun <T> errorResponse(e: Throwable, fallback: ErrorCode): ResponseEntity<ApiResponse<T>> {
        val errorCode = when (e) {
            is LeaderResearchCandidateNotReadyException -> ErrorCode.LEADER_RESEARCH_CANDIDATE_NOT_READY
            is LeaderResearchApprovalConfirmRequiredException -> ErrorCode.LEADER_RESEARCH_APPROVAL_CONFIRM_REQUIRED
            is LeaderResearchDuplicateTrialConfigException -> ErrorCode.LEADER_RESEARCH_DUPLICATE_TRIAL_CONFIG
            is LeaderResearchRealMoneyForbiddenException -> ErrorCode.LEADER_RESEARCH_REAL_MONEY_FORBIDDEN
            is LeaderResearchCandidateLockedException -> ErrorCode.LEADER_RESEARCH_CANDIDATE_LOCKED
            is IllegalArgumentException -> when (e.message) {
                "账户不存在" -> ErrorCode.ACCOUNT_NOT_FOUND
                "候选不存在" -> ErrorCode.LEADER_RESEARCH_CANDIDATE_NOT_FOUND
                else -> ErrorCode.PARAM_ERROR
            }
            else -> fallback
        }
        return ResponseEntity.ok(ApiResponse.error(errorCode, null, messageSource))
    }

    private fun BigDecimal.strip(): String = stripTrailingZeros().toPlainString()
}
