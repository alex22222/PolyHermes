package com.wrbug.polymarketbot.dto

data class PortfolioExposureAccountDto(
    val accountId: Long,
    val accountName: String?,
    val walletAddress: String,
    val availableBalance: String?,
    val openPositionsValue: String,
    val pendingRedeemValue: String?,
    val totalAssets: String?,
    val valuationStatus: String,
    val positionCostBasis: String?,
    val unrealizedPnl: String?,
    val firstObservedAt: Long?,
    val positionCount: Int,
    val asOf: Long?
)

data class PortfolioExposureBucketDto(
    val key: String,
    val label: String,
    val value: String,
    val percentOfTotalAssets: String?,
    val positionCount: Int,
    val attributionSource: String,
    val attributionQuality: String,
    val leaderId: Long?,
    val costBasis: String?,
    val unrealizedPnl: String?,
    val firstObservedAt: Long?,
    val positionKeys: List<String>
)

data class PortfolioExposureDimensionCoverageDto(
    val knownValue: String,
    val unknownValue: String,
    val knownValueCoveragePercent: String?,
    val minimumShadowCoveragePercent: String,
    val status: String,
    val shadowEligible: Boolean
)

data class PortfolioExposureCoverageDto(
    val totalPositions: Int,
    val unknownValuePositions: Int,
    val unknownLeaderPositions: Int,
    val unknownCategoryPositions: Int,
    val unknownEventPositions: Int,
    val unknownMarketPositions: Int,
    val leader: PortfolioExposureDimensionCoverageDto,
    val category: PortfolioExposureDimensionCoverageDto,
    val event: PortfolioExposureDimensionCoverageDto,
    val market: PortfolioExposureDimensionCoverageDto
)

data class PortfolioExposureResponse(
    val account: PortfolioExposureAccountDto,
    val leaders: List<PortfolioExposureBucketDto>,
    val categories: List<PortfolioExposureBucketDto>,
    val events: List<PortfolioExposureBucketDto>,
    val markets: List<PortfolioExposureBucketDto>,
    val coverage: PortfolioExposureCoverageDto
)
