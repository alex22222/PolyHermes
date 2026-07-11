package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchActivityScoreRequest
import com.wrbug.polymarketbot.dto.LeaderResearchStrategyBackfillRequest
import com.wrbug.polymarketbot.dto.LeaderResearchUnknownStrategySampleEnrichRequest
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.entity.LeaderResearchScore
import com.wrbug.polymarketbot.enums.LeaderResearchState
import com.wrbug.polymarketbot.repository.LeaderResearchActivityMetricProjection
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.repository.LeaderResearchScoreRepository
import org.springframework.data.domain.PageRequest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class LeaderResearchActivityScoringServiceTest {
    private val service = LeaderResearchActivityScoringService(
        candidateRepository = mock(),
        scoreRepository = mock()
    )

    @Test
    fun `compute rewards active diversified politics candidate`() {
        val candidate = LeaderResearchCandidate(
            id = 1L,
            normalizedWallet = "0x1111111111111111111111111111111111111111",
            source = "SCANNER_POOL",
            sourceEvidence = "scanner_pool:1 | category:politics | discovery_score:90"
        )

        val result = service.compute(
            candidate,
            metric(
                totalEvents = 80,
                distinctMarkets = 18,
                buyEvents = 50,
                sellEvents = 30,
                usablePaperEvents = 70,
                safePriceEvents = 65,
                tailPriceEvents = 2,
                avgAmount = BigDecimal("12.50"),
                totalAmount = BigDecimal("1000"),
                lastEventTime = System.currentTimeMillis()
            ),
            runId = null
        )

        assertTrue(result.totalScore >= BigDecimal("70"))
        assertEquals("politics", result.category)
        assertEquals(LeaderResearchStrategyTypeClassifier.HUMAN_DIRECTIONAL, result.strategyType)
        assertFalse(result.riskFlags.contains("tail_price_spray"))
        assertFalse(result.riskFlags.contains("buy_only_no_exit"))
    }

    @Test
    fun `compute caps tail price spray buy only candidate`() {
        val candidate = LeaderResearchCandidate(
            id = 2L,
            normalizedWallet = "0x2222222222222222222222222222222222222222",
            source = "SCANNER_POOL",
            sourceEvidence = "scanner_pool:2 | category:finance | discovery_score:88"
        )

        val result = service.compute(
            candidate,
            metric(
                totalEvents = 60,
                distinctMarkets = 30,
                buyEvents = 60,
                sellEvents = 0,
                usablePaperEvents = 10,
                safePriceEvents = 8,
                tailPriceEvents = 45,
                avgAmount = BigDecimal("0.22"),
                totalAmount = BigDecimal("13.20"),
                lastEventTime = System.currentTimeMillis()
            ),
            runId = null
        )

        assertTrue(result.totalScore <= BigDecimal("20"))
        assertEquals(LeaderResearchStrategyTypeClassifier.LOW_PRICE_TAIL_RISK, result.strategyType)
        assertTrue(result.riskFlags.contains("tail_price_spray"))
        assertTrue(result.riskFlags.contains("strategy_low_price_tail_risk"))
        assertTrue(result.riskFlags.contains("buy_only_no_exit"))
        assertTrue(result.riskFlags.contains("low_average_size"))
    }

    @Test
    fun `compute identifies market maker like high churn activity as non copyable`() {
        val candidate = LeaderResearchCandidate(
            id = 5L,
            normalizedWallet = "0x5555555555555555555555555555555555555555",
            source = "ACTIVITY_SOURCE",
            sourceEvidence = "activity_source:finance | category:finance"
        )

        val result = service.compute(
            candidate,
            metric(
                totalEvents = 120,
                distinctMarkets = 25,
                buyEvents = 58,
                sellEvents = 62,
                usablePaperEvents = 110,
                safePriceEvents = 100,
                tailPriceEvents = 0,
                avgAmount = BigDecimal("1.20"),
                totalAmount = BigDecimal("144"),
                lastEventTime = System.currentTimeMillis()
            ),
            runId = null
        )

        assertEquals(LeaderResearchStrategyTypeClassifier.MARKET_MAKER_LP, result.strategyType)
        assertTrue(result.riskFlags.contains("strategy_market_maker_lp"))
        assertTrue(result.totalScore <= BigDecimal("55"))
    }

    @Test
    fun `compute caps high buy weak exit sample`() {
        val candidate = LeaderResearchCandidate(
            id = 6L,
            normalizedWallet = "0x6666666666666666666666666666666666666666",
            source = "ACTIVITY_SOURCE",
            sourceEvidence = "activity_source:politics | category:politics"
        )

        val result = service.compute(
            candidate,
            metric(
                totalEvents = 64,
                distinctMarkets = 39,
                buyEvents = 60,
                sellEvents = 4,
                usablePaperEvents = 64,
                safePriceEvents = 62,
                tailPriceEvents = 1,
                avgAmount = BigDecimal("88.75"),
                totalAmount = BigDecimal("5680"),
                lastEventTime = System.currentTimeMillis()
            ),
            runId = null
        )

        assertEquals(LeaderResearchStrategyTypeClassifier.UNKNOWN, result.strategyType)
        assertTrue(result.riskFlags.contains("weak_exit_sample"))
        assertTrue(result.totalScore <= BigDecimal("55"))
        assertEquals(1, result.unknownStrategyReasons.count { it == "sell_ratio_outside_copyable_range" })
    }

    @Test
    fun `compute uses dominant activity market category over source evidence`() {
        val candidate = LeaderResearchCandidate(
            id = 7L,
            normalizedWallet = "0x7777777777777777777777777777777777777777",
            source = "SCANNER_POOL",
            sourceEvidence = """
                scanner_pool:1 | category:politics | discovery_score:90
                scanner_pool:2 | category:finance | discovery_score:40
            """.trimIndent()
        )

        val result = service.compute(
            candidate,
            metric(
                totalEvents = 100,
                distinctMarkets = 30,
                buyEvents = 98,
                sellEvents = 2,
                usablePaperEvents = 90,
                safePriceEvents = 80,
                tailPriceEvents = 2,
                politicsEvents = 1,
                financeEvents = 0,
                sportsEvents = 95,
                cryptoEvents = 0,
                avgAmount = BigDecimal("20.00"),
                totalAmount = BigDecimal("2000"),
                lastEventTime = System.currentTimeMillis()
            ),
            runId = null
        )

        assertEquals("sports", result.category)
        assertTrue(result.riskFlags.contains("activity_category_mismatch"))
        assertTrue(result.riskFlags.contains("weak_exit_sample"))
        assertTrue(result.unknownStrategyReasons.contains("activity_category_mismatch"))
        assertTrue(result.totalScore <= BigDecimal("50"))
        assertTrue(result.reason.contains("activity_category=sports"))
    }

    @Test
    fun `compute caps sell only candidate`() {
        val candidate = LeaderResearchCandidate(
            id = 3L,
            normalizedWallet = "0x3333333333333333333333333333333333333333",
            source = "ACTIVITY_SOURCE",
            sourceEvidence = "activity_source:finance | category:finance"
        )

        val result = service.compute(
            candidate,
            metric(
                totalEvents = 40,
                distinctMarkets = 20,
                buyEvents = 0,
                sellEvents = 40,
                usablePaperEvents = 30,
                safePriceEvents = 35,
                tailPriceEvents = 0,
                avgAmount = BigDecimal("5.00"),
                totalAmount = BigDecimal("200"),
                lastEventTime = System.currentTimeMillis()
            ),
            runId = null
        )

        assertTrue(result.totalScore <= BigDecimal("55"))
        assertTrue(result.riskFlags.contains("sell_only_no_entry"))
    }

    @Test
    fun `compute caps mixed category evidence`() {
        val candidate = LeaderResearchCandidate(
            id = 4L,
            normalizedWallet = "0x4444444444444444444444444444444444444444",
            source = "SCANNER_POOL",
            sourceEvidence = """
                scanner_pool:1 | category:politics | discovery_score:90
                scanner_pool:2 | category:sports | discovery_score:88
            """.trimIndent()
        )

        val result = service.compute(
            candidate,
            metric(
                totalEvents = 80,
                distinctMarkets = 20,
                buyEvents = 50,
                sellEvents = 30,
                usablePaperEvents = 75,
                safePriceEvents = 70,
                tailPriceEvents = 1,
                avgAmount = BigDecimal("10.00"),
                totalAmount = BigDecimal("800"),
                lastEventTime = System.currentTimeMillis()
            ),
            runId = null
        )

        assertEquals("politics", result.category)
        assertTrue(result.riskFlags.contains("mixed_category_evidence"))
        assertTrue(result.totalScore <= BigDecimal("60"))
    }

    @Test
    fun `score activity prescreen can target candidate ids without full state scan`() {
        val candidateRepository: LeaderResearchCandidateRepository = mock()
        val scoreRepository: LeaderResearchScoreRepository = mock()
        val service = LeaderResearchActivityScoringService(candidateRepository, scoreRepository)
        val candidate = LeaderResearchCandidate(
            id = 42L,
            normalizedWallet = "0x4242424242424242424242424242424242424242",
            researchState = LeaderResearchState.DISCOVERED,
            source = "ACTIVITY_SOURCE",
            sourceEvidence = "activity_source:politics | category:politics"
        )
        Mockito.`when`(candidateRepository.findAllById(listOf(42L, 404L))).thenReturn(listOf(candidate))
        Mockito.`when`(candidateRepository.aggregateActivityMetricsForCandidateIds(listOf(42L))).thenReturn(
            listOf(
                metric(
                    candidateId = 42L,
                    totalEvents = 40,
                    distinctMarkets = 8,
                    buyEvents = 25,
                    sellEvents = 10,
                    usablePaperEvents = 30,
                    safePriceEvents = 32,
                    tailPriceEvents = 1,
                    avgAmount = BigDecimal("4.00"),
                    totalAmount = BigDecimal("160"),
                    lastEventTime = System.currentTimeMillis()
                )
            )
        )
        Mockito.`when`(scoreRepository.save(anyScore())).thenAnswer { it.arguments[0] }
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }

        val response = service.scoreActivityPrescreen(
            LeaderResearchActivityScoreRequest(
                force = true,
                candidateIds = listOf(42L, 404L)
            )
        )

        assertEquals(1, response.scannedCount)
        assertEquals(1, response.scoredCount)
        val savedCandidate = Mockito.mockingDetails(candidateRepository).invocations
            .last { it.method.name == "save" }
            .arguments[0] as LeaderResearchCandidate
        assertEquals(LeaderResearchStrategyTypeClassifier.HUMAN_DIRECTIONAL, savedCandidate.strategyType)
        Mockito.verify(candidateRepository, Mockito.never()).findByResearchStateIn(anyStates())
        Mockito.verify(candidateRepository).aggregateActivityMetricsForCandidateIds(listOf(42L))
    }

    @Test
    fun `backfill unknown strategy types selects limited active candidates and scores them`() {
        val candidateRepository: LeaderResearchCandidateRepository = mock()
        val scoreRepository: LeaderResearchScoreRepository = mock()
        val service = LeaderResearchActivityScoringService(candidateRepository, scoreRepository)
        val candidate = LeaderResearchCandidate(
            id = 77L,
            normalizedWallet = "0x7777777777777777777777777777777777777777",
            researchState = LeaderResearchState.PAPER,
            strategyType = null,
            source = "ACTIVITY_SOURCE",
            sourceEvidence = "activity_source:finance | category:finance"
        )
        val unknownCandidate = LeaderResearchCandidate(
            id = 78L,
            normalizedWallet = "0x7878787878787878787878787878787878787878",
            researchState = LeaderResearchState.PAPER,
            strategyType = null,
            source = "SCANNER_POOL",
            sourceEvidence = "scanner_pool:78 | category:politics | discovery_score:70"
        )
        Mockito.`when`(
            candidateRepository.findUnknownStrategyCandidates(
                listOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY),
                PageRequest.of(0, 100)
            )
        ).thenReturn(listOf(candidate, unknownCandidate))
        Mockito.`when`(candidateRepository.findAllById(listOf(77L, 78L))).thenReturn(listOf(candidate, unknownCandidate))
        Mockito.`when`(candidateRepository.aggregateActivityMetricsForCandidateIds(listOf(77L, 78L))).thenReturn(
            listOf(
                metric(
                    candidateId = 77L,
                    totalEvents = 80,
                    distinctMarkets = 20,
                    buyEvents = 45,
                    sellEvents = 30,
                    usablePaperEvents = 70,
                    safePriceEvents = 68,
                    tailPriceEvents = 0,
                    avgAmount = BigDecimal("9.00"),
                    totalAmount = BigDecimal("720"),
                    lastEventTime = System.currentTimeMillis()
                ),
                metric(
                    candidateId = 78L,
                    totalEvents = 10,
                    distinctMarkets = 2,
                    buyEvents = 10,
                    sellEvents = 0,
                    usablePaperEvents = 5,
                    safePriceEvents = 2,
                    tailPriceEvents = 1,
                    avgAmount = BigDecimal("2.00"),
                    totalAmount = BigDecimal("20"),
                    lastEventTime = System.currentTimeMillis()
                )
            )
        )
        Mockito.`when`(scoreRepository.save(anyScore())).thenAnswer { it.arguments[0] }
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }

        val response = service.backfillUnknownStrategyTypes(
            LeaderResearchStrategyBackfillRequest(limit = 100, force = true)
        )

        assertEquals(2, response.selectedCount)
        assertEquals(listOf(77L, 78L), response.selectedCandidateIds)
        assertEquals(2, response.scoreResult.scoredCount)
        assertEquals(1, response.scoreResult.unknownStrategyReasonCounts["insufficient_sample"])
        assertEquals(1, response.scoreResult.unknownStrategyReasonCounts["insufficient_market_diversity"])
        assertEquals(1, response.scoreResult.unknownStrategyReasonCounts["no_sell_sample"])
        assertEquals(1, response.scoreResult.unknownStrategyReasonCounts["low_safe_price_ratio_for_directional"])
        val savedCandidate = Mockito.mockingDetails(candidateRepository).invocations
            .last { it.method.name == "save" }
            .arguments[0] as LeaderResearchCandidate
        assertEquals(LeaderResearchStrategyTypeClassifier.UNKNOWN, savedCandidate.strategyType)
    }

    @Test
    fun `plan unknown strategy sample enrichment selects primary category sample gaps`() {
        val candidateRepository: LeaderResearchCandidateRepository = mock()
        val scoreRepository: LeaderResearchScoreRepository = mock()
        val service = LeaderResearchActivityScoringService(candidateRepository, scoreRepository)
        val financeGap = LeaderResearchCandidate(
            id = 81L,
            normalizedWallet = "0x8181818181818181818181818181818181818181",
            researchState = LeaderResearchState.PAPER,
            strategyType = "unknown",
            source = "SCANNER_POOL",
            sourceEvidence = "scanner_pool:81 | category:finance | discovery_score:80"
        )
        val sportsGap = LeaderResearchCandidate(
            id = 82L,
            normalizedWallet = "0x8282828282828282828282828282828282828282",
            researchState = LeaderResearchState.PAPER,
            strategyType = "unknown",
            source = "SCANNER_POOL",
            sourceEvidence = "scanner_pool:82 | category:sports | discovery_score:80"
        )
        val humanDirectional = LeaderResearchCandidate(
            id = 83L,
            normalizedWallet = "0x8383838383838383838383838383838383838383",
            researchState = LeaderResearchState.PAPER,
            strategyType = "unknown",
            source = "ACTIVITY_SOURCE",
            sourceEvidence = "activity_source:finance | category:finance"
        )
        Mockito.`when`(
            candidateRepository.findUnknownStrategyCandidates(
                listOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY),
                PageRequest.of(0, 200)
            )
        ).thenReturn(listOf(financeGap, sportsGap, humanDirectional))
        Mockito.`when`(candidateRepository.aggregateActivityMetricsForCandidateIds(setOf(81L, 82L, 83L))).thenReturn(
            listOf(
                metric(
                    candidateId = 81L,
                    totalEvents = 10,
                    distinctMarkets = 2,
                    buyEvents = 10,
                    sellEvents = 0,
                    usablePaperEvents = 5,
                    safePriceEvents = 2,
                    tailPriceEvents = 1,
                    avgAmount = BigDecimal("2.00"),
                    totalAmount = BigDecimal("20"),
                    lastEventTime = System.currentTimeMillis()
                ),
                metric(
                    candidateId = 82L,
                    totalEvents = 8,
                    distinctMarkets = 2,
                    buyEvents = 8,
                    sellEvents = 0,
                    usablePaperEvents = 4,
                    safePriceEvents = 2,
                    tailPriceEvents = 1,
                    avgAmount = BigDecimal("2.00"),
                    totalAmount = BigDecimal("16"),
                    lastEventTime = System.currentTimeMillis()
                ),
                metric(
                    candidateId = 83L,
                    totalEvents = 80,
                    distinctMarkets = 20,
                    buyEvents = 45,
                    sellEvents = 30,
                    usablePaperEvents = 70,
                    safePriceEvents = 68,
                    tailPriceEvents = 0,
                    avgAmount = BigDecimal("9.00"),
                    totalAmount = BigDecimal("720"),
                    lastEventTime = System.currentTimeMillis()
                )
            )
        )

        val response = service.planUnknownStrategySampleEnrichment(
            LeaderResearchUnknownStrategySampleEnrichRequest(categories = listOf("finance"), limit = 5, dryRun = true)
        )

        assertEquals(true, response.dryRun)
        assertEquals(1, response.selectedCount)
        assertEquals(listOf(81L), response.selectedCandidateIds)
        assertEquals(1, response.categoryCounts["finance"])
        assertEquals(1, response.unknownStrategyReasonCounts["insufficient_sample"])
        assertEquals(1, response.unknownStrategyReasonCounts["no_sell_sample"])
    }

    @Test
    fun `plan unknown strategy sample enrichment excludes dominant non primary activity category`() {
        val candidateRepository: LeaderResearchCandidateRepository = mock()
        val scoreRepository: LeaderResearchScoreRepository = mock()
        val service = LeaderResearchActivityScoringService(candidateRepository, scoreRepository)
        val sportsDominant = LeaderResearchCandidate(
            id = 91L,
            normalizedWallet = "0x9191919191919191919191919191919191919191",
            researchState = LeaderResearchState.PAPER,
            strategyType = "unknown",
            source = "SCANNER_POOL",
            sourceEvidence = "scanner_pool:91 | category:politics | discovery_score:80"
        )
        Mockito.`when`(
            candidateRepository.findUnknownStrategyCandidates(
                listOf(LeaderResearchState.PAPER, LeaderResearchState.TRIAL_READY),
                PageRequest.of(0, 200)
            )
        ).thenReturn(listOf(sportsDominant))
        Mockito.`when`(candidateRepository.aggregateActivityMetricsForCandidateIds(setOf(91L))).thenReturn(
            listOf(
                metric(
                    candidateId = 91L,
                    totalEvents = 100,
                    distinctMarkets = 30,
                    buyEvents = 98,
                    sellEvents = 2,
                    usablePaperEvents = 90,
                    safePriceEvents = 80,
                    tailPriceEvents = 2,
                    politicsEvents = 1,
                    sportsEvents = 95,
                    avgAmount = BigDecimal("20.00"),
                    totalAmount = BigDecimal("2000"),
                    lastEventTime = System.currentTimeMillis()
                )
            )
        )

        val response = service.planUnknownStrategySampleEnrichment(
            LeaderResearchUnknownStrategySampleEnrichRequest(categories = listOf("politics", "finance"), limit = 5, dryRun = true)
        )

        assertEquals(0, response.selectedCount)
        assertEquals(emptyList<Long>(), response.selectedCandidateIds)
    }

    private fun metric(
        candidateId: Long = 1L,
        totalEvents: Long,
        distinctMarkets: Long,
        buyEvents: Long,
        sellEvents: Long,
        usablePaperEvents: Long,
        safePriceEvents: Long,
        tailPriceEvents: Long,
        politicsEvents: Long = 0,
        financeEvents: Long = 0,
        sportsEvents: Long = 0,
        cryptoEvents: Long = 0,
        avgAmount: BigDecimal,
        totalAmount: BigDecimal,
        lastEventTime: Long?
    ): LeaderResearchActivityMetricProjection {
        return object : LeaderResearchActivityMetricProjection {
            override fun getCandidateId(): Long = candidateId
            override fun getTotalEvents(): Long = totalEvents
            override fun getDistinctMarkets(): Long = distinctMarkets
            override fun getBuyEvents(): Long = buyEvents
            override fun getSellEvents(): Long = sellEvents
            override fun getUsablePaperEvents(): Long = usablePaperEvents
            override fun getSafePriceEvents(): Long = safePriceEvents
            override fun getTailPriceEvents(): Long = tailPriceEvents
            override fun getPoliticsEvents(): Long = politicsEvents
            override fun getFinanceEvents(): Long = financeEvents
            override fun getSportsEvents(): Long = sportsEvents
            override fun getCryptoEvents(): Long = cryptoEvents
            override fun getAvgAmount(): BigDecimal = avgAmount
            override fun getTotalAmount(): BigDecimal = totalAmount
            override fun getLastEventTime(): Long? = lastEventTime
        }
    }

    private fun anyCandidate(): LeaderResearchCandidate {
        Mockito.any(LeaderResearchCandidate::class.java)
        return LeaderResearchCandidate(normalizedWallet = "0x1111111111111111111111111111111111111111")
    }

    private fun anyScore(): LeaderResearchScore {
        Mockito.any(LeaderResearchScore::class.java)
        return LeaderResearchScore(candidateId = 1, scoreVersion = LeaderResearchActivityScoringService.SCORE_VERSION)
    }

    private fun anyStates(): Collection<LeaderResearchState> {
        Mockito.anyCollection<LeaderResearchState>()
        return emptyList()
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
