package com.wrbug.polymarketbot.service.copytrading.research

import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.wrbug.polymarketbot.dto.LeaderResearchActivityScoreResponse
import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchFunnelCandidateDto
import com.wrbug.polymarketbot.dto.LeaderResearchPaperPromotionResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationExecuteRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceDiagnoseRequest
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceDiagnoseResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPoliticsSourceRecommendationDto
import com.wrbug.polymarketbot.dto.LeaderResearchTrialReadinessDto
import com.wrbug.polymarketbot.entity.LeaderResearchRecommendationExecution
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderResearchRecommendationExecutionRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.mockito.ArgumentCaptor
import org.springframework.data.domain.PageImpl
import org.springframework.data.domain.PageRequest

class LeaderResearchPoliticsRecommendationExecutionServiceTest {
    private val diagnoseService: LeaderResearchPoliticsSourceDiagnoseService = mock()
    private val activitySourceImportService: LeaderResearchActivitySourceImportService = mock()
    private val activityScoringService: LeaderResearchActivityScoringService = mock()
    private val paperPromotionService: LeaderResearchPaperPromotionService = mock()
    private val paperTradingService: LeaderPaperTradingService = mock()
    private val researchService: LeaderResearchService = mock()
    private val scoringService: LeaderResearchScoringService = mock()
    private val executionRepository: LeaderResearchRecommendationExecutionRepository = mock()
    private val objectMapper = jacksonObjectMapper()
    private val service = LeaderResearchPoliticsRecommendationExecutionService(
        diagnoseService = diagnoseService,
        activitySourceImportService = activitySourceImportService,
        activityScoringService = activityScoringService,
        paperPromotionService = paperPromotionService,
        paperTradingService = paperTradingService,
        researchService = researchService,
        scoringService = scoringService,
        executionRepository = executionRepository,
        objectMapper = objectMapper
    )

    @Test
    fun `dry run previews import and does not mutate score or paper process`() {
        val request = LeaderResearchPoliticsRecommendationExecuteRequest(dryRun = true, maxImport = 1)
        Mockito.`when`(diagnoseService.diagnose(request.diagnose)).thenReturn(diagnose())
        Mockito.`when`(activitySourceImportService.importFromActivitySource(anyActivitySourceImportRequest()))
            .thenReturn(activitySourceImport(dryRun = true))
        Mockito.`when`(paperPromotionService.promote(anyPaperPromotionRequest()))
            .thenReturn(promotion(dryRun = true))

        val response = service.execute(request)

        assertEquals(true, response.dryRun)
        assertEquals(mapOf("FAST_WATCH_REVIEW" to 1, "IMPORT_NOW" to 1, "PAPER_PROCESS" to 1, "SCORE_REFRESH" to 1), response.recommendationCounts)
        assertEquals(listOf("0x1111111111111111111111111111111111111111"), response.plannedActions.first { it.action == "IMPORT_NOW" }.wallets)
        assertEquals("dry_run", response.plannedActions.first { it.action == "PAPER_PROCESS" }.skippedReason)
        assertEquals(true, response.importResult!!.dryRun)
        assertNull(response.activityScoreResult)
        assertNull(response.paperProcessResult)
        assertNull(response.paperScoreResult)
        Mockito.verifyNoInteractions(activityScoringService, paperTradingService, researchService, scoringService)
        val saved = captureSavedExecution()
        assertEquals("SUCCESS", saved.status)
        assertEquals(true, saved.dryRun)
        assertEquals("politics", saved.category)
        assertEquals(true, saved.plannedActionsJson!!.contains("PAPER_PROCESS"))
    }

