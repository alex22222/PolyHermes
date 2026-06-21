package com.wrbug.polymarketbot.dto

/**
 * 桥接交易记录列表请求
 */
data class BridgeTradeRecordListRequest(
    val bridgeId: String? = null,
    val status: String? = null,
    val page: Int = 1,
    val size: Int = 20
)

/**
 * 桥接交易记录详情请求
 */
data class BridgeTradeRecordDetailRequest(
    val id: Long
)

/**
 * 桥接交易统计请求
 */
data class BridgeTradeStatisticsRequest(
    val bridgeId: String? = null,
    val startTime: Long? = null,
    val endTime: Long? = null
)

/**
 * 桥接交易记录列表响应
 */
data class BridgeTradeRecordListResponse(
    val list: List<BridgeTradeRecordDto>,
    val total: Long,
    val page: Int,
    val size: Int
)

/**
 * 桥接交易统计响应
 */
data class BridgeTradeStatisticsResponse(
    val bridgeId: String?,
    val totalTrades: Long,
    val successTrades: Long,
    val failedTrades: Long,
    val pendingTrades: Long,
    val buyTrades: Long,
    val sellTrades: Long,
    val successBuyTrades: Long,
    val successSellTrades: Long,
    val successBuyAmount: String,
    val successSellAmount: String,
    val totalFees: String,
    val netCashflow: String,
    val totalPnl: String,
    val successRate: String,
    val avgSuccessTradeAmount: String,
    val openPositionCount: Long,
    val openPositionQuantity: String,
    val openPositionValue: String,
    val openPositionPnl: String,
    val maxPositionProfit: String,
    val maxPositionLoss: String,
    val statisticsSource: String,
    val latestTradeAt: Long?,
    val latestBuyAt: Long?,
    val latestSellAt: Long?,
    val latestSnapshotSyncedAt: Long?
)

/**
 * 桥接交易记录 DTO
 */
data class BridgeTradeRecordDto(
    val id: Long,
    val bridgeId: String,
    val externalTradeId: String?,
    val marketId: String,
    val marketTitle: String?,
    val side: String,
    val outcome: String?,
    val outcomeIndex: Int?,
    val quantity: String,
    val price: String,
    val amount: String,
    val fee: String,
    val status: String,
    val errorMessage: String?,
    val rawPayload: String?,
    val executedAt: Long?,
    val createdAt: Long,
    val updatedAt: Long,
    val ledgerNetQuantity: String? = null,
    val snapshotQuantity: String? = null,
    val snapshotSyncedAt: Long? = null,
    val positionMismatch: Boolean = false,
    val positionMismatchReason: String? = null
)
