package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceImportRequest
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderCandidateProvenance
import com.wrbug.polymarketbot.repository.LeaderActivityEventRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.repository.LeaderResearchActivitySourceProjection
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class LeaderResearchActivitySourceImportServiceTest {
    private val activityEventRepository: LeaderActivityEventRepository = mock()
    private val candidateRepository: LeaderResearchCandidateRepository = mock()
    private val leaderRepository: LeaderRepository = mock()
    private val eventService: LeaderResearchEventService = mock()
    private val service = LeaderResearchActivitySourceImportService(
        activityEventRepository = activityEventRepository,
        candidateRepository = candidateRepository,
        leaderRepository = leaderRepository,
        eventService = eventService
    )

    @Test
    fun `dry run previews activity source candidates without writing`() {
        val wallet = "0x1111111111111111111111111111111111111111"
        Mockito.`when`(
            activityEventRepository.discoverWalletsFromActivitySource(
                Mockito.anyLong(),
                Mockito.anyString(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                anyBigDecimal(),
                anyBigDecimal(),
                Mockito.anyInt()
            )
        ).thenReturn(listOf(activitySource(wallet)))
        Mockito.`when`(candidateRepository.findByNormalizedWallet(wallet)).thenReturn(null)
        Mockito.`when`(leaderRepository.findByLeaderAddress(wallet)).thenReturn(null)

        val response = service.importFromActivitySource(
            LeaderResearchActivitySourceImportRequest(
                dryRun = true,
                categories = listOf("politics"),
                limitPerCategory = 1
            )
        )

        assertEquals(true, response.dryRun)
        assertEquals(1, response.selectedTotal)
        assertEquals(1, response.createdTotal)
        assertEquals("CREATE", response.previewItems.single().action)
        assertTrue(response.previewItems.single().sourceEvidence.contains("activity_source:politics"))
        Mockito.verify(candidateRepository, Mockito.never()).save(anyCandidate())
    }

    @Test
    fun `import creates updates and skips locked candidates`() {
        val newWallet = "0x1111111111111111111111111111111111111111"
        val existingWallet = "0x2222222222222222222222222222222222222222"
        val lockedWallet = "0x3333333333333333333333333333333333333333"
        Mockito.`when`(
            activityEventRepository.discoverWalletsFromActivitySource(
                Mockito.anyLong(),
                Mockito.anyString(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                anyBigDecimal(),
                anyBigDecimal(),
                Mockito.anyInt()
            )
        ).thenReturn(
            listOf(
                activitySource(newWallet),
                activitySource(existingWallet),
                activitySource(lockedWallet)
            )
        )
        Mockito.`when`(candidateRepository.findByNormalizedWallet(newWallet)).thenReturn(null)
        Mockito.`when`(candidateRepository.findByNormalizedWallet(existingWallet)).thenReturn(
            LeaderResearchCandidate(
                id = 20L,
                normalizedWallet = existingWallet,
                source = "SCANNER_POOL",
                sourceEvidence = "scanner_pool:1 | category:politics"
            )
        )
        Mockito.`when`(candidateRepository.findByNormalizedWallet(lockedWallet)).thenReturn(
            LeaderResearchCandidate(
                id = 30L,
                normalizedWallet = lockedWallet,
                locked = true,
                provenance = LeaderCandidateProvenance.MANUAL_LOCKED,
                source = "manual"
            )
        )
        Mockito.`when`(leaderRepository.findByLeaderAddress(Mockito.anyString())).thenReturn(null)
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer {
            val candidate = it.arguments[0] as LeaderResearchCandidate
            candidate.copy(id = candidate.id ?: 100L)
        }

        val response = service.importFromActivitySource(
            LeaderResearchActivitySourceImportRequest(
                dryRun = false,
                categories = listOf("politics"),
                limitPerCategory = 3
            )
        )

        assertEquals(3, response.selectedTotal)
        assertEquals(1, response.createdTotal)
        assertEquals(1, response.updatedTotal)
        assertEquals(1, response.skippedLockedTotal)
        assertTrue(response.previewItems.map { it.action }.containsAll(listOf("CREATE", "UPDATE", "SKIP_LOCKED")))
        Mockito.verify(candidateRepository, Mockito.times(2)).save(anyCandidate())
    }

    @Test
    fun `import refreshes existing activity source candidate when evidence changes`() {
        val wallet = "0x4444444444444444444444444444444444444444"
        Mockito.`when`(
            activityEventRepository.discoverWalletsFromActivitySource(
                Mockito.anyLong(),
                Mockito.anyString(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                anyBigDecimal(),
                anyBigDecimal(),
                Mockito.anyInt()
            )
        ).thenReturn(listOf(activitySource(wallet)))
        Mockito.`when`(candidateRepository.findByNormalizedWallet(wallet)).thenReturn(
            LeaderResearchCandidate(
                id = 40L,
                normalizedWallet = wallet,
                source = "ACTIVITY_SOURCE",
                sourceEvidence = "activity_source:politics | category:politics | events:1 | markets:1"
            )
        )
        Mockito.`when`(leaderRepository.findByLeaderAddress(wallet)).thenReturn(null)
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }

        val response = service.importFromActivitySource(
            LeaderResearchActivitySourceImportRequest(
                dryRun = false,
                categories = listOf("politics"),
                limitPerCategory = 1
            )
        )

        assertEquals(1, response.selectedTotal)
        assertEquals(1, response.updatedTotal)
        assertEquals(0, response.skippedExistingTotal)
        assertEquals("UPDATE", response.previewItems.single().action)
        Mockito.verify(candidateRepository).save(anyCandidate())
    }

    @Test
    fun `import skips existing activity source candidate when evidence is unchanged`() {
        val wallet = "0x5555555555555555555555555555555555555555"
        val source = activitySource(wallet)
        val evidence = "activity_source:politics | category:politics | events:24 | markets:6 | buy_events:18 | sell_events:6 | safe_price_ratio:0.5833 | tail_price_ratio:0.0833 | avg_amount:3.2500 | total_amount:78.0000 | last_event_time:1782284401000"
        Mockito.`when`(
            activityEventRepository.discoverWalletsFromActivitySource(
                Mockito.anyLong(),
                Mockito.anyString(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                anyBigDecimal(),
                anyBigDecimal(),
                Mockito.anyInt()
            )
        ).thenReturn(listOf(source))
        Mockito.`when`(candidateRepository.findByNormalizedWallet(wallet)).thenReturn(
            LeaderResearchCandidate(
                id = 50L,
                normalizedWallet = wallet,
                source = "ACTIVITY_SOURCE",
                sourceEvidence = evidence
            )
        )
        Mockito.`when`(leaderRepository.findByLeaderAddress(wallet)).thenReturn(null)

        val response = service.importFromActivitySource(
            LeaderResearchActivitySourceImportRequest(
                dryRun = false,
                categories = listOf("politics"),
                limitPerCategory = 1
            )
        )

        assertEquals(1, response.selectedTotal)
        assertEquals(0, response.updatedTotal)
        assertEquals(1, response.skippedExistingTotal)
        assertEquals("SKIP_EXISTING", response.previewItems.single().action)
        Mockito.verify(candidateRepository, Mockito.never()).save(anyCandidate())
    }

    @Test
    fun `import prioritizes new wallets before unchanged existing wallets when batch is full`() {
        val existingWallet = "0x6666666666666666666666666666666666666666"
        val newWallet = "0x7777777777777777777777777777777777777777"
        val existingSource = activitySource(existingWallet)
        val newSource = activitySource(newWallet)
        val existingEvidence = "activity_source:politics | category:politics | events:24 | markets:6 | buy_events:18 | sell_events:6 | safe_price_ratio:0.5833 | tail_price_ratio:0.0833 | avg_amount:3.2500 | total_amount:78.0000 | last_event_time:1782284401000"
        Mockito.`when`(
            activityEventRepository.discoverWalletsFromActivitySource(
                Mockito.anyLong(),
                Mockito.anyString(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                Mockito.anyInt(),
                anyBigDecimal(),
                anyBigDecimal(),
                Mockito.anyInt()
            )
        ).thenReturn(listOf(existingSource, newSource))
        Mockito.`when`(candidateRepository.findByNormalizedWallet(existingWallet)).thenReturn(
            LeaderResearchCandidate(
                id = 60L,
                normalizedWallet = existingWallet,
                source = "ACTIVITY_SOURCE",
                sourceEvidence = existingEvidence
            )
        )
        Mockito.`when`(candidateRepository.findByNormalizedWallet(newWallet)).thenReturn(null)
        Mockito.`when`(leaderRepository.findByLeaderAddress(newWallet)).thenReturn(null)

        val response = service.importFromActivitySource(
            LeaderResearchActivitySourceImportRequest(
                dryRun = true,
                categories = listOf("politics"),
                limitPerCategory = 1
            )
        )

        assertEquals(1, response.selectedTotal)
        assertEquals(1, response.createdTotal)
        assertEquals(newWallet, response.previewItems.single().wallet)
        assertEquals("CREATE", response.previewItems.single().action)
    }

    private fun activitySource(wallet: String) = object : LeaderResearchActivitySourceProjection {
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
    }

    private fun anyCandidate(): LeaderResearchCandidate {
        Mockito.any(LeaderResearchCandidate::class.java)
        return LeaderResearchCandidate(normalizedWallet = "0x1111111111111111111111111111111111111111")
    }

    private fun anyBigDecimal(): BigDecimal {
        Mockito.any(BigDecimal::class.java)
        return BigDecimal.ZERO
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
