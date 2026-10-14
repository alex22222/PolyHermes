package com.wrbug.polymarketbot.api

import com.google.gson.annotations.SerializedName

data class FutureBtc5mActivityPage(
    val data: List<UserActivityResponse>? = null,
    val pagination: FutureBtc5mActivityPagination? = null
)

data class FutureBtc5mActivityPagination(
    @SerializedName("has_more") val hasMore: Boolean? = null,
    @SerializedName("next_cursor") val nextCursor: String? = null
)

data class FutureBtc5mSettlementMarket(
    @SerializedName("condition_id") val conditionId: String? = null,
    @SerializedName("market_slug") val slug: String? = null,
    val closed: Boolean? = null,
    val tokens: List<FutureBtc5mSettlementToken>? = null
)

data class FutureBtc5mSettlementToken(
    @SerializedName("token_id") val tokenId: String? = null,
    val outcome: String? = null,
    val winner: Boolean? = null
)
