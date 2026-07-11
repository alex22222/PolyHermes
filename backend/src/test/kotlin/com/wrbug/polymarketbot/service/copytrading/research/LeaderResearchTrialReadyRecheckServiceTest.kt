package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchTrialReadyRecheckRequest
import com.wrbug.polymarketbot.entity.LeaderPaperSession
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.entity.LeaderResearchScore
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderPaperSessionRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.repository.LeaderResearchScoreRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class LeaderResearchTrialReadyRecheckServiceTest {
    private val candidateRepository: LeaderResearchCandidateRepository = mock()
    private val paperSessionRepository: LeaderPaperSessionRepository = mock()
    private val scoreRepository: LeaderResearchScoreRepository = mock()
    private val scoringService: LeaderResearchScoringService = mock()
    private val stateMachine: LeaderResearchStateMachine = mock()
    private val service = LeaderResearchTrialReadyRecheckService(
        candidateRepository,
        paperSessionRepository,
        scoreRepository,
        scoringService,
        stateMachine
    )

    @Test
    fun `dry run reports strategy blocker when strategy type is not copyable`() {
        val now = System.currentTimeMillis()
        val candidate = LeaderResearchCandidate(
            id = 44,
            normalizedWallet = "0x3333333333333333333333333333333333333333",
            researchState = LeaderResearchState.PAPER,
            lastSourceSeenAt = now,
            score = BigDecimal("91"),
            strategyType = LeaderResearchStrategyTypeClassifier.REBALANCE_CHURN,
            riskFlags = null,
            sourceEvidence = "profit_window:30d:12 profit_window:180d:40 activity_window:7d_trades:8"
        )
        val session = LeaderPaperSession(
            id = 102,
            candidateId = 44,
            startedAt = now - 8L * 24 * 60 * 60 * 1000,
            tradeCount = 24,
            filteredCount = 0,
            openExposure = BigDecimal("10"),
            copyablePnl = BigDecimal("6"),
            maxDrawdown = BigDecimal.ZERO,
            unknownValuationExposure = BigDecimal.ZERO,
            filteredRatio = BigDecimal.ZERO
        )
        Mockito.`when`(candidateRepository.findAllById(listOf(44L))).thenReturn(listOf(candidate))
        Mockito.`when`(paperSessionRepository.findLatestByCandidateIds(listOf(44L))).thenReturn(listOf(session))
        Mockito.`when`(scoreRepository.findByCandidateIdOrderByCreatedAtDesc(44L)).thenReturn(
            listOf(stableScore("91"), stableScore("90"), stableScore("92"))
        )

        val response = service.recheck(
            LeaderResearchTrialReadyRecheckRequest(dryRun = true, candidateIds = listOf(44L), maxCandidates = 1)
        )

        assertEquals(1, response.selectedCount)
        assertFalse(response.items.single().eligible)
        assertEquals("strategy_not_copyable_rebalance_churn", response.items.single().reason)
    }

    private fun stableScore(score: String): LeaderResearchScore {
        return LeaderResearchScore(
            candidateId = 44L,
            scoreVersion = LeaderResearchScoringService.SCORE_VERSION,
            totalScore = BigDecimal(score)
        )
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
