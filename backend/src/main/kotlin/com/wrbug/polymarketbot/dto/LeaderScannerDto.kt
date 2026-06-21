package com.wrbug.polymarketbot.dto

/**
 * Leader 扫描触发请求
 */
data class LeaderScanTriggerRequest(
    val category: String? = null,  // 指定类别扫描，null 表示全部
    val dryRun: Boolean = false  //  true 只预览不写入
)

/**
 * Leader 扫描状态响应
 */
data class LeaderScanStatusDto(
    val isRunning: Boolean,
    val lastScanAt: Long?,
    val lastScanDurationMs: Long?,
    val lastScanResult: String?,
    val nextScheduledScan: String? = null,
    val nextScheduledDiscovery: String? = "每小时 00 分"
)

/**
 * Leader 扫描结果项
 */
data class LeaderScanResultItem(
    val leaderAddress: String,
    val leaderName: String? = null,
    val category: String?,
    val totalTrades: Int?,
    val winRate: Double?,
    val totalPnl: String?,
    val totalVolume: String?,
    val avgTradeSize: String? = null,
    val lastTradeAt: Long? = null,
    val activityScore: Double?,
    val smartMoneyRank: Int?,
    val source: String
)

/**
 * Leader 扫描预览响应
 */
data class LeaderScanPreviewResponse(
    val category: String,
    val candidates: List<LeaderScanResultItem>,
    val marketCount: Int,
    val analyzedWalletCount: Int
)

/**
 * Leader 批量扫描响应
 */
data class LeaderScanBatchResponse(
    val success: Boolean,
    val message: String?,
    val createdCount: Int = 0,
    val updatedCount: Int = 0,
    val categories: List<String> = emptyList(),
    val previews: List<LeaderScanPreviewResponse> = emptyList(),
    val totalCandidateCount: Int = 0,
    val totalAnalyzedWalletCount: Int = 0,
    val durationMs: Long? = null
)

/**
 * Leader 候选发现响应
 */
data class LeaderScanDiscoveryResponse(
    val category: String,
    val discoveredCount: Int,
    val pendingCount: Long,
    val message: String
)

/**
 * 候选池条目 DTO
 */
data class LeaderScannerCandidatePoolDto(
    val id: Long,
    val category: String,
    val normalizedWallet: String,
    val source: String,
    val sourceDetail: String?,
    val discoveryScore: Int,
    val firstDiscoveredAt: Long,
    val lastSeenAt: Long,
    val analysisState: String,
    val analyzedAt: Long?,
    val promotedAt: Long?,
    val lastAnalysisResult: String?,
    val createdAt: Long,
    val updatedAt: Long
)

/**
 * 候选池查询请求
 */
data class LeaderScannerCandidatePoolQueryRequest(
    val category: String? = null,
    val analysisState: String? = null,
    val wallet: String? = null,
    val page: Int = 1,
    val size: Int = 20
)

/**
 * 候选池查询响应
 */
data class LeaderScannerCandidatePoolQueryResponse(
    val list: List<LeaderScannerCandidatePoolDto>,
    val total: Long,
    val page: Int,
    val size: Int
)
