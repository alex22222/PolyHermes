package com.wrbug.polymarketbot.service.risk

import com.google.gson.Gson
import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.entity.PortfolioRiskDecision
import com.wrbug.polymarketbot.entity.PortfolioRiskReservation
import com.wrbug.polymarketbot.repository.PortfolioRiskDecisionRepository
import com.wrbug.polymarketbot.repository.PortfolioRiskReservationRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertFalse
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito
import java.math.BigDecimal

class PortfolioRiskShadowReportServiceTest {
    private val decisions = Mockito.mock(PortfolioRiskDecisionRepository::class.java)
    private val reservations = Mockito.mock(PortfolioRiskReservationRepository::class.java)
    private val gson = Gson()
    private val policy = PortfolioRiskPolicy()
    private val service = PortfolioRiskShadowReportService(decisions, reservations, policy, gson)

    @Test
    fun `report excludes legacy era and exposes unmet sample and completeness gates`() {
        val snapshot = snapshot("FINAL")
        val result = policy.evaluate(snapshot)
        val legacy = decision("legacy", 1, null, "PASS", "[]")
        val current = decision("current", 2, gson.toJson(snapshot), result.outcome, gson.toJson(result.rules))
        Mockito.`when`(decisions.findByAccountIdAndCreatedAtGreaterThanEqualOrderByCreatedAtAsc(2, 0))
            .thenReturn(listOf(legacy, current))
        Mockito.`when`(reservations.findByCorrelationId("corr-1")).thenReturn(
            PortfolioRiskReservation(correlationId = "corr-1", accountId = 2, amount = BigDecimal.ONE, status = "FAILED", expiresAt = 9, completedAt = 3)
        )

        val report = service.generate(2, 0, now = 10)

        assertEquals(1, report.legacyDecisionsExcluded)
        assertEquals(1, report.totalDecisions)
        assertEquals("100", report.snapshotCoveragePercent)
        assertEquals("100", report.replayConsistencyPercent)
        assertEquals("100", report.terminalLinkagePercent)
        assertEquals(1, report.terminalStatuses["FAILED"])
        assertFalse(report.readyForEnforcedReview)
        assertEquals(false, report.gates.first { it.code == "MIN_BUY_SAMPLES" }.passed)
        assertEquals(false, report.gates.first { it.code == "FULLY_EVALUATED_BUY_RATE" }.passed)
    }

    @Test
    fun `report becomes review ready only when every gate passes`() {
        val week = 168L * 60 * 60 * 1000
        val rows = (0 until 100).map { index ->
            val final = index >= 80
            val snapshot = snapshot(if (final) "FINAL" else "EVALUATE", "corr-$index", week * index / 99)
            val evaluated = policy.evaluate(snapshot)
            if (final) {
                Mockito.`when`(reservations.findByCorrelationId("corr-$index")).thenReturn(
                    PortfolioRiskReservation(correlationId = "corr-$index", accountId = 2, amount = BigDecimal.ONE, status = "SUCCESS", expiresAt = week, completedAt = week)
                )
            }
            decision("d-$index", snapshot.capturedAt, gson.toJson(snapshot), evaluated.outcome, gson.toJson(evaluated.rules))
        }
        Mockito.`when`(decisions.findByAccountIdAndCreatedAtGreaterThanEqualOrderByCreatedAtAsc(2, 0)).thenReturn(rows)

        val report = service.generate(2, 0, now = week)

        assertTrue(report.readyForEnforcedReview)
        assertTrue(report.blockers.isEmpty())
        assertEquals(100, report.buyDecisions)
        assertEquals(20, report.finalDecisions)
        assertEquals("100", report.terminalLinkagePercent)
    }

    private fun snapshot(stage: String, correlationId: String = "corr-1", capturedAt: Long = 2): PortfolioRiskInputSnapshot {
        val ready = PortfolioExposureDimensionCoverageDto("100", "0", "100", "95", "READY_FOR_SHADOW", true)
        val insufficient = ready.copy(shadowEligible = false, status = "INSUFFICIENT_ATTRIBUTION")
        val bucket = PortfolioExposureBucketDto("crypto", "crypto", "10", "10", 1, "TEST", "EXACT", null, "10", "0", 1, listOf("p"))
        return PortfolioRiskInputSnapshot(
            request = PortfolioRiskEvaluationRequest(
                2, "BUY", "1", marketId = "market-1", eventSlug = "event-1",
                leaderAddress = "0xleader", category = "crypto", correlationId = correlationId, stage = stage
            ),
            resolvedCategory = "crypto",
            resolvedEventSlug = "event-1",
            exposure = PortfolioExposureResponse(
                PortfolioExposureAccountDto(2, "Bridge", "0x", "50", "50", "0", "100", "COMPLETE", "50", "0", 1, 1, 1),
                listOf(bucket.copy(key = "0xleader")), listOf(bucket), listOf(bucket.copy(key = "event-1")), listOf(bucket.copy(key = "market-1")),
                PortfolioExposureCoverageDto(1, 0, 0, 0, 0, 0, if (stage == "FINAL" && correlationId == "corr-1" && capturedAt == 2L) insufficient else ready, ready, ready, ready)
            ),
            daily = PortfolioRiskDailyInput("0", "MIDNIGHT", 0, true, 0),
            capturedAt = capturedAt
        )
    }

    private fun decision(id: String, createdAt: Long, input: String?, outcome: String, rules: String) = PortfolioRiskDecision(
        requestId = id, accountId = 2, policyVersion = PortfolioRiskPolicy.POLICY_VERSION,
        mode = "SHADOW", side = "BUY", outcome = outcome, executionAllowed = true,
        requestJson = "{}", rulesJson = rules, inputSnapshotJson = input, createdAt = createdAt
    )
}
