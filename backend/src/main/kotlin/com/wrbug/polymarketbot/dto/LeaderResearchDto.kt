package com.wrbug.polymarketbot.dto

data class LeaderResearchRunRequest(
    val dryRun: Boolean = false,
    val triggerType: String = "MANUAL"
)

data class LeaderResearchScannerPoolImportRequest(
    val dryRun: Boolean = false,
    val politicsLimit: Int = 350,
    val financeLimit: Int = 350,
    val sportsLimit: Int = 150,
    val cryptoLimit: Int = 150,
    val onlyPending: Boolean = true,
    val minDiscoveryScore: Int? = null,
    val requireActivityQuality: Boolean = false,
    val minActivityEvents: Int = 20,
    val minActivityDistinctMarkets: Int = 5,
    val minActivityBuyEvents: Int = 3,
    val minActivitySellEvents: Int = 2,
    val minActivitySafePriceRatio: String = "0.30",
    val maxActivityTailPriceRatio: String = "0.45"
)

data class LeaderResearchScannerPoolImportCategoryDto(
    val category: String,
    val requestedLimit: Int,
    val selectedCount: Int,
    val createdCount: Int,
    val updatedCount: Int,
    val skippedLockedCount: Int,
    val skippedExistingCount: Int
)

data class LeaderResearchScannerPoolImportPreviewItemDto(
    val category: String,
    val wallet: String,
    val source: String,
    val discoveryScore: Int,
    val action: String,
    val sourceEvidence: String
)

data class LeaderResearchScannerPoolImportResponse(
    val dryRun: Boolean,
    val requestedTotal: Int,
    val selectedTotal: Int,
    val createdTotal: Int,
    val updatedTotal: Int,
    val skippedLockedTotal: Int,
    val skippedExistingTotal: Int,
    val categories: List<LeaderResearchScannerPoolImportCategoryDto>,
    val previewItems: List<LeaderResearchScannerPoolImportPreviewItemDto>
)

data class LeaderResearchActivityScoreRequest(
    val states: List<String> = listOf("DISCOVERED", "CANDIDATE"),
    val force: Boolean = false
)

data class LeaderResearchActivityScoreResponse(
    val scoreVersion: String,
    val scannedCount: Int,
    val scoredCount: Int,
    val skippedCount: Int,
    val riskFlagCounts: Map<String, Int>,
    val categoryCounts: Map<String, Int>
)

data class LeaderResearchActivitySourceImportRequest(
    val dryRun: Boolean = false,
    val categories: List<String> = listOf("politics", "finance"),
    val limitPerCategory: Int = 100,
    val lookbackDays: Int = 30,
    val minEvents: Int = 12,
    val minDistinctMarkets: Int = 3,
    val minBuyEvents: Int = 3,
    val minSellEvents: Int = 2,
    val minSafePriceRatio: String = "0.25",
    val maxTailPriceRatio: String = "0.45"
)

data class LeaderResearchActivitySourceCategoryDto(
    val category: String,
    val selectedCount: Int,
    val createdCount: Int,
    val updatedCount: Int,
    val skippedExistingCount: Int,
    val skippedLockedCount: Int
)

data class LeaderResearchActivitySourcePreviewItemDto(
    val category: String,
    val wallet: String,
    val action: String,
    val totalEvents: Long,
    val distinctMarkets: Long,
    val buyEvents: Long,
    val sellEvents: Long,
    val safePriceEvents: Long,
    val tailPriceEvents: Long,
    val avgAmount: String,
    val totalAmount: String,
    val lastEventTime: Long?,
    val sourceEvidence: String
)

data class LeaderResearchActivitySourceImportResponse(
    val dryRun: Boolean,
    val requestedCategories: List<String>,
    val selectedTotal: Int,
    val createdTotal: Int,
    val updatedTotal: Int,
    val skippedExistingTotal: Int,
    val skippedLockedTotal: Int,
    val categories: List<LeaderResearchActivitySourceCategoryDto>,
    val previewItems: List<LeaderResearchActivitySourcePreviewItemDto>
)

