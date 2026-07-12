package com.wrbug.polymarketbot.service.copytrading.statistics

import com.wrbug.polymarketbot.api.TradeResponse
import com.wrbug.polymarketbot.entity.ModelTradeCandidate
import com.wrbug.polymarketbot.repository.ModelTradeCandidateRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNotEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito

class ModelTradeCandidateServiceTest {
    private val repository = Mockito.mock(ModelTradeCandidateRepository::class.java)
    private val service = ModelTradeCandidateService(repository)

    @Test
    fun `same trade and configuration reuses candidate`() {
        val saved = mutableListOf<ModelTradeCandidate>()
        Mockito.`when`(repository.findByLeaderIdAndLeaderTradeIdAndCopyTradingIdAndAccountId(7, "trade-1", 11, 2))
            .thenAnswer { saved.firstOrNull() }
        Mockito.`when`(repository.saveAndFlush(anyCandidate())).thenAnswer {
            (it.arguments[0] as ModelTradeCandidate).also(saved::add)
        }

        val first = service.observe(7, 11, 2, trade(), "activity-ws")
        val repeated = service.observe(7, 11, 2, trade(), "onchain-ws")

        assertEquals(first.candidateId, repeated.candidateId)
        assertEquals("activity-ws", repeated.source)
        assertEquals(1, saved.size)
    }

    @Test
    fun `same leader trade creates separate candidates for separate configurations`() {
        Mockito.`when`(repository.saveAndFlush(anyCandidate())).thenAnswer { it.arguments[0] }

        val first = service.observe(7, 11, 2, trade(), "activity-ws")
        val second = service.observe(7, 12, 2, trade(), "activity-ws")

        assertNotEquals(first.candidateId, second.candidateId)
    }

    private fun trade() = TradeResponse(
        id = "trade-1",
        market = "market-1",
        side = "BUY",
        price = "0.52",
        size = "10",
        timestamp = "1783746300",
        user = null,
        outcomeIndex = 0,
        outcome = "Up"
    )

    private fun anyCandidate(): ModelTradeCandidate {
        Mockito.any(ModelTradeCandidate::class.java)
        return ModelTradeCandidate(
            candidateId = "unused",
            leaderId = 0,
            leaderTradeId = "unused",
            copyTradingId = 0,
            accountId = 0,
            source = "test",
            side = "BUY",
            leaderPrice = java.math.BigDecimal.ZERO,
            leaderSize = java.math.BigDecimal.ZERO
        )
    }
}
