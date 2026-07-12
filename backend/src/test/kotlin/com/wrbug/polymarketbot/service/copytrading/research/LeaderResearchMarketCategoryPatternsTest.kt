package com.wrbug.polymarketbot.service.copytrading.research

import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class LeaderResearchMarketCategoryPatternsTest {
    @Test
    fun `classifies macro releases and company financial results as finance`() {
        assertTrue(LeaderResearchMarketCategoryPatterns.matches("finance", "Will PPI YoY be 5.8% or less in June?"))
        assertTrue(LeaderResearchMarketCategoryPatterns.matches("finance", "Will AT&T Q2 total revenue be above 31.4B?"))
        assertTrue(LeaderResearchMarketCategoryPatterns.matches("finance", "Will Honeywell Q2 sales be above 1.85B?"))
    }
}
