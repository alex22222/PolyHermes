package com.wrbug.polymarketbot.controller.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchApprovalRequest
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchMarketPeerSourceImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchMarketPeerSourceImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchFastWatchRequest
import com.wrbug.polymarketbot.dto.LeaderResearchFastWatchResponse
import com.wrbug.polymarketbot.dto.LeaderResearchFunnelCandidateDto
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardDiagnoseRequest
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardDiagnoseResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPaperProcessRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPaperScoreRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationExecuteRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationExecutionSnapshotDto
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationExecuteResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceDiagnoseRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceDiagnoseResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPolymarketAnalyticsCopyTradeImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPolymarketAnalyticsCopyTradeImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPolyburgTelegramImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPolyburgTelegramImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchRunRequest
import com.wrbug.polymarketbot.dto.LeaderResearchTrialReadinessDto
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.entity.LeaderResearchRun
import com.wrbug.polymarketbot.entity.LeaderResearchScore
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.enums.LeaderResearchTriggerType
import com.wrbug.polymarketbot.enums.ErrorCode
import com.wrbug.polymarketbot.service.copytrading.research.LeaderPaperCandidateProcessingSummary
import com.wrbug.polymarketbot.service.copytrading.research.LeaderPaperProcessingResult
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchApprovalConfirmRequiredException
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchApprovalService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchActivityScoringService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchActivitySourceImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchCandidateLockedException
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchExternalAnalyticsImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchFalconLeaderboardImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchJobService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchMapper
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchMarketPeerSourceImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchOfficialLeaderboardImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchOfficialLeaderboardDiagnoseService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchPoliticsRecommendationExecutionService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchPoliticsSourceDiagnoseService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchPolymarketAnalyticsCopyTradeImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchPolyburgTelegramImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchScannerPoolImportService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchScoringService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchPaperPromotionService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderPaperTradingService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchTrialReadyRecheckService
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.springframework.context.support.StaticMessageSource
import java.math.BigDecimal

class LeaderResearchControllerTest {
    private val jobService: LeaderResearchJobService = mock()
    private val researchService: LeaderResearchService = mock()
    private val scannerPoolImportService: LeaderResearchScannerPoolImportService = mock()
    private val activityScoringService: LeaderResearchActivityScoringService = mock()
    private val activitySourceImportService: LeaderResearchActivitySourceImportService = mock()
    private val marketPeerSourceImportService: LeaderResearchMarketPeerSourceImportService = mock()
    private val externalAnalyticsImportService: LeaderResearchExternalAnalyticsImportService = mock()
    private val falconLeaderboardImportService: LeaderResearchFalconLeaderboardImportService = mock()
    private val polymarketAnalyticsCopyTradeImportService: LeaderResearchPolymarketAnalyticsCopyTradeImportService = mock()
    private val polyburgTelegramImportService: LeaderResearchPolyburgTelegramImportService = mock()
    private val officialLeaderboardImportService: LeaderResearchOfficialLeaderboardImportService = mock()
    private val officialLeaderboardDiagnoseService: LeaderResearchOfficialLeaderboardDiagnoseService = mock()
    private val politicsSourceDiagnoseService: LeaderResearchPoliticsSourceDiagnoseService = mock()
    private val politicsRecommendationExecutionService: LeaderResearchPoliticsRecommendationExecutionService = mock()
    private val paperTradingService: LeaderPaperTradingService = mock()
    private val paperPromotionService: LeaderResearchPaperPromotionService = mock()
    private val trialReadyRecheckService: LeaderResearchTrialReadyRecheckService = mock()
    private val scoringService: LeaderResearchScoringService = mock()
    private val approvalService: LeaderResearchApprovalService = mock()
    private val mapper: LeaderResearchMapper = mock()
    private val controller = LeaderResearchController(
        jobService = jobService,
        researchService = researchService,
        scannerPoolImportService = scannerPoolImportService,
        activityScoringService = activityScoringService,
        activitySourceImportService = activitySourceImportService,
        marketPeerSourceImportService = marketPeerSourceImportService,
        externalAnalyticsImportService = externalAnalyticsImportService,
        falconLeaderboardImportService = falconLeaderboardImportService,
        polymarketAnalyticsCopyTradeImportService = polymarketAnalyticsCopyTradeImportService,
        polyburgTelegramImportService = polyburgTelegramImportService,
        officialLeaderboardImportService = officialLeaderboardImportService,
        officialLeaderboardDiagnoseService = officialLeaderboardDiagnoseService,
        politicsSourceDiagnoseService = politicsSourceDiagnoseService,
        politicsRecommendationExecutionService = politicsRecommendationExecutionService,
        paperTradingService = paperTradingService,
        paperPromotionService = paperPromotionService,
        trialReadyRecheckService = trialReadyRecheckService,
        scoringService = scoringService,
        approvalService = approvalService,
        mapper = mapper,
        messageSource = StaticMessageSource()
    )

