package com.wrbug.polymarketbot.service.risk

import com.google.gson.Gson
import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.repository.MarketRepository
import com.wrbug.polymarketbot.repository.PortfolioRiskDecisionRepository
import com.wrbug.polymarketbot.service.accounts.PortfolioExposureService
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Test
import org.mockito.ArgumentCaptor
import org.mockito.Mockito
import com.wrbug.polymarketbot.entity.PortfolioRiskDecision

class PortfolioRiskEvaluationServiceTest {
    private val exposureService = Mockito.mock(PortfolioExposureService::class.java)
    private val marketRepository = Mockito.mock(MarketRepository::class.java)
    private val decisionRepository = Mockito.mock(PortfolioRiskDecisionRepository::class.java)
    private val reservationService = Mockito.mock(PortfolioRiskReservationService::class.java) { invocation ->
        if (invocation.method.name == "prepare") PortfolioRiskReservationProjection(null)
        else Mockito.RETURNS_DEFAULTS.answer(invocation)
    }
    private val dailyMetricsService = Mockito.mock(PortfolioRiskDailyMetricsService::class.java) { invocation ->
        if (invocation.method.name == "calculate") PortfolioRiskDailyMetrics(0L, java.math.BigDecimal.ZERO, "MIDNIGHT", 0, true)
        else Mockito.RETURNS_DEFAULTS.answer(invocation)
    }
    private val buyControlService = Mockito.mock(PortfolioBuyControlService::class.java) { invocation ->
        if (invocation.method.name == "snapshot") PortfolioBuyControlSnapshot() else Mockito.RETURNS_DEFAULTS.answer(invocation)
    }
    private val service = PortfolioRiskEvaluationService(
        exposureService, marketRepository, decisionRepository, reservationService, dailyMetricsService, buyControlService, PortfolioRiskPolicy(), Gson()
    )

    @Test
    fun `buy evaluation records shadow would-block rules but still allows execution`() {
        Mockito.`when`(exposureService.getExposure(2L)).thenReturn(exposure())

        val result = service.evaluate(
            PortfolioRiskEvaluationRequest(
                accountId = 2,
                side = "BUY",
                amount = "11",
                marketId = "market-1",
                marketTitle = "Bitcoin market",
                eventSlug = "event-1",
                leaderAddress = "0xleader",
                category = "crypto",
                requestId = "request-1"
            )
        )

        assertEquals("G3-SHADOW-V4", result.policyVersion)
        assertEquals("SHADOW", result.mode)
        assertEquals("WOULD_BLOCK", result.outcome)
        assertEquals(true, result.executionAllowed)
        assertEquals("WOULD_BLOCK", result.rules.first { it.code == "MIN_CASH_RESERVE" }.status)
        assertEquals("WOULD_BLOCK", result.rules.first { it.code == "MAX_SINGLE_ORDER" }.status)
        assertEquals("WOULD_BLOCK", result.rules.first { it.code == "MAX_MARKET_EXPOSURE" }.status)
        assertEquals("WOULD_BLOCK", result.rules.first { it.code == "MAX_EVENT_EXPOSURE" }.status)
        assertEquals("INSUFFICIENT_DATA", result.rules.first { it.code == "MAX_LEADER_EXPOSURE" }.status)
        assertEquals("WOULD_BLOCK", result.rules.first { it.code == "MAX_CATEGORY_EXPOSURE" }.status)

        val captor = ArgumentCaptor.forClass(com.wrbug.polymarketbot.entity.PortfolioRiskDecision::class.java)
        Mockito.verify(decisionRepository).save(captor.capture())
        assertEquals("request-1", captor.value.requestId)
        assertEquals("WOULD_BLOCK", captor.value.outcome)
        assertEquals(true, captor.value.executionAllowed)
        assertEquals(true, captor.value.inputSnapshotJson?.contains("\"totalAssets\":\"100\"") == true)
    }

    @Test
    fun `sell is priority path and never evaluated by buy concentration rules`() {
        val result = service.evaluate(
            PortfolioRiskEvaluationRequest(
                accountId = 2,
                side = "SELL",
                amount = "5",
                marketId = "market-1",
                requestId = "sell-1"
            )
        )

        assertEquals("SELL_PRIORITY", result.outcome)
        assertEquals(true, result.executionAllowed)
        assertEquals(listOf("SELL_PRIORITY"), result.rules.map { it.code })
        Mockito.verifyNoInteractions(exposureService)
        Mockito.verify(decisionRepository).save(Mockito.any())
    }

    @Test
    fun `incomplete account valuation produces insufficient data instead of false pass`() {
        Mockito.`when`(exposureService.getExposure(2L)).thenReturn(
            exposure().copy(account = exposure().account.copy(totalAssets = null, valuationStatus = "BALANCE_UNKNOWN"))
        )

        val result = service.evaluate(
            PortfolioRiskEvaluationRequest(accountId = 2, side = "BUY", amount = "1", marketId = "market-1")
        )

        assertEquals("INSUFFICIENT_DATA", result.outcome)
        assertEquals(true, result.executionAllowed)
        assertEquals("INSUFFICIENT_DATA", result.rules.first { it.code == "MIN_CASH_RESERVE" }.status)
        assertEquals("INSUFFICIENT_DATA", result.rules.first { it.code == "MAX_SINGLE_ORDER" }.status)
    }

