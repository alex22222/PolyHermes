package com.wrbug.polymarketbot.service.copytrading.research

import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportRequest
import com.wrbug.polymarketbot.dto.LeaderResearchExternalAnalyticsImportResponse
import com.wrbug.polymarketbot.dto.LeaderResearchPolymarketAnalyticsCopyTradeImportRequest
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito

class LeaderResearchPolymarketAnalyticsCopyTradeImportServiceTest {
    private val externalAnalyticsImportService: LeaderResearchExternalAnalyticsImportService = mock()
    private val service = LeaderResearchPolymarketAnalyticsCopyTradeImportService(externalAnalyticsImportService)

    @Test
    fun `parses pasted Polymarket Analytics copy trade text and delegates to external analytics import`() {
        var capturedRequest: LeaderResearchExternalAnalyticsImportRequest? = null
        Mockito.doAnswer {
            capturedRequest = it.arguments[0] as LeaderResearchExternalAnalyticsImportRequest
            importResponse(capturedRequest!!.items.size)
        }.`when`(externalAnalyticsImportService).importFromExternalAnalytics(anyImportRequest())

        val response = service.importFromCopyTradePage(
            LeaderResearchPolymarketAnalyticsCopyTradeImportRequest(
                dryRun = true,
                rawText = """
                    Smart Wallet #1
                    copied: 42 pnl: ${'$'}532.10 roi: 18% finance
                    0x1111111111111111111111111111111111111111
                    #2 sports 9 copy traders volume ${'$'}1200 0x2222222222222222222222222222222222222222
                """.trimIndent(),
                defaultCategory = "finance"
            )
        )

        assertEquals(2, response.parsedTotal)
        assertEquals(2, response.dedupedTotal)
        assertEquals("polymarket_analytics_copy_trade", response.sourceName)
        val items = capturedRequest!!.items
        assertEquals("polymarket_analytics_copy_trade", capturedRequest!!.defaultSourceName)
        assertEquals(1, items[0].externalRank)
        assertEquals("finance", items[0].category)
        assertEquals("copied:42", items[0].externalScore)
        assertTrue(items[0].note!!.contains("source_url:https://polymarketanalytics.com/copy-trade"))
        assertTrue(items[0].note!!.contains("pnl:532.10"))
        assertEquals("sports", items[1].category)
        assertEquals("copied:9", items[1].externalScore)
    }

    @Test
    fun `dedupes wallets before import`() {
        Mockito.`when`(externalAnalyticsImportService.importFromExternalAnalytics(anyImportRequest()))
            .thenReturn(importResponse(1))

        val response = service.importFromCopyTradePage(
            LeaderResearchPolymarketAnalyticsCopyTradeImportRequest(
                rawText = """
                    #1 copied 5 0x1111111111111111111111111111111111111111
                    #2 copied 4 0x1111111111111111111111111111111111111111
                """.trimIndent()
            )
        )

        assertEquals(2, response.parsedTotal)
        assertEquals(1, response.dedupedTotal)
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
}
