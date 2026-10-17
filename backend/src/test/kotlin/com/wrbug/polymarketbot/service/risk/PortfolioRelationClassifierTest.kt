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

    @Test
    fun `candidate calculation exactly matches full graph across all relationship types`() {
        val now = 40L * 24 * 60 * 60 * 1000
        val existing = listOf(
            position("duplicate", "m1", "e1", "YES", "politics", "Democrats win Senate"),
            position("true-hedge", "m1", "e1", "NO", "politics", "Democrats win Senate", "18"),
            position("pseudo-hedge", "m1", "e1", "Other", "sports", "World Cup winner"),
            position("same-event", "m2", "e1", "YES", "politics", "Other question"),
            position("same-entity", "m3", "e3", "YES", "politics", "Democrats win House"),
            position("unknown", null, null, "YES", null, "Unknown"),
            position("finance", "m4", "e4", "YES", "finance", "Fed rate decision"),
            position("crypto", "m5", "e5", "UP", "crypto", "Bitcoin Up or Down"),
            position("sports", "m6", "e6", "Team A", "sports", "World Cup winner")
        )
        val candidates = existing.mapIndexed { index, it -> it.copy(positionKey = "candidate-$index") } +
            existing.first().copy(positionKey = "unknown-candidate", marketId = null, eventSlug = null, category = null, currentValue = null)
        candidates.forEach { candidate ->
            assertEquals(
                classifier.classify(existing + candidate, now).filter { candidate.positionKey in it.positionKeys },
                classifier.classifyCandidate(existing, candidate, now)
            )
        }
        assertEquals(emptyList<PortfolioPositionRelation>(), classifier.classifyCandidate(emptyList(), existing.first(), 100))
    }

    @Test
    fun `report equivalent 84 position buy relationship cost`() {
        val existing = (0 until 84).map { index ->
            position("position-$index", "market-$index", "event-$index", "YES", "politics", "Will Democrats win election $index?")
        }
        val candidate = position("candidate", "market-0", "event-0", "YES", "politics", "Will Democrats win election 0?")
        repeat(2) { classifier.classify(existing, 100) }
        val started = System.nanoTime()
        repeat(8) {
            classifier.classify(existing, 100)
            classifier.classify(existing + candidate, 100).filter { candidate.positionKey in it.positionKeys }
        }
        println("LEGACY_84_POSITIONS_8_BUYS_MS=${(System.nanoTime() - started) / 1_000_000.0}")
        val optimizedStarted = System.nanoTime()
        repeat(8) { classifier.classifyCandidate(existing, candidate, 100) }
        println("CANDIDATE_84_POSITIONS_8_BUYS_MS=${(System.nanoTime() - optimizedStarted) / 1_000_000.0}")
        assertEquals(
            classifier.classify(existing + candidate, 100).filter { candidate.positionKey in it.positionKeys },
            classifier.classifyCandidate(existing, candidate, 100)
        )
    }

    private fun position(key: String, market: String?, event: String?, outcome: String, category: String?, title: String, value: String = "10", createdAt: Long = 90) = PortfolioRelationPosition(
        key, market, event, outcome, category, title, BigDecimal(value), BigDecimal.ONE, createdAt, null
    )
}
