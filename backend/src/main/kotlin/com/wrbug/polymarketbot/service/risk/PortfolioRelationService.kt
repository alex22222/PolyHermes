package com.wrbug.polymarketbot.service.risk

import com.wrbug.polymarketbot.dto.*
import com.wrbug.polymarketbot.entity.BridgePositionSnapshot
import com.wrbug.polymarketbot.repository.AccountRepository
import com.wrbug.polymarketbot.repository.BridgePositionSnapshotRepository
import com.wrbug.polymarketbot.repository.MarketRepository
import com.wrbug.polymarketbot.service.copytrading.research.LeaderResearchMarketCategoryPatterns
import org.springframework.stereotype.Service
import java.math.BigDecimal

@Service
class PortfolioRelationService(
    private val accountRepository: AccountRepository,
    private val snapshotRepository: BridgePositionSnapshotRepository,
    private val marketRepository: MarketRepository,
    private val classifier: PortfolioRelationClassifier
) {
    fun getRelations(accountId: Long, now: Long = System.currentTimeMillis()): PortfolioRelationResponse {
        val snapshots = getSnapshots(accountId)
        val positions = snapshots.map { it.toPosition() }
        val relations = classifier.classify(positions, now)
        val relatedValueByType = relations.groupBy { it.type }.mapValues { (_, items) ->
            items.mapNotNull { it.relatedValue?.toBigDecimalOrNull() }.fold(BigDecimal.ZERO, BigDecimal::add).strip()
        }.toSortedMap()
        return PortfolioRelationResponse(
            accountId = accountId,
            asOf = snapshots.maxOfOrNull { it.syncedAt },
            positions = positions.map { it.toDto() },
            relations = relations.map { it.toDto() },
            countsByType = relations.groupingBy { it.type }.eachCount().toSortedMap(),
            relatedValueByType = relatedValueByType,
            generatedAt = now
        )
    }

    fun getPositions(accountId: Long): List<PortfolioRelationPosition> = getSnapshots(accountId).map { it.toPosition() }

    private fun getSnapshots(accountId: Long): List<BridgePositionSnapshot> {
        val account = accountRepository.findById(accountId).orElse(null) ?: throw IllegalArgumentException("账户不存在")
        return snapshotRepository.findByBridgeIdAndWalletAddress(BRIDGE_ID, account.walletAddress.lowercase())
    }

    private fun BridgePositionSnapshot.toPosition(): PortfolioRelationPosition {
        val market = marketId?.let(marketRepository::findByMarketId)
        val category = market?.category?.trim()?.lowercase()?.takeIf { it in CATEGORIES }
            ?: inferCategory(marketTitle)
        return PortfolioRelationPosition(
            positionKey = "${marketId ?: marketTitle}|${side.uppercase()}",
            marketId = marketId,
            eventSlug = eventSlug ?: market?.eventSlug,
            outcome = side,
            category = category,
            marketTitle = marketTitle,
            currentValue = currentValue,
            quantity = quantity,
            firstObservedAt = createdAt,
            marketEndAt = market?.endDate
        )
    }

    private fun inferCategory(title: String): String? =
        CATEGORIES.firstOrNull { LeaderResearchMarketCategoryPatterns.matches(it, title) }

    private fun PortfolioRelationPosition.toDto() = PortfolioRelationPositionDto(
        positionKey, marketId, eventSlug, outcome, category, marketTitle,
        currentValue?.strip(), quantity.strip(), firstObservedAt, marketEndAt
    )

    private fun PortfolioPositionRelation.toDto() = PortfolioPositionRelationDto(
        type, category, entityKey, positionKeys, relatedValue, unmatchedValue, confidence, rationale
    )

    private fun BigDecimal.strip() = stripTrailingZeros().toPlainString()

    companion object {
        private const val BRIDGE_ID = "polymtrade-bridge"
        private val CATEGORIES = listOf("crypto", "sports", "finance", "politics")
    }
}
