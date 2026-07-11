package com.wrbug.polymarketbot.service.copytrading.research

import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import java.math.BigDecimal

class LeaderResearchStrategyTypeClassifierTest {
    @Test
    fun `calibrates Low Futon as low price tail risk from observed activity metrics`() {
        val result = LeaderResearchStrategyTypeClassifier.classify(
            totalEvents = 1753,
            distinctMarkets = 119,
            buyEvents = 945,
            sellEvents = 808,
            safePriceRatio = BigDecimal.ZERO,
            tailPriceRatio = BigDecimal("0.9994"),
            avgAmount = BigDecimal("0.48684639")
        )

        assertEquals(LeaderResearchStrategyTypeClassifier.LOW_PRICE_TAIL_RISK, result.strategyType)
        assertTrue(result.riskFlags.contains("strategy_low_price_tail_risk"))
    }

    @Test
    fun `calibrates XAE tail-heavy sell churn as low price tail risk instead of unknown`() {
        val result = LeaderResearchStrategyTypeClassifier.classify(
            totalEvents = 63,
            distinctMarkets = 9,
            buyEvents = 19,
            sellEvents = 44,
            safePriceRatio = BigDecimal("0.2540"),
            tailPriceRatio = BigDecimal("0.4286"),
            avgAmount = BigDecimal("55.40457252")
        )

        assertEquals(LeaderResearchStrategyTypeClassifier.LOW_PRICE_TAIL_RISK, result.strategyType)
        assertTrue(result.riskFlags.contains("strategy_low_price_tail_risk"))
    }

    @Test
    fun `calibrates Research ad53 as human directional from observed activity metrics`() {
        val result = LeaderResearchStrategyTypeClassifier.classify(
            totalEvents = 245,
            distinctMarkets = 188,
            buyEvents = 153,
            sellEvents = 92,
            safePriceRatio = BigDecimal("0.5714"),
            tailPriceRatio = BigDecimal("0.1224"),
            avgAmount = BigDecimal("11.35448494")
        )

        assertEquals(LeaderResearchStrategyTypeClassifier.HUMAN_DIRECTIONAL, result.strategyType)
        assertTrue(result.riskFlags.isEmpty())
    }
}
