package com.wrbug.polymarketbot.dto

data class FutureBtc5mWalletSnapshot(
    val walletAddress: String,
    val cashUsd: Double?,
    val observedAt: Double,
    val receivedAt: Double,
    val marketUrl: String,
    val source: String,
    val fresh: Boolean
)

data class FutureBtc5mWalletEnvelope(val wallet: FutureBtc5mWalletSnapshot?)

data class FutureBtc5mAssetPosition(
    val asset: String,
    val slug: String,
    val title: String,
    val side: String,
    val quantity: Double,
    val avgPrice: Double?,
    val currentPrice: Double?,
    val currentValueUsd: Double?,
    val cashPnlUsd: Double?,
    val redeemable: Boolean
)

data class FutureBtc5mAssetBuy(
    val id: String,
    val asset: String,
    val slug: String,
    val title: String,
    val side: String,
    val quantity: Double,
    val price: Double?,
    val amountUsd: Double?,
    val boughtAt: Long,
    val transactionHash: String?,
    val result: String = "UNKNOWN",
    val winningSide: String? = null
)

data class FutureBtc5mAssets(
    val wallet: FutureBtc5mWalletSnapshot?,
    val dataStatus: String,
    val positions: List<FutureBtc5mAssetPosition>?,
    val recentBuys: List<FutureBtc5mAssetBuy>?,
    val positionsValueUsd: Double?,
    val marketDataObservedAt: Double?,
    val reasons: List<String>,
    val buyHistoryComplete: Boolean = false
)
