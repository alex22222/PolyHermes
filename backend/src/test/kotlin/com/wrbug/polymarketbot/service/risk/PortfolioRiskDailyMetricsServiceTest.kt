package com.wrbug.polymarketbot.service.risk

import com.wrbug.polymarketbot.entity.DailyAssetSnapshot
import com.wrbug.polymarketbot.repository.DailyAssetSnapshotRepository
import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal
import java.time.LocalDate
import java.time.ZoneId

class PortfolioRiskDailyMetricsServiceTest {
    private val repository = Mockito.mock(DailyAssetSnapshotRepository::class.java)
    private val tradeRepository = Mockito.mock(BridgeTradeRecordRepository::class.java)
    private val service = PortfolioRiskDailyMetricsService(repository, tradeRepository)

    @Test
    fun `calculates daily loss from complete local-day asset baseline`() {
        val zone = ZoneId.of("Asia/Shanghai")
        val dayStart = LocalDate.of(2026, 7, 11).atStartOfDay(zone).toInstant().toEpochMilli()
        Mockito.`when`(repository.findByBridgeIdAndWalletAddressOrderByDayStartAtAsc("polymtrade-bridge", "0xwallet"))
            .thenReturn(listOf(snapshot(dayStart, "100")))
        Mockito.`when`(tradeRepository.countScopedSuccessBuysSince("polymtrade-bridge", 2, dayStart)).thenReturn(4)
        Mockito.`when`(tradeRepository.countUnscopedSuccessBuysSince("polymtrade-bridge", dayStart)).thenReturn(0)

        val result = service.calculate(2, "0xWallet", BigDecimal("94"), dayStart + 3_600_000)

        assertEquals(BigDecimal("6.0000"), result.lossPercent)
        assertEquals("MIDNIGHT", result.baselineType)
        assertEquals(4, result.successfulBuyCount)
        assertEquals(true, result.orderCountComplete)
    }

    @Test
    fun `incomplete baseline leaves daily loss unknown`() {
        val zone = ZoneId.of("Asia/Shanghai")
        val dayStart = LocalDate.of(2026, 7, 11).atStartOfDay(zone).toInstant().toEpochMilli()
        Mockito.`when`(repository.findByBridgeIdAndWalletAddressOrderByDayStartAtAsc("polymtrade-bridge", "0xwallet"))
            .thenReturn(listOf(snapshot(dayStart, "100").copy(valuationStatus = "INCOMPLETE")))

        val result = service.calculate(2, "0xwallet", BigDecimal("94"), dayStart + 1)

        assertEquals(null, result.lossPercent)
    }

    private fun snapshot(dayStart: Long, total: String) = DailyAssetSnapshot(
        bridgeId = "polymtrade-bridge",
        walletAddress = "0xwallet",
        dayStartAt = dayStart,
        availableBalance = BigDecimal("20"),
        positionsValue = BigDecimal("80"),
        pendingRedeemValue = BigDecimal.ZERO,
        redeemablePositionCount = 0,
        redeemValuationStatus = "COMPLETE",
        totalAssets = BigDecimal(total),
        valuationStatus = "COMPLETE",
        snapshotType = "MIDNIGHT",
        captureOffsetMs = 0,
        capturedAt = dayStart
    )
}
