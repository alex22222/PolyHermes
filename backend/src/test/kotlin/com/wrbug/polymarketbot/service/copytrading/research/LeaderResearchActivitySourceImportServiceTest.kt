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
