package com.wrbug.polymarketbot.service.accounts

import com.wrbug.polymarketbot.entity.Account
import com.wrbug.polymarketbot.entity.BridgePositionSnapshot
import com.wrbug.polymarketbot.repository.BridgePositionSnapshotRepository
import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import com.wrbug.polymarketbot.repository.MarketRepository
import com.wrbug.polymarketbot.service.common.MarketPriceService
import kotlinx.coroutines.runBlocking
import org.junit.jupiter.api.Assertions.*
import org.junit.jupiter.api.Test
import org.mockito.Mockito.*
import java.math.BigDecimal

class BridgePositionServiceTest {

    private val tradeRecordRepository = mock(BridgeTradeRecordRepository::class.java)
    private val snapshotRepository = mock(BridgePositionSnapshotRepository::class.java)
    private val marketRepository = mock(MarketRepository::class.java)
    private val marketPriceService = mock(MarketPriceService::class.java)

    private val service = BridgePositionService(
        tradeRecordRepository,
        snapshotRepository,
        marketRepository,
        marketPriceService
    )

    @Test
    fun `snapshot with null currentValue pnl percentPnl falls back to zero`() = runBlocking {
        val account = Account(
            id = 1L,
            walletAddress = "0xabc",
            proxyAddress = "0xdef"
        )
        val snapshot = BridgePositionSnapshot(
            id = 1L,
            bridgeId = "polymtrade-bridge",
            walletAddress = "0xabc",
            marketTitle = "Will France win?",
            side = "YES",
            quantity = BigDecimal("10.00000000"),
            currentValue = null,
            pnl = null,
            percentPnl = null
        )
        `when`(snapshotRepository.findByBridgeIdAndWalletAddress("polymtrade-bridge", "0xabc"))
            .thenReturn(listOf(snapshot))

        val positions = service.getSnapshotPositionsForAccount(account)

        assertEquals(1, positions.size)
        val dto = positions.first()
        assertEquals("0.0000", dto.currentValue)
        assertEquals("0.0000", dto.pnl)
        assertEquals("0.00", dto.percentPnl)
        assertEquals("0.0000", dto.avgPrice)
        assertEquals("0.0000", dto.currentPrice)
    }

    @Test
    fun `snapshot with valid values computes prices correctly`() = runBlocking {
        val account = Account(
            id = 2L,
            walletAddress = "0x123",
            proxyAddress = "0x456"
        )
        val snapshot = BridgePositionSnapshot(
            id = 2L,
            bridgeId = "polymtrade-bridge",
            walletAddress = "0x123",
            marketTitle = "Will Spain win?",
            side = "NO",
            quantity = BigDecimal("8.00000000"),
            currentValue = BigDecimal("4.00000000"),
            pnl = BigDecimal("1.00000000"),
            percentPnl = BigDecimal("25.0000")
        )
        `when`(snapshotRepository.findByBridgeIdAndWalletAddress("polymtrade-bridge", "0x123"))
            .thenReturn(listOf(snapshot))

        val positions = service.getSnapshotPositionsForAccount(account)

        assertEquals(1, positions.size)
        val dto = positions.first()
        assertEquals("4.0000", dto.currentValue)
        assertEquals("1.0000", dto.pnl)
        assertEquals("25.00", dto.percentPnl)
        // initialValue = currentValue - pnl = 3; avgPrice = 3 / 8 = 0.375
        assertEquals("0.3750", dto.avgPrice)
        // currentPrice = 4 / 8 = 0.5
        assertEquals("0.5000", dto.currentPrice)
    }

    @Test
    fun `snapshot with null percentPnl computes from pnl and initialValue`() = runBlocking {
        val account = Account(
            id = 3L,
            walletAddress = "0x789",
            proxyAddress = "0xabc"
        )
        val snapshot = BridgePositionSnapshot(
            id = 3L,
            bridgeId = "polymtrade-bridge",
            walletAddress = "0x789",
            marketTitle = "Will Italy win?",
            side = "YES",
            quantity = BigDecimal("4.00000000"),
            currentValue = BigDecimal("3.00000000"),
            pnl = BigDecimal("1.00000000"),
            percentPnl = null
        )
        `when`(snapshotRepository.findByBridgeIdAndWalletAddress("polymtrade-bridge", "0x789"))
            .thenReturn(listOf(snapshot))

        val positions = service.getSnapshotPositionsForAccount(account)

        assertEquals(1, positions.size)
        val dto = positions.first()
        // initialValue = 3 - 1 = 2; percentPnl = 1 / 2 * 100 = 50
        assertEquals("50.00", dto.percentPnl)
    }
}
