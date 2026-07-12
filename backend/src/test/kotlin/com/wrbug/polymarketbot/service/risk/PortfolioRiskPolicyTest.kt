package com.wrbug.polymarketbot.service.risk

import com.wrbug.polymarketbot.dto.*
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test

class PortfolioRiskPolicyTest {
    private val policy = PortfolioRiskPolicy()

    @Test
    fun `same captured input deterministically reproduces rules and outcome`() {
        val snapshot = PortfolioRiskInputSnapshot(
            request = PortfolioRiskEvaluationRequest(2, "BUY", "3", "market-1", eventSlug = "event-1", leaderAddress = "0xleader"),
            resolvedCategory = "crypto",
            resolvedEventSlug = "event-1",
            exposure = exposure(),
            daily = PortfolioRiskDailyInput("6", "MIDNIGHT", 20, true, 1),
            reservation = PortfolioRiskReservationInput("0", "2", "2", "0", "2", 1, false),
            capturedAt = 123
        )

        val first = policy.evaluate(snapshot)
        val replay = policy.evaluate(snapshot)

        assertEquals(first, replay)
        assertEquals("WOULD_BLOCK", replay.outcome)
        assertEquals("WOULD_BLOCK", replay.rules.first { it.code == "MAX_DAILY_LOSS" }.status)
        assertEquals("WOULD_BLOCK", replay.rules.first { it.code == "MAX_DAILY_BUY_ORDERS" }.status)
    }

    @Test
    fun `incomplete captured valuation remains insufficient during replay`() {
        val snapshot = PortfolioRiskInputSnapshot(
            request = PortfolioRiskEvaluationRequest(2, "BUY", "1"),
            exposure = exposure().copy(account = exposure().account.copy(totalAssets = null, valuationStatus = "BALANCE_UNKNOWN")),
            capturedAt = 1
        )

        val result = policy.evaluate(snapshot)

        assertEquals("INSUFFICIENT_DATA", result.outcome)
        assertEquals("INSUFFICIENT_DATA", result.rules.first { it.code == "MIN_CASH_RESERVE" }.status)
    }

    @Test
    fun `manual BUY pause blocks execution policy while preserving all other audit rules`() {
        val snapshot = PortfolioRiskInputSnapshot(
            request = PortfolioRiskEvaluationRequest(2, "BUY", "1"),
            exposure = exposure(),
            daily = PortfolioRiskDailyInput("0", "MIDNIGHT", 0, true, 1),
            buyControl = PortfolioBuyControlSnapshot(true, "人工检查相关仓位", 10),
            capturedAt = 10
        )
        val result = policy.evaluate(snapshot)
        assertEquals("WOULD_BLOCK", result.outcome)
        assertEquals("WOULD_BLOCK", result.rules.first { it.code == "ACCOUNT_BUY_PAUSED" }.status)
        assertEquals(true, result.rules.any { it.code == "MAX_SINGLE_ORDER" })
    }

    private fun exposure(): PortfolioExposureResponse {
        val ready = PortfolioExposureDimensionCoverageDto("100", "0", "100", "95", "READY_FOR_SHADOW", true)
        return PortfolioExposureResponse(
            PortfolioExposureAccountDto(2, "Bridge", "0xwallet", "30", "70", "0", "100", "COMPLETE", "70", "0", 1, 3, 2),
            listOf(bucket("0xleader", "5")),
            listOf(bucket("crypto", "30")),
            listOf(bucket("event-1", "10")),
            listOf(bucket("market-1", "5")),
            PortfolioExposureCoverageDto(3, 0, 0, 0, 0, 0, ready, ready, ready, ready)
        )
    }

    private fun bucket(key: String, value: String) = PortfolioExposureBucketDto(
        key, key, value, value, 1, "TEST", "EXACT", null, value, "0", 1, listOf(key)
    )
}
