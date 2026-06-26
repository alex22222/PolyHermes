package com.wrbug.polymarketbot.service.copytrading.research

import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test

class LeaderResearchMarketCategoryPatternsTest {
    @Test
    fun `finance pattern matches real finance markets`() {
        assertTrue(LeaderResearchMarketCategoryPatterns.matches("finance", "will-the-fed-decrease-interest-rates-by-50-bps-after-the-july-2026-meeting"))
        assertTrue(LeaderResearchMarketCategoryPatterns.matches("finance", "spx-up-or-down-on-june-22-2026"))
        assertTrue(LeaderResearchMarketCategoryPatterns.matches("finance", "wti-up-or-down-on-june-24-2026"))
        assertTrue(LeaderResearchMarketCategoryPatterns.matches("finance", "will-gold-gc-hit-high-6200-by-end-of-june"))
    }

    @Test
    fun `finance pattern rejects known false positives`() {
        assertFalse(LeaderResearchMarketCategoryPatterns.matches("finance", "btc-updown-5m-1782191700"))
        assertFalse(LeaderResearchMarketCategoryPatterns.matches("finance", "will-federico-valverde-be-the-top-goalscorer-at-the-2026-fifa-world-cup"))
        assertFalse(LeaderResearchMarketCategoryPatterns.matches("finance", "iran-agrees-to-surrender-enriched-uranium-stockpile-by-july-31-2026"))
    }

    @Test
    fun `politics pattern matches explicit political markets`() {
        assertTrue(LeaderResearchMarketCategoryPatterns.matches("politics", "israel-x-hezbollah-permanent-peace-deal-by-july-31-2026"))
        assertTrue(LeaderResearchMarketCategoryPatterns.matches("politics", "us-x-iran-diplomatic-meeting-by-july-31-2026"))
        assertTrue(LeaderResearchMarketCategoryPatterns.matches("politics", "will-ukraine-recapture-crimean-territory-by-december-31-2026"))
    }
}
