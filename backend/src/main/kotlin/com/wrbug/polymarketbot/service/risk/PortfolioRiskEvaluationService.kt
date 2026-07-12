package com.wrbug.polymarketbot.service.risk

import com.google.gson.Gson
import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.entity.PortfolioRiskDecision
import com.wrbug.polymarketbot.repository.MarketRepository
import com.wrbug.polymarketbot.repository.PortfolioRiskDecisionRepository
import com.wrbug.polymarketbot.service.accounts.PortfolioExposureService
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchMarketCategoryPatterns
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal
import java.util.UUID

@Service
class PortfolioRiskEvaluationService(
    private val exposureService: PortfolioExposureService,
    private val marketRepository: MarketRepository,
    private val decisionRepository: PortfolioRiskDecisionRepository,
    private val reservationService: PortfolioRiskReservationService,
    private val dailyMetricsService: PortfolioRiskDailyMetricsService,
    private val buyControlService: PortfolioBuyControlService,
    private val policy: PortfolioRiskPolicy,
    private val gson: Gson
) {
    @Transactional
    fun evaluate(request: PortfolioRiskEvaluationRequest): PortfolioRiskEvaluationResponse {
        val side = request.side.trim().uppercase()
        require(side == "BUY" || side == "SELL") { "side 必须是 BUY 或 SELL" }
        val amount = request.amount.toBigDecimalOrNull()
            ?: throw IllegalArgumentException("amount 无效")
        require(amount > BigDecimal.ZERO) { "amount 必须大于 0" }
        val requestId = request.requestId?.trim()?.takeIf { it.isNotBlank() } ?: UUID.randomUUID().toString()

        decisionRepository.findByRequestId(requestId)?.let { return it.toResponse() }

        val evaluatedAt = System.currentTimeMillis()
        val category = resolveCategory(request)
        val eventSlug = resolveEventSlug(request)
        val reservationProjection = if (side == "BUY") {
            reservationService.prepare(
                request.accountId,
                request.correlationId,
                request.stage,
                amount,
                request.marketId,
                eventSlug,
                request.leaderAddress,
                category
            )
        } else PortfolioRiskReservationProjection(null)
        val exposure = if (side == "BUY") exposureService.getExposure(request.accountId) else null
        val totalAssets = exposure?.account?.totalAssets?.toBigDecimalOrNull()
        val daily = if (side == "BUY" && exposure != null && totalAssets != null && totalAssets > BigDecimal.ZERO &&
            exposure.account.availableBalance?.toBigDecimalOrNull() != null && exposure.account.valuationStatus == "COMPLETE"
        ) dailyMetricsService.calculate(request.accountId, exposure.account.walletAddress, totalAssets) else null
        val snapshot = PortfolioRiskInputSnapshot(
            request = request.copy(side = side, amount = amount.strip()),
            resolvedCategory = category,
            resolvedEventSlug = eventSlug,
            exposure = exposure,
            daily = daily?.let { PortfolioRiskDailyInput(it.lossPercent?.strip(), it.baselineType, it.successfulBuyCount, it.orderCountComplete, it.dayStartAt) },
            reservation = reservationProjection.toInput(),
            buyControl = if (side == "BUY") buyControlService.snapshot(request.accountId) else PortfolioBuyControlSnapshot(),
            capturedAt = evaluatedAt
        )
        val policyResult = policy.evaluate(snapshot)
        val rules = policyResult.rules
        val outcome = policyResult.outcome
        val response = PortfolioRiskEvaluationResponse(
            decisionId = requestId,
            policyVersion = PortfolioRiskPolicy.POLICY_VERSION,
            mode = MODE,
            side = side,
            outcome = outcome,
            executionAllowed = side == "SELL" || snapshot.buyControl?.paused != true,
            rules = rules,
            evaluatedAt = evaluatedAt,
            reservationStatus = reservationProjection.reservation?.status,
            reservedAmount = reservationProjection.reservation?.amount?.strip()
        )
        decisionRepository.save(
            PortfolioRiskDecision(
                requestId = requestId,
                accountId = request.accountId,
                policyVersion = PortfolioRiskPolicy.POLICY_VERSION,
                mode = MODE,
                side = side,
                outcome = outcome,
                executionAllowed = response.executionAllowed,
                marketId = request.marketId,
                eventSlug = eventSlug,
                leaderAddress = request.leaderAddress?.lowercase(),
                category = category,
                requestJson = gson.toJson(request),
                rulesJson = gson.toJson(rules),
                inputSnapshotJson = gson.toJson(snapshot),
                createdAt = evaluatedAt
            )
        )
        return response
    }

    private fun PortfolioRiskReservationProjection.toInput() = PortfolioRiskReservationInput(
        otherTotalAmount.strip(), otherEventAmount.strip(), otherMarketAmount.strip(),
        otherLeaderAmount.strip(), otherCategoryAmount.strip(), otherActiveCount, recoveredAtFinal
    )

    private fun resolveCategory(request: PortfolioRiskEvaluationRequest): String? {
        request.category?.trim()?.lowercase()?.takeIf { it in CATEGORIES }?.let { return it }
        request.marketId?.let { marketRepository.findByMarketId(it)?.category?.trim()?.lowercase() }
            ?.takeIf { it in CATEGORIES }?.let { return it }
        val title = request.marketTitle ?: return null
        return CATEGORIES.firstOrNull { LeaderResearchMarketCategoryPatterns.matches(it, title) }
    }

    private fun resolveEventSlug(request: PortfolioRiskEvaluationRequest): String? =
        request.eventSlug?.trim()?.takeIf { it.isNotBlank() }
            ?: request.marketId?.let { marketRepository.findByMarketId(it)?.eventSlug?.trim()?.takeIf(String::isNotBlank) }

    private fun PortfolioRiskDecision.toResponse(): PortfolioRiskEvaluationResponse = PortfolioRiskEvaluationResponse(
        decisionId = requestId,
        policyVersion = policyVersion,
        mode = mode,
        side = side,
        outcome = outcome,
        executionAllowed = executionAllowed,
        rules = gson.fromJson(rulesJson, Array<PortfolioRiskRuleResultDto>::class.java).toList(),
        evaluatedAt = createdAt
    )

    private fun BigDecimal.strip(): String = stripTrailingZeros().toPlainString()

    companion object {
        private const val MODE = "SHADOW"
        private val CATEGORIES = listOf("crypto", "sports", "finance", "politics")
    }
}
