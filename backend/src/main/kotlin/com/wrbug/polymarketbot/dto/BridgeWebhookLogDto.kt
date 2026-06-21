package com.wrbug.polymarketbot.dto

/**
 * Webhook 日志列表请求
 */
data class BridgeWebhookLogListRequest(
    val status: String? = null,
    val page: Int = 1,
    val size: Int = 20
)

/**
 * Webhook 日志列表响应
 */
data class BridgeWebhookLogListResponse(
    val list: List<BridgeWebhookLogDto>,
    val total: Long,
    val page: Int,
    val size: Int
)

/**
 * Webhook 日志 DTO
 */
data class BridgeWebhookLogDto(
    val id: Long,
    val bridgeId: String,
    val event: String,
    val leaderAddress: String?,
    val leaderName: String?,
    val transactionHash: String?,
    val conditionId: String?,
    val marketSlug: String?,
    val side: String?,
    val outcome: String?,
    val requestBody: String?,
    val responseBody: String?,
    val statusCode: Int?,
    val status: String,
    val errorMessage: String?,
    val createdAt: Long,
    val updatedAt: Long
)
