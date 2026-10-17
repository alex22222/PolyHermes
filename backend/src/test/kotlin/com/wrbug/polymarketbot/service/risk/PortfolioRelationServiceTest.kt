package com.wrbug.polymarketbot.service.risk

import com.wrbug.polymarketbot.entity.Account
import com.wrbug.polymarketbot.entity.BridgePositionSnapshot
import com.wrbug.polymarketbot.entity.Market
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.BridgePositionSnapshotRepository
import com.wrbug.polymarketbot.repository.MarketRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal
import java.util.Optional

class PortfolioRelationServiceTest {
    @Test
    fun `positions only path preserves full graph metadata without classifying pairs`() {
        val accounts = Mockito.mock(AccountRepository::class.java)
        val snapshots = Mockito.mock(BridgePositionSnapshotRepository::class.java)
        val markets = Mockito.mock(MarketRepository::class.java)
        val classifier = Mockito.spy(PortfolioRelationClassifier())
        Mockito.`when`(accounts.findById(2L)).thenReturn(Optional.of(Account(id = 2, walletAddress = "0xWALLET", proxyAddress = "0xproxy")))
        Mockito.`when`(snapshots.findByBridgeIdAndWalletAddress("polymtrade-bridge", "0xwallet")).thenReturn(listOf(
            BridgePositionSnapshot(bridgeId = "polymtrade-bridge", marketId = "m1", marketTitle = "Democrats win Senate", side = "Yes", quantity = BigDecimal("2.000"), currentValue = BigDecimal("1.2300"), syncedAt = 42, createdAt = 1),
            BridgePositionSnapshot(bridgeId = "polymtrade-bridge", marketTitle = "Unknown", side = "No", quantity = BigDecimal.ONE, syncedAt = 41, createdAt = 2)
        ))
        Mockito.`when`(markets.findByMarketId("m1")).thenReturn(Market(marketId = "m1", title = "Democrats win Senate", category = "politics", eventSlug = "event", endDate = 100))
        val service = PortfolioRelationService(accounts, snapshots, markets, classifier)

        val positions = service.getPositions(2L)
        Mockito.verifyNoInteractions(classifier)
        val full = service.getRelations(2L, 100)

        assertEquals(42L, full.asOf)
        assertEquals(full.positions.map { it.positionKey }, positions.map { it.positionKey })
        assertEquals(full.positions.map { it.eventSlug }, positions.map { it.eventSlug })
        assertEquals(full.positions.map { it.category }, positions.map { it.category })
        assertEquals(full.positions.map { it.currentValue?.toBigDecimal() }, positions.map { it.currentValue?.stripTrailingZeros() })
        assertEquals(full.positions.map { it.firstObservedAt }, positions.map { it.firstObservedAt })
        assertEquals(full.positions.map { it.marketEndAt }, positions.map { it.marketEndAt })
        assertEquals(listOf("UNKNOWN"), full.relations.map { it.type })
    }
}
