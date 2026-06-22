package com.wrbug.polymarketbot.service.copytrading.scoring

import com.wrbug.polymarketbot.api.OrderbookResponse
import com.wrbug.polymarketbot.entity.CopyTrading
import com.wrbug.polymarketbot.entity.Leader
import com.wrbug.polymarketbot.util.multi
import com.wrbug.polymarketbot.util.toSafeBigDecimal
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service
import java.math.BigDecimal
import java.math.RoundingMode

/**
 * 统一跟单评分服务
 *
 * 将文档中定义的 copy_score 公式落地：
 * copy_score =
 *   leader_edge_score
 *   * market_quality
 *   * price_quality
 *   * recency
 *   * category_fit
 *   * liquidity_score
 *   - risk_penalty
 *
 * 本实现先采用加法加权模型（0-100），便于解释和调试。
 * 未来可根据 paper trading 结果校准权重。
 */
@Service
class CopyScoreService {

    private val logger = LoggerFactory.getLogger(CopyScoreService::class.java)

    /**
     * 计算 copy_score
     *
     * @param copyTrading 跟单配置
     * @param leader Leader 信息
     * @param orderbook 当前订单簿（可选）
     @param leaderTradePrice Leader 成交价
     * @param leaderTradeTimestamp Leader 交易发生时间（毫秒）
     * @param marketCategory 当前市场分类
     * @return CopyScoreResult，包含总分和拆解
     */
    fun computeCopyScore(
        copyTrading: CopyTrading,
        leader: Leader?,
        orderbook: OrderbookResponse?,
        leaderTradePrice: BigDecimal,
        leaderTradeTimestamp: Long?,
        marketCategory: String?
    ): CopyScoreResult {
        val leaderEdgeScore = computeLeaderEdgeScore(leader)
        val categoryFit = computeCategoryFit(leader, marketCategory)
        val priceQuality = computePriceQuality(copyTrading, orderbook, leaderTradePrice)
        val recency = computeRecency(copyTrading, leaderTradeTimestamp)
        val liquidityScore = computeLiquidityScore(copyTrading, orderbook)
        val marketQuality = computeMarketQuality(copyTrading, orderbook)
        val riskPenalty = computeRiskPenalty(leader)

        // 文档定义：copy_score = leader_edge_score * market_quality * price_quality * recency * category_fit * liquidity_score - risk_penalty
        val score = leaderEdgeScore
            .multiply(marketQuality)
            .multiply(priceQuality)
            .multiply(recency)
            .multiply(categoryFit)
            .multiply(liquidityScore)
            .multiply(BigDecimal("100"))
            .subtract(riskPenalty.multiply(BigDecimal("100")))
            .setScale(2, RoundingMode.HALF_UP)
            .coerceIn(BigDecimal.ZERO, BigDecimal("100"))

        val breakdown = CopyScoreBreakdown(
            leaderEdgeScore = leaderEdgeScore.setScale(4, RoundingMode.HALF_UP),
            categoryFit = categoryFit.setScale(4, RoundingMode.HALF_UP),
            priceQuality = priceQuality.setScale(4, RoundingMode.HALF_UP),
            recency = recency.setScale(4, RoundingMode.HALF_UP),
            liquidityScore = liquidityScore.setScale(4, RoundingMode.HALF_UP),
            marketQuality = marketQuality.setScale(4, RoundingMode.HALF_UP),
            riskPenalty = riskPenalty.setScale(4, RoundingMode.HALF_UP)
        )

        logger.debug(
            "copy_score computed: copyTradingId={}, score={}, breakdown={}",
            copyTrading.id, score, breakdown
        )

        return CopyScoreResult(score = score, breakdown = breakdown)
    }

    /**
     * 检查 copy_score 是否满足门控
     */
    fun isScoreAcceptable(copyTrading: CopyTrading, result: CopyScoreResult): Boolean {
        val minScore = copyTrading.minCopyScore ?: return true
        return result.score >= minScore
    }

    private fun computeLeaderEdgeScore(leader: Leader?): BigDecimal {
        val score = leader?.researchScore ?: BigDecimal("50")
        return score.divide(BigDecimal("100"), 8, RoundingMode.HALF_UP)
            .coerceIn(BigDecimal.ZERO, BigDecimal.ONE)
    }

    private fun computeCategoryFit(leader: Leader?, marketCategory: String?): BigDecimal {
        val leaderCategory = leader?.category
        if (leaderCategory.isNullOrBlank() || marketCategory.isNullOrBlank()) {
            return BigDecimal.ONE
        }
        return if (leaderCategory.equals(marketCategory, ignoreCase = true)) {
            BigDecimal.ONE
        } else {
            BigDecimal.ZERO
        }
    }

