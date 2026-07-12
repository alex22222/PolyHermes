package com.wrbug.polymarketbot.service.accounts

import com.google.gson.Gson
import com.wrbug.polymarketbot.entity.*
import com.wrbug.polymarketbot.repository.*
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class PortfolioExposureServiceTest {
    private val snapshotRepository = Mockito.mock(BridgePositionSnapshotRepository::class.java)
    private val currentRepository = Mockito.mock(CurrentAssetValuationRepository::class.java)
    private val accountRepository = Mockito.mock(AccountRepository::class.java)
    private val marketRepository = Mockito.mock(MarketRepository::class.java)
    private val tradeRepository = Mockito.mock(BridgeTradeRecordRepository::class.java)
    private val leaderRepository = Mockito.mock(LeaderRepository::class.java)
    private val service = PortfolioExposureService(
        snapshotRepository,
        currentRepository,
        accountRepository,
        marketRepository,
        tradeRepository,
        leaderRepository,
        Gson()
    )

    @Test
    fun `aggregates account leader category and event with explicit unknown buckets`() {
        val wallet = "0xabc"
        val account = Account(id = 2, walletAddress = wallet, proxyAddress = "0xproxy", accountName = "Bridge")
        val known = snapshot("market-1", "Finance market", "YES", "30", "event-1").copy(
            pnl = BigDecimal("5"), createdAt = 100L
        )
        val unknown = snapshot("market-2", "Mystery market", "NO", "20", null).copy(
            pnl = BigDecimal("-2"), createdAt = 200L
        )
        val leaderAddress = "0x1111111111111111111111111111111111111111"

        Mockito.`when`(accountRepository.findById(2L)).thenReturn(java.util.Optional.of(account))
        Mockito.`when`(snapshotRepository.findByBridgeIdAndWalletAddress("polymtrade-bridge", wallet))
            .thenReturn(listOf(known, unknown))
        Mockito.`when`(currentRepository.findByBridgeIdAndWalletAddress("polymtrade-bridge", wallet))
            .thenReturn(current(wallet, "100"))
        Mockito.`when`(marketRepository.findByMarketId("market-1"))
            .thenReturn(Market(marketId = "market-1", title = "Finance market", category = "finance"))
        Mockito.`when`(marketRepository.findByMarketId("market-2")).thenReturn(null)
        Mockito.`when`(tradeRepository.findByBridgeIdAndStatus("polymtrade-bridge", "SUCCESS"))
            .thenReturn(listOf(trade("market-1", "Finance market", "YES", leaderAddress, "9.98")))
        Mockito.`when`(leaderRepository.findLatestByLeaderAddressIn(listOf(leaderAddress)))
            .thenReturn(listOf(Leader(id = 8, leaderAddress = leaderAddress, leaderName = "Leader A")))

        val result = service.getExposure(2L)

        assertEquals("50", result.account.openPositionsValue)
        assertEquals("47", result.account.positionCostBasis)
        assertEquals("3", result.account.unrealizedPnl)
        assertEquals(100L, result.account.firstObservedAt)
        assertEquals("30", result.leaders.first { it.key == leaderAddress }.value)
        assertEquals("20", result.leaders.first { it.key == "UNKNOWN" }.value)
        assertEquals("30", result.categories.first { it.key == "finance" }.value)
        assertEquals("20", result.categories.first { it.key == "UNKNOWN" }.value)
        assertEquals("30", result.events.first { it.key == "event-1" }.value)
        assertEquals("20", result.events.first { it.key.startsWith("UNKNOWN:") }.value)
        assertEquals("TRADE_LEDGER", result.leaders.first { it.key == leaderAddress }.attributionSource)
        assertEquals(8L, result.leaders.first { it.key == leaderAddress }.leaderId)
        assertEquals(null, result.leaders.first { it.key == "UNKNOWN" }.leaderId)
        assertEquals("EXACT", result.leaders.first { it.key == leaderAddress }.attributionQuality)
        assertEquals("MARKET_METADATA", result.categories.first { it.key == "finance" }.attributionSource)
        assertEquals("EXACT", result.categories.first { it.key == "finance" }.attributionQuality)
        assertEquals("TITLE_PATTERN", result.categories.first { it.key == "UNKNOWN" }.attributionSource)
        assertEquals("UNKNOWN", result.categories.first { it.key == "UNKNOWN" }.attributionQuality)
        assertEquals("EVENT_SLUG", result.events.first { it.key == "event-1" }.attributionSource)
        assertEquals("25", result.leaders.first { it.key == leaderAddress }.costBasis)
        assertEquals("5", result.leaders.first { it.key == leaderAddress }.unrealizedPnl)
        assertEquals(100L, result.leaders.first { it.key == leaderAddress }.firstObservedAt)
        assertEquals(listOf("market-1|YES"), result.leaders.first { it.key == leaderAddress }.positionKeys)
        assertEquals("22", result.categories.first { it.key == "UNKNOWN" }.costBasis)
        assertEquals("-2", result.categories.first { it.key == "UNKNOWN" }.unrealizedPnl)
        assertEquals(200L, result.categories.first { it.key == "UNKNOWN" }.firstObservedAt)
        assertEquals(1, result.coverage.unknownLeaderPositions)
        assertEquals(1, result.coverage.unknownCategoryPositions)
        assertEquals(1, result.coverage.unknownEventPositions)
        assertEquals("60", result.coverage.leader.knownValueCoveragePercent)
        assertEquals("30", result.coverage.leader.knownValue)
        assertEquals("20", result.coverage.leader.unknownValue)
        assertEquals("INSUFFICIENT_ATTRIBUTION", result.coverage.leader.status)
        assertEquals(false, result.coverage.leader.shadowEligible)
        assertEquals("60", result.coverage.category.knownValueCoveragePercent)
        assertEquals("60", result.coverage.event.knownValueCoveragePercent)
    }

    @Test
    fun `value coverage reaches shadow eligibility only at configured threshold`() {
        val wallet = "0xabc"
        val account = Account(id = 2, walletAddress = wallet, proxyAddress = "0xproxy", accountName = "Bridge")
        val known = snapshot("market-1", "Bitcoin market", "YES", "95", "event-1")
        val unknown = snapshot("market-2", "Mystery market", "NO", "5", null)
        val leaderAddress = "0x1111111111111111111111111111111111111111"

        Mockito.`when`(accountRepository.findById(2L)).thenReturn(java.util.Optional.of(account))
        Mockito.`when`(snapshotRepository.findByBridgeIdAndWalletAddress("polymtrade-bridge", wallet))
            .thenReturn(listOf(known, unknown))
        Mockito.`when`(currentRepository.findByBridgeIdAndWalletAddress("polymtrade-bridge", wallet))
            .thenReturn(current(wallet, "150"))
        Mockito.`when`(marketRepository.findByMarketId("market-1"))
            .thenReturn(Market(marketId = "market-1", title = "Bitcoin market", category = "crypto"))
        Mockito.`when`(marketRepository.findByMarketId("market-2")).thenReturn(null)
        Mockito.`when`(tradeRepository.findByBridgeIdAndStatus("polymtrade-bridge", "SUCCESS"))
            .thenReturn(listOf(trade("market-1", "Bitcoin market", "YES", leaderAddress, "10")))
        Mockito.`when`(leaderRepository.findLatestByLeaderAddressIn(listOf(leaderAddress))).thenReturn(emptyList())

        val result = service.getExposure(2L)

        assertEquals("95", result.coverage.leader.knownValueCoveragePercent)
        assertEquals("READY_FOR_SHADOW", result.coverage.leader.status)
        assertEquals(true, result.coverage.leader.shadowEligible)
        assertEquals("95", result.coverage.category.knownValueCoveragePercent)
        assertEquals(true, result.coverage.category.shadowEligible)
        assertEquals("95", result.coverage.event.knownValueCoveragePercent)
        assertEquals(true, result.coverage.event.shadowEligible)
    }

    @Test
    fun `unknown position valuation blocks shadow eligibility regardless of attribution`() {
        val wallet = "0xabc"
        val account = Account(id = 2, walletAddress = wallet, proxyAddress = "0xproxy", accountName = "Bridge")
        val unknownValue = snapshot("market-1", "Bitcoin market", "YES", "10", "event-1").copy(currentValue = null)
        val leaderAddress = "0x1111111111111111111111111111111111111111"

        Mockito.`when`(accountRepository.findById(2L)).thenReturn(java.util.Optional.of(account))
        Mockito.`when`(snapshotRepository.findByBridgeIdAndWalletAddress("polymtrade-bridge", wallet))
            .thenReturn(listOf(unknownValue))
        Mockito.`when`(currentRepository.findByBridgeIdAndWalletAddress("polymtrade-bridge", wallet))
            .thenReturn(current(wallet, "50").copy(totalAssets = null, unknownPositionCount = 1, valuationStatus = "INCOMPLETE"))
        Mockito.`when`(marketRepository.findByMarketId("market-1"))
            .thenReturn(Market(marketId = "market-1", title = "Bitcoin market", category = "crypto"))
        Mockito.`when`(tradeRepository.findByBridgeIdAndStatus("polymtrade-bridge", "SUCCESS"))
            .thenReturn(listOf(trade("market-1", "Bitcoin market", "YES", leaderAddress, "10")))
        Mockito.`when`(leaderRepository.findLatestByLeaderAddressIn(listOf(leaderAddress))).thenReturn(emptyList())

        val result = service.getExposure(2L)

        assertEquals("VALUATION_INCOMPLETE", result.coverage.leader.status)
        assertEquals(false, result.coverage.leader.shadowEligible)
        assertEquals("VALUATION_INCOMPLETE", result.coverage.category.status)
        assertEquals(false, result.coverage.category.shadowEligible)
        assertEquals("VALUATION_INCOMPLETE", result.coverage.event.status)
        assertEquals(false, result.coverage.event.shadowEligible)
    }

    @Test
    fun `missing pnl keeps bucket cost and pnl unknown instead of treating them as zero`() {
        val wallet = "0xabc"
        val account = Account(id = 2, walletAddress = wallet, proxyAddress = "0xproxy", accountName = "Bridge")
        val position = snapshot("market-1", "Bitcoin market", "YES", "10", "event-1")

        Mockito.`when`(accountRepository.findById(2L)).thenReturn(java.util.Optional.of(account))
        Mockito.`when`(snapshotRepository.findByBridgeIdAndWalletAddress("polymtrade-bridge", wallet)).thenReturn(listOf(position))
        Mockito.`when`(currentRepository.findByBridgeIdAndWalletAddress("polymtrade-bridge", wallet)).thenReturn(current(wallet, "60"))
        Mockito.`when`(marketRepository.findByMarketId("market-1"))
            .thenReturn(Market(marketId = "market-1", title = "Bitcoin market", category = "crypto"))
        Mockito.`when`(tradeRepository.findByBridgeIdAndStatus("polymtrade-bridge", "SUCCESS")).thenReturn(emptyList())

        val result = service.getExposure(2L)

        assertEquals(null, result.categories.single().costBasis)
        assertEquals(null, result.categories.single().unrealizedPnl)
        assertEquals(listOf("market-1|YES"), result.categories.single().positionKeys)
        assertEquals(null, result.account.positionCostBasis)
        assertEquals(null, result.account.unrealizedPnl)
    }

    private fun snapshot(marketId: String, title: String, side: String, value: String, eventSlug: String?) =
        BridgePositionSnapshot(
            bridgeId = "polymtrade-bridge",
            walletAddress = "0xabc",
            marketId = marketId,
            marketTitle = title,
            side = side,
            quantity = BigDecimal.TEN,
            currentValue = BigDecimal(value),
            eventSlug = eventSlug
        )

    private fun current(wallet: String, total: String) = CurrentAssetValuation(
        bridgeId = "polymtrade-bridge",
        walletAddress = wallet,
        availableBalance = BigDecimal("50"),
        positionsValue = BigDecimal("50"),
        pendingRedeemValue = BigDecimal.ZERO,
        redeemablePositionCount = 0,
        redeemValuationStatus = "COMPLETE",
        totalAssets = BigDecimal(total),
        unknownPositionCount = 0,
        valuationStatus = "COMPLETE",
        capturedAt = 1000L
    )

    private fun trade(marketId: String, title: String, outcome: String, leaderAddress: String, quantity: String) = BridgeTradeRecord(
        bridgeId = "polymtrade-bridge",
        marketId = marketId,
        marketTitle = title,
        side = "BUY",
        outcome = outcome,
        quantity = BigDecimal(quantity),
        price = BigDecimal("0.5"),
        amount = BigDecimal("5"),
        status = "SUCCESS",
        rawPayload = "{\"leaderAddress\":\"$leaderAddress\"}"
    )
}
