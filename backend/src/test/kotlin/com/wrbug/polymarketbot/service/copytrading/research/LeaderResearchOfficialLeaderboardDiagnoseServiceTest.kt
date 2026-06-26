package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardDiagnoseRequest
import com.wrbug.polymarketbot.entity.LeaderPaperSession
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderPaperSessionRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class LeaderResearchOfficialLeaderboardDiagnoseServiceTest {
    private val candidateRepository: LeaderResearchCandidateRepository = mock()
    private val paperSessionRepository: LeaderPaperSessionRepository = mock()
    private val service = LeaderResearchOfficialLeaderboardDiagnoseService(candidateRepository, paperSessionRepository)

    @Test
    fun `diagnoses official leaderboard candidates into actionable buckets`() {
        val now = System.currentTimeMillis()
        val ready = candidate(1, "finance", LeaderResearchState.DISCOVERED, "90", null, now)
        val noActivity = candidate(2, "politics", LeaderResearchState.DISCOVERED, "40", "no_activity_sample", now)
        val stale = candidate(3, "finance", LeaderResearchState.DISCOVERED, "100", null, now - 72L * 60 * 60 * 1000)
        val clean = candidate(4, "politics", LeaderResearchState.PAPER, "85", null, now)
        val cleanSession = LeaderPaperSession(
            id = 40L,
            candidateId = 4L,
            tradeCount = 12,
            filteredCount = 1,
            copyablePnl = BigDecimal("6.5"),
            filteredRatio = BigDecimal("0.07")
        )
        Mockito.`when`(candidateRepository.findOfficialLeaderboardCandidates()).thenReturn(listOf(ready, noActivity, stale, clean))
        Mockito.`when`(paperSessionRepository.findLatestByCandidateIds(Mockito.anyCollection())).thenReturn(listOf(cleanSession))

        val response = service.diagnose(LeaderResearchOfficialLeaderboardDiagnoseRequest(sampleLimit = 10, staleHours = 48))

        assertEquals(4, response.total)
        assertEquals(1, response.paperTotal)
        assertEquals(1, response.cleanHighTotal)
        assertEquals(1, response.readyForPaperTotal)
        assertTrue(response.buckets.any { it.bucket == "READY_FOR_PAPER" && it.count == 1 })
        assertTrue(response.buckets.any { it.bucket == "NO_ACTIVITY_SAMPLE" && it.count == 1 })
        assertTrue(response.buckets.any { it.bucket == "STALE_ACTIVITY" && it.count == 1 })
        assertTrue(response.buckets.any { it.bucket == "CLEAN_HIGH" && it.count == 1 })
        assertEquals(2, response.categories.first { it.category == "finance" }.total)
        assertEquals(2, response.categories.first { it.category == "politics" }.total)
        assertTrue(response.riskFlagCounts["no_activity_sample"] == 1)
        assertEquals(4, response.samples.size)
    }

    private fun candidate(
        id: Long,
        category: String,
        state: LeaderResearchState,
        score: String,
        riskFlags: String?,
        lastSourceSeenAt: Long
    ) = LeaderResearchCandidate(
        id = id,
        normalizedWallet = "0x${id.toString().padStart(40, '0')}",
        researchState = state,
        source = "EXTERNAL_ANALYTICS_SOURCE",
        sourceEvidence = "external_analytics:polymarket_official_leaderboard | category:$category | rank:$id",
        score = BigDecimal(score),
        scoreVersion = LeaderResearchActivityScoringService.SCORE_VERSION,
        riskFlags = riskFlags,
        lastSourceSeenAt = lastSourceSeenAt
    )

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