data class LeaderResearchMarketPeerSourceImportRequest(
    val dryRun: Boolean = true,
    val categories: List<String> = listOf("politics", "finance"),
    val limitPerCategory: Int = 50,
    val lookbackDays: Int = 60,
    val hotMarketLimit: Int = 40,
    val minMarketEvents: Int = 25,
    val minMarketWallets: Int = 20,
    val minEvents: Int = 8,
    val minDistinctMarkets: Int = 2,
    val minBuyEvents: Int = 2,
    val minSellEvents: Int = 1,
    val minSafePriceRatio: String = "0.20",
    val maxTailPriceRatio: String = "0.50"
)

data class LeaderResearchMarketPeerSourceCategoryDto(
    val category: String,
    val selectedCount: Int,
    val createdCount: Int,
    val updatedCount: Int,
    val skippedExistingCount: Int,
    val skippedLockedCount: Int
)

data class LeaderResearchMarketPeerSourcePreviewItemDto(
    val category: String,
    val wallet: String,
    val action: String,
    val totalEvents: Long,
    val distinctMarkets: Long,
    val buyEvents: Long,
    val sellEvents: Long,
    val safePriceEvents: Long,
    val tailPriceEvents: Long,
    val avgAmount: String,
    val totalAmount: String,
    val lastEventTime: Long?,
    val topMarkets: List<String>,
    val sourceEvidence: String
)

data class LeaderResearchMarketPeerSourceImportResponse(
    val dryRun: Boolean,
    val requestedCategories: List<String>,
    val selectedTotal: Int,
    val createdTotal: Int,
    val updatedTotal: Int,
    val skippedExistingTotal: Int,
    val skippedLockedTotal: Int,
    val categories: List<LeaderResearchMarketPeerSourceCategoryDto>,
    val previewItems: List<LeaderResearchMarketPeerSourcePreviewItemDto>
)

data class LeaderResearchExternalAnalyticsImportItemDto(
    val wallet: String,
    val category: String,
    val sourceName: String = "",
    val externalRank: Int? = null,
    val externalScore: String? = null,
    val note: String? = null
)

data class LeaderResearchExternalAnalyticsImportRequest(
    val dryRun: Boolean = true,
    val items: List<LeaderResearchExternalAnalyticsImportItemDto> = emptyList(),
    val defaultCategory: String = "finance",
    val defaultSourceName: String = "external_analytics",
    val maxItems: Int = 500
)

data class LeaderResearchExternalAnalyticsImportPreviewItemDto(
    val wallet: String,
    val category: String,
    val sourceName: String,
    val action: String,
    val externalRank: Int?,
    val externalScore: String?,
    val sourceEvidence: String
)

data class LeaderResearchExternalAnalyticsImportResponse(
    val dryRun: Boolean,
    val requestedTotal: Int,
    val selectedTotal: Int,
    val createdTotal: Int,
    val updatedTotal: Int,
    val skippedInvalidTotal: Int,
    val skippedExistingTotal: Int,
    val skippedLockedTotal: Int,
    val previewItems: List<LeaderResearchExternalAnalyticsImportPreviewItemDto>
)

data class LeaderResearchOfficialLeaderboardImportRequest(
    val dryRun: Boolean = true,
    val categories: List<String> = listOf("politics", "finance"),
    val timePeriods: List<String> = listOf("MONTH"),
    val orderBys: List<String> = listOf("PNL"),
    val limitPerPage: Int = 50,
    val maxPagesPerQuery: Int = 2,
    val maxItems: Int = 500
)

data class LeaderResearchOfficialLeaderboardFetchDto(
    val category: String,
    val timePeriod: String,
    val orderBy: String,
    val requestedPages: Int,
    val fetchedItems: Int,
    val error: String? = null
)

