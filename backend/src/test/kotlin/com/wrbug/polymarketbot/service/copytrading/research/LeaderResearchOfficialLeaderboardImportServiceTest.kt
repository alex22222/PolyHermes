package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchOfficialLeaderboardRefreshRequest
import com.wrbug.polymarketbot.entity.LeaderResearchCandidate
import com.wrbug.polymarketbot.repository.LeaderResearchCandidateRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class LeaderResearchOfficialLeaderboardImportServiceTest {
    private val client = FakeOfficialLeaderboardClient()
    private val externalAnalyticsImportService: LeaderResearchExternalAnalyticsImportService = mock()
    private val candidateRepository: LeaderResearchCandidateRepository = mock()
    private val service = LeaderResearchOfficialLeaderboardImportService(
        client = client,
        externalAnalyticsImportService = externalAnalyticsImportService,
        candidateRepository = candidateRepository
    )

    @Test
    fun `imports primary category leaderboard entries through external analytics service`() {
        val politicsWallet = "0x1111111111111111111111111111111111111111"
        val financeWallet = "0x2222222222222222222222222222222222222222"
        client.responses["POLITICS-MONTH-PNL-0"] = listOf(
            OfficialLeaderboardEntry(wallet = politicsWallet, rank = 1, name = "politics-alpha", pnl = BigDecimal("12.5"), volume = BigDecimal("100"))
        )
        client.responses["FINANCE-MONTH-PNL-0"] = listOf(
            OfficialLeaderboardEntry(wallet = financeWallet, rank = 1, name = "finance-alpha", pnl = BigDecimal("9.1"), volume = BigDecimal("80")),
            OfficialLeaderboardEntry(wallet = politicsWallet, rank = 2, name = "duplicate", pnl = BigDecimal("8"), volume = BigDecimal("70"))
        )
        var capturedRequest: LeaderResearchExternalAnalyticsImportRequest? = null
        Mockito.doAnswer {
            capturedRequest = it.arguments[0] as LeaderResearchExternalAnalyticsImportRequest
            importResponse(requested = capturedRequest!!.items.size)
        }.`when`(externalAnalyticsImportService).importFromExternalAnalytics(anyImportRequest())

        val response = service.importFromOfficialLeaderboard(
            LeaderResearchOfficialLeaderboardImportRequest(
                dryRun = true,
                categories = listOf("politics", "finance", "sports"),
                timePeriods = listOf("MONTH"),
                limitPerPage = 50,
                maxPagesPerQuery = 1,
                maxItems = 10
            )
        )

        assertEquals(3, response.fetchedTotal)
        assertEquals(2, response.dedupedTotal)
        assertEquals(2, response.importResult.requestedTotal)
        val importedItems = capturedRequest!!.items
        assertEquals(listOf(politicsWallet, financeWallet), importedItems.map { it.wallet })
        assertTrue(importedItems.all { it.sourceName == "polymarket_official_leaderboard" })
        assertTrue(importedItems.all { it.category in setOf("politics", "finance") })
    }

    @Test
    fun `imports only wallets profitable across every requested pnl period`() {
        val consistentlyProfitable = "0x6666666666666666666666666666666666666666"
        val longTermLoser = "0x7777777777777777777777777777777777777777"
        client.responses["FINANCE-MONTH-PNL-0"] = listOf(
            OfficialLeaderboardEntry(
                wallet = consistentlyProfitable,
                rank = 3,
                name = "steady",
                pnl = BigDecimal("25"),
                volume = BigDecimal("250")
            ),
            OfficialLeaderboardEntry(
                wallet = longTermLoser,
                rank = 4,
                name = "recent-only",
                pnl = BigDecimal("20"),
                volume = BigDecimal("200")
            )
        )
        client.responses["FINANCE-ALL-PNL-0"] = listOf(
            OfficialLeaderboardEntry(
                wallet = consistentlyProfitable,
                rank = 8,
                name = "steady",
                pnl = BigDecimal("120"),
                volume = BigDecimal("1200")
            ),
            OfficialLeaderboardEntry(
                wallet = longTermLoser,
                rank = 9,
                name = "recent-only",
                pnl = BigDecimal("-10"),
                volume = BigDecimal("900")
            )
        )
        var capturedRequest: LeaderResearchExternalAnalyticsImportRequest? = null
        Mockito.doAnswer {
            capturedRequest = it.arguments[0] as LeaderResearchExternalAnalyticsImportRequest
            importResponse(requested = capturedRequest!!.items.size)
        }.`when`(externalAnalyticsImportService).importFromExternalAnalytics(anyImportRequest())

        val response = service.importFromOfficialLeaderboard(
            LeaderResearchOfficialLeaderboardImportRequest(
                dryRun = true,
                categories = listOf("finance"),
                timePeriods = listOf("MONTH", "ALL"),
                orderBys = listOf("PNL"),
                limitPerPage = 50,
                maxPagesPerQuery = 1,
                maxItems = 10
            )
        )

        assertEquals(4, response.fetchedTotal)
        assertEquals(1, response.dedupedTotal)
        assertEquals(listOf(consistentlyProfitable), capturedRequest!!.items.map { it.wallet })
        assertTrue(capturedRequest!!.items.single().note!!.contains("MONTH"))
        assertTrue(capturedRequest!!.items.single().note!!.contains("ALL"))
    }

    @Test
    fun `records fetch errors instead of silently returning empty success`() {
        client.failKeys += "POLITICS-MONTH-PNL-0"
        Mockito.`when`(externalAnalyticsImportService.importFromExternalAnalytics(anyImportRequest()))
            .thenReturn(importResponse(requested = 0))

        val response = service.importFromOfficialLeaderboard(
            LeaderResearchOfficialLeaderboardImportRequest(
                dryRun = true,
                categories = listOf("politics"),
                timePeriods = listOf("MONTH"),
                limitPerPage = 20,
                maxPagesPerQuery = 1
            )
        )

        assertEquals(0, response.fetchedTotal)
        assertEquals(0, response.dedupedTotal)
        assertEquals(1, response.fetches.size)
        assertTrue(response.fetches.single().error!!.contains("boom"))
        Mockito.verify(externalAnalyticsImportService).importFromExternalAnalytics(anyImportRequest())
    }

    @Test
    fun `refreshes only requested official leaderboard wallets`() {
        val targetWallet = "0x3333333333333333333333333333333333333333"
        val otherWallet = "0x4444444444444444444444444444444444444444"
        client.responses["FINANCE-MONTH-PNL-0"] = listOf(
            OfficialLeaderboardEntry(wallet = otherWallet, rank = 1, name = "other", pnl = BigDecimal("30"), volume = BigDecimal("300")),
            OfficialLeaderboardEntry(wallet = targetWallet, rank = 2, name = "target", pnl = BigDecimal("20"), volume = BigDecimal("200"))
        )
        var capturedRequest: LeaderResearchExternalAnalyticsImportRequest? = null
        Mockito.doAnswer {
            capturedRequest = it.arguments[0] as LeaderResearchExternalAnalyticsImportRequest
            importResponse(requested = capturedRequest!!.items.size)
        }.`when`(externalAnalyticsImportService).importFromExternalAnalytics(anyImportRequest())

        val response = service.refreshCandidatesFromOfficialLeaderboard(
            LeaderResearchOfficialLeaderboardRefreshRequest(
                dryRun = true,
                wallets = listOf(targetWallet),
                categories = listOf("finance"),
                limitPerPage = 50,
                maxPagesPerQuery = 1
            )
        )

        assertEquals(2, response.fetchedTotal)
        assertEquals(1, response.matchedTotal)
        assertEquals(listOf(targetWallet), response.requestedWallets)
        assertEquals(listOf(targetWallet), capturedRequest!!.items.map { it.wallet })
        assertEquals("finance", capturedRequest!!.items.single().category)
    }

    @Test
    fun `refresh resolves candidate ids to wallets`() {
        val targetWallet = "0x5555555555555555555555555555555555555555"
        Mockito.`when`(candidateRepository.findAllById(listOf(1660L))).thenReturn(
            listOf(LeaderResearchCandidate(id = 1660L, normalizedWallet = targetWallet))
        )
        client.responses["FINANCE-MONTH-PNL-0"] = listOf(
            OfficialLeaderboardEntry(wallet = targetWallet, rank = 7, name = "target", pnl = BigDecimal("10"), volume = BigDecimal("100"))
        )
        var capturedRequest: LeaderResearchExternalAnalyticsImportRequest? = null
        Mockito.doAnswer {
            capturedRequest = it.arguments[0] as LeaderResearchExternalAnalyticsImportRequest
            importResponse(requested = capturedRequest!!.items.size)
        }.`when`(externalAnalyticsImportService).importFromExternalAnalytics(anyImportRequest())

        val response = service.refreshCandidatesFromOfficialLeaderboard(
            LeaderResearchOfficialLeaderboardRefreshRequest(
                dryRun = true,
                candidateIds = listOf(1660L),
                categories = listOf("finance"),
                limitPerPage = 50,
                maxPagesPerQuery = 1
            )
        )

        assertEquals(1, response.matchedTotal)
        assertEquals(listOf(targetWallet), response.requestedWallets)
        assertEquals(listOf(targetWallet), capturedRequest!!.items.map { it.wallet })
    }

    private fun importResponse(requested: Int) = LeaderResearchExternalAnalyticsImportResponse(
        dryRun = true,
        requestedTotal = requested,
        selectedTotal = requested,
        createdTotal = requested,
        updatedTotal = 0,
        skippedInvalidTotal = 0,
        skippedExistingTotal = 0,
        skippedLockedTotal = 0,
        previewItems = emptyList()
    )

    private fun anyImportRequest(): LeaderResearchExternalAnalyticsImportRequest {
        Mockito.any(LeaderResearchExternalAnalyticsImportRequest::class.java)
        return LeaderResearchExternalAnalyticsImportRequest()
    }

    @Suppress("UNCHECKED_CAST")
    private inline fun <reified T> mock(): T = Mockito.mock(T::class.java)

    private class FakeOfficialLeaderboardClient : LeaderResearchOfficialLeaderboardClient {
        val responses = mutableMapOf<String, List<OfficialLeaderboardEntry>>()
        val failKeys = mutableSetOf<String>()

        override fun fetch(category: String, timePeriod: String, orderBy: String, limit: Int, offset: Int): List<OfficialLeaderboardEntry> {
            val key = "$category-$timePeriod-$orderBy-$offset"
            if (key in failKeys) error("boom for $key")
            return responses[key].orEmpty()
        }
    }
}
