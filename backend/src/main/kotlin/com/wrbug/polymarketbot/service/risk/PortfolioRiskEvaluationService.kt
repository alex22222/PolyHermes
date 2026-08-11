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
    private val relationService: PortfolioRelationService,
    private val relationClassifier: PortfolioRelationClassifier,
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
        val relation = if (side == "BUY") {
            buildRelationInput(request, amount, category, eventSlug, evaluatedAt)
        } else null
        val totalAssets = exposure?.account?.totalAssets?.toBigDecimalOrNull()
        val daily = if (side == "BUY" && exposure != null && totalAssets != null && totalAssets > BigDecimal.ZERO &&
            exposure.account.availableBalance?.toBigDecimalOrNull() != null && exposure.account.valuationStatus == "COMPLETE"
        ) dailyMetricsService.calculate(request.accountId, exposure.account.walletAddress, totalAssets) else null
        val snapshot = PortfolioRiskInputSnapshot(
            request = request.copy(side = side, amount = amount.strip()),
            resolvedCategory = category,
            resolvedEventSlug = eventSlug,
            exposure = exposure,
            relation = relation,
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

    private fun buildRelationInput(
        request: PortfolioRiskEvaluationRequest,
        amount: BigDecimal,
        category: String?,
        eventSlug: String?,
        now: Long
    ): PortfolioRiskRelationInput {
        val marketId = request.marketId?.trim()?.takeIf { it.isNotBlank() }
            ?: return PortfolioRiskRelationInput(false, "请求缺少 marketId，无法识别重复或相关仓位")
        val outcome = request.outcome?.trim()?.takeIf { it.isNotBlank() }
            ?: return PortfolioRiskRelationInput(false, "请求缺少 outcome，无法识别重复或相关仓位")
        val marketTitle = request.marketTitle?.trim()?.takeIf { it.isNotBlank() } ?: marketId
        val resolvedCategory = category?.takeIf { it.isNotBlank() }
            ?: return PortfolioRiskRelationInput(false, "请求缺少领域归因，无法识别跨市场相关仓位")
        val resolvedEventSlug = eventSlug?.takeIf { it.isNotBlank() }
            ?: return PortfolioRiskRelationInput(false, "请求缺少 eventSlug，无法识别事件内相关仓位")
        val existing = relationService.getRelations(request.accountId, now).positions.map {
            PortfolioRelationPosition(
                positionKey = it.positionKey,
                marketId = it.marketId,
                eventSlug = it.eventSlug,
                outcome = it.outcome,
                category = it.category,
                marketTitle = it.marketTitle,
                currentValue = it.currentValue?.toBigDecimalOrNull(),
                quantity = it.quantity.toBigDecimalOrNull() ?: BigDecimal.ZERO,
                firstObservedAt = it.firstObservedAt,
                marketEndAt = it.marketEndAt
            )
        }
        val candidateKey = "CANDIDATE_BUY|$marketId|${outcome.uppercase()}"
        val marketEndAt = request.marketId?.let { marketRepository.findByMarketId(it)?.endDate }
        val candidate = PortfolioRelationPosition(
            positionKey = candidateKey,
            marketId = marketId,
            eventSlug = resolvedEventSlug,
            outcome = outcome,
            category = resolvedCategory,
            marketTitle = marketTitle,
            currentValue = amount,
            quantity = BigDecimal.ONE,
            firstObservedAt = now,
            marketEndAt = marketEndAt
        )
        val relations = relationClassifier.classify(existing + candidate, now)
            .filter { candidateKey in it.positionKeys }
        val counts = relations.groupingBy { it.type }.eachCount().toSortedMap()
        val valueByType = relations.groupBy { it.type }.mapValues { (_, items) ->
            items.mapNotNull { it.relatedValue?.toBigDecimalOrNull() }.fold(BigDecimal.ZERO, BigDecimal::add).strip()
        }.toSortedMap()
        val blocking = BLOCKING_RELATION_TYPES.filter { (counts[it] ?: 0) > 0 }
        return PortfolioRiskRelationInput(
            available = true,
            candidatePositionKey = candidateKey,
            relationCount = relations.size,
            countsByType = counts,
            relatedValueByType = valueByType,
            blockingTypes = blocking,
            unknownCount = counts["UNKNOWN"] ?: 0
        )
    }

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
        private val BLOCKING_RELATION_TYPES = listOf("DUPLICATE", "PSEUDO_HEDGE", "RELATED")
    }
}
