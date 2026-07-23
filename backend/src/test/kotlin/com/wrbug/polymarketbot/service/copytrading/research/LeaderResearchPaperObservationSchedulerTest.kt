package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchTrialReadyRecheckRequest
import com.wrbug.polymarketbot.dto.LeaderResearchTrialReadyRecheckResponse
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.service.loop.LoopGoalControlService
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.springframework.data.domain.PageImpl
import org.springframework.data.domain.PageRequest
import org.springframework.data.domain.Sort
import java.math.BigDecimal

class LeaderResearchPaperObservationSchedulerTest {
    private val candidateRepository: LeaderResearchCandidateRepository = mock()
    private val paperTradingService: LeaderPaperTradingService = mock()
    private val trialReadyRecheckService: LeaderResearchTrialReadyRecheckService = mock()
    private val loopGoalControlService: LoopGoalControlService = mock()

    @Test
    fun `scheduled run does nothing when disabled`() {
        scheduler(enabled = false).scheduledRun()

        Mockito.verifyNoInteractions(candidateRepository, paperTradingService, trialReadyRecheckService, loopGoalControlService)
    }

    @Test
    fun `observation processes only fresh official primary category candidates`() {
        val now = System.currentTimeMillis()
        val eligible = candidate(31, now, "politics")
        val crypto = candidate(32, now, "crypto")
        val stale = candidate(33, now - 73L * 60 * 60 * 1000, "finance")
        Mockito.`when`(
            candidateRepository.findByResearchStateIn(
                listOf(LeaderResearchState.PAPER),
                PageRequest.of(0, 25, Sort.by(Sort.Direction.DESC, "lastTransitionAt"))
            )
        )
            .thenReturn(PageImpl(listOf(eligible, crypto, stale)))
        Mockito.`when`(
            paperTradingService.processPaperCandidates(runId = null, batchSize = 20, candidateIds = listOf(31L))
        ).thenReturn(LeaderPaperProcessingResult(processed = 1, filtered = 0, failed = 0))
        Mockito.`when`(trialReadyRecheckService.recheck(anyRecheckRequest())).thenReturn(
            LeaderResearchTrialReadyRecheckResponse(
                dryRun = false,
                scannedCount = 1,
                selectedCount = 1,
                scoredCount = 1,
                advancedCount = 0,
                trialReadyCandidateIds = emptyList(),
                items = emptyList(),
                generatedAt = now
            )
        )

        val observed = scheduler().observeOnce()

        assertEquals(listOf(31L), observed)
        Mockito.verify(paperTradingService).processPaperCandidates(runId = null, batchSize = 20, candidateIds = listOf(31L))
        Mockito.verify(trialReadyRecheckService).recheck(anyRecheckRequest())
    }

    private fun scheduler(enabled: Boolean = true) = LeaderResearchPaperObservationScheduler(
        candidateRepository = candidateRepository,
        paperTradingService = paperTradingService,
        trialReadyRecheckService = trialReadyRecheckService,
        loopGoalControlService = loopGoalControlService,
        enabled = enabled,
        maxCandidates = 5,
        batchSize = 20,
        maxTransitionAgeHours = 336
    )

    private fun candidate(id: Long, sourceSeenAt: Long, category: String): LeaderResearchCandidate {
        val now = System.currentTimeMillis()
        return LeaderResearchCandidate(
            id = id,
            normalizedWallet = "0x${id.toString().padStart(40, '0')}",
            researchState = LeaderResearchState.PAPER,
            score = BigDecimal("90"),
            sourceEvidence = "polymarket_official_leaderboard category:$category",
            lastSourceSeenAt = sourceSeenAt,
            lastTransitionAt = now - 60_000
        )
    }

    private fun anyRecheckRequest(): LeaderResearchTrialReadyRecheckRequest {
        Mockito.any(LeaderResearchTrialReadyRecheckRequest::class.java)
        return LeaderResearchTrialReadyRecheckRequest()
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
