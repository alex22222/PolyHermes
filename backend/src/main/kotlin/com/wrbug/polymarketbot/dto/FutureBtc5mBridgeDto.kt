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
    val preparation: FutureBtc5mPreparation,
    val paperRegime: FutureBtc5mPaperRegime? = null
)

// Paper shadow of regime filters (scripts/future_btc5m_paper_regime.py): every 15m PREPARE
// decision is mirrored by a $1 paper trade at the decision-time quote and resolved from Binance
// 15m klines, so the page can compare baseline vs trend-filtered results without touching real orders.
// G1 keeps only |trend60Bp| >= 15; G2 (added 2026-11-10) skips just the 5-15bp chop band.
data class FutureBtc5mPaperRegime(
    val rule: String,
    val minTrend60Bp: Double,
    val resolutionSource: String,
    val ruleG2: String? = null,
    val baseline: FutureBtc5mPaperRegimeStats,
    val filtered: FutureBtc5mPaperRegimeStats,
    val filteredG2: FutureBtc5mPaperRegimeStats? = null,
    val recent: List<FutureBtc5mPaperRegimeTrade>,
    val updatedAt: Double
)

data class FutureBtc5mPaperRegimeStats(
    val trades: Int,
    val settled: Int,
    val wins: Int,
    val winRate: Double?,
    val roiPerDollar: Double?,
    val totalUsd: Double
)

data class FutureBtc5mPaperRegimeTrade(
    val periodStart: Long,
    val side: String,
    val priceCents: Double,
    val trend60Bp: Double,
    val g1Eligible: Boolean,
    val g2Eligible: Boolean? = null,
    val win: Boolean?,
    val roi: Double?
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

// Full paginated ledger of paper trades (scripts/future_btc5m_paper_regime.py listing()), for the
// history table below the paper regime card. Unlike FutureBtc5mPaperRegimeTrade (recent summary),
// every field of the ledger row is exposed.
data class FutureBtc5mPaperListRequest(val page: Int = 1, val size: Int = 20)
data class FutureBtc5mPaperListResponse(val list: List<FutureBtc5mPaperListEntry>, val total: Int, val page: Int, val size: Int)
data class FutureBtc5mPaperListEntry(
    val schemaVersion: Int,
    val rule: String,
    val periodStart: Long,
    val side: String,
    val priceCents: Double,
    val trend60Bp: Double,
    val volatilityBp: Double,
    val g1Eligible: Boolean,
    val g2Eligible: Boolean? = null,
    val state: String,
    val createdAt: Double,
    val outcome: String?,
    val win: Boolean?,
    val roi: Double?,
    val binanceOpen: Double?,
    val binanceClose: Double?,
    val resolvedAt: Double?
)
data class FutureBtc5mOrderDetailRequest(val id: String)
