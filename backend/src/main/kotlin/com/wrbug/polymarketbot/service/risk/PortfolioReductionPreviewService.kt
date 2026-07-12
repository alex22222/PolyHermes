package com.wrbug.polymarketbot.service.risk

import com.google.gson.Gson
import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.entity.PortfolioReductionDraft
import com.wrbug.polymarketbot.repository.PortfolioReductionDraftRepository
import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import com.wrbug.polymarketbot.service.accounts.PortfolioExposureService
import com.wrbug.polymarketbot.service.accounts.BridgePositionSellService
import org.springframework.stereotype.Service
import org.springframework.transaction.annotation.Transactional
import java.math.BigDecimal
import java.math.RoundingMode
import java.util.UUID

@Service
class PortfolioReductionPreviewService(
    private val relationService: PortfolioRelationService,
    private val exposureService: PortfolioExposureService,
    private val repository: PortfolioReductionDraftRepository,
    private val gson: Gson,
    private val bridgePositionSellService: BridgePositionSellService,
    private val bridgeTradeRecordRepository: BridgeTradeRecordRepository
) {
    @Transactional
    fun preview(request: PortfolioReductionPreviewRequest, actor: String, now: Long = System.currentTimeMillis()): PortfolioReductionPreviewResponse {
        require(request.accountId > 0) { "accountId 无效" }
        require(request.positionKey.isNotBlank()) { "positionKey 不能为空" }
        val quantity = request.quantity.toBigDecimalOrNull()
            ?: throw IllegalArgumentException("quantity 无效")
        require(quantity > BigDecimal.ZERO) { "quantity 必须大于 0" }

        val relation = relationService.getRelations(request.accountId, now)
        val position = relation.positions.singleOrNull { it.positionKey == request.positionKey }
            ?: throw IllegalArgumentException("持仓不存在或 positionKey 不唯一")
        val availableQuantity = position.quantity.toBigDecimal()
        require(quantity <= availableQuantity) { "减仓数量超过当前持仓" }
        val currentValue = position.currentValue?.toBigDecimalOrNull()
            ?: throw IllegalArgumentException("持仓估值未知，不能生成减仓预览")
        require(availableQuantity > BigDecimal.ZERO) { "当前持仓数量无效" }

        val exposure = exposureService.getExposure(request.accountId)
        require(exposure.account.valuationStatus == "COMPLETE") { "账户估值不完整，不能生成减仓预览" }
        val balance = exposure.account.availableBalance?.toBigDecimalOrNull()
            ?: throw IllegalArgumentException("账户余额未知，不能生成减仓预览")
        val totalAssets = exposure.account.totalAssets?.toBigDecimalOrNull()
            ?: throw IllegalArgumentException("账户总资产未知，不能生成减仓预览")
        val openValue = exposure.account.openPositionsValue.toBigDecimal()
        val proceeds = currentValue.multiply(quantity).divide(availableQuantity, 8, RoundingMode.HALF_UP)
        val draftId = UUID.randomUUID().toString()
        val expiresAt = now + DRAFT_TTL_MS
        val response = PortfolioReductionPreviewResponse(
            draftId = draftId,
            accountId = request.accountId,
            positionKey = position.positionKey,
            marketTitle = position.marketTitle,
            outcome = position.outcome,
            requestedQuantity = quantity.strip(),
            availableQuantity = availableQuantity.strip(),
            estimatedProceeds = proceeds.strip(),
            beforeAvailableBalance = balance.strip(),
            afterAvailableBalance = balance.add(proceeds).strip(),
            beforeOpenPositionsValue = openValue.strip(),
            afterOpenPositionsValue = openValue.subtract(proceeds).max(BigDecimal.ZERO).strip(),
            beforeTotalAssets = totalAssets.strip(),
            afterTotalAssets = totalAssets.strip(),
            impacts = impacts(exposure, position.positionKey, proceeds, totalAssets),
            status = "DRAFT",
            executionEnabled = false,
            createdBy = actor,
            confirmedBy = null,
            confirmedAt = null,
            createdAt = now,
            expiresAt = expiresAt
        )
        repository.save(
            PortfolioReductionDraft(
                draftId = draftId,
                accountId = request.accountId,
                positionKey = position.positionKey,
                quantity = quantity,
                snapshotJson = gson.toJson(response),
                createdBy = actor,
                expiresAt = expiresAt,
                createdAt = now,
                updatedAt = now
            )
        )
        return response
    }

    @Transactional
    fun get(draftId: String, now: Long = System.currentTimeMillis()): PortfolioReductionPreviewResponse {
        val draft = repository.findById(draftId).orElse(null) ?: throw IllegalArgumentException("减仓草案不存在")
        if (draft.status in setOf("DRAFT", "CONFIRMED", "FAILED") && draft.expiresAt <= now) {
            draft.status = "EXPIRED"
            draft.updatedAt = now
            repository.save(draft)
        }
        return response(draft)
    }

    @Transactional
    fun confirm(draftId: String, actor: String, now: Long = System.currentTimeMillis()): PortfolioReductionPreviewResponse {
        val draft = repository.findById(draftId).orElse(null) ?: throw IllegalArgumentException("减仓草案不存在")
        if (draft.status == "CONFIRMED") return response(draft)
        require(draft.status == "DRAFT") { "减仓草案状态不允许确认：${draft.status}" }
        if (draft.expiresAt <= now) {
            draft.status = "EXPIRED"
            draft.updatedAt = now
            repository.save(draft)
            throw IllegalArgumentException("减仓草案已过期，请重新生成预览")
        }
        val livePosition = relationService.getRelations(draft.accountId, now).positions
            .singleOrNull { it.positionKey == draft.positionKey }
            ?: throw IllegalArgumentException("真实持仓已不存在，请重新生成预览")
        val liveQuantity = livePosition.quantity.toBigDecimalOrNull()
            ?: throw IllegalArgumentException("真实持仓数量无效")
        require(liveQuantity >= draft.quantity) { "真实持仓数量已不足，请重新生成预览" }
        require(livePosition.currentValue?.toBigDecimalOrNull() != null) { "真实持仓估值未知，请重新生成预览" }

        draft.status = "CONFIRMED"
        draft.confirmedBy = actor
        draft.confirmedAt = now
        draft.updatedAt = now
        repository.save(draft)
        return response(draft)
    }

    @Transactional
    fun execute(draftId: String, actor: String, now: Long = System.currentTimeMillis()): PortfolioReductionPreviewResponse {
        val draft = repository.findLockedByDraftId(draftId) ?: throw IllegalArgumentException("减仓草案不存在")
        if (draft.status == "SUBMITTED") return response(draft)
        require(draft.status in setOf("CONFIRMED", "FAILED")) { "减仓草案状态不允许执行：${draft.status}" }
        if (draft.expiresAt <= now) {
            draft.status = "EXPIRED"
            draft.updatedAt = now
            repository.save(draft)
            return response(draft)
        }
        val livePosition = relationService.getRelations(draft.accountId, now).positions
            .singleOrNull { it.positionKey == draft.positionKey }
        if (livePosition == null || livePosition.marketId.isNullOrBlank()) {
            return failExecution(draft, actor, now, "真实持仓已不存在或缺少 marketId，请重新生成预览")
        }
        val liveQuantity = livePosition.quantity.toBigDecimalOrNull()
        if (liveQuantity == null || liveQuantity < draft.quantity) {
            return failExecution(draft, actor, now, "真实持仓数量已不足，请重新生成预览")
        }

        val priorRecord = draft.executionExternalTradeId?.let(bridgeTradeRecordRepository::findByExternalTradeId)
        if (priorRecord?.status == "SUCCESS") {
            draft.status = "EXECUTED"
            draft.executionRecordId = priorRecord.id
            draft.executionError = null
            draft.updatedAt = now
            repository.save(draft)
            return response(draft)
        }
        val startNewAttempt = priorRecord?.status == "FAILED"
        if (draft.executionAttempt == 0) draft.executionAttempt = 1
        if (startNewAttempt) draft.executionAttempt += 1
        val idempotencyKey = if (startNewAttempt) {
            "reduction-${draft.draftId}-retry-${draft.executionAttempt}"
        } else draft.executionExternalTradeId ?: "reduction-${draft.draftId}"
        draft.status = "EXECUTING"
        draft.executionRequestedBy = actor
        draft.executionRequestedAt = now
        draft.executionExternalTradeId = idempotencyKey
        draft.executionError = null
        draft.updatedAt = now
        repository.saveAndFlush(draft)

        val result = bridgePositionSellService.sellBridgePosition(
            BridgePositionSellRequest(
                accountId = draft.accountId,
                marketId = livePosition.marketId,
                side = livePosition.outcome,
                orderType = "MARKET",
                quantity = draft.quantity.strip(),
                externalTradeId = idempotencyKey
            )
        )
        return result.fold(
            onSuccess = { bridge ->
                draft.status = "SUBMITTED"
                draft.executionRecordId = bridge.recordId
                draft.executionExternalTradeId = bridge.externalTradeId ?: idempotencyKey
                draft.executionError = null
                draft.updatedAt = System.currentTimeMillis()
                repository.save(draft)
                response(draft)
            },
            onFailure = { error -> failExecution(draft, actor, System.currentTimeMillis(), error.message ?: error.javaClass.simpleName) }
        )
    }

    @Transactional
    fun refresh(draftId: String, now: Long = System.currentTimeMillis()): PortfolioReductionPreviewResponse {
        val draft = repository.findLockedByDraftId(draftId) ?: throw IllegalArgumentException("减仓草案不存在")
        require(draft.status in setOf("SUBMITTED", "EXECUTING", "EXECUTED", "FAILED")) { "减仓草案尚未提交执行" }
        val externalId = draft.executionExternalTradeId ?: return response(draft)
        val record = bridgeTradeRecordRepository.findByExternalTradeId(externalId) ?: return response(draft)
        draft.executionRecordId = record.id
        when (record.status) {
            "SUCCESS" -> {
                draft.status = "EXECUTED"
                draft.executionError = null
            }
            "FAILED" -> {
                draft.status = "FAILED"
                draft.executionError = record.errorMessage ?: "Bridge 执行失败"
            }
            else -> draft.status = "SUBMITTED"
        }
        draft.updatedAt = now
        repository.save(draft)
        return response(draft)
    }

    @Transactional
    fun list(accountId: Long, now: Long = System.currentTimeMillis()): List<PortfolioReductionPreviewResponse> {
        require(accountId > 0) { "accountId 无效" }
        return repository.findByAccountIdOrderByCreatedAtDesc(accountId).take(MAX_LIST_SIZE).map { draft ->
            if (draft.status in setOf("DRAFT", "CONFIRMED", "FAILED") && draft.expiresAt <= now) {
                draft.status = "EXPIRED"
                draft.updatedAt = now
                repository.save(draft)
            }
            response(draft)
        }
    }

    private fun failExecution(draft: PortfolioReductionDraft, actor: String, now: Long, error: String): PortfolioReductionPreviewResponse {
        draft.status = "FAILED"
        draft.executionRequestedBy = actor
        draft.executionRequestedAt = now
        draft.executionError = error
        draft.updatedAt = now
        repository.save(draft)
        return response(draft)
    }

    private fun response(draft: PortfolioReductionDraft) =
        gson.fromJson(draft.snapshotJson, PortfolioReductionPreviewResponse::class.java).copy(
            status = draft.status,
            executionEnabled = draft.status in setOf("CONFIRMED", "FAILED"),
            confirmedBy = draft.confirmedBy,
            confirmedAt = draft.confirmedAt,
            executionRequestedBy = draft.executionRequestedBy,
            executionRequestedAt = draft.executionRequestedAt,
            executionExternalTradeId = draft.executionExternalTradeId,
            executionRecordId = draft.executionRecordId,
            executionError = draft.executionError,
            executionAttempt = draft.executionAttempt
        )

    private fun impacts(
        exposure: PortfolioExposureResponse,
        positionKey: String,
        proceeds: BigDecimal,
        totalAssets: BigDecimal
    ): List<PortfolioReductionDimensionImpactDto> = listOf(
        "LEADER" to exposure.leaders,
        "CATEGORY" to exposure.categories,
        "EVENT" to exposure.events,
        "MARKET" to exposure.markets
    ).flatMap { (dimension, buckets) ->
        val matching = buckets.filter { positionKey in it.positionKeys }
        val denominator = matching.sumOf { it.value.toBigDecimal() }
        matching.map { bucket ->
            val before = bucket.value.toBigDecimal()
            val allocated = if (denominator > BigDecimal.ZERO) {
                proceeds.multiply(before).divide(denominator, 8, RoundingMode.HALF_UP)
            } else BigDecimal.ZERO
            val after = before.subtract(allocated).max(BigDecimal.ZERO)
            PortfolioReductionDimensionImpactDto(
                dimension = dimension,
                key = bucket.key,
                label = bucket.label,
                beforeValue = before.strip(),
                afterValue = after.strip(),
                beforePercent = percent(before, totalAssets),
                afterPercent = percent(after, totalAssets),
                calculationQuality = if (matching.size == 1 && bucket.positionCount == 1) "EXACT" else "ESTIMATED_PRO_RATA"
            )
        }
    }

    private fun percent(value: BigDecimal, total: BigDecimal): String? =
        if (total <= BigDecimal.ZERO) null else value.multiply(BigDecimal("100")).divide(total, 4, RoundingMode.HALF_UP).strip()

    private fun BigDecimal.strip() = stripTrailingZeros().toPlainString()

    companion object {
        private const val DRAFT_TTL_MS = 10 * 60 * 1000L
        private const val MAX_LIST_SIZE = 100
    }
}
