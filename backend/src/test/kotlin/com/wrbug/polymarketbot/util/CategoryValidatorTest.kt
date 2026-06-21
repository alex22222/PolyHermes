package com.wrbug.polymarketbot.util

import org.junit.jupiter.api.Assertions.assertEquals
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
}
