package com.wrbug.polymarketbot.dto

import com.google.gson.annotations.SerializedName

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
 * 按跟单关系查询桥接交易记录请求
 */
data class BridgeTradeRecordByCopyTradingRequest(
    val copyTradingId: Long,
    val page: Int = 1,
    val size: Int = 20
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
 * Bridge 执行链路审计请求
 */
data class BridgeAuditRequest(
    val sinceMs: Long? = null,
    val limit: Int = 500,
    val failureLimit: Int = 100,
    val portfolioTimeout: Int = 90
)

/**
 * Bridge runtime 状态响应
 */
data class BridgeRuntimeStatusResponse(
    val ready: Boolean? = null,
    @SerializedName("logged_in") val loggedIn: Boolean? = null,
    @SerializedName("last_error") val lastError: String? = null,
    @SerializedName("copy_trading_account_id") val copyTradingAccountId: Long? = null,
    @SerializedName("copy_trading_config_count") val copyTradingConfigCount: Long? = null
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
 * Bridge 执行链路审计响应
 * 字段保持为只读监控快照，来源为 polymtrade-bridge /audit。
 */
data class BridgeAuditResponse(
    @SerializedName("bridge_id") val bridgeId: String? = null,
    @SerializedName("synced_at") val syncedAt: Long? = null,
    val metrics: BridgeAuditMetrics? = null,
    @SerializedName("monitor_status") val monitorStatus: BridgeAuditMonitorStatus? = null,
    @SerializedName("runtime_status") val runtimeStatus: BridgeRuntimeStatusResponse? = null,
    @SerializedName("reconciliation_suggestions") val reconciliationSuggestions: List<BridgeAuditReconciliationSuggestion> = emptyList(),
    @SerializedName("next_action_candidates") val nextActionCandidates: List<BridgeAuditBucket> = emptyList()
)

data class BridgeAuditMetrics(
    @SerializedName("records_checked") val recordsChecked: Long? = null,
    @SerializedName("raw_records_checked") val rawRecordsChecked: Long? = null,
    @SerializedName("since_ms") val sinceMs: Long? = null,
    @SerializedName("latest_raw_record_time_ms") val latestRawRecordTimeMs: Long? = null,
    @SerializedName("latest_record_time_ms") val latestRecordTimeMs: Long? = null,
    @SerializedName("latest_failure_time_ms") val latestFailureTimeMs: Long? = null,
    @SerializedName("portfolio_position_count") val portfolioPositionCount: Long? = null,
    @SerializedName("pending_timeout_count") val pendingTimeoutCount: Long? = null,
    @SerializedName("recent_failure_count") val recentFailureCount: Long? = null,
    @SerializedName("success_position_mismatch_count") val successPositionMismatchCount: Long? = null,
    @SerializedName("active_success_position_mismatch_count") val activeSuccessPositionMismatchCount: Long? = null,
    @SerializedName("fresh_success_position_mismatch_count") val freshSuccessPositionMismatchCount: Long? = null,
    @SerializedName("stale_success_position_mismatch_count") val staleSuccessPositionMismatchCount: Long? = null,
    @SerializedName("reconciled_success_position_mismatch_count") val reconciledSuccessPositionMismatchCount: Long? = null,
    @SerializedName("unresolved_success_position_mismatch_count") val unresolvedSuccessPositionMismatchCount: Long? = null,
    @SerializedName("reconciliation_suggestion_count") val reconciliationSuggestionCount: Long? = null,
    @SerializedName("failure_bucket_count") val failureBucketCount: Long? = null,
    @SerializedName("actionable_failure_bucket_count") val actionableFailureBucketCount: Long? = null
)

data class BridgeAuditMonitorStatus(
    val status: String? = null,
    val message: String? = null,
    @SerializedName("actionable_failure_bucket_count") val actionableFailureBucketCount: Long? = null,
    @SerializedName("actionable_issue_count") val actionableIssueCount: Long? = null,
    @SerializedName("pending_timeout_count") val pendingTimeoutCount: Long? = null,
    @SerializedName("recent_failure_count") val recentFailureCount: Long? = null,
    @SerializedName("active_success_position_mismatch_count") val activeSuccessPositionMismatchCount: Long? = null,
    @SerializedName("latest_raw_record_time_ms") val latestRawRecordTimeMs: Long? = null,
    @SerializedName("latest_record_time_ms") val latestRecordTimeMs: Long? = null,
    @SerializedName("latest_failure_time_ms") val latestFailureTimeMs: Long? = null,
    @SerializedName("since_ms") val sinceMs: Long? = null,
    @SerializedName("runtime_block_reasons") val runtimeBlockReasons: List<String> = emptyList(),
    @SerializedName("next_action_buckets") val nextActionBuckets: List<BridgeAuditBucket> = emptyList()
)

data class BridgeAuditBucket(
    val bucket: String? = null,
    val count: Long? = null,
    @SerializedName("covered_count") val coveredCount: Long? = null,
    @SerializedName("uncovered_count") val uncoveredCount: Long? = null,
    val priority: Int? = null,
    val actionability: String? = null,
    @SerializedName("next_action") val nextAction: String? = null,
    @SerializedName("sample_record_ids") val sampleRecordIds: List<Long> = emptyList(),
    @SerializedName("uncovered_sample_record_ids") val uncoveredSampleRecordIds: List<Long> = emptyList(),
    @SerializedName("sample_markets") val sampleMarkets: List<String> = emptyList(),
    @SerializedName("coverage_ids") val coverageIds: List<String> = emptyList(),
    @SerializedName("latest_created_at") val latestCreatedAt: Long? = null
)

data class BridgeAuditReconciliationSuggestion(
    val key: String? = null,
    val status: String? = null,
    val confidence: String? = null,
    val reason: String? = null,
    @SerializedName("market_id") val marketId: String? = null,
    @SerializedName("market_title") val marketTitle: String? = null,
    val outcome: String? = null,
    @SerializedName("outcome_index") val outcomeIndex: Int? = null,
    @SerializedName("expected_quantity") val expectedQuantity: String? = null,
    @SerializedName("actual_quantity") val actualQuantity: String? = null,
    @SerializedName("latest_record_id") val latestRecordId: Long? = null,
    @SerializedName("latest_record_updated_at") val latestRecordUpdatedAt: Long? = null,
    @SerializedName("age_ms") val ageMs: Long? = null,
    @SerializedName("contributing_record_ids") val contributingRecordIds: List<Long> = emptyList(),
    @SerializedName("annotation_payload") val annotationPayload: BridgeAuditReconciliationPayload? = null
)

data class BridgeAuditReconciliationPayload(
    val status: String? = null,
    val note: String? = null,
    val actor: String? = null,
    @SerializedName("market_id") val marketId: String? = null,
    @SerializedName("market_title") val marketTitle: String? = null,
    val outcome: String? = null,
    @SerializedName("outcome_index") val outcomeIndex: Int? = null
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