    @Test
    fun `live execution runs score promotion and paper process for selected recommendations`() {
        val request = LeaderResearchPoliticsRecommendationExecuteRequest(dryRun = false, paperProcessBatchSize = 5)
        Mockito.`when`(diagnoseService.diagnose(request.diagnose)).thenReturn(diagnose())
        Mockito.`when`(activitySourceImportService.importFromActivitySource(anyActivitySourceImportRequest()))
            .thenReturn(activitySourceImport(dryRun = false))
        Mockito.`when`(activityScoringService.scoreActivityPrescreen(anyActivityScoreRequest()))
            .thenReturn(activityScore())
        Mockito.`when`(paperPromotionService.promote(anyPaperPromotionRequest()))
            .thenReturn(promotion(dryRun = false))
        Mockito.`when`(paperTradingService.processPaperCandidates(runId = null, batchSize = 5, candidateIds = listOf(33L)))
            .thenReturn(LeaderPaperProcessingResult(processed = 2, filtered = 1, failed = 0))
        Mockito.`when`(researchService.findCandidatesByIds(listOf(33L))).thenReturn(emptyList())

        val response = service.execute(request)

        assertEquals(false, response.dryRun)
        assertEquals(1, response.importResult!!.createdTotal)
        assertEquals(1, response.activityScoreResult!!.scoredCount)
        assertEquals(1, response.promotionResult!!.selectedTotal)
        assertEquals(2, response.paperProcessResult!!.processed)
        assertEquals(listOf(44L), response.fastWatchReviewCandidateIds)
        assertEquals(listOf(44L), response.trialReadyCandidateIds)
        assertEquals(true, response.plannedActions.first { it.action == "PAPER_PROCESS" }.executed)
        Mockito.verify(activityScoringService).scoreActivityPrescreen(anyActivityScoreRequest())
        Mockito.verify(paperTradingService).processPaperCandidates(runId = null, batchSize = 5, candidateIds = listOf(33L))
        Mockito.verify(researchService).findCandidatesByIds(listOf(33L))
        val saved = captureSavedExecution()
        assertEquals("SUCCESS", saved.status)
        assertEquals(false, saved.dryRun)
        assertEquals(true, saved.resultSummaryJson!!.contains("paperProcessed"))
    }

    @Test
    fun `finance execution is forced to safe dry run and saved under finance category`() {
        val request = LeaderResearchPoliticsRecommendationExecuteRequest(
            dryRun = false,
            diagnose = LeaderResearchPoliticsSourceDiagnoseRequest(category = "finance")
        )
        Mockito.`when`(diagnoseService.diagnose(request.diagnose)).thenReturn(diagnose(category = "finance"))
        Mockito.`when`(activitySourceImportService.importFromActivitySource(anyActivitySourceImportRequest()))
            .thenReturn(activitySourceImport(dryRun = true, category = "finance"))
        Mockito.`when`(paperPromotionService.promote(anyPaperPromotionRequest()))
            .thenReturn(promotion(dryRun = true))

        val response = service.execute(request)

        assertEquals(true, response.dryRun)
        assertEquals(true, response.importResult!!.dryRun)
        assertNull(response.activityScoreResult)
        assertNull(response.paperProcessResult)
        Mockito.verifyNoInteractions(activityScoringService, paperTradingService, researchService, scoringService)
        val saved = captureSavedExecution()
        assertEquals("SUCCESS", saved.status)
        assertEquals("finance", saved.category)
        assertEquals(true, saved.dryRun)
    }

    @Test
    fun `latest returns saved execution snapshot`() {
        val execution = LeaderResearchRecommendationExecution(
            id = 7L,
            category = "politics",
            status = "SUCCESS",
            dryRun = true,
            actionsJson = objectMapper.writeValueAsString(listOf("IMPORT_NOW")),
            recommendationCountsJson = objectMapper.writeValueAsString(mapOf("IMPORT_NOW" to 2)),
            plannedActionsJson = objectMapper.writeValueAsString(
                listOf(
                    com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationActionPlanDto(
                        action = "IMPORT_NOW",
                        selectedCount = 2,
                        wallets = listOf("0x1111111111111111111111111111111111111111")
                    )
                )
            ),
            resultSummaryJson = objectMapper.writeValueAsString(mapOf("importSelected" to 2)),
            startedAt = 100L,
            finishedAt = 140L,
            durationMs = 40L
        )
        Mockito.`when`(executionRepository.findTopByCategoryOrderByStartedAtDesc("politics")).thenReturn(execution)

        val latest = service.latestPoliticsExecution()!!

        assertEquals(7L, latest.id)
        assertEquals("SUCCESS", latest.status)
        assertEquals(listOf("IMPORT_NOW"), latest.actions)
        assertEquals(2, latest.recommendationCounts["IMPORT_NOW"])
        assertEquals(1, latest.plannedActions.size)
        assertEquals(40L, latest.durationMs)
    }

