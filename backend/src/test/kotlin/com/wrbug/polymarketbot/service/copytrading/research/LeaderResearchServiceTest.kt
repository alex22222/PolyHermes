package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchFastWatchRequest
import com.wrbug.polymarketbot.entity.Leader
import com.wrbug.polymarketbot.entity.LeaderPaperSession
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
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
import com.wrbug.polymarketbot.repository.LeaderResearchStableScoreProjection
import com.wrbug.polymarketbot.repository.LeaderResearchStrategyCountProjection
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
    private val loopDiagnosticsService: LeaderResearchLoopDiagnosticsService = mock()
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
        loopDiagnosticsService = loopDiagnosticsService,
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
        Mockito.`when`(scoreRepository.countRecentHighScores(listOf(42), LeaderResearchScoringService.SCORE_VERSION, BigDecimal("80"), 3))
            .thenReturn(listOf(stableScoreProjection(42, 3)))

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
        Mockito.`when`(candidateRepository.findByResearchStateIn(anyStates()))
            .thenReturn(listOf(candidate))
        Mockito.`when`(paperSessionRepository.findLatestByCandidateIds(listOf(43)))
            .thenReturn(listOf(session))
        Mockito.`when`(scoreRepository.countRecentHighScores(listOf(43), LeaderResearchScoringService.SCORE_VERSION, BigDecimal("80"), 3))
            .thenReturn(listOf(stableScoreProjection(43, 3)))

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
        Mockito.`when`(candidateRepository.findByResearchStateIn(anyStates()))
            .thenReturn(listOf(candidate))
        Mockito.`when`(paperSessionRepository.findLatestByCandidateIds(listOf(44)))
            .thenReturn(listOf(session))
        Mockito.`when`(scoreRepository.countRecentHighScores(listOf(44), LeaderResearchScoringService.SCORE_VERSION, BigDecimal("80"), 3))
            .thenReturn(listOf(stableScoreProjection(44, 3)))

        val response = service.fastWatch(
            LeaderResearchFastWatchRequest(categories = listOf("finance"), limit = 10, includeTrialReady = true)
        )

        assertEquals(0, response.total)
        assertTrue(response.items.isEmpty())
    }

    @Test
    fun `summary includes active strategy type distribution and non copyable blockers`() {
        val activeStrategyCounts = listOf(
            strategyCountProjection(LeaderResearchStrategyTypeClassifier.HUMAN_DIRECTIONAL, 1),
            strategyCountProjection(LeaderResearchStrategyTypeClassifier.LOW_PRICE_TAIL_RISK, 1),
            strategyCountProjection(null, 1)
        )
        Mockito.`when`(candidateRepository.countStrategyTypesByResearchStateIn(listOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY)))
            .thenReturn(activeStrategyCounts)
        Mockito.`when`(candidateRepository.countByResearchState(LeaderResearchState.COOLDOWN))
            .thenReturn(7)
        Mockito.`when`(loopDiagnosticsService.strictReadyCount()).thenReturn(2)
        Mockito.`when`(mapper.sourceLimitations()).thenReturn(emptyList())

        val summary = service.summary()

        assertEquals(3, summary.activePaperSessions)
        assertEquals(2, summary.strictReadyCount)
        assertEquals(7, summary.pendingRiskCount)
        Mockito.verify(loopDiagnosticsService).strictReadyCount()
        Mockito.verifyNoMoreInteractions(loopDiagnosticsService)
        Mockito.verify(candidateRepository).countByResearchState(LeaderResearchState.COOLDOWN)
        Mockito.verify(candidateRepository, Mockito.never())
            .findByResearchStateIn(listOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY))
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

    private fun stableScoreProjection(candidateId: Long, count: Long): LeaderResearchStableScoreProjection {
        return object : LeaderResearchStableScoreProjection {
            override fun getCandidateId() = candidateId
            override fun getStableHighScoreCount() = count
        }
    }

    private fun strategyCountProjection(strategyType: String?, count: Long): LeaderResearchStrategyCountProjection {
        return object : LeaderResearchStrategyCountProjection {
            override fun getStrategyType() = strategyType
            override fun getTotal() = count
        }
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
