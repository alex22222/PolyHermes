package com.wrbug.polymarketbot.service.bridge

import com.wrbug.polymarketbot.dto.BridgeTradeRecordByCopyTradingRequest
import com.wrbug.polymarketbot.dto.BridgeTradeRecordDetailRequest
import com.wrbug.polymarketbot.dto.BridgeTradeRecordDto
import com.wrbug.polymarketbot.dto.BridgeTradeRecordListRequest
import com.wrbug.polymarketbot.dto.BridgeTradeRecordListResponse
import com.wrbug.polymarketbot.dto.BridgeTradeStatisticsRequest
import com.wrbug.polymarketbot.dto.BridgeTradeStatisticsResponse
import com.wrbug.polymarketbot.entity.BridgePositionSnapshot
import com.wrbug.polymarketbot.entity.BridgeTradeRecord
import com.wrbug.polymarketbot.repository.BridgePositionSnapshotRepository
import com.wrbug.polymarketbot.repository.BridgeTradeRecordRepository
import com.wrbug.polymarketbot.repository.BridgeWebhookLogRepository
import com.wrbug.polymarketbot.repository.CopyTradingRepository
import com.wrbug.polymarketbot.repository.LeaderRepository
import org.slf4j.LoggerFactory
import org.springframework.data.domain.Page
import org.springframework.data.domain.PageRequest
import org.springframework.data.domain.Sort
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode

/**
 * 外部桥交易记录服务
 */
