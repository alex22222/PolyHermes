package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardDiagnoseRequest
import com.wrbug.polymarketbot.entity.LeaderPaperSession
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderPaperSessionRepository
import com.wrbug.polymarketbot.repository.LeaderResearchActivityMetricProjection
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
        Mockito.`when`(candidateRepository.aggregateActivityMetricsForCandidateIds(Mockito.anyCollection())).thenReturn(emptyList())

        val response = service.diagnose(LeaderResearchOfficialLeaderboardDiagnoseRequest(sampleLimit = 10, staleHours = 48))

        assertEquals(4, response.total)
        assertEquals(1, response.paperTotal)
        assertEquals(1, response.cleanHighTotal)
        assertEquals(1, response.readyForPaperTotal)
        assertEquals(0, response.disabledTrialCandidateTotal)
        assertTrue(response.buckets.any { it.bucket == "READY_FOR_PAPER" && it.count == 1 })
        assertTrue(response.buckets.any { it.bucket == "NO_ACTIVITY_SAMPLE" && it.count == 1 })
        assertTrue(response.buckets.any { it.bucket == "STALE_ACTIVITY" && it.count == 1 })
        assertTrue(response.buckets.any { it.bucket == "CLEAN_HIGH" && it.count == 1 })
        assertEquals(2, response.categories.first { it.category == "finance" }.total)
        assertEquals(2, response.categories.first { it.category == "politics" }.total)
        assertTrue(response.riskFlagCounts["no_activity_sample"] == 1)
        assertEquals(4, response.samples.size)
    }

    @Test
    fun `diagnose marks source category mismatch when real activity category differs`() {
        val now = System.currentTimeMillis()
        val fakeFinance = candidate(174, "finance", LeaderResearchState.PAPER, "100", null, now)
        val session = LeaderPaperSession(
            id = 1740L,
            candidateId = 174L,
            tradeCount = 12,
            filteredCount = 1,
            copyablePnl = BigDecimal("4.2"),
            filteredRatio = BigDecimal("0.07")
        )
        Mockito.`when`(candidateRepository.findOfficialLeaderboardCandidates()).thenReturn(listOf(fakeFinance))
        Mockito.`when`(paperSessionRepository.findLatestByCandidateIds(Mockito.anyCollection())).thenReturn(listOf(session))
        Mockito.`when`(candidateRepository.aggregateActivityMetricsForCandidateIds(Mockito.anyCollection())).thenReturn(
            listOf(activityMetric(candidateId = 174L, sportsEvents = 30L, financeEvents = 2L))
        )

        val response = service.diagnose(LeaderResearchOfficialLeaderboardDiagnoseRequest(sampleLimit = 10, staleHours = 48))

        assertEquals(0, response.cleanHighTotal)
        assertTrue(response.buckets.any { it.bucket == "CATEGORY_CONFLICT" && it.count == 1 })
        assertEquals(1, response.riskFlagCounts["activity_category_mismatch"])
        assertEquals("CATEGORY_CONFLICT", response.samples.first().bucket)
        assertTrue(response.samples.first().riskFlags.contains("activity_category_mismatch"))
    }

    @Test
    fun `diagnose blocks official candidates with unsafe price distribution before paper promotion`() {
        val now = System.currentTimeMillis()
        val lowSafe = candidate(503, "politics", LeaderResearchState.PAPER, "92", null, now)
        val tailSpray = candidate(512, "finance", LeaderResearchState.PAPER, "91", null, now)
        val sessions = listOf(
            LeaderPaperSession(
                id = 5030L,
                candidateId = 503L,
                tradeCount = 12,
                filteredCount = 1,
                copyablePnl = BigDecimal("5.0"),
                filteredRatio = BigDecimal("0.07")
            ),
            LeaderPaperSession(
                id = 5120L,
                candidateId = 512L,
                tradeCount = 12,
                filteredCount = 1,
                copyablePnl = BigDecimal("5.0"),
                filteredRatio = BigDecimal("0.07")
            )
        )
        Mockito.`when`(candidateRepository.findOfficialLeaderboardCandidates()).thenReturn(listOf(lowSafe, tailSpray))
        Mockito.`when`(paperSessionRepository.findLatestByCandidateIds(Mockito.anyCollection())).thenReturn(sessions)
        Mockito.`when`(candidateRepository.aggregateActivityMetricsForCandidateIds(Mockito.anyCollection())).thenReturn(
            listOf(
                activityMetric(candidateId = 503L, politicsEvents = 24L, safePriceEvents = 10L, tailPriceEvents = 1L),
                activityMetric(candidateId = 512L, financeEvents = 24L, safePriceEvents = 20L, tailPriceEvents = 4L)
            )
        )

        val response = service.diagnose(LeaderResearchOfficialLeaderboardDiagnoseRequest(sampleLimit = 10, staleHours = 48))

        assertEquals(0, response.cleanHighTotal)
        assertTrue(response.buckets.any { it.bucket == "HARD_RISK" && it.count == 2 })
        assertEquals(1, response.riskFlagCounts["low_safe_price_ratio"])
        assertEquals(1, response.riskFlagCounts["tail_price_spray"])
        assertTrue(response.samples.all { it.bucket == "HARD_RISK" })
    }

    @Test
    fun `diagnose prefers official leaderboard category when evidence has multiple sources`() {
        val now = System.currentTimeMillis()
        val mixedEvidence = candidate(1660, "finance", LeaderResearchState.TRIAL_READY, "90", null, now).copy(
            sourceEvidence = """
                activity_source:sports | category:sports | events:160
                scanner_pool:88 | category:sports | discovery_score:75
                external_analytics:polymarket_official_leaderboard | category:finance | rank:12
                profit_window:30d:12 profit_window:180d:40 activity_window:7d_trades:8
            """.trimIndent()
        )
        val session = LeaderPaperSession(
            id = 16600L,
            candidateId = 1660L,
            tradeCount = 23,
            filteredCount = 11,
            copyablePnl = BigDecimal("13.5"),
            filteredRatio = BigDecimal("0.3235")
        )
        Mockito.`when`(candidateRepository.findOfficialLeaderboardCandidates()).thenReturn(listOf(mixedEvidence))
        Mockito.`when`(paperSessionRepository.findLatestByCandidateIds(Mockito.anyCollection())).thenReturn(listOf(session))
        Mockito.`when`(candidateRepository.aggregateActivityMetricsForCandidateIds(Mockito.anyCollection())).thenReturn(
            listOf(activityMetric(candidateId = 1660L, financeEvents = 80L, safePriceEvents = 70L, tailPriceEvents = 5L))
        )

        val response = service.diagnose(LeaderResearchOfficialLeaderboardDiagnoseRequest(sampleLimit = 10, staleHours = 48))

        assertEquals(1, response.categories.first { it.category == "finance" }.total)
        assertEquals(0, response.categories.first { it.category == "crypto" }.total)
        assertEquals("finance", response.samples.first().category)
        assertTrue(response.samples.first().bucket in setOf("CLEAN_HIGH", "PAPER_OBSERVING"))
    }

    @Test
    fun `diagnose separates stale high quality official candidates from ordinary stale activity`() {
        val now = System.currentTimeMillis()
        val staleHighQuality = candidate(
            id = 1660,
            category = "finance",
            state = LeaderResearchState.TRIAL_READY,
            score = "90",
            riskFlags = null,
            lastSourceSeenAt = now - 56L * 60 * 60 * 1000
        )
        val session = LeaderPaperSession(
            id = 16601L,
            candidateId = 1660L,
            tradeCount = 23,
            filteredCount = 11,
            copyablePnl = BigDecimal("13.5"),
            filteredRatio = BigDecimal("0.3235")
        )
        Mockito.`when`(candidateRepository.findOfficialLeaderboardCandidates()).thenReturn(listOf(staleHighQuality))
        Mockito.`when`(paperSessionRepository.findLatestByCandidateIds(Mockito.anyCollection())).thenReturn(listOf(session))
        Mockito.`when`(candidateRepository.aggregateActivityMetricsForCandidateIds(Mockito.anyCollection())).thenReturn(
            listOf(activityMetric(candidateId = 1660L, financeEvents = 80L, safePriceEvents = 70L, tailPriceEvents = 5L))
        )

        val response = service.diagnose(LeaderResearchOfficialLeaderboardDiagnoseRequest(sampleLimit = 10, staleHours = 48))

        assertEquals(0, response.cleanHighTotal)
        assertTrue(response.buckets.any { it.bucket == "STALE_HIGH_QUALITY" && it.count == 1 })
        assertEquals("STALE_HIGH_QUALITY", response.samples.first().bucket)
        assertEquals("finance", response.samples.first().category)
    }

    @Test
    fun `diagnose counts clean trial ready human directional candidates for disabled trial queue`() {
        val now = System.currentTimeMillis()
        val candidate = candidate(
            id = 1660,
            category = "finance",
            state = LeaderResearchState.TRIAL_READY,
            score = "90",
            riskFlags = null,
            lastSourceSeenAt = now,
            strategyType = "human_directional"
        )
        val session = LeaderPaperSession(
            id = 16602L,
            candidateId = 1660L,
            tradeCount = 23,
            filteredCount = 11,
            copyablePnl = BigDecimal("13.5"),
            filteredRatio = BigDecimal("0.3235")
        )
        Mockito.`when`(candidateRepository.findOfficialLeaderboardCandidates()).thenReturn(listOf(candidate))
        Mockito.`when`(paperSessionRepository.findLatestByCandidateIds(Mockito.anyCollection())).thenReturn(listOf(session))
        Mockito.`when`(candidateRepository.aggregateActivityMetricsForCandidateIds(Mockito.anyCollection())).thenReturn(
            listOf(activityMetric(candidateId = 1660L, financeEvents = 80L, safePriceEvents = 70L, tailPriceEvents = 5L))
        )

        val response = service.diagnose(LeaderResearchOfficialLeaderboardDiagnoseRequest(sampleLimit = 10, staleHours = 48))

        assertEquals(1, response.cleanHighTotal)
        assertEquals(1, response.disabledTrialCandidateTotal)
        assertEquals("CLEAN_HIGH", response.samples.first().bucket)
        assertEquals("human_directional", response.samples.first().strategyType)
        assertTrue(response.samples.first().riskFlags.isEmpty())
    }

    @Test
    fun `diagnose excludes clean trial ready candidates with unknown strategy from disabled trial queue`() {
        val now = System.currentTimeMillis()
        val candidate = candidate(
            id = 1661,
            category = "finance",
            state = LeaderResearchState.TRIAL_READY,
            score = "90",
            riskFlags = null,
            lastSourceSeenAt = now,
            strategyType = "unknown"
        )
        val session = LeaderPaperSession(
            id = 16610L,
            candidateId = 1661L,
            tradeCount = 23,
            filteredCount = 11,
            copyablePnl = BigDecimal("13.5"),
            filteredRatio = BigDecimal("0.3235")
        )
        Mockito.`when`(candidateRepository.findOfficialLeaderboardCandidates()).thenReturn(listOf(candidate))
        Mockito.`when`(paperSessionRepository.findLatestByCandidateIds(Mockito.anyCollection())).thenReturn(listOf(session))
        Mockito.`when`(candidateRepository.aggregateActivityMetricsForCandidateIds(Mockito.anyCollection())).thenReturn(
            listOf(activityMetric(candidateId = 1661L, financeEvents = 80L, safePriceEvents = 70L, tailPriceEvents = 5L))
        )

        val response = service.diagnose(LeaderResearchOfficialLeaderboardDiagnoseRequest(sampleLimit = 10, staleHours = 48))

        assertEquals(1, response.cleanHighTotal)
        assertEquals(0, response.disabledTrialCandidateTotal)
        assertEquals("unknown", response.samples.first().strategyType)
    }

    private fun candidate(
        id: Long,
        category: String,
        state: LeaderResearchState,
        score: String,
        riskFlags: String?,
        lastSourceSeenAt: Long,
        strategyType: String? = null
    ) = LeaderResearchCandidate(
        id = id,
        normalizedWallet = "0x${id.toString().padStart(40, '0')}",
        researchState = state,
        source = "EXTERNAL_ANALYTICS_SOURCE",
        sourceEvidence = "external_analytics:polymarket_official_leaderboard | category:$category | rank:$id | " +
            "profit_window:30d:12 profit_window:180d:40 activity_window:7d_trades:8",
        score = BigDecimal(score),
        scoreVersion = LeaderResearchActivityScoringService.SCORE_VERSION,
        riskFlags = riskFlags,
        strategyType = strategyType,
        lastSourceSeenAt = lastSourceSeenAt
    )

    private fun activityMetric(
        candidateId: Long,
        politicsEvents: Long = 0,
        financeEvents: Long = 0,
        sportsEvents: Long = 0,
        cryptoEvents: Long = 0,
        safePriceEvents: Long = 20,
        tailPriceEvents: Long = 0
    ): LeaderResearchActivityMetricProjection {
        return object : LeaderResearchActivityMetricProjection {
            override fun getCandidateId() = candidateId
            override fun getTotalEvents() = politicsEvents + financeEvents + sportsEvents + cryptoEvents
            override fun getDistinctMarkets() = 10L
            override fun getBuyEvents() = 20L
            override fun getSellEvents() = 5L
            override fun getUsablePaperEvents() = 25L
            override fun getSafePriceEvents() = safePriceEvents
            override fun getTailPriceEvents() = tailPriceEvents
            override fun getPoliticsEvents() = politicsEvents
            override fun getFinanceEvents() = financeEvents
            override fun getSportsEvents() = sportsEvents
            override fun getCryptoEvents() = cryptoEvents
            override fun getAvgAmount() = BigDecimal("10")
            override fun getTotalAmount() = BigDecimal("250")
            override fun getLastEventTime() = 1L
        }
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