    @Test
    fun `same request id returns persisted decision without re-evaluating or duplicating audit`() {
        Mockito.`when`(decisionRepository.findByRequestId("same-1")).thenReturn(
            PortfolioRiskDecision(
                requestId = "same-1",
                accountId = 2,
                policyVersion = "G3-SHADOW-V1",
                mode = "SHADOW",
                side = "BUY",
                outcome = "PASS",
                executionAllowed = true,
                requestJson = "{}",
                rulesJson = "[{\"code\":\"MAX_SINGLE_ORDER\",\"status\":\"PASS\",\"actual\":\"1\",\"threshold\":\"2\",\"message\":\"ok\"}]",
                createdAt = 123L
            )
        )

        val result = service.evaluate(
            PortfolioRiskEvaluationRequest(accountId = 2, side = "BUY", amount = "1", requestId = "same-1")
        )

        assertEquals("same-1", result.decisionId)
        assertEquals(123L, result.evaluatedAt)
        assertEquals("PASS", result.outcome)
        Mockito.verifyNoInteractions(exposureService)
        Mockito.verify(decisionRepository, Mockito.never()).save(Mockito.any())
    }

    @Test
    fun `concurrent reservations and daily metrics are included in shadow projection`() {
        val projectedReservation = Mockito.mock(PortfolioRiskReservationService::class.java) { invocation ->
            if (invocation.method.name == "prepare") PortfolioRiskReservationProjection(
                reservation = com.wrbug.polymarketbot.entity.PortfolioRiskReservation(
                    correlationId = "c1", accountId = 2, amount = java.math.BigDecimal.ONE, expiresAt = 10_000
                ),
                otherTotalAmount = java.math.BigDecimal("10"),
                otherEventAmount = java.math.BigDecimal("5"),
                otherMarketAmount = java.math.BigDecimal("5"),
                otherCategoryAmount = java.math.BigDecimal("5"),
                otherActiveCount = 2
            ) else Mockito.RETURNS_DEFAULTS.answer(invocation)
        }
        val daily = Mockito.mock(PortfolioRiskDailyMetricsService::class.java) { invocation ->
            if (invocation.method.name == "calculate") PortfolioRiskDailyMetrics(0, java.math.BigDecimal("6"), "MIDNIGHT", 20, true)
            else Mockito.RETURNS_DEFAULTS.answer(invocation)
        }
        val localService = PortfolioRiskEvaluationService(
            exposureService, marketRepository, decisionRepository, projectedReservation, daily, buyControlService, PortfolioRiskPolicy(), Gson()
        )
        Mockito.`when`(exposureService.getExposure(2L)).thenReturn(exposure())

        val result = localService.evaluate(
            PortfolioRiskEvaluationRequest(
                accountId = 2,
                side = "BUY",
                amount = "1",
                eventSlug = "event-1",
                category = "crypto",
                requestId = "concurrent-1",
                correlationId = "c1",
                stage = "PRECHECK"
            )
        )

        assertEquals("WOULD_BLOCK", result.rules.first { it.code == "MIN_CASH_RESERVE" }.status)
        assertEquals("WOULD_BLOCK", result.rules.first { it.code == "MAX_EVENT_EXPOSURE" }.status)
        assertEquals("WOULD_BLOCK", result.rules.first { it.code == "MAX_DAILY_LOSS" }.status)
        assertEquals("WOULD_BLOCK", result.rules.first { it.code == "MAX_DAILY_BUY_ORDERS" }.status)
        assertEquals("ACTIVE", result.reservationStatus)
        assertEquals("1", result.reservedAmount)
    }

    @Test
    fun `manual account pause denies BUY even while threshold policy remains shadow`() {
        val pausedControl = Mockito.mock(PortfolioBuyControlService::class.java) { invocation ->
            if (invocation.method.name == "snapshot") PortfolioBuyControlSnapshot(true, "人工暂停", 10)
            else Mockito.RETURNS_DEFAULTS.answer(invocation)
        }
        val pausedService = PortfolioRiskEvaluationService(
            exposureService, marketRepository, decisionRepository, reservationService,
            dailyMetricsService, pausedControl, PortfolioRiskPolicy(), Gson()
        )
        Mockito.`when`(exposureService.getExposure(2L)).thenReturn(exposure())

        val result = pausedService.evaluate(
            PortfolioRiskEvaluationRequest(2, "BUY", "1", requestId = "paused-buy")
        )

        assertEquals(false, result.executionAllowed)
        assertEquals("WOULD_BLOCK", result.rules.first { it.code == "ACCOUNT_BUY_PAUSED" }.status)
    }

    private fun exposure(): PortfolioExposureResponse {
        val ready = PortfolioExposureDimensionCoverageDto("80", "0", "100", "95", "READY_FOR_SHADOW", true)
        val insufficient = PortfolioExposureDimensionCoverageDto("40", "40", "50", "95", "INSUFFICIENT_ATTRIBUTION", false)
        return PortfolioExposureResponse(
            account = PortfolioExposureAccountDto(2, "Bridge", "0xwallet", "30", "70", "0", "100", "COMPLETE", "75", "-5", 1L, 3, 2L),
            leaders = listOf(bucket("0xleader", "20", 8L)),
            categories = listOf(bucket("crypto", "30")),
            events = listOf(bucket("event-1", "10")),
            markets = listOf(bucket("market-1", "10")),
            coverage = PortfolioExposureCoverageDto(
                totalPositions = 3,
                unknownValuePositions = 0,
                unknownLeaderPositions = 1,
                unknownCategoryPositions = 0,
                unknownEventPositions = 0,
                unknownMarketPositions = 0,
                leader = insufficient,
                category = ready,
                event = ready,
                market = ready
            )
        )
    }

    private fun bucket(key: String, value: String, leaderId: Long? = null) = PortfolioExposureBucketDto(
        key, key, value, value, 1, "TEST", "EXACT", leaderId, value, "0", 1L, listOf("market-1|YES")
    )
}
