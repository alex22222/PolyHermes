package com.wrbug.polymarketbot.service.risk

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.math.BigDecimal

class PortfolioRelationClassifierTest {
    private val classifier = PortfolioRelationClassifier()

    @Test
    fun `same binary condition opposite outcomes are true hedge with unmatched value disclosed`() {
        val result = classifier.classify(listOf(position("a", "m1", "e1", "YES", "politics", "Republicans control Senate", "10"), position("b", "m1", "e1", "NO", "politics", "Republicans control Senate", "18")), now = 100)

        val hedge = result.single { it.type == "TRUE_HEDGE" }
        assertEquals("8", hedge.unmatchedValue)
        assertTrue(hedge.rationale.contains("同一二元 condition"))
    }

    @Test
    fun `same condition same outcome is duplicate`() {
        val result = classifier.classify(listOf(position("a", "m1", "e1", "YES", "finance", "Fed rate decision"), position("b", "m1", "e1", "YES", "finance", "Fed rate decision")), 100)
        assertEquals("DUPLICATE", result.single().type)
    }

    @Test
    fun `same crypto asset across different short markets is related not hedge`() {
        val result = classifier.classify(listOf(position("a", "m1", "e1", "UP", "crypto", "XRP Up or Down 10PM"), position("b", "m2", "e2", "DOWN", "crypto", "XRP Up or Down 10 05PM")), 100)
        assertEquals("RELATED", result.single().type)
        assertEquals("XRP", result.single().entityKey)
    }

    @Test
    fun `opposite labels on non binary condition are pseudo hedge`() {
        val result = classifier.classify(listOf(position("a", "m1", "e1", "France", "sports", "World Cup winner"), position("b", "m1", "e1", "Brazil", "sports", "World Cup winner")), 100)
        assertEquals("PSEUDO_HEDGE", result.single().type)
    }

    @Test
    fun `missing deterministic identity stays unknown and old finance position is long occupied`() {
        val unknown = position("a", null, null, "YES", null, "Unknown market", createdAt = 1)
        val old = position("b", "m2", "e2", "YES", "finance", "Fed rate decision", createdAt = 1)
        val result = classifier.classify(listOf(unknown, old), now = 40L * 24 * 60 * 60 * 1000)
        assertTrue(result.any { it.type == "UNKNOWN" && it.positionKeys == listOf("a") })
        assertTrue(result.any { it.type == "LONG_OCCUPIED" && it.positionKeys == listOf("b") })
    }

    @Test
    fun `missing condition cannot join cross market entity relation`() {
        val unknownIran = position("a", null, null, "YES", "politics", "US Iran diplomatic meeting")
        val knownIran = position("b", "m2", "e2", "NO", "politics", "Iran control of island")
        val result = classifier.classify(listOf(unknownIran, knownIran), 100)
        assertEquals(listOf("UNKNOWN"), result.map { it.type })
    }

    private fun position(key: String, market: String?, event: String?, outcome: String, category: String?, title: String, value: String = "10", createdAt: Long = 90) = PortfolioRelationPosition(
        key, market, event, outcome, category, title, BigDecimal(value), BigDecimal.ONE, createdAt, null
    )
}
