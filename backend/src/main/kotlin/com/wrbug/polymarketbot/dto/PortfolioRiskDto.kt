package com.wrbug.polymarketbot.dto

data class PortfolioRiskEvaluationRequest(
    val accountId: Long,
    val side: String,
    val amount: String,
    val marketId: String? = null,
    val marketTitle: String? = null,
    val eventSlug: String? = null,
    val leaderAddress: String? = null,
    val category: String? = null,
    val requestId: String? = null,
    val correlationId: String? = null,
    val stage: String = "EVALUATE",
    val modelCandidateId: String? = null
)

data class PortfolioRiskCompletionRequest(
    val correlationId: String,
    val status: String
)

data class PortfolioRiskCompletionResponse(
    val correlationId: String,
    val status: String,
    val completedAt: Long
)

data class PortfolioRiskDecisionListRequest(val accountId: Long, val limit: Int = 100)

data class PortfolioRiskDecisionDto(
    val requestId: String,
    val accountId: Long,
    val policyVersion: String,
    val mode: String,
    val side: String,
    val outcome: String,
    val executionAllowed: Boolean,
    val marketId: String?,
    val eventSlug: String?,
    val leaderAddress: String?,
    val category: String?,
    val rules: List<PortfolioRiskRuleResultDto>,
    val createdAt: Long
)

data class PortfolioRiskReplayRequest(val requestId: String)

data class PortfolioRiskShadowReportRequest(
    val accountId: Long,
    val since: Long? = null
)

data class PortfolioRelationRequest(val accountId: Long)

data class PortfolioBuyControlRequest(val accountId: Long)
data class PortfolioBuyControlUpdateRequest(val accountId: Long, val paused: Boolean, val reason: String? = null)
data class PortfolioBuyControlAuditDto(val action: String, val reason: String?, val actor: String, val createdAt: Long)
data class PortfolioBuyControlResponse(
    val accountId: Long,
    val paused: Boolean,
    val reason: String?,
    val updatedBy: String?,
    val updatedAt: Long?,
    val changed: Boolean = false,
    val audit: List<PortfolioBuyControlAuditDto> = emptyList()
)

data class PortfolioReductionPreviewRequest(
    val accountId: Long,
    val positionKey: String,
    val quantity: String
)

data class PortfolioReductionDimensionImpactDto(
    val dimension: String,
    val key: String,
    val label: String,
    val beforeValue: String,
    val afterValue: String,
    val beforePercent: String?,
    val afterPercent: String?,
    val calculationQuality: String
)

data class PortfolioReductionPreviewResponse(
    val draftId: String,
    val accountId: Long,
    val positionKey: String,
    val marketTitle: String,
    val outcome: String,
    val requestedQuantity: String,
    val availableQuantity: String,
    val estimatedProceeds: String,
    val beforeAvailableBalance: String,
    val afterAvailableBalance: String,
    val beforeOpenPositionsValue: String,
    val afterOpenPositionsValue: String,
    val beforeTotalAssets: String,
    val afterTotalAssets: String,
    val impacts: List<PortfolioReductionDimensionImpactDto>,
    val status: String,
    val executionEnabled: Boolean,
    val createdBy: String,
    val createdAt: Long,
    val expiresAt: Long,
    val confirmedBy: String? = null,
    val confirmedAt: Long? = null,
    val executionRequestedBy: String? = null,
    val executionRequestedAt: Long? = null,
    val executionExternalTradeId: String? = null,
    val executionRecordId: Long? = null,
    val executionError: String? = null,
    val executionAttempt: Int = 0
)

data class PortfolioReductionDraftRequest(val draftId: String)
data class PortfolioReductionConfirmRequest(val draftId: String)
data class PortfolioReductionExecuteRequest(val draftId: String)
data class PortfolioReductionRefreshRequest(val draftId: String)
data class PortfolioReductionListRequest(val accountId: Long)

data class PortfolioRelationPositionDto(
    val positionKey: String,
    val marketId: String?,
    val eventSlug: String?,
    val outcome: String,
    val category: String?,
    val marketTitle: String,
    val currentValue: String?,
    val quantity: String,
    val firstObservedAt: Long,
    val marketEndAt: Long?
)

data class PortfolioPositionRelationDto(
    val type: String,
    val category: String?,
    val entityKey: String?,
    val positionKeys: List<String>,
    val relatedValue: String?,
    val unmatchedValue: String?,
    val confidence: String,
    val rationale: String
)

data class PortfolioRelationResponse(
    val accountId: Long,
    val asOf: Long?,
    val positions: List<PortfolioRelationPositionDto>,
    val relations: List<PortfolioPositionRelationDto>,
    val countsByType: Map<String, Int>,
    val relatedValueByType: Map<String, String>,
    val generatedAt: Long
)

data class PortfolioRiskShadowRuleStatsDto(
    val code: String,
    val pass: Int,
    val wouldBlock: Int,
    val insufficientData: Int
)

data class PortfolioRiskShadowGateDto(
    val code: String,
    val passed: Boolean,
    val actual: String,
    val required: String
)

data class PortfolioRiskShadowReportResponse(
    val accountId: Long,
    val requestedSince: Long,
    val sampleWindowStart: Long?,
    val sampleWindowEnd: Long?,
    val observationHours: String,
    val legacyDecisionsExcluded: Int,
    val totalDecisions: Int,
    val buyDecisions: Int,
    val sellDecisions: Int,
    val fullyEvaluatedBuyDecisions: Int,
    val snapshotCoveragePercent: String?,
    val replayConsistencyPercent: String?,
    val finalDecisions: Int,
    val terminalLinkedFinalDecisions: Int,
    val terminalLinkagePercent: String?,
    val terminalStatuses: Map<String, Int>,
    val rules: List<PortfolioRiskShadowRuleStatsDto>,
    val gates: List<PortfolioRiskShadowGateDto>,
    val readyForEnforcedReview: Boolean,
    val blockers: List<String>,
    val generatedAt: Long
)

data class PortfolioRiskHistoricalReplayRequest(
    val accountId: Long,
    val since: Long? = null
)

data class PortfolioRiskReplayMetricDto(
    val code: String,
    val value: String?,
    val status: String,
    val rationale: String
)

data class PortfolioRiskHistoricalReplayResponse(
    val accountId: Long,
    val requestedSince: Long,
    val generatedAt: Long,
    val scopedBridgeRecords: Int,
    val unscopedBridgeRecords: Int,
    val buySuccess: Int,
    val buyFailed: Int,
    val sellSuccess: Int,
    val sellFailed: Int,
    val failureTaxonomy: Map<String, Int>,
    val metrics: List<PortfolioRiskReplayMetricDto>,
    val blockers: List<String>
)

data class PortfolioRiskReplayResponse(
    val requestId: String,
    val policyVersion: String,
    val storedOutcome: String,
    val replayedOutcome: String?,
    val consistent: Boolean,
    val replayScope: String,
    val rules: List<PortfolioRiskRuleResultDto>,
    val snapshotAvailable: Boolean
)

data class PortfolioRiskRuleResultDto(
    val code: String,
    val status: String,
    val actual: String?,
    val threshold: String?,
    val message: String
)

data class PortfolioRiskEvaluationResponse(
    val decisionId: String,
    val policyVersion: String,
    val mode: String,
    val side: String,
    val outcome: String,
    val executionAllowed: Boolean,
    val rules: List<PortfolioRiskRuleResultDto>,
    val evaluatedAt: Long,
    val reservationStatus: String? = null,
    val reservedAmount: String? = null
)