data class LeaderResearchOfficialLeaderboardImportResponse(
    val dryRun: Boolean,
    val sourceName: String,
    val fetchedTotal: Int,
    val dedupedTotal: Int,
    val fetches: List<LeaderResearchOfficialLeaderboardFetchDto>,
    val importResult: LeaderResearchExternalAnalyticsImportResponse
)

data class LeaderResearchFalconLeaderboardImportRequest(
    val dryRun: Boolean = true,
    val sortBys: List<String> = listOf("h_score", "sharpe", "pnl"),
    val minWinRate15d: String = "0.45",
    val maxWinRate15d: String = "0.95",
    val minRoi15d: String = "0",
    val minTotalTrades15d: String = "50",
    val maxTotalTrades15d: String = "100000",
    val minPnl15d: String = "0",
    val limitPerPage: Int = 50,
    val maxPagesPerSort: Int = 1,
    val maxItems: Int = 500,
    val defaultCategory: String = "finance"
)

data class LeaderResearchFalconLeaderboardFetchDto(
    val sortBy: String,
    val requestedPages: Int,
    val fetchedItems: Int,
    val error: String? = null
)

data class LeaderResearchFalconLeaderboardImportResponse(
    val dryRun: Boolean,
    val sourceName: String,
    val fetchedTotal: Int,
    val dedupedTotal: Int,
    val fetches: List<LeaderResearchFalconLeaderboardFetchDto>,
    val importResult: LeaderResearchExternalAnalyticsImportResponse
)

data class LeaderResearchPolyburgTelegramImportRequest(
    val dryRun: Boolean = true,
    val rawText: String = "",
    val defaultCategory: String = "finance",
    val sourceUrl: String = "https://web.telegram.org/a/#7698624735",
    val maxItems: Int = 500
)

data class LeaderResearchPolyburgTelegramImportResponse(
    val dryRun: Boolean,
    val sourceName: String,
    val parsedTotal: Int,
    val dedupedTotal: Int,
    val importResult: LeaderResearchExternalAnalyticsImportResponse
)

data class LeaderResearchPolymarketAnalyticsCopyTradeImportRequest(
    val dryRun: Boolean = true,
    val rawText: String = "",
    val defaultCategory: String = "finance",
    val sourceUrl: String = "https://polymarketanalytics.com/copy-trade",
    val maxItems: Int = 500
)

data class LeaderResearchPolymarketAnalyticsCopyTradeImportResponse(
    val dryRun: Boolean,
    val sourceName: String,
    val parsedTotal: Int,
    val dedupedTotal: Int,
    val importResult: LeaderResearchExternalAnalyticsImportResponse
)

data class LeaderResearchOfficialLeaderboardDiagnoseRequest(
    val sampleLimit: Int = 12,
    val staleHours: Int = 48
)

data class LeaderResearchOfficialLeaderboardBucketDto(
    val bucket: String,
    val count: Int,
    val description: String
)

data class LeaderResearchOfficialLeaderboardCategoryDto(
    val category: String,
    val total: Int,
    val paper: Int,
    val cleanHigh: Int,
    val fastWatch: Int,
    val readyForPaper: Int,
    val noActivitySample: Int,
    val staleActivity: Int
)

data class LeaderResearchOfficialLeaderboardSampleDto(
    val candidateId: Long,
    val wallet: String,
    val category: String,
    val bucket: String,
    val researchState: String,
    val score: String?,
    val riskFlags: List<String>,
    val lastSourceAgeHours: Long?,
    val paperTrades: Int?,
    val filteredRatio: String?,
    val copyablePnl: String?,
    val sourceEvidence: String?
)

data class LeaderResearchOfficialLeaderboardDiagnoseResponse(
    val total: Int,
    val paperTotal: Int,
    val cleanHighTotal: Int,
    val fastWatchTotal: Int,
    val readyForPaperTotal: Int,
    val buckets: List<LeaderResearchOfficialLeaderboardBucketDto>,
    val categories: List<LeaderResearchOfficialLeaderboardCategoryDto>,
    val riskFlagCounts: Map<String, Int>,
    val samples: List<LeaderResearchOfficialLeaderboardSampleDto>,
    val generatedAt: Long
)

