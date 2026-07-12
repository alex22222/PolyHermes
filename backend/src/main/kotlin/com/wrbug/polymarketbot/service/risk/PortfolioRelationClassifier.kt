package com.wrbug.polymarketbot.service.risk

import org.springframework.stereotype.Service
import java.math.BigDecimal

data class PortfolioRelationPosition(
    val positionKey: String,
    val marketId: String?,
    val eventSlug: String?,
    val outcome: String,
    val category: String?,
    val marketTitle: String,
    val currentValue: BigDecimal?,
    val quantity: BigDecimal,
    val firstObservedAt: Long,
    val marketEndAt: Long?
)

data class PortfolioPositionRelation(
    val type: String,
    val category: String?,
    val entityKey: String?,
    val positionKeys: List<String>,
    val relatedValue: String?,
    val unmatchedValue: String?,
    val confidence: String,
    val rationale: String
)

@Service
class PortfolioRelationClassifier {
    fun classify(positions: List<PortfolioRelationPosition>, now: Long = System.currentTimeMillis()): List<PortfolioPositionRelation> {
        val results = mutableListOf<PortfolioPositionRelation>()
        positions.forEach { position ->
            if (position.marketId.isNullOrBlank() || position.eventSlug.isNullOrBlank() || position.category.isNullOrBlank()) {
                results += single(position, "UNKNOWN", "LOW", "缺少 condition、event 或领域元数据，禁止猜测关系")
            }
            if (now - position.firstObservedAt >= longOccupiedThreshold(position.category)) {
                results += single(position, "LONG_OCCUPIED", "HIGH", "持仓持续时间超过 ${longOccupiedThreshold(position.category) / DAY_MS} 天领域阈值")
            }
        }

        for (leftIndex in positions.indices) {
            for (rightIndex in leftIndex + 1 until positions.size) {
                val left = positions[leftIndex]
                val right = positions[rightIndex]
                classifyPair(left, right)?.let(results::add)
            }
        }
        return results.sortedWith(compareBy<PortfolioPositionRelation> { TYPE_ORDER.indexOf(it.type) }.thenBy { it.positionKeys.joinToString() })
    }

    private fun classifyPair(left: PortfolioRelationPosition, right: PortfolioRelationPosition): PortfolioPositionRelation? {
        val sameMarket = !left.marketId.isNullOrBlank() && left.marketId.equals(right.marketId, true)
        val leftOutcome = normalizeOutcome(left.outcome)
        val rightOutcome = normalizeOutcome(right.outcome)
        if (sameMarket && leftOutcome == rightOutcome) {
            return pair(left, right, "DUPLICATE", entityKey(left), "HIGH", "同一 condition 且 outcome 相同，属于重复方向暴露")
        }
        if (sameMarket && leftOutcome != rightOutcome) {
            val binaryComplements = setOf(leftOutcome, rightOutcome) in BINARY_COMPLEMENTS
            return if (binaryComplements) {
                pair(left, right, "TRUE_HEDGE", entityKey(left), "HIGH", "同一二元 condition 的互斥 outcome；仅重叠价值形成锁定，剩余部分仍暴露")
            } else {
                pair(left, right, "PSEUDO_HEDGE", entityKey(left), "HIGH", "同一 condition 但不是已验证的二元互补 outcome，不能按完全抵消处理")
            }
        }

        val sameEvent = !left.eventSlug.isNullOrBlank() && left.eventSlug.equals(right.eventSlug, true)
        val sameCategory = !left.category.isNullOrBlank() && left.category.equals(right.category, true)
        val leftEntity = entityKey(left)
        val rightEntity = entityKey(right)
        if (sameEvent && left.hasDeterministicIdentity() && right.hasDeterministicIdentity()) {
            return pair(left, right, "RELATED", leftEntity ?: rightEntity, "HIGH", "同一 event 下的不同 condition，相关但不构成 condition 级对冲")
        }
        if (left.hasDeterministicIdentity() && right.hasDeterministicIdentity() &&
            sameCategory && leftEntity != null && leftEntity == rightEntity && withinDomainWindow(left, right)
        ) {
            return pair(left, right, "RELATED", leftEntity, "MEDIUM", "同领域、同标准化实体且结算时间窗口接近")
        }
        return null
    }

