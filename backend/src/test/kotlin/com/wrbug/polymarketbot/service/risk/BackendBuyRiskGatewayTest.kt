package com.wrbug.polymarketbot.service.risk

import com.wrbug.polymarketbot.dto.PortfolioRiskEvaluationRequest
import com.wrbug.polymarketbot.dto.PortfolioRiskEvaluationResponse
import org.junit.jupiter.api.Assertions.assertThrows
import org.junit.jupiter.api.Test
import org.mockito.Mockito

class BackendBuyRiskGatewayTest {
    private val evaluationService = Mockito.mock(PortfolioRiskEvaluationService::class.java)
    private val reservationService = Mockito.mock(PortfolioRiskReservationService::class.java)
    private val gateway = BackendBuyRiskGateway(evaluationService, reservationService)

    @Test
    fun `precheck and final use distinct idempotency keys with one correlation`() {
        val candidate = BackendBuyRiskCandidate(2, "1.25", "market-1", "Market title", "event-1", "crypto")
        Mockito.`when`(evaluationService.evaluate(anyRequest())).thenReturn(allowed())

        gateway.precheck("correlation-1", candidate)
        gateway.finalCheck("correlation-1", candidate)

        val captor = org.mockito.ArgumentCaptor.forClass(PortfolioRiskEvaluationRequest::class.java)
        Mockito.verify(evaluationService, Mockito.times(2)).evaluate(
            captor.capture() ?: PortfolioRiskEvaluationRequest(0, "BUY", "1")
        )
        assert(captor.allValues[0].requestId == "correlation-1:precheck")
        assert(captor.allValues[0].stage == "PRECHECK")
        assert(captor.allValues[1].requestId == "correlation-1:final")
        assert(captor.allValues[1].stage == "FINAL")
        assert(captor.allValues.all { it.correlationId == "correlation-1" })
    }

    @Test
    fun `blocked final check stops execution`() {
        Mockito.`when`(evaluationService.evaluate(anyRequest())).thenReturn(allowed(), blocked())
        val candidate = BackendBuyRiskCandidate(2, "1")

        gateway.precheck("correlation-2", candidate)
        assertThrows(PortfolioRiskBlockedException::class.java) {
            gateway.finalCheck("correlation-2", candidate)
        }
        val completion = Mockito.mockingDetails(reservationService).invocations.single()
        assert(completion.arguments[0] == "correlation-2")
        assert(completion.arguments[1] == "FAILED")
    }

    @Test
    fun `completion closes reservation`() {
        gateway.complete("correlation-3", false)
        val invocation = Mockito.mockingDetails(reservationService).invocations.single()
        assert(invocation.arguments[0] == "correlation-3")
        assert(invocation.arguments[1] == "FAILED")
    }

    private fun allowed() = PortfolioRiskEvaluationResponse(
        "decision", "v", "SHADOW", "BUY", "PASS", true, emptyList(), 1
    )

    private fun blocked() = allowed().copy(executionAllowed = false, outcome = "BLOCK")

    private fun anyRequest(): PortfolioRiskEvaluationRequest =
        Mockito.any(PortfolioRiskEvaluationRequest::class.java)
            ?: PortfolioRiskEvaluationRequest(0, "BUY", "1")
}
