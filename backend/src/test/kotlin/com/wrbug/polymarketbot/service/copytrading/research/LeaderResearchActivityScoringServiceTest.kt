package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.repository.LeaderResearchActivityMetricProjection
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.repository.LeaderResearchScoreRepository
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
        assertTrue(result.riskFlags.contains("tail_price_spray"))
        assertTrue(result.riskFlags.contains("buy_only_no_exit"))
        assertTrue(result.riskFlags.contains("low_average_size"))
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

    private fun metric(
        totalEvents: Long,
        distinctMarkets: Long,
        buyEvents: Long,
        sellEvents: Long,
        usablePaperEvents: Long,
        safePriceEvents: Long,
        tailPriceEvents: Long,
        avgAmount: BigDecimal,
        totalAmount: BigDecimal,
        lastEventTime: Long?
    ): LeaderResearchActivityMetricProjection {
        return object : LeaderResearchActivityMetricProjection {
            override fun getCandidateId(): Long = 1
            override fun getTotalEvents(): Long = totalEvents
            override fun getDistinctMarkets(): Long = distinctMarkets
            override fun getBuyEvents(): Long = buyEvents
            override fun getSellEvents(): Long = sellEvents
            override fun getUsablePaperEvents(): Long = usablePaperEvents
            override fun getSafePriceEvents(): Long = safePriceEvents
            override fun getTailPriceEvents(): Long = tailPriceEvents
            override fun getAvgAmount(): BigDecimal = avgAmount
            override fun getTotalAmount(): BigDecimal = totalAmount
            override fun getLastEventTime(): Long? = lastEventTime
        }
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
