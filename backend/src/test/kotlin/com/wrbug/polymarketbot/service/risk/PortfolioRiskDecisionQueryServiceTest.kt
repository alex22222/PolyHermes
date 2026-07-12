package com.wrbug.polymarketbot.service.risk

import com.google.gson.Gson
import com.wrbug.polymarketbot.entity.PortfolioRiskDecision
import com.wrbug.polymarketbot.repository.PortfolioRiskDecisionRepository
import org.junit.jupiter.api.Assertions.assertEquals
import org.junit.jupiter.api.Assertions.assertTrue
import org.junit.jupiter.api.Test
import org.mockito.Mockito

class PortfolioRiskDecisionQueryServiceTest {
    private val repository = Mockito.mock(PortfolioRiskDecisionRepository::class.java)
    private val policy = PortfolioRiskPolicy()
    private val gson = Gson()
    private val service = PortfolioRiskDecisionQueryService(repository, policy, gson)

    @Test
    fun `full input replay deterministically verifies stored decision`() {
        val snapshot = snapshot()
        val evaluated = policy.evaluate(snapshot)
        Mockito.`when`(repository.findByRequestId("d1")).thenReturn(
            decision(evaluated.outcome, gson.toJson(evaluated.rules), gson.toJson(snapshot))
        )

        val result = service.replay("d1")

        assertEquals("WOULD_BLOCK", result.replayedOutcome)
        assertTrue(result.consistent)
        assertEquals("FULL_INPUT_SNAPSHOT", result.replayScope)
        assertTrue(result.snapshotAvailable)
    }

    @Test
    fun `legacy decision without input snapshot is explicitly unavailable`() {
        Mockito.`when`(repository.findByRequestId("d1")).thenReturn(decision("PASS", "[]", null))

        val result = service.replay("d1")

        assertEquals(null, result.replayedOutcome)
        assertEquals(false, result.consistent)
        assertEquals("INPUT_SNAPSHOT_UNAVAILABLE", result.replayScope)
        assertEquals(false, result.snapshotAvailable)
    }

    @Test
    fun `snapshot created before buy control remains replayable`() {
        val snapshot = snapshot().copy(policyVersion = "G3-SHADOW-V3")
        val evaluated = policy.evaluate(snapshot)
        val legacyJson = gson.toJson(snapshot).replace(Regex(",\"buyControl\":\\{[^}]*}"), "")
        Mockito.`when`(repository.findByRequestId("d1")).thenReturn(
            decision(evaluated.outcome, gson.toJson(evaluated.rules), legacyJson).copy(policyVersion = "G3-SHADOW-V3")
        )

        val result = service.replay("d1")

        assertTrue(result.consistent)
        assertEquals("FULL_INPUT_SNAPSHOT", result.replayScope)
    }

    private fun decision(outcome: String, rules: String, input: String?) = PortfolioRiskDecision(
        requestId = "d1",
        accountId = 2,
        policyVersion = PortfolioRiskPolicy.POLICY_VERSION,
        mode = "SHADOW",
        side = "BUY",
        outcome = outcome,
        executionAllowed = true,
        requestJson = "{}",
        rulesJson = rules,
        inputSnapshotJson = input,
        createdAt = 1
    )

    private fun snapshot(): PortfolioRiskInputSnapshot {
        val ready = com.wrbug.polymarketbot.dto.PortfolioExposureDimensionCoverageDto("100", "0", "100", "95", "READY_FOR_SHADOW", true)
        val bucket = com.wrbug.polymarketbot.dto.PortfolioExposureBucketDto("market-1", "market-1", "10", "10", 1, "TEST", "EXACT", null, "10", "0", 1, listOf("p"))
        val exposure = com.wrbug.polymarketbot.dto.PortfolioExposureResponse(
            com.wrbug.polymarketbot.dto.PortfolioExposureAccountDto(2, "Bridge", "0xwallet", "10", "90", "0", "100", "COMPLETE", "90", "0", 1, 1, 1),
            listOf(bucket.copy(key = "0xleader")), listOf(bucket.copy(key = "crypto")),
            listOf(bucket.copy(key = "event-1")), listOf(bucket),
            com.wrbug.polymarketbot.dto.PortfolioExposureCoverageDto(1, 0, 0, 0, 0, 0, ready, ready, ready, ready)
        )
        return PortfolioRiskInputSnapshot(
            request = com.wrbug.polymarketbot.dto.PortfolioRiskEvaluationRequest(2, "BUY", "3", "market-1", eventSlug = "event-1", leaderAddress = "0xleader"),
            resolvedCategory = "crypto", resolvedEventSlug = "event-1", exposure = exposure,
            daily = PortfolioRiskDailyInput("0", "MIDNIGHT", 0, true, 1), capturedAt = 1
        )
    }
}