    @Test
    fun `manual run queues async run and returns run dto`() {
        val run = LeaderResearchRun(id = 1L)
        Mockito.`when`(jobService.startAsync(false, LeaderResearchTriggerType.MANUAL)).thenReturn(run)
        Mockito.`when`(mapper.runDto(run)).thenReturn(
            com.wrbug.polymarketbot.dto.LeaderResearchRunDto(
                id = 1,
                status = "RUNNING",
                triggerType = "MANUAL",
                dryRun = false,
                startedAt = run.startedAt,
                finishedAt = null,
                durationMs = null,
                sourceCountsJson = null,
                candidateCountsJson = null,
                partialFailure = false,
                skippedReason = null,
                errorClass = null,
                errorMessage = null
            )
        )

        val response = controller.run(LeaderResearchRunRequest())

        assertEquals(0, response.body!!.code)
        assertEquals(1, response.body!!.data!!.id)
        Mockito.verify(jobService).startAsync(false, LeaderResearchTriggerType.MANUAL)
        Mockito.verify(jobService, Mockito.never()).runOnce(false, LeaderResearchTriggerType.MANUAL)
    }

    @Test
    fun `preview run stays synchronous`() {
        val run = LeaderResearchRun(id = 2L, dryRun = true, triggerType = LeaderResearchTriggerType.PREVIEW)
        Mockito.`when`(jobService.runOnce(true, LeaderResearchTriggerType.PREVIEW)).thenReturn(run)
        Mockito.`when`(mapper.runDto(run)).thenReturn(
            com.wrbug.polymarketbot.dto.LeaderResearchRunDto(
                id = 2,
                status = "SUCCESS",
                triggerType = "PREVIEW",
                dryRun = true,
                startedAt = run.startedAt,
                finishedAt = null,
                durationMs = null,
                sourceCountsJson = null,
                candidateCountsJson = null,
                partialFailure = false,
                skippedReason = null,
                errorClass = null,
                errorMessage = null
            )
        )

        val response = controller.run(LeaderResearchRunRequest(dryRun = true, triggerType = "PREVIEW"))

        assertEquals(0, response.body!!.code)
        assertEquals(2, response.body!!.data!!.id)
        Mockito.verify(jobService).runOnce(true, LeaderResearchTriggerType.PREVIEW)
        Mockito.verify(jobService, Mockito.never()).startAsync(true, LeaderResearchTriggerType.PREVIEW)
    }

    @Test
    fun `detail rejects invalid candidate id`() {
        val response = controller.detail(LeaderResearchDetailRequest(candidateId = 0))

        assertEquals(ErrorCode.PARAM_INVALID.code, response.body!!.code)
    }

