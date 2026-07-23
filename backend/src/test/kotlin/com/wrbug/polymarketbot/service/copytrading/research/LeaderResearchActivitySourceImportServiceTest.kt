package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchActivitySourceMetricRefreshRequest
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
        val lastEventTime = 1782284401000L
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
        ).thenReturn(listOf(activitySource(wallet, lastEventTime)))
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
        val saved = captureSavedCandidates().single()
        assertEquals(lastEventTime, saved.lastSourceSeenAt)
    }

    @Test
    fun `import uses source last event time as freshness marker`() {
        val wallet = "0x9999999999999999999999999999999999999999"
        val lastEventTime = 1782400000000L
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
        ).thenReturn(listOf(activitySource(wallet, lastEventTime)))
        Mockito.`when`(candidateRepository.findByNormalizedWallet(wallet)).thenReturn(null)
        Mockito.`when`(leaderRepository.findByLeaderAddress(wallet)).thenReturn(null)
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer {
            val candidate = it.arguments[0] as LeaderResearchCandidate
            candidate.copy(id = candidate.id ?: 100L)
        }

        val response = service.importFromActivitySource(
            LeaderResearchActivitySourceImportRequest(
                dryRun = false,
                categories = listOf("politics"),
                limitPerCategory = 1
            )
        )

        assertEquals(1, response.createdTotal)
        val saved = captureSavedCandidates().single()
        assertEquals(lastEventTime, saved.lastSourceSeenAt)
    }

    @Test
    fun `import skips existing activity source candidate when evidence is unchanged`() {
        val wallet = "0x5555555555555555555555555555555555555555"
        val source = activitySource(wallet)
        val evidence = "activity_source:politics | category:politics | events:24 | markets:6 | buy_events:18 | sell_events:6 | safe_price_ratio:0.5833 | tail_price_ratio:0.0833 | avg_amount:3.2500 | total_amount:78.0000 | activity_window:30d_trades:24 | last_event_time:1782284401000"
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
                sourceEvidence = evidence,
                lastSourceSeenAt = source.getLastEventTime()
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
    fun `import skips unchanged evidence when existing freshness is newer than activity`() {
        val wallet = "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        val source = activitySource(wallet)
        val evidence = "activity_source:politics | category:politics | events:24 | markets:6 | buy_events:18 | sell_events:6 | safe_price_ratio:0.5833 | tail_price_ratio:0.0833 | avg_amount:3.2500 | total_amount:78.0000 | activity_window:30d_trades:24 | last_event_time:1782284401000"
        val newerSourceSeenAt = source.getLastEventTime() + 60_000L
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
        Mockito.`when`(candidateRepository.findByNormalizedWalletIn(listOf(wallet))).thenReturn(emptyList())
        Mockito.`when`(candidateRepository.findByNormalizedWallet(wallet)).thenReturn(
            LeaderResearchCandidate(
                id = 51L,
                normalizedWallet = wallet,
                source = "ACTIVITY_SOURCE",
                sourceEvidence = evidence,
                lastSourceSeenAt = newerSourceSeenAt
            )
        )
        Mockito.`when`(leaderRepository.findLatestByLeaderAddressIn(listOf(wallet))).thenReturn(emptyList())
        Mockito.`when`(leaderRepository.findByLeaderAddress(wallet)).thenReturn(null)

        val response = service.importFromActivitySource(
            LeaderResearchActivitySourceImportRequest(
                dryRun = false,
                categories = listOf("politics"),
                limitPerCategory = 1
            )
        )

        assertEquals(0, response.updatedTotal)
        assertEquals(1, response.skippedExistingTotal)
        assertEquals("SKIP_EXISTING", response.previewItems.single().action)
        Mockito.verify(candidateRepository, Mockito.never()).save(anyCandidate())
    }

    @Test
    fun `import preserves newer existing freshness when activity evidence changes`() {
        val wallet = "0xabaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
        val lastEventTime = 1782284401000L
        val newerSourceSeenAt = lastEventTime + 60_000L
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
        ).thenReturn(listOf(activitySource(wallet, lastEventTime)))
        Mockito.`when`(candidateRepository.findByNormalizedWalletIn(listOf(wallet))).thenReturn(emptyList())
        Mockito.`when`(candidateRepository.findByNormalizedWallet(wallet)).thenReturn(
            LeaderResearchCandidate(
                id = 52L,
                normalizedWallet = wallet,
                source = "EXTERNAL_ANALYTICS_SOURCE",
                sourceEvidence = "external_analytics:polymarket_official_leaderboard | category:politics",
                lastSourceSeenAt = newerSourceSeenAt
            )
        )
        Mockito.`when`(leaderRepository.findLatestByLeaderAddressIn(listOf(wallet))).thenReturn(emptyList())
        Mockito.`when`(leaderRepository.findByLeaderAddress(wallet)).thenReturn(null)
        Mockito.`when`(candidateRepository.save(anyCandidate())).thenAnswer { it.arguments[0] }

        val response = service.importFromActivitySource(
            LeaderResearchActivitySourceImportRequest(
                dryRun = false,
                categories = listOf("politics"),
                limitPerCategory = 1
            )
        )

        assertEquals(1, response.updatedTotal)
        assertEquals("UPDATE", response.previewItems.single().action)
        val saved = captureSavedCandidates().single()
        assertEquals(newerSourceSeenAt, saved.lastSourceSeenAt)
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

    @Test
    fun `targeted import only scans requested wallets`() {
        val requestedWallet = "0x8888888888888888888888888888888888888888"
        Mockito.`when`(
            activityEventRepository.discoverWalletsFromActivitySourceForWallets(
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
        ).thenReturn(listOf(activitySource(requestedWallet)))
        Mockito.`when`(candidateRepository.findByNormalizedWallet(requestedWallet)).thenReturn(null)
        Mockito.`when`(leaderRepository.findByLeaderAddress(requestedWallet)).thenReturn(null)

        val response = service.importFromActivitySource(
            LeaderResearchActivitySourceImportRequest(
                dryRun = true,
                categories = listOf("politics"),
                wallets = listOf(requestedWallet, "not-a-wallet"),
                limitPerCategory = 10
            )
        )

        assertEquals(1, response.selectedTotal)
        assertEquals(1, response.createdTotal)
        assertEquals(requestedWallet, response.previewItems.single().wallet)
        Mockito.verify(activityEventRepository, Mockito.never()).discoverWalletsFromActivitySource(
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
    }

    @Test
    fun `untargeted import uses precomputed metrics when available`() {
        val wallet = "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
        Mockito.`when`(activityEventRepository.countActivityWalletMetrics("finance", 14)).thenReturn(12)
        Mockito.`when`(
            activityEventRepository.discoverWalletsFromActivitySourceMetrics(
                Mockito.eq("finance") ?: "finance",
                Mockito.eq(14),
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
                categories = listOf("finance"),
                lookbackDays = 14,
                limitPerCategory = 1
            )
        )

        assertEquals(listOf("finance"), response.metricsBackedCategories)
        assertEquals(1, response.selectedTotal)
        assertEquals(wallet, response.previewItems.single().wallet)
        Mockito.verify(activityEventRepository, Mockito.never()).discoverWalletsFromActivitySource(
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
    }

    @Test
    fun `scheduled metrics refresh is disabled by default`() {
        service.scheduledMetricsRefresh()

        Mockito.verify(activityEventRepository, Mockito.never()).deleteActivityWalletMetrics(
            Mockito.anyString(),
            Mockito.anyInt()
        )
        Mockito.verify(activityEventRepository, Mockito.never()).insertActivityWalletMetrics(
            Mockito.anyString(),
            Mockito.anyInt(),
            Mockito.anyLong(),
            Mockito.anyString(),
            Mockito.anyLong()
        )
    }

    @Test
    fun `refresh metrics recomputes each requested category`() {
        Mockito.`when`(
            activityEventRepository.deleteActivityWalletMetrics(Mockito.anyString(), Mockito.eq(14))
        ).thenReturn(0)
        Mockito.`when`(
            activityEventRepository.insertActivityWalletMetrics(
                Mockito.eq("politics") ?: "politics",
                Mockito.eq(14),
                Mockito.anyLong(),
                Mockito.anyString(),
                Mockito.anyLong()
            )
        ).thenReturn(12)
        Mockito.`when`(
            activityEventRepository.insertActivityWalletMetrics(
                Mockito.eq("finance") ?: "finance",
                Mockito.eq(14),
                Mockito.anyLong(),
                Mockito.anyString(),
                Mockito.anyLong()
            )
        ).thenReturn(7)

        val response = service.refreshMetrics(
            LeaderResearchActivitySourceMetricRefreshRequest(
                categories = listOf("politics", "finance"),
                lookbackDays = 14
            )
        )

        assertEquals(19, response.refreshedTotal)
        assertEquals(listOf("politics", "finance"), response.requestedCategories)
        assertEquals(listOf(12, 7), response.categories.map { it.refreshedCount })
        Mockito.verify(activityEventRepository).deleteActivityWalletMetrics("politics", 14)
        Mockito.verify(activityEventRepository).deleteActivityWalletMetrics("finance", 14)
    }

    private fun activitySource(
        wallet: String,
        lastEventTime: Long = 1782284401000
    ) = object : LeaderResearchActivitySourceProjection {
        override fun getNormalizedWallet(): String = wallet
        override fun getTotalEvents(): Long = 24
        override fun getDistinctMarkets(): Long = 6
        override fun getBuyEvents(): Long = 18
        override fun getSellEvents(): Long = 6
        override fun getSafePriceEvents(): Long = 14
        override fun getTailPriceEvents(): Long = 2
        override fun getAvgAmount(): BigDecimal = BigDecimal("3.25")
        override fun getTotalAmount(): BigDecimal = BigDecimal("78.00")
        override fun getLastEventTime(): Long = lastEventTime
    }

    private fun captureSavedCandidates(): List<LeaderResearchCandidate> {
        val captor = org.mockito.ArgumentCaptor.forClass(LeaderResearchCandidate::class.java)
        Mockito.verify(candidateRepository, Mockito.atLeastOnce()).save(captor.capture())
        return captor.allValues
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