data class LeaderResearchPoliticsSourceDiagnoseRequest(
    val lookbackDays: Int = 60,
    val minEvents: Int = 8,
    val minDistinctMarkets: Int = 2,
    val minBuyEvents: Int = 2,
    val minSellEvents: Int = 1,
    val minSafePriceRatio: String = "0.20",
    val maxTailPriceRatio: String = "0.50",
    val limit: Int = 500
)

data class LeaderResearchPoliticsSourceBucketDto(
    val bucket: String,
    val count: Int,
    val description: String
)

data class LeaderResearchPoliticsSourceSampleDto(
    val wallet: String,
    val action: String,
    val totalEvents: Long,
    val distinctMarkets: Long,
    val buyEvents: Long,
    val sellEvents: Long,
    val safePriceRatio: String,
    val tailPriceRatio: String,
    val avgAmount: String,
    val totalAmount: String,
    val currentState: String?,
    val currentScore: String?,
    val riskFlags: List<String>,
    val blockers: List<String>
)

data class LeaderResearchPoliticsSourceDiagnoseResponse(
    val category: String,
    val lookbackDays: Int,
    val scannedWallets: Int,
    val passImportCriteria: Int,
    val unknownWallets: Int,
    val existingWallets: Int,
    val paperWallets: Int,
    val cleanHighWallets: Int,
    val eligibleForPaperNow: Int,
    val buckets: List<LeaderResearchPoliticsSourceBucketDto>,
    val samples: List<LeaderResearchPoliticsSourceSampleDto>,
    val generatedAt: Long
)

data class LeaderResearchPaperProcessRequest(
    val batchSize: Int = 20,
    val candidateIds: List<Long> = emptyList()
)

data class LeaderResearchPaperProcessResponse(
    val processed: Int,
    val filtered: Int,
    val failed: Int,
    val requestedBatchSize: Int,
    val effectiveBatchSize: Int,
    val maxBatchSize: Int,
    val truncated: Boolean
)

data class LeaderResearchPaperScoreResponse(
    val scoredCount: Int,
    val states: List<String>,
    val scoreVersion: String
)

data class LeaderResearchPaperPromotionRequest(
    val minScore: String = "80",
    val politicsLimit: Int = 20,
    val financeLimit: Int = 20,
    val sportsLimit: Int = 5,
    val cryptoLimit: Int = 5,
    val dryRun: Boolean = false
)

data class LeaderResearchPaperPromotionCategoryDto(
    val category: String,
    val requestedLimit: Int,
    val selectedCount: Int,
    val promotedCount: Int,
    val skippedRiskCount: Int
)

data class LeaderResearchPaperPromotionItemDto(
    val candidateId: Long,
    val wallet: String,
    val category: String,
    val score: String,
    val previousState: String,
    val nextState: String,
    val riskFlags: List<String>
)

data class LeaderResearchPaperPromotionResponse(
    val dryRun: Boolean,
    val minScore: String,
    val selectedTotal: Int,
    val promotedTotal: Int,
    val skippedRiskTotal: Int,
    val categories: List<LeaderResearchPaperPromotionCategoryDto>,
    val items: List<LeaderResearchPaperPromotionItemDto>,
    val requestedSelectedTotal: Int = selectedTotal,
    val effectiveSelectedLimit: Int = selectedTotal,
    val truncated: Boolean = false
)

data class LeaderResearchRunDto(
    val id: Long,
    val status: String,
    val triggerType: String,
    val dryRun: Boolean,
    val startedAt: Long,
    val finishedAt: Long?,
    val durationMs: Long?,
    val sourceCountsJson: String?,
    val candidateCountsJson: String?,
    val partialFailure: Boolean,
    val skippedReason: String?,
    val errorClass: String?,
    val errorMessage: String?
)

