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
 * 桥接交易记录列表响应
 */
data class BridgeTradeRecordListResponse(
    val list: List<BridgeTradeRecordDto>,
    val total: Long,
    val page: Int,
    val size: Int
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
    val updatedAt: Long
)
