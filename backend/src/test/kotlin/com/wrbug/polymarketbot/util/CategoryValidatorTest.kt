package com.wrbug.polymarketbot.util

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertNull
import org.junit.jupiter.api.Test

class CategoryValidatorTest {

    @Test
    fun `infers esports markets as sports`() {
        val category = CategoryValidator.inferMarketCategory(
            "Counter-Strike: Natus Vincere vs G2 (BO3) - IEM Cologne Major Stage 3",
            "cs2-navi-g2-2026-06-15"
        )

        assertEquals("sports", category)
    }

    @Test
    fun `infers over under markets as sports`() {
        val category = CategoryValidator.inferMarketCategory(
            "Sports O/U: Team A vs Team B over/under 2.5"
        )

        assertEquals("sports", category)
    }

    @Test
    fun `infers fifa world cup slug as sports even with null title`() {
        val category = CategoryValidator.inferMarketCategory(
            null,
            "fifwc-nld-swe-2026-06-20-swe"
        )

        assertEquals("sports", category)
    }

    @Test
    fun `infers mlb slug as sports even with token in title`() {
        val category = CategoryValidator.inferMarketCategory(
            "Baseball Token Market",
            "mlb-cin-nyy-2026-06-20"
        )

        assertEquals("sports", category)
    }

    @Test
    fun `infers nba wnba slug as sports`() {
        assertEquals("sports", CategoryValidator.inferMarketCategory(null, "nba-lal-bos-2026-06-20"))
        assertEquals("sports", CategoryValidator.inferMarketCategory(null, "wnba-las-ny-2026-06-20"))
    }

    @Test
    fun `infers premier league slug as sports`() {
        val category = CategoryValidator.inferMarketCategory(
            null,
            "premier-league-mci-ars-2026-05-15"
        )

        assertEquals("sports", category)
    }

    @Test
    fun `infers legal case title as politics`() {
        val category = CategoryValidator.inferMarketCategory(
            "Will Harvey Weinstein be sentenced to prison by July?",
            "will-harvey-weinstein-be-sentenced"
        )

        assertEquals("politics", category)
    }

    @Test
    fun `infers election title as politics`() {
        val category = CategoryValidator.inferMarketCategory(
            "Will Trump win the 2028 presidential election?"
        )

        assertEquals("politics", category)
    }

    @Test
    fun `infers genuine crypto market as crypto`() {
        val category = CategoryValidator.inferMarketCategory(
            "Will Bitcoin reach $100k by end of year?",
            "bitcoin-100k-2024"
        )

        assertEquals("crypto", category)
    }

    @Test
    fun `infers finance market as finance`() {
        val category = CategoryValidator.inferMarketCategory(
            "Will the Fed cut interest rates in June?"
        )

        assertEquals("finance", category)
    }

    @Test
    fun `normalizes api category variants`() {
        assertEquals("crypto", CategoryValidator.normalizeCategory("cryptocurrency"))
        assertEquals("politics", CategoryValidator.normalizeCategory("political"))
        assertEquals("finance", CategoryValidator.normalizeCategory("financial"))
    }

    @Test
    fun `returns null for unrecognizable text`() {
        val category = CategoryValidator.inferMarketCategory("random unknown market")

        assertNull(category)
    }
}