    @Test
    fun `paper process caps oversized manual batch and reports effective size`() {
        Mockito.`when`(paperTradingService.processPaperCandidates(runId = null, batchSize = 20, candidateIds = emptyList()))
            .thenReturn(LeaderPaperProcessingResult(processed = 7, filtered = 3, failed = 0))

        val response = controller.processPaper(LeaderResearchPaperProcessRequest(batchSize = 100))

        assertEquals(0, response.body!!.code)
        assertEquals(7, response.body!!.data!!.processed)
        assertEquals(3, response.body!!.data!!.filtered)
        assertEquals(100, response.body!!.data!!.requestedBatchSize)
        assertEquals(20, response.body!!.data!!.effectiveBatchSize)
        assertEquals(20, response.body!!.data!!.maxBatchSize)
        assertEquals(true, response.body!!.data!!.truncated)
        Mockito.verify(paperTradingService).processPaperCandidates(runId = null, batchSize = 20, candidateIds = emptyList())
    }

    @Test
    fun `paper process passes targeted candidate ids`() {
        Mockito.`when`(paperTradingService.processPaperCandidates(runId = null, batchSize = 5, candidateIds = listOf(42L, 43L)))
            .thenReturn(
                LeaderPaperProcessingResult(
                    processed = 4,
                    filtered = 1,
                    failed = 0,
                    candidateSummaries = listOf(
                        LeaderPaperCandidateProcessingSummary(
                            candidateId = 42L,
                            wallet = "0x4242424242424242424242424242424242424242",
                            processed = 4,
                            filtered = 1,
                            failed = 0,
                            beforeTradeCount = 18,
                            afterTradeCount = 22,
                            beforeFilteredCount = 2,
                            afterFilteredCount = 3,
                            beforeCopyablePnl = BigDecimal("1.25"),
                            afterCopyablePnl = BigDecimal("2.75")
                        )
                    )
                )
            )

        val response = controller.processPaper(
            LeaderResearchPaperProcessRequest(batchSize = 5, candidateIds = listOf(42L, 43L))
        )

        assertEquals(0, response.body!!.code)
        assertEquals(4, response.body!!.data!!.processed)
        assertEquals(1, response.body!!.data!!.filtered)
        assertEquals(5, response.body!!.data!!.effectiveBatchSize)
        val summary = response.body!!.data!!.candidateSummaries.single()
        assertEquals(42L, summary.candidateId)
        assertEquals(4, summary.tradeCountDelta)
        assertEquals(1, summary.filteredCountDelta)
        assertEquals("1.5", summary.copyablePnlDelta)
        Mockito.verify(paperTradingService).processPaperCandidates(runId = null, batchSize = 5, candidateIds = listOf(42L, 43L))
    }

    @Test
    fun `paper score can target candidate ids without full paper scan`() {
        val candidate = LeaderResearchCandidate(
            id = 42L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            researchState = LeaderResearchState.PAPER
        )
        val score = LeaderResearchScore(
            candidateId = 42L,
            scoreVersion = LeaderResearchScoringService.SCORE_VERSION,
            totalScore = BigDecimal("90")
        )
        Mockito.`when`(researchService.findCandidatesByIds(listOf(42L, 404L))).thenReturn(listOf(candidate))
        Mockito.`when`(scoringService.scoreCandidate(candidate, runId = null)).thenReturn(score)

        val response = controller.scorePaper(
            LeaderResearchPaperScoreRequest(candidateIds = listOf(42L, 404L), maxCandidates = 10)
        )

        assertEquals(0, response.body!!.code)
        assertEquals(1, response.body!!.data!!.scoredCount)
        assertEquals(true, response.body!!.data!!.targeted)
        assertEquals(listOf(42L, 404L), response.body!!.data!!.requestedCandidateIds)
        assertEquals(listOf(404L), response.body!!.data!!.missingCandidateIds)
        assertEquals(1, response.body!!.data!!.effectiveCandidateCount)
        assertEquals(10, response.body!!.data!!.maxCandidates)
        assertEquals(false, response.body!!.data!!.truncated)
        Mockito.verify(researchService).findCandidatesByIds(listOf(42L, 404L))
        Mockito.verify(scoringService).scoreCandidate(candidate, runId = null)
    }