    private fun computePriceQuality(
        copyTrading: CopyTrading,
        orderbook: OrderbookResponse?,
        leaderTradePrice: BigDecimal
    ): BigDecimal {
        val maxDeviation = copyTrading.maxPriceDeviation
        if (maxDeviation == null || orderbook == null || leaderTradePrice <= BigDecimal.ZERO) {
            return BigDecimal.ONE
        }

        val bestAsk = orderbook.asks.mapNotNull { it.price.toSafeBigDecimal() }.minOrNull()
            ?: return BigDecimal.ZERO

        if (bestAsk <= leaderTradePrice) {
            return BigDecimal.ONE
        }

        val deviationPercent = bestAsk.subtract(leaderTradePrice)
            .divide(leaderTradePrice, 8, RoundingMode.HALF_UP)
            .multiply(BigDecimal("100"))

        return BigDecimal.ONE.subtract(
            deviationPercent.divide(maxDeviation, 8, RoundingMode.HALF_UP)
        ).coerceIn(BigDecimal.ZERO, BigDecimal.ONE)
    }

    private fun computeRecency(
        copyTrading: CopyTrading,
        leaderTradeTimestamp: Long?
    ): BigDecimal {
        val maxDelaySeconds = copyTrading.maxDelaySeconds
        if (maxDelaySeconds == null || leaderTradeTimestamp == null || leaderTradeTimestamp <= 0) {
            return BigDecimal.ONE
        }

        val delaySeconds = (System.currentTimeMillis() - leaderTradeTimestamp) / 1000
        if (delaySeconds <= 0) {
            return BigDecimal.ONE
        }

        return BigDecimal.ONE.subtract(
            BigDecimal(delaySeconds).divide(BigDecimal(maxDelaySeconds), 8, RoundingMode.HALF_UP)
        ).coerceIn(BigDecimal.ZERO, BigDecimal.ONE)
    }

    private fun computeLiquidityScore(
        copyTrading: CopyTrading,
        orderbook: OrderbookResponse?
    ): BigDecimal {
        val minDepth = copyTrading.minOrderDepth
        if (minDepth == null || orderbook == null || minDepth <= BigDecimal.ZERO) {
            return BigDecimal.ONE
        }

        var bidsDepth = BigDecimal.ZERO
        for (order in orderbook.bids) {
            val price = order.price.toSafeBigDecimal()
            val size = order.size.toSafeBigDecimal()
            bidsDepth = bidsDepth.add(price.multi(size))
        }

        var asksDepth = BigDecimal.ZERO
        for (order in orderbook.asks) {
            val price = order.price.toSafeBigDecimal()
            val size = order.size.toSafeBigDecimal()
            asksDepth = asksDepth.add(price.multi(size))
        }

        val totalDepth = bidsDepth.add(asksDepth)
        return totalDepth.divide(minDepth, 8, RoundingMode.HALF_UP)
            .coerceIn(BigDecimal.ZERO, BigDecimal.ONE)
    }

    private fun computeMarketQuality(
        copyTrading: CopyTrading,
        orderbook: OrderbookResponse?
    ): BigDecimal {
        val maxSpread = copyTrading.maxSpread
        if (maxSpread == null || orderbook == null || maxSpread <= BigDecimal.ZERO) {
            return BigDecimal.ONE
        }

        val bestBid = orderbook.bids.mapNotNull { it.price.toSafeBigDecimal() }.maxOrNull()
        val bestAsk = orderbook.asks.mapNotNull { it.price.toSafeBigDecimal() }.minOrNull()

        if (bestBid == null || bestAsk == null) {
            return BigDecimal.ZERO
        }

        val spread = bestAsk.subtract(bestBid)
        return BigDecimal.ONE.subtract(
            spread.divide(maxSpread, 8, RoundingMode.HALF_UP)
        ).coerceIn(BigDecimal.ZERO, BigDecimal.ONE)
    }

    private fun computeRiskPenalty(leader: Leader?): BigDecimal {
        val flags = leader?.researchRiskFlags
        if (flags.isNullOrBlank()) {
            return BigDecimal.ZERO
        }
        // 每个风险标记扣 0.05，最多扣 0.30
        val count = flags.split(",").count { it.isNotBlank() }
        return (BigDecimal("0.05") * BigDecimal(count)).coerceAtMost(BigDecimal("0.30"))
    }

    private fun BigDecimal.coerceIn(min: BigDecimal, max: BigDecimal): BigDecimal {
        return if (this < min) min else if (this > max) max else this
    }
}

/**
 * copy_score 计算结果
 */
data class CopyScoreResult(
    val score: BigDecimal,
    val breakdown: CopyScoreBreakdown
)

/**
 * copy_score 各维度拆解（均为 0-1 之间）
 */
data class CopyScoreBreakdown(
    val leaderEdgeScore: BigDecimal,
    val categoryFit: BigDecimal,
    val priceQuality: BigDecimal,
    val recency: BigDecimal,
    val liquidityScore: BigDecimal,
    val marketQuality: BigDecimal,
    val riskPenalty: BigDecimal
)
