package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.entity.LeaderPaperSession
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderPaperFilterResult
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class LeaderResearchScoringServiceTest {
    private val service = LeaderResearchScoringService(
        candidateRepository = mock(),
        paperSessionRepository = mock(),
        paperTradeRepository = mock(),
        scoreRepository = mock()
    )

    @Test
    fun `compute rewards profitable repeatable fresh paper session`() {
        val now = System.currentTimeMillis()
        val candidate = LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            lastSourceSeenAt = now
        )
        val session = LeaderPaperSession(
            id = 10L,
            candidateId = 1L,
            startedAt = now - 8L * 24 * 60 * 60 * 1000,
            tradeCount = 12,
            filteredCount = 1,
            openExposure = BigDecimal("10"),
            copyablePnl = BigDecimal("4"),
            maxDrawdown = BigDecimal("-3"),
            unknownValuationExposure = BigDecimal("1"),
            filteredRatio = BigDecimal("0.08")
        )

        val score = service.compute(candidate, session, runId = 99L)

        assertTrue(score.totalScore >= BigDecimal("60"))
        assertEquals("research-copyability-v1", score.scoreVersion)
        assertEquals(12, score.sampleTradeCount)
        assertTrue(score.reason!!.contains("source_fresh=true"))
    }

    @Test
    fun `compute penalizes stale source and unknown quotes`() {
        val candidate = LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            lastSourceSeenAt = System.currentTimeMillis() - 7L * 24 * 60 * 60 * 1000
        )
        val session = LeaderPaperSession(
            id = 10L,
            candidateId = 1L,
            tradeCount = 2,
            openExposure = BigDecimal("10"),
            unknownValuationExposure = BigDecimal("8"),
            filteredRatio = BigDecimal("0.50")
        )

        val score = service.compute(candidate, session, runId = null)

        assertTrue(score.totalScore < BigDecimal("60"))
        assertTrue(score.reason!!.contains("source_fresh=false"))
    }

    @Test
    fun `compute caps small samples below promotion threshold`() {
        val now = System.currentTimeMillis()
        val candidate = LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            lastSourceSeenAt = now
        )
        val session = LeaderPaperSession(
            id = 10L,
            candidateId = 1L,
            startedAt = now - 8L * 24 * 60 * 60 * 1000,
            tradeCount = 1,
            openExposure = BigDecimal("1"),
            copyablePnl = BigDecimal("100"),
            maxDrawdown = BigDecimal.ZERO,
            filteredRatio = BigDecimal.ZERO
        )

        val score = service.compute(candidate, session, runId = null)

        assertTrue(score.totalScore <= BigDecimal("59"))
        assertTrue(score.reason!!.contains("sample_cap_applied=true"))
    }

    @Test
    fun `score candidate flags low price tail spray paper sessions`() {
        val candidateRepository = mock<com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository>()
        val paperSessionRepository = mock<com.wrbug.polymarketbot.repository.LeaderPaperSessionRepository>()
        val paperTradeRepository = mock<com.wrbug.polymarketbot.repository.LeaderPaperTradeRepository>()
        val scoreRepository = mock<com.wrbug.polymarketbot.repository.LeaderResearchScoreRepository>()
        val localService = LeaderResearchScoringService(
            candidateRepository = candidateRepository,
            paperSessionRepository = paperSessionRepository,
            paperTradeRepository = paperTradeRepository,
            scoreRepository = scoreRepository
        )
        val now = System.currentTimeMillis()
        val candidate = LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            lastSourceSeenAt = now
        )
        val session = LeaderPaperSession(
            id = 10L,
            candidateId = 1L,
            startedAt = now - 8L * 24 * 60 * 60 * 1000,
            tradeCount = 1,
            filteredCount = 11,
            filteredRatio = BigDecimal("0.91666667")
        )

        Mockito.`when`(paperSessionRepository.findTopByCandidateIdOrderByStartedAtDesc(1L)).thenReturn(session)
        Mockito.`when`(
            paperTradeRepository.countBySessionIdAndFilterResultAndFilterReasonContaining(
                10L,
                LeaderPaperFilterResult.FILTERED,
                "price_outside_safe_band"
            )
        ).thenReturn(11)
        Mockito.`when`(scoreRepository.save(anyScore())).thenAnswer { it.arguments[0] }
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }

        localService.scoreCandidate(candidate, runId = null)

        val savedCandidate = Mockito.mockingDetails(candidateRepository).invocations
            .last { it.method.name == "save" }
            .arguments[0] as LeaderResearchCandidate
        assertTrue(savedCandidate.riskFlags!!.contains("tail_price_spray"))
        assertTrue(savedCandidate.riskFlags!!.contains("high_filtered_ratio"))
    }

    @Test
    fun `score candidate preserves mixed category evidence risk`() {
        val candidateRepository = mock<com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository>()
        val paperSessionRepository = mock<com.wrbug.polymarketbot.repository.LeaderPaperSessionRepository>()
        val paperTradeRepository = mock<com.wrbug.polymarketbot.repository.LeaderPaperTradeRepository>()
        val scoreRepository = mock<com.wrbug.polymarketbot.repository.LeaderResearchScoreRepository>()
        val localService = LeaderResearchScoringService(
            candidateRepository = candidateRepository,
            paperSessionRepository = paperSessionRepository,
            paperTradeRepository = paperTradeRepository,
            scoreRepository = scoreRepository
        )
        val now = System.currentTimeMillis()
        val candidate = LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            sourceEvidence = """
                scanner_pool:1 | category:finance | discovery_score:90
                scanner_pool:2 | category:sports | discovery_score:88
            """.trimIndent(),
            lastSourceSeenAt = now
        )
        val session = LeaderPaperSession(
            id = 10L,
            candidateId = 1L,
            startedAt = now - 8L * 24 * 60 * 60 * 1000,
            tradeCount = 12,
            filteredCount = 0,
            copyablePnl = BigDecimal("4"),
            maxDrawdown = BigDecimal.ZERO,
            filteredRatio = BigDecimal.ZERO
        )

        Mockito.`when`(paperSessionRepository.findTopByCandidateIdOrderByStartedAtDesc(1L)).thenReturn(session)
        Mockito.`when`(scoreRepository.save(anyScore())).thenAnswer { it.arguments[0] }
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }

        localService.scoreCandidate(candidate, runId = null)

        val savedCandidate = Mockito.mockingDetails(candidateRepository).invocations
            .last { it.method.name == "save" }
            .arguments[0] as LeaderResearchCandidate
        assertTrue(savedCandidate.riskFlags!!.contains("mixed_category_evidence"))
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = org.mockito.Mockito.mock(T::class.java)

    private fun anyScore(): com.wrbug.polymarketbot.entity.LeaderResearchScore {
        Mockito.any(com.wrbug.polymarketbot.entity.LeaderResearchScore::class.java)
        return com.wrbug.polymarketbot.entity.LeaderResearchScore(
            candidateId = 1L,
            scoreVersion = LeaderResearchScoringService.SCORE_VERSION
        )
    }

    private fun anyCandidate(): LeaderResearchCandidate {
        Mockito.any(LeaderResearchCandidate::class.java)
        return LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111"
        )
    }
}
