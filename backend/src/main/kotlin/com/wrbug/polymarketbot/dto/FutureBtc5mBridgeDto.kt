package com.wrbug.polymarketbot.dto

data class FutureBtc5mBridgeStatus(
    val bridgeId: String,
    val online: Boolean,
    val requestedEnabled: Boolean,
    val effectiveEnabled: Boolean,
    val amountUsd: Int,
    val series: String,
    val strategy: String? = null,
    val strategySeries: List<String>? = null,
    val fourHour: FutureBtc5mFourHour? = null,
    val mode: String,
    val serverTime: Double,
    val periodStart: Long?,
    val feedStatus: String,
    val reason: String?,
    val blockReasons: List<String>,
    val executorReady: Boolean,
    val signal: FutureBtc5mSignal?,
    val orderCounts: FutureBtc5mOrderCounts,
    val preflight: FutureBtc5mPreflight? = null,
    val preparation: FutureBtc5mPreparation
)

// The 4h weekend leg of the combined strategy: this round's decision and latest checkpoint evaluation.
data class FutureBtc5mFourHour(
    val periodStart: Long,
    val weekend: Boolean,
    val decision: FutureBtc5mFourHourDecision?,
    val lastEvaluation: FutureBtc5mFourHourEvaluation?
)

data class FutureBtc5mFourHourDecision(val checkpointAt: Long, val side: String)

data class FutureBtc5mFourHourEvaluation(
    val checkpointAt: Long,
    val minute: Int,
    val side: String?,
    val pUp: Double,
    val upAskCents: Double?,
    val downAskCents: Double?,
    val decision: String,
    val reason: String?
)

data class FutureBtc5mSignal(
    val slug: String,
    val side: String?,
    val period_start: Long,
    val price_observed_at: Double,
    val open_price: Double,
    val current_price: Double,
    val period_end: Long? = null,
    val price_source: String? = null,
    val open_price_source: String? = null,
    val twap_lookback_seconds: Int? = null
)

data class FutureBtc5mPreflight(
    val mode: String, val noSubmission: Boolean, val browserConnected: Boolean,
    val checkedAt: Double?, val receivedAt: Double?, val marketUrl: String?, val pagePeriodStart: Long?,
    val navigation: String, val ticketStatus: String, val amountUsd: Double?, val selectedSide: String?,
    val buyButtonEnabled: Boolean, val signalFresh: Boolean, val signalSide: String?, val sideMatches: Boolean,
    val result: String, val reasons: List<String>, val lastPassed: FutureBtc5mPreflightPass?,
    val upQuoteCents: Double?, val downQuoteCents: Double?, val preferredSide: String?, val selectionSource: String?
)

data class FutureBtc5mPreflightPass(
    val periodStart: Long, val checkedAt: Double, val marketUrl: String,
    val signalSide: String?, val amountUsd: Int, val noSubmission: Boolean,
    val schemaVersion: Int? = null, val selectionSource: String? = null,
    val upQuoteCents: Double? = null, val downQuoteCents: Double? = null, val preferredSide: String? = null
)

data class FutureBtc5mPreparation(
    val mode: String, val noSubmission: Boolean, val operatorAuthorized: Boolean,
    val authorizationSource: String, val enabled: Boolean, val state: String,
    val intent: FutureBtc5mPreparationIntent?, val lastAttempt: FutureBtc5mPreparationRecord?,
    val reasons: List<String>, val strategy: String? = null, val series: String? = null
)

data class FutureBtc5mPreparationIntent(
    val schemaVersion: Int, val id: String, val slug: String, val periodStart: Long, val periodEnd: Long,
    val side: String, val amountUsd: Int, val createdAt: Double, val expiresAt: Double,
    val priceObservedAt: Double, val openPrice: Double, val currentPrice: Double,
    val priceSource: String, val openPriceSource: String, val twapLookbackSeconds: Int,
    val mode: String, val noSubmission: Boolean, val operatorAuthorized: Boolean,
    val authorizationSource: String, val claimToken: String?,
    val upQuoteCents: Double? = null, val downQuoteCents: Double? = null,
    val quoteObservedAt: Double? = null, val selectionSource: String? = null
)

data class FutureBtc5mPreparationRecord(
    val schemaVersion: Int, val id: String, val slug: String, val periodStart: Long, val periodEnd: Long,
    val side: String, val amountUsd: Int, val createdAt: Double, val expiresAt: Double,
    val priceObservedAt: Double, val openPrice: Double, val currentPrice: Double,
    val priceSource: String, val openPriceSource: String, val twapLookbackSeconds: Int,
    val mode: String, val noSubmission: Boolean, val operatorAuthorized: Boolean,
    val authorizationSource: String, val claimToken: String?,
    val state: String, val updatedAt: Double, val claimedAt: Double?, val reason: String?,
    val receipt: FutureBtc5mPreparationReceipt?,
    val upQuoteCents: Double? = null, val downQuoteCents: Double? = null,
    val quoteObservedAt: Double? = null, val selectionSource: String? = null
)

data class FutureBtc5mPreparationReceipt(
    val checkedAt: Double, val marketUrl: String, val amountUsd: Double?, val selectedSide: String?
)

data class FutureBtc5mOrderCounts(
    val total: Int, val pending: Int, val submitted: Int, val filled: Int, val failed: Int, val skipped: Int
)

data class FutureBtc5mOrderEvent(val stage: String, val at: Double, val reason: String?)

data class FutureBtc5mOrder(
    val id: String,
    val bridgeId: String,
    val slug: String,
    val periodStart: Long,
    val periodEnd: Long,
    val side: String,
    val amountUsd: Int,
    val status: String,
    val reason: String?,
    val createdAt: Double,
    val updatedAt: Double,
    val submittedAt: Double?,
    val filledAt: Double?,
    val platformOrderId: String?,
    val filledQuantity: Double?,
    val avgFilledPrice: Double?,
    val feeUsd: Double?,
    val events: List<FutureBtc5mOrderEvent>
)

data class FutureBtc5mOrderListRequest(val page: Int = 1, val size: Int = 20, val status: String? = null)
data class FutureBtc5mOrderListResponse(val list: List<FutureBtc5mOrder>, val total: Int, val page: Int, val size: Int)
data class FutureBtc5mOrderDetailRequest(val id: String)
