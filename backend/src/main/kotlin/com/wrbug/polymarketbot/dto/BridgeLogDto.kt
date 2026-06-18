package com.wrbug.polymarketbot.dto

/**
 * 桥接日志内容请求
 */
data class BridgeLogContentRequest(
    val name: String,
    val lines: Int? = 200
)

/**
 * 桥接日志内容响应
 */
data class BridgeLogContentResponse(
    val name: String,
    val content: String,
    val lines: Int
)

/**
 * 桥接日志信息
 */
data class BridgeLogInfo(
    val name: String,
    val displayName: String,
    val path: String
)