data class LeaderResearchSummaryDto(
    val discoveredCount: Long,
    val candidateCount: Long,
    val paperCount: Long,
    val trialReadyCount: Long,
    val cooldownCount: Long,
    val retiredCount: Long,
    val activePaperSessions: Long,
    val pendingRiskCount: Long,
    val lastRun: LeaderResearchRunDto?,
    val sourceLimitations: List<String>
)

data class LeaderResearchFunnelCategoryDto(
    val category: String,
    val totalCandidates: Int,
    val paperCandidates: Int,
    val cleanHighScoreCandidates: Int,
    val topScore: String?,
    val topCandidateId: Long?
)

data class LeaderResearchFunnelCandidateDto(
    val candidateId: Long,
    val wallet: String,
    val category: String,
    val score: String,
    val tradeCount: Int,
    val filteredRatio: String,
    val copyablePnl: String,
    val maxDrawdown: String,
    val researchState: String,
    val trialReadiness: LeaderResearchTrialReadinessDto
)

data class LeaderResearchTrialReadinessDto(
    val eligible: Boolean,
    val level: String,
    val label: String,
    val blockers: List<String>,
    val fastWatchBlockers: List<String>,
    val ageHours: Long,
    val stableHighScoreCount: Int,
    val requiredStableHighScoreCount: Int
)

data class LeaderResearchAllocationHealthDto(
    val primaryCategories: List<String>,
    val secondaryCategories: List<String>,
    val primaryTargetPercent: String,
    val secondaryTargetPercent: String,
    val primaryActualPercent: String,
    val secondaryActualPercent: String,
    val primaryCleanHighCount: Int,
    val secondaryCleanHighCount: Int,
    val primaryDeficitCount: Int,
    val status: String,
    val message: String
)

data class LeaderResearchFunnelResponse(
    val targetTotal: Int,
    val totalCandidates: Int,
    val managedLeaderTotal: Long,
    val leaderPoolTotal: Long,
    val progressPercent: String,
    val cleanHighScoreTotal: Int,
    val criteria: String,
    val categories: List<LeaderResearchFunnelCategoryDto>,
    val allocationHealth: LeaderResearchAllocationHealthDto,
    val priorityCandidates: List<LeaderResearchFunnelCandidateDto>,
    val generatedAt: Long
)

data class LeaderResearchCandidateListRequest(
    val page: Int = 0,
    val size: Int = 20,
    val state: String? = null,
    val query: String? = null
)

data class LeaderResearchCandidateListResponse(
    val list: List<LeaderResearchCandidateDto>,
    val total: Long,
    val summary: LeaderResearchSummaryDto
)

data class LeaderResearchCandidateDto(
    val id: Long,
    val normalizedWallet: String,
    val leaderId: Long?,
    val leaderName: String?,
    val poolId: Long?,
    val poolStatus: String?,
    val suggestedFixedAmount: String?,
    val suggestedMaxDailyLoss: String?,
    val suggestedMaxDailyOrders: Int?,
    val suggestedMinPrice: String?,
    val suggestedMaxPrice: String?,
    val suggestedMaxPositionValue: String?,
    val researchState: String,
    val source: String,
    val sourceRank: Int?,
    val score: String?,
    val scoreVersion: String?,
    val reason: String?,
    val riskFlags: List<String>,
    val locked: Boolean,
    val agentOwned: Boolean,
    val provenance: String,
    val sourceEvidence: String?,
    val firstSeenAt: Long,
    val lastSourceSeenAt: Long?,
    val lastScoredAt: Long?,
    val cooldownUntil: Long?,
    val cooldownCount: Int,
    val trialReadyAt: Long?,
    val retiredAt: Long?,
    val lastPaperSessionId: Long?,
    val latestPaperSession: LeaderPaperSessionDto?
)