@Service
class BridgeTradeRecordService(
    private val bridgeTradeRecordRepository: BridgeTradeRecordRepository,
    private val bridgePositionSnapshotRepository: BridgePositionSnapshotRepository,
    private val bridgePortfolioClient: BridgePortfolioClient,
    private val copyTradingRepository: CopyTradingRepository,
    private val leaderRepository: LeaderRepository,
    private val bridgeWebhookLogRepository: BridgeWebhookLogRepository
) {
    private val logger = LoggerFactory.getLogger(BridgeTradeRecordService::class.java)
    private val quantityTolerance = BigDecimal("0.01")

    /**
     * 查询桥接交易记录列表
     */
    fun getBridgeTradeRecordList(request: BridgeTradeRecordListRequest): Result<BridgeTradeRecordListResponse> {
        return try {
            val pageRequest = PageRequest.of(
                (request.page - 1).coerceAtLeast(0),
                request.size.coerceIn(1, 100),
                Sort.by(Sort.Order.desc("createdAt"))
            )

            val page: Page<BridgeTradeRecord> = when {
                !request.bridgeId.isNullOrBlank() && !request.status.isNullOrBlank() -> {
                    bridgeTradeRecordRepository.findByBridgeIdAndStatus(request.bridgeId, request.status, pageRequest)
                }
                !request.bridgeId.isNullOrBlank() -> {
                    bridgeTradeRecordRepository.findByBridgeId(request.bridgeId, pageRequest)
                }
                !request.status.isNullOrBlank() -> {
                    bridgeTradeRecordRepository.findByStatus(request.status, pageRequest)
                }
                else -> {
                    bridgeTradeRecordRepository.findAll(pageRequest)
                }
            }

            val positionViews = buildPositionViews(page.content)
            val list = page.content.map { it.toDto(positionViews[it.positionKey()]) }

            Result.success(
                BridgeTradeRecordListResponse(
                    list = list,
                    total = page.totalElements,
                    page = request.page,
                    size = request.size
                )
            )
        } catch (e: Exception) {
            logger.error("查询桥接交易记录列表失败", e)
            Result.failure(e)
        }
    }

    /**
     * 按跟单关系查询桥接交易记录
     * 通过 copyTrading -> leader -> webhook 日志中的 conditionId -> bridge_trade_record
     */
    fun getBridgeTradeRecordListByCopyTrading(request: BridgeTradeRecordByCopyTradingRequest): Result<BridgeTradeRecordListResponse> {
        return try {
            val copyTrading = copyTradingRepository.findById(request.copyTradingId).orElse(null)
                ?: return Result.failure(IllegalArgumentException("跟单关系不存在: ${request.copyTradingId}"))

            val leader = leaderRepository.findById(copyTrading.leaderId).orElse(null)
                ?: return Result.failure(IllegalArgumentException("Leader 不存在: ${copyTrading.leaderId}"))

            val leaderAddress = leader.leaderAddress
            val conditionIds = bridgeWebhookLogRepository
                .findDistinctConditionIdsByLeaderAddress(leaderAddress)
                .filter { !it.isNullOrBlank() }

            if (conditionIds.isEmpty()) {
                return Result.success(
                    BridgeTradeRecordListResponse(
                        list = emptyList(),
                        total = 0,
                        page = request.page,
                        size = request.size
                    )
                )
            }

            val pageRequest = PageRequest.of(
                (request.page - 1).coerceAtLeast(0),
                request.size.coerceIn(1, 100),
                Sort.by(Sort.Order.desc("createdAt"))
            )

            val page = bridgeTradeRecordRepository.findByBridgeIdAndMarketIdIn(
                "polymtrade-bridge",
                conditionIds,
                pageRequest
            )

            val positionViews = buildPositionViews(page.content)
            val list = page.content.map { it.toDto(positionViews[it.positionKey()]) }

            Result.success(
                BridgeTradeRecordListResponse(
                    list = list,
                    total = page.totalElements,
                    page = request.page,
                    size = request.size
                )
            )
        } catch (e: Exception) {
            logger.error("按跟单关系查询桥接交易记录失败: copyTradingId=${request.copyTradingId}", e)
            Result.failure(e)
        }
    }

    /**
     * 查询桥接交易记录详情
     */
    fun getBridgeTradeRecordDetail(request: BridgeTradeRecordDetailRequest): Result<BridgeTradeRecordDto> {
        return try {
            val record = bridgeTradeRecordRepository.findById(request.id).orElse(null)
                ?: return Result.failure(IllegalArgumentException("桥接交易记录不存在"))

            val positionViews = buildPositionViews(listOf(record))
            Result.success(record.toDto(positionViews[record.positionKey()]))
        } catch (e: Exception) {
            logger.error("查询桥接交易记录详情失败", e)
            Result.failure(e)
        }
    }

    /**
     * 查询桥接交易统计
     */
    fun getBridgeTradeStatistics(request: BridgeTradeStatisticsRequest): Result<BridgeTradeStatisticsResponse> {
        return try {
            val bridgeId = request.bridgeId?.trim()?.takeIf { it.isNotBlank() }
            val allRecords = if (bridgeId != null) {
                bridgeTradeRecordRepository.findByBridgeId(bridgeId)
            } else {
                bridgeTradeRecordRepository.findAll()
            }
            val records = allRecords.filter { record ->
                val tradeTime = record.executedAt ?: record.createdAt
                val afterStart = request.startTime?.let { tradeTime >= it } ?: true
                val beforeEnd = request.endTime?.let { tradeTime <= it } ?: true
                afterStart && beforeEnd
            }

            val successRecords = records.filter { it.status.equals("SUCCESS", ignoreCase = true) }
            val failedRecords = records.filter { it.status.equals("FAILED", ignoreCase = true) }
            val pendingRecords = records.filter { it.status.equals("PENDING", ignoreCase = true) }
            val buyRecords = records.filter { it.side.equals("BUY", ignoreCase = true) }
            val sellRecords = records.filter { it.side.equals("SELL", ignoreCase = true) }
            val successBuyRecords = successRecords.filter { it.side.equals("BUY", ignoreCase = true) }
            val successSellRecords = successRecords.filter { it.side.equals("SELL", ignoreCase = true) }
            val successBuyAmount = successBuyRecords.sumOf { it.amount }
            val successSellAmount = successSellRecords.sumOf { it.amount }
            val totalFees = successRecords.sumOf { it.fee }
            val netCashflow = successSellAmount.subtract(successBuyAmount).subtract(totalFees)
            val avgSuccessTradeAmount = if (successRecords.isNotEmpty()) {
                successRecords.sumOf { it.amount }.divide(BigDecimal(successRecords.size), 8, RoundingMode.HALF_UP)
            } else {
                BigDecimal.ZERO
            }
            val successRate = if (records.isNotEmpty()) {
                BigDecimal(successRecords.size)
                    .multiply(BigDecimal("100"))
                    .divide(BigDecimal(records.size), 4, RoundingMode.HALF_UP)
                    .setScale(2, RoundingMode.HALF_UP)
            } else {
                BigDecimal.ZERO
            }

            val snapshots = if (bridgeId != null) {
                bridgePositionSnapshotRepository.findByBridgeId(bridgeId)
            } else {
                bridgePositionSnapshotRepository.findAll()
            }
            val openSnapshots = snapshots.filter { it.quantity > BigDecimal.ZERO }
            val openPositionQuantity = openSnapshots.sumOf { it.quantity }
            val openPositionValue = openSnapshots.sumOf { it.currentValue ?: BigDecimal.ZERO }
            val openPositionPnl = openSnapshots.sumOf { it.pnl ?: BigDecimal.ZERO }
            val positionPnlValues = openSnapshots.map { it.pnl ?: BigDecimal.ZERO }
            val maxPositionProfit = positionPnlValues.maxOrNull() ?: BigDecimal.ZERO
            val maxPositionLoss = positionPnlValues.minOrNull() ?: BigDecimal.ZERO
            val availableBalance = if (bridgeId == null || bridgeId == "polymtrade-bridge") {
                bridgePortfolioClient.fetchBalance()?.availableBalance
                    ?.let { BigDecimal.valueOf(it).setScale(8, RoundingMode.HALF_UP) }
            } else {
                null
            }
            val estimatedTotalAssets = availableBalance?.add(openPositionValue)

            Result.success(
                BridgeTradeStatisticsResponse(
                    bridgeId = bridgeId,
                    totalTrades = records.size.toLong(),
                    successTrades = successRecords.size.toLong(),
                    failedTrades = failedRecords.size.toLong(),
                    pendingTrades = pendingRecords.size.toLong(),
                    buyTrades = buyRecords.size.toLong(),
                    sellTrades = sellRecords.size.toLong(),
                    successBuyTrades = successBuyRecords.size.toLong(),
                    successSellTrades = successSellRecords.size.toLong(),
                    successBuyAmount = successBuyAmount.toPlainString(),
                    successSellAmount = successSellAmount.toPlainString(),
                    totalFees = totalFees.toPlainString(),
                    netCashflow = netCashflow.toPlainString(),
                    availableBalance = availableBalance?.toPlainString(),
                    estimatedTotalAssets = estimatedTotalAssets?.toPlainString(),
                    totalPnl = openPositionPnl.toPlainString(),
                    successRate = successRate.toPlainString(),
                    avgSuccessTradeAmount = avgSuccessTradeAmount.toPlainString(),
                    openPositionCount = openSnapshots.size.toLong(),
                    openPositionQuantity = openPositionQuantity.toPlainString(),
                    openPositionValue = openPositionValue.toPlainString(),
                    openPositionPnl = openPositionPnl.toPlainString(),
                    maxPositionProfit = maxPositionProfit.toPlainString(),
                    maxPositionLoss = maxPositionLoss.toPlainString(),
                    statisticsSource = "bridge_position_snapshot",
                    latestTradeAt = records.maxOfOrNull { it.executedAt ?: it.createdAt },
                    latestBuyAt = buyRecords.maxOfOrNull { it.executedAt ?: it.createdAt },
                    latestSellAt = sellRecords.maxOfOrNull { it.executedAt ?: it.createdAt },
                    latestSnapshotSyncedAt = openSnapshots.maxOfOrNull { it.syncedAt }
                )
            )
        } catch (e: Exception) {
            logger.error("查询桥接交易统计失败", e)
            Result.failure(e)
        }
    }

    private fun BridgeTradeRecord.toDto(positionView: PositionView? = null): BridgeTradeRecordDto {
        val exposePositionMismatch = this.status == "SUCCESS" && positionView?.positionMismatch == true
        return BridgeTradeRecordDto(
            id = this.id!!,
            bridgeId = this.bridgeId,
            externalTradeId = this.externalTradeId,
            marketId = this.marketId,
            marketTitle = this.marketTitle,
            side = this.side,
            outcome = this.outcome,
            outcomeIndex = this.outcomeIndex,
            quantity = this.quantity.toPlainString(),
            price = this.price.toPlainString(),
            amount = this.amount.toPlainString(),
            fee = this.fee.toPlainString(),
            status = this.status,
            errorMessage = this.errorMessage,
            rawPayload = this.rawPayload,
            ledgerNetQuantity = positionView?.ledgerNetQuantity?.toPlainString(),
            snapshotQuantity = positionView?.snapshotQuantity?.toPlainString(),
            snapshotSyncedAt = positionView?.snapshotSyncedAt,
            positionMismatch = exposePositionMismatch,
            positionMismatchReason = if (exposePositionMismatch) positionView?.positionMismatchReason else null,
            executedAt = this.executedAt,
            createdAt = this.createdAt,
            updatedAt = this.updatedAt
        )
    }

    private fun buildPositionViews(records: List<BridgeTradeRecord>): Map<PositionKey, PositionView> {
        if (records.isEmpty()) return emptyMap()

        val bridgeIds = records.map { it.bridgeId }.distinct()
        val snapshots = bridgeIds.flatMap { bridgePositionSnapshotRepository.findByBridgeId(it) }
        val successRecords = bridgeIds.flatMap { bridgeTradeRecordRepository.findByBridgeIdAndStatus(it, "SUCCESS") }

        val ledgerByKey = mutableMapOf<PositionKey, BigDecimal>()
        successRecords.forEach { record ->
            val key = record.positionKey()
            val signedQuantity = if (record.side.equals("SELL", ignoreCase = true)) {
                record.quantity.negate()
            } else {
                record.quantity
            }
            ledgerByKey[key] = (ledgerByKey[key] ?: BigDecimal.ZERO).add(signedQuantity)
        }

        return records.associate { record ->
            val key = record.positionKey()
            val ledgerQuantity = ledgerByKey[key] ?: BigDecimal.ZERO
            val snapshot = snapshots.find { it.matches(record) }
            val snapshotQuantity = snapshot?.quantity ?: BigDecimal.ZERO
            val mismatch = record.status == "SUCCESS" &&
                ledgerQuantity.abs() > quantityTolerance &&
                ledgerQuantity.subtract(snapshotQuantity).abs() > quantityTolerance
            val reason = if (mismatch) {
                "success_position_mismatch"
            } else {
                null
            }
            key to PositionView(
                ledgerNetQuantity = ledgerQuantity,
                snapshotQuantity = snapshotQuantity,
                snapshotSyncedAt = snapshot?.syncedAt,
                positionMismatch = mismatch,
                positionMismatchReason = reason
            )
        }
    }

    private fun BridgePositionSnapshot.matches(record: BridgeTradeRecord): Boolean {
        if (!bridgeId.equals(record.bridgeId, ignoreCase = true)) return false
        if (!side.equals(record.outcome ?: "", ignoreCase = true)) return false

        val snapshotMarketId = marketId?.trim()?.lowercase().orEmpty()
        val recordMarketId = record.marketId.trim().lowercase()
        if (snapshotMarketId.isNotBlank() && snapshotMarketId == recordMarketId) return true

        val snapshotTitle = marketTitle.trim().lowercase()
        val recordTitle = record.marketTitle?.trim()?.lowercase().orEmpty()
        return snapshotTitle.isNotBlank() && snapshotTitle == recordTitle
    }

    private fun BridgeTradeRecord.positionKey(): PositionKey {
        return PositionKey(
            bridgeId = bridgeId.trim().lowercase(),
            marketId = marketId.trim().lowercase(),
            marketTitle = marketTitle?.trim()?.lowercase().orEmpty(),
            outcome = outcome?.trim()?.lowercase().orEmpty(),
            outcomeIndex = outcomeIndex
        )
    }

    private data class PositionKey(
        val bridgeId: String,
        val marketId: String,
        val marketTitle: String,
        val outcome: String,
        val outcomeIndex: Int?
    )

    private data class PositionView(
        val ledgerNetQuantity: BigDecimal,
        val snapshotQuantity: BigDecimal,
        val snapshotSyncedAt: Long?,
        val positionMismatch: Boolean,
        val positionMismatchReason: String?
    )
}
