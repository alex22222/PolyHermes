package com.wrbug.polymarketbot.service.copytrading.leaders

import com.wrbug.polymarketbot.entity.BacktestTask
import com.wrbug.polymarketbot.entity.Leader
import com.wrbug.polymarketbot.repository.BacktestTaskRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class LeaderResearchScoreAdapterServiceTest {
    private val leaderRepository: LeaderRepository = mock()
    private val backtestTaskRepository: BacktestTaskRepository = mock()
    private val leaderExecutionStatsService: LeaderExecutionStatsService = mock()
    private val service = LeaderResearchScoreAdapterService(
        leaderRepository,
        backtestTaskRepository,
        leaderExecutionStatsService
    )

    @Test
    fun `low average trade size with uncopyable backtest is blocked as tail spray`() {
        val leader = Leader(
            id = 66L,
            leaderAddress = "0xc21ea96be762bb55041529af6e386e7c53b80215",
            leaderName = "Low-Futon",
            category = "finance",
            totalTrades = 22,
            winRate = BigDecimal("80.00"),
            totalPnl = "2629.2755",
            totalVolume = "4.8182",
            avgTradeSize = "0.2190",
            lastTradeAt = System.currentTimeMillis(),
            activityScore = BigDecimal("100.00"),
            smartMoneyRank = 5
        )
        val backtest = BacktestTask(
            id = 1L,
            taskName = "Low-Futon backtest",
            leaderId = 66L,
            initialBalance = BigDecimal("100"),
            backtestDays = 7,
            startTime = System.currentTimeMillis() - 7L * 24 * 60 * 60 * 1000,
            status = "COMPLETED",
            totalTrades = 0,
            profitAmount = BigDecimal.ZERO,
            profitRate = BigDecimal.ZERO
        )
        Mockito.`when`(backtestTaskRepository.findByLeaderIdAndStatus(66L, "COMPLETED")).thenReturn(listOf(backtest))
        Mockito.`when`(
            leaderExecutionStatsService.scoreLeaderExecution(
                66L,
                "0xc21ea96be762bb55041529af6e386e7c53b80215",
                BigDecimal.ZERO
            )
        ).thenReturn(
            LeaderExecutionScoreResult(
                score = BigDecimal.ZERO,
                riskFlags = emptyList(),
                stats = LeaderExecutionStats(
                    buyCreatedCount = 0,
                    filteredBuyCount = 0,
                    filteredSellCount = 0,
                    matchedSellCount = 0,
                    openBuyCount = 0,
                    lossSellCount = 0
                ),
                source = "REAL_EXECUTION"
            )
        )

        val result = service.computeScore(leader)

        assertEquals("RISKY", result.tag)
        assertTrue(result.score <= BigDecimal("14.99"))
        assertTrue(result.riskFlags!!.contains("tail_price_spray"))
        assertTrue(result.riskFlags!!.contains("backtest_no_simulated_trades"))
    }

    @Test
    fun `zero win rate negative pnl leader is blocked as risky`() {
        val leader = Leader(
            id = 91L,
            leaderAddress = "0x0ec7f0eac6c47934ab9b41e02bd8f15a5f4293d1",
            leaderName = "Alienated-Invite",
            category = "sports",
            totalTrades = 66,
            winRate = BigDecimal("0.00"),
            totalPnl = "-5.1105",
            totalVolume = "142.8971",
            avgTradeSize = "2.1651",
            lastTradeAt = System.currentTimeMillis(),
            activityScore = BigDecimal("80.00"),
            smartMoneyRank = null
        )
        Mockito.`when`(backtestTaskRepository.findByLeaderIdAndStatus(91L, "COMPLETED")).thenReturn(emptyList())
        Mockito.`when`(
            leaderExecutionStatsService.scoreLeaderExecution(
                91L,
                "0x0ec7f0eac6c47934ab9b41e02bd8f15a5f4293d1",
                BigDecimal("25")
            )
        ).thenReturn(
            LeaderExecutionScoreResult(
                score = BigDecimal("25"),
                riskFlags = emptyList(),
                stats = LeaderExecutionStats(
                    buyCreatedCount = 0,
                    filteredBuyCount = 0,
                    filteredSellCount = 0,
                    matchedSellCount = 0,
                    openBuyCount = 0,
                    lossSellCount = 0
                ),
                source = "BACKTEST_FALLBACK"
            )
        )

        val result = service.computeScore(leader)

        assertEquals("RISKY", result.tag)
        assertTrue(result.score <= BigDecimal("14.99"))
        assertTrue(result.riskFlags!!.contains("zero_win_rate"))
        assertTrue(result.riskFlags!!.contains("zero_win_negative_pnl"))
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
