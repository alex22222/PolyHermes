package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportItemDto
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportRequest
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.enums.LeaderCandidateProvenance
import com.wrbug.polymarketbot.repository.LeaderRepository
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito

class LeaderResearchExternalAnalyticsImportServiceTest {
    private val candidateRepository: LeaderResearchCandidateRepository = mock()
    private val leaderRepository: LeaderRepository = mock()
    private val eventService: LeaderResearchEventService = mock()
    private val service = LeaderResearchExternalAnalyticsImportService(
        candidateRepository = candidateRepository,
        leaderRepository = leaderRepository,
        eventService = eventService
    )

    @Test
    fun `dry run previews external analytics candidates without writing`() {
        val wallet = "0x1111111111111111111111111111111111111111"
        Mockito.`when`(candidateRepository.findByNormalizedWallet(wallet)).thenReturn(null)
        Mockito.`when`(leaderRepository.findByLeaderAddress(wallet)).thenReturn(null)

        val response = service.importFromExternalAnalytics(
            LeaderResearchExternalAnalyticsImportRequest(
                dryRun = true,
                items = listOf(externalItem(wallet, "politics", "polyburg", 1, "92.5"))
            )
        )

        assertEquals(true, response.dryRun)
        assertEquals(1, response.selectedTotal)
        assertEquals(1, response.createdTotal)
        assertEquals("CREATE", response.previewItems.single().action)
        assertTrue(response.previewItems.single().sourceEvidence.contains("external_analytics:polyburg"))
        Mockito.verify(candidateRepository, Mockito.never()).save(anyCandidate())
    }

    @Test
    fun `import creates updates and skips invalid locked and unchanged candidates`() {
        val newWallet = "0x1111111111111111111111111111111111111111"
        val existingWallet = "0x2222222222222222222222222222222222222222"
        val lockedWallet = "0x3333333333333333333333333333333333333333"
        val unchangedWallet = "0x4444444444444444444444444444444444444444"
        val unchangedEvidence = "external_analytics:polyburg | category:finance | rank:4 | external_score:77"

        Mockito.`when`(candidateRepository.findByNormalizedWallet(newWallet)).thenReturn(null)
        Mockito.`when`(candidateRepository.findByNormalizedWallet(existingWallet)).thenReturn(
            LeaderResearchCandidate(id = 20L, normalizedWallet = existingWallet, source = "SCANNER_POOL,ACTIVITY_SOURCE,MARKET_PEER_SOURCE")
        )
        Mockito.`when`(candidateRepository.findByNormalizedWallet(lockedWallet)).thenReturn(
            LeaderResearchCandidate(
                id = 30L,
                normalizedWallet = lockedWallet,
                source = "MANUAL",
                locked = true,
                provenance = LeaderCandidateProvenance.MANUAL_LOCKED
            )
        )
        Mockito.`when`(candidateRepository.findByNormalizedWallet(unchangedWallet)).thenReturn(
            LeaderResearchCandidate(
                id = 40L,
                normalizedWallet = unchangedWallet,
                source = "EXTERNAL_ANALYTICS_SOURCE",
                sourceEvidence = unchangedEvidence,
                lastSourceSeenAt = System.currentTimeMillis()
            )
        )
        Mockito.`when`(leaderRepository.findByLeaderAddress(Mockito.anyString())).thenReturn(null)
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer {
            val candidate = it.arguments[0] as LeaderResearchCandidate
            assertTrue(candidate.source.length <= 50)
            candidate.copy(id = candidate.id ?: 100L)
        }

        val response = service.importFromExternalAnalytics(
            LeaderResearchExternalAnalyticsImportRequest(
                dryRun = false,
                items = listOf(
                    externalItem(newWallet, "politics", "polyburg", 1, "92"),
                    externalItem(existingWallet, "finance", "polyburg", 2, "88"),
                    externalItem(lockedWallet, "finance", "polyburg", 3, "80"),
                    externalItem(unchangedWallet, "finance", "polyburg", 4, "77"),
                    externalItem("not-a-wallet", "finance", "polyburg", 5, "70")
                )
            )
        )

        assertEquals(4, response.selectedTotal)
        assertEquals(1, response.createdTotal)
        assertEquals(1, response.updatedTotal)
        assertEquals(1, response.skippedLockedTotal)
        assertEquals(1, response.skippedExistingTotal)
        assertEquals(1, response.skippedInvalidTotal)
        assertTrue(response.previewItems.map { it.action }.containsAll(listOf("CREATE", "UPDATE", "SKIP_LOCKED", "SKIP_EXISTING", "SKIP_INVALID")))
        Mockito.verify(candidateRepository, Mockito.times(2)).save(anyCandidate())
    }

    @Test
    fun `import refreshes stale exact evidence without appending duplicate source evidence`() {
        val wallet = "0x5555555555555555555555555555555555555555"
        val evidence = "external_analytics:polymarket_official_leaderboard | category:politics | rank:12 | external_score:88"
        Mockito.`when`(candidateRepository.findByNormalizedWallet(wallet)).thenReturn(
            LeaderResearchCandidate(
                id = 50L,
                normalizedWallet = wallet,
                source = "EXTERNAL_ANALYTICS_SOURCE",
                sourceEvidence = evidence,
                lastSourceSeenAt = System.currentTimeMillis() - 2L * 60 * 60 * 1000
            )
        )
        Mockito.`when`(leaderRepository.findByLeaderAddress(wallet)).thenReturn(null)
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }

        val response = service.importFromExternalAnalytics(
            LeaderResearchExternalAnalyticsImportRequest(
                dryRun = false,
                items = listOf(externalItem(wallet, "politics", "polymarket_official_leaderboard", 12, "88"))
            )
        )

        assertEquals(1, response.updatedTotal)
        assertEquals(0, response.skippedExistingTotal)
        assertEquals("REFRESH", response.previewItems.single().action)
        val saved = captureSavedCandidates().single()
        assertEquals(evidence, saved.sourceEvidence)
        assertTrue(saved.lastSourceSeenAt!! > System.currentTimeMillis() - 60_000L)
    }

    private fun externalItem(
        wallet: String,
        category: String,
        sourceName: String,
        rank: Int,
        score: String
    ) = LeaderResearchExternalAnalyticsImportItemDto(
        wallet = wallet,
        category = category,
        sourceName = sourceName,
        externalRank = rank,
        externalScore = score
    )

    private fun anyCandidate(): LeaderResearchCandidate {
        Mockito.any(LeaderResearchCandidate::class.java)
        return LeaderResearchCandidate(normalizedWallet = "0x1111111111111111111111111111111111111111")
    }

    private fun captureSavedCandidates(): List<LeaderResearchCandidate> {
        val captor = org.mockito.ArgumentCaptor.forClass(LeaderResearchCandidate::class.java)
        Mockito.verify(candidateRepository, Mockito.atLeastOnce()).save(captor.capture())
        return captor.allValues
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)
}
