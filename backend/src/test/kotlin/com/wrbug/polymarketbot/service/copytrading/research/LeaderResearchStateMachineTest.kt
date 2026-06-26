package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.entity.LeaderPaperSession
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.entity.LeaderResearchScore
import com.wrbug.polymarketbot.enums.LeaderResearchState
import java.math.BigDecimal
import com.wrbug.polymarketbot.repository.LeaderPaperSessionRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.repository.LeaderResearchScoreRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito

class LeaderResearchStateMachineTest {
    private val candidateRepository: LeaderResearchCandidateRepository = mock()
    private val paperSessionRepository: LeaderPaperSessionRepository = mock()
    private val scoreRepository: LeaderResearchScoreRepository = mock()
    private val paperTradingService: LeaderPaperTradingService = mock()
    private val poolMappingService: LeaderResearchPoolMappingService = mock()
    private val eventService: LeaderResearchEventService = mock()
    private val stateMachine = LeaderResearchStateMachine(
        candidateRepository,
        paperSessionRepository,
        scoreRepository,
        paperTradingService,
        poolMappingService,
        eventService
    )

    @Test
    fun `fresh discovered agent candidate can bootstrap into candidate for paper observation`() {
        val candidate = LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            researchState = LeaderResearchState.DISCOVERED,
            lastSourceSeenAt = System.currentTimeMillis(),
            agentOwned = true
        )
        Mockito.`when`(paperSessionRepository.findTopByCandidateIdOrderByStartedAtDesc(1L)).thenReturn(null)
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }
        Mockito.`when`(poolMappingService.syncCandidate(anyCandidate())).thenAnswer { it.arguments[0] }

        val result = stateMachine.advance(candidate, runId = 99L)

        assertEquals(LeaderResearchState.CANDIDATE, result.researchState)
    }

    @Test
    fun `locked candidate is not automatically advanced`() {
        val candidate = LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            researchState = LeaderResearchState.DISCOVERED,
            lastSourceSeenAt = System.currentTimeMillis(),
            locked = true
        )
        val result = stateMachine.advance(candidate, runId = 99L)

        assertEquals(LeaderResearchState.DISCOVERED, result.researchState)
        Mockito.verify(candidateRepository, Mockito.never()).save(anyCandidate())
        Mockito.verify(poolMappingService, Mockito.never()).syncCandidate(anyCandidate())
    }

    @Test
    fun `unchanged discovered candidate does not sync into leader pool`() {
        val candidate = LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            researchState = LeaderResearchState.DISCOVERED,
            lastSourceSeenAt = System.currentTimeMillis() - 7L * 24 * 60 * 60 * 1000,
            agentOwned = false
        )
        Mockito.`when`(paperSessionRepository.findTopByCandidateIdOrderByStartedAtDesc(1L)).thenReturn(null)

        val result = stateMachine.advance(candidate, runId = 99L)

        assertEquals(LeaderResearchState.DISCOVERED, result.researchState)
        Mockito.verify(poolMappingService, Mockito.never()).syncCandidate(anyCandidate())
    }

    @Test
    fun `new paper candidate starts observation without creating leader pool row`() {
        val now = System.currentTimeMillis()
        val candidate = LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            researchState = LeaderResearchState.CANDIDATE,
            lastSourceSeenAt = now,
            score = BigDecimal("80")
        )
        val session = LeaderPaperSession(
            id = 10L,
            candidateId = 1L,
            startedAt = now
        )
        Mockito.`when`(paperSessionRepository.findTopByCandidateIdOrderByStartedAtDesc(1L)).thenReturn(null)
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }
        Mockito.`when`(paperTradingService.ensureSession(anyCandidate(), Mockito.eq(99L))).thenReturn(session)

        val result = stateMachine.advance(candidate, runId = 99L)

        assertEquals(LeaderResearchState.PAPER, result.researchState)
        assertEquals(10L, result.lastPaperSessionId)
        Mockito.verify(poolMappingService, Mockito.never()).syncCandidate(anyCandidate())
    }

    @Test
    fun `trial ready candidate syncs into leader pool`() {
        val now = System.currentTimeMillis()
        val candidate = LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            researchState = LeaderResearchState.PAPER,
            lastSourceSeenAt = now,
            score = BigDecimal("83")
        )
        val session = LeaderPaperSession(
            id = 10L,
            candidateId = 1L,
            startedAt = now - 8L * 24 * 60 * 60 * 1000,
            tradeCount = 12,
            filteredCount = 0,
            openExposure = BigDecimal("10"),
            copyablePnl = BigDecimal("5"),
            maxDrawdown = BigDecimal.ZERO,
            unknownValuationExposure = BigDecimal.ZERO,
            filteredRatio = BigDecimal.ZERO
        )
        Mockito.`when`(paperSessionRepository.findTopByCandidateIdOrderByStartedAtDesc(1L)).thenReturn(session)
        Mockito.`when`(paperTradingService.isEligibleForTrialReady(anySession(), Mockito.anyLong())).thenReturn(true)
        Mockito.`when`(scoreRepository.findByCandidateIdOrderByCreatedAtDesc(1L)).thenReturn(
            listOf(stableScore("83"), stableScore("84"), stableScore("82"))
        )
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }
        Mockito.`when`(poolMappingService.syncCandidate(anyCandidate())).thenAnswer { it.arguments[0] }

        val result = stateMachine.advance(candidate, runId = 99L)

        assertEquals(LeaderResearchState.TRIAL_READY, result.researchState)
        Mockito.verify(poolMappingService).syncCandidate(anyCandidate())
    }

    @Test
    fun `trial ready requires three stable clean high scores`() {
        val now = System.currentTimeMillis()
        val candidate = LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            researchState = LeaderResearchState.PAPER,
            lastSourceSeenAt = now,
            score = BigDecimal("85")
        )
        val session = LeaderPaperSession(
            id = 10L,
            candidateId = 1L,
            startedAt = now - 8L * 24 * 60 * 60 * 1000,
            tradeCount = 12,
            filteredCount = 0,
            openExposure = BigDecimal("10"),
            copyablePnl = BigDecimal("5"),
            maxDrawdown = BigDecimal.ZERO,
            unknownValuationExposure = BigDecimal.ZERO,
            filteredRatio = BigDecimal.ZERO
        )
        Mockito.`when`(paperSessionRepository.findTopByCandidateIdOrderByStartedAtDesc(1L)).thenReturn(session)
        Mockito.`when`(paperTradingService.isEligibleForTrialReady(anySession(), Mockito.anyLong())).thenReturn(true)
        Mockito.`when`(scoreRepository.findByCandidateIdOrderByCreatedAtDesc(1L)).thenReturn(
            listOf(stableScore("85"), stableScore("84"))
        )

        val result = stateMachine.advance(candidate, runId = 99L)

        assertEquals(LeaderResearchState.PAPER, result.researchState)
        Mockito.verify(poolMappingService, Mockito.never()).syncCandidate(anyCandidate())
    }

    @Test
    fun `trial ready requires all recent stable scores above threshold`() {
        val now = System.currentTimeMillis()
        val candidate = LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            researchState = LeaderResearchState.PAPER,
            lastSourceSeenAt = now,
            score = BigDecimal("85")
        )
        val session = LeaderPaperSession(
            id = 10L,
            candidateId = 1L,
            startedAt = now - 8L * 24 * 60 * 60 * 1000,
            tradeCount = 12,
            filteredCount = 0,
            openExposure = BigDecimal("10"),
            copyablePnl = BigDecimal("5"),
            maxDrawdown = BigDecimal.ZERO,
            unknownValuationExposure = BigDecimal.ZERO,
            filteredRatio = BigDecimal.ZERO
        )
        Mockito.`when`(paperSessionRepository.findTopByCandidateIdOrderByStartedAtDesc(1L)).thenReturn(session)
        Mockito.`when`(paperTradingService.isEligibleForTrialReady(anySession(), Mockito.anyLong())).thenReturn(true)
        Mockito.`when`(scoreRepository.findByCandidateIdOrderByCreatedAtDesc(1L)).thenReturn(
            listOf(stableScore("85"), stableScore("79"), stableScore("84"))
        )

        val result = stateMachine.advance(candidate, runId = 99L)

        assertEquals(LeaderResearchState.PAPER, result.researchState)
        Mockito.verify(poolMappingService, Mockito.never()).syncCandidate(anyCandidate())
    }

    @Test
    fun `mixed category evidence blocks trial ready transition`() {
        val now = System.currentTimeMillis()
        val candidate = LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            researchState = LeaderResearchState.PAPER,
            lastSourceSeenAt = now,
            riskFlags = "mixed_category_evidence"
        )
        val session = LeaderPaperSession(
            id = 10L,
            candidateId = 1L,
            startedAt = now - 8L * 24 * 60 * 60 * 1000,
            tradeCount = 12,
            filteredCount = 0,
            openExposure = BigDecimal("10"),
            copyablePnl = BigDecimal("5"),
            maxDrawdown = BigDecimal.ZERO,
            unknownValuationExposure = BigDecimal.ZERO,
            filteredRatio = BigDecimal.ZERO
        )
        Mockito.`when`(paperSessionRepository.findTopByCandidateIdOrderByStartedAtDesc(1L)).thenReturn(session)
        Mockito.`when`(poolMappingService.syncCandidate(anyCandidate())).thenAnswer { it.arguments[0] }

        val result = stateMachine.advance(candidate, runId = 99L)

        assertEquals(LeaderResearchState.PAPER, result.researchState)
        Mockito.verify(candidateRepository, Mockito.never()).save(anyCandidate())
    }

    private fun anyCandidate(): LeaderResearchCandidate {
        Mockito.any(LeaderResearchCandidate::class.java)
        return LeaderResearchCandidate(normalizedWallet = "0x1111111111111111111111111111111111111111")
    }

    private fun anySession(): LeaderPaperSession {
        Mockito.any(LeaderPaperSession::class.java)
        return LeaderPaperSession(candidateId = 1L)
    }

    private fun stableScore(score: String): LeaderResearchScore {
        return LeaderResearchScore(
            candidateId = 1L,
            scoreVersion = LeaderResearchScoringService.SCORE_VERSION,
            totalScore = BigDecimal(score)
        )
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
