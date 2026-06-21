package com.wrbug.polymarketbot.dto

/**
 * Leader Scanner 配置项
 */
data class LeaderScannerConfigDto(
    val category: String,
    val seedWallets: List<String>,
    val description: String? = null
)

/**
 * Leader Scanner 全局配置
 */
data class LeaderScannerGlobalConfigDto(
    val analysisWindowDays: Int,
    val seedWallets: Map<String, List<String>>,
    val generalSeedWallets: List<String>
)

/**
 * 更新 seed wallets 请求
 */
data class UpdateLeaderScannerSeedWalletsRequest(
    val category: String,
    val wallets: List<String>
)
