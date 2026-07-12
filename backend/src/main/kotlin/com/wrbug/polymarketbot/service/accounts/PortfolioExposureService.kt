package com.wrbug.polymarketbot.service.accounts

import com.google.gson.Gson
import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.entity.BridgePositionSnapshot
import com.wrbug.polymarketbot.entity.BridgeTradeRecord
import com.wrbug.polymarketbot.repository.*
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchMarketCategoryPatterns
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode

@Service
class PortfolioExposureService(
    private val snapshotRepository: BridgePositionSnapshotRepository,
    private val currentRepository: CurrentAssetValuationRepository,
    private val accountRepository: AccountRepository,
    private val marketRepository: MarketRepository,
    private val tradeRepository: BridgeTradeRecordRepository,
    private val leaderRepository: LeaderRepository,
    private val gson: Gson
) {
    private val bridgeId = "polymtrade-bridge"

    fun getExposure(accountId: Long): PortfolioExposureResponse {
        val account = accountRepository.findById(accountId).orElse(null)
            ?: throw IllegalArgumentException("账户不存在")
        val wallet = account.walletAddress.lowercase()
        val snapshots = snapshotRepository.findByBridgeIdAndWalletAddress(bridgeId, wallet)
        val current = currentRepository.findByBridgeIdAndWalletAddress(bridgeId, wallet)
        val totalAssets = current?.totalAssets
        val trades = tradeRepository.findByBridgeIdAndStatus(bridgeId, "SUCCESS")

        val leaderParts = snapshots.flatMap { allocateLeaders(it, trades) }
        val leaderAddresses = leaderParts.map { it.key }.filter { it != UNKNOWN }.distinct()
        val leadersByAddress = if (leaderAddresses.isEmpty()) emptyMap() else {
            leaderRepository.findLatestByLeaderAddressIn(leaderAddresses).associateBy { it.leaderAddress.lowercase() }
        }

        val categoryParts = snapshots.map { snapshot ->
            val market = snapshot.marketId?.let { marketRepository.findByMarketId(it) }
            val metadataCategory = market?.category?.trim()?.lowercase().takeUnless { it.isNullOrBlank() }
            val category = metadataCategory ?: inferCategory(snapshot.marketTitle)
            snapshot.toExposurePart(
                category,
                if (metadataCategory != null) "MARKET_METADATA" else "TITLE_PATTERN",
                if (category == UNKNOWN) "UNKNOWN" else if (metadataCategory != null) "EXACT" else "INFERRED"
            )
        }
        val eventParts = snapshots.map { snapshot ->
            val eventKey = snapshot.eventSlug?.takeIf { it.isNotBlank() } ?: "$UNKNOWN:${snapshot.idKey()}"
            snapshot.toExposurePart(
                eventKey,
                if (eventKey.startsWith("$UNKNOWN:")) UNKNOWN else "EVENT_SLUG",
                if (eventKey.startsWith("$UNKNOWN:")) UNKNOWN else "EXACT"
            )
        }
        val marketParts = snapshots.map { snapshot ->
            val marketKey = snapshot.marketId?.takeIf { it.isNotBlank() } ?: "$UNKNOWN:${snapshot.idKey()}"
            snapshot.toExposurePart(
                marketKey,
                if (marketKey.startsWith("$UNKNOWN:")) UNKNOWN else "MARKET_ID",
                if (marketKey.startsWith("$UNKNOWN:")) UNKNOWN else "EXACT"
            )
        }

        val unknownValuePositions = snapshots.count { it.currentValue == null }
        val accountPnl = snapshots.sumSnapshotIfComplete { it.pnl }
        val accountCostBasis = if (snapshots.any { it.currentValue == null || it.pnl == null }) null else {
            snapshots.fold(BigDecimal.ZERO) { total, snapshot -> total.add(snapshot.currentValue!!.subtract(snapshot.pnl)) }
        }

        return PortfolioExposureResponse(
            account = PortfolioExposureAccountDto(
                accountId = account.id!!,
                accountName = account.accountName,
                walletAddress = account.walletAddress,
                availableBalance = current?.availableBalance?.strip(),
                openPositionsValue = snapshots.sumKnownValue().strip(),
                pendingRedeemValue = current?.pendingRedeemValue?.strip(),
                totalAssets = totalAssets?.strip(),
                valuationStatus = current?.valuationStatus ?: "UNKNOWN",
                positionCostBasis = accountCostBasis?.strip(),
                unrealizedPnl = accountPnl?.strip(),
                firstObservedAt = snapshots.minOfOrNull { it.createdAt },
                positionCount = snapshots.size,
                asOf = current?.capturedAt
            ),
            leaders = aggregate(
                leaderParts,
                totalAssets,
                label = { key -> if (key == UNKNOWN) "未归属 Leader" else leadersByAddress[key]?.leaderName ?: key },
                leaderId = { key -> leadersByAddress[key]?.id }
            ),
            categories = aggregate(categoryParts, totalAssets, label = { key -> if (key == UNKNOWN) "未分类领域" else key }),
            events = aggregate(eventParts, totalAssets, label = { key -> if (key.startsWith("$UNKNOWN:")) "未归属事件" else key }),
            markets = aggregate(marketParts, totalAssets, label = { key -> if (key.startsWith("$UNKNOWN:")) "未归属市场" else key }),
            coverage = PortfolioExposureCoverageDto(
                totalPositions = snapshots.size,
                unknownValuePositions = unknownValuePositions,
                unknownLeaderPositions = leaderParts.filter { it.key == UNKNOWN }.map { it.positionKey }.distinct().size,
                unknownCategoryPositions = categoryParts.count { it.key == UNKNOWN },
                unknownEventPositions = eventParts.count { it.key.startsWith("$UNKNOWN:") },
                unknownMarketPositions = marketParts.count { it.key.startsWith("$UNKNOWN:") },
                leader = dimensionCoverage(leaderParts, { it.key == UNKNOWN }, unknownValuePositions),
                category = dimensionCoverage(categoryParts, { it.key == UNKNOWN }, unknownValuePositions),
                event = dimensionCoverage(eventParts, { it.key.startsWith("$UNKNOWN:") }, unknownValuePositions),
                market = dimensionCoverage(marketParts, { it.key.startsWith("$UNKNOWN:") }, unknownValuePositions)
            )
        )
    }

    private fun allocateLeaders(snapshot: BridgePositionSnapshot, trades: List<BridgeTradeRecord>): List<ExposurePart> {
        val matching = trades.filter {
            (it.marketId == snapshot.marketId || it.marketTitle == snapshot.marketTitle) &&
                it.outcome.equals(snapshot.side, ignoreCase = true)
        }
        val netByLeader = matching.mapNotNull { trade ->
            extractLeaderAddress(trade)?.let { it to if (trade.side.equals("SELL", true)) trade.quantity.negate() else trade.quantity }
        }.groupBy({ it.first }, { it.second }).mapValues { (_, values) -> values.fold(BigDecimal.ZERO, BigDecimal::add) }
            .filterValues { it > BigDecimal.ZERO }

        val value = snapshot.currentValue ?: BigDecimal.ZERO
        val quantity = snapshot.quantity
        if (netByLeader.isEmpty() || quantity <= BigDecimal.ZERO) {
            return listOf(snapshot.toExposurePart(UNKNOWN, UNKNOWN, UNKNOWN))
        }
        val totalAttributedQuantity = netByLeader.values.fold(BigDecimal.ZERO, BigDecimal::add)
        val attributionGap = quantity.subtract(totalAttributedQuantity).max(BigDecimal.ZERO)
        val roundingGap = attributionGap <= MAX_ROUNDING_QUANTITY_GAP ||
            (quantity > BigDecimal.ZERO && attributionGap.divide(quantity, 8, RoundingMode.HALF_UP) <= MAX_ROUNDING_RATIO_GAP)
        val denominator = if (totalAttributedQuantity > quantity || roundingGap) totalAttributedQuantity else quantity
        val parts = netByLeader.map { (leader, netQuantity) ->
            snapshot.toExposurePart(
                key = leader,
                source = "TRADE_LEDGER",
                quality = "EXACT",
                fraction = netQuantity.divide(denominator, 12, RoundingMode.HALF_UP)
            )
        }.toMutableList()
        val attributedValue = parts.fold(BigDecimal.ZERO) { total, part -> total.add(part.value) }
        val unknownValue = value.subtract(attributedValue)
        if (unknownValue > BigDecimal("0.00000001")) {
            val unknownFraction = if (value > BigDecimal.ZERO) {
                unknownValue.divide(value, 12, RoundingMode.HALF_UP)
            } else {
                BigDecimal.ZERO
            }
            parts += snapshot.toExposurePart(UNKNOWN, UNKNOWN, UNKNOWN, unknownFraction)
        }
        return parts
    }

    private fun extractLeaderAddress(trade: BridgeTradeRecord): String? = try {
        trade.rawPayload?.let { gson.fromJson(it, Map::class.java)["leaderAddress"] as? String }
            ?.trim()?.lowercase()?.takeIf { it.isNotBlank() }
    } catch (_: Exception) {
        null
    }

    private fun inferCategory(title: String): String =
        listOf("crypto", "sports", "finance", "politics")
            .firstOrNull { LeaderResearchMarketCategoryPatterns.matches(it, title) }
            ?: UNKNOWN

    private fun aggregate(
        parts: List<ExposurePart>,
        totalAssets: BigDecimal?,
        label: (String) -> String,
        leaderId: (String) -> Long? = { null }
    ): List<PortfolioExposureBucketDto> = parts.groupBy { it.key }.map { (key, grouped) ->
        val value = grouped.fold(BigDecimal.ZERO) { total, part -> total.add(part.value) }
        val costBasis = grouped.sumIfComplete { it.costBasis }
        val unrealizedPnl = grouped.sumIfComplete { it.unrealizedPnl }
        PortfolioExposureBucketDto(
            key = key,
            label = label(key),
            value = value.strip(),
            percentOfTotalAssets = if (totalAssets != null && totalAssets > BigDecimal.ZERO) {
                value.multiply(BigDecimal("100")).divide(totalAssets, 4, RoundingMode.HALF_UP).strip()
            } else null,
            positionCount = grouped.map { it.positionKey }.distinct().size,
            attributionSource = grouped.map { it.source }.distinct().singleOrNull() ?: "MIXED",
            attributionQuality = grouped.map { it.quality }.distinct().singleOrNull() ?: "MIXED",
            leaderId = leaderId(key),
            costBasis = costBasis?.strip(),
            unrealizedPnl = unrealizedPnl?.strip(),
            firstObservedAt = grouped.minOfOrNull { it.firstObservedAt },
            positionKeys = grouped.map { it.positionKey }.distinct().sorted()
        )
    }.sortedByDescending { BigDecimal(it.value) }

    private fun dimensionCoverage(
        parts: List<ExposurePart>,
        isUnknown: (ExposurePart) -> Boolean,
        unknownValuePositions: Int
    ): PortfolioExposureDimensionCoverageDto {
        val knownValue = parts.filterNot(isUnknown).fold(BigDecimal.ZERO) { total, part -> total.add(part.value) }
        val unknownValue = parts.filter(isUnknown).fold(BigDecimal.ZERO) { total, part -> total.add(part.value) }
        val attributedValue = knownValue.add(unknownValue)
        val coveragePercent = if (attributedValue > BigDecimal.ZERO) {
            knownValue.multiply(BigDecimal("100")).divide(attributedValue, 4, RoundingMode.HALF_UP)
        } else null
        val shadowEligible = unknownValuePositions == 0 && coveragePercent != null && coveragePercent >= MIN_SHADOW_COVERAGE_PERCENT
        val status = when {
            unknownValuePositions > 0 -> "VALUATION_INCOMPLETE"
            shadowEligible -> "READY_FOR_SHADOW"
            else -> "INSUFFICIENT_ATTRIBUTION"
        }
        return PortfolioExposureDimensionCoverageDto(
            knownValue = knownValue.strip(),
            unknownValue = unknownValue.strip(),
            knownValueCoveragePercent = coveragePercent?.strip(),
            minimumShadowCoveragePercent = MIN_SHADOW_COVERAGE_PERCENT.strip(),
            status = status,
            shadowEligible = shadowEligible
        )
    }

    private fun List<BridgePositionSnapshot>.sumKnownValue(): BigDecimal =
        fold(BigDecimal.ZERO) { total, snapshot -> total.add(snapshot.currentValue ?: BigDecimal.ZERO) }

    private fun List<BridgePositionSnapshot>.sumSnapshotIfComplete(value: (BridgePositionSnapshot) -> BigDecimal?): BigDecimal? {
        if (any { value(it) == null }) return null
        return fold(BigDecimal.ZERO) { total, snapshot -> total.add(value(snapshot)!!) }
    }

    private fun BridgePositionSnapshot.toExposurePart(
        key: String,
        source: String,
        quality: String,
        fraction: BigDecimal = BigDecimal.ONE
    ): ExposurePart {
        val value = currentValue?.multiply(fraction) ?: BigDecimal.ZERO
        val partPnl = pnl?.multiply(fraction)
        val cost = if (currentValue != null && pnl != null) currentValue!!.subtract(pnl).multiply(fraction) else null
        return ExposurePart(key, value, idKey(), source, quality, cost, partPnl, createdAt)
    }

    private fun List<ExposurePart>.sumIfComplete(value: (ExposurePart) -> BigDecimal?): BigDecimal? {
        if (any { value(it) == null }) return null
        return fold(BigDecimal.ZERO) { total, part -> total.add(value(part)!!) }
    }

    private fun BridgePositionSnapshot.idKey(): String = "${marketId ?: marketTitle}|${side.uppercase()}"

    private fun BigDecimal.strip(): String = stripTrailingZeros().toPlainString()

    private data class ExposurePart(
        val key: String,
        val value: BigDecimal,
        val positionKey: String,
        val source: String,
        val quality: String,
        val costBasis: BigDecimal?,
        val unrealizedPnl: BigDecimal?,
        val firstObservedAt: Long
    )

    companion object {
        private const val UNKNOWN = "UNKNOWN"
        private val MAX_ROUNDING_QUANTITY_GAP = BigDecimal("0.05")
        private val MAX_ROUNDING_RATIO_GAP = BigDecimal("0.02")
        private val MIN_SHADOW_COVERAGE_PERCENT = BigDecimal("95")
    }
}
