package com.wrbug.polymarketbot.service.copytrading.leaders

import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import com.wrbug.polymarketbot.repository.CopyOrderTrackingRepository
import com.wrbug.polymarketbot.repository.FilteredOrderRepository
import com.wrbug.polymarketbot.repository.SellMatchRecordRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class LeaderExecutionStatsServiceTest {
    private val bridgeTradeRecordRepository: BridgeTradeRecordRepository = mock()
    private val copyOrderTrackingRepository: CopyOrderTrackingRepository = mock()
    private val filteredOrderRepository: FilteredOrderRepository = mock()
    private val sellMatchRecordRepository: SellMatchRecordRepository = mock()
    private val service = RepositoryLeaderExecutionStatsService(
        bridgeTradeRecordRepository,
        copyOrderTrackingRepository,
        filteredOrderRepository,
        sellMatchRecordRepository
    )

    @Test
    fun `uses backtest fallback when no real execution data exists`() {
        val result = service.scoreLeaderExecution(10L, null, BigDecimal("75"))

        assertEquals(BigDecimal("75"), result.score)
        assertEquals("BACKTEST_FALLBACK", result.source)
        assertTrue(result.riskFlags.isEmpty())
    }

    @Test
    fun `successful buy and sell execution produces high score`() {
        Mockito.`when`(copyOrderTrackingRepository.countByLeaderId(10L)).thenReturn(8)
        Mockito.`when`(filteredOrderRepository.countByLeaderIdAndSide(10L, "BUY")).thenReturn(1)
        Mockito.`when`(filteredOrderRepository.countByLeaderIdAndSide(10L, "SELL")).thenReturn(0)
        Mockito.`when`(sellMatchRecordRepository.countByLeaderId(10L)).thenReturn(5)
        Mockito.`when`(copyOrderTrackingRepository.countOpenByLeaderId(10L)).thenReturn(1)
        Mockito.`when`(sellMatchRecordRepository.countLossByLeaderId(10L)).thenReturn(0)

        val result = service.scoreLeaderExecution(10L, null, BigDecimal("20"))

        assertEquals("REAL_EXECUTION", result.source)
        assertTrue(result.score > BigDecimal("80"))
        assertTrue(result.riskFlags.none { it.contains("execution_weak") })
    }

    @Test
    fun `filtered sells and open backlog penalize execution score`() {
        Mockito.`when`(copyOrderTrackingRepository.countByLeaderId(10L)).thenReturn(5)
        Mockito.`when`(filteredOrderRepository.countByLeaderIdAndSide(10L, "BUY")).thenReturn(0)
        Mockito.`when`(filteredOrderRepository.countByLeaderIdAndSide(10L, "SELL")).thenReturn(5)
        Mockito.`when`(sellMatchRecordRepository.countByLeaderId(10L)).thenReturn(1)
        Mockito.`when`(copyOrderTrackingRepository.countOpenByLeaderId(10L)).thenReturn(5)
        Mockito.`when`(sellMatchRecordRepository.countLossByLeaderId(10L)).thenReturn(0)

        val result = service.scoreLeaderExecution(10L, null, BigDecimal("85"))

        assertEquals("REAL_EXECUTION", result.source)
        assertTrue(result.score <= BigDecimal("45"))
        assertTrue(result.riskFlags.contains("sell_execution_weak"))
        assertTrue(result.riskFlags.contains("open_position_backlog"))
    }

    @Test
    fun `bridge raw payload failures by leader address penalize execution score`() {
        Mockito.`when`(
            bridgeTradeRecordRepository.countByLeaderAddressAndSideAndStatus(
                "0xleader",
                "BUY",
                "SUCCESS"
            )
        ).thenReturn(2)
        Mockito.`when`(
            bridgeTradeRecordRepository.countByLeaderAddressAndSideAndStatus(
                "0xleader",
                "BUY",
                "FAILED"
            )
        ).thenReturn(10)
        Mockito.`when`(
            bridgeTradeRecordRepository.countByLeaderAddressAndSideAndStatus(
                "0xleader",
                "SELL",
                "SUCCESS"
            )
        ).thenReturn(0)
        Mockito.`when`(
            bridgeTradeRecordRepository.countByLeaderAddressAndSideAndStatus(
                "0xleader",
                "SELL",
                "FAILED"
            )
        ).thenReturn(4)

        val result = service.scoreLeaderExecution(10L, "0xleader", BigDecimal("90"))

        assertEquals("REAL_EXECUTION", result.source)
        assertTrue(result.score <= BigDecimal("45"))
        assertTrue(result.riskFlags.contains("buy_execution_weak"))
        assertTrue(result.riskFlags.contains("sell_execution_weak"))
        assertEquals(10, result.stats.bridgeBuyFailedCount)
        assertEquals(4, result.stats.bridgeSellFailedCount)
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