    @Test
    fun `paper fast watch delegates to research service`() {
        val request = LeaderResearchFastWatchRequest(categories = listOf("finance"), limit = 5)
        val result = LeaderResearchFastWatchResponse(
            total = 1,
            fastWatchCount = 1,
            trialReadyCount = 0,
            categories = listOf("finance"),
            criteria = "criteria",
            items = listOf(
                LeaderResearchFunnelCandidateDto(
                    candidateId = 42L,
                    wallet = "0x1111111111111111111111111111111111111111",
                    category = "finance",
                    score = "90",
                    tradeCount = 25,
                    filteredRatio = "0.1",
                    copyablePnl = "5",
                    maxDrawdown = "0",
                    researchState = "PAPER",
                    trialReadiness = LeaderResearchTrialReadinessDto(
                        eligible = false,
                        level = "FAST_WATCH",
                        label = "快速观察",
                        blockers = listOf("PAPER 观察不足 7 天：当前 96 小时"),
                        fastWatchBlockers = emptyList(),
                        ageHours = 96,
                        stableHighScoreCount = 3,
                        requiredStableHighScoreCount = 3
                    )
                )
            ),
            generatedAt = 123L
        )
        Mockito.`when`(researchService.fastWatch(request)).thenReturn(result)

        val response = controller.fastWatch(request)

        assertEquals(0, response.body!!.code)
        assertEquals(1, response.body!!.data!!.fastWatchCount)
        assertEquals("FAST_WATCH", response.body!!.data!!.items.first().trialReadiness.level)
        Mockito.verify(researchService).fastWatch(request)
    }

    @Test
    fun `politics source diagnose delegates to service`() {
        val request = LeaderResearchPoliticsSourceDiagnoseRequest(limit = 25)
        val diagnose = LeaderResearchPoliticsSourceDiagnoseResponse(
            category = "politics",
            lookbackDays = 60,
            scannedWallets = 10,
            passImportCriteria = 3,
            unknownWallets = 1,
            existingWallets = 9,
            paperWallets = 2,
            cleanHighWallets = 1,
            eligibleForPaperNow = 0,
            buckets = emptyList(),
            samples = emptyList(),
            generatedAt = 123L
        )
        Mockito.`when`(politicsSourceDiagnoseService.diagnose(request)).thenReturn(diagnose)

        val response = controller.diagnosePoliticsSource(request)

        assertEquals(0, response.body!!.code)
        assertEquals(10, response.body!!.data!!.scannedWallets)
        Mockito.verify(politicsSourceDiagnoseService).diagnose(request)
    }

    @Test
    fun `politics recommendation execution delegates to service`() {
        val request = LeaderResearchPoliticsRecommendationExecuteRequest(dryRun = true, maxPaperProcess = 3)
        val result = LeaderResearchPoliticsRecommendationExecuteResponse(
            dryRun = true,
            generatedAt = 123L,
            recommendationCounts = mapOf("PAPER_PROCESS" to 2),
            plannedActions = emptyList(),
            recommendations = emptyList()
        )
        Mockito.`when`(politicsRecommendationExecutionService.execute(request)).thenReturn(result)

        val response = controller.executePoliticsRecommendations(request)

        assertEquals(0, response.body!!.code)
        assertEquals(true, response.body!!.data!!.dryRun)
        assertEquals(2, response.body!!.data!!.recommendationCounts["PAPER_PROCESS"])
        Mockito.verify(politicsRecommendationExecutionService).execute(request)
    }

