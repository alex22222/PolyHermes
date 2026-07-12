package com.wrbug.polymarketbot.service.risk

import com.wrbug.polymarketbot.dto.PortfolioRiskEvaluationRequest
import com.wrbug.polymarketbot.dto.PortfolioRiskEvaluationResponse
import org.springframework.stereotype.Service

data class BackendBuyRiskCandidate(
    val accountId: Long,
    val amount: String,
    val marketId: String? = null,
    val marketTitle: String? = null,
    val eventSlug: String? = null,
    val category: String? = null,
    val leaderAddress: String? = null,
    val modelCandidateId: String? = null
)

class PortfolioRiskBlockedException(val decision: PortfolioRiskEvaluationResponse) :
    IllegalStateException("组合风控拒绝执行：${decision.outcome}")

@Service
class BackendBuyRiskGateway(
    private val evaluationService: PortfolioRiskEvaluationService,
    private val reservationService: PortfolioRiskReservationService
) {
    fun precheck(correlationId: String, candidate: BackendBuyRiskCandidate) =
        evaluate(correlationId, candidate, "PRECHECK")

    fun finalCheck(correlationId: String, candidate: BackendBuyRiskCandidate) =
        evaluate(correlationId, candidate, "FINAL")

    fun complete(correlationId: String, success: Boolean) {
        reservationService.complete(correlationId, if (success) "SUCCESS" else "FAILED")
    }

    private fun evaluate(
        correlationId: String,
        candidate: BackendBuyRiskCandidate,
        stage: String
    ): PortfolioRiskEvaluationResponse {
        val response = evaluationService.evaluate(
            PortfolioRiskEvaluationRequest(
                accountId = candidate.accountId,
                modelCandidateId = candidate.modelCandidateId,
                side = "BUY",
                amount = candidate.amount,
                marketId = candidate.marketId,
                marketTitle = candidate.marketTitle,
                eventSlug = candidate.eventSlug,
                leaderAddress = candidate.leaderAddress,
                category = candidate.category,
                requestId = "$correlationId:${stage.lowercase()}",
                correlationId = correlationId,
                stage = stage
            )
        )
        if (!response.executionAllowed) {
            reservationService.complete(correlationId, "FAILED")
            throw PortfolioRiskBlockedException(response)
        }
        return response
    }
}
