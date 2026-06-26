package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchPaperPromotionRequest
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class LeaderResearchPaperPromotionServiceTest {
    private val candidateRepository: LeaderResearchCandidateRepository = mock()
    private val stateMachine: LeaderResearchStateMachine = mock()
    private val service = LeaderResearchPaperPromotionService(candidateRepository, stateMachine)

    @Test
    fun `dry run previews all selected candidates without live throttle`() {
        Mockito.`when`(candidateRepository.findByResearchStateIn(anyStates()))
            .thenReturn(financeCandidates(17))

        val response = service.promote(
            LeaderResearchPaperPromotionRequest(
                minScore = "80",
                politicsLimit = 0,
                financeLimit = 20,
                sportsLimit = 0,
                cryptoLimit = 0,
                dryRun = true
            )
        )

        assertEquals(17, response.requestedSelectedTotal)
        assertEquals(17, response.selectedTotal)
        assertEquals(17, response.effectiveSelectedLimit)
        assertFalse(response.truncated)
        Mockito.verify(stateMachine, Mockito.never()).advance(anyCandidate(), Mockito.any())
    }

    @Test
    fun `live promotion is throttled to bounded batch size`() {
        val candidates = financeCandidates(17)
        Mockito.`when`(candidateRepository.findByResearchStateIn(anyStates()))
            .thenReturn(candidates)
        candidates.forEach { candidate ->
            Mockito.`when`(stateMachine.advance(candidate, null))
                .thenReturn(candidate.copy(researchState = LeaderResearchState.CANDIDATE))
            Mockito.`when`(stateMachine.advance(candidate.copy(researchState = LeaderResearchState.CANDIDATE), null))
                .thenReturn(candidate.copy(researchState = LeaderResearchState.PAPER))
        }

        val response = service.promote(
            LeaderResearchPaperPromotionRequest(
                minScore = "80",
                politicsLimit = 0,
                financeLimit = 20,
                sportsLimit = 0,
                cryptoLimit = 0,
                dryRun = false
            )
        )

        assertEquals(17, response.requestedSelectedTotal)
        assertEquals(8, response.selectedTotal)
        assertEquals(8, response.effectiveSelectedLimit)
        assertEquals(8, response.promotedTotal)
        assertTrue(response.truncated)
        Mockito.verify(stateMachine, Mockito.times(16)).advance(anyCandidate(), Mockito.any())
    }

    @Test
    fun `stale source candidate is not selected for paper promotion dry run`() {
        val fresh = financeCandidate(1, System.currentTimeMillis())
        val stale = financeCandidate(2, System.currentTimeMillis() - 50L * 60 * 60 * 1000)
        Mockito.`when`(candidateRepository.findByResearchStateIn(anyStates()))
            .thenReturn(listOf(fresh, stale))

        val response = service.promote(
            LeaderResearchPaperPromotionRequest(
                minScore = "80",
                politicsLimit = 0,
                financeLimit = 20,
                sportsLimit = 0,
                cryptoLimit = 0,
                dryRun = true
            )
        )

        assertEquals(1, response.selectedTotal)
        assertEquals(fresh.id, response.items.single().candidateId)
        assertEquals("PAPER", response.items.single().nextState)
    }

    private fun financeCandidates(count: Int): List<LeaderResearchCandidate> {
        return (1..count).map { index ->
            financeCandidate(index, System.currentTimeMillis())
        }
    }

    private fun financeCandidate(index: Int, lastSourceSeenAt: Long): LeaderResearchCandidate {
        return LeaderResearchCandidate(
            id = index.toLong(),
            normalizedWallet = "0x${index.toString().padStart(40, '0')}",
            researchState = LeaderResearchState.DISCOVERED,
            source = "ACTIVITY_SOURCE",
            sourceEvidence = "activity_source:finance | category:finance",
            score = BigDecimal("90"),
            scoreVersion = LeaderResearchActivityScoringService.SCORE_VERSION,
            lastSourceSeenAt = lastSourceSeenAt,
            agentOwned = true
        )
    }

    private fun anyStates(): Collection<LeaderResearchState> {
        Mockito.anyCollection<LeaderResearchState>()
        return emptyList()
    }

    private fun anyCandidate(): LeaderResearchCandidate {
        Mockito.any(LeaderResearchCandidate::class.java)
        return LeaderResearchCandidate(normalizedWallet = "0x1111111111111111111111111111111111111111")
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