    @Test
    fun `recent returns latest execution snapshots`() {
        val first = LeaderResearchRecommendationExecution(
            id = 8L,
            category = "politics",
            status = "SUCCESS",
            dryRun = true,
            recommendationCountsJson = objectMapper.writeValueAsString(mapOf("PAPER_PROCESS" to 0, "FAST_WATCH_REVIEW" to 0)),
            plannedActionsJson = objectMapper.writeValueAsString(emptyList<com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationActionPlanDto>()),
            startedAt = 200L
        )
        val second = LeaderResearchRecommendationExecution(
            id = 7L,
            category = "politics",
            status = "SUCCESS",
            dryRun = true,
            recommendationCountsJson = objectMapper.writeValueAsString(mapOf("PAPER_PROCESS" to 2)),
            plannedActionsJson = objectMapper.writeValueAsString(emptyList<com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationActionPlanDto>()),
            startedAt = 100L
        )
        Mockito.`when`(executionRepository.findByCategoryOrderByStartedAtDesc("politics", PageRequest.of(0, 5)))
            .thenReturn(PageImpl(listOf(first, second)))

        val recent = service.recentPoliticsExecutions()

        assertEquals(listOf(8L, 7L), recent.map { it.id })
        assertEquals(0, recent.first().recommendationCounts["PAPER_PROCESS"])
        assertEquals(2, recent[1].recommendationCounts["PAPER_PROCESS"])
    }

    @Test
    fun `latest primary category executions returns politics and finance snapshots`() {
        val politics = LeaderResearchRecommendationExecution(
            id = 10L,
            category = "politics",
            status = "SUCCESS",
            dryRun = true,
            recommendationCountsJson = objectMapper.writeValueAsString(mapOf("FAST_WATCH_REVIEW" to 1)),
            plannedActionsJson = objectMapper.writeValueAsString(emptyList<com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationActionPlanDto>()),
            startedAt = 200L
        )
        val finance = LeaderResearchRecommendationExecution(
            id = 11L,
            category = "finance",
            status = "SUCCESS",
            dryRun = true,
            recommendationCountsJson = objectMapper.writeValueAsString(mapOf("PAPER_PROCESS" to 2)),
            plannedActionsJson = objectMapper.writeValueAsString(emptyList<com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationActionPlanDto>()),
            startedAt = 300L
        )
        Mockito.`when`(executionRepository.findTopByCategoryOrderByStartedAtDesc("politics")).thenReturn(politics)
        Mockito.`when`(executionRepository.findTopByCategoryOrderByStartedAtDesc("finance")).thenReturn(finance)

        val latest = service.latestPrimaryCategoryExecutions()

        assertEquals(listOf("finance", "politics"), latest.map { it.category })
        assertEquals(listOf(11L, 10L), latest.map { it.id })
    }

    @Test
    fun `snapshot includes fast watch review candidate details`() {
        val execution = LeaderResearchRecommendationExecution(
            id = 9L,
            category = "politics",
            status = "SUCCESS",
            dryRun = true,
            recommendationCountsJson = objectMapper.writeValueAsString(mapOf("FAST_WATCH_REVIEW" to 1)),
            plannedActionsJson = objectMapper.writeValueAsString(
                listOf(
                    com.wrbug.polymarketbot.dto.LeaderResearchPoliticsRecommendationActionPlanDto(
                        action = "FAST_WATCH_REVIEW",
                        selectedCount = 1,
                        candidateIds = listOf(44L)
                    )
                )
            ),
            startedAt = 300L
        )
        Mockito.`when`(executionRepository.findTopByCategoryOrderByStartedAtDesc("politics")).thenReturn(execution)
        Mockito.`when`(researchService.funnelCandidatesByIds(listOf(44L))).thenReturn(
            listOf(
                LeaderResearchFunnelCandidateDto(
                    candidateId = 44L,
                    wallet = "0x4444444444444444444444444444444444444444",
                    category = "politics",
                    score = "88.5000",
                    tradeCount = 21,
                    filteredRatio = "0.1000",
                    copyablePnl = "2.5000",
                    maxDrawdown = "-1.0000",
                    researchState = LeaderResearchState.PAPER.name,
                    trialReadiness = LeaderResearchTrialReadinessDto(
                        eligible = false,
                        level = "FAST_WATCH",
                        label = "快速观察",
                        blockers = listOf("PAPER 观察不足 7 天：当前 74 小时"),
                        fastWatchBlockers = emptyList(),
                        ageHours = 74,
                        stableHighScoreCount = 3,
                        requiredStableHighScoreCount = 3
                    )
                )
            )
        )

        val latest = service.latestPoliticsExecution()!!

        assertEquals(listOf(44L), latest.plannedActions.single().candidateIds)
        assertEquals(44L, latest.reviewCandidates.single().candidateId)
        assertEquals("FAST_WATCH", latest.reviewCandidates.single().trialReadiness.level)
    }