data class LeaderResearchCandidateDetailDto(
    val candidate: LeaderResearchCandidateDto,
    val latestScore: LeaderResearchScoreDto?,
    val paperSessions: List<LeaderPaperSessionDto>,
    val paperTrades: List<LeaderPaperTradeDto>,
    val paperPositions: List<LeaderPaperPositionDto>,
    val events: List<LeaderResearchEventDto>
)

data class LeaderResearchScoreDto(
    val id: Long,
    val candidateId: Long,
    val runId: Long?,
    val scoreVersion: String,
    val totalScore: String,
    val profitSignal: String,
    val repeatability: String,
    val liquidityFit: String,
    val entryPriceFit: String,
    val slippageRisk: String,
    val holdingPeriodFit: String,
    val marketTypeRisk: String,
    val drawdownRisk: String,
    val exitLiquidityRisk: String,
    val dataFreshness: String,
    val filterPassRate: String,
    val sampleTradeCount: Int,
    val reason: String?,
    val createdAt: Long
)

data class LeaderPaperSessionDto(
    val id: Long,
    val candidateId: Long,
    val status: String,
    val startedAt: Long,
    val endedAt: Long?,
    val tradeCount: Int,
    val filteredCount: Int,
    val openExposure: String,
    val totalRealizedPnl: String,
    val totalUnrealizedPnl: String,
    val copyablePnl: String,
    val maxDrawdown: String,
    val unknownValuationExposure: String,
    val confirmedZeroExposure: String,
    val filteredRatio: String,
    val lastProcessedEventTime: Long?,
    val scoreSnapshot: String?
)

data class LeaderPaperTradeDto(
    val id: Long,
    val sessionId: Long,
    val candidateId: Long,
    val activityEventId: Long?,
    val leaderTradeId: String,
    val marketId: String,
    val marketTitle: String?,
    val marketSlug: String?,
    val side: String,
    val outcome: String?,
    val outcomeIndex: Int?,
    val leaderPrice: String?,
    val leaderSize: String?,
    val simulatedPrice: String?,
    val simulatedSize: String?,
    val simulatedAmount: String?,
    val fillAssumption: String,
    val quoteConfidence: String,
    val quoteSource: String?,
    val quoteTimestamp: Long?,
    val filterResult: String,
    val filterReason: String?,
    val valuationStatus: String,
    val realizedPnl: String?,
    val eventTime: Long,
    val createdAt: Long
)

data class LeaderPaperPositionDto(
    val id: Long,
    val sessionId: Long,
    val candidateId: Long,
    val marketId: String,
    val outcome: String?,
    val outcomeIndex: Int?,
    val quantity: String,
    val cost: String,
    val avgPrice: String,
    val currentPrice: String?,
    val currentValue: String,
    val realizedPnl: String,
    val unrealizedPnl: String,
    val valuationStatus: String,
    val quoteConfidence: String,
    val quoteSource: String?,
    val quoteTimestamp: Long?,
    val updatedAt: Long
)

data class LeaderResearchSourceStateDto(
    val sourceType: String,
    val status: String,
    val lastSuccessAt: Long?,
    val lastFailureAt: Long?,
    val lastRunAt: Long?,
    val lastCandidateCount: Int,
    val errorClass: String?,
    val errorMessage: String?,
    val stale: Boolean,
    val disabledReason: String?,
    val lastCursor: String?,
    val updatedAt: Long
)

data class LeaderResearchEventDto(
    val id: Long,
    val candidateId: Long?,
    val runId: Long?,
    val eventType: String,
    val reason: String?,
    val payloadSummary: String?,
    val notificationStatus: String,
    val notificationError: String?,
    val dedupeKey: String?,
    val createdAt: Long,
    val notifiedAt: Long?
)

data class LeaderResearchApprovalRequest(
    val candidateId: Long,
    val accountId: Long,
    val confirm: Boolean = false
)

data class LeaderResearchApprovalResponse(
    val copyTrading: CopyTradingDto,
    val warning: String = "已创建禁用状态的试跟配置；需要你手动启用后才会真钱跟单。"
)