    private fun PortfolioRelationPosition.hasDeterministicIdentity() =
        !marketId.isNullOrBlank() && !eventSlug.isNullOrBlank() && !category.isNullOrBlank()

    private fun withinDomainWindow(left: PortfolioRelationPosition, right: PortfolioRelationPosition): Boolean {
        val category = left.category?.lowercase()
        val maxGap = when (category) {
            "crypto" -> DAY_MS
            "finance" -> 90 * DAY_MS
            "politics" -> 180 * DAY_MS
            "sports" -> 30 * DAY_MS
            else -> return false
        }
        val leftTime = left.marketEndAt ?: left.firstObservedAt
        val rightTime = right.marketEndAt ?: right.firstObservedAt
        return kotlin.math.abs(leftTime - rightTime) <= maxGap
    }

    private fun entityKey(position: PortfolioRelationPosition): String? {
        val title = position.marketTitle.uppercase()
        return when (position.category?.lowercase()) {
            "crypto" -> listOf("BTC", "BITCOIN", "ETH", "ETHEREUM", "XRP", "SOL", "SOLANA")
                .firstOrNull { Regex("\\b$it\\b").containsMatchIn(title) }
                ?.let { when (it) { "BITCOIN" -> "BTC"; "ETHEREUM" -> "ETH"; "SOLANA" -> "SOL"; else -> it } }
            "finance" -> when {
                Regex("\\b(FED|FEDERAL RESERVE|INTEREST RATE)\\b").containsMatchIn(title) -> "FED_RATES"
                Regex("\\b(CRUDE OIL|OIL|WTI|BRENT)\\b").containsMatchIn(title) -> "CRUDE_OIL"
                Regex("\\(([A-Z]{1,5})\\)").find(title) != null -> Regex("\\(([A-Z]{1,5})\\)").find(title)!!.groupValues[1]
                else -> null
            }
            "politics" -> when {
                Regex("\\b(REPUBLICAN|REPUBLICANS|GOP)\\b").containsMatchIn(title) -> "US_REPUBLICAN"
                Regex("\\b(DEMOCRAT|DEMOCRATIC|DEMOCRATS)\\b").containsMatchIn(title) -> "US_DEMOCRATIC"
                Regex("\\b(ISRAEL)\\b").containsMatchIn(title) -> "ISRAEL"
                Regex("\\b(IRAN|IRANIAN)\\b").containsMatchIn(title) -> "IRAN"
                Regex("\\b(FRANCE|FRENCH)\\b").containsMatchIn(title) -> "FRANCE"
                else -> null
            }
            "sports" -> Regex("\\b([A-Z][A-Z ]{2,20})\\b").find(title)?.value?.trim()
            else -> null
        }
    }

    private fun pair(left: PortfolioRelationPosition, right: PortfolioRelationPosition, type: String, entity: String?, confidence: String, rationale: String): PortfolioPositionRelation {
        val values = listOfNotNull(left.currentValue, right.currentValue)
        val related = if (values.size == 2) values.minOrNull() else null
        val unmatched = if (values.size == 2) values[0].subtract(values[1]).abs() else null
        return PortfolioPositionRelation(type, left.category ?: right.category, entity, listOf(left.positionKey, right.positionKey).sorted(), related?.strip(), unmatched?.strip(), confidence, rationale)
    }

    private fun single(position: PortfolioRelationPosition, type: String, confidence: String, rationale: String) =
        PortfolioPositionRelation(type, position.category, entityKey(position), listOf(position.positionKey), position.currentValue?.strip(), null, confidence, rationale)

    private fun normalizeOutcome(value: String) = value.trim().uppercase()
    private fun longOccupiedThreshold(category: String?) = when (category?.lowercase()) {
        "crypto" -> DAY_MS
        "sports" -> 14 * DAY_MS
        "finance", "politics" -> 30 * DAY_MS
        else -> 30 * DAY_MS
    }

    private fun BigDecimal.strip() = stripTrailingZeros().toPlainString()

    companion object {
        private const val DAY_MS = 24L * 60 * 60 * 1000
        private val BINARY_COMPLEMENTS = setOf(setOf("YES", "NO"), setOf("UP", "DOWN"))
        private val TYPE_ORDER = listOf("DUPLICATE", "TRUE_HEDGE", "PSEUDO_HEDGE", "RELATED", "LONG_OCCUPIED", "UNKNOWN")
    }
}
