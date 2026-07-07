package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchFastWatchRequest
import com.wrbug.polymarketbot.entity.Leader
import com.wrbug.polymarketbot.entity.LeaderPaperSession
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.entity.LeaderResearchScore
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderPaperPositionRepository
import com.wrbug.polymarketbot.repository.LeaderPaperSessionRepository
import com.wrbug.polymarketbot.repository.LeaderPaperTradeRepository
import com.wrbug.polymarketbot.repository.LeaderPoolRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.repository.LeaderResearchEventRepository
import com.wrbug.polymarketbot.repository.LeaderResearchRunRepository
import com.wrbug.polymarketbot.repository.LeaderResearchScoreRepository
import com.wrbug.polymarketbot.repository.LeaderResearchSourceStateRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class LeaderResearchServiceTest {
    private val candidateRepository: LeaderResearchCandidateRepository = mock()
    private val runRepository: LeaderResearchRunRepository = mock()
    private val scoreRepository: LeaderResearchScoreRepository = mock()
    private val sourceStateRepository: LeaderResearchSourceStateRepository = mock()
    private val eventRepository: LeaderResearchEventRepository = mock()
    private val paperSessionRepository: LeaderPaperSessionRepository = mock()
    private val paperTradeRepository: LeaderPaperTradeRepository = mock()
    private val paperPositionRepository: LeaderPaperPositionRepository = mock()
    private val leaderRepository: LeaderRepository = mock()
    private val leaderPoolRepository: LeaderPoolRepository = mock()
    private val mapper: LeaderResearchMapper = mock()
    private val service = LeaderResearchService(
        candidateRepository = candidateRepository,
        runRepository = runRepository,
        scoreRepository = scoreRepository,
        sourceStateRepository = sourceStateRepository,
        eventRepository = eventRepository,
        paperSessionRepository = paperSessionRepository,
        paperTradeRepository = paperTradeRepository,
        paperPositionRepository = paperPositionRepository,
        leaderRepository = leaderRepository,
        leaderPoolRepository = leaderPoolRepository,
        mapper = mapper
    )

    @Test
    fun `fast watch uses bound leader category before source evidence category`() {
        val candidate = LeaderResearchCandidate(
            id = 42,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            leaderId = 7,
            researchState = LeaderResearchState.TRIAL_READY,
            source = "EXTERNAL_ANALYTICS_SOURCE,ACTIVITY_DERIVED",
            sourceEvidence = "external_analytics:polymarket_official_leaderboard | category:politics",
            score = BigDecimal("90"),
            riskFlags = null
        )
        val session = LeaderPaperSession(
            id = 100,
            candidateId = 42,
            startedAt = System.currentTimeMillis() - 8L * 24 * 60 * 60 * 1000,
            tradeCount = 20,
            filteredCount = 0,
            copyablePnl = BigDecimal("12.50"),
            maxDrawdown = BigDecimal.ZERO
        )
        val stableScores = (1..3).map {
            LeaderResearchScore(
                candidateId = 42,
                scoreVersion = LeaderResearchScoringService.SCORE_VERSION,
                totalScore = BigDecimal("90"),
                createdAt = System.currentTimeMillis() - it
            )
        }

        Mockito.`when`(candidateRepository.findByResearchStateIn(anyStates()))
            .thenReturn(listOf(candidate))
        Mockito.`when`(paperSessionRepository.findLatestByCandidateIds(listOf(42)))
            .thenReturn(listOf(session))
        Mockito.`when`(leaderRepository.findByIdIn(listOf(7)))
            .thenReturn(
                listOf(
                    Leader(
                        id = 7,
                        leaderAddress = candidate.normalizedWallet,
                        leaderName = "Bound Category",
                        category = "crypto"
                    )
                )
            )
        Mockito.`when`(scoreRepository.findByCandidateIdOrderByCreatedAtDesc(42))
            .thenReturn(stableScores)

        val cryptoResponse = service.fastWatch(
            LeaderResearchFastWatchRequest(categories = listOf("crypto"), limit = 10, includeTrialReady = true)
        )
        val politicsResponse = service.fastWatch(
            LeaderResearchFastWatchRequest(categories = listOf("politics"), limit = 10, includeTrialReady = true)
        )

        assertEquals(1, cryptoResponse.total)
        assertEquals("crypto", cryptoResponse.items.single().category)
        assertEquals("TRIAL_READY", cryptoResponse.items.single().trialReadiness.level)
        assertEquals(0, politicsResponse.total)
        assertTrue(politicsResponse.items.isEmpty())
    }

    private fun anyStates(): Collection<LeaderResearchState> {
        Mockito.anyCollection<LeaderResearchState>()
        return emptyList()
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