    @Test
    fun `latest politics recommendation execution delegates to service`() {
        val result = LeaderResearchPoliticsRecommendationExecutionSnapshotDto(
            id = 7L,
            category = "politics",
            status = "SUCCESS",
            dryRun = true,
            actions = listOf("IMPORT_NOW"),
            recommendationCounts = mapOf("IMPORT_NOW" to 1),
            plannedActions = emptyList(),
            resultSummary = emptyMap(),
            errorMessage = null,
            startedAt = 100L,
            finishedAt = 120L,
            durationMs = 20L
        )
        Mockito.`when`(politicsRecommendationExecutionService.latestPoliticsExecution()).thenReturn(result)

        val response = controller.latestPoliticsRecommendationExecution()

        assertEquals(0, response.body!!.code)
        assertEquals(7L, response.body!!.data!!.id)
        assertEquals("SUCCESS", response.body!!.data!!.status)
        Mockito.verify(politicsRecommendationExecutionService).latestPoliticsExecution()
    }

    @Test
    fun `recent politics recommendation executions delegates to service`() {
        val result = listOf(
            LeaderResearchPoliticsRecommendationExecutionSnapshotDto(
                id = 8L,
                category = "politics",
                status = "SUCCESS",
                dryRun = true,
                actions = listOf("PAPER_PROCESS"),
                recommendationCounts = mapOf("PAPER_PROCESS" to 0),
                plannedActions = emptyList(),
                resultSummary = emptyMap(),
                errorMessage = null,
                startedAt = 200L,
                finishedAt = 220L,
                durationMs = 20L
            )
        )
        Mockito.`when`(politicsRecommendationExecutionService.recentPoliticsExecutions()).thenReturn(result)

        val response = controller.recentPoliticsRecommendationExecutions()

        assertEquals(0, response.body!!.code)
        assertEquals(1, response.body!!.data!!.size)
        assertEquals(8L, response.body!!.data!!.first().id)
        Mockito.verify(politicsRecommendationExecutionService).recentPoliticsExecutions()
    }

    @Test
    fun `latest primary category recommendation executions delegates to service`() {
        val result = listOf(
            LeaderResearchPoliticsRecommendationExecutionSnapshotDto(
                id = 9L,
                category = "finance",
                status = "SUCCESS",
                dryRun = true,
                actions = listOf("PAPER_PROCESS"),
                recommendationCounts = mapOf("PAPER_PROCESS" to 2),
                plannedActions = emptyList(),
                resultSummary = emptyMap(),
                errorMessage = null,
                startedAt = 300L,
                finishedAt = 320L,
                durationMs = 20L
            ),
            LeaderResearchPoliticsRecommendationExecutionSnapshotDto(
                id = 8L,
                category = "politics",
                status = "SUCCESS",
                dryRun = true,
                actions = listOf("FAST_WATCH_REVIEW"),
                recommendationCounts = mapOf("FAST_WATCH_REVIEW" to 1),
                plannedActions = emptyList(),
                resultSummary = emptyMap(),
                errorMessage = null,
                startedAt = 200L,
                finishedAt = 220L,
                durationMs = 20L
            )
        )
        Mockito.`when`(politicsRecommendationExecutionService.latestPrimaryCategoryExecutions()).thenReturn(result)

        val response = controller.latestPrimaryCategoryRecommendationExecutions()

        assertEquals(0, response.body!!.code)
        assertEquals(listOf("finance", "politics"), response.body!!.data!!.map { it.category })
        Mockito.verify(politicsRecommendationExecutionService).latestPrimaryCategoryExecutions()
    }

    @Test
    fun `recent primary category recommendation executions delegates to service`() {
        val result = listOf(
            LeaderResearchPoliticsRecommendationExecutionSnapshotDto(
                id = 10L,
                category = "finance",
                status = "SUCCESS",
                dryRun = true,
                actions = listOf("PAPER_PROCESS"),
                recommendationCounts = mapOf("PAPER_PROCESS" to 1),
                plannedActions = emptyList(),
                resultSummary = emptyMap(),
                errorMessage = null,
                startedAt = 400L,
                finishedAt = 420L,
                durationMs = 20L
            )
        )
        Mockito.`when`(politicsRecommendationExecutionService.recentPrimaryCategoryExecutions()).thenReturn(result)

        val response = controller.recentPrimaryCategoryRecommendationExecutions()

        assertEquals(0, response.body!!.code)
        assertEquals(1, response.body!!.data!!.size)
        assertEquals("finance", response.body!!.data!!.first().category)
        Mockito.verify(politicsRecommendationExecutionService).recentPrimaryCategoryExecutions()
    }

