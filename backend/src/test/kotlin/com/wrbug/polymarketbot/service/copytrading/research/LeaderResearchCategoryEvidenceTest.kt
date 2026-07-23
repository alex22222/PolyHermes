package com.wrbug.polymarketbot.service.copytrading.research

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Test

class LeaderResearchCategoryEvidenceTest {
    @Test
    fun `uses official leaderboard category instead of discovery default`() {
        val evidence = """
            external_analytics:falcon_leaderboard | category:finance | rank:123
            external_analytics:polymarket_official_leaderboard | category:politics | rank:456
        """.trimIndent()

        val result = LeaderResearchCategoryEvidenceClassifier.classify(evidence)

        assertEquals("politics", result.category)
        assertEquals(mapOf("politics" to 1), result.counts)
        assertFalse(result.mixed)
    }
}