    private fun diagnose(category: String = "politics"): LeaderResearchPoliticsSourceDiagnoseResponse {
        return LeaderResearchPoliticsSourceDiagnoseResponse(
            category = category,
            lookbackDays = 60,
            scannedWallets = 4,
            passImportCriteria = 1,
            unknownWallets = 1,
            existingWallets = 3,
            paperWallets = 1,
            cleanHighWallets = 1,
            eligibleForPaperNow = 1,
            buckets = emptyList(),
            samples = emptyList(),
            recommendations = listOf(
                recommendation("0x1111111111111111111111111111111111111111", null, "IMPORT_NOW", null),
                recommendation("0x2222222222222222222222222222222222222222", 22L, "SCORE_REFRESH", LeaderResearchState.DISCOVERED.name),
                recommendation("0x3333333333333333333333333333333333333333", 33L, "PAPER_PROCESS", LeaderResearchState.PAPER.name),
                recommendation("0x4444444444444444444444444444444444444444", 44L, "FAST_WATCH_REVIEW", LeaderResearchState.TRIAL_READY.name)
            ),
            generatedAt = 123L
        )
    }

    private fun recommendation(
        wallet: String,
        candidateId: Long?,
        recommendation: String,
        state: String?
    ): LeaderResearchPoliticsSourceRecommendationDto {
        return LeaderResearchPoliticsSourceRecommendationDto(
            wallet = wallet,
            candidateId = candidateId,
            recommendation = recommendation,
            priority = 100,
            reason = "reason",
            action = "action",
            currentState = state,
            currentScore = "88",
            totalEvents = 24,
            distinctMarkets = 5,
            buyEvents = 16,
            sellEvents = 4,
            safePriceRatio = "0.7500",
            tailPriceRatio = "0.0500",
            paperTradeCount = 12,
            copyablePnl = "3.5",
            blockers = emptyList()
        )
    }

    private fun activitySourceImport(dryRun: Boolean, category: String = "politics"): LeaderResearchActivitySourceImportResponse {
        return LeaderResearchActivitySourceImportResponse(
            dryRun = dryRun,
            requestedCategories = listOf(category),
            selectedTotal = 1,
            createdTotal = if (dryRun) 0 else 1,
            updatedTotal = 0,
            skippedExistingTotal = 0,
            skippedLockedTotal = 0,
            categories = emptyList(),
            previewItems = emptyList()
        )
    }

    private fun activityScore(): LeaderResearchActivityScoreResponse {
        return LeaderResearchActivityScoreResponse(
            scoreVersion = LeaderResearchActivityScoringService.SCORE_VERSION,
            scannedCount = 1,
            scoredCount = 1,
            skippedCount = 0,
            riskFlagCounts = emptyMap(),
            categoryCounts = mapOf("politics" to 1)
        )
    }

    private fun promotion(dryRun: Boolean): LeaderResearchPaperPromotionResponse {
        return LeaderResearchPaperPromotionResponse(
            dryRun = dryRun,
            minScore = "70",
            selectedTotal = 1,
            promotedTotal = if (dryRun) 0 else 1,
            skippedRiskTotal = 0,
            categories = emptyList(),
            items = emptyList()
        )
    }

    private fun anyActivitySourceImportRequest(): LeaderResearchActivitySourceImportRequest {
        Mockito.any(LeaderResearchActivitySourceImportRequest::class.java)
        return LeaderResearchActivitySourceImportRequest()
    }

    private fun anyActivityScoreRequest(): com.wrbug.polymarketbot.dto.LeaderResearchActivityScoreRequest {
        Mockito.any(com.wrbug.polymarketbot.dto.LeaderResearchActivityScoreRequest::class.java)
        return com.wrbug.polymarketbot.dto.LeaderResearchActivityScoreRequest()
    }

    private fun anyPaperPromotionRequest(): com.wrbug.polymarketbot.dto.LeaderResearchPaperPromotionRequest {
        Mockito.any(com.wrbug.polymarketbot.dto.LeaderResearchPaperPromotionRequest::class.java)
        return com.wrbug.polymarketbot.dto.LeaderResearchPaperPromotionRequest()
    }

    private fun captureSavedExecution(): LeaderResearchRecommendationExecution {
        val captor = ArgumentCaptor.forClass(LeaderResearchRecommendationExecution::class.java)
        Mockito.verify(executionRepository).save(captor.capture())
        return captor.value
    }

    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
