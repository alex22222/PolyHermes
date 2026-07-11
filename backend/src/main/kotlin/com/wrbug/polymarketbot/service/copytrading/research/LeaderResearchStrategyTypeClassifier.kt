package com.wrbug.polymarketbot.service.copytrading.research

import java.math.BigDecimal

data class LeaderResearchStrategyTypeResult(
    val strategyType: String,
    val riskFlags: List<String>,
    val reason: String
)

object LeaderResearchStrategyTypeClassifier {
    const val HUMAN_DIRECTIONAL = "human_directional"
    const val WHALE = "whale"
    const val BOT_HFT = "bot_hft"
    const val MARKET_MAKER_LP = "market_maker_lp"
    const val ARBITRAGE = "arbitrage"
    const val LOW_PRICE_TAIL_RISK = "low_price_tail_risk"
    const val REBALANCE_CHURN = "rebalance_churn"
    const val UNKNOWN = "unknown"

    private val WHALE_AVG_AMOUNT = BigDecimal("1000")
    private val BOT_AVG_AMOUNT = BigDecimal("1.00")
    private val TAIL_RATIO = BigDecimal("0.50")
    private val SAFE_RATIO = BigDecimal("0.50")

    fun classify(
        totalEvents: Long,
        distinctMarkets: Long,
        buyEvents: Long,
        sellEvents: Long,
        safePriceRatio: BigDecimal,
        tailPriceRatio: BigDecimal,
        avgAmount: BigDecimal
    ): LeaderResearchStrategyTypeResult {
        val sellRatio = ratio(sellEvents, totalEvents)
        val buyRatio = ratio(buyEvents, totalEvents)
        val type = when {
            totalEvents <= 0 -> UNKNOWN
            avgAmount >= WHALE_AVG_AMOUNT && totalEvents >= 5 -> WHALE
            tailPriceRatio >= TAIL_RATIO && buyEvents > sellEvents -> LOW_PRICE_TAIL_RISK
            totalEvents >= 20 && tailPriceRatio >= BigDecimal("0.40") -> LOW_PRICE_TAIL_RISK
            totalEvents >= 100 && avgAmount > BigDecimal.ZERO && avgAmount < BOT_AVG_AMOUNT -> BOT_HFT
            totalEvents >= 50 && distinctMarkets <= 3 && buyEvents > 0 && sellEvents > 0 -> REBALANCE_CHURN
            totalEvents >= 50 &&
                avgAmount < BigDecimal("5.00") &&
                buyRatio >= BigDecimal("0.35") &&
                sellRatio >= BigDecimal("0.35") -> MARKET_MAKER_LP
            sellEvents >= 10 && buyEvents == 0L -> ARBITRAGE
            totalEvents >= 20 &&
                distinctMarkets >= 5 &&
                buyEvents > 0 &&
                sellEvents > 0 &&
                sellRatio in BigDecimal("0.10")..BigDecimal("0.70") &&
                safePriceRatio >= SAFE_RATIO -> HUMAN_DIRECTIONAL
            else -> UNKNOWN
        }
        return LeaderResearchStrategyTypeResult(
            strategyType = type,
            riskFlags = riskFlags(type),
            reason = "strategy_type=$type"
        )
    }

    fun riskFlags(strategyType: String?): List<String> {
        return when (strategyType) {
            WHALE -> listOf("strategy_whale")
            BOT_HFT -> listOf("strategy_bot_hft")
            MARKET_MAKER_LP -> listOf("strategy_market_maker_lp")
            ARBITRAGE -> listOf("strategy_arbitrage")
            LOW_PRICE_TAIL_RISK -> listOf("strategy_low_price_tail_risk")
            REBALANCE_CHURN -> listOf("strategy_rebalance_churn")
            else -> emptyList()
        }
    }

    fun isTrialReadyCopyable(strategyType: String?): Boolean {
        return trialReadyBlockerCode(strategyType) == null
    }

    fun trialReadyBlocker(strategyType: String?): String? {
        return when (strategyType) {
            WHALE -> "不可复制机制：巨鲸大额交易，本地小额跟单容易失真"
            BOT_HFT -> "不可复制机制：高频小额交易，Bridge 时效和成交质量不匹配"
            MARKET_MAKER_LP -> "不可复制机制：疑似做市/LP，买卖平衡收益不适合方向跟单"
            ARBITRAGE -> "不可复制机制：疑似套利或只卖出样本，缺少可跟随入场信号"
            LOW_PRICE_TAIL_RISK -> "不可复制机制：低价长尾铺单，固定金额跟单会放大尾部亏损"
            REBALANCE_CHURN -> "不可复制机制：短窗口反复调仓，本地跟单易高买低卖"
            else -> null
        }
    }

    fun trialReadyBlockerCode(strategyType: String?): String? {
        return when (strategyType) {
            WHALE -> "strategy_not_copyable_whale"
            BOT_HFT -> "strategy_not_copyable_bot_hft"
            MARKET_MAKER_LP -> "strategy_not_copyable_market_maker_lp"
            ARBITRAGE -> "strategy_not_copyable_arbitrage"
            LOW_PRICE_TAIL_RISK -> "strategy_not_copyable_low_price_tail_risk"
            REBALANCE_CHURN -> "strategy_not_copyable_rebalance_churn"
            else -> null
        }
    }

    private fun ratio(numerator: Long, denominator: Long): BigDecimal {
        if (denominator <= 0) return BigDecimal.ZERO
        return BigDecimal(numerator).divide(BigDecimal(denominator), 8, java.math.RoundingMode.HALF_UP)
    }
}