    @Test
    fun `market peer source import delegates to service`() {
        val request = LeaderResearchMarketPeerSourceImportRequest(dryRun = true, categories = listOf("politics"), limitPerCategory = 5)
        val result = LeaderResearchMarketPeerSourceImportResponse(
            dryRun = true,
            requestedCategories = listOf("politics"),
            selectedTotal = 2,
            createdTotal = 2,
            updatedTotal = 0,
            skippedExistingTotal = 0,
            skippedLockedTotal = 0,
            categories = emptyList(),
            previewItems = emptyList()
        )
        Mockito.`when`(marketPeerSourceImportService.importFromMarketPeerSource(request)).thenReturn(result)

        val response = controller.importMarketPeerSource(request)

        assertEquals(0, response.body!!.code)
        assertEquals(2, response.body!!.data!!.selectedTotal)
        Mockito.verify(marketPeerSourceImportService).importFromMarketPeerSource(request)
    }

    @Test
    fun `external analytics import delegates to service`() {
        val request = LeaderResearchExternalAnalyticsImportRequest(dryRun = true)
        val result = LeaderResearchExternalAnalyticsImportResponse(
            dryRun = true,
            requestedTotal = 1,
            selectedTotal = 1,
            createdTotal = 1,
            updatedTotal = 0,
            skippedInvalidTotal = 0,
            skippedExistingTotal = 0,
            skippedLockedTotal = 0,
            previewItems = emptyList()
        )
        Mockito.`when`(externalAnalyticsImportService.importFromExternalAnalytics(request)).thenReturn(result)

        val response = controller.importExternalAnalytics(request)

        assertEquals(0, response.body!!.code)
        assertEquals(1, response.body!!.data!!.createdTotal)
        Mockito.verify(externalAnalyticsImportService).importFromExternalAnalytics(request)
    }

    @Test
    fun `official leaderboard import delegates to service`() {
        val request = LeaderResearchOfficialLeaderboardImportRequest(dryRun = true, categories = listOf("politics"))
        val importResult = LeaderResearchExternalAnalyticsImportResponse(
            dryRun = true,
            requestedTotal = 2,
            selectedTotal = 2,
            createdTotal = 1,
            updatedTotal = 1,
            skippedInvalidTotal = 0,
            skippedExistingTotal = 0,
            skippedLockedTotal = 0,
            previewItems = emptyList()
        )
        val result = LeaderResearchOfficialLeaderboardImportResponse(
            dryRun = true,
            sourceName = "polymarket_official_leaderboard",
            fetchedTotal = 2,
            dedupedTotal = 2,
            fetches = emptyList(),
            importResult = importResult
        )
        Mockito.`when`(officialLeaderboardImportService.importFromOfficialLeaderboard(request)).thenReturn(result)

        val response = controller.importOfficialLeaderboard(request)

        assertEquals(0, response.body!!.code)
        assertEquals(2, response.body!!.data!!.dedupedTotal)
        Mockito.verify(officialLeaderboardImportService).importFromOfficialLeaderboard(request)
    }

    @Test
    fun `polyburg telegram import delegates to service`() {
        val request = LeaderResearchPolyburgTelegramImportRequest(dryRun = true, rawText = "0x1111111111111111111111111111111111111111")
        val importResult = LeaderResearchExternalAnalyticsImportResponse(
            dryRun = true,
            requestedTotal = 1,
            selectedTotal = 1,
            createdTotal = 1,
            updatedTotal = 0,
            skippedInvalidTotal = 0,
            skippedExistingTotal = 0,
            skippedLockedTotal = 0,
            previewItems = emptyList()
        )
        val result = LeaderResearchPolyburgTelegramImportResponse(
            dryRun = true,
            sourceName = "polyburg_telegram",
            parsedTotal = 1,
            dedupedTotal = 1,
            importResult = importResult
        )
        Mockito.`when`(polyburgTelegramImportService.importFromPolyburgTelegram(request)).thenReturn(result)

        val response = controller.importPolyburgTelegram(request)

        assertEquals(0, response.body!!.code)
        assertEquals(1, response.body!!.data!!.dedupedTotal)
        Mockito.verify(polyburgTelegramImportService).importFromPolyburgTelegram(request)
    }

