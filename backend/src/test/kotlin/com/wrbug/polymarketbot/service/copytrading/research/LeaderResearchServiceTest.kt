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
            sourceEvidence = "external_analytics:polymarket_official_leaderboard | category:politics | " +
                "profit_window:30d:12 profit_window:180d:40 activity_window:7d_trades:8",
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

    @Test
    fun `fast watch excludes non copyable strategy even when risk flags are missing`() {
        val candidate = LeaderResearchCandidate(
            id = 43,
            normalizedWallet = "0x2222222222222222222222222222222222222222",
            researchState = LeaderResearchState.PAPER,
            sourceEvidence = "category:finance",
            score = BigDecimal("92"),
            strategyType = LeaderResearchStrategyTypeClassifier.MARKET_MAKER_LP,
            riskFlags = null
        )
        val session = LeaderPaperSession(
            id = 101,
            candidateId = 43,
            startedAt = System.currentTimeMillis() - 8L * 24 * 60 * 60 * 1000,
            tradeCount = 25,
            filteredCount = 0,
            copyablePnl = BigDecimal("9.50"),
            maxDrawdown = BigDecimal.ZERO,
            filteredRatio = BigDecimal.ZERO
        )
        val stableScores = (1..3).map {
            LeaderResearchScore(
                candidateId = 43,
                scoreVersion = LeaderResearchScoringService.SCORE_VERSION,
                totalScore = BigDecimal("92"),
                createdAt = System.currentTimeMillis() - it
            )
        }

        Mockito.`when`(candidateRepository.findByResearchStateIn(anyStates()))
            .thenReturn(listOf(candidate))
        Mockito.`when`(paperSessionRepository.findLatestByCandidateIds(listOf(43)))
            .thenReturn(listOf(session))
        Mockito.`when`(scoreRepository.findByCandidateIdOrderByCreatedAtDesc(43))
            .thenReturn(stableScores)

        val response = service.fastWatch(
            LeaderResearchFastWatchRequest(categories = listOf("finance"), limit = 10, includeTrialReady = true)
        )

        assertEquals(0, response.total)
        assertTrue(response.items.isEmpty())
    }

    @Test
    fun `fast watch excludes candidate without long term profit evidence`() {
        val candidate = LeaderResearchCandidate(
            id = 44,
            normalizedWallet = "0x3333333333333333333333333333333333333333",
            researchState = LeaderResearchState.PAPER,
            sourceEvidence = "activity_source:finance | category:finance | activity_window:14d_trades:20",
            score = BigDecimal("92"),
            strategyType = LeaderResearchStrategyTypeClassifier.HUMAN_DIRECTIONAL,
            riskFlags = null
        )
        val session = LeaderPaperSession(
            id = 102,
            candidateId = 44,
            startedAt = System.currentTimeMillis() - 8L * 24 * 60 * 60 * 1000,
            tradeCount = 25,
            filteredCount = 0,
            copyablePnl = BigDecimal("9.50"),
            maxDrawdown = BigDecimal.ZERO,
            filteredRatio = BigDecimal.ZERO
        )
        val stableScores = (1..3).map {
            LeaderResearchScore(
                candidateId = 44,
                scoreVersion = LeaderResearchScoringService.SCORE_VERSION,
                totalScore = BigDecimal("92"),
                createdAt = System.currentTimeMillis() - it
            )
        }

        Mockito.`when`(candidateRepository.findByResearchStateIn(anyStates()))
            .thenReturn(listOf(candidate))
        Mockito.`when`(paperSessionRepository.findLatestByCandidateIds(listOf(44)))
            .thenReturn(listOf(session))
        Mockito.`when`(scoreRepository.findByCandidateIdOrderByCreatedAtDesc(44))
            .thenReturn(stableScores)

        val response = service.fastWatch(
            LeaderResearchFastWatchRequest(categories = listOf("finance"), limit = 10, includeTrialReady = true)
        )

        assertEquals(0, response.total)
        assertTrue(response.items.isEmpty())
    }

    @Test
    fun `summary includes active strategy type distribution and non copyable blockers`() {
        val activeCandidates = listOf(
            LeaderResearchCandidate(
                id = 1,
                normalizedWallet = "0x1111111111111111111111111111111111111111",
                researchState = LeaderResearchState.PAPER,
                strategyType = LeaderResearchStrategyTypeClassifier.HUMAN_DIRECTIONAL
            ),
            LeaderResearchCandidate(
                id = 2,
                normalizedWallet = "0x2222222222222222222222222222222222222222",
                researchState = LeaderResearchState.PAPER,
                strategyType = LeaderResearchStrategyTypeClassifier.LOW_PRICE_TAIL_RISK
            ),
            LeaderResearchCandidate(
                id = 3,
                normalizedWallet = "0x3333333333333333333333333333333333333333",
                researchState = LeaderResearchState.TRIAL_READY,
                strategyType = null
            )
        )
        Mockito.`when`(candidateRepository.findByResearchStateIn(listOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY)))
            .thenReturn(activeCandidates)
        Mockito.`when`(candidateRepository.findByResearchStateIn(listOf(LeaderResearchState.COOLDOWN)))
            .thenReturn(emptyList())
        Mockito.`when`(mapper.sourceLimitations()).thenReturn(emptyList())

        val summary = service.summary()

        assertEquals(3, summary.activePaperSessions)
        assertEquals(
            mapOf(
                LeaderResearchStrategyTypeClassifier.HUMAN_DIRECTIONAL to 1L,
                LeaderResearchStrategyTypeClassifier.LOW_PRICE_TAIL_RISK to 1L,
                LeaderResearchStrategyTypeClassifier.UNKNOWN to 1L
            ),
            summary.strategyTypeCounts.associate { it.key to it.count }
        )
        assertEquals(
            mapOf("strategy_not_copyable_low_price_tail_risk" to 1L),
            summary.nonCopyableStrategyBlockers.associate { it.key to it.count }
        )
    }

    private fun anyStates(): Collection<LeaderResearchState> {
        Mockito.anyCollection<LeaderResearchState>()
        return emptyList()
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
