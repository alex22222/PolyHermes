package com.wrbug.polymarketbot.service.risk

import com.google.gson.Gson
import com.wrbug.polymarketbot.dto.PortfolioRiskHistoricalReplayRequest
import com.wrbug.polymarketbot.entity.Account
import com.wrbug.polymarketbot.entity.BridgeTradeRecord
import com.wrbug.polymarketbot.entity.CurrentAssetValuation
import com.wrbug.polymarketbot.entity.DailyAssetSnapshot
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import com.wrbug.polymarketbot.repository.CurrentAssetValuationRepository
import com.wrbug.polymarketbot.repository.DailyAssetSnapshotRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.util.Optional

class PortfolioRiskHistoricalReplayServiceTest {
    private val accounts = Mockito.mock(AccountRepository::class.java)
    private val trades = Mockito.mock(BridgeTradeRecordRepository::class.java)
    private val daily = Mockito.mock(DailyAssetSnapshotRepository::class.java)
    private val current = Mockito.mock(CurrentAssetValuationRepository::class.java)
    private val service = PortfolioRiskHistoricalReplayService(accounts, trades, daily, current, Gson())

    @Test
    fun `report separates scoped executions and refuses unavailable settlement pnl`() {
        Mockito.`when`(accounts.findById(2)).thenReturn(Optional.of(Account(id = 2, walletAddress = "0xwallet", proxyAddress = "0xproxy")))
        Mockito.`when`(trades.findByBridgeId("polymtrade-bridge")).thenReturn(listOf(
            record("BUY", "SUCCESS", "{\"copyTradingAccountId\":2}"),
            record("BUY", "FAILED", "{\"copyTradingAccountId\":2}", "BUY skipped: price band"),
            record("SELL", "SUCCESS", "{\"copyTradingAccountId\":2}"),
            record("SELL", "FAILED", "{\"copyTradingAccountId\":2}", "Insufficient position"),
            record("BUY", "SUCCESS", "{}")
        ))
        Mockito.`when`(daily.findByBridgeIdAndWalletAddressOrderByDayStartAtAsc("polymtrade-bridge", "0xwallet")).thenReturn(listOf(
            snapshot(100, 1_000), snapshot(80, 2_000)
        ))
        Mockito.`when`(current.findByBridgeIdAndWalletAddress("polymtrade-bridge", "0xwallet")).thenReturn(
            CurrentAssetValuation(bridgeId = "polymtrade-bridge", walletAddress = "0xwallet", availableBalance = 45.toBigDecimal(), positionsValue = 45.toBigDecimal(), pendingRedeemValue = 0.toBigDecimal(), redeemablePositionCount = 0, redeemValuationStatus = "COMPLETE", totalAssets = 90.toBigDecimal(), unknownPositionCount = 0, valuationStatus = "COMPLETE", capturedAt = 3_000)
        )

        val report = service.generate(PortfolioRiskHistoricalReplayRequest(2, 0), 4_000)

        assertEquals(4, report.scopedBridgeRecords)
        assertEquals(1, report.unscopedBridgeRecords)
        assertEquals(1, report.buySuccess)
        assertEquals(1, report.buyFailed)
        assertEquals(1, report.sellSuccess)
        assertEquals(1, report.sellFailed)
        assertEquals(1, report.failureTaxonomy["RISK_FILTER"])
        assertEquals("50", report.metrics.first { it.code == "SELL_COMPLETION_RATE" }.value)
        assertEquals("20", report.metrics.first { it.code == "MAX_DRAWDOWN" }.value)
        assertEquals("50", report.metrics.first { it.code == "CURRENT_CAPITAL_UTILIZATION" }.value)
        assertEquals("UNAVAILABLE", report.metrics.first { it.code == "REALIZED_PNL" }.status)
        assertTrue(report.blockers.any { it.startsWith("REALIZED_PNL") })
    }

    private fun record(side: String, status: String, raw: String, error: String? = null) = BridgeTradeRecord(
        bridgeId = "polymtrade-bridge", marketId = "market", side = side, quantity = 1.toBigDecimal(), price = 1.toBigDecimal(), amount = 1.toBigDecimal(), status = status, rawPayload = raw, errorMessage = error, createdAt = 100
    )

    private fun snapshot(total: Int, day: Long) = DailyAssetSnapshot(
        bridgeId = "polymtrade-bridge", walletAddress = "0xwallet", dayStartAt = day,
        availableBalance = total.toBigDecimal(), positionsValue = 0.toBigDecimal(), pendingRedeemValue = 0.toBigDecimal(), redeemablePositionCount = 0,
        redeemValuationStatus = "COMPLETE", totalAssets = total.toBigDecimal(), capturedAt = day
    )
}