    @Test
    fun `polymarket analytics copy trade import delegates to service`() {
        val request = LeaderResearchPolymarketAnalyticsCopyTradeImportRequest(
            dryRun = true,
            rawText = "0x1111111111111111111111111111111111111111"
        )
        val importResult = LeaderResearchExternalAnalyticsImportResponse(
            dryRun = true,
            requestedTotal = 1,
            selectedTotal = 1,
            createdTotal = 1,
            updatedTotal = 0,
            skippedInvalidTotal = 0,
            skippedExistingTotal = 0,
            skippedLockedTotal = 0,
            previewItems = emptyList()
        )
        val result = LeaderResearchPolymarketAnalyticsCopyTradeImportResponse(
            dryRun = true,
            sourceName = "polymarket_analytics_copy_trade",
            parsedTotal = 1,
            dedupedTotal = 1,
            importResult = importResult
        )
        Mockito.`when`(polymarketAnalyticsCopyTradeImportService.importFromCopyTradePage(request)).thenReturn(result)

        val response = controller.importPolymarketAnalyticsCopyTrade(request)

        assertEquals(0, response.body!!.code)
        assertEquals(1, response.body!!.data!!.dedupedTotal)
        Mockito.verify(polymarketAnalyticsCopyTradeImportService).importFromCopyTradePage(request)
    }

    @Test
    fun `official leaderboard diagnose delegates to service`() {
        val request = LeaderResearchOfficialLeaderboardDiagnoseRequest(sampleLimit = 5)
        val result = LeaderResearchOfficialLeaderboardDiagnoseResponse(
            total = 10,
            paperTotal = 2,
            cleanHighTotal = 1,
            fastWatchTotal = 1,
            readyForPaperTotal = 3,
            buckets = emptyList(),
            categories = emptyList(),
            riskFlagCounts = emptyMap(),
            samples = emptyList(),
            generatedAt = 123L
        )
        Mockito.`when`(officialLeaderboardDiagnoseService.diagnose(request)).thenReturn(result)

        val response = controller.diagnoseOfficialLeaderboard(request)

        assertEquals(0, response.body!!.code)
        assertEquals(10, response.body!!.data!!.total)
        Mockito.verify(officialLeaderboardDiagnoseService).diagnose(request)
    }

    @Test
    fun `approval maps confirm required`() {
        Mockito.`when`(approvalService.createDisabledTrialConfig(anyApprovalRequest()))
            .thenReturn(Result.failure(LeaderResearchApprovalConfirmRequiredException()))

        val response = controller.approve(LeaderResearchApprovalRequest(candidateId = 1, accountId = 2, confirm = false))

        assertEquals(ErrorCode.LEADER_RESEARCH_APPROVAL_CONFIRM_REQUIRED.code, response.body!!.code)
    }

    @Test
    fun `approval maps locked candidate`() {
        Mockito.`when`(approvalService.createDisabledTrialConfig(anyApprovalRequest()))
            .thenReturn(Result.failure(LeaderResearchCandidateLockedException()))

        val response = controller.approve(LeaderResearchApprovalRequest(candidateId = 1, accountId = 2, confirm = true))

        assertEquals(ErrorCode.LEADER_RESEARCH_CANDIDATE_LOCKED.code, response.body!!.code)
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)

    private fun anyApprovalRequest(): LeaderResearchApprovalRequest {
        Mockito.any(LeaderResearchApprovalRequest::class.java)
        return LeaderResearchApprovalRequest(candidateId = 1, accountId = 2, confirm = true)
    }
}
