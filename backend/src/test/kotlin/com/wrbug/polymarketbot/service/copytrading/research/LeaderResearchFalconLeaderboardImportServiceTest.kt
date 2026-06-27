package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchFalconLeaderboardImportRequest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class LeaderResearchFalconLeaderboardImportServiceTest {
    private val client = FakeFalconLeaderboardClient()
    private val externalAnalyticsImportService: LeaderResearchExternalAnalyticsImportService = mock()
    private val service = LeaderResearchFalconLeaderboardImportService(
        client = client,
        externalAnalyticsImportService = externalAnalyticsImportService
    )

    @Test
    fun `imports Falcon leaderboard entries through external analytics service`() {
        val wallet = "0x1111111111111111111111111111111111111111"
        client.responses["h_score-0"] = listOf(
            FalconLeaderboardEntry(
                wallet = wallet,
                leaderboardRank = 7,
                tier = "A",
                hScore = BigDecimal("86.5"),
                roiPct15d = BigDecimal("0.42"),
                winRatePct15d = BigDecimal("0.61"),
                sharpeRatio15d = BigDecimal("2.4"),
                totalTrades15d = 81,
                marketsTraded15d = 24,
                totalPnl15d = BigDecimal("532.1"),
                totalVolume15d = BigDecimal("12000"),
                trajectory = "stable",
                category = null
            )
        )
        var capturedRequest: LeaderResearchExternalAnalyticsImportRequest? = null
        Mockito.doAnswer {
            capturedRequest = it.arguments[0] as LeaderResearchExternalAnalyticsImportRequest
            importResponse(requested = capturedRequest!!.items.size)
        }.`when`(externalAnalyticsImportService).importFromExternalAnalytics(anyImportRequest())

        val response = service.importFromFalconLeaderboard(
            LeaderResearchFalconLeaderboardImportRequest(
                dryRun = true,
                sortBys = listOf("h_score"),
                limitPerPage = 50,
                maxPagesPerSort = 1,
                defaultCategory = "finance"
            )
        )

        assertEquals(1, response.fetchedTotal)
        assertEquals(1, response.dedupedTotal)
        val item = capturedRequest!!.items.single()
        assertEquals(wallet, item.wallet)
        assertEquals("finance", item.category)
        assertEquals("falcon_leaderboard", item.sourceName)
        assertEquals(7, item.externalRank)
        assertEquals("86.5", item.externalScore)
        assertTrue(item.note!!.contains("trades15d:81"))
    }

    @Test
    fun `records Falcon fetch errors and still calls import pipeline`() {
        client.failKeys += "h_score-0"
        Mockito.`when`(externalAnalyticsImportService.importFromExternalAnalytics(anyImportRequest()))
            .thenReturn(importResponse(requested = 0))

        val response = service.importFromFalconLeaderboard(
            LeaderResearchFalconLeaderboardImportRequest(
                dryRun = true,
                sortBys = listOf("h_score"),
                maxPagesPerSort = 1
            )
        )

        assertEquals(0, response.fetchedTotal)
        assertEquals(0, response.dedupedTotal)
        assertEquals(1, response.fetches.size)
        assertTrue(response.fetches.single().error!!.contains("boom"))
        Mockito.verify(externalAnalyticsImportService).importFromExternalAnalytics(anyImportRequest())
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

    private class FakeFalconLeaderboardClient : LeaderResearchFalconLeaderboardClient {
        val responses = mutableMapOf<String, List<FalconLeaderboardEntry>>()
        val failKeys = mutableSetOf<String>()

        override fun fetch(filters: FalconLeaderboardFilters, limit: Int, offset: Int): List<FalconLeaderboardEntry> {
            val key = "${filters.sortBy}-$offset"
            if (key in failKeys) error("boom for $key")
            return responses[key].orEmpty()
        }
    }
}
