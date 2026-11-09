package com.wrbug.polymarketbot.api

import com.google.gson.annotations.SerializedName
import retrofit2.Response
import retrofit2.http.GET
import retrofit2.http.Query

/**
 * Polymarket Data API 接口定义
 * 用于查询仓位信息
 * Base URL: https://data-api.polymarket.com
 */
interface PolymarketDataApi {
    @GET("/v2/activity")
    suspend fun getActivityHistory(
        @Query("user") user: String,
        @Query("limit") limit: Int = 500,
        @Query("cursor") cursor: String? = null,
        @Query("type") type: String = "TRADE",
        @Query("side") side: String = "BUY",
        @Query("start") start: Long = 1,
        @Query("sort_direction") sortDirection: String = "DESC"
    ): Response<FutureBtc5mActivityPage>
    
    /**
     * 获取用户当前仓位
     * 文档: https://docs.polymarket.com/api-reference/core/get-current-positions-for-a-user
     */
    @GET("/positions")
    suspend fun getPositions(
        @Query("user") user: String,
        @Query("market") market: String? = null,
        @Query("eventId") eventId: String? = null,
        @Query("sizeThreshold") sizeThreshold: Double? = null,
        @Query("redeemable") redeemable: Boolean? = null,
        @Query("mergeable") mergeable: Boolean? = null,
        @Query("limit") limit: Int? = null,
        @Query("offset") offset: Int? = null,
        @Query("sortBy") sortBy: String? = null,
        @Query("sortDirection") sortDirection: String? = null,
        @Query("title") title: String? = null
    ): Response<List<PositionResponse>>

    @GET("/v2/positions")
    suspend fun getPositionsV2(
        @Query("user") user: String,
        @Query("sizeThreshold") sizeThreshold: Double? = null,
        @Query("limit") limit: Int? = null,
        @Query("cursor") cursor: String? = null
    ): Response<FutureBtc5mPositionsPage>
    
    /**
     * 获取用户仓位总价值
     * 文档: https://docs.polymarket.com/api-reference/core/get-total-value-of-a-users-positions
     */
    @GET("/value")
    suspend fun getTotalValue(
        @Query("user") user: String,
        @Query("market") market: List<String>? = null
    ): Response<List<ValueResponse>>
    
    /**
     * 获取用户活动（包括交易）
     * 文档: https://docs.polymarket.com/api-reference/core/get-user-activity
     */
    @GET("/activity")
    suspend fun getUserActivity(
        @Query("user") user: String,
        @Query("limit") limit: Int? = null,
        @Query("offset") offset: Int? = null,
        @Query("market") market: List<String>? = null,
        @Query("eventId") eventId: List<Int>? = null,
        @Query("type") type: List<String>? = null,
        @Query("start") start: Long? = null,
        @Query("end") end: Long? = null,
        @Query("sortBy") sortBy: String? = null,
        @Query("sortDirection") sortDirection: String? = null,
        @Query("side") side: String? = null
    ): Response<List<UserActivityResponse>>
}

/**
 * 仓位响应（根据 Polymarket Data API 文档）
 */
data class PositionResponse(
    @SerializedName(value = "proxyWallet", alternate = ["proxy_wallet"]) val proxyWallet: String,
    @SerializedName(value = "asset", alternate = ["token_id"]) val asset: String? = null,
    @SerializedName(value = "conditionId", alternate = ["condition_id"]) val conditionId: String? = null,
    @SerializedName(value = "size", alternate = ["current_size"]) val size: Double? = null,
    @SerializedName(value = "avgPrice", alternate = ["avg_price"]) val avgPrice: Double? = null,
    @SerializedName(value = "initialValue", alternate = ["entry_cost_usdc"]) val initialValue: Double? = null,
    @SerializedName(value = "currentValue", alternate = ["current_value"]) val currentValue: Double? = null,
    @SerializedName(value = "cashPnl", alternate = ["total_pnl"]) val cashPnl: Double? = null,
    @SerializedName(value = "percentPnl", alternate = ["percent_pnl"]) val percentPnl: Double? = null,
    @SerializedName(value = "totalBought", alternate = ["total_size"]) val totalBought: Double? = null,
    @SerializedName(value = "realizedPnl", alternate = ["realized_pnl"]) val realizedPnl: Double? = null,
    @SerializedName(value = "percentRealizedPnl", alternate = ["percent_realized_pnl"]) val percentRealizedPnl: Double? = null,
    @SerializedName(value = "curPrice", alternate = ["current_price"]) val curPrice: Double? = null,
    val redeemable: Boolean? = null,
    val mergeable: Boolean? = null,
    val title: String? = null,
    val slug: String? = null,
    val icon: String? = null,
    @SerializedName(value = "eventSlug", alternate = ["event_slug"]) val eventSlug: String? = null,
    val outcome: String? = null,
    @SerializedName(value = "outcomeIndex", alternate = ["outcome_index"]) val outcomeIndex: Int? = null,
    @SerializedName(value = "oppositeOutcome", alternate = ["opposite_outcome"]) val oppositeOutcome: String? = null,
    @SerializedName(value = "oppositeAsset", alternate = ["opposite_token_id"]) val oppositeAsset: String? = null,
    @SerializedName(value = "endDate", alternate = ["end_date"]) val endDate: String? = null,
    @SerializedName(value = "negativeRisk", alternate = ["negative_risk"]) val negativeRisk: Boolean? = null
)

/**
 * 仓位价值响应（根据 Polymarket Data API 文档）
 */
data class ValueResponse(
    val user: String,
    val value: Double
)

/**
 * 用户活动响应（根据 Polymarket Data API 文档）
 * 文档: https://docs.polymarket.com/api-reference/core/get-user-activity
 */
data class UserActivityResponse(
    @SerializedName(value = "proxyWallet", alternate = ["proxy_wallet"]) val proxyWallet: String,
    val timestamp: Long,
    @SerializedName(value = "conditionId", alternate = ["condition_id"]) val conditionId: String,
    val type: String,  // TRADE, SPLIT, MERGE, REDEEM, REWARD, CONVERSION
    val size: Double? = null,
    @SerializedName(value = "usdcSize", alternate = ["usdc_size"]) val usdcSize: Double? = null,
    @SerializedName(value = "transactionHash", alternate = ["transaction_hash"]) val transactionHash: String? = null,
    val price: Double? = null,
    @SerializedName(value = "asset", alternate = ["token_id"]) val asset: String? = null,
    val side: String? = null,  // BUY, SELL
    @SerializedName(value = "outcomeIndex", alternate = ["outcome_index"]) val outcomeIndex: Int? = null,
    val title: String? = null,
    val slug: String? = null,
    val icon: String? = null,
    @SerializedName(value = "eventSlug", alternate = ["event_slug"]) val eventSlug: String? = null,
    val outcome: String? = null,
    val name: String? = null,
    val pseudonym: String? = null,
    val bio: String? = null,
    val profileImage: String? = null,
    val profileImageOptimized: String? = null
)


