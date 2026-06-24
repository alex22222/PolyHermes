package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchScannerPoolImportRequest
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.entity.LeaderScannerCandidatePool
import com.wrbug.polymarketbot.enums.LeaderCandidateProvenance
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import com.wrbug.polymarketbot.repository.LeaderScannerCandidatePoolRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import org.springframework.data.domain.PageImpl
import org.springframework.data.domain.PageRequest
import org.springframework.data.domain.Pageable

class LeaderResearchScannerPoolImportServiceTest {
    private val scannerPoolRepository: LeaderScannerCandidatePoolRepository = mock()
    private val candidateRepository: LeaderResearchCandidateRepository = mock()
    private val leaderRepository: LeaderRepository = mock()
    private val eventService: LeaderResearchEventService = mock()
    private val service = LeaderResearchScannerPoolImportService(
        scannerPoolRepository = scannerPoolRepository,
        candidateRepository = candidateRepository,
        leaderRepository = leaderRepository,
        eventService = eventService
    )

    @Test
    fun `dry run previews scanner pool import without writing`() {
        val wallet = "0x1111111111111111111111111111111111111111"
        Mockito.`when`(
            scannerPoolRepository.findByCategoryAndAnalysisStateOrderByDiscoveryScoreDesc(
                eqString("politics"),
                eqString("PENDING"),
                anyPageable()
            )
        ).thenReturn(PageImpl(listOf(poolCandidate(1L, "politics", wallet, 90))))
        Mockito.`when`(candidateRepository.findByNormalizedWallet(wallet)).thenReturn(null)
        Mockito.`when`(leaderRepository.findByLeaderAddress(wallet)).thenReturn(null)

        val response = service.importFromScannerPool(
            LeaderResearchScannerPoolImportRequest(
                dryRun = true,
                politicsLimit = 1,
                financeLimit = 0,
                sportsLimit = 0,
                cryptoLimit = 0
            )
        )

        assertEquals(true, response.dryRun)
        assertEquals(1, response.selectedTotal)
        assertEquals(1, response.createdTotal)
        assertEquals("CREATE", response.previewItems.single().action)
        Mockito.verify(candidateRepository, Mockito.never()).save(anyCandidate())
        Mockito.verify(scannerPoolRepository, Mockito.never()).markPromoted(Mockito.anyLong(), Mockito.anyLong(), Mockito.anyLong())
    }

    @Test
    fun `import creates updates and preserves locked candidates`() {
        val newWallet = "0x1111111111111111111111111111111111111111"
        val existingWallet = "0x2222222222222222222222222222222222222222"
        val lockedWallet = "0x3333333333333333333333333333333333333333"
        Mockito.`when`(
            scannerPoolRepository.findByCategoryAndAnalysisStateOrderByDiscoveryScoreDesc(
                eqString("politics"),
                eqString("PENDING"),
                anyPageable()
            )
        ).thenReturn(
            PageImpl(
                listOf(
                    poolCandidate(1L, "politics", newWallet, 90),
                    poolCandidate(2L, "politics", existingWallet, 80),
                    poolCandidate(3L, "politics", lockedWallet, 70)
                )
            )
        )
        Mockito.`when`(candidateRepository.findByNormalizedWallet(newWallet)).thenReturn(null)
        Mockito.`when`(candidateRepository.findByNormalizedWallet(existingWallet)).thenReturn(
            LeaderResearchCandidate(
                id = 20L,
                normalizedWallet = existingWallet,
                source = "ACTIVITY_DERIVED",
                sourceEvidence = "activity"
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

        val response = service.importFromScannerPool(
            LeaderResearchScannerPoolImportRequest(
                dryRun = false,
                politicsLimit = 3,
                financeLimit = 0,
                sportsLimit = 0,
                cryptoLimit = 0
            )
        )

        assertEquals(3, response.selectedTotal)
        assertEquals(1, response.createdTotal)
        assertEquals(1, response.updatedTotal)
        assertEquals(1, response.skippedLockedTotal)
        assertTrue(response.previewItems.map { it.action }.containsAll(listOf("CREATE", "UPDATE", "SKIP_LOCKED")))
        Mockito.verify(candidateRepository, Mockito.times(2)).save(anyCandidate())
        Mockito.verify(scannerPoolRepository, Mockito.times(2)).markPromoted(Mockito.anyLong(), Mockito.anyLong(), Mockito.anyLong())
    }

    private fun poolCandidate(id: Long, category: String, wallet: String, score: Int) = LeaderScannerCandidatePool(
        id = id,
        category = category,
        normalizedWallet = wallet,
        source = "HOT_MARKET",
        sourceDetail = "slug-$id",
        discoveryScore = score
    )

    private fun anyCandidate(): LeaderResearchCandidate {
        Mockito.any(LeaderResearchCandidate::class.java)
        return LeaderResearchCandidate(normalizedWallet = "0x1111111111111111111111111111111111111111")
    }

    private fun eqString(value: String): String {
        Mockito.eq(value)
        return value
    }

    private fun anyPageable(): Pageable {
        Mockito.any(Pageable::class.java)
        return PageRequest.of(0, 1)
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
