package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchMarketPeerSourceImportRequest
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.repository.LeaderActivityEventRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.repository.LeaderResearchMarketPeerSourceProjection
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class LeaderResearchMarketPeerSourceImportServiceTest {
    private val activityEventRepository: LeaderActivityEventRepository = mock()
    private val candidateRepository: LeaderResearchCandidateRepository = mock()
    private val leaderRepository: LeaderRepository = mock()
    private val eventService: LeaderResearchEventService = mock()
    private val service = LeaderResearchMarketPeerSourceImportService(
        activityEventRepository = activityEventRepository,
        candidateRepository = candidateRepository,
        leaderRepository = leaderRepository,
        eventService = eventService
    )

    @Test
    fun `targeted import only scans requested wallets`() {
        val requestedWallet = "0x8888888888888888888888888888888888888888"
        Mockito.`when`(
            activityEventRepository.discoverWalletsFromMarketPeerSourceForWallets(
                Mockito.eq(listOf(requestedWallet)) ?: emptyList(),
                Mockito.anyLong(),
                Mockito.anyString(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                anyBigDecimal(),
                anyBigDecimal()
            )
        ).thenReturn(listOf(marketPeerSource(requestedWallet)))
        Mockito.`when`(candidateRepository.findByNormalizedWallet(requestedWallet)).thenReturn(null)
        Mockito.`when`(leaderRepository.findByLeaderAddress(requestedWallet)).thenReturn(null)

        val response = service.importFromMarketPeerSource(
            LeaderResearchMarketPeerSourceImportRequest(
                dryRun = true,
                categories = listOf("politics"),
                wallets = listOf(requestedWallet, "not-a-wallet"),
                limitPerCategory = 10
            )
        )

        assertEquals(1, response.selectedTotal)
        assertEquals(1, response.createdTotal)
        assertEquals(requestedWallet, response.previewItems.single().wallet)
        Mockito.verify(activityEventRepository, Mockito.never()).discoverWalletsFromMarketPeerSource(
            Mockito.anyLong(),
            Mockito.anyString(),
            Mockito.anyInt(),
            Mockito.anyInt(),
            Mockito.anyInt(),
            Mockito.anyInt(),
            Mockito.anyInt(),
            Mockito.anyInt(),
            Mockito.anyInt(),
            anyBigDecimal(),
            anyBigDecimal(),
            Mockito.anyInt()
        )
    }

    private fun marketPeerSource(wallet: String) = object : LeaderResearchMarketPeerSourceProjection {
        override fun getNormalizedWallet(): String = wallet
        override fun getTotalEvents(): Long = 24
        override fun getDistinctMarkets(): Long = 6
        override fun getBuyEvents(): Long = 18
        override fun getSellEvents(): Long = 6
        override fun getSafePriceEvents(): Long = 14
        override fun getTailPriceEvents(): Long = 2
        override fun getAvgAmount(): BigDecimal = BigDecimal("3.25")
        override fun getTotalAmount(): BigDecimal = BigDecimal("78.00")
        override fun getLastEventTime(): Long = 1782284401000
        override fun getTopMarkets(): String = "market-a,market-b"
    }

    private fun anyBigDecimal(): BigDecimal {
        Mockito.any(BigDecimal::class.java)
        return BigDecimal.ZERO
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
